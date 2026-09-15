"""HTTP client for api.deadlock-api.com.

Encodes three access constraints measured against the live API on 2026-09-03:

1. The default urllib/requests User-Agent is rejected by Cloudflare with a
   403 (error 1010). A browser-like UA is required.
2. Rate limits are per-endpoint and tighter than documented. The observed
   ceiling on /v1/matches/metadata was ~6 req/min against a documented 10, so
   we pace below it rather than relying on 429 handling alone.
3. Responses are large (a 200-match page is ~35 MB), so every response is
   cached on disk. Re-runs of a completed pull cost zero requests.

An API key lifts every documented limit, some of them several-fold. Set
``DEADLOCK_API_KEY`` and the key is sent and the higher pacing applied; leave
it unset and the client behaves exactly as it did before. Nothing here
requires a key.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.deadlock-api.com"

# Cloudflare rejects the default urllib/requests UA with 403 (error 1010).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# The header the API authenticates with. Read from the environment on every
# call rather than at import, so a key set after this module loads still
# takes effect. Never logged.
API_KEY_ENV = "DEADLOCK_API_KEY"
API_KEY_HEADER = "X-API-KEY"


def api_key() -> str | None:
    """The configured API key, or None when running unauthenticated."""
    return os.environ.get(API_KEY_ENV) or None


# Requests per minute, keyed by path prefix, as (anonymous, with a key).
# Both columns sit at half the documented ceiling, because the documented
# ceiling is optimistic: /v1/matches/metadata documents 10/min but 429s at ~6.
RATE_LIMITS: dict[str, tuple[float, float]] = {
    # Anonymous is also capped at 20/hr, which nothing here enforces, so the
    # unauthenticated path stays exploration-only. A key lifts the hourly cap.
    "/v1/sql": (2.0, 5.0),            # documented 2/min anon, 10/min keyed
    "/v1/matches": (5.0, 30.0),       # documented 10/min anon, 10/10s keyed
    "/v1/analytics": (100.0, 200.0),  # documented 200/400, shared across analytics
    "/v1/assets": (30.0, 30.0),       # no documented limit either way
}
DEFAULT_RATE_LIMIT = (10.0, 10.0)


class RateLimiter:
    """Token bucket enforcing a minimum interval between calls, per key."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, per_minute: float) -> None:
        interval = 60.0 / per_minute
        with self._lock:
            now = time.monotonic()
            last = self._last.get(key)
            if last is not None:
                wait = interval - (now - last)
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
            self._last[key] = now


_limiter = RateLimiter()


def _rate_key(path: str, *, keyed: bool) -> tuple[str, float]:
    """The limiter bucket for a path, and the requests/minute to pace it at."""
    column = 1 if keyed else 0
    for prefix, limits in RATE_LIMITS.items():
        if path.startswith(prefix):
            return prefix, limits[column]
    return path, DEFAULT_RATE_LIMIT[column]


def _cache_path(cache_dir: Path, path: str, params: dict[str, Any]) -> Path:
    """Stable cache filename from the path plus a hash of sorted params."""
    canonical = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(f"{path}?{canonical}".encode()).hexdigest()[:16]
    slug = path.strip("/").replace("/", "_")
    return cache_dir / f"{slug}__{digest}.json"


def get(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    cache_dir: Path | None = None,
    max_retries: int = 5,
    timeout: float = 180.0,
) -> Any:
    """GET a JSON endpoint, honoring rate limits and the on-disk cache.

    A cache hit performs no network call and consumes no rate-limit budget.
    """
    params = params or {}
    cached_at = None
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_at = _cache_path(cache_dir, path, params)
        if cached_at.exists():
            log.debug("cache hit %s", cached_at.name)
            with cached_at.open(encoding="utf-8") as fh:
                return json.load(fh)

    token = api_key()
    key, rpm = _rate_key(path, keyed=token is not None)
    url = f"{BASE_URL}{path}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token is not None:
        headers[API_KEY_HEADER] = token

    last_error: Exception | None = None
    for attempt in range(max_retries):
        _limiter.acquire(key, rpm)
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as exc:  # network flake
            last_error = exc
            backoff = min(60.0, 2.0**attempt) + random.uniform(0, 1)
            log.warning("request failed (%s), retrying in %.1fs", exc, backoff)
            time.sleep(backoff)
            continue

        if resp.status_code == 429:
            # Server knows better than our pacing; prefer its hint.
            wait = _retry_after(resp, attempt)
            log.warning("429 on %s, sleeping %.1fs", path, wait)
            time.sleep(wait)
            continue

        if resp.status_code in (401, 403):
            if token is not None:
                raise RuntimeError(
                    f"{resp.status_code} on {path} — either the User-Agent was "
                    f"blocked by Cloudflare or ${API_KEY_ENV} is rejected. "
                    f"Unset {API_KEY_ENV} to tell the two apart."
                )
            raise RuntimeError(
                f"{resp.status_code} on {path} — Cloudflare block. "
                "Check the User-Agent header."
            )

        resp.raise_for_status()
        data = resp.json()

        if cached_at is not None:
            tmp = cached_at.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh)
            tmp.replace(cached_at)  # atomic; never leave a half-written cache
        return data

    raise RuntimeError(
        f"GET {path} failed after {max_retries} attempts"
    ) from last_error


def _retry_after(resp: requests.Response, attempt: int) -> float:
    """Seconds to wait after a 429, preferring the server's own hint."""
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return float(header) + 1.0
        except ValueError:
            pass
    try:  # the API returns {"error": {"quota": {"next_request_in": N}}}
        body = resp.json()
        hint = body.get("error", {}).get("quota", {}).get("next_request_in")
        if hint is not None:
            return float(hint) + 1.0
    except Exception:
        pass
    return min(120.0, 5.0 * 2**attempt) + random.uniform(0, 1)

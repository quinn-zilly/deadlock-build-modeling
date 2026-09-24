"""HTTP client for api.deadlock-api.com.

Three things about the API, each found against the live service:

1. Cloudflare rejects the default urllib/requests User-Agent with a 403
   (error 1010), so we send a browser User-Agent.
2. Each endpoint has three rate limits: per IP, per API key (higher), and a
   global one shared with every other caller. We pace to the per-IP or
   per-key limit. The global limit can still return 429 at any rate, so we
   also handle 429s.
3. Responses are large (a 200-match page is about 92 MB, measured
   2026-09-15), so every response is cached on disk. Rerunning a finished
   pull makes no requests.

An API key is optional. Set DEADLOCK_API_KEY to send it and use the higher
limits.
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

# The key is read from the environment on every call, so a key set after
# import still works. Never log it.
API_KEY_ENV = "DEADLOCK_API_KEY"
API_KEY_HEADER = "X-API-KEY"


def api_key() -> str | None:
    """The configured API key, or None when running unauthenticated."""
    return os.environ.get(API_KEY_ENV) or None


# Requests per minute by path prefix, as (without key, with key).
#
# Only /v1/matches was measured. On 2026-09-15, ten anonymous requests
# succeeded and the eleventh returned
#   {"type":"IP","quota":{"limit":10,"period":60},"next_request_in":56}
# which matches the documented 10/min.
#
# The measured limit is set 10% below the real one, to allow for clock drift
# against the server. Unmeasured limits are set well below the documented
# ones, because too high costs a 429 and too low only costs time.
RATE_LIMITS: dict[str, tuple[float, float]] = {
    # Without a key, /v1/sql is also limited to 20 an hour. We don't enforce
    # that, so only use it for small exploratory queries.
    "/v1/sql": (2.0, 5.0),            # unmeasured; documented 2/min, 10/min keyed
    "/v1/matches": (9.0, 50.0),       # measured 10/min; documented 10req/10s keyed
    "/v1/analytics": (100.0, 200.0),  # unmeasured; documented 200/400, shared pool
    "/v1/assets": (30.0, 30.0),       # no documented limit either way
}
DEFAULT_RATE_LIMIT = (10.0, 10.0)


class RateLimiter:
    """Enforces a minimum interval between calls to each bucket."""

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
    """Cache filename for a request: the path plus a hash of the sorted params."""
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
    """GET a JSON endpoint, with rate limiting, retries, and an optional disk cache.

    A cache hit makes no request.
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
            # Wait as long as the server says. Log which limit rejected us:
            # "IP" means RATE_LIMITS is too high and should be lowered. The
            # global limit is other callers' traffic, which we can't avoid.
            wait = _retry_after(resp, attempt)
            log.warning(
                "429 on %s (%s pool), sleeping %.1fs", path, _quota_type(resp), wait
            )
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
            tmp.replace(cached_at)  # atomic, so a crash can't leave a partial file
        return data

    raise RuntimeError(
        f"GET {path} failed after {max_retries} attempts"
    ) from last_error


def _quota_type(resp: requests.Response) -> str:
    """Which limit rejected the request: "IP", "Key", "Global", or "unknown"."""
    try:  # the API returns {"error": {"type": "IP", "quota": {...}}}
        return str(resp.json().get("error", {}).get("type") or "unknown")
    except Exception:
        return "unknown"


def _retry_after(resp: requests.Response, attempt: int) -> float:
    """Seconds to wait after a 429: the server's hint if it gave one, else exponential backoff."""
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

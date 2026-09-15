"""Tests for the HTTP client's rate-limit pacing and optional API key.

An API key lifts every documented limit, so the pacing table has two columns
and the wrong one being read is a silent overrun rather than a failure. These
tests pin the column choice and the header, and make no network calls.
"""

from __future__ import annotations

import pytest

from deadlock import api


@pytest.fixture(autouse=True)
def _no_ambient_key(monkeypatch):
    """A key in the developer's own environment must not steer the tests."""
    monkeypatch.delenv(api.API_KEY_ENV, raising=False)


def test_api_key_is_none_when_unset():
    assert api.api_key() is None


def test_api_key_reads_the_environment_at_call_time(monkeypatch):
    # Set after import: a module-level constant would miss this.
    monkeypatch.setenv(api.API_KEY_ENV, "secret")
    assert api.api_key() == "secret"


def test_empty_api_key_counts_as_unset(monkeypatch):
    monkeypatch.setenv(api.API_KEY_ENV, "")
    assert api.api_key() is None


@pytest.mark.parametrize("path", ["/v1/sql", "/v1/matches/metadata", "/v1/analytics/item-stats"])
def test_a_key_never_paces_slower_than_anonymous(path):
    _, anon = api._rate_key(path, keyed=False)
    _, keyed = api._rate_key(path, keyed=True)
    assert keyed >= anon


def test_rate_key_buckets_by_prefix_not_full_path():
    bucket, _ = api._rate_key("/v1/matches/12345/metadata", keyed=False)
    assert bucket == "/v1/matches"


def test_unknown_paths_fall_back_to_the_default():
    assert api._rate_key("/v1/nope", keyed=False)[1] == api.DEFAULT_RATE_LIMIT[0]
    assert api._rate_key("/v1/nope", keyed=True)[1] == api.DEFAULT_RATE_LIMIT[1]


def test_every_documented_limit_has_both_columns():
    for prefix, limits in api.RATE_LIMITS.items():
        assert len(limits) == 2, prefix
        assert all(rpm > 0 for rpm in limits), prefix


def test_get_sends_the_key_only_when_one_is_set(monkeypatch):
    sent: list[dict[str, str]] = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def _fake_get(url, params=None, headers=None, timeout=None):
        sent.append(dict(headers))
        return _Resp()

    monkeypatch.setattr(api.requests, "get", _fake_get)
    monkeypatch.setattr(api._limiter, "acquire", lambda key, rpm: None)

    api.get("/v1/assets/ranks")
    assert api.API_KEY_HEADER not in sent[-1]

    monkeypatch.setenv(api.API_KEY_ENV, "secret")
    api.get("/v1/assets/ranks")
    assert sent[-1][api.API_KEY_HEADER] == "secret"

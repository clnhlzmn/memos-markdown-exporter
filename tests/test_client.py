"""HTTP-level tests for MemosClient using the `responses` mock library."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from memos_md_export.client import MemosClient
from memos_md_export.render import render

BASE = "http://memos:5230"


def _client(token="tok"):
    return MemosClient(BASE, token, verify_tls=True)


@responses.activate
def test_current_user_parses_name_and_username():
    responses.add(
        responses.GET,
        f"{BASE}/api/v1/auth/me",
        json={"user": {"name": "users/7", "username": "alice"}},
        status=200,
    )
    user = _client().current_user()
    assert user["name"] == "users/7"
    assert user["username"] == "alice"
    # Authorization header was sent
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"


@responses.activate
def test_current_user_missing_name_raises():
    responses.add(
        responses.GET, f"{BASE}/api/v1/auth/me", json={"user": {}}, status=200
    )
    with pytest.raises(RuntimeError):
        _client().current_user()


@responses.activate
def test_list_memos_follows_next_page_token_and_sends_filter():
    seen_filters = []

    def cb(request):
        qs = parse_qs(urlparse(request.url).query)
        seen_filters.append(qs["filter"][0])
        token = qs.get("pageToken", [""])[0]
        if not token:
            body = {
                "memos": [{"name": "memos/a", "creator": "users/1",
                           "content": "one"}],
                "nextPageToken": "PAGE2",
            }
        else:
            assert token == "PAGE2"
            body = {
                "memos": [{"name": "memos/b", "creator": "users/1",
                           "content": "two"}],
                "nextPageToken": "",
            }
        return (200, {}, json.dumps(body))

    responses.add_callback(
        responses.GET, f"{BASE}/api/v1/memos",
        callback=cb, content_type="application/json",
    )

    memos = _client().list_memos("users/1", archived=False)
    assert [m["name"] for m in memos] == ["memos/a", "memos/b"]
    # both pages carried the creator-scoped filter
    assert seen_filters == ['creator == "users/1"', 'creator == "users/1"']


@responses.activate
def test_list_memos_drops_foreign_creator():
    body = {
        "memos": [
            {"name": "memos/mine", "creator": "users/1", "content": "ok"},
            {"name": "memos/theirs", "creator": "users/2", "content": "leak"},
        ],
        "nextPageToken": "",
    }
    responses.add(responses.GET, f"{BASE}/api/v1/memos", json=body, status=200)
    memos = _client().list_memos("users/1", archived=False)
    assert [m["name"] for m in memos] == ["memos/mine"]


@responses.activate
def test_list_memos_state_normal_vs_archived():
    captured = {}

    def cb(request):
        qs = parse_qs(urlparse(request.url).query)
        captured["state"] = qs["state"][0]
        return (200, {}, json.dumps({"memos": [], "nextPageToken": ""}))

    responses.add_callback(
        responses.GET, f"{BASE}/api/v1/memos",
        callback=cb, content_type="application/json",
    )
    _client().list_memos("users/1", archived=True)
    assert captured["state"] == "ARCHIVED"


@responses.activate
def test_memo_with_attachments_round_trips_into_frontmatter():
    body = {
        "memos": [{
            "name": "memos/withatt",
            "creator": "users/1",
            "createTime": "2026-07-11T00:00:00Z",
            "updateTime": "2026-07-11T00:00:00Z",
            "content": "see attachment",
            "attachments": [{
                "name": "attachments/att1",
                "filename": "photo.png",
                "type": "image/png",
                "size": "2048",
            }],
        }],
        "nextPageToken": "",
    }
    responses.add(responses.GET, f"{BASE}/api/v1/memos", json=body, status=200)
    memos = _client().list_memos("users/1", archived=False)
    out = render(memos[0])
    assert "attachments:" in out
    assert '  - filename: "photo.png"' in out
    assert "    uid: att1" in out
    assert "    type: image/png" in out
    assert "    size: 2048" in out
    assert '    url: "/file/attachments/att1/photo.png"' in out

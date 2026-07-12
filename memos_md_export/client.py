"""HTTP client for the memos API (auth/me + paginated list_memos)."""

from __future__ import annotations

import requests

PAGE_SIZE = 1000  # API max; fewer round-trips


class MemosClient:
    def __init__(self, base_url: str, token: str, verify_tls: bool) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.verify = verify_tls

    def current_user(self) -> dict:
        r = self.session.get(f"{self.base_url}/api/v1/auth/me", timeout=30)
        r.raise_for_status()
        user = r.json().get("user") or {}
        if not user.get("name"):
            raise RuntimeError("auth/me returned no user; token invalid?")
        return user

    def list_memos(self, creator: str, archived: bool) -> list[dict]:
        """Return all memos created by `creator` (e.g. 'users/1')."""
        memos: list[dict] = []
        page_token = ""
        params_base = {
            "pageSize": PAGE_SIZE,
            "state": "ARCHIVED" if archived else "NORMAL",
            # server-side scope to this creator; we also guard client-side below
            "filter": f'creator == "{creator}"',
        }
        while True:
            params = dict(params_base)
            if page_token:
                params["pageToken"] = page_token
            r = self.session.get(
                f"{self.base_url}/api/v1/memos", params=params, timeout=60
            )
            r.raise_for_status()
            body = r.json()
            batch = body.get("memos") or []
            for m in batch:
                # defense in depth: never misfile another user's memo even if
                # the server-side filter were ignored by some build.
                if m.get("creator") == creator:
                    memos.append(m)
            page_token = body.get("nextPageToken", "")
            if not page_token:
                break
        return memos

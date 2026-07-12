"""Tests for filesystem sync: write_if_changed, prune_user, sync_once."""

from __future__ import annotations

import os
from datetime import timezone

import memos_md_export.sync as sync
from memos_md_export.sync import prune_user, sync_once, write_if_changed


# --------------------------------------------------------------------------- #
# write_if_changed
# --------------------------------------------------------------------------- #
def test_write_if_changed_creates_file(tmp_path):
    p = tmp_path / "a" / "b.md"
    write_if_changed(str(p), "hello\n")
    assert p.read_text() == "hello\n"


def test_write_if_changed_unchanged_leaves_mtime(tmp_path):
    p = tmp_path / "b.md"
    write_if_changed(str(p), "same\n")
    before = os.stat(p).st_mtime_ns
    # rewrite identical content: must be a no-op (no rewrite)
    write_if_changed(str(p), "same\n")
    after = os.stat(p).st_mtime_ns
    assert before == after


def test_write_if_changed_changed_rewrites(tmp_path):
    p = tmp_path / "b.md"
    write_if_changed(str(p), "one\n")
    write_if_changed(str(p), "two\n")
    assert p.read_text() == "two\n"


def test_write_if_changed_atomic_no_tmp_left(tmp_path):
    p = tmp_path / "b.md"
    write_if_changed(str(p), "x\n")
    assert not (tmp_path / "b.md.tmp").exists()


# --------------------------------------------------------------------------- #
# prune_user
# --------------------------------------------------------------------------- #
def test_prune_removes_orphans_keeps_written_cleans_dirs(tmp_path):
    root = tmp_path / "alice"
    keep = root / "2026-07-11" / "a.md"
    orphan = root / "2026-07-10" / "b.md"
    for f in (keep, orphan):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n")

    prune_user(str(root), {os.path.abspath(str(keep))})

    assert keep.exists()
    assert not orphan.exists()
    # the now-empty date dir is removed bottom-up
    assert not (root / "2026-07-10").exists()
    # the kept dir and root remain
    assert (root / "2026-07-11").exists()


def test_prune_noop_on_missing_root(tmp_path):
    # must not raise
    prune_user(str(tmp_path / "does-not-exist"), set())


def test_prune_ignores_non_md_files(tmp_path):
    root = tmp_path / "alice"
    root.mkdir()
    other = root / "notes.txt"
    other.write_text("keep me\n")
    prune_user(str(root), set())
    assert other.exists()


# --------------------------------------------------------------------------- #
# sync_once
# --------------------------------------------------------------------------- #
class _FakeClient:
    """Stand-in for MemosClient keyed by token."""

    behaviors: dict = {}

    def __init__(self, base_url, token, verify_tls):
        self.token = token

    def current_user(self):
        beh = _FakeClient.behaviors[self.token]
        if beh.get("fail"):
            raise RuntimeError("boom: token revoked")
        return {"name": beh["creator"], "username": beh["username"]}

    def list_memos(self, creator, archived):
        if archived:
            return []
        return _FakeClient.behaviors[self.token]["memos"]


class _Cfg:
    def __init__(self, export_dir):
        self.export_dir = export_dir
        self.base_url = "http://memos:5230"
        self.verify_tls = True
        self.date_basis = "created"
        self.tz = timezone.utc
        self.include_archived = False
        self.interval = None


def test_sync_failing_token_does_not_prune_and_returns_nonzero(
    tmp_path, monkeypatch
):
    export = tmp_path / "export"
    export.mkdir()

    # Pre-existing file for the user whose token will fail. It must survive.
    bob_root = export / "bob"
    bob_file = bob_root / "2026-07-01" / "old.md"
    bob_file.parent.mkdir(parents=True)
    bob_file.write_text("precious\n")

    _FakeClient.behaviors = {
        "good": {
            "creator": "users/1",
            "username": "alice",
            "memos": [{
                "name": "memos/m1",
                "creator": "users/1",
                "createTime": "2026-07-11T00:00:00Z",
                "updateTime": "2026-07-11T00:00:00Z",
                "content": "hi",
            }],
        },
        "bad": {"fail": True},
    }
    monkeypatch.setattr(sync, "MemosClient", _FakeClient)

    cfg = _Cfg(str(export))
    cfg.tokens = ["good", "bad"]

    rc = sync_once(cfg)

    # one token failed -> non-zero
    assert rc == 1
    # failed user's files untouched (NOT pruned)
    assert bob_file.exists()
    assert bob_file.read_text() == "precious\n"
    # good token synced and wrote its memo
    assert (export / "alice" / "2026-07-11" / "m1.md").exists()


def test_sync_all_success_returns_zero_and_prunes(tmp_path, monkeypatch):
    export = tmp_path / "export"
    export.mkdir()

    # stale orphan for alice from a previous run
    stale = export / "alice" / "2026-01-01" / "gone.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n")

    _FakeClient.behaviors = {
        "good": {
            "creator": "users/1",
            "username": "alice",
            "memos": [{
                "name": "memos/m1",
                "creator": "users/1",
                "createTime": "2026-07-11T00:00:00Z",
                "updateTime": "2026-07-11T00:00:00Z",
                "content": "hi",
            }],
        },
    }
    monkeypatch.setattr(sync, "MemosClient", _FakeClient)

    cfg = _Cfg(str(export))
    cfg.tokens = ["good"]

    rc = sync_once(cfg)

    assert rc == 0
    assert (export / "alice" / "2026-07-11" / "m1.md").exists()
    # orphan pruned, empty dir cleaned
    assert not stale.exists()
    assert not (export / "alice" / "2026-01-01").exists()

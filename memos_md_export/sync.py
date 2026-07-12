"""Filesystem sync: write-if-changed, per-user prune, the sync loop, and main."""

from __future__ import annotations

import logging
import os
import sys
import time

from .client import MemosClient
from .config import Config
from .render import date_dir, memo_uid, render, safe

log = logging.getLogger("memos-export")


def write_if_changed(path: str, content: str) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == content:
                return
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)  # atomic


def prune_user(user_root: str, written: set[str]) -> None:
    """Remove .md files under user_root we didn't write, then empty dirs."""
    if not os.path.isdir(user_root):
        return
    for dirpath, _dirs, files in os.walk(user_root):
        for fn in files:
            if fn.endswith(".md"):
                p = os.path.join(dirpath, fn)
                if os.path.abspath(p) not in written:
                    try:
                        os.remove(p)
                    except OSError as e:
                        log.error("prune failed for %s: %s", p, e)
    # remove now-empty directories, deepest first
    for dirpath, _dirs, _files in sorted(
        os.walk(user_root), key=lambda x: len(x[0]), reverse=True
    ):
        if dirpath == user_root:
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError:
            pass


def sync_once(cfg: Config) -> int:
    """Return process exit code (0 = all tokens synced, 1 = at least one failed)."""
    os.makedirs(cfg.export_dir, exist_ok=True)
    failures = 0

    for idx, token in enumerate(cfg.tokens, 1):
        client = MemosClient(cfg.base_url, token, cfg.verify_tls)
        try:
            user = client.current_user()
            creator = user["name"]                 # users/<id>
            username = user.get("username") or creator.split("/")[-1]
            user_root = os.path.join(cfg.export_dir, safe(username))

            written: set[str] = set()
            memos = client.list_memos(creator, archived=False)
            if cfg.include_archived:
                memos += [dict(m, _archived=True)
                          for m in client.list_memos(creator, archived=True)]

            for memo in memos:
                sub = "_archived" if memo.get("_archived") else ""
                parts = [user_root]
                if sub:
                    parts.append(sub)
                parts += [date_dir(memo, cfg.date_basis, cfg.tz),
                          safe(memo_uid(memo)) + ".md"]
                path = os.path.join(*parts)
                write_if_changed(path, render(memo))
                written.add(os.path.abspath(path))

            # Only prune THIS user's tree, and only because their sync succeeded.
            prune_user(user_root, written)
            log.info("synced %s: %d memos", username, len(written))

        except Exception as e:  # noqa: BLE001 - keep going for other users
            failures += 1
            log.error("token #%d failed (%s); leaving that user's files intact",
                      idx, e)

    if failures:
        log.warning("%d/%d token(s) failed; their mirrors were not pruned",
                    failures, len(cfg.tokens))
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    cfg = Config()
    if cfg.interval is None:
        return sync_once(cfg)
    log.info("looping every %ds", cfg.interval)
    while True:
        try:
            sync_once(cfg)
        except Exception as e:  # noqa: BLE001
            log.error("run failed: %s", e)
        time.sleep(cfg.interval)


if __name__ == "__main__":
    sys.exit(main())

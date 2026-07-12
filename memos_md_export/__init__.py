"""Mirror a memos (usememos.com) instance to a directory of markdown files.

One-way sync over the HTTP API: new memos become files, deleted/archived memos
have their files pruned, unchanged memos are left untouched (mtimes preserved).

See the package modules:
  config  -- environment parsing (Config)
  client  -- MemosClient (auth/me, list_memos pagination)
  render  -- parse_time, memo_uid, date_dir, extract_attachments, render, safe
  sync    -- sync_once, prune_user, write_if_changed, main loop
"""

__version__ = "0.1.0"

"""Pure rendering + path-safety helpers.

Turns a memo dict (protojson, camelCase field names) into the markdown file
body with YAML frontmatter, plus filesystem-safety helpers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

# Inline markdown link/image: keep the visible text/alt, drop the target.
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_SLUG_TRIM = re.compile(r"[^a-z0-9]+")
_SLUG_MAX = 50


def parse_time(value) -> datetime:
    """Parse an RFC3339 timestamp (protojson) into an aware UTC datetime."""
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if isinstance(value, (int, float)):  # tolerate epoch, just in case
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def memo_uid(memo: dict) -> str:
    name = memo.get("name", "")  # "memos/<uid>"
    return name.split("/")[-1] if "/" in name else name


def date_dir(memo: dict, basis: str, tz) -> str:
    created = parse_time(memo["createTime"])
    updated = parse_time(memo["updateTime"])
    dt = updated if basis == "updated" else created
    return dt.astimezone(tz).strftime("%Y-%m-%d")


def _slugify(text: str) -> str:
    """Lowercase, hyphenate, ASCII-only; truncated to _SLUG_MAX on a word edge."""
    slug = _SLUG_TRIM.sub("-", text.lower()).strip("-")
    if len(slug) <= _SLUG_MAX:
        return slug
    slug = slug[:_SLUG_MAX]
    # Prefer cutting at the last hyphen so we don't split a word, unless that
    # would throw away almost everything.
    cut = slug.rfind("-")
    if cut >= _SLUG_MAX // 2:
        slug = slug[:cut]
    return slug.strip("-")


def title_slug(memo: dict) -> str:
    """Filename fragment: the memo's first non-empty line, slugified.

    Returns "" for empty memos so the caller can omit the segment.
    """
    content = memo.get("content", "") or ""
    chosen = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
    chosen = _LINK.sub(r"\1", chosen)  # links/images -> visible text
    return _slugify(chosen)


def extract_attachments(memo: dict) -> list[dict]:
    """Normalize a memo's attachments into stable, sorted dicts.

    The API exposes filename, uid, MIME type, size, and (for external/S3
    attachments) an external link. It does NOT expose the internal on-disk
    path, so we emit the original filename plus the server-relative serving
    path `/file/attachments/<uid>/<filename>`. For LOCAL storage the file lives
    in the memos assets directory and ends with this filename; see the README
    for exact-path resolution options.
    """
    out: list[dict] = []
    for a in memo.get("attachments", []):
        name = a.get("name", "")              # attachments/<uid>
        a_uid = name.split("/")[-1] if "/" in name else name
        filename = a.get("filename", "")
        rec = {
            "filename": filename,
            "uid": a_uid,
            "type": a.get("type", ""),
            # protojson encodes int64 as a string; coerce back to int.
            "size": _coerce_int(a.get("size")),
        }
        ext = a.get("externalLink")
        if ext:
            rec["external_link"] = ext
        elif a_uid and filename:
            rec["url"] = f"/file/attachments/{a_uid}/{filename}"
        out.append(rec)
    # Stable order so unchanged memos don't churn the file.
    out.sort(key=lambda r: (r["filename"], r["uid"]))
    return out


def _coerce_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _yaml_str(s: str) -> str:
    """A safe YAML double-quoted scalar. JSON string syntax is valid YAML."""
    return json.dumps(s, ensure_ascii=False)


def render(memo: dict, tz=timezone.utc) -> str:
    uid = memo_uid(memo)
    created = parse_time(memo["createTime"]).astimezone(tz)
    updated = parse_time(memo["updateTime"]).astimezone(tz)
    visibility = memo.get("visibility", "PRIVATE")
    pinned = bool(memo.get("pinned"))
    content = memo.get("content", "")
    tags = memo.get("tags", [])
    attachments = extract_attachments(memo)

    lines = ["---", f"uid: {uid}",
             f"created: {created.isoformat(timespec='seconds')}",
             f"updated: {updated.isoformat(timespec='seconds')}",
             f"visibility: {visibility}", f"pinned: {str(pinned).lower()}"]
    if tags:
        lines.append("tags:")
        lines += [f"  - {t}" for t in sorted(tags)]
    if attachments:
        lines.append("attachments:")
        for a in attachments:
            lines.append(f"  - filename: {_yaml_str(a['filename'])}")
            lines.append(f"    uid: {a['uid']}")
            if a["type"]:
                lines.append(f"    type: {a['type']}")
            lines.append(f"    size: {a['size']}")
            if "url" in a:
                lines.append(f"    url: {_yaml_str(a['url'])}")
            if "external_link" in a:
                lines.append(f"    external_link: {_yaml_str(a['external_link'])}")
    lines += ["---", ""]
    body = "\n".join(lines) + "\n" + content
    if not body.endswith("\n"):
        body += "\n"
    return body


def safe(seg: str) -> str:
    seg = UNSAFE.sub("_", seg or "")
    return seg if seg not in ("", ".", "..") else "_"

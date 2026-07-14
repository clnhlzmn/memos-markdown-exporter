"""Tests for the pure rendering + path-safety helpers."""

from __future__ import annotations

from datetime import timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from memos_md_export.render import (
    date_dir,
    extract_attachments,
    memo_uid,
    parse_time,
    render,
    safe,
    title_slug,
)


# --------------------------------------------------------------------------- #
# parse_time
# --------------------------------------------------------------------------- #
def test_parse_time_with_z():
    dt = parse_time("2026-07-11T14:30:00Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(None)
    assert dt.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-07-11T14:30:00Z"


def test_parse_time_with_offset_normalized_to_utc():
    # 14:30 at +02:00 == 12:30 UTC
    dt = parse_time("2026-07-11T14:30:00+02:00")
    assert dt.strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-07-11T12:30:00Z"


def test_parse_time_epoch_int():
    dt = parse_time(0)
    assert dt == parse_time(None)
    assert dt.strftime("%Y-%m-%dT%H:%M:%SZ") == "1970-01-01T00:00:00Z"


def test_parse_time_epoch_float():
    dt = parse_time(1_000_000_000.0)
    assert dt.tzinfo is not None
    assert dt.strftime("%Y") == "2001"


def test_parse_time_garbage_falls_back_to_epoch():
    dt = parse_time("not-a-timestamp")
    assert dt.strftime("%Y-%m-%dT%H:%M:%SZ") == "1970-01-01T00:00:00Z"


def test_parse_time_empty_is_epoch():
    assert parse_time("").strftime("%Y") == "1970"
    assert parse_time(None).strftime("%Y") == "1970"


# --------------------------------------------------------------------------- #
# memo_uid
# --------------------------------------------------------------------------- #
def test_memo_uid_from_resource_name():
    assert memo_uid({"name": "memos/abc123"}) == "abc123"


def test_memo_uid_bare_id():
    assert memo_uid({"name": "abc123"}) == "abc123"


def test_memo_uid_missing():
    assert memo_uid({}) == ""


# --------------------------------------------------------------------------- #
# date_dir
# --------------------------------------------------------------------------- #
def test_date_dir_created_vs_updated_pick_different_days():
    memo = {
        "createTime": "2026-07-10T10:00:00Z",
        "updateTime": "2026-07-11T10:00:00Z",
    }
    assert date_dir(memo, "created", timezone.utc) == "2026-07-10"
    assert date_dir(memo, "updated", timezone.utc) == "2026-07-11"


def test_date_dir_timezone_shifts_bucket_across_midnight():
    # ~02:30Z is the previous evening in America/New_York (UTC-4/-5),
    # so the local date bucket is the day before.
    assert ZoneInfo is not None
    memo = {"createTime": "2026-07-11T02:30:00Z",
            "updateTime": "2026-07-11T02:30:00Z"}
    tz = ZoneInfo("America/New_York")
    assert date_dir(memo, "created", tz) == "2026-07-10"
    assert date_dir(memo, "created", timezone.utc) == "2026-07-11"


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
def _base_memo(**over):
    memo = {
        "name": "memos/abc",
        "createTime": "2026-07-10T09:00:00Z",
        "updateTime": "2026-07-11T09:00:00Z",
        "visibility": "PUBLIC",
        "pinned": True,
        "content": "hello world",
        "tags": ["zeta", "alpha", "mango"],
    }
    memo.update(over)
    return memo


def test_render_frontmatter_shape_and_ordering():
    out = render(_base_memo())
    lines = out.splitlines()
    assert lines[0] == "---"
    assert lines[1] == "uid: abc"
    assert lines[2] == "created: 2026-07-10T09:00:00+00:00"
    assert lines[3] == "updated: 2026-07-11T09:00:00+00:00"
    assert lines[4] == "visibility: PUBLIC"
    assert lines[5] == "pinned: true"


def test_render_frontmatter_respects_timezone():
    tz = ZoneInfo("America/New_York")  # UTC-4 in July (DST)
    lines = render(_base_memo(), tz).splitlines()
    assert lines[2] == "created: 2026-07-10T05:00:00-04:00"
    assert lines[3] == "updated: 2026-07-11T05:00:00-04:00"


def test_render_tags_sorted():
    out = render(_base_memo())
    assert "tags:\n  - alpha\n  - mango\n  - zeta" in out


def test_render_pinned_false_lowercase():
    out = render(_base_memo(pinned=False))
    assert "pinned: false" in out


def test_render_trailing_newline_and_content():
    out = render(_base_memo(content="body text"))
    assert out.endswith("\n")
    assert out.endswith("---\n\nbody text\n")


def test_render_defaults_visibility_private():
    memo = _base_memo()
    del memo["visibility"]
    assert "visibility: PRIVATE" in render(memo)


def test_render_no_tags_omits_key():
    memo = _base_memo(tags=[])
    assert "tags:" not in render(memo)


# --------------------------------------------------------------------------- #
# attachments
# --------------------------------------------------------------------------- #
def test_attachments_sorted_by_filename_then_uid():
    memo = {
        "attachments": [
            {"name": "attachments/u2", "filename": "b.png", "type": "image/png",
             "size": 10},
            {"name": "attachments/u1", "filename": "a.png", "type": "image/png",
             "size": 20},
        ]
    }
    atts = extract_attachments(memo)
    assert [a["filename"] for a in atts] == ["a.png", "b.png"]


def test_attachments_size_string_coerced_to_int():
    memo = {"attachments": [
        {"name": "attachments/u1", "filename": "a.bin", "size": "12345"}]}
    atts = extract_attachments(memo)
    assert atts[0]["size"] == 12345
    assert isinstance(atts[0]["size"], int)


def test_attachments_local_gets_serving_url():
    memo = {"attachments": [
        {"name": "attachments/u1", "filename": "a.png", "type": "image/png",
         "size": 1}]}
    atts = extract_attachments(memo)
    assert atts[0]["url"] == "/file/attachments/u1/a.png"
    assert "external_link" not in atts[0]


def test_attachments_external_emits_link_no_url():
    memo = {"attachments": [
        {"name": "attachments/u1", "filename": "a.png", "size": 1,
         "externalLink": "https://s3.example.com/a.png"}]}
    atts = extract_attachments(memo)
    assert atts[0]["external_link"] == "https://s3.example.com/a.png"
    assert "url" not in atts[0]


def test_attachments_yaml_special_chars_quoted_in_render():
    memo = _base_memo(attachments=[
        {"name": "attachments/u1", "filename": "my: file name.png",
         "type": "image/png", "size": 1}])
    out = render(memo)
    assert '  - filename: "my: file name.png"' in out
    # the url contains the raw filename and must also be quoted
    assert '    url: "/file/attachments/u1/my: file name.png"' in out


def test_render_no_attachments_omits_key():
    assert "attachments:" not in render(_base_memo())


def test_render_attachment_block_full_shape():
    memo = _base_memo(tags=[], attachments=[
        {"name": "attachments/u1", "filename": "a.png", "type": "image/png",
         "size": "7"}])
    out = render(memo)
    assert "attachments:\n" in out
    assert "  - filename: \"a.png\"" in out
    assert "    uid: u1" in out
    assert "    type: image/png" in out
    assert "    size: 7" in out


# --------------------------------------------------------------------------- #
# title_slug
# --------------------------------------------------------------------------- #
def test_title_slug_uses_first_nonempty_line():
    memo = {"content": "#todo #home\n# Weekly Review\nsome body text"}
    assert title_slug(memo) == "todo-home"


def test_title_slug_heading_hash_is_slugified_like_any_line():
    assert title_slug({"content": "# Groceries\n#todo"}) == "groceries"


def test_title_slug_deeper_heading_hash_dropped():
    assert title_slug({"content": "### A Sub Heading"}) == "a-sub-heading"


def test_title_slug_tags_are_kept_in_slug():
    memo = {"content": "#idea just some plain text here"}
    assert title_slug(memo) == "idea-just-some-plain-text-here"


def test_title_slug_tag_line_is_used_not_skipped():
    memo = {"content": "#todo #home\n#work\nActual content line"}
    assert title_slug(memo) == "todo-home"


def test_title_slug_tags_only_still_produces_slug():
    assert title_slug({"content": "#todo #home\n#work"}) == "todo-home"


def test_title_slug_skips_leading_blank_lines():
    assert title_slug({"content": "\n\nHello world"}) == "hello-world"


def test_title_slug_empty_content_returns_empty():
    assert title_slug({"content": ""}) == ""
    assert title_slug({}) == ""


def test_title_slug_strips_emphasis_and_links():
    memo = {"content": "**Bold** _title_ with [a link](https://ex.com) end"}
    assert title_slug(memo) == "bold-title-with-a-link-end"


def test_title_slug_image_reduces_to_alt_text():
    assert title_slug({"content": "![my photo](x.png) caption"}) == \
        "my-photo-caption"


def test_title_slug_truncates_long_title_on_word_boundary():
    memo = {"content": "# " + " ".join(["word"] * 20)}
    slug = title_slug(memo)
    assert len(slug) <= 50
    # cut at a hyphen -> no trailing partial "wor"
    assert not slug.endswith("-")
    assert slug.split("-")[-1] == "word"


def test_title_slug_non_ascii_dropped():
    # accents/CJK are not in [a-z0-9]; they collapse to separators.
    assert title_slug({"content": "# Café Über"}) == "caf-ber"


def test_title_slug_first_line_wins_over_later_lines():
    # No heading/tag special-casing: the first non-empty line is used as-is.
    memo = {"content": "#weekly\nreal title"}
    assert title_slug(memo) == "weekly"


# --------------------------------------------------------------------------- #
# safe
# --------------------------------------------------------------------------- #
def test_safe_slash_neutralized():
    assert "/" not in safe("a/b")
    assert safe("a/b") == "a_b"


def test_safe_dotdot_neutralized():
    assert safe("..") == "_"
    assert safe(".") == "_"


def test_safe_empty_neutralized():
    assert safe("") == "_"
    assert safe(None) == "_"


def test_safe_keeps_allowed_chars():
    assert safe("Abc-123_x.y") == "Abc-123_x.y"

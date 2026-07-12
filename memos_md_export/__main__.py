"""Entrypoint: ``python -m memos_md_export``."""

from __future__ import annotations

import sys

from .sync import main

if __name__ == "__main__":
    sys.exit(main())

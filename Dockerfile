FROM python:3.12-slim

# Runtime dependency only; the package itself is pure-Python and copied below.
RUN pip install --no-cache-dir "requests>=2.31,<3"

WORKDIR /app
COPY memos_md_export/ /app/memos_md_export/

# Static OCI labels; the release workflow adds/overrides these via metadata-action.
LABEL org.opencontainers.image.title="memos-md-export" \
      org.opencontainers.image.description="One-way sync of a memos instance to markdown files." \
      org.opencontainers.image.source="https://github.com/clnhlzmn/memos-markdown-exporter" \
      org.opencontainers.image.licenses="MIT"

# Runs as root by default so the export volume can be owned by any host uid.
# Override with `--user PUID:PGID` (Unraid style); the export dir must then be
# writable by that uid/gid. Do NOT bake a fixed owner into the image.
ENTRYPOINT ["python", "-m", "memos_md_export"]

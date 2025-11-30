from __future__ import annotations

import html
import pathlib
from datetime import datetime
from typing import Dict, Optional

from aiohttp import web

from config import EXTERNAL_URL, HTTP_HOST, HTTP_PORT

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".log",
    ".json",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
}


def human_readable_size(size: int) -> str:
    size = float(size or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def format_timestamp(ts: Optional[int]) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y/%m/%d %H:%M:%S")
    except Exception:
        return "-"


def render_template(path: pathlib.Path, replacements: Dict[str, str]) -> str:
    template = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


def build_preview_payload(
    path: pathlib.Path, filename: str, mime_type: Optional[str]
) -> Dict[str, object]:
    file_ext = pathlib.Path(filename).suffix.lower()
    if (mime_type and mime_type.startswith("image/")) or (file_ext in IMAGE_EXTENSIONS):
        return {"kind": "image"}
    if (mime_type and mime_type.startswith("video/")) or (file_ext in VIDEO_EXTENSIONS):
        return {"kind": "video"}
    if (mime_type and mime_type.startswith("audio/")) or (file_ext in AUDIO_EXTENSIONS):
        return {"kind": "audio"}
    if mime_type == "application/pdf" or file_ext == ".pdf":
        return {"kind": "pdf"}
    if (
        mime_type and (mime_type.startswith("text/") or mime_type == "application/json")
    ) or file_ext in TEXT_EXTENSIONS:
        snippet = ""
        has_more = False
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                snippet = f.read(4000)
                if f.read(1):
                    has_more = True
        except Exception:
            snippet = ""
        if snippet:
            return {"kind": "text", "snippet": snippet, "truncated": has_more}
    return {"kind": "none"}


def make_file_url(request: web.Request, token: str) -> str:
    if EXTERNAL_URL:
        base = EXTERNAL_URL.rstrip("/")
        return f"{base}/files/{token}"
    scheme = request.scheme
    host = request.headers.get("Host") or f"{HTTP_HOST}:{HTTP_PORT}"
    return f"{scheme}://{host}/files/{token}"


def public_base_url() -> str:
    if EXTERNAL_URL:
        return EXTERNAL_URL.rstrip("/")
    return f"http://{HTTP_HOST}:{HTTP_PORT}"


def file_page_url(token: str) -> str:
    base = public_base_url().rstrip("/")
    return f"{base}/files/{token}"


def client_ip_from_request(request: web.Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    peer = request.transport.get_extra_info("peername")
    if peer:
        return peer[0]
    return "unknown"


def escape_filename(name: str) -> str:
    return html.escape(name)

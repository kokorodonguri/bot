from __future__ import annotations

import json
import os
import pathlib
import secrets

from dotenv import load_dotenv

# Load environment variables as early as possible so that other modules can
# import configuration constants without worrying about calling load_dotenv().
load_dotenv()

ROOT = pathlib.Path(__file__).parent
WEBSITE_DIR = ROOT / "website"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = ROOT / "file_index.json"
UPLOAD_PAGE = WEBSITE_DIR / "upload.html"
DOWNLOAD_PAGE = WEBSITE_DIR / "download.html"
PREVIEW_TEMPLATE = WEBSITE_DIR / "preview.html"
LISTING_PAGE = WEBSITE_DIR / "listing.html"
LISTING_NOT_FOUND_PAGE = WEBSITE_DIR / "listing_not_found.html"
LISTING_LOGIN_DIR = WEBSITE_DIR / "login"
LISTING_LOGIN_PAGE = LISTING_LOGIN_DIR / "index.html"
LISTING_LOGIN_ASSETS_DIR = LISTING_LOGIN_DIR / "assets"
ASSETS_DIR = WEBSITE_DIR / "assets"
TOKEN_PATH = ROOT / "token.txt"

HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
HTTP_LISTING_PORT = int(os.getenv("HTTP_LISTING_PORT", "8004"))
HTTP_LOGIN_PORT = int(os.getenv("HTTP_LOGIN_PORT", "8080"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024 * 1024)))
EXTERNAL_URL = os.getenv("EXTERNAL_URL")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://upload.dongurihub.jp")
LISTING_HOME_URL = os.getenv("LISTING_HOME_URL", "/")
LISTING_USERNAME = os.getenv("LISTING_USERNAME")
LISTING_PASSWORD = os.getenv("LISTING_PASSWORD")
LISTING_SESSION_SECRET = os.getenv("LISTING_SESSION_SECRET") or secrets.token_hex(32)
LISTING_SESSION_TTL = int(os.getenv("LISTING_SESSION_TTL", str(12 * 60 * 60)))
MAX_IP_STORAGE_BYTES = int(
    os.getenv("MAX_IP_STORAGE_BYTES", str(80 * 1024 * 1024 * 1024))
)

LISTING_CREDENTIALS_FILE = pathlib.Path(
    os.getenv("LISTING_CREDENTIALS_FILE", ROOT / "listing_credentials.json")
)


def _load_credentials_from_file(path: pathlib.Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    users = []
    if isinstance(data, dict):
        if "users" in data and isinstance(data["users"], list):
            records = data["users"]
        else:
            records = [data]
    elif isinstance(data, list):
        records = data
    else:
        records = []
    for entry in records:
        if not isinstance(entry, dict):
            continue
        username = entry.get("username") or entry.get("user")
        password = entry.get("password") or entry.get("pass")
        if username and password:
            users.append((str(username), str(password)))
    return users


LISTING_CREDENTIALS = []
if LISTING_USERNAME and LISTING_PASSWORD:
    LISTING_CREDENTIALS.append((LISTING_USERNAME, LISTING_PASSWORD))
LISTING_CREDENTIALS.extend(_load_credentials_from_file(LISTING_CREDENTIALS_FILE))
if LISTING_CREDENTIALS:
    LISTING_USERNAME, LISTING_PASSWORD = LISTING_CREDENTIALS[0]

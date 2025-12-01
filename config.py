from __future__ import annotations

import os
import pathlib

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
ASSETS_DIR = WEBSITE_DIR / "assets"
TOKEN_PATH = ROOT / "token.txt"

HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
HTTP_LISTING_PORT = int(os.getenv("HTTP_LISTING_PORT", "8004"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024 * 1024)))
EXTERNAL_URL = os.getenv("EXTERNAL_URL")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://upload.dongurihub.jp")
LISTING_HOME_URL = os.getenv("LISTING_HOME_URL", "/")
MAX_IP_STORAGE_BYTES = int(
    os.getenv("MAX_IP_STORAGE_BYTES", str(80 * 1024 * 1024 * 1024))
)

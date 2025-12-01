import asyncio
import html
import json
import mimetypes
import os
import pathlib
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment
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

# Server bind settings (can be overridden with env)
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
HTTP_LISTING_PORT = int(os.getenv("HTTP_LISTING_PORT", "8004"))
MAX_UPLOAD_BYTES = int(
    os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024 * 1024))
)  # default 5GB
EXTERNAL_URL = os.getenv(
    "EXTERNAL_URL"
)  # optional public base URL (e.g. https://example.com)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://upload.dongurihub.jp")
LISTING_HOME_URL = os.getenv("LISTING_HOME_URL", "/")

# Discord/gihub constants
GITHUB_API_URL = "https://api.github.com/repos"
GITHUB_HEADERS = {"Accept": "application/vnd.github.v3.raw"}
GITHUB_URL_PATTERN = __import__("re").compile(
    r"https://github.com/([\w\-]+)/([\w\-]+)(?:/|$)"
)
FILE_URL_PATTERN = __import__("re").compile(r"(https?://[^\s/]+)/files/([0-9a-fA-F]+)")

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

# Create bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def load_token() -> str:
    path = ROOT / "token.txt"
    return path.read_text(encoding="utf-8").strip()


def load_index() -> Dict[str, Dict]:
    if not INDEX_PATH.exists():
        return {}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_index(index: Dict[str, Dict]) -> None:
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
    # build from request
    scheme = request.scheme
    host = request.headers.get("Host") or f"{HTTP_HOST}:{HTTP_PORT}"
    return f"{scheme}://{host}/files/{token}"


def public_base_url() -> str:
    if EXTERNAL_URL:
        return EXTERNAL_URL.rstrip("/")
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    return f"http://{HTTP_HOST}:{HTTP_PORT}"


def file_page_url(token: str) -> str:
    base = public_base_url().rstrip("/")
    return f"{base}/files/{token}"


def client_ip_from_request(request: web.Request) -> str:
    # trust X-Forwarded-For if present (useful behind reverse-proxy)
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    peer = request.transport.get_extra_info("peername")
    if peer:
        return peer[0]
    return "unknown"


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPRequestEntityTooLarge as exc:
        limit = human_readable_size(exc.max_size or MAX_UPLOAD_BYTES)
        return web.json_response(
            {"error": f"ファイルサイズが大きすぎます。上限: {limit}"},
            status=exc.status,
        )
    except web.HTTPException:
        raise
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def create_app() -> web.Application:
    app = web.Application(
        middlewares=[error_middleware], client_max_size=MAX_UPLOAD_BYTES
    )

    def file_not_found_page() -> web.Response:
        if LISTING_NOT_FOUND_PAGE.exists():
            rendered = render_template(
                LISTING_NOT_FOUND_PAGE,
                {"LISTING_URL": LISTING_HOME_URL},
            )
            return web.Response(
                text=rendered,
                content_type="text/html",
                charset="utf-8",
                status=404,
            )
        return web.Response(text="file not found", status=404)

    async def handle_root(request: web.Request):
        """Serve upload.html from website/upload.html"""
        if UPLOAD_PAGE.exists():
            return web.FileResponse(
                UPLOAD_PAGE, headers={"Content-Type": "text/html; charset=utf-8"}
            )
        return web.Response(text="upload.html not found", status=404)

    async def handle_upload(request: web.Request):
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "file":
            return web.json_response({"error": "missing file field"}, status=400)

        filename = field.filename
        token = uuid.uuid4().hex
        saved_name = f"{token}-{filename}"
        dest = UPLOAD_DIR / saved_name

        size = 0
        with dest.open("wb") as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                f.write(chunk)
                size += len(chunk)

        index = load_index()
        client_ip = client_ip_from_request(request)
        index[token] = {
            "filename": filename,
            "saved_name": saved_name,
            "size": size,
            "timestamp": int(time.time()),
            "ip": client_ip,
            "uploader": "web",
        }
        save_index(index)

        url = make_file_url(request, token)
        return web.json_response({"url": url, "token": token})

    async def handle_get_file(request: web.Request):
        token = request.match_info.get("token")
        index = load_index()
        meta = index.get(token)
        if not meta:
            return file_not_found_page()
        path = UPLOAD_DIR / meta["saved_name"]
        if not path.exists():
            return file_not_found_page()

        filename = meta.get("filename", "file")
        size_bytes = meta.get("size", 0)
        base_url = make_file_url(request, token).split("?")[0]
        inline_url = f"{base_url}?raw=inline"

        raw_mode = request.query.get("raw")
        if raw_mode is not None:
            headers = {}
            if raw_mode != "inline":
                headers["Content-Disposition"] = f'attachment; filename="{filename}"'
            return web.FileResponse(path, headers=headers)

        if request.query.get("preview") == "1":
            if not PREVIEW_TEMPLATE.exists():
                return web.Response(text="preview template missing", status=500)
            escaped_filename = html.escape(filename)
            replacements = {
                "TITLE": escaped_filename,
                "DESCRIPTION": f"ファイルサイズ: {human_readable_size(size_bytes)}",
                "URL": base_url,
                "IMAGE_URL": inline_url,
                "TOKEN": token,
            }
            rendered = render_template(PREVIEW_TEMPLATE, replacements)
            return web.Response(
                text=rendered, content_type="text/html", charset="utf-8"
            )

        if DOWNLOAD_PAGE.exists():
            return web.FileResponse(
                DOWNLOAD_PAGE, headers={"Content-Type": "text/html; charset=utf-8"}
            )
        return web.Response(text="download page not found", status=404)

    async def handle_file_info(request: web.Request):
        token = request.match_info.get("token")
        index = load_index()
        meta = index.get(token)
        if not meta:
            return web.json_response({"error": "not found"}, status=404)
        path = UPLOAD_DIR / meta["saved_name"]
        if not path.exists():
            return web.json_response({"error": "file missing"}, status=404)

        filename = meta.get("filename", "file")
        size_bytes = meta.get("size", 0)
        base_url = make_file_url(request, token).split("?")[0]
        download_url = f"{base_url}?raw=1"
        inline_url = f"{base_url}?raw=inline"
        mime_type, _ = mimetypes.guess_type(filename)
        preview = build_preview_payload(path, filename, mime_type)

        return web.json_response(
            {
                "token": token,
                "filename": filename,
                "size": size_bytes,
                "size_readable": human_readable_size(size_bytes),
                "timestamp": meta.get("timestamp"),
                "uploaded_at": format_timestamp(meta.get("timestamp")),
                "mime_type": mime_type,
                "download_url": download_url,
                "inline_url": inline_url,
                "base_url": base_url,
                "preview": preview,
            }
        )

    async def handle_list(request: web.Request):
        index = load_index()
        client_ip = client_ip_from_request(request)
        # return only files uploaded from this IP
        items = []
        for token, meta in index.items():
            if meta.get("ip") == client_ip:
                items.append(
                    {
                        "token": token,
                        "filename": meta.get("filename"),
                        "size": meta.get("size"),
                        "timestamp": meta.get("timestamp"),
                        "url": make_file_url(request, token),
                    }
                )
        return web.json_response(items)

    async def handle_delete(request: web.Request):
        token = request.match_info.get("token")
        index = load_index()
        meta = index.get(token)
        if not meta:
            raise web.HTTPNotFound(text="file not found")
        client_ip = client_ip_from_request(request)
        if meta.get("ip") != client_ip:
            return web.json_response({"error": "not allowed"}, status=403)
        path = UPLOAD_DIR / meta["saved_name"]
        if path.exists():
            path.unlink()
        del index[token]
        save_index(index)
        return web.json_response({"ok": True})

    app.router.add_get("/", handle_root)
    app.router.add_post("/api/upload", handle_upload)
    app.router.add_get("/files/{token}", handle_get_file)
    app.router.add_get("/api/files", handle_list)
    app.router.add_get("/api/file/{token}", handle_file_info)
    app.router.add_delete("/api/delete/{token}", handle_delete)

    if ASSETS_DIR.exists():
        app.router.add_static("/assets", str(ASSETS_DIR))

    return app


def create_listing_app() -> web.Application:
    app = web.Application(middlewares=[error_middleware])

    async def handle_root(request: web.Request):
        if LISTING_PAGE.exists():
            return web.FileResponse(
                LISTING_PAGE, headers={"Content-Type": "text/html; charset=utf-8"}
            )
        return web.Response(text="listing page not found", status=404)

    async def handle_listing(request: web.Request):
        index = load_index()
        records: List[Dict[str, object]] = []
        for token, meta in index.items():
            timestamp = meta.get("timestamp") or 0
            filename = meta.get("filename", "file")
            mime_type, _ = mimetypes.guess_type(filename)
            file_type = mime_type or "不明"
            records.append(
                {
                    "filename": filename,
                    "size": meta.get("size", 0),
                    "size_readable": human_readable_size(meta.get("size", 0)),
                    "uploaded_at": format_timestamp(timestamp),
                    "file_type": file_type,
                    "url": file_page_url(token),
                    "timestamp": timestamp,
                    "token": token,
                }
            )

        records.sort(key=lambda item: item["timestamp"], reverse=True)
        for record in records:
            record.pop("timestamp", None)
        return web.json_response(records)

    app.router.add_get("/", handle_root)
    app.router.add_get("/api/files", handle_listing)
    if ASSETS_DIR.exists():
        app.router.add_static("/assets", str(ASSETS_DIR))
    return app


# --- Discord bot logic (GitHub preview + verify) ---


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user}")

    # create aiohttp client session for github requests
    if not hasattr(bot, "session"):
        bot.session = aiohttp.ClientSession()

    # start web server in background (only once)
    if not hasattr(bot, "web_runner"):
        app = create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
        await site.start()
        bot.web_runner = runner
        print(f"HTTP server started on {HTTP_HOST}:{HTTP_PORT}")

    if not hasattr(bot, "listing_runner"):
        listing_app = create_listing_app()
        listing_runner = web.AppRunner(listing_app)
        await listing_runner.setup()
        listing_site = web.TCPSite(listing_runner, HTTP_HOST, HTTP_LISTING_PORT)
        await listing_site.start()
        bot.listing_runner = listing_runner
        print(f"Listing server started on {HTTP_HOST}:{HTTP_LISTING_PORT}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


@bot.event
async def on_close() -> None:
    if hasattr(bot, "session"):
        await bot.session.close()
    if hasattr(bot, "web_runner"):
        await bot.web_runner.cleanup()
    if hasattr(bot, "listing_runner"):
        await bot.listing_runner.cleanup()


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    match = GITHUB_URL_PATTERN.search(message.content)
    if match:
        owner, repo = match.groups()
        try:
            await message.edit(suppress=True)
        except (discord.Forbidden, discord.HTTPException):
            pass

        readme_text = await fetch_github_readme(owner, repo)
        if readme_text:
            preview = readme_text[:500] + ("..." if len(readme_text) > 500 else "")
            embed = discord.Embed(
                title=f"{owner}/{repo} README",
                description=f"```\n{preview}\n```",
                color=0x1F6FEB,
            )
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"README not found for **{owner}/{repo}**")

    file_match = FILE_URL_PATTERN.search(message.content)
    if file_match:
        base, token = file_match.groups()
        index = load_index()
        meta = index.get(token)
        if meta:
            filename = meta.get("filename", "file")
            size_readable = human_readable_size(meta.get("size", 0))
            uploaded_at = format_timestamp(meta.get("timestamp"))
            page_url = f"{base}/files/{token}"
            embed = discord.Embed(
                title=f"共有ファイル: {filename}",
                description=f"[こちらからダウンロード]({page_url})",
                color=0x4E73DF,
            )
            mime_type, _ = mimetypes.guess_type(filename)
            file_type = mime_type or "不明"
            embed.add_field(name="ファイルサイズ", value=size_readable, inline=True)
            embed.add_field(name="アップロード", value=uploaded_at, inline=True)
            embed.add_field(name="ファイルタイプ", value=file_type, inline=True)
            embed.set_footer(text="共有リンク詳細")
            try:
                await message.edit(suppress=True)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(
                f"共有リンクのファイル情報を見つけられませんでした: {token}"
            )

    await bot.process_commands(message)


async def fetch_github_readme(owner: str, repo: str) -> Optional[str]:
    url = f"{GITHUB_API_URL}/{owner}/{repo}/readme"
    try:
        async with bot.session.get(url, headers=GITHUB_HEADERS) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        print(f"Error fetching README: {e}")
    return None


@app_commands.checks.has_permissions(administrator=True)
@bot.tree.command(name="setupverify", description="認証用メッセージを送信します")
@app_commands.describe(role="認証時に付与するロール")
async def setupverify(interaction: discord.Interaction, role: discord.Role) -> None:
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "このコマンドは管理者のみ実行できます。",
            ephemeral=True,
        )
        return

    if role.permissions.administrator:
        await interaction.response.send_message(
            "管理者権限のあるロールは選択できません。",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="認証",
        description="以下のボタンを押して認証してください。",
        color=0x00FF00,
    )
    view = discord.ui.View()
    view.add_item(VerifyButton(role.id))
    await interaction.response.send_message(embed=embed, view=view)


class VerifyButton(discord.ui.Button):
    def __init__(self, role_id: int) -> None:
        super().__init__(
            label="認証する",
            style=discord.ButtonStyle.success,
            custom_id=f"verify_button_{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction) -> None:
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message(
                "ロールが見つかりませんでした。", ephemeral=True
            )
            return
        await interaction.user.add_roles(role)
        await interaction.response.send_message("認証されました！", ephemeral=True)


@bot.tree.command(name="upload", description="アップロードページのリンクを表示します")
async def upload_link(interaction: discord.Interaction) -> None:
    base = public_base_url()
    url = f"{base}/" if not base.endswith("/") else base
    await interaction.response.send_message(
        f"📤 ファイルアップロードはこちらからどうぞ:\n{url}", ephemeral=False
    )


if __name__ == "__main__":
    token = load_token()
    try:
        bot.run(token)
    except Exception as e:
        print(f"Error running bot: {e}")

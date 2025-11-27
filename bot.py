import asyncio
import json
import os
import pathlib
import time
import uuid
from typing import Dict, Optional

import aiohttp
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment
load_dotenv()

ROOT = pathlib.Path(__file__).parent
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = ROOT / "file_index.json"

# Server bind settings (can be overridden with env)
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
EXTERNAL_URL = os.getenv("EXTERNAL_URL")  # optional public base URL (e.g. https://example.com)

# Discord/gihub constants
GITHUB_API_URL = "https://api.github.com/repos"
GITHUB_HEADERS = {"Accept": "application/vnd.github.v3.raw"}
GITHUB_URL_PATTERN = __import__("re").compile(r'https://github.com/([\w\-]+)/([\w\-]+)(?:/|$)')

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
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def make_file_url(request: web.Request, token: str) -> str:
    if EXTERNAL_URL:
        base = EXTERNAL_URL.rstrip("/")
        return f"{base}/files/{token}"
    # build from request
    scheme = request.scheme
    host = request.headers.get("Host") or f"{HTTP_HOST}:{HTTP_PORT}"
    return f"{scheme}://{host}/files/{token}"


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
    except web.HTTPException:
        raise
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def create_app() -> web.Application:
    app = web.Application(middlewares=[error_middleware])

    async def handle_root(request: web.Request):
        """Serve upload.html from website/upload.html"""
        html_path = ROOT / "website" / "upload.html"
        if html_path.exists():
            return web.FileResponse(html_path, headers={"Content-Type": "text/html; charset=utf-8"})
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
            raise web.HTTPNotFound(text="file not found")
        path = UPLOAD_DIR / meta["saved_name"]
        if not path.exists():
            raise web.HTTPNotFound(text="file missing")
        
        # Check if this is a preview request (for Discord embeds)
        if request.query.get("preview") == "1":
            filename = meta.get("filename", "file")
            size_mb = meta.get("size", 0) / (1024 * 1024)
            base_url = make_file_url(request, token).split("?")[0]
            
            # Generate OGP HTML for Discord preview
            html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta property="og:title" content="{filename}">
    <meta property="og:description" content="ファイルサイズ: {size_mb:.2f} MB">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{base_url}">
    <title>{filename}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; }}
        .info {{ color: #666; font-size: 14px; }}
        .button {{ display: inline-block; margin-top: 20px; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 4px; }}
        .button:hover {{ background: #764ba2; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📥 {filename}</h1>
        <div class="info">
            <p><strong>ファイルサイズ:</strong> {size_mb:.2f} MB</p>
            <p><a href="{base_url}" class="button">ダウンロード</a></p>
        </div>
    </div>
</body>
</html>"""
            return web.Response(text=html, content_type="text/html; charset=utf-8")
        
        return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{meta["filename"]}"'})

    async def handle_list(request: web.Request):
        index = load_index()
        client_ip = client_ip_from_request(request)
        # return only files uploaded from this IP
        items = []
        for token, meta in index.items():
            if meta.get("ip") == client_ip:
                items.append({
                    "token": token,
                    "filename": meta.get("filename"),
                    "size": meta.get("size"),
                    "timestamp": meta.get("timestamp"),
                    "url": make_file_url(request, token),
                })
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
    app.router.add_delete("/api/delete/{token}", handle_delete)

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
                color=0x1f6feb,
            )
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"README not found for **{owner}/{repo}**")

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

    embed = discord.Embed(title="認証", description="以下のボタンを押して認証してください。", color=0x00FF00)
    view = discord.ui.View()
    view.add_item(VerifyButton(role.id))
    await interaction.response.send_message(embed=embed, view=view)


class VerifyButton(discord.ui.Button):
    def __init__(self, role_id: int) -> None:
        super().__init__(label="認証する", style=discord.ButtonStyle.success, custom_id=f"verify_button_{role_id}")
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction) -> None:
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("ロールが見つかりませんでした。", ephemeral=True)
            return
        await interaction.user.add_roles(role)
        await interaction.response.send_message("認証されました！", ephemeral=True)


if __name__ == "__main__":
    token = load_token()
    try:
        bot.run(token)
    except Exception as e:
        print(f"Error running bot: {e}")

from __future__ import annotations

import mimetypes
import re

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands

from config import (
    ENABLE_LISTING_SERVER,
    ENABLE_UPLOAD_SERVER,
    HTTP_HOST,
    HTTP_LISTING_PORT,
    HTTP_LOGIN_PORT,
    HTTP_PORT,
)
from file_index import load_index
from github_client import fetch_readme
from helpers import format_timestamp, human_readable_size, public_base_url
from web_server import (
    create_listing_app,
    create_uploader_app,
    load_file_credentials,
    refresh_allowed_users,
    save_file_credentials,
)

GITHUB_URL_PATTERN = re.compile(r"https://github.com/([\w\-]+)/([\w\-]+)(?:/|$)")
FILE_URL_PATTERN = re.compile(r"(https?://[^\s/]+)/files/([0-9a-fA-F]+)")

UPLOAD_SERVER_DISABLED_LOGGED = False
LISTING_SERVER_DISABLED_LOGGED = False


def configure_bot(bot: commands.Bot) -> None:
    register_events(bot)
    register_commands(bot)


def register_events(bot: commands.Bot) -> None:
    @bot.event
    async def on_ready() -> None:  # type: ignore[misc]
        global UPLOAD_SERVER_DISABLED_LOGGED, LISTING_SERVER_DISABLED_LOGGED
        print(f"Logged in as {bot.user}")

        if not hasattr(bot, "session"):
            bot.session = aiohttp.ClientSession()

        if ENABLE_UPLOAD_SERVER:
            if not hasattr(bot, "web_runner"):
                upload_app = create_uploader_app()
                runner = web.AppRunner(upload_app)
                await runner.setup()
                site = web.TCPSite(runner, HTTP_HOST, HTTP_PORT)
                await site.start()
                bot.web_runner = runner
                print(f"HTTP server started on {HTTP_HOST}:{HTTP_PORT}")
        elif not UPLOAD_SERVER_DISABLED_LOGGED:
            print("Skipping embedded upload server (ENABLE_UPLOAD_SERVER=0)")
            UPLOAD_SERVER_DISABLED_LOGGED = True

        if ENABLE_LISTING_SERVER:
            if not hasattr(bot, "listing_runner"):
                listing_app = create_listing_app()
                listing_runner = web.AppRunner(listing_app)
                await listing_runner.setup()
                listing_site = web.TCPSite(listing_runner, HTTP_HOST, HTTP_LISTING_PORT)
                await listing_site.start()
                bot.listing_site = listing_site
                if HTTP_LOGIN_PORT != HTTP_LISTING_PORT:
                    login_site = web.TCPSite(listing_runner, HTTP_HOST, HTTP_LOGIN_PORT)
                    await login_site.start()
                    bot.login_site = login_site
                    print(f"Login page server started on {HTTP_HOST}:{HTTP_LOGIN_PORT}")
                bot.listing_runner = listing_runner
                print(f"Listing server started on {HTTP_HOST}:{HTTP_LISTING_PORT}")
        elif not LISTING_SERVER_DISABLED_LOGGED:
            print("Skipping listing/login server (ENABLE_LISTING_SERVER=0)")
            LISTING_SERVER_DISABLED_LOGGED = True

        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as exc:
            print(f"Failed to sync commands: {exc}")

    @bot.event
    async def on_close() -> None:  # type: ignore[misc]
        if hasattr(bot, "session"):
            await bot.session.close()
        if hasattr(bot, "web_runner"):
            await bot.web_runner.cleanup()
        if hasattr(bot, "listing_runner"):
            await bot.listing_runner.cleanup()

    @bot.event
    async def on_message(message: discord.Message) -> None:  # type: ignore[misc]
        if message.author.bot:
            return

        match = GITHUB_URL_PATTERN.search(message.content)
        if match and hasattr(bot, "session"):
            owner, repo = match.groups()
            await suppress_original(message)
            readme_text = await fetch_readme(bot.session, owner, repo)
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
                await suppress_original(message)
                await message.channel.send(embed=embed)
            else:
                await message.channel.send(
                    f"共有リンクのファイル情報を見つけられませんでした: {token}"
                )

        await bot.process_commands(message)


def register_commands(bot: commands.Bot) -> None:
    class VerifyButton(discord.ui.Button):
        def __init__(self, role_id: int) -> None:
            super().__init__(
                label="認証する",
                style=discord.ButtonStyle.success,
                custom_id=f"verify_button_{role_id}",
            )
            self.role_id = role_id

        async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
            role = interaction.guild.get_role(self.role_id)
            if not role:
                await interaction.response.send_message(
                    "ロールが見つかりませんでした。", ephemeral=True
                )
                return
            await interaction.user.add_roles(role)
            await interaction.response.send_message("認証されました！", ephemeral=True)

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

    @bot.tree.command(
        name="upload", description="アップロードページのリンクを表示します"
    )
    async def upload_link(interaction: discord.Interaction) -> None:
        base = public_base_url()
        url = f"{base}/" if not base.endswith("/") else base
        await interaction.response.send_message(
            f"📤 ファイルアップロードはこちらからどうぞ:\n{url}", ephemeral=False
        )

    @app_commands.checks.has_permissions(administrator=True)
    @bot.tree.command(
        name="adduser", description="共有一覧のログインユーザーを追加/更新します"
    )
    @app_commands.describe(
        username="追加または上書きするユーザーID", password="設定するパスワード"
    )
    async def adduser(
        interaction: discord.Interaction, username: str, password: str
    ) -> None:
        username = (username or "").strip()
        password = password or ""
        if not username or not password:
            await interaction.response.send_message(
                "ユーザーIDとパスワードを入力してください。", ephemeral=True
            )
            return

        try:
            current = {user: pwd for user, pwd in load_file_credentials()}
            existed = username in current
            current[username] = password
            save_file_credentials(list(current.items()))
            refresh_allowed_users()
            action = "更新" if existed else "追加"
            await interaction.response.send_message(
                f"✅ ログインユーザーを{action}しました: `{username}`",
                ephemeral=True,
            )
        except Exception as exc:
            await interaction.response.send_message(
                f"ユーザー追加に失敗しました: {exc}", ephemeral=True
            )


async def suppress_original(message: discord.Message) -> None:
    try:
        await message.edit(suppress=True)
    except (discord.Forbidden, discord.HTTPException):
        pass

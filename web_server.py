from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import time
import uuid
from typing import Dict, List

from aiohttp import web

from config import (
    ASSETS_DIR,
    DOWNLOAD_PAGE,
    LISTING_HOME_URL,
    LISTING_NOT_FOUND_PAGE,
    LISTING_PAGE,
    MAX_IP_STORAGE_BYTES,
    MAX_UPLOAD_BYTES,
    PREVIEW_TEMPLATE,
    UPLOAD_DIR,
    UPLOAD_PAGE,
)
from file_index import load_index, save_index
from helpers import (
    build_preview_payload,
    client_ip_from_request,
    escape_filename,
    file_page_url,
    format_timestamp,
    human_readable_size,
    make_file_url,
    render_template,
)


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
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


def create_uploader_app() -> web.Application:
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

        index = load_index()
        client_ip = client_ip_from_request(request)
        quota_limit = MAX_IP_STORAGE_BYTES
        current_usage = 0
        if quota_limit > 0:
            current_usage = sum(
                meta.get("size", 0)
                for meta in index.values()
                if meta.get("ip") == client_ip
            )
            if current_usage >= quota_limit:
                limit_str = human_readable_size(quota_limit)
                used_str = human_readable_size(current_usage)
                return web.json_response(
                    {
                        "error": "同じIPからアップロードできる容量の上限を超えています。",
                        "limit": limit_str,
                        "used": used_str,
                        "remaining": "0 B",
                    },
                    status=400,
                )

        size = 0
        quota_hit = False
        upload_completed = False
        try:
            with dest.open("wb") as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        upload_completed = True
                        break
                    f.write(chunk)
                    size += len(chunk)
                    if quota_limit > 0 and (current_usage + size) > quota_limit:
                        quota_hit = True
                        break
        except asyncio.CancelledError:
            dest.unlink(missing_ok=True)
            raise
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        finally:
            if upload_completed:
                with contextlib.suppress(Exception):
                    await field.release()

        if quota_hit:
            dest.unlink(missing_ok=True)
            limit_str = human_readable_size(quota_limit)
            used_str = human_readable_size(current_usage)
            remaining = max(quota_limit - current_usage, 0)
            return web.json_response(
                {
                    "error": "同じIPからアップロードできる容量の上限を超えました。",
                    "limit": limit_str,
                    "used": used_str,
                    "remaining": human_readable_size(remaining),
                },
                status=400,
            )

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
            replacements = {
                "TITLE": escape_filename(filename),
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

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import mimetypes
import os
import time
import uuid
from typing import Dict, List
from urllib.parse import splitport, unquote, urlencode

from aiohttp import web

from config import (
    ASSETS_DIR,
    DOWNLOAD_PAGE,
    HTTP_HOST,
    HTTP_LISTING_PORT,
    HTTP_LOGIN_PORT,
    HTTP_PORT,
    LISTING_CREDENTIALS_FILE,
    LISTING_HOME_URL,
    LISTING_LOGIN_ASSETS_DIR,
    LISTING_LOGIN_PAGE,
    LISTING_NOT_FOUND_PAGE,
    LISTING_PAGE,
    LISTING_SESSION_SECRET,
    LISTING_SESSION_TTL,
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

SESSION_COOKIE = "listing_session"
ALLOWED_USERS: dict[str, str] = {}
AUTH_ENABLED = False
SESSION_SECRET_BYTES = (LISTING_SESSION_SECRET or "listing-secret").encode("utf-8")
SESSION_TTL = max(int(LISTING_SESSION_TTL), 0)


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET_BYTES, payload.encode("utf-8"), "sha256").hexdigest()


def create_session_token(username: str) -> str:
    issued = str(int(time.time()))
    payload = f"{username}|{issued}"
    signature = _sign(payload)
    return f"{payload}|{signature}"


def validate_session_token(token: str) -> bool:
    parts = token.split("|")
    if len(parts) != 3:
        return False
    username, issued_str, signature = parts
    if username not in ALLOWED_USERS:
        return False
    payload = f"{username}|{issued_str}"
    expected = _sign(payload)
    if not hmac.compare_digest(expected, signature):
        return False
    try:
        issued = int(issued_str)
    except ValueError:
        return False
    if SESSION_TTL and (time.time() - issued) > SESSION_TTL:
        return False
    return True


def load_file_credentials() -> list[tuple[str, str]]:
    path = LISTING_CREDENTIALS_FILE
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    records: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        candidates = raw.get("users") if isinstance(raw.get("users"), list) else [raw]
    elif isinstance(raw, list):
        candidates = raw
    else:
        candidates = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        username = entry.get("username") or entry.get("user")
        password = entry.get("password") or entry.get("pass")
        if username and password:
            records.append((str(username), str(password)))
    return records


def refresh_allowed_users() -> None:
    global AUTH_ENABLED
    env_user = os.getenv("LISTING_USERNAME")
    env_pass = os.getenv("LISTING_PASSWORD")
    combined: dict[str, str] = {}
    if env_user and env_pass:
        combined[env_user] = env_pass
    for user, pwd in load_file_credentials():
        combined[user] = pwd
    ALLOWED_USERS.clear()
    ALLOWED_USERS.update(combined)
    AUTH_ENABLED = bool(ALLOWED_USERS)


def verify_credentials(username: str, password: str) -> bool:
    expected = ALLOWED_USERS.get(username)
    return expected is not None and expected == password


def is_authenticated(request: web.Request) -> bool:
    if not AUTH_ENABLED:
        return True
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    return validate_session_token(token)


def sanitize_next(target: str | None) -> str:
    if not target:
        return "/"
    try:
        candidate = unquote(target)
    except Exception:
        candidate = target
    if not candidate.startswith("/"):
        return "/"
    if candidate.startswith("//"):
        return "/"
    return candidate


def _forwarded_host(request: web.Request) -> str | None:
    return request.headers.get("X-Forwarded-Host") or request.headers.get("Host")


def _forwarded_proto(request: web.Request) -> str:
    return request.headers.get("X-Forwarded-Proto") or request.scheme


def _forwarded_port(request: web.Request) -> int | None:
    port = request.headers.get("X-Forwarded-Port")
    if port and port.isdigit():
        return int(port)
    return None


def _is_secure(request: web.Request) -> bool:
    proto = request.headers.get("X-Forwarded-Proto")
    if proto:
        return proto == "https"
    return request.secure


def _split_host(host: str | None) -> tuple[str, int | None]:
    hostname, port = splitport(host) if host else (None, None)
    if not hostname:
        hostname = HTTP_HOST
    port_value = None
    if port:
        with contextlib.suppress(ValueError):
            port_value = int(port)
    return hostname, port_value


def _request_host(request: web.Request) -> tuple[str, int | None]:
    forwarded = _forwarded_host(request)
    hostname, port = _split_host(forwarded)
    if not hostname:
        hostname = request.url.host or HTTP_HOST
    if port is None:
        port = _forwarded_port(request) or request.url.port
    return hostname, port


def _normalize_host(hostname: str) -> str:
    if ":" in hostname and not hostname.startswith("["):
        return f"[{hostname}]"
    return hostname


def _build_origin(request: web.Request, port: int) -> str:
    scheme = _forwarded_proto(request)
    hostname, _ = _request_host(request)
    if not hostname:
        hostname = HTTP_HOST
    default_port = 443 if scheme == "https" else 80
    port_part = "" if port == default_port else f":{port}"
    return f"{scheme}://{_normalize_host(hostname)}{port_part}"


def login_origin(request: web.Request) -> str:
    return _build_origin(request, HTTP_LOGIN_PORT)


def listing_origin(request: web.Request) -> str:
    return _build_origin(request, HTTP_LISTING_PORT)


def build_login_url(
    request: web.Request, next_path: str = "/", error: bool = False
) -> str:
    params = []
    if next_path and next_path != "/":
        params.append(("next", next_path))
    if error:
        params.append(("error", "1"))
    query = f"?{urlencode(params)}" if params else ""
    base = f"{login_origin(request)}/"
    return f"{base}{query}" if query else base


def build_listing_url(request: web.Request, next_path: str = "/") -> str:
    base = listing_origin(request)
    if not next_path or next_path == "/":
        return f"{base}/"
    return f"{base}{next_path}"


def is_login_port_request(request: web.Request) -> bool:
    port = _forwarded_port(request)
    if port is None:
        host_header = request.headers.get("Host")
        if host_header:
            _, host_port = splitport(host_header)
            if host_port and host_port.isdigit():
                port = int(host_port)
    if port is None:
        port = request.url.port
    if port is None:
        port = 443 if _forwarded_proto(request) == "https" else 80
    return port == HTTP_LOGIN_PORT


def login_redirect_response(
    request: web.Request, next_path: str = "/", error: bool = False
) -> web.HTTPFound:
    return web.HTTPFound(location=build_login_url(request, next_path, error))


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

    def serve_login_page() -> web.StreamResponse:
        if LISTING_LOGIN_PAGE.exists():
            return web.FileResponse(
                LISTING_LOGIN_PAGE,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        return web.Response(text="login page not found", status=500)

    refresh_allowed_users()

    async def handle_root(request: web.Request):
        refresh_allowed_users()
        if is_login_port_request(request):
            return serve_login_page()

        if AUTH_ENABLED and not is_authenticated(request):
            next_path = sanitize_next(request.rel_url.path_qs or "/")
            raise login_redirect_response(request, next_path)

        if LISTING_PAGE.exists():
            return web.FileResponse(
                LISTING_PAGE, headers={"Content-Type": "text/html; charset=utf-8"}
            )
        return web.Response(text="listing page not found", status=404)

    async def handle_login_page(request: web.Request):
        if is_login_port_request(request):
            return serve_login_page()
        refresh_allowed_users()
        next_path = sanitize_next(request.rel_url.query.get("next"))
        raise login_redirect_response(request, next_path)

    async def handle_login_submit(request: web.Request):
        if not AUTH_ENABLED:
            return serve_login_page()
        refresh_allowed_users()
        form = await request.post()
        username = form.get("username", "")
        password = form.get("password", "")
        target = sanitize_next(form.get("next") or request.rel_url.query.get("next"))
        if verify_credentials(username, password):
            response = web.HTTPFound(location=build_listing_url(request, target))
            response.set_cookie(
                SESSION_COOKIE,
                create_session_token(username),
                max_age=SESSION_TTL or None,
                httponly=True,
                secure=_is_secure(request),
                samesite="Lax",
                path="/",
            )
            raise response
        raise login_redirect_response(request, target, error=True)

    async def handle_logout(request: web.Request):
        response = web.HTTPFound(location=f"{login_origin(request)}/")
        response.del_cookie(SESSION_COOKIE, path="/")
        raise response

    async def handle_listing(request: web.Request):
        if AUTH_ENABLED and not is_authenticated(request):
            return web.json_response({"error": "unauthorized"}, status=401)
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
    app.router.add_get("/login", handle_login_page)
    app.router.add_post("/login", handle_login_submit)
    app.router.add_get("/logout", handle_logout)
    app.router.add_post("/logout", handle_logout)
    app.router.add_get("/api/files", handle_listing)
    if LISTING_LOGIN_ASSETS_DIR.exists():
        app.router.add_static("/login/assets", str(LISTING_LOGIN_ASSETS_DIR))
    if ASSETS_DIR.exists():
        app.router.add_static("/assets", str(ASSETS_DIR))
    return app

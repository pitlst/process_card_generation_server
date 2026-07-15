"""工序卡生成服务 —— 入口模块。

启动方式：
    uv run main.py
    或
    uv run uvicorn main:app --reload
"""

from pathlib import Path

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.openapi import OpenAPIConfig
from litestar.response import File, Response

from app.routes import generate_process_card, upload_images

static_dir = Path(__file__).parent / "static"


# ── 静态文件服务（兼容 Next.js 静态导出）─────────────────

def _guess_mime(file_path: Path) -> str:
    """根据扩展名返回 MIME 类型。"""
    ext = file_path.suffix.lower()
    return {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".txt": "text/plain",
        ".xml": "application/xml",
    }.get(ext, "application/octet-stream")


def _resolve_static(raw_path: str) -> tuple[Path | None, str, int]:
    """将 URL 路径解析为 static/ 下的实际文件。"""
    path = raw_path.lstrip("/")

    # 根路径
    if path == "":
        return static_dir / "index.html", "text/html", 200

    # 直接匹配文件
    direct = static_dir / path
    if direct.is_file():
        return direct, _guess_mime(direct), 200

    # 无扩展名 → 尝试补 .html
    if "." not in path.rsplit("/", 1)[-1]:
        html_candidate = static_dir / (path + ".html")
        if html_candidate.exists():
            return html_candidate, "text/html", 200

    # 404
    not_found = static_dir / "404.html"
    if not_found.exists():
        return not_found, "text/html", 404

    return None, "", 404


@get("/", include_in_schema=False)
async def serve_index() -> File:
    """首页。"""
    return File(
        path=str(static_dir / "index.html"),
        media_type="text/html",
        content_disposition_type="inline",
    )


@get("/{path:path}", include_in_schema=False)
async def serve_static(path: str) -> File | Response:
    """统一静态文件服务。"""
    file_path, media_type, status = _resolve_static("/" + path)
    if file_path is not None:
        return File(
            path=str(file_path),
            media_type=media_type,
            status_code=status,
            content_disposition_type="inline",
        )
    return Response(
        content=b"<html><body><h1>404 Not Found</h1></body></html>",
        media_type="text/html",
        status_code=404,
    )


# ── 应用配置 ───────────────────────────────────────────

cors_config = CORSConfig(allow_origins=["*"])
openapi_config = OpenAPIConfig(
    title="工序卡生成服务",
    version="0.1.0",
    description="接收 JSON 格式的工序卡数据，生成 PDF 工序卡文件。",
)

app = Litestar(
    route_handlers=[upload_images, generate_process_card, serve_index, serve_static],
    cors_config=cors_config,
    openapi_config=openapi_config,
)

# ── 直接运行入口 ────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18000)

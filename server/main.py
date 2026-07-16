"""工序卡生成服务 —— 入口模块。

启动方式：
    uv run main.py
    或
    uv run uvicorn main:app --reload
"""

from pathlib import Path

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.response import File
from litestar.static_files.config import create_static_files_router

from app.routes import generate_process_card, upload_images

static_dir = Path(__file__).parent / "static"


front_static_files = create_static_files_router(
    path="/",
    directories=["static"],
    name="static",
    html_mode=True,
    include_in_schema=False,
)

images_static_files = create_static_files_router(
    path="/images",
    directories=["uploads"],
    name="images",
    include_in_schema=False,
)


# ── 应用配置 ───────────────────────────────────────────

cors_config = CORSConfig(allow_origins=["*"])
app = Litestar(
    route_handlers=[upload_images, generate_process_card, front_static_files, images_static_files],
    cors_config=cors_config,
)

# ── 直接运行入口 ────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18000)

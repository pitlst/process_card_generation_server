"""工序卡生成服务 —— 入口模块。

启动方式：
    uv run uvicorn main:app --reload
"""

from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin

from app.routes import generate_process_card, upload_images

cors_config = CORSConfig(allow_origins=["*"])
openapi_config = OpenAPIConfig(
    title="工序卡生成服务",
    version="0.1.0",
    description="接收 JSON 格式的工序卡数据，生成 PDF 工序卡文件。",
    render_plugins=[ScalarRenderPlugin()],
)

app = Litestar(
    route_handlers=[upload_images, generate_process_card],
    cors_config=cors_config,
    openapi_config=openapi_config,
)

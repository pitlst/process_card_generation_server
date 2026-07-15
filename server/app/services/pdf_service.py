"""工序卡 PDF 生成服务。

将 ProcessCardInput 数据 + 已上传的图片 → Jinja2 模板 → Playwright(Chromium) → PDF 字节流。
"""

from __future__ import annotations

import base64
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from loguru import logger
from playwright.async_api import async_playwright

from app.models import ProcessCardInput
from app.services.image_store import ImageStore

# ── 硬编码浏览器路径（按实际部署环境修改）────────────────────
# 支持 Edge / Chrome / Thorium 等任意 Chromium 内核浏览器
BROWSER_EXECUTABLE_PATH: str = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
# ─────────────────────────────────────────────────────────────


class ProcessCardPDFService:
    """工序卡 PDF 生成服务。"""

    def __init__(self, image_store: ImageStore) -> None:
        self.image_store = image_store

        template_dir = Path(__file__).resolve().parent.parent.parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
        )

    async def generate(self, data: ProcessCardInput) -> bytes:
        """生成工序卡 PDF，返回 PDF 字节流。"""

        # ── 1. 收集所有引用的 image_id ──────────────────────
        image_ids: set[str] = set()
        for res in data.process_step_resources:
            if res.image_id:
                image_ids.add(res.image_id)
        for body in data.step_bodies:
            for fid in (
                body.image_id,
                body.image_page_1_id,
                body.image_page_2_id,
                body.image_page_3_id,
            ):
                if fid:
                    image_ids.add(fid)

        # ── 2. 从文件存储读取图片，转为 base64 data URI ──────
        images: dict[str, str] = {}
        for iid in image_ids:
            img_bytes = await self.image_store.read_bytes(iid)
            if not img_bytes:
                continue
            meta = await self.image_store.get(iid)
            mime = meta.mime_type if meta else "image/png"
            b64 = base64.b64encode(img_bytes).decode("ascii")
            images[iid] = f"data:{mime};base64,{b64}"

        # ── 3. 构建 BOM 页面数据 ────────────────────────────
        # 按 vehicle_group 分组，每组内双栏配对（左/右各一个物料），
        # 每页最多 25 行（共 50 个物料），超出自动分页
        bom_pages: list[list[tuple[str, list]]] = []
        if data.material_list:
            groups: dict[str, list] = {}
            for item in data.material_list:
                key = item.vehicle_group or ""
                groups.setdefault(key, []).append(item)

            MAX_ROWS = 25
            current_page: list[tuple[str, list]] = []
            current_rows = 0

            for group_name, items in groups.items():
                # 两两配对为双栏行
                pairs: list[list] = []
                for i in range(0, len(items), 2):
                    row = [items[i]]
                    if i + 1 < len(items):
                        row.append(items[i + 1])
                    pairs.append(row)

                # 按页拆分
                chunk_start = 0
                while chunk_start < len(pairs):
                    remaining = MAX_ROWS - current_rows
                    chunk = pairs[chunk_start : chunk_start + remaining]
                    current_page.append((group_name, chunk))
                    current_rows += len(chunk)
                    chunk_start += len(chunk)

                    if current_rows >= MAX_ROWS:
                        bom_pages.append(current_page)
                        current_page = []
                        current_rows = 0

            if current_page:
                bom_pages.append(current_page)

        # ── 4. 构建工步正文数据 ──────────────────────────────
        # 每个 step_body 可能附带 0~3 张额外配图页
        step_bodies: list[dict] = []
        image_page_counts: list[int] = []

        for body in data.step_bodies:
            extra_images: list[dict] = []
            for title, fid in [
                ("配图页 1", body.image_page_1_id),
                ("配图页 2", body.image_page_2_id),
                ("配图页 3", body.image_page_3_id),
            ]:
                if fid and fid in images:
                    extra_images.append({"title": title, "image_id": fid})
            image_page_counts.append(len(extra_images))

            step_bodies.append({
                "step_number": body.step_number,
                "step_name": body.step_name,
                "action_sequence": body.action_sequence,
                "action_description": body.action_description,
                "technical_requirements": body.technical_requirements,
                "self_inspection": body.self_inspection,
                "layout": body.layout,
                "image_id": body.image_id,
                "extra_images": extra_images,
            })

        # ── 5. 收集工步标识（去重后用 、连接）────────────────
        markers: list[str] = []
        seen: set[str] = set()
        for res in data.process_step_resources:
            if res.step_marker:
                for ch in res.step_marker:
                    if ch.strip() and ch not in seen:
                        seen.add(ch)
                        markers.append(ch)
        step_markers = "、".join(markers) if markers else ""

        # ── 6. 计算总页数 ────────────────────────────────────
        total_pages = 1  # 封面
        if data.normative_references or data.change_records:
            total_pages += 1  # 规范性引用文件 + 版本历史
        total_pages += len(bom_pages)
        if data.process_step_resources:
            total_pages += 1  # 工步作业资源需求表
        for img_count in image_page_counts:
            total_pages += 1 + img_count  # 工步正文页 + 配图页

        # ── 7. Jinja2 渲染 HTML ─────────────────────────────
        template = self.jinja_env.get_template("process_card.html.j2")
        html_str = template.render(
            basic_info=data.basic_info,
            normative_references=data.normative_references,
            change_records=data.change_records,
            bom_pages=bom_pages,
            process_step_resources=data.process_step_resources,
            step_bodies=step_bodies,
            step_markers=step_markers,
            images=images,
            total_pages=total_pages,
        )
        logger.info(f"渲染 HTML 完成 ({len(html_str)} 字符)，开始生成 PDF...")

        # ── 8. Playwright → PDF ─────────────────────────────
        if not Path(BROWSER_EXECUTABLE_PATH).exists():
            raise FileNotFoundError(
                f"浏览器未找到: {BROWSER_EXECUTABLE_PATH}\n"
                f"请修改 pdf_service.py 顶部的 BROWSER_EXECUTABLE_PATH 常量，"
                f"指向本机已安装的 Chromium 内核浏览器（Edge / Chrome / Thorium 等）"
            )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=BROWSER_EXECUTABLE_PATH,
                headless=True,
            )
            try:
                page = await browser.new_page()
                await page.set_content(html_str, wait_until="networkidle")
                pdf_bytes = await page.pdf(
                    format="A4",
                    landscape=True,
                    print_background=True,
                    margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                )
            finally:
                await browser.close()

        logger.info(f"PDF 生成完成 ({len(pdf_bytes)} bytes)")
        return pdf_bytes

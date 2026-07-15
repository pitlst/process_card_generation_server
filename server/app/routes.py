"""工序卡生成 API 路由。"""

from __future__ import annotations

from litestar import Request, post
from litestar.response import Response
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED

from app.models import (
    ImageBatchUploadResponse,
    ImageUploadResult,
    InvalidImageReference,
    ProcessCardInput,
)
from app.services.image_store import get_image_store
from app.services.pdf_service import ProcessCardPDFService


# ──────────────────────────────────────────────
# POST /api/process-card/images/upload
# ──────────────────────────────────────────────


@post(
    path="/api/process-card/images/upload",
    summary="上传工序卡配图",
    description=(
        "上传工序卡所需的全部图片（支持批量）。"
        "表单字段名使用 `files`，可重复多次以批量上传。"
        "返回每张图片的唯一 image_id，后续在工序卡 JSON 中引用。"
    ),
    status_code=HTTP_201_CREATED,
)
async def upload_images(request: Request) -> ImageBatchUploadResponse:
    """批量上传图片，返回 image_id 列表。"""
    store = get_image_store()
    results: list[ImageUploadResult] = []
    errors: list[dict] = []

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return ImageBatchUploadResponse(
            status="error",
            images=[],
            total_count=0,
            total_size_bytes=0,
            errors=[{"error": "Content-Type 必须为 multipart/form-data"}],
        )

    form = await request.form()
    uploaded_files = form.getall("files")

    if not uploaded_files:
        return ImageBatchUploadResponse(
            status="error",
            images=[],
            total_count=0,
            total_size_bytes=0,
            errors=[{"error": "未收到任何文件，请在 `files` 字段中上传图片"}],
        )

    for f in uploaded_files:
        raw = await f.read()
        filename = f.filename if hasattr(f, "filename") and f.filename else "unknown"
        try:
            meta = await store.save(file_data=raw, original_filename=filename)
            results.append(
                ImageUploadResult(
                    image_id=meta.image_id,
                    original_filename=meta.original_filename,
                    mime_type=meta.mime_type,
                    size_bytes=meta.size_bytes,
                )
            )
        except ValueError as e:
            errors.append({"filename": filename, "error": str(e)})

    return ImageBatchUploadResponse(
        status="ok" if not errors else ("error" if not results else "partial"),
        images=results,
        total_count=len(results),
        total_size_bytes=sum(r.size_bytes for r in results),
        errors=errors if errors else None,
    )


# ──────────────────────────────────────────────
# POST /api/process-card/generate
# ──────────────────────────────────────────────


@post(
    path="/api/process-card/generate",
    summary="生成工序卡 PDF",
    description=(
        "接收完整的工序卡 JSON 数据（图片字段填入 image_id），"
        "校验图片引用有效性后，生成 PDF 工序卡文件并返回。"
    ),
    status_code=HTTP_200_OK,
)
async def generate_process_card(data: ProcessCardInput) -> Response:
    """生成工序卡 PDF 文件。"""
    store = get_image_store()

    # ── 1. 收集所有 image_id 引用及其字段路径 ────────────────
    refs: dict[str, list[str]] = {}
    for i, step in enumerate(data.process_step_resources):
        if step.image_id:
            refs.setdefault(step.image_id, []).append(
                f"process_step_resources[{i}].image_id"
            )
    for i, body in enumerate(data.step_bodies):
        for field_name, fid in [
            ("image_id", body.image_id),
            ("image_page_1_id", body.image_page_1_id),
            ("image_page_2_id", body.image_page_2_id),
            ("image_page_3_id", body.image_page_3_id),
        ]:
            if fid:
                refs.setdefault(fid, []).append(f"step_bodies[{i}].{field_name}")

    # ── 2. 批量校验图片是否存在 ──────────────────────────────
    existing = await store.get_batch(list(refs.keys()))
    missing: list[InvalidImageReference] = []
    for iid, field_paths in refs.items():
        if iid not in existing:
            for fp in field_paths:
                missing.append(InvalidImageReference(field_path=fp, image_id=iid))

    if missing:
        return Response(
            content={
                "status": "error",
                "message": f"引用了 {len(missing)} 个不存在的图片，请先上传图片",
                "missing_images": [m.model_dump() for m in missing],
            },
            status_code=400,
            media_type="application/json",
        )

    # ── 3. 生成 PDF ─────────────────────────────────────────
    pdf_service = ProcessCardPDFService(image_store=store)
    pdf_bytes = await pdf_service.generate(data)

    filename = (data.basic_info.document_number or "process_card") + ".pdf"
    return Response(
        content=pdf_bytes,
        status_code=HTTP_200_OK,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )

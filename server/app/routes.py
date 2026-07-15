"""工序卡生成 API 路由。"""

from __future__ import annotations

from litestar import Request, post
from litestar.status_codes import HTTP_201_CREATED

from app.models import (
    ImageBatchUploadResponse,
    ImageUploadResult,
    InvalidImageReference,
    ProcessCardInput,
)
from app.services.image_store import get_image_store


def _collect_image_refs(data: ProcessCardInput) -> dict[str, list[str]]:
    """收集 ProcessCardInput 中所有引用的 image_id → 字段路径 映射。"""
    refs: dict[str, list[str]] = {}

    for i, step in enumerate(data.process_step_resources):
        if step.image_id:
            refs.setdefault(step.image_id, []).append(
                f"process_step_resources[{i}].image_id"
            )

    for i, body in enumerate(data.step_bodies):
        if body.image_id:
            refs.setdefault(body.image_id, []).append(
                f"step_bodies[{i}].image_id"
            )
        if body.image_page_1_id:
            refs.setdefault(body.image_page_1_id, []).append(
                f"step_bodies[{i}].image_page_1_id"
            )
        if body.image_page_2_id:
            refs.setdefault(body.image_page_2_id, []).append(
                f"step_bodies[{i}].image_page_2_id"
            )
        if body.image_page_3_id:
            refs.setdefault(body.image_page_3_id, []).append(
                f"step_bodies[{i}].image_page_3_id"
            )

    return refs


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
    summary="接收工序卡数据并生成 PDF",
    description=(
        "接收完整的工序卡 JSON 数据（图片字段填入 image_id），"
        "校验图片引用有效性后，生成 PDF 工序卡文件。"
    ),
    status_code=HTTP_201_CREATED,
)
async def generate_process_card(data: ProcessCardInput) -> dict:
    """接收工序卡输入数据，校验图片引用。"""
    store = get_image_store()

    refs = _collect_image_refs(data)
    referenced_ids = list(refs.keys())

    existing = await store.get_batch(referenced_ids)
    missing: list[InvalidImageReference] = []
    for iid, field_paths in refs.items():
        if iid not in existing:
            for fp in field_paths:
                missing.append(InvalidImageReference(field_path=fp, image_id=iid))

    if missing:
        return {
            "status": "error",
            "message": f"引用了 {len(missing)} 个不存在的图片，请先上传图片",
            "missing_images": [m.model_dump() for m in missing],
        }

    return {
        "status": "ok",
        "message": "数据校验通过，图片引用全部有效，已成功接收工序卡数据",
        "summary": {
            "process_number": data.basic_info.process_number,
            "process_name": data.basic_info.process_name,
            "step_count": len(data.process_step_resources),
            "action_count": len(data.step_bodies),
            "material_count": len(data.material_list),
            "referenced_image_count": len(referenced_ids),
        },
    }

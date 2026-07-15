from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from datetime import datetime, timezone

from loguru import logger

# 允许的图片 MIME 类型
ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/bmp",
    "image/webp",
    "image/svg+xml",
})

# 允许的图片扩展名
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
})

# 单张图片最大 10 MB
MAX_IMAGE_SIZE_BYTES: int = 10 * 1024 * 1024


class ImageMeta:
    """已存储图片的元数据。"""

    def __init__(
        self,
        image_id: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        stored_path: Path,
        uploaded_at: datetime,
    ) -> None:
        self.image_id = image_id
        self.original_filename = original_filename
        self.mime_type = mime_type
        self.size_bytes = size_bytes
        self.stored_path = stored_path
        self.uploaded_at = uploaded_at


class ImageStore:
    """简单的文件系统图片存储。

    生产环境可替换为 S3 / MinIO 实现。
    """

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, ImageMeta] = {}
        self._lock = asyncio.Lock()

    async def save(
        self,
        file_data: bytes,
        original_filename: str,
        mime_type: str | None = None,
    ) -> ImageMeta:
        """保存一张图片，返回元数据。"""

        # --- 校验尺寸 ---
        if len(file_data) > MAX_IMAGE_SIZE_BYTES:
            raise ValueError(
                f"图片 {original_filename} 大小 {len(file_data)} bytes 超过上限 "
                f"{MAX_IMAGE_SIZE_BYTES} bytes"
            )

        # --- 校验扩展名 ---
        suffix = Path(original_filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"不支持的文件类型: {suffix}，允许的类型: {sorted(ALLOWED_EXTENSIONS)}"
            )

        # --- 推断 MIME ---
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(original_filename)
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"不支持的 MIME 类型: {mime_type}，允许: {sorted(ALLOWED_MIME_TYPES)}"
            )

        # --- 生成唯一 ID 并写入磁盘 ---
        image_id = uuid.uuid4().hex
        stored_path = self.storage_dir / f"{image_id}{suffix}"
        stored_path.write_bytes(file_data)

        meta = ImageMeta(
            image_id=image_id,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=len(file_data),
            stored_path=stored_path,
            uploaded_at=datetime.now(timezone.utc),
        )

        async with self._lock:
            self._registry[image_id] = meta

        logger.info(
            f"图片已保存: id={image_id}, file={original_filename}, "
            f"size={len(file_data)} bytes"
        )
        return meta

    async def exists(self, image_id: str) -> bool:
        async with self._lock:
            return image_id in self._registry and self._registry[image_id].stored_path.exists()

    async def get(self, image_id: str) -> ImageMeta | None:
        async with self._lock:
            meta = self._registry.get(image_id)
            if meta and meta.stored_path.exists():
                return meta
            return None

    async def get_batch(self, image_ids: list[str]) -> dict[str, ImageMeta]:
        """批量获取。不存在的 ID 不会出现在结果中。"""
        result: dict[str, ImageMeta] = {}
        async with self._lock:
            for iid in image_ids:
                meta = self._registry.get(iid)
                if meta and meta.stored_path.exists():
                    result[iid] = meta
        return result

    async def read_bytes(self, image_id: str) -> bytes | None:
        meta = await self.get(image_id)
        if meta is None:
            return None
        return meta.stored_path.read_bytes()


# 全局单例
_image_store: ImageStore | None = None


def get_image_store() -> ImageStore:
    global _image_store
    if _image_store is None:
        # 存储目录：项目根目录下的 uploads/images/
        storage_dir = Path(__file__).resolve().parent.parent.parent / "uploads" / "images"
        _image_store = ImageStore(storage_dir)
    return _image_store

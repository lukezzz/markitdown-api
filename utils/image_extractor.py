import base64
import os
import zipfile
from typing import Dict, List

IMAGE_EXT_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".svg": "image/svg+xml",
}

ZIP_IMAGE_DIRS = {
    "docx": "word/media/",
    "pptx": "ppt/media/",
    "xlsx": "xl/media/",
}


def _to_image_payload(filename: str, raw_data: bytes) -> Dict[str, object] | None:
    ext = os.path.splitext(filename)[1].lower()
    content_type = IMAGE_EXT_TO_MIME.get(ext)
    if not content_type:
        return None

    return {
        "filename": os.path.basename(filename),
        "content_type": content_type,
        "size": len(raw_data),
        "data": base64.b64encode(raw_data).decode("ascii"),
    }


def extract_images(file_path: str, original_filename: str) -> List[Dict[str, object]]:
    extension = ""
    if original_filename and "." in original_filename:
        extension = original_filename.rsplit(".", 1)[1].lower()

    media_dir = ZIP_IMAGE_DIRS.get(extension)
    if not media_dir:
        return []

    images: List[Dict[str, object]] = []

    try:
        with zipfile.ZipFile(file_path, "r") as archive:
            for member in archive.namelist():
                if not member.startswith(media_dir) or member.endswith("/"):
                    continue

                raw_data = archive.read(member)
                image_payload = _to_image_payload(member, raw_data)
                if image_payload:
                    images.append(image_payload)
    except zipfile.BadZipFile:
        return []

    return images

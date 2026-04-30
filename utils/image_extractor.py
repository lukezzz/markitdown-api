import base64
import os
import re
import zipfile
from typing import Dict, List, Optional, Tuple

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

MIME_TYPE_TO_EXT: Dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/svg+xml": ".svg",
}

_BASE64_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\(data:(image/[a-z+\-.]+);base64,([A-Za-z0-9+/=\s]+)\)'
)


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


def replace_base64_images_in_markdown(
    markdown: str,
    zip_images: Optional[List[Dict[str, object]]] = None,
) -> Tuple[str, List[Dict[str, object]]]:
    """Replace inline base64 data URI images in markdown with filenames.

    When zip_images are provided, each inline base64 is matched by raw bytes
    against the ZIP images and the ZIP filename is used (e.g. image1.png).
    Images not found in ZIP get synthetic names (inline_image_001.png, ...).

    Returns (modified_markdown, list_of_unmatched_inline_image_dicts).
    """
    # Build bytes → filename lookup from ZIP images
    zip_lookup: Dict[bytes, str] = {}
    if zip_images:
        for img in zip_images:
            raw = base64.b64decode(img["data"])
            zip_lookup[raw] = img["filename"]

    seen: Dict[str, str] = {}   # stripped b64 -> assigned filename
    inline_images: List[Dict[str, object]] = []
    counter = 0

    def _replace(match: re.Match) -> str:
        nonlocal counter
        alt_text = match.group(1)
        mime_type = match.group(2)
        b64_data = re.sub(r"\s+", "", match.group(3))  # strip any whitespace
        if b64_data not in seen:
            raw = base64.b64decode(b64_data)
            if raw in zip_lookup:
                filename = zip_lookup[raw]
            else:
                counter += 1
                ext = MIME_TYPE_TO_EXT.get(mime_type, ".bin")
                filename = f"inline_image_{counter:03d}{ext}"
                inline_images.append(
                    {
                        "filename": filename,
                        "content_type": mime_type,
                        "size": len(raw),
                        "data": b64_data,
                    }
                )
            seen[b64_data] = filename
        return f"![{alt_text}]({seen[b64_data]})"

    modified = _BASE64_IMAGE_RE.sub(_replace, markdown)
    return modified, inline_images


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

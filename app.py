import logging
import os
import tempfile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from markitdown import MarkItDown
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from utils.image_extractor import extract_images

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()


class ImageItem(BaseModel):
    filename: str = Field(..., description="Original filename of the embedded image")
    content_type: str = Field(..., description="MIME type, e.g. image/png")
    size: int = Field(..., description="Image size in bytes")
    data: str = Field(..., description="Base64-encoded image data")


class ProcessFileResponse(BaseModel):
    markdown: str = Field(..., description="Document content converted to Markdown")
    images: list[ImageItem] = Field(
        default_factory=list,
        description="Embedded images extracted from the source document (docx/pptx/xlsx)",
    )


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error message")


class OCRProcessFileResponse(BaseModel):
    markdown: str = Field(..., description="Document content converted to Markdown")
    model: str = Field(..., description="LLM model used for OCR")
    ocr_enabled: bool = Field(..., description="Whether OCR plugin conversion was enabled")

app = FastAPI(
    title="MarkItDown API Server",
    description="API endpoint to extract text and convert it to markdown, using MarkItDown (https://github.com/microsoft/markitdown).",
)


FORBIDDEN_EXTENSIONS = [
    # Executable and Script Files (Security Risk)
    "exe",
    "msi",
    "bat",
    "cmd",  # Windows
    "dmg",
    "pkg",
    "app",  # macOS
    "bin",
    "sh",
    "run",  # Linux/Unix
    "dll",
    "so",
    "dylib",  # Dynamic libraries
    "jar",
    "apk",  # Java/Android packages
    "vbs",
    "ps1",  # Windows scripting
    "pyc",
    "pyo",  # Compiled Python
    # System and Configuration Files
    "sys",
    "drv",  # System and driver files
    "config",
    "ini",  # Configuration files
    # Binary Data Files
    "dat",
    "bin",  # Generic binary data
    "db",
    "sqlite",
    "mdb",  # Database files
    "dbf",
    "myd",  # Database format files
    # CAD and Specialized Technical Files
    "dxf",
    "dwg",  # AutoCAD files
    "stl",
    "obj",
    "3ds",  # 3D model files
    "blend",  # Blender 3D files
    # Encrypted/Protected Files
    "gpg",
    "asc",
    "pgp",  # Encrypted files
    # Virtual Machine and Container Files
    "vdi",
    "vmdk",
    "ova",  # Virtual machine disks
    "docker",
    "containerd",  # Container images
    # Other Binary Formats
    "class",  # Java class files
    "o",
    "a",  # Object and archive files
    "lib",
    "obj",  # Compiled library files
    "ttf",
    "otf",  # Font files
    "fon",  # Windows font resource
]


def is_forbidden_file(filename):
    return (
        "." in filename and filename.rsplit(".", 1)[1].lower() in FORBIDDEN_EXTENSIONS
    )


def convert_to_md(filepath: str) -> str:
    logger.info(f"Converting file: {filepath}")
    markitdown = MarkItDown()
    result = markitdown.convert(filepath)
    logger.info(f"Conversion result: {result.text_content[:100]}")
    return result.text_content


def convert_to_md_with_ocr(
    filepath: str,
    llm_model: str,
    llm_prompt: str | None = None,
) -> str:
    logger.info(f"Converting file with OCR plugin: {filepath}, model={llm_model}")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for OCR endpoint")

    markitdown_kwargs = {
        "enable_plugins": True,
        "llm_client": OpenAI(api_key=openai_api_key),
        "llm_model": llm_model,
    }
    if llm_prompt:
        markitdown_kwargs["llm_prompt"] = llm_prompt

    markitdown = MarkItDown(**markitdown_kwargs)
    result = markitdown.convert(filepath)
    logger.info(f"OCR conversion result: {result.text_content[:100]}")
    return result.text_content


@app.get("/")
def read_root():
    return {"MarkItDown API Server": "hit /docs for endpoint reference"}


@app.on_event("startup")
def validate_openai_config() -> None:
    """Fail fast at startup when OCR API prerequisites are missing."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required. Set it via environment variable or .env file before startup."
        )


@app.post(
    "/process_file",
    response_model=ProcessFileResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def process_file(file: UploadFile = File(...)):
    if is_forbidden_file(file.filename):
        return JSONResponse(content={"error": "File type not allowed"}, status_code=400)

    temp_file_path = None

    try:
        # Save the file to a temporary directory
        original_ext = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_ext) as temp_file:
            temp_file.write(await file.read())
            temp_file_path = temp_file.name
            logger.info(f"Temporary file path: {temp_file_path}")

        # Convert the file to markdown
        markdown_content = convert_to_md(temp_file_path)
        logger.info("File converted to markdown successfully")

        # Extract embedded images for supported source formats
        images = extract_images(temp_file_path, file.filename or "")
        logger.info(f"Extracted {len(images)} embedded image(s)")

        # Append markdown image references for any image not already cited
        unreferenced = [
            img for img in images if img["filename"] not in markdown_content
        ]
        if unreferenced:
            refs = "\n".join(
                f"![{img['filename']}]({img['filename']})" for img in unreferenced
            )
            markdown_content = markdown_content.rstrip() + "\n\n" + refs
            logger.info(f"Appended {len(unreferenced)} image reference(s) to markdown")

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

    finally:
        # Ensure the temporary file is deleted
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"Temporary file deleted: {temp_file_path}")

    return ProcessFileResponse(markdown=markdown_content, images=images)


@app.post(
    "/process_file_ocr",
    response_model=OCRProcessFileResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def process_file_ocr(
    file: UploadFile = File(...),
    llm_prompt: str | None = Form(default=None),
):
    if is_forbidden_file(file.filename):
        return JSONResponse(content={"error": "File type not allowed"}, status_code=400)

    temp_file_path = None

    try:
        selected_model = os.getenv("OPENAI_MODEL")
        if not selected_model:
            raise ValueError("OPENAI_MODEL is required for OCR endpoint")

        original_ext = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=original_ext) as temp_file:
            temp_file.write(await file.read())
            temp_file_path = temp_file.name
            logger.info(f"Temporary OCR file path: {temp_file_path}")

        markdown_content = convert_to_md_with_ocr(
            temp_file_path,
            llm_model=selected_model,
            llm_prompt=llm_prompt,
        )
        logger.info("File converted to markdown with OCR successfully")

    except Exception as e:
        logger.error(f"An OCR error occurred: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"Temporary OCR file deleted: {temp_file_path}")

    return OCRProcessFileResponse(
        markdown=markdown_content,
        model=selected_model,
        ocr_enabled=True,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8490)

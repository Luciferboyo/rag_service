import fitz  # PyMuPDF
from pathlib import Path

MIN_PAGE_CHARS = 10  # 过滤内容过少的页面


def parse(filename: str, file_bytes: bytes) -> str:
    if not isinstance(file_bytes, (bytes, bytearray)):
        raise TypeError(f"file_bytes 应为 bytes 类型，实际收到: {type(file_bytes)}")

    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return _parse_pdf(file_bytes)
    elif ext in (".txt", ".md"):
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"不支持的文件类型: {ext}，仅支持 pdf/txt/md")


def _parse_pdf(file_bytes: bytes) -> str:
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            pages = [
                text
                for page in doc
                if len((text := page.get_text("text")).strip()) >= MIN_PAGE_CHARS
            ]
        return "\n\n".join(pages)
    except fitz.FileDataError as e:
        raise ValueError(f"PDF 解析失败，文件可能已损坏或加密: {e}") from e
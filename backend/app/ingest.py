"""Read PDF / TXT / MD files and split them into overlapping word-based chunks."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md"}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    source: str  # file name, shown to the farmer as the citation
    page: int


def _clean(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"-\n(\w)", r"\1", text)      # re-join words hyphenated across lines
    text = re.sub(r"[ \t]+", " ", text)         # collapse spaces
    text = re.sub(r"\n{2,}", "\n", text)        # collapse blank lines
    return text.strip()


def extract_pages(filename: str, data: bytes) -> list[tuple[int, str]]:
    """Return (page_number, text) pairs. Text files count as a single page."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type '{suffix or 'none'}'. Upload a PDF, TXT or MD file.")
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            text = _clean(page.extract_text() or "")
            if text:
                pages.append((number, text))
        return pages
    text = _clean(data.decode("utf-8", errors="replace"))
    return [(1, text)] if text else []


def chunk_text(text: str, size: int = 120, overlap: int = 20) -> list[str]:
    """Split text into windows of `size` words that overlap by `overlap` words."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    words = text.split()
    if not words:
        return []
    step = size - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return chunks


def build_chunks(filename: str, data: bytes, size: int = 120, overlap: int = 20) -> list[Chunk]:
    name = Path(filename).name
    stem = Path(name).stem
    chunks: list[Chunk] = []
    for page_number, text in extract_pages(name, data):
        for piece in chunk_text(text, size, overlap):
            chunks.append(Chunk(
                chunk_id=f"{stem}-{len(chunks) + 1:04d}",
                text=piece,
                source=name,
                page=page_number,
            ))
    return chunks

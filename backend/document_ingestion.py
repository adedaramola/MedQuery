"""
Document parsing and chunking for PDF, DOCX, and plain-text files.

Chunks are produced with a fixed character window and overlap so that
context is not lost at boundaries.  IDs are deterministic so re-running
the ingest script on the same file is a safe upsert.
"""
import hashlib
import io
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800     # characters per chunk
CHUNK_OVERLAP = 150  # characters shared between consecutive chunks


# ──────────────────────────────────────────────────────────
# Text chunking
# ──────────────────────────────────────────────────────────

def _chunk_text(text: str, filename: str, page: int = None) -> List[Tuple[str, dict]]:
    """Split *text* into overlapping chunks. Returns list of (chunk_text, metadata)."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        chunk = text[start : start + CHUNK_SIZE].strip()
        if chunk:
            meta = {"filename": filename, "chunk_index": idx}
            if page is not None:
                meta["page"] = page
            chunks.append((chunk, meta))
            idx += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ──────────────────────────────────────────────────────────
# Parsers
# ──────────────────────────────────────────────────────────

def parse_pdf(file_bytes: bytes, filename: str) -> List[Tuple[str, dict]]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    all_chunks: List[Tuple[str, dict]] = []
    global_idx = 0
    for page_num, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        for chunk, meta in _chunk_text(text, filename, page=page_num + 1):
            meta["chunk_index"] = global_idx
            all_chunks.append((chunk, meta))
            global_idx += 1
    return all_chunks


def parse_docx(file_bytes: bytes, filename: str) -> List[Tuple[str, dict]]:
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return _chunk_text(full_text, filename)


def parse_txt(file_bytes: bytes, filename: str) -> List[Tuple[str, dict]]:
    text = file_bytes.decode("utf-8", errors="replace")
    return _chunk_text(text, filename)


_PARSERS = {
    ".pdf":  parse_pdf,
    ".docx": parse_docx,
    ".txt":  parse_txt,
}

SUPPORTED_EXTENSIONS = set(_PARSERS.keys())


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

def parse_document(file_bytes: bytes, filename: str) -> List[Tuple[str, dict]]:
    """Dispatch to the right parser based on file extension."""
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        raise ValueError(
            f"Unsupported file type: {ext!r}. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    chunks = parser(file_bytes, filename)
    logger.info(f"Parsed '{filename}': {len(chunks)} chunks")
    return chunks


def make_chunk_ids(filename: str, chunks: List[Tuple[str, dict]]) -> List[str]:
    """Stable, deterministic IDs — re-ingesting the same file upserts cleanly."""
    return [
        hashlib.md5(f"doc:{filename}:{meta['chunk_index']}".encode()).hexdigest()
        for _, meta in chunks
    ]

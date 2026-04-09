"""
Unit tests for backend/document_ingestion.py

All file I/O is kept in-memory — no disk reads, no network calls.
"""
import io
import pytest
from unittest.mock import MagicMock, patch

from backend.document_ingestion import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    SUPPORTED_EXTENSIONS,
    _chunk_text,
    make_chunk_ids,
    parse_document,
    parse_txt,
)


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_empty_string_returns_empty(self):
        assert _chunk_text("", "file.txt") == []

    def test_whitespace_only_returns_empty(self):
        assert _chunk_text("   \n\t  ", "file.txt") == []

    def test_short_text_produces_one_chunk(self):
        chunks = _chunk_text("Hello world", "file.txt")
        assert len(chunks) == 1
        assert chunks[0][0] == "Hello world"

    def test_chunk_metadata_contains_filename(self):
        chunks = _chunk_text("Some text", "report.txt")
        assert chunks[0][1]["filename"] == "report.txt"

    def test_chunk_index_starts_at_zero(self):
        chunks = _chunk_text("Some text", "report.txt")
        assert chunks[0][1]["chunk_index"] == 0

    def test_page_included_in_metadata_when_provided(self):
        chunks = _chunk_text("Some text", "doc.pdf", page=3)
        assert chunks[0][1]["page"] == 3

    def test_page_absent_when_not_provided(self):
        chunks = _chunk_text("Some text", "doc.txt")
        assert "page" not in chunks[0][1]

    def test_long_text_produces_multiple_chunks(self):
        text = "A" * (CHUNK_SIZE * 3)
        chunks = _chunk_text(text, "big.txt")
        assert len(chunks) > 1

    def test_chunks_overlap(self):
        # Two consecutive chunks must share CHUNK_OVERLAP characters
        text = "X" * (CHUNK_SIZE + CHUNK_OVERLAP + 10)
        chunks = _chunk_text(text, "f.txt")
        assert len(chunks) >= 2
        end_of_first = chunks[0][0][-CHUNK_OVERLAP:]
        start_of_second = chunks[1][0][:CHUNK_OVERLAP]
        assert end_of_first == start_of_second

    def test_chunk_indices_are_sequential(self):
        text = "B" * (CHUNK_SIZE * 4)
        chunks = _chunk_text(text, "f.txt")
        indices = [meta["chunk_index"] for _, meta in chunks]
        assert indices == list(range(len(chunks)))


# ---------------------------------------------------------------------------
# parse_txt
# ---------------------------------------------------------------------------

class TestParseTxt:
    def test_returns_chunks_from_utf8_bytes(self):
        content = "Medical note: patient shows signs of hypertension."
        chunks = parse_txt(content.encode("utf-8"), "note.txt")
        assert len(chunks) == 1
        assert "hypertension" in chunks[0][0]

    def test_handles_non_utf8_bytes_without_raising(self):
        bad_bytes = b"\xff\xfe" + b"Some text"
        chunks = parse_txt(bad_bytes, "note.txt")
        assert len(chunks) >= 1

    def test_filename_in_metadata(self):
        chunks = parse_txt(b"Hello", "my_file.txt")
        assert chunks[0][1]["filename"] == "my_file.txt"


# ---------------------------------------------------------------------------
# parse_pdf  (PdfReader mocked)
# ---------------------------------------------------------------------------

class TestParsePdf:
    def _make_page(self, text: str):
        page = MagicMock()
        page.extract_text.return_value = text
        return page

    def test_extracts_text_from_pages(self):
        from backend.document_ingestion import parse_pdf
        pages = [self._make_page("Page one content."), self._make_page("Page two content.")]
        mock_reader = MagicMock()
        mock_reader.pages = pages

        with patch("pypdf.PdfReader", return_value=mock_reader):
            chunks = parse_pdf(b"fake-pdf-bytes", "report.pdf")

        texts = [c for c, _ in chunks]
        assert any("Page one" in t for t in texts)
        assert any("Page two" in t for t in texts)

    def test_page_number_in_metadata(self):
        from backend.document_ingestion import parse_pdf
        pages = [self._make_page("Content on page one.")]
        mock_reader = MagicMock()
        mock_reader.pages = pages

        with patch("pypdf.PdfReader", return_value=mock_reader):
            chunks = parse_pdf(b"fake", "doc.pdf")

        assert chunks[0][1]["page"] == 1

    def test_empty_page_produces_no_chunks(self):
        from backend.document_ingestion import parse_pdf
        pages = [self._make_page(""), self._make_page("   ")]
        mock_reader = MagicMock()
        mock_reader.pages = pages

        with patch("pypdf.PdfReader", return_value=mock_reader):
            chunks = parse_pdf(b"fake", "empty.pdf")

        assert chunks == []

    def test_chunk_indices_are_globally_sequential(self):
        from backend.document_ingestion import parse_pdf
        # Two pages each producing more than one chunk
        long_text = "W" * (CHUNK_SIZE * 2)
        pages = [self._make_page(long_text), self._make_page(long_text)]
        mock_reader = MagicMock()
        mock_reader.pages = pages

        with patch("pypdf.PdfReader", return_value=mock_reader):
            chunks = parse_pdf(b"fake", "multi.pdf")

        indices = [meta["chunk_index"] for _, meta in chunks]
        assert indices == list(range(len(chunks)))


# ---------------------------------------------------------------------------
# parse_docx  (python-docx mocked)
# ---------------------------------------------------------------------------

class TestParseDocx:
    def test_joins_paragraphs_and_chunks(self):
        from backend.document_ingestion import parse_docx

        para1, para2 = MagicMock(), MagicMock()
        para1.text = "First paragraph."
        para2.text = "Second paragraph."
        mock_doc = MagicMock()
        mock_doc.paragraphs = [para1, para2]

        with patch("docx.Document", return_value=mock_doc):
            chunks = parse_docx(b"fake-docx", "report.docx")

        combined = " ".join(c for c, _ in chunks)
        assert "First paragraph" in combined
        assert "Second paragraph" in combined

    def test_empty_paragraphs_skipped(self):
        from backend.document_ingestion import parse_docx

        para1, para2 = MagicMock(), MagicMock()
        para1.text = ""
        para2.text = "   "
        mock_doc = MagicMock()
        mock_doc.paragraphs = [para1, para2]

        with patch("docx.Document", return_value=mock_doc):
            chunks = parse_docx(b"fake-docx", "empty.docx")

        assert chunks == []


# ---------------------------------------------------------------------------
# parse_document  (dispatch)
# ---------------------------------------------------------------------------

class TestParseDocument:
    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_document(b"data", "file.csv")

    def test_no_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_document(b"data", "nodotfile")

    def test_dispatches_txt(self):
        chunks = parse_document(b"Hello", "note.txt")
        assert len(chunks) == 1

    def test_dispatches_pdf(self):
        mock_reader = MagicMock()
        page = MagicMock()
        page.extract_text.return_value = "PDF content here."
        mock_reader.pages = [page]
        with patch("pypdf.PdfReader", return_value=mock_reader):
            result = parse_document(b"bytes", "x.pdf")
        assert len(result) == 1
        assert "PDF content" in result[0][0]

    def test_extension_matching_is_case_insensitive(self):
        chunks = parse_document(b"Hello", "NOTE.TXT")
        assert len(chunks) == 1

    def test_supported_extensions_set(self):
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# make_chunk_ids
# ---------------------------------------------------------------------------

class TestMakeChunkIds:
    def _chunks(self, n: int, filename: str = "f.txt"):
        return [("text", {"filename": filename, "chunk_index": i}) for i in range(n)]

    def test_returns_one_id_per_chunk(self):
        chunks = self._chunks(5)
        ids = make_chunk_ids("f.txt", chunks)
        assert len(ids) == 5

    def test_ids_are_unique(self):
        chunks = self._chunks(10)
        ids = make_chunk_ids("f.txt", chunks)
        assert len(set(ids)) == 10

    def test_ids_are_deterministic(self):
        chunks = self._chunks(3)
        assert make_chunk_ids("f.txt", chunks) == make_chunk_ids("f.txt", chunks)

    def test_different_filenames_produce_different_ids(self):
        chunks = self._chunks(1)
        id_a = make_chunk_ids("a.txt", chunks)
        id_b = make_chunk_ids("b.txt", chunks)
        assert id_a != id_b

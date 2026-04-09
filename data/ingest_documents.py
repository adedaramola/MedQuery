"""
Batch-ingest all PDF, DOCX, and TXT files from data/documents/ into the vector store.

Each file is parsed, split into overlapping chunks, embedded via OpenAI, and
upserted into the document_chunks table.  Successfully processed files are
moved to data/documents/processed/ so they are not re-ingested on the next run.

Usage (from the project root):
    python data/ingest_documents.py

Prerequisites:
    - PostgreSQL running with pgvector extension
    - OPENAI_API_KEY set in .env
    - Dependencies installed: pip install -r requirements.txt
"""
import logging
import os
import shutil
import sys

# Allow running as a script from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.document_ingestion import (
    SUPPORTED_EXTENSIONS,
    make_chunk_ids,
    parse_document,
)
from backend.vector_store import init_document_schema, ingest_document_chunks

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DOCUMENTS_DIR = os.path.join(os.path.dirname(__file__), "documents")
PROCESSED_DIR = os.path.join(DOCUMENTS_DIR, "processed")


def main() -> None:
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    # Ensure the DB table exists before we try to write
    init_document_schema()

    candidates = [
        f for f in os.listdir(DOCUMENTS_DIR)
        if os.path.isfile(os.path.join(DOCUMENTS_DIR, f))
        and os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
    ]

    if not candidates:
        print(
            f"No supported files found in {DOCUMENTS_DIR}.\n"
            f"Add PDF, DOCX, or TXT files and re-run.\n"
            f"Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
        )
        return

    print(f"Found {len(candidates)} file(s) to process.\n")

    total_chunks = 0
    ok_count = 0
    for filename in sorted(candidates):
        src = os.path.join(DOCUMENTS_DIR, filename)
        dst = os.path.join(PROCESSED_DIR, filename)
        print(f"  Processing: {filename}")
        try:
            with open(src, "rb") as fh:
                file_bytes = fh.read()

            chunks = parse_document(file_bytes, filename)
            if not chunks:
                print(f"    [SKIP] No text could be extracted — file not moved.\n")
                continue

            ids = make_chunk_ids(filename, chunks)
            texts = [c[0] for c in chunks]
            metas = [c[1] for c in chunks]

            count = ingest_document_chunks(ids, texts, metas, filename)
            shutil.move(src, dst)

            total_chunks += count
            ok_count += 1
            print(f"    [OK] {count} chunks ingested → moved to processed/\n")

        except Exception as exc:
            logger.error(f"    [ERROR] {filename}: {exc}\n")

    print(
        f"Done. {ok_count}/{len(candidates)} file(s) ingested, "
        f"{total_chunks} total chunks stored."
    )


if __name__ == "__main__":
    main()

import hashlib
import json
import logging
import os
from typing import List

import numpy as np
import pandas as pd
from openai import OpenAI

from backend.config import OPENAI_API_KEY, EMBED_MODEL, N_RESULTS
from backend.db import get_conn, get_vector_conn, put_conn

logger = logging.getLogger(__name__)

_openai_client = OpenAI(api_key=OPENAI_API_KEY)

VECTOR_DIM = 1536  # text-embedding-3-small


# ──────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────

def init_schema() -> None:
    """Create pgvector extension + tables + HNSW indexes (idempotent)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS medical_qna (
                    id        TEXT PRIMARY KEY,
                    content   TEXT NOT NULL,
                    embedding vector({VECTOR_DIM}),
                    metadata  JSONB
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS medical_device (
                    id        TEXT PRIMARY KEY,
                    content   TEXT NOT NULL,
                    embedding vector({VECTOR_DIM}),
                    metadata  JSONB
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_medical_qna_embedding
                ON medical_qna USING hnsw (embedding vector_cosine_ops)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_medical_device_embedding
                ON medical_device USING hnsw (embedding vector_cosine_ops)
            """)
            conn.commit()
        logger.info("PostgreSQL/pgvector schema initialised")
    except Exception as e:
        conn.rollback()
        logger.error(f"Schema init error: {e}")
        raise
    finally:
        put_conn(conn)


# ──────────────────────────────────────────────────────────
# Embeddings
# ──────────────────────────────────────────────────────────

def _embed(texts: List[str]) -> List[np.ndarray]:
    try:
        response = _openai_client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [np.array(item.embedding) for item in response.data]
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise


# ──────────────────────────────────────────────────────────
# Query
# ──────────────────────────────────────────────────────────

def _query_table(table: str, query: str, n: int = N_RESULTS) -> List[str]:
    embedding = _embed([query])[0]
    conn = get_vector_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT content FROM {table} ORDER BY embedding <=> %s LIMIT %s",
                (embedding, n),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        put_conn(conn)


def query_qna(query: str, n: int = N_RESULTS) -> List[str]:
    return _query_table("medical_qna", query, n)


def query_device(query: str, n: int = N_RESULTS) -> List[str]:
    return _query_table("medical_device", query, n)


# ──────────────────────────────────────────────────────────
# Counts (used by /api/health)
# ──────────────────────────────────────────────────────────

def _count(table: str) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()[0]
    except Exception:
        return 0
    finally:
        put_conn(conn)


def count_qna() -> int:
    return _count("medical_qna")


def count_device() -> int:
    return _count("medical_device")


# ──────────────────────────────────────────────────────────
# Ingest
# ──────────────────────────────────────────────────────────

def _upsert(table: str, ids: List[str], docs: List[str], metas: List[dict]) -> None:
    embeddings = _embed(docs)
    conn = get_vector_conn()
    try:
        with conn.cursor() as cur:
            for id_, doc, emb, meta in zip(ids, docs, embeddings, metas):
                cur.execute(
                    f"""
                    INSERT INTO {table} (id, content, embedding, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        content   = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata  = EXCLUDED.metadata
                    """,
                    (id_, doc, emb, json.dumps(meta)),
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Upsert error: {e}")
        raise
    finally:
        put_conn(conn)


def ingest_data(
    qa_csv: str = "data/medical_q_n_a.csv",
    device_csv: str = "data/medical_device_manuals_dataset.csv",
    pubmed_csv: str = "data/medical_pubmed.csv",
    fda_csv: str = "data/medical_fda_labels.csv",
    sample_size: int = 500,
) -> dict:
    """
    Ingest Q&A and device data.

    Data priority:
      1. data/medical_pubmed.csv  — real PubMed abstracts (run data/fetch_real_data.py first)
      2. data/medical_q_n_a.csv   — synthetic fallback (clearly labelled)
      3. data/medical_fda_labels.csv — real FDA drug labels
      4. data/medical_device_manuals_dataset.csv — synthetic fallback

    If both a real CSV and a synthetic CSV exist, BOTH are ingested so the
    real data enriches rather than replaces the structured device knowledge.
    """
    counts = {"qa": 0, "device": 0}

    # --- Q&A: prefer real PubMed, supplement with synthetic ---
    qa_sources = []
    if os.path.exists(pubmed_csv):
        qa_sources.append((pubmed_csv, "PubMed"))
    if os.path.exists(qa_csv):
        qa_sources.append((qa_csv, "synthetic"))
    if not qa_sources:
        logger.warning("No Q&A CSV found. Run data/fetch_real_data.py to generate real data.")

    for src_path, src_label in qa_sources:
        df_qa = pd.read_csv(src_path)
        if src_label == "synthetic":
            # Surface the synthetic origin in metadata so the system knows
            df_qa["source_label"] = "SYNTHETIC — do not rely on for clinical decisions"
        df_qa = df_qa.drop_duplicates(subset=["Question"]).reset_index(drop=True)
        df_qa = df_qa.sample(min(sample_size, len(df_qa)), random_state=42)
        df_qa["combined_text"] = (
            "Q: " + df_qa["Question"].astype(str) + " | "
            "A: " + df_qa["Answer"].astype(str) + " | "
            "Type: " + df_qa.get("qtype", pd.Series(["General"] * len(df_qa))).astype(str)
        )
        # Prefix IDs with source label to avoid cross-source collisions
        ids = [hashlib.md5(f"{src_label}:{q}".encode()).hexdigest() for q in df_qa["Question"]]
        _upsert(
            "medical_qna",
            ids=ids,
            docs=df_qa["combined_text"].tolist(),
            metas=df_qa.to_dict(orient="records"),
        )
        counts["qa"] += len(df_qa)
        logger.info(f"Ingested {len(df_qa)} Q&A records from {src_label} ({src_path})")

    # --- Device / drug labels: prefer real FDA labels, supplement with synthetic ---
    device_sources = []
    if os.path.exists(fda_csv):
        device_sources.append((fda_csv, "FDA"))
    if os.path.exists(device_csv):
        device_sources.append((device_csv, "synthetic"))
    if not device_sources:
        logger.warning("No device CSV found. Run data/fetch_real_data.py to generate real data.")

    for src_path, src_label in device_sources:
        df_dev = pd.read_csv(src_path)
        if src_label == "synthetic":
            df_dev["source_label"] = "SYNTHETIC — do not rely on for clinical decisions"
        df_dev = df_dev.drop_duplicates(subset=["Device_Name", "Model_Number"]).reset_index(drop=True)
        df_dev = df_dev.sample(min(sample_size, len(df_dev)), random_state=42)
        df_dev["combined_text"] = (
            "Device: " + df_dev.get("Device_Name", "Unknown").astype(str) + " | "
            "Model: " + df_dev.get("Model_Number", "N/A").astype(str) + " | "
            "Indications: " + df_dev.get("Indications_for_Use", "N/A").astype(str) + " | "
            "Contraindications: " + df_dev.get("Contraindications", "N/A").astype(str)
        )
        ids = [hashlib.md5(f"{src_label}:{r['Device_Name']}{r['Model_Number']}".encode()).hexdigest()
               for _, r in df_dev.iterrows()]
        _upsert(
            "medical_device",
            ids=ids,
            docs=df_dev["combined_text"].tolist(),
            metas=df_dev.to_dict(orient="records"),
        )
        counts["device"] += len(df_dev)
        logger.info(f"Ingested {len(df_dev)} device records from {src_label} ({src_path})")

    return counts

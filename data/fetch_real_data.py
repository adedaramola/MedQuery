"""
Fetch real medical corpora from public APIs and write ingestion-ready CSVs.

Sources:
  - PubMed E-utilities  (free, no auth)   → medical_pubmed.csv
  - openFDA drug labels (free, no auth)   → medical_fda_labels.csv

Usage:
    python data/fetch_real_data.py [--pubmed-queries N] [--fda-drugs N]

Output files are written to the same data/ directory and can be passed
directly to the /api/ingest endpoint or the ingest script.

NOTE: These APIs have rate limits.  Default fetches are conservative.
  PubMed: 3 requests/second without an API key, 10/s with NCBI_API_KEY set.
  openFDA: 240 requests/minute without an API key.
"""

import argparse
import csv
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# PubMed helpers
# ---------------------------------------------------------------------------

PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

PUBMED_QUERIES = [
    "hypertension treatment guidelines",
    "diabetes mellitus management",
    "asthma diagnosis clinical",
    "myocardial infarction therapy",
    "stroke prevention anticoagulation",
    "pneumonia antibiotic treatment",
    "chronic kidney disease progression",
    "heart failure management",
    "rheumatoid arthritis biologics",
    "depression antidepressant efficacy",
    "epilepsy anticonvulsant review",
    "osteoporosis bisphosphonate treatment",
    "COPD exacerbation management",
    "lupus hydroxychloroquine",
    "Kawasaki disease IVIG treatment",
    "sepsis management protocol",
    "atrial fibrillation anticoagulation",
    "chronic pain opioid guidelines",
    "obesity bariatric surgery outcomes",
    "COVID-19 clinical management",
]


def _pubmed_api_key() -> dict:
    key = os.getenv("NCBI_API_KEY", "")
    return {"api_key": key} if key else {}


def fetch_pubmed_abstracts(queries: list[str], max_per_query: int = 10) -> list[dict]:
    """
    For each query, search PubMed for article IDs then fetch title + abstract.
    Returns list of {Question, Answer, qtype} dicts ready for the Q&A CSV.
    """
    rows = []
    seen_ids: set[str] = set()

    for query in queries:
        try:
            # Step 1: search
            search_params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_per_query,
                "retmode": "json",
                **_pubmed_api_key(),
            }
            r = requests.get(PUBMED_SEARCH_URL, params=search_params, timeout=15)
            r.raise_for_status()
            ids = r.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                logger.warning(f"No PubMed results for: {query}")
                continue

            # Deduplicate
            new_ids = [i for i in ids if i not in seen_ids]
            seen_ids.update(new_ids)
            if not new_ids:
                continue

            # Step 2: fetch abstracts
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(new_ids),
                "rettype": "abstract",
                "retmode": "text",
                **_pubmed_api_key(),
            }
            r2 = requests.get(PUBMED_FETCH_URL, params=fetch_params, timeout=30)
            r2.raise_for_status()
            raw = r2.text.strip()

            # Each article is separated by a blank line after the abstract block.
            # We split on double-newlines and take blocks that look like abstracts.
            blocks = [b.strip() for b in raw.split("\n\n") if len(b.strip()) > 100]
            for idx, block in enumerate(blocks):
                # Include block index so each row has a unique Question for deduplication.
                rows.append({
                    "Question": f"[PubMed] {query} [{idx + 1}]",
                    "Answer": block[:2000],   # cap at 2000 chars for embedding efficiency
                    "qtype": "Research",
                })
            logger.info(f"PubMed '{query}': {len(blocks)} abstract blocks")

            # Rate limit: 3 req/s without API key
            delay = 0.35 if not os.getenv("NCBI_API_KEY") else 0.11
            time.sleep(delay)

        except Exception as e:
            logger.error(f"PubMed error for '{query}': {e}")

    logger.info(f"Total PubMed rows collected: {len(rows)}")
    return rows


# ---------------------------------------------------------------------------
# openFDA drug label helpers
# ---------------------------------------------------------------------------

FDA_SEARCH_URL = "https://api.fda.gov/drug/label.json"

FDA_DRUG_QUERIES = [
    "metformin", "lisinopril", "atorvastatin", "amoxicillin", "sertraline",
    "omeprazole", "salbutamol", "warfarin", "alendronate", "methotrexate",
    "furosemide", "levetiracetam", "carbimazole", "hydroxychloroquine",
    "aspirin", "tiotropium", "alteplase", "doxycycline", "ciprofloxacin",
    "prednisone", "levothyroxine", "amlodipine", "ramipril", "clopidogrel",
    "insulin glargine",
]

_FDA_FIELDS = [
    "indications_and_usage",
    "contraindications",
    "warnings_and_cautions",
    "dosage_and_administration",
    "adverse_reactions",
    "drug_interactions",
]


def _extract_fda_section(label: dict, field: str) -> Optional[str]:
    val = label.get(field)
    if isinstance(val, list) and val:
        return val[0][:1500]
    return None


def fetch_fda_drug_labels(drug_names: list[str]) -> list[dict]:
    """
    For each drug name, fetch its FDA label and emit one row per non-empty
    section as {Device_Name, Model_Number, Manufacturer, Indications_for_Use, Contraindications}.
    We reuse the device CSV schema so both can be ingested via the same route.
    """
    rows = []
    for drug in drug_names:
        try:
            params = {
                "search": f'openfda.brand_name:"{drug}"',
                "limit": 1,
            }
            r = requests.get(FDA_SEARCH_URL, params=params, timeout=15)
            if r.status_code == 404:
                # Try generic name
                params["search"] = f'openfda.generic_name:"{drug}"'
                r = requests.get(FDA_SEARCH_URL, params=params, timeout=15)
            r.raise_for_status()
            results = r.json().get("results", [])
            if not results:
                logger.warning(f"No FDA label for: {drug}")
                continue

            label = results[0]
            indications   = _extract_fda_section(label, "indications_and_usage") or ""
            contraindications = _extract_fda_section(label, "contraindications") or ""
            warnings      = _extract_fda_section(label, "warnings_and_cautions") or ""
            dosage        = _extract_fda_section(label, "dosage_and_administration") or ""
            adverse       = _extract_fda_section(label, "adverse_reactions") or ""
            interactions  = _extract_fda_section(label, "drug_interactions") or ""

            brand_names  = label.get("openfda", {}).get("brand_name", [drug])
            manufacturer = label.get("openfda", {}).get("manufacturer_name", ["Unknown"])[0]
            display_name = brand_names[0] if brand_names else drug

            # Combine all non-empty sections into indications field for retrieval
            combined = "\n\n".join(
                f"[{s.upper()}]\n{t}"
                for s, t in [
                    ("Indications", indications),
                    ("Contraindications", contraindications),
                    ("Warnings", warnings),
                    ("Dosage", dosage),
                    ("Adverse Reactions", adverse),
                    ("Drug Interactions", interactions),
                ]
                if t
            )

            rows.append({
                "Device_Name":        f"{display_name} (Drug Label)",
                "Model_Number":       f"FDA-{drug.upper().replace(' ', '-')}",
                "Manufacturer":       manufacturer,
                "Indications_for_Use": combined[:3000],
                "Contraindications":  contraindications or "See full label.",
            })
            logger.info(f"FDA label fetched: {display_name}")
            time.sleep(0.26)   # ~240 req/min limit

        except Exception as e:
            logger.error(f"FDA error for '{drug}': {e}")

    logger.info(f"Total FDA rows collected: {len(rows)}")
    return rows


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"Wrote {len(rows)} rows → {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch real medical data from PubMed and openFDA.")
    parser.add_argument("--pubmed-queries", type=int, default=len(PUBMED_QUERIES),
                        help="Number of PubMed search queries to run (default: all)")
    parser.add_argument("--pubmed-per-query", type=int, default=10,
                        help="Max PubMed abstracts per query (default: 10)")
    parser.add_argument("--fda-drugs", type=int, default=len(FDA_DRUG_QUERIES),
                        help="Number of drug labels to fetch from openFDA (default: all)")
    args = parser.parse_args()

    # PubMed
    pubmed_rows = fetch_pubmed_abstracts(
        PUBMED_QUERIES[: args.pubmed_queries],
        max_per_query=args.pubmed_per_query,
    )
    if pubmed_rows:
        write_csv(
            DATA_DIR / "medical_pubmed.csv",
            pubmed_rows,
            ["Question", "Answer", "qtype"],
        )
    else:
        logger.warning("No PubMed rows fetched — check network access and rate limits.")

    # openFDA
    fda_rows = fetch_fda_drug_labels(FDA_DRUG_QUERIES[: args.fda_drugs])
    if fda_rows:
        write_csv(
            DATA_DIR / "medical_fda_labels.csv",
            fda_rows,
            ["Device_Name", "Model_Number", "Manufacturer", "Indications_for_Use", "Contraindications"],
        )
    else:
        logger.warning("No FDA rows fetched — check network access.")

    print("\nDone. Ingest real data with:")
    print("  POST /api/ingest   (set ingest_pubmed=true / ingest_fda=true)")
    print("  or: python data/ingest_cli.py --source pubmed")


if __name__ == "__main__":
    main()

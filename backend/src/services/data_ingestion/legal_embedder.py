"""
FinSight RegTech - Multi-Act Legal Text Parser & FAISS Vector Store Ingestion
=============================================================================
Aggregates statutory texts across all European Fintech, Banking, and AI Regulations:
- AMLD6 (Directive (EU) 2018/1673)
- AMLD5 (Directive (EU) 2018/843)
- PSD2 (Directive (EU) 2015/2366)
- MiCA (Regulation (EU) 2023/1114)
- TFR (Regulation (EU) 2023/1113)
- DORA (Regulation (EU) 2022/2554)
- EU_AI_ACT (Regulation (EU) 2024/1689)
- GDPR (Regulation (EU) 2016/679)

Parses and chunks documents by individual legal Articles, generates dense embeddings
via Google Gemini Embeddings API, and compiles a single unified FAISS index
at 'backend/data/faiss_index'.
"""

import os
import re
import sys
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Auto-detect local virtual environment site-packages for seamless execution
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # src/services/data_ingestion
SERVICES_DIR = os.path.dirname(SCRIPT_DIR)               # src/services
SRC_DIR = os.path.dirname(SERVICES_DIR)                  # src
BACKEND_DIR = os.path.dirname(SRC_DIR)                   # backend

# Load project environment variables (.env)
load_dotenv(os.path.join(BACKEND_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(BACKEND_DIR), ".env"))

VENV_SITE_PACKAGES = os.path.join(BACKEND_DIR, ".venv", "Lib", "site-packages")
if os.path.exists(VENV_SITE_PACKAGES) and VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# LangChain and Vector Store Imports
try:
    from langchain_core.documents import Document
except ImportError:
    try:
        from langchain.schema import Document
    except ImportError:
        from langchain.docstore.document import Document

try:
    from langchain_community.vectorstores import FAISS
except ImportError:
    from langchain.vectorstores import FAISS

from langchain_google_genai import GoogleGenerativeAIEmbeddings


# =====================================================================
# Configuration Paths & Regulatory Targets
# =====================================================================

REGULATIONS: Dict[str, str] = {
    "AMLD6": "32018L1673",
    "AMLD5": "32018L0843",
    "PSD2": "32015L2366",
    "MiCA": "32023R1114",
    "TFR": "32023R1113",      # Transfer of Funds (Travel Rule)
    "DORA": "32022R2554",     # Digital Operational Resilience Act
    "EU_AI_ACT": "32024R1689", # European Artificial Intelligence Act
    "GDPR": "32016R0679"      # General Data Protection Regulation
}

FAISS_INDEX_DIR = os.path.join(BACKEND_DIR, "data", "faiss_index")
RAW_STATUTES_DIR = os.path.join(BACKEND_DIR, "data", "raw_statutes")
DEFAULT_EMBEDDING_MODEL = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-2-preview")


def get_google_embeddings(model_name: str = DEFAULT_EMBEDDING_MODEL) -> GoogleGenerativeAIEmbeddings:
    """
    Initializes Google Generative AI Embeddings using the Gemini API.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY environment variable is not set. "
            "Please configure GOOGLE_API_KEY in your .env file or environment."
        )

    return GoogleGenerativeAIEmbeddings(
        model=model_name,
        google_api_key=api_key
    )


# =====================================================================
# 1. Statutory Article Parser & Document Chunking
# =====================================================================

def parse_and_chunk_articles(
    raw_text: str,
    source_name: str = "EU_REGULATION",
    celex_id: str = "UNKNOWN_CELEX",
    jurisdiction: str = "EU"
) -> List[Document]:
    """
    Parses statutory text and splits the document by specific sequential Articles.
    Wraps each article into a LangChain Document with enriched regulatory metadata
    dynamically reflecting the source act and CELEX identifier.

    Args:
        raw_text: Full plain text of the directive / regulation.
        source_name: Key identifier of the regulation (e.g. 'MiCA', 'GDPR', 'DORA').
        celex_id: Official CELEX identifier (e.g. '32023R1114').
        jurisdiction: Regulatory jurisdiction (e.g. 'EU').

    Returns:
        List of LangChain Document objects.
    """
    # Regex to match Article headers at line start
    article_pattern = r'(?im)^\s*(?:Article|ARTICLE)\s+(\d+[a-z]?)\b'
    all_matches = list(re.finditer(article_pattern, raw_text))

    # Filter to genuine sequential article headings to avoid mid-sentence cross-references
    filtered_matches = []
    last_num = 0
    for m in all_matches:
        try:
            num = int(re.sub(r'\D', '', m.group(1)))
        except (ValueError, TypeError):
            continue
        if num == last_num + 1 or (last_num == 0 and num <= 3) or (num > last_num and num <= last_num + 5):
            filtered_matches.append(m)
            last_num = num

    # Fallback to all matches if sequence filtering found very few matches
    matches = filtered_matches if len(filtered_matches) >= 5 else all_matches

    documents: List[Document] = []

    # If no explicit article headers are matched, fallback to paragraph or full-text chunking
    if not matches:
        cleaned = raw_text.strip()
        if cleaned:
            # If text is very long, split by double newlines
            paragraphs = [p.strip() for p in cleaned.split("\n\n") if len(p.strip()) > 80]
            if not paragraphs:
                paragraphs = [cleaned]

            for idx, para in enumerate(paragraphs):
                documents.append(
                    Document(
                        page_content=para,
                        metadata={
                            "source": source_name,
                            "celex_id": celex_id,
                            "jurisdiction": jurisdiction,
                            "article_number": idx + 1,
                            "title": f"{source_name} - Section {idx + 1}"
                        }
                    )
                )
        return documents

    # 1. Preamble / Recitals chunk (content preceding Article 1)
    if matches[0].start() > 150:
        preamble_text = raw_text[:matches[0].start()].strip()
        if preamble_text and len(preamble_text) > 100:
            documents.append(
                Document(
                    page_content=preamble_text,
                    metadata={
                        "source": source_name,
                        "celex_id": celex_id,
                        "jurisdiction": jurisdiction,
                        "article_number": 0,
                        "title": f"{source_name} - Preamble & Recitals",
                    }
                )
            )

    # 2. Extract each individual Article block
    for idx, match in enumerate(matches):
        art_str = match.group(1)
        try:
            art_num = int(re.sub(r'\D', '', art_str))
        except (ValueError, TypeError):
            art_num = idx + 1

        start_pos = match.start()
        end_pos = matches[idx + 1].start() if (idx + 1 < len(matches)) else len(raw_text)

        article_block = raw_text[start_pos:end_pos].strip()

        # Extract title line if available right after the Article header
        lines = [line.strip() for line in article_block.splitlines() if line.strip()]
        title_summary = lines[1] if len(lines) > 1 and len(lines[1]) < 140 else f"Article {art_str}"

        doc = Document(
            page_content=article_block,
            metadata={
                "source": source_name,
                "celex_id": celex_id,
                "jurisdiction": jurisdiction,
                "article_number": art_num,
                "article_label": f"Article {art_str}",
                "title": f"{source_name} - {title_summary}",
            }
        )
        documents.append(doc)

    return documents


# =====================================================================
# 2. FAISS Vector Store Building & Persistence
# =====================================================================

import time


def build_faiss_vectorstore(
    documents: List[Document],
    index_dir: str = FAISS_INDEX_DIR,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 25
) -> FAISS:
    """
    Initializes Google Generative AI embeddings, builds a fresh FAISS vector store,
    and saves 'index.faiss' and 'index.pkl' to disk with automatic rate-limit backoff.

    Args:
        documents: List of LangChain Document objects to embed.
        index_dir: Destination folder path for FAISS index binaries.
        model_name: Google GenAI embedding model identifier.
        batch_size: Number of documents to embed per Gemini API batch.

    Returns:
        The newly instantiated FAISS vector store.
    """
    if not documents:
        raise ValueError("Cannot build FAISS index: document list is empty.")

    print(f"\n[Embedder] Initializing Google API Embeddings ('{model_name}')...", flush=True)
    embeddings = get_google_embeddings(model_name)

    os.makedirs(index_dir, exist_ok=True)

    # Sanitize document contents to prevent token overflow on gigantic articles
    for d in documents:
        if len(d.page_content) > 8000:
            d.page_content = d.page_content[:8000]

    total_docs = len(documents)
    total_batches = (total_docs + batch_size - 1) // batch_size
    print(f"[Vector Store] Calling Google Gemini API to embed {total_docs} regulatory documents in {total_batches} batches (size {batch_size})...", flush=True)

    vector_db = None
    backoff_schedule = [15, 30, 45, 60, 90, 120]

    for batch_idx, i in enumerate(range(0, total_docs, batch_size), 1):
        batch = documents[i:i + batch_size]
        print(f" • [Batch {batch_idx}/{total_batches}] Embedding docs {i + 1}-{min(i + batch_size, total_docs)} of {total_docs}...", flush=True)

        for attempt, wait_time in enumerate(backoff_schedule):
            try:
                if vector_db is None:
                    vector_db = FAISS.from_documents(batch, embeddings)
                else:
                    vector_db.add_documents(batch)
                break
            except Exception as err:
                err_str = str(err)
                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "Quota" in err_str or "quota" in err_str.lower()) and attempt < len(backoff_schedule) - 1:
                    print(f"   ⏳ Rate limit detected. Backing off for {wait_time}s (attempt {attempt + 1}/{len(backoff_schedule)})...", flush=True)
                    time.sleep(wait_time)
                else:
                    raise err

        # Pace calls at ~15 requests per minute to respect standard API quotas
        time.sleep(3.5)

    # Persist index binaries (index.faiss and index.pkl)
    vector_db.save_local(index_dir)
    print(f"\n✅ Unified FAISS index binaries saved successfully to: '{index_dir}'", flush=True)
    print(f"   • {os.path.join(index_dir, 'index.faiss')}", flush=True)
    print(f"   • {os.path.join(index_dir, 'index.pkl')}", flush=True)

    return vector_db


# =====================================================================
# 3. Master Multi-Regulation Ingestion Pipeline
# =====================================================================

def main():
    print("=" * 76)
    print("⚖️  FinSight RegTech: Master Multi-Act Legal Parser & FAISS Vector Ingestion")
    print("=" * 76)

    # 1. Master list to collect chunks across all acts
    master_documents: List[Document] = []
    regulations_found = 0

    print("\n[1/3] Parsing statutory text files for all target EU regulations...")

    for name, celex in REGULATIONS.items():
        filename = f"{name.lower()}_raw.txt"
        file_path = os.path.join(RAW_STATUTES_DIR, filename)

        if not os.path.exists(file_path):
            print(f"⚠️  [{name}] File '{filename}' not found at '{RAW_STATUTES_DIR}'. Attempting live fetch via EUR-Lex SPARQL...")
            try:
                from src.services.data_ingestion.eur_lex_fetcher import fetch_regulation
                fetch_regulation(name=name, celex_id=celex, output_path=file_path)
            except Exception as fetch_err:
                print(f"❌ [{name}] Could not fetch '{filename}': {fetch_err}. Skipping.")
                continue

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                raw_content = f.read()

            chunks = parse_and_chunk_articles(
                raw_text=raw_content,
                source_name=name,
                celex_id=celex,
                jurisdiction="EU"
            )

            master_documents.extend(chunks)
            regulations_found += 1
            print(f" • [{name}] Parsed {len(chunks)} Article chunks (CELEX: {celex})")

    print(f"\n[2/3] Aggregation complete: {len(master_documents)} total Document chunks compiled from {regulations_found}/{len(REGULATIONS)} regulations.")

    if not master_documents:
        print("❌ Error: No document chunks were generated. Please run eur_lex_fetcher.py first.")
        return

    # Print sample preview of chunks
    print("\n--- Master Corpus Chunks Sample Preview ---")
    for idx, doc in enumerate(master_documents[:6]):
        src = doc.metadata.get("source", "UNKNOWN")
        art = doc.metadata.get("article_label", f"Art. {doc.metadata.get('article_number', idx)}")
        title = doc.metadata.get("title", "")
        preview = doc.page_content[:75].replace("\n", " ")
        print(f"   [{idx + 1}] [{src}] {art:<12} | {title:<30} | \"{preview}...\"")

    if len(master_documents) > 6:
        print(f"   [... and {len(master_documents) - 6} more Article chunks across all EU acts ...]")

    # 3. Generate dense embeddings via Gemini API and persist single FAISS vector index
    print("\n[3/3] Generating dense embeddings via Google Gemini API & saving unified FAISS index...")
    vector_db = build_faiss_vectorstore(
        documents=master_documents,
        index_dir=FAISS_INDEX_DIR,
        model_name=DEFAULT_EMBEDDING_MODEL
    )

    print("\n" + "=" * 76)
    print(f"✅ Ingestion Complete: {len(master_documents)} Articles from {regulations_found} EU Regulations indexed.")
    print(f"   Destination: {FAISS_INDEX_DIR}")
    print("=" * 76)


if __name__ == "__main__":
    main()

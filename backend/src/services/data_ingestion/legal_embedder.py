"""
FinSight RegTech - AMLD6 Legal Text Parser & FAISS Vector Store Ingestion
========================================================================
Reads the full statutory text from 'backend/amld6_raw.txt', parses and chunks
the document by individual legal Articles, generates dense embeddings
using the project's standard 'all-MiniLM-L6-v2' model, and persists the
FAISS vector index binaries ('index.faiss' and 'index.pkl') to 'backend/data/faiss_index'.
"""

import os
import re
import sys
from typing import List, Dict, Any, Optional

# Auto-detect local virtual environment site-packages for seamless execution
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # src/services/data_ingestion
SERVICES_DIR = os.path.dirname(SCRIPT_DIR)               # src/services
SRC_DIR = os.path.dirname(SERVICES_DIR)                  # src
BACKEND_DIR = os.path.dirname(SRC_DIR)                   # backend

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

from langchain_huggingface import HuggingFaceEmbeddings


# =====================================================================
# Configuration Paths
# =====================================================================

RAW_TEXT_PATH = os.path.join(BACKEND_DIR, "amld6_raw.txt")
FAISS_INDEX_DIR = os.path.join(BACKEND_DIR, "data", "faiss_index")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


# =====================================================================
# 1. Statutory Article Parser & Document Chunking
# =====================================================================

def parse_and_chunk_articles(raw_text: str) -> List[Document]:
    """
    Parses statutory text and splits the document by specific Articles.
    Wraps each article into a LangChain Document with enriched regulatory metadata.

    Args:
        raw_text: Full plain text of the directive / regulation.

    Returns:
        List of LangChain Document objects.
    """
    # Regex to match Article headers (e.g., 'Article 1', 'Article 2', etc.)
    article_pattern = r'(?i)(?:^|\n)\s*Article\s+(\d+)\b'
    matches = list(re.finditer(article_pattern, raw_text))

    documents: List[Document] = []

    if not matches:
        print("⚠️  No explicit 'Article X' headers detected. Chunking entire text as single document.")
        cleaned = raw_text.strip()
        if cleaned:
            documents.append(
                Document(
                    page_content=cleaned,
                    metadata={
                        "source": "AMLD6",
                        "celex_id": "32018L1673",
                        "jurisdiction": "EU",
                        "type": "directive",
                        "article_number": 1,
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
                        "source": "AMLD6",
                        "celex_id": "32018L1673",
                        "jurisdiction": "EU",
                        "type": "directive",
                        "article_number": 0,
                        "title": "Preamble & Recitals",
                    }
                )
            )

    # 2. Extract each individual Article block
    for idx, match in enumerate(matches):
        try:
            art_num = int(match.group(1))
        except (ValueError, TypeError):
            art_num = idx + 1

        start_pos = match.start()
        end_pos = matches[idx + 1].start() if (idx + 1 < len(matches)) else len(raw_text)

        article_block = raw_text[start_pos:end_pos].strip()

        # Extract title line if available right after the Article header
        lines = [line.strip() for line in article_block.splitlines() if line.strip()]
        title_summary = lines[1] if len(lines) > 1 and len(lines[1]) < 120 else f"Article {art_num}"

        doc = Document(
            page_content=article_block,
            metadata={
                "source": "AMLD6",
                "celex_id": "32018L1673",
                "jurisdiction": "EU",
                "type": "directive",
                "article_number": art_num,
                "title": title_summary,
            }
        )
        documents.append(doc)

    return documents


# =====================================================================
# 2. FAISS Vector Store Building & Persistence
# =====================================================================

def build_faiss_vectorstore(
    documents: List[Document],
    index_dir: str = FAISS_INDEX_DIR,
    model_name: str = EMBEDDING_MODEL_NAME
) -> FAISS:
    """
    Initializes HuggingFace Sentence-Transformer embeddings, builds a fresh
    FAISS vector store, and saves 'index.faiss' and 'index.pkl' to disk.

    Args:
        documents: List of LangChain Document objects to embed.
        index_dir: Destination folder path for FAISS index binaries.
        model_name: Sentence-Transformer model identifier.

    Returns:
        The newly instantiated FAISS vector store.
    """
    if not documents:
        raise ValueError("Cannot build FAISS index: document list is empty.")

    print(f"\n[Embedder] Initializing standard project embeddings ('{model_name}')...")
    embeddings = HuggingFaceEmbeddings(model_name=model_name)

    os.makedirs(index_dir, exist_ok=True)

    print(f"[Vector Store] Embedding and indexing {len(documents)} regulatory documents...")
    vector_db = FAISS.from_documents(documents, embeddings)

    # Persist index binaries (index.faiss and index.pkl)
    vector_db.save_local(index_dir)
    print(f"✅ FAISS index binaries saved successfully to: '{index_dir}'")
    print(f"   • {os.path.join(index_dir, 'index.faiss')}")
    print(f"   • {os.path.join(index_dir, 'index.pkl')}")

    return vector_db


# =====================================================================
# 3. Main Pipeline Execution
# =====================================================================

def main():
    print("=" * 72)
    print("⚖️  FinSight RegTech: AMLD6 Legal Parser & Vector Store Ingestion")
    print("=" * 72)

    # Step 1: Read raw statutory text from amld6_raw.txt
    print(f"\n[1/3] Reading statutory text from: '{RAW_TEXT_PATH}'...")
    if not os.path.exists(RAW_TEXT_PATH):
        print(f"⚠️  File '{RAW_TEXT_PATH}' not found. Fetching live via SPARQL fetcher...")
        from src.services.data_ingestion.eur_lex_fetcher import fetch_amld6_regulation
        fetch_amld6_regulation(RAW_TEXT_PATH)

    with open(RAW_TEXT_PATH, "r", encoding="utf-8") as f:
        raw_content = f.read()

    print(f" • Loaded {len(raw_content):,} characters of statutory content.")

    # Step 2: Parse and chunk by Article
    print("\n[2/3] Parsing statutory text into individual Article Documents...")
    documents = parse_and_chunk_articles(raw_content)
    print(f" • Generated {len(documents)} LangChain Document chunks.")

    print("\n--- Document Chunks Sample Preview ---")
    for idx, doc in enumerate(documents[:5]):
        art_num = doc.metadata.get("article_number", idx)
        title = doc.metadata.get("title", f"Article {art_num}")
        preview = doc.page_content[:85].replace("\n", " ")
        print(f"   [{idx + 1}] Article {art_num:02d}: {title:<35} | Preview: \"{preview}...\"")

    if len(documents) > 5:
        print(f"   [... and {len(documents) - 5} more Articles ...]")

    # Step 3: Build and persist fresh FAISS Vector Store
    print("\n[3/3] Generating dense embeddings and persisting FAISS vector store...")
    vector_db = build_faiss_vectorstore(
        documents=documents,
        index_dir=FAISS_INDEX_DIR,
        model_name=EMBEDDING_MODEL_NAME
    )

    print("\n" + "=" * 72)
    print(f"✅ Ingestion Complete: {len(documents)} AMLD6 Articles successfully indexed in FAISS.")
    print("=" * 72)


if __name__ == "__main__":
    main()

"""
FinSight RegTech - Legal Text Parser & Vector Store Ingestion Service
====================================================================
Splits regulatory text (AMLD6 / EU Directives) by statutory Articles,
generates LangChain Document representations with structured metadata,
computes dense vector embeddings (all-MiniLM-L6-v2), and upserts them
into the FAISS vector database.
"""

import os
import re
import sys
from typing import List, Dict, Any, Optional

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


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Dynamically calculate project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # src/services/data_ingestion
SERVICES_DIR = os.path.dirname(SCRIPT_DIR)               # src/services
SRC_DIR = os.path.dirname(SERVICES_DIR)                  # src
BACKEND_DIR = os.path.dirname(SRC_DIR)                   # backend

FAISS_INDEX_DIR = os.path.join(BACKEND_DIR, "data", "faiss_index")
DEFAULT_INPUT_FILE = os.path.join(BACKEND_DIR, "amld6_raw.txt")


# =====================================================================
# 1. Legal Text Parser & Chunking Engine
# =====================================================================

def chunk_by_article(
    text: str,
    source_name: str = "AMLD6",
    jurisdiction: str = "EU",
    doc_type: str = "directive"
) -> List[Dict[str, Any]]:
    """
    Parses and divides plain legal/statutory text into distinct chunks
    where each chunk corresponds to an individual legal 'Article'.

    Args:
        text: Full plain text of the regulation/directive.
        source_name: Primary regulatory citation/acronym (e.g., 'AMLD6').
        jurisdiction: Target regional jurisdiction (e.g., 'EU', 'UK', 'US').
        doc_type: Type of statutory instrument (e.g., 'directive', 'regulation').

    Returns:
        List of dictionaries with 'page_content' and structured 'metadata'.
    """
    # Regex pattern to identify standard EU/UK/US Article headers: "Article 1", "Article 2", etc.
    article_pattern = r'(?i)(?:^|\n)\s*Article\s+(\d+)\b'
    matches = list(re.finditer(article_pattern, text))

    chunks: List[Dict[str, Any]] = []

    if not matches:
        # Fallback if no explicit "Article X" headers exist: return text as single chunk
        cleaned = text.strip()
        if cleaned:
            chunks.append({
                "page_content": cleaned,
                "metadata": {
                    "source": source_name,
                    "article_number": 1,
                    "jurisdiction": jurisdiction,
                    "type": doc_type
                }
            })
        return chunks

    # 1. Optional Preamble / Recitals chunk (content preceding Article 1)
    if matches[0].start() > 150:
        preamble_text = text[:matches[0].start()].strip()
        if preamble_text and len(preamble_text) > 100:
            chunks.append({
                "page_content": preamble_text,
                "metadata": {
                    "source": source_name,
                    "article_number": 0,
                    "section_title": "Preamble & Recitals",
                    "jurisdiction": jurisdiction,
                    "type": doc_type
                }
            })

    # 2. Iterate through each Article match and slice the text block
    for idx, match in enumerate(matches):
        try:
            art_num = int(match.group(1))
        except (ValueError, TypeError):
            art_num = idx + 1

        start_pos = match.start()
        end_pos = matches[idx + 1].start() if (idx + 1 < len(matches)) else len(text)

        article_block = text[start_pos:end_pos].strip()

        # Extract title line if available right after Article header
        lines = [line.strip() for line in article_block.splitlines() if line.strip()]
        title_summary = lines[1] if len(lines) > 1 and len(lines[1]) < 120 else f"Article {art_num}"

        chunks.append({
            "page_content": article_block,
            "metadata": {
                "source": source_name,
                "article_number": art_num,
                "title": title_summary,
                "jurisdiction": jurisdiction,
                "type": doc_type
            }
        })

    return chunks


# =====================================================================
# 2. Vector Database Embedding & Upsert Engine
# =====================================================================

def upsert_to_vectorstore(
    chunks: List[Dict[str, Any]],
    index_dir: Optional[str] = None
) -> FAISS:
    """
    Converts chunked dictionaries to LangChain Document instances,
    computes HuggingFace Sentence-Transformer embeddings, and upserts
    them into the FAISS vector database.

    Args:
        chunks: List of chunk dictionaries containing 'page_content' and 'metadata'.
        index_dir: Target path for the FAISS index binaries (defaults to data/faiss_index).

    Returns:
        Updated LangChain FAISS vector store object.
    """
    if not index_dir:
        index_dir = FAISS_INDEX_DIR

    if not chunks:
        raise ValueError("No chunks provided for vector store upsert.")

    # 1. Convert to LangChain Document objects
    documents = [
        Document(
            page_content=chunk["page_content"],
            metadata=chunk.get("metadata", {})
        )
        for chunk in chunks
        if chunk.get("page_content", "").strip()
    ]

    print(f"\n[Embedder] Initializing Sentence-Transformer Embedding Model ('all-MiniLM-L6-v2')...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    os.makedirs(index_dir, exist_ok=True)
    index_file = os.path.join(index_dir, "index.faiss")

    # 2. Upsert or create FAISS vector index
    if os.path.exists(index_file):
        print(f"[Vector Store] Loading existing FAISS index from: '{index_dir}'...")
        vector_db = FAISS.load_local(
            index_dir,
            embeddings,
            allow_dangerous_deserialization=True
        )
        print(f"[Vector Store] Adding {len(documents)} new regulatory Article documents to index...")
        vector_db.add_documents(documents)
    else:
        print(f"[Vector Store] Building new FAISS vector database with {len(documents)} documents...")
        vector_db = FAISS.from_documents(documents, embeddings)

    # 3. Persist index binaries to disk
    vector_db.save_local(index_dir)
    print(f"✅ Successfully persisted FAISS vector index to: '{index_dir}'")

    return vector_db


# =====================================================================
# 3. Pipeline Execution
# =====================================================================

def ingest_amld6_pipeline(raw_file_path: str = DEFAULT_INPUT_FILE) -> Dict[str, Any]:
    """
    Orchestrates the ingestion pipeline:
    1. Reads statutory text from file (or triggers live SPARQL fetch if missing).
    2. Chunks statutory text by Article.
    3. Generates embeddings and upserts into FAISS vector database.
    """
    print("=" * 70)
    print("⚖️  FinSight RegTech: Legal Text Parser & FAISS Vector Store Ingestion")
    print("=" * 70)

    # Step 1: Read Statutory Text
    if os.path.exists(raw_file_path):
        print(f"\n[1/3] Loading statutory text from local file: '{raw_file_path}'...")
        with open(raw_file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
    else:
        print(f"\n[1/3] Local file '{raw_file_path}' not found. Triggering live SPARQL fetcher...")
        from src.services.data_ingestion.eur_lex_fetcher import query_eur_lex_sparql, download_regulation_text, clean_html_content
        meta = query_eur_lex_sparql("32018L1673")
        html_content = download_regulation_text(meta["direct_doc_url"])
        raw_text = clean_html_content(html_content)

    print(f" • Loaded {len(raw_text):,} characters of legal statutory content.")

    # Step 2: Chunk by Article
    print("\n[2/3] Parsing and chunking regulatory text by Article...")
    chunks = chunk_by_article(
        text=raw_text,
        source_name="AMLD6",
        jurisdiction="EU",
        doc_type="directive"
    )
    print(f" • Successfully created {len(chunks)} structured Article chunks.")

    for i, c in enumerate(chunks[:5]):
        art_num = c["metadata"].get("article_number")
        title = c["metadata"].get("title", c["metadata"].get("section_title", "N/A"))
        preview = c["page_content"][:80].replace("\n", " ")
        print(f"   [{i + 1}] Article {art_num}: {title} (Preview: \"{preview}...\")")

    if len(chunks) > 5:
        print(f"   [... and {len(chunks) - 5} more Articles ...]")

    # Step 3: Embed & Upsert to Vector Store
    print("\n[3/3] Generating dense embeddings and upserting to FAISS vector database...")
    vector_db = upsert_to_vectorstore(chunks, FAISS_INDEX_DIR)

    print("\n✅ End-to-End Legal Parsing & FAISS Vector Upsert Pipeline Complete!")
    print("=" * 70)

    return {
        "status": "success",
        "chunks_count": len(chunks),
        "index_dir": FAISS_INDEX_DIR,
        "sample_metadata": chunks[0]["metadata"] if chunks else {}
    }


if __name__ == "__main__":
    ingest_amld6_pipeline(DEFAULT_INPUT_FILE)

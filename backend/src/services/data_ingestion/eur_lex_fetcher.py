"""
FinSight RegTech - EUR-Lex Multi-Act Automated Regulatory Ingestion Service
===========================================================================
Queries the European Union Publications Office SPARQL endpoint (Cellar / CDM Ontology)
and EUR-Lex portal to retrieve statutory metadata and full statutory texts for all key
European financial, banking, and AI regulatory frameworks:
- AMLD6 (Directive (EU) 2018/1673 - Anti-Money Laundering Criminal Law)
- AMLD5 (Directive (EU) 2018/843 - Anti-Money Laundering 5th Directive)
- PSD2 (Directive (EU) 2015/2366 - Payment Services Directive 2)
- MiCA (Regulation (EU) 2023/1114 - Markets in Crypto-Assets)
- TFR (Regulation (EU) 2023/1113 - Transfer of Funds / Crypto Travel Rule)
- DORA (Regulation (EU) 2022/2554 - Digital Operational Resilience Act)
- EU_AI_ACT (Regulation (EU) 2024/1689 - European Artificial Intelligence Act)
- GDPR (Regulation (EU) 2016/679 - General Data Protection Regulation)
"""

import os
import re
import sys
import html
from html.parser import HTMLParser
from typing import Dict, Any, Optional
import requests

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Directory Resolution
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # src/services/data_ingestion
SERVICES_DIR = os.path.dirname(SCRIPT_DIR)               # src/services
SRC_DIR = os.path.dirname(SERVICES_DIR)                  # src
BACKEND_DIR = os.path.dirname(SRC_DIR)                   # backend
RAW_STATUTES_DIR = os.path.join(BACKEND_DIR, "data", "raw_statutes")


# =====================================================================
# Configuration & Regulatory Targets
# =====================================================================

REGULATIONS: Dict[str, str] = {
    "AMLD6": "32018L1673",
    "AMLD5": "32018L0843",
    "PSD2": "32015L2366",
    "MiCA": "32023R1114",
    "TFR": "32023R1113",      # Transfer of Funds (Crypto Travel Rule)
    "DORA": "32022R2554",     # Digital Operational Resilience Act
    "EU_AI_ACT": "32024R1689", # European Artificial Intelligence Act
    "GDPR": "32016R0679"      # General Data Protection Regulation
}

EUR_LEX_SPARQL_ENDPOINT = "http://publications.europa.eu/webapi/rdf/sparql"
EUR_LEX_PORTAL_URL_TEMPLATE = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 FinSight-RegTech/2.0",
    "Accept": "application/sparql-results+json, application/json, text/html, application/xhtml+xml, */*",
}


# =====================================================================
# HTML / XHTML Text Stripping & Normalization Utility
# =====================================================================

class HTMLTextExtractor(HTMLParser):
    """HTML / XHTML Parser that extracts legible statutory content, stripping markup and tags."""

    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []
        self._ignore = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style", "head", "meta", "noscript"):
            self._ignore = True

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style", "head", "meta", "noscript"):
            self._ignore = False

    def handle_data(self, d):
        if not self._ignore:
            self.fed.append(d)

    def get_data(self) -> str:
        raw_text = "".join(self.fed)
        # Normalize whitespace while preserving line and paragraph breaks
        lines = [line.strip() for line in raw_text.splitlines()]
        cleaned = "\n".join([line for line in lines if line])
        return html.unescape(cleaned)


def clean_html_content(raw_html: str) -> str:
    """Strips HTML/XML tags and returns clean plaintext formatted for LLM tokenization."""
    extractor = HTMLTextExtractor()
    extractor.feed(raw_html)
    return extractor.get_data()


# =====================================================================
# SPARQL Query Execution
# =====================================================================

def query_eur_lex_sparql(celex: str, endpoint: str = EUR_LEX_SPARQL_ENDPOINT) -> Dict[str, Any]:
    """
    Executes a semantic SPARQL query against the EU Publications Office endpoint
    to extract legal act metadata, official title, date, and document manifestation URIs.

    Args:
        celex: Official CELEX identifier (e.g. '32023R1114' for MiCA).
        endpoint: SPARQL service URL.

    Returns:
        Dictionary containing extracted metadata.
    """
    sparql_query = f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    PREFIX lang: <http://publications.europa.eu/resource/authority/language/>

    SELECT DISTINCT ?work ?celex ?title ?date ?expr ?manifestation ?type WHERE {{
      ?work cdm:resource_legal_id_celex ?celex .
      FILTER(STR(?celex) = '{celex}')
      OPTIONAL {{ ?work cdm:work_date_document ?date . }}
      
      OPTIONAL {{
        ?expr cdm:expression_belongs_to_work ?work ;
              cdm:expression_uses_language lang:ENG .
        OPTIONAL {{ ?expr cdm:expression_title ?title . }}
        OPTIONAL {{
          ?manifestation cdm:manifestation_manifests_expression ?expr ;
                         cdm:manifestation_type ?type .
        }}
      }}
    }}
    """

    params = {
        "query": sparql_query.strip(),
        "format": "application/sparql-results+json"
    }

    portal_url = EUR_LEX_PORTAL_URL_TEMPLATE.format(celex=celex)

    try:
        response = requests.get(
            endpoint,
            params=params,
            headers=DEFAULT_HEADERS,
            timeout=25
        )
        response.raise_for_status()
        data = response.json()

        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
            raise ValueError(f"No SPARQL records returned for CELEX: {celex}")

        work_uri = bindings[0].get("work", {}).get("value", "")
        celex_id = bindings[0].get("celex", {}).get("value", celex)
        title = bindings[0].get("title", {}).get("value", f"Regulation/Directive CELEX {celex}")
        doc_date = bindings[0].get("date", {}).get("value", "N/A")

        # Locate XHTML manifestation for raw statutory text download
        direct_doc_url = None
        for item in bindings:
            m_type = item.get("type", {}).get("value", "")
            m_uri = item.get("manifestation", {}).get("value", "")
            if m_type == "xhtml" and m_uri:
                direct_doc_url = f"{m_uri}/DOC_1"
                break

        if not direct_doc_url:
            direct_doc_url = portal_url

        return {
            "celex": celex_id,
            "title": title,
            "date": doc_date,
            "work_uri": work_uri,
            "direct_doc_url": direct_doc_url,
            "portal_url": portal_url,
            "source_endpoint": endpoint
        }

    except Exception as e:
        sys.stderr.write(f"[SPARQL Notice] CELEX {celex} SPARQL lookup fell back to portal endpoint ({e})\n")
        return {
            "celex": celex,
            "title": f"European Legal Act (CELEX: {celex})",
            "date": "N/A",
            "work_uri": "",
            "direct_doc_url": portal_url,
            "portal_url": portal_url,
            "source_endpoint": endpoint
        }


# =====================================================================
# Document Content Ingestion
# =====================================================================

def download_regulation_text(document_url: str) -> str:
    """
    Downloads raw HTML/XHTML/XML content from the given EUR-Lex document URI.

    Args:
        document_url: Direct download URL to the legal text manifestation.

    Returns:
        Raw document string content.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 FinSight/2.0",
        "Accept": "application/xhtml+xml, text/html, application/xml;q=0.9, */*;q=0.8"
    }

    response = requests.get(document_url, headers=headers, timeout=35)
    response.raise_for_status()
    return response.text


def fetch_regulation(name: str, celex_id: str, output_path: str) -> Dict[str, Any]:
    """
    Fetches, cleans, and saves a single regulation statutory text to the designated output path.
    """
    print(f"\n[{name}] Querying EUR-Lex metadata for CELEX: {celex_id}...")
    meta = query_eur_lex_sparql(celex=celex_id)

    print(f" • Title: {meta['title'][:80]}...")
    print(f" • Fetching text from: {meta['direct_doc_url']}...")

    try:
        raw_content = download_regulation_text(meta["direct_doc_url"])
    except Exception as download_err:
        if meta["direct_doc_url"] != meta["portal_url"]:
            print(f"   ⚠️ Direct manifestation failed ({download_err}). Retrying via portal URL...")
            raw_content = download_regulation_text(meta["portal_url"])
        else:
            raise download_err

    cleaned_text = clean_html_content(raw_content)

    # Write clean statutory file
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"=== FINSIGHT REGTECH: REGULATION INGESTION AUDIT ===\n")
        f.write(f"REGULATION_NAME: {name}\n")
        f.write(f"CELEX ID:        {meta['celex']}\n")
        f.write(f"OFFICIAL TITLE:  {meta['title']}\n")
        f.write(f"DATE OF ACT:     {meta['date']}\n")
        f.write(f"DIRECT DOC URL:  {meta['direct_doc_url']}\n")
        f.write(f"EUR-LEX PORTAL:  {meta['portal_url']}\n")
        f.write(f"{'=' * 60}\n\n")
        f.write(cleaned_text)

    print(f" • Saved {len(cleaned_text):,} characters to '{os.path.basename(output_path)}'.")
    return {
        "name": name,
        "celex": celex_id,
        "metadata": meta,
        "cleaned_size_chars": len(cleaned_text),
        "output_path": output_path
    }


# =====================================================================
# Multi-Regulation Execution Pipeline
# =====================================================================

def fetch_all_regulations(output_dir: str = RAW_STATUTES_DIR) -> Dict[str, Any]:
    """
    Iterates through the entire catalog of European Fintech and AI regulations,
    downloads and cleans each statutory text, and saves it to a unique file in 'backend/data/raw_statutes'
    (e.g., amld6_raw.txt, mica_raw.txt, dora_raw.txt, etc.).

    Gracefully catches errors per act so that individual failure does not interrupt
    the broader multi-act ingestion pipeline.
    """
    os.makedirs(output_dir, exist_ok=True)
    print("=" * 76)
    print("🚀 FinSight RegTech: Multi-Act EUR-Lex Regulatory Ingestion Service")
    print(f"Target Acts Catalog: {', '.join(REGULATIONS.keys())}")
    print(f"Output Directory:    {output_dir}")
    print("=" * 76)

    results: Dict[str, Any] = {"successful": [], "failed": []}

    for name, celex in REGULATIONS.items():
        filename = f"{name.lower()}_raw.txt"
        output_file = os.path.join(output_dir, filename)

        try:
            res = fetch_regulation(name=name, celex_id=celex, output_path=output_file)
            results["successful"].append(res)
            print(f"✅ [{name}] Ingestion successful -> {output_file}")
        except Exception as e:
            sys.stderr.write(f"❌ [{name}] Ingestion failed for CELEX {celex}: {e}\n")
            results["failed"].append({"name": name, "celex": celex, "error": str(e)})

    print("\n" + "=" * 76)
    print(f"📊 Summary: {len(results['successful'])}/{len(REGULATIONS)} regulations downloaded successfully.")
    if results["failed"]:
        print(f"⚠️ Failed targets: {[item['name'] for item in results['failed']]}")
    print("=" * 76)

    return results


# Backward compatibility alias for single AMLD6 execution
def fetch_amld6_regulation(output_file: str = "amld6_raw.txt") -> Dict[str, Any]:
    target_path = os.path.join(RAW_STATUTES_DIR, output_file) if not os.path.isabs(output_file) else output_file
    return fetch_regulation("AMLD6", REGULATIONS["AMLD6"], target_path)


if __name__ == "__main__":
    fetch_all_regulations(RAW_STATUTES_DIR)

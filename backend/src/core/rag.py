"""
FinSight RegTech - Unified Multi-Act Compliance RAG Engine
===========================================================
Executes high-precision regulatory compliance audits against all 8 European
statutory frameworks (AMLD6, AMLD5, PSD2, MiCA, TFR, DORA, EU AI Act, GDPR).

Features:
- Native Structured Output with Google Gemini Flash & LangChain.
- Full multi-turn conversational memory formatting.
- Dual Evaluation Modes: 'strict' (3-State Agentic Auditor) vs 'lenient' (Demo Mode).
- Real-time token streaming via Server-Sent Events (SSE).
- Cryptographic anchoring to immutable PostgreSQL SHA-256 ledger.
"""

import os
import re
import sys
import json
import threading
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from langchain_core.callbacks import BaseCallbackHandler
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from src.core.llm import get_gemini_llm

# Dynamically calculate project root to prevent broken relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # src/core
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # root workspace
FAISS_INDEX_DIR = os.path.join(PROJECT_ROOT, "data", "faiss_index")
DEFAULT_EMBEDDING_MODEL = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-2-preview")


class NuclearLogger(BaseCallbackHandler):
    """Intercepts both the text prompt and the JSON schema payload heading to the LLM."""

    def _safe_write(self, text: str):
        """Safely writes text to sys.stderr handling platform-specific encoding limits."""
        try:
            sys.stderr.write(text)
        except UnicodeEncodeError:
            safe_text = text.encode(sys.stderr.encoding or "utf-8", errors="backslashreplace").decode(sys.stderr.encoding or "utf-8")
            sys.stderr.write(safe_text)

    def on_chat_model_start(self, serialized, messages, **kwargs):
        try:
            try:
                if hasattr(sys.stderr, "reconfigure"):
                    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass

            self._safe_write("\n\n" + "🔥" * 20 + " 1. TEXT PROMPT & FAISS CONTEXT SENT " + "🔥" * 20 + "\n")
            for message_list in messages:
                if isinstance(message_list, (list, tuple)):
                    for msg in message_list:
                        content = getattr(msg, "content", str(msg))
                        self._safe_write(f"\n{content}\n")
                else:
                    content = getattr(message_list, "content", str(message_list))
                    self._safe_write(f"\n{content}\n")

            self._safe_write("\n" + "⚡" * 20 + " 2. COMPILED JSON SCHEMA CONTRACT " + "⚡" * 20 + "\n")
            try:
                self._safe_write(json.dumps(kwargs, default=str, indent=2) + "\n")
            except Exception:
                self._safe_write(str(kwargs) + "\n")

            self._safe_write("🔥" * 64 + "\n\n")
            try:
                sys.stderr.flush()
            except Exception:
                pass
        except Exception:
            pass


# =====================================================================
# 1. Define Pydantic Data Contracts
# =====================================================================

class ComplianceCitation(BaseModel):
    document: str = Field(description="The filename of the regulation.")
    page: str = Field(description="The exact page or Article number of the source.")
    quoted_text: str = Field(
        description="A substantial, verbatim paragraph extracted directly from the document snippet. You MUST provide the complete surrounding sentence or paragraph so the quote stands alone and provides full legal context. Do not use short, ambiguous fragments."
    )


class ComplianceJudgment(BaseModel):
    risk_category: str = Field(
        description=(
            "Must be strictly 'Minimal Risk' if the architecture satisfies the statutory technical requirements or is 'Compliant with Controls'. "
            "Use 'High-Risk' or 'Prohibited' ONLY if there is an explicit legal violation. "
            "Use 'Pending Clarification' if critical mandatory information is missing to make a determination."
        )
    )
    is_compliant: bool = Field(
        description=(
            "Set strictly to True if there are NO active legal violations or missing mandatory technical controls. "
            "Ongoing operational recommendations (like periodic DPIA reviews or continuous monitoring) DO NOT make an architecture non-compliant; mark is_compliant=True."
        )
    )
    citations: List[ComplianceCitation] = Field(
        description="A list of the documents and pages used to make this judgment."
    )
    executive_summary_markdown: str = Field(
        description=(
            "A detailed, human-readable markdown report explaining the legal analysis. "
            "Use clean markdown hierarchy: section headings must be prefixed with '## ' or '### ' and placed on their own isolated lines with double newlines before and after. "
            "Bullet points must start with '* ' on new lines. Never put headings and paragraph body text on the same line. "
            "CRITICAL STRICT RULE: You MUST NOT include a 'Citations', 'References', or 'Sources' section inside this markdown. "
            "Do NOT manually list the document names or page numbers in this summary. You must leave citation tracking entirely to the separate structured 'citations' array."
        )
    )


# =====================================================================
# 2. Thread-Safe Singleton Cache for Embeddings & Vector Store
# =====================================================================

_embeddings_instance: Optional[GoogleGenerativeAIEmbeddings] = None
_vector_db_instance: Optional[FAISS] = None
_store_lock = threading.RLock()


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Returns a thread-safe singleton instance of GoogleGenerativeAIEmbeddings."""
    global _embeddings_instance
    if _embeddings_instance is None:
        with _store_lock:
            if _embeddings_instance is None:
                model_name = DEFAULT_EMBEDDING_MODEL
                if model_name in ["models/embedding-001", "embedding-001"]:
                    model_name = "models/gemini-embedding-001"
                api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
                _embeddings_instance = GoogleGenerativeAIEmbeddings(
                    model=model_name,
                    google_api_key=api_key
                )
    return _embeddings_instance


def get_vector_store() -> FAISS:
    """
    Returns a thread-safe singleton instance of the FAISS vector database.
    Validates index existence (both .faiss and .pkl) and provides actionable guidance if missing.
    """
    global _vector_db_instance
    if _vector_db_instance is None:
        with _store_lock:
            if _vector_db_instance is None:
                if not os.path.exists(FAISS_INDEX_DIR):
                    raise FileNotFoundError(
                        f"FAISS index directory not found at: '{FAISS_INDEX_DIR}'. "
                        "Please run 'python -m src.services.data_ingestion.legal_embedder' to generate vector embeddings."
                    )
                index_faiss_file = os.path.join(FAISS_INDEX_DIR, "index.faiss")
                index_pkl_file = os.path.join(FAISS_INDEX_DIR, "index.pkl")
                if not os.path.exists(index_faiss_file) or not os.path.exists(index_pkl_file):
                    raise FileNotFoundError(
                        f"FAISS index binaries missing in '{FAISS_INDEX_DIR}' (requires both 'index.faiss' and 'index.pkl'). "
                        "Please run 'python -m src.services.data_ingestion.legal_embedder' to rebuild."
                    )
                try:
                    embeddings = get_embeddings()
                    _vector_db_instance = FAISS.load_local(
                        FAISS_INDEX_DIR,
                        embeddings,
                        allow_dangerous_deserialization=True
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to load FAISS index from '{FAISS_INDEX_DIR}': {e}. "
                        "Rebuild the index by running 'python -m src.services.data_ingestion.legal_embedder'."
                    ) from e
    return _vector_db_instance


# =====================================================================
# 3. Regulatory Text Cleaning & Formatting Utilities
# =====================================================================

def clean_regulatory_text(text: str) -> str:
    """
    Cleans and repairs intra-word kerning spaces and spacing artifacts commonly
    introduced by PDF font subsets in EUR-Lex and EU official journal documents.
    """
    if not text:
        return ""

    two_letter = {
        r'\bb\s+y\b': 'by', r'\bt\s+o\b': 'to', r'\bf\s+or\b': 'for', r'\ba\s+n\b': 'an', r'\bi\s+n\b': 'in',
        r'\bi\s+s\b': 'is', r'\bi\s+t\b': 'it', r'\ba\s+t\b': 'at', r'\bo\s+n\b': 'on', r'\bo\s+r\b': 'or',
        r'\ba\s+s\b': 'as', r'\bb\s+e\b': 'be', r'\bh\s+e\b': 'he', r'\bm\s+e\b': 'me', r'\bm\s+y\b': 'my',
        r'\bn\s+o\b': 'no', r'\bs\s+o\b': 'so', r'\bu\s+p\b': 'up', r'\bu\s+s\b': 'us', r'\bw\s+e\b': 'we',
        r'\bd\s+o\b': 'do', r'\bg\s+o\b': 'go', r'\bi\s+f\b': 'if'
    }
    for pat, rep in two_letter.items():
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)

    word_fixes = [
        (r'\bAr\s+ticle\b', 'Article'), (r'\bar\s+ticle\b', 'article'),
        (r'\br\s+ight\b', 'right'), (r'\br\s+ights\b', 'rights'),
        (r'\bJour\s+nal\b', 'Journal'), (r'\bjour\s+nal\b', 'journal'),
        (r'\bf\s+ollo\s*wing\b', 'following'), (r'\bf\s+orgotten\b', 'forgotten'),
        (r'\bcr\s+ite\s*r\s*ia\b', 'criteria'), (r'\bpro\s+viding\b', 'providing'),
        (r'\bpro\s+vided\b', 'provided'), (r'\bpro\s+vision\b', 'provision'),
        (r'\bpro\s+visions\b', 'provisions'), (r'\bpur\s+poses\b', 'purposes'),
        (r'\bpur\s+pose\b', 'purpose'), (r'\bother\s+wise\b', 'otherwise'),
        (r'\bstate\s+ment\b', 'statement'), (r'\bstate\s+ments\b', 'statements'),
        (r'\bthe\s+y\b', 'they'), (r'\bwhic\s+h\b', 'which'), (r'\ban\s+y\b', 'any'),
        (r'\bhav\s+e\b', 'have'), (r'\bdat\s+a\b', 'data'), (r'\bdela\s+y\b', 'delay'),
        (r'\boblig\s+ation\b', 'obligation'), (r'\boblig\s+ations\b', 'obligations'),
        (r'\bnecessar\s+y\b', 'necessary'), (r'\bcatego\s*r\s*ies\b', 'categories'),
        (r'\bcategor\s+y\b', 'category'), (r'\bidentifi\s+cation\b', 'identification'),
        (r'\bbiometr\s+ic\b', 'biometric'), (r'\bbiometr\s+ics\b', 'biometrics'),
        (r'\bver\s+ification\b', 'verification'), (r'\bauthen\s+tication\b', 'authentication'),
        (r'\bsecur\s+ity\b', 'security'), (r'\bpers\s+onal\b', 'personal'),
        (r'\bsyste\s+m\b', 'system'), (r'\bsyste\s+ms\b', 'systems'),
        (r'\bpr\s+ovider\b', 'provider'), (r'\bpr\s+oviders\b', 'providers'),
        (r'\bclassifi\s+cation\b', 'classification'), (r'\btranspar\s+ency\b', 'transparency'),
        (r'\bprohibit\s+ed\b', 'prohibited'), (r'\bprohibit\s+ion\b', 'prohibition'),
        (r'\bfinanci\s+al\b', 'financial'), (r'\bpay\s+ment\b', 'payment'),
        (r'\bpay\s+ments\b', 'payments'), (r'\bser\s+vice\b', 'service'),
        (r'\bser\s+vices\b', 'services'), (r'\bcr\s+itical\b', 'critical')
    ]
    for pattern, replacement in word_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    suffix_pattern = r'\b([a-zA-Z]{3,})\s+(ed|ing|tion|tions|ment|ments|ty|ties|ly|able|ible|ness|ful|less|al|ive|ous|ic|ise|ize|ised|ized|ising|izing)\b'
    text = re.sub(suffix_pattern, r'\1\2', text, flags=re.IGNORECASE)

    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def _normalize_text(text: str) -> str:
    """Normalizes whitespace, casing, and common typographic substitutions."""
    if not text:
        return ""
    t = clean_regulatory_text(text)
    t = t.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    t = t.replace("—", "-").replace("–", "-")
    return " ".join(t.lower().split())


def _extract_digits(value: str) -> str:
    """Extracts numeric digits from page/article strings."""
    if not value or str(value).lower() in ("none", "unknown", "n/a"):
        return ""
    nums = re.findall(r"\d+", str(value))
    return nums[0] if nums else str(value).strip()


def _calculate_token_overlap(fragment: str, document_text: str) -> float:
    """Calculates word-level token overlap ratio between quotation fragment and FAISS chunk."""
    frag_tokens = set(fragment.split())
    if not frag_tokens:
        return 0.0
    doc_tokens = set(document_text.split())
    intersection = frag_tokens.intersection(doc_tokens)
    return len(intersection) / len(frag_tokens)


def format_markdown_report(text: str) -> str:
    """
    Normalizes markdown formatting to ensure proper header hierarchy, line breaks,
    and list structure for clean UI rendering without excessive blank lines.
    """
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\\n", "\n")
    # Ensure headings have single blank line separation
    t = re.sub(r'(?<!\n)\s*(#{1,6}\s+)', r'\n\1', t)
    
    lines = t.split("\n")
    formatted_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            match = re.match(
                r'^(#{1,6}\s+(?:(?:\d+\.\s*)?[A-Z][A-Za-z0-9\s/&,-]{2,50}?))\s+([A-Z][a-z]+(?:\s+[a-z]+){2,}.*)$',
                stripped
            )
            if match:
                heading_part = match.group(1).strip()
                body_part = match.group(2).strip()
                formatted_lines.append(f"{heading_part}\n{body_part}")
                continue
        formatted_lines.append(line)

    t = "\n".join(formatted_lines)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def _extract_chunk_text(content: Any) -> str:
    """
    Safely extracts plain string text from LangChain message chunk content.
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item and isinstance(item["text"], str):
                    parts.append(item["text"])
                elif "content" in item and isinstance(item["content"], str):
                    parts.append(item["content"])
                else:
                    parts.append(str(item))
            elif hasattr(item, "text"):
                parts.append(str(item.text))
            elif hasattr(item, "content"):
                parts.append(str(item.content))
            else:
                parts.append(str(item))
        return "".join(parts)
    elif hasattr(content, "text"):
        return str(content.text)
    elif content is None:
        return ""
    return str(content)


# =====================================================================
# 4. Prompt Engineering & 3-State Agentic Auditor Logic
# =====================================================================

def format_conversation_history(history: Optional[List[Dict[str, Any]]]) -> str:
    """
    Formats multi-turn conversation history into a structured dialogue block.
    """
    if not history or not isinstance(history, list) or len(history) == 0:
        return ""

    lines = ["PREVIOUS ARCHITECTURAL DIALOGUE & CONTEXT:"]
    for turn in history:
        if not isinstance(turn, dict):
            continue
        role_raw = turn.get("role", "user").lower()
        role_label = "User" if role_raw == "user" else "Auditor"
        content = turn.get("content", "").strip()
        if content:
            lines.append(f"{role_label}: {content}")

    return "\n".join(lines) + "\n\n" if len(lines) > 1 else ""


def build_system_prompt(jurisdiction_str: str, mode: str = "strict") -> str:
    """
    Constructs the system prompt dynamically based on the active evaluation mode ('strict' vs 'lenient').
    """
    base_role = (
        f"You are FinSight AI, a premier regulatory compliance officer and principal fintech auditor specialized in EU and cross-border financial and AI regulations "
        f"(AMLD6/5, PSD2, MiCA, TFR, DORA, EU AI Act, and GDPR).\n"
        f"Target Jurisdictions: {jurisdiction_str}.\n"
    )

    if mode == "lenient":
        mode_instructions = (
            "SCOPE LIMITATION (DEMO MODE):\n"
            "Evaluate ONLY the technical mechanisms explicitly stated in the query. Do NOT fail or penalize the architecture for omitted operational or administrative obligations "
            "(e.g., insurance, regulatory reporting schedules, continuous audit testing). Assume unstated operational requirements are satisfied.\n\n"
            "- COMPLIANCE DETERMINATION RULE: When all technical mechanisms satisfy applicable EU regulations (even if ongoing governance best practices or periodic reviews are recommended), you MUST classify the risk as 'Minimal Risk' and set 'is_compliant=True'.\n\n"
            "MANDATORY OUTPUT STRUCTURE:\n"
            "### 🚨 Risk Classification\n"
            "* **EU AI Act**: [Prohibited / High-Risk / Specific Transparency / Minimal Risk] - [1-sentence justification citing Article/Annex]\n"
            "* **FinTech & Data Protection (MiCA/PSD2/GDPR/DORA)**: [Non-Compliant / High-Risk / Compliant with Controls] - [1-sentence justification citing Article/Clause]\n\n"
            "### 🛡️ Critical Vulnerabilities / Verified Controls\n"
            "* **[Title]**: [Detailed analysis citing specific Articles/Clauses]\n\n"
            "### ✅ Remediation / Recommendations\n"
            "1. **[Step 1]**: [Actionable technical requirement or operational recommendation]\n"
            "2. **[Step 2]**: [Actionable technical requirement or operational recommendation]\n"
        )
    else:  # "strict" (Agentic Auditor Mode - Default)
        mode_instructions = (
            "STRICT AGENTIC AUDITOR MODE - 3-STATE DECISION MATRIX:\n"
            "You MUST evaluate the cumulative architectural specification across the entire dialogue against all 8 EU acts (AMLD, PSD2, MiCA, TFR, DORA, AI Act, GDPR).\n"
            "You MUST choose and output EXACTLY ONE of the following 3 paths based on the evidence:\n\n"
            "- COMPLIANCE DETERMINATION RULE: When all technical mechanisms satisfy applicable EU regulations (even if ongoing governance best practices or periodic reviews are recommended), you MUST classify the risk as 'Minimal Risk' and set 'is_compliant=True'.\n\n"
            "═══════════════════════════════════════════════════════════════════════════════\n"
            "PATH 1: EXPLICIT VIOLATION (Instant Fail)\n"
            "Condition: The architecture contains an active legal or technical breach (e.g., prohibited biometric emotion scoring, unauthorized EMT algorithmic yield, unauthenticated payment APIs, unauthorized personal data transfer).\n"
            "Decision: is_compliant=False, risk_category='Prohibited' or 'High-Risk'.\n"
            "Mandatory Output Format (Use ONLY these exact headings):\n"
            "### 🚨 Risk Classification\n"
            "* **EU AI Act**: [Classification] - [Justification citing Article/Annex]\n"
            "* **FinTech & Data Protection (MiCA/PSD2/GDPR/DORA)**: [Classification] - [Justification citing Article/Clause]\n\n"
            "### 🛡️ Critical Vulnerabilities\n"
            "* **[Vulnerability Title]**: [Detailed legal violation citing specific statutory Articles]\n\n"
            "### ✅ Mandatory Remediation Steps\n"
            "1. **[Remediation Step]**: [Actionable technical/governance requirement]\n\n"
            "═══════════════════════════════════════════════════════════════════════════════\n"
            "PATH 2: MISSING CRITICAL DATA (Pending Clarification)\n"
            "Condition: No active violation is stated, BUT the user describes an architecture that triggers specific statutory obligations without articulating required safeguards (e.g., Payment Initiation without stating SCA/dynamic linking under PSD2, Crypto-Asset issuance without stating licensing/reserve status under MiCA, ICT cloud deployment without stating EU redundancy/incident reporting under DORA). DO NOT automatically fail it.\n"
            "Decision: risk_category='Pending Clarification', is_compliant=False.\n"
            "Mandatory Output Format (Use ONLY these exact headings):\n"
            "### 🚨 Risk Classification\n"
            "* **Status**: ⏳ Pending Information - Compliance determination suspended pending architectural details.\n\n"
            "### ❓ Required Clarifications\n"
            "1. **[Topic/Article Inquiry]**: [Specific technical question regarding the missing operational safeguard or statutory requirement].\n"
            "2. **[Topic/Article Inquiry]**: [Specific technical question regarding the missing operational safeguard or statutory requirement].\n\n"
            "═══════════════════════════════════════════════════════════════════════════════\n"
            "PATH 3: FULLY COMPLIANT (Pass)\n"
            "Condition: All necessary statutory safeguards across the entire cumulative chat history are explicitly articulated and satisfied.\n"
            "Decision: is_compliant=True, risk_category='Minimal Risk'.\n"
            "Mandatory Output Format (Use ONLY these exact headings):\n"
            "### 🚨 Risk Classification\n"
            "* **Status**: ✅ Compliant Architecture - All applicable EU statutory requirements satisfied.\n\n"
            "### 🛡️ Verified Compliance Controls\n"
            "* **[Control Title]**: [Explanation of how the architecture satisfies specific EU statutory Articles].\n\n"
            "### 📋 Operational Recommendations\n"
            "1. **[Best Practice]**: [Ongoing governance or monitoring suggestion].\n"
            "═══════════════════════════════════════════════════════════════════════════════\n\n"
            "CRITICAL STRICT FORMATTING RULES:\n"
            "- Output ONLY the markdown sections corresponding to the single chosen path. Never mix headings from multiple paths.\n"
            "- DO NOT include conversational preambles (e.g., 'Based on the provided snippets...', 'Hello') or concluding sign-offs.\n"
            "- Headings must always be isolated on their own lines with double newlines before and after.\n"
        )

    return base_role + "\n" + mode_instructions


# =====================================================================
# 5. Core RAG Evaluation Functions
# =====================================================================

def query_compliance_engine(
    user_query: str,
    jurisdictions: Optional[List[str]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    mode: str = "strict"
) -> dict:
    """
    Takes a query and conversation history, retrieves context from FAISS with optional multi-jurisdictional filtering,
    and enforces Native Structured Output via Google Gemini to return a validated dictionary
    conforming to ComplianceJudgment.
    """
    if not user_query or not user_query.strip():
        raise ValueError("User query cannot be empty.")

    # 1. Retrieve the cached vector database singleton
    vector_db = get_vector_store()

    # 2. Configure FAISS search kwargs with metadata filtering
    search_kwargs: Dict[str, Any] = {"k": 3}

    if jurisdictions and len(jurisdictions) > 0:
        def jurisdiction_filter(metadata: dict) -> bool:
            doc_jurisdiction = str(metadata.get("jurisdiction", "")).strip().upper()
            doc_source = str(metadata.get("source", "")).strip().upper()

            for target in jurisdictions:
                t_clean = target.strip().upper()
                if doc_jurisdiction and (t_clean in doc_jurisdiction or doc_jurisdiction in t_clean):
                    return True
                tokens = [tok for tok in re.split(r'[^A-Z0-9]+', t_clean) if len(tok) >= 2]
                if any(token in doc_source for token in tokens):
                    return True
            return False

        search_kwargs["filter"] = jurisdiction_filter

    # Search FAISS with retriever
    retriever = vector_db.as_retriever(search_kwargs=search_kwargs)
    relevant_docs = retriever.invoke(user_query)

    # Handle edge case: empty vector database or zero retrieval
    if not relevant_docs:
        jurisdiction_label = ", ".join(jurisdictions) if jurisdictions else "All Active Jurisdictions"
        return {
            "risk_category": "Minimal Risk",
            "is_compliant": True,
            "citations": [],
            "executive_summary_markdown": (
                f"### 🚨 Risk Classification\n"
                f"* **Status**: ✅ Minimal Risk - No matching regulatory restrictions found for {jurisdiction_label}.\n\n"
                f"### 📋 Operational Recommendations\n"
                f"1. **Ingest Regulatory Corpus**: Verify that all official statutory articles for {jurisdiction_label} are indexed in FAISS.\n"
            )
        }

    # 3. Construct the context wall with cleaned text
    context_text = ""
    for doc in relevant_docs:
        source_file = doc.metadata.get("source", "Unknown")
        art_label = doc.metadata.get("article_label", f"Article {doc.metadata.get('article_number', 'Unknown')}")
        title = doc.metadata.get("title", "")
        doc_jur = doc.metadata.get("jurisdiction", "EU")
        cleaned_page_content = clean_regulatory_text(doc.page_content)
        context_text += f"\n--- [{doc_jur}] {source_file} ({art_label} - {title}) ---\n{cleaned_page_content}\n"

    # 4. Build prompt with conversational history & mode
    jurisdiction_str = ", ".join(jurisdictions) if jurisdictions else "EU Financial & AI Regulations"
    system_prompt = build_system_prompt(jurisdiction_str=jurisdiction_str, mode=mode)
    formatted_history = format_conversation_history(history)

    human_content = (
        f"TARGET JURISDICTIONS: {jurisdiction_str}\n\n"
        f"LEGAL CONTEXT SNIPPETS:\n{context_text}\n\n"
        f"{formatted_history}"
        f"CURRENT USER ARCHITECTURAL QUERY:\n{user_query}\n\n"
        f"Perform the compliance analysis:"
    )

    messages = [
        ("system", system_prompt),
        ("human", human_content)
    ]

    # 5. Initialize LLM and force Native Structured Output at the API level
    llm = get_gemini_llm()
    structured_llm = llm.with_structured_output(ComplianceJudgment)

    nuclear_tracker = NuclearLogger()

    try:
        parsed_obj = structured_llm.invoke(
            messages,
            config={"callbacks": [nuclear_tracker]}
        )
    except Exception as e:
        sys.stderr.write(f"[LLM Error] Structured output invocation failed: {e}\n")
        raise RuntimeError(f"Compliance engine evaluation failed: {e}") from e

    if isinstance(parsed_obj, ComplianceJudgment):
        result_dict = parsed_obj.model_dump()
    elif isinstance(parsed_obj, dict):
        result_dict = parsed_obj
    else:
        result_dict = dict(parsed_obj)

    # 6. Programmatic Deduplication & Context Hydration
    unique_citations = []
    seen_quotes = set()
    MIN_HYDRATION_FRAGMENT_LEN = 20
    MIN_HYDRATION_WORDS = 4

    for citation in result_dict.get("citations", []):
        if isinstance(citation, dict):
            cit_dict = citation
        elif hasattr(citation, "model_dump"):
            cit_dict = citation.model_dump()
        else:
            cit_dict = dict(citation)

        original_fragment = cit_dict.get("quoted_text", "").strip()
        normalized_fragment = _normalize_text(original_fragment)

        if normalized_fragment and normalized_fragment not in seen_quotes:
            seen_quotes.add(normalized_fragment)

            cit_doc = str(cit_dict.get("document", "")).strip().lower()
            cit_page = _extract_digits(cit_dict.get("page", ""))

            best_chunk_text = None
            best_overlap_score = 0.0

            is_long_enough = (
                len(normalized_fragment) >= MIN_HYDRATION_FRAGMENT_LEN
                and len(normalized_fragment.split()) >= MIN_HYDRATION_WORDS
            )

            for doc in relevant_docs:
                doc_source = str(doc.metadata.get("source", "")).strip().lower()
                doc_page = _extract_digits(doc.metadata.get("page", str(doc.metadata.get("article_number", ""))))

                doc_match = (not cit_doc or not doc_source) or (doc_source == cit_doc or cit_doc in doc_source or doc_source in cit_doc)
                page_match = (doc_page == cit_page) if (doc_page and cit_page) else True

                if doc_match and page_match:
                    normalized_doc_content = _normalize_text(doc.page_content)
                    
                    if is_long_enough:
                        if normalized_fragment in normalized_doc_content or normalized_doc_content in normalized_fragment:
                            best_chunk_text = clean_regulatory_text(" ".join(doc.page_content.split()))
                            break

                        overlap_score = _calculate_token_overlap(normalized_fragment, normalized_doc_content)
                        if overlap_score >= 0.60 and overlap_score > best_overlap_score:
                            best_overlap_score = overlap_score
                            best_chunk_text = clean_regulatory_text(" ".join(doc.page_content.split()))

            if best_chunk_text:
                cit_dict["quoted_text"] = best_chunk_text
            else:
                cit_dict["quoted_text"] = clean_regulatory_text(cit_dict.get("quoted_text", ""))

            unique_citations.append(cit_dict)

    result_dict["citations"] = unique_citations
    result_dict["executive_summary_markdown"] = format_markdown_report(result_dict.get("executive_summary_markdown", ""))
    return result_dict


async def astream_compliance_engine(
    user_query: str,
    jurisdictions: Optional[List[str]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    mode: str = "strict"
):
    """
    High-speed asynchronous streaming generator with multi-turn conversational memory:
    1. Retrieves top 3 context chunks from FAISS with optional multi-jurisdiction filtering (search_kwargs={'k': 3}).
    2. Formats multi-turn conversation history into dialogue context.
    3. Enforces dual evaluation mode ('strict' vs 'lenient') and the 3-state agentic decision matrix.
    4. Yields real-time token chunks via Gemini Flash LLM async streaming (.astream).
    5. Yields citation metadata and final payload.
    """
    if not user_query or not user_query.strip():
        raise ValueError("User query cannot be empty.")

    # 1. Retrieve the cached vector database singleton
    vector_db = get_vector_store()
    search_kwargs: Dict[str, Any] = {"k": 3}

    if jurisdictions and len(jurisdictions) > 0:
        def jurisdiction_filter(metadata: dict) -> bool:
            doc_jurisdiction = str(metadata.get("jurisdiction", "")).strip().upper()
            doc_source = str(metadata.get("source", "")).strip().upper()

            for target in jurisdictions:
                t_clean = target.strip().upper()
                if doc_jurisdiction and (t_clean in doc_jurisdiction or doc_jurisdiction in t_clean):
                    return True
                tokens = [tok for tok in re.split(r'[^A-Z0-9]+', t_clean) if len(tok) >= 2]
                if any(token in doc_source for token in tokens):
                    return True
            return False

        search_kwargs["filter"] = jurisdiction_filter

    retriever = vector_db.as_retriever(search_kwargs=search_kwargs)
    relevant_docs = retriever.invoke(user_query)

    # 2. Extract grounded citations directly from top 3 FAISS documents
    citations = []
    seen_sources = set()
    for doc in relevant_docs:
        source_file = doc.metadata.get("source", "Regulation Document")
        art_label = doc.metadata.get("article_label", f"Article {doc.metadata.get('article_number', 1)}")
        dedup_key = f"{source_file}_{art_label}"
        if dedup_key not in seen_sources:
            seen_sources.add(dedup_key)
            cleaned_snippet = clean_regulatory_text(doc.page_content)
            citations.append({
                "document": source_file,
                "page": str(art_label),
                "quoted_text": cleaned_snippet
            })

    yield {
        "type": "start",
        "jurisdictions": jurisdictions or ["EU (AI Act, GDPR, PSD2, MiCA, DORA)"],
        "citations": citations
    }

    if not relevant_docs:
        jurisdiction_label = ", ".join(jurisdictions) if jurisdictions else "All Active Jurisdictions"
        fallback_msg = (
            f"### 🚨 Risk Classification\n"
            f"* **Status**: ✅ Compliant Architecture - No matching regulatory prohibitions found for {jurisdiction_label}.\n\n"
            f"### 📋 Operational Recommendations\n"
            f"1. **Ingest Regulatory Corpus**: Ensure official legal articles for {jurisdiction_label} are ingested in FAISS.\n"
        )
        yield {"type": "token", "content": fallback_msg}
        return

    # 3. Construct the context wall with cleaned text
    context_text = ""
    for doc in relevant_docs:
        source_file = doc.metadata.get("source", "Unknown")
        art_label = doc.metadata.get("article_label", f"Article {doc.metadata.get('article_number', 'Unknown')}")
        title = doc.metadata.get("title", "")
        doc_jur = doc.metadata.get("jurisdiction", "EU")
        cleaned_page_content = clean_regulatory_text(doc.page_content)
        context_text += f"\n--- [{doc_jur}] {source_file} ({art_label} - {title}) ---\n{cleaned_page_content}\n"

    # 4. Strict System Prompt with 3-State Agentic Routing & History
    jurisdiction_str = ", ".join(jurisdictions) if jurisdictions else "EU Financial & AI Regulations"
    system_prompt = build_system_prompt(jurisdiction_str=jurisdiction_str, mode=mode)
    formatted_history = format_conversation_history(history)

    human_content = (
        f"TARGET JURISDICTIONS: {jurisdiction_str}\n\n"
        f"LEGAL CONTEXT SNIPPETS:\n{context_text}\n\n"
        f"{formatted_history}"
        f"CURRENT USER ARCHITECTURAL SPECIFICATION:\n{user_query}\n\n"
        f"Perform the compliance analysis:"
    )

    messages = [
        ("system", system_prompt),
        ("human", human_content)
    ]

    llm = get_gemini_llm()
    nuclear_tracker = NuclearLogger()

    async for chunk in llm.astream(messages, config={"callbacks": [nuclear_tracker]}):
        raw_content = getattr(chunk, "content", "")
        token_text = _extract_chunk_text(raw_content)
        if token_text:
            yield {"type": "token", "content": token_text}
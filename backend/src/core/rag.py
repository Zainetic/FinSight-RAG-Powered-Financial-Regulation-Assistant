import os
import re
import sys
import json
import threading
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from langchain_core.callbacks import BaseCallbackHandler
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from src.core.llm import get_gemini_llm

# Dynamically calculate project root to prevent broken relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # src/core
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # root workspace
FAISS_INDEX_DIR = os.path.join(PROJECT_ROOT, "data", "faiss_index")


class NuclearLogger(BaseCallbackHandler):
    """Intercepts both the text prompt and the JSON schema payload heading to the LLM."""

    def _safe_write(self, text: str):
        """Safely writes text to sys.stderr handling platform-specific encoding limits."""
        try:
            sys.stderr.write(text)
        except UnicodeEncodeError:
            # Fallback for consoles with restricted encodings (e.g. cp1252 on Windows)
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


# --- 1. Define the Pydantic Data Contract ---
class ComplianceCitation(BaseModel):
    document: str = Field(description="The filename of the regulation.")
    page: str = Field(description="The exact page number of the source.")
    quoted_text: str = Field(
        description="A substantial, verbatim paragraph extracted directly from the document snippet. You MUST provide the complete surrounding sentence or paragraph so the quote stands alone and provides full legal context. Do not use short, ambiguous fragments."
    )


class ComplianceJudgment(BaseModel):
    risk_category: str = Field(
        description="Must be strictly classified as: Prohibited, High-Risk, Specific Transparency, or Minimal Risk"
    )
    is_compliant: bool = Field(
        description="True if the action is allowed under the law, False if it is prohibited or high-risk."
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


# --- Thread-Safe Singleton Cache for Embeddings & Vector Store ---
_embeddings_instance: Optional[HuggingFaceEmbeddings] = None
_vector_db_instance: Optional[FAISS] = None
_store_lock = threading.RLock()


def get_embeddings() -> HuggingFaceEmbeddings:
    """Returns a singleton instance of the HuggingFace embedding model."""
    global _embeddings_instance
    if _embeddings_instance is None:
        with _store_lock:
            if _embeddings_instance is None:
                _embeddings_instance = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
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


def clean_regulatory_text(text: str) -> str:

    """
    Cleans and repairs intra-word kerning spaces and spacing artifacts commonly
    introduced by PDF font subsets in EUR-Lex and EU official journal documents.
    """
    if not text:
        return ""

    # 1. Common two-letter words split by font kerning
    two_letter = {
        r'\bb\s+y\b': 'by', r'\bt\s+o\b': 'to', r'\bf\s+or\b': 'for', r'\ba\s+n\b': 'an', r'\bi\s+n\b': 'in',
        r'\bi\s+s\b': 'is', r'\bi\s+t\b': 'it', r'\ba\s+t\b': 'at', r'\bo\s+n\b': 'on', r'\bo\s+r\b': 'or',
        r'\ba\s+s\b': 'as', r'\bb\s+e\b': 'be', r'\bh\s+e\b': 'he', r'\bm\s+e\b': 'me', r'\bm\s+y\b': 'my',
        r'\bn\s+o\b': 'no', r'\bs\s+o\b': 'so', r'\bu\s+p\b': 'up', r'\bu\s+s\b': 'us', r'\bw\s+e\b': 'we',
        r'\bd\s+o\b': 'do', r'\bg\s+o\b': 'go', r'\bi\s+f\b': 'if'
    }
    for pat, rep in two_letter.items():
        text = re.sub(pat, rep, text, flags=re.IGNORECASE)

    # 2. Known EUR-Lex regulatory dictionary replacements
    word_fixes = [
        (r'\bAr\s+ticle\b', 'Article'),
        (r'\bar\s+ticle\b', 'article'),
        (r'\br\s+ight\b', 'right'),
        (r'\br\s+ights\b', 'rights'),
        (r'\bJour\s+nal\b', 'Journal'),
        (r'\bjour\s+nal\b', 'journal'),
        (r'\bf\s+ollo\s*wing\b', 'following'),
        (r'\bf\s+orgotten\b', 'forgotten'),
        (r'\bcr\s+ite\s*r\s*ia\b', 'criteria'),
        (r'\bpro\s+viding\b', 'providing'),
        (r'\bpro\s+vided\b', 'provided'),
        (r'\bpro\s+vision\b', 'provision'),
        (r'\bpro\s+visions\b', 'provisions'),
        (r'\bpur\s+poses\b', 'purposes'),
        (r'\bpur\s+pose\b', 'purpose'),
        (r'\bother\s+wise\b', 'otherwise'),
        (r'\bstate\s+ment\b', 'statement'),
        (r'\bstate\s+ments\b', 'statements'),
        (r'\bthe\s+y\b', 'they'),
        (r'\bwhic\s+h\b', 'which'),
        (r'\ban\s+y\b', 'any'),
        (r'\bhav\s+e\b', 'have'),
        (r'\bdat\s+a\b', 'data'),
        (r'\bdela\s+y\b', 'delay'),
        (r'\bincomplet\s+e\b', 'incomplete'),
        (r'\bcompl\s+eted\b', 'completed'),
        (r'\bcompl\s+ete\b', 'complete'),
        (r'\bconcer\s+ning\b', 'concerning'),
        (r'\bconcer\s+ned\b', 'concerned'),
        (r'\bconcer\s+n\b', 'concern'),
        (r'\bconcer\s+ns\b', 'concerns'),
        (r'\boblig\s+ation\b', 'obligation'),
        (r'\boblig\s+ations\b', 'obligations'),
        (r'\bnecessar\s+y\b', 'necessary'),
        (r'\bsupplementar\s+y\b', 'supplementary'),
        (r'\bcollect\s+ed\b', 'collected'),
        (r'\bconfir\s+mation\b', 'confirmation'),
        (r'\bconfi\s+r\s*m\b', 'confirm'),
        (r'\bcatego\s*r\s*ies\b', 'categories'),
        (r'\bcategor\s+y\b', 'category'),
        (r'\bpar\s+ticular\b', 'particular'),
        (r'\bcountr\s+ies\b', 'countries'),
        (r'\binternati\s+onal\b', 'international'),
        (r'\borg\s+anisations\b', 'organisations'),
        (r'\borg\s+anization\b', 'organization'),
        (r'\borg\s+anizations\b', 'organizations'),
        (r'\benvisag\s+ed\b', 'envisaged'),
        (r'\bstor\s+ed\b', 'stored'),
        (r'\bdet\s+er\s*mine\b', 'determine'),
        (r'\bdet\s+er\s*mined\b', 'determined'),
        (r'\bexiste\s+nce\b', 'existence'),
        (r'\bexisten\s+ce\b', 'existence'),
        (r'\brectifi\s+cation\b', 'rectification'),
        (r'\brestr\s+iction\b', 'restriction'),
        (r'\brestr\s+ictions\b', 'restrictions'),
        (r'\bsuper\s+visor\s*y\b', 'supervisory'),
        (r'\bauthor\s+ity\b', 'authority'),
        (r'\bauthor\s+ities\b', 'authorities'),
        (r'\bav\s+ailable\b', 'available'),
        (r'\bautoma\s+ted\b', 'automated'),
        (r'\bprof\s+iling\b', 'profiling'),
        (r'\brefer\s+red\b', 'referred'),
        (r'\brefere\s+nce\b', 'reference'),
        (r'\bidentifi\s+cation\b', 'identification'),
        (r'\bidentifi\s+ed\b', 'identified'),
        (r'\bbiometr\s+ic\b', 'biometric'),
        (r'\bbiometr\s+ics\b', 'biometrics'),
        (r'\bver\s+ificati\s*on\b', 'verification'),
        (r'\bver\s+ification\b', 'verification'),
        (r'\bauthen\s+tication\b', 'authentication'),
        (r'\bsecur\s+ity\b', 'security'),
        (r'\bpers\s+on\b', 'person'),
        (r'\bpers\s+ons\b', 'persons'),
        (r'\bper\s+sonal\b', 'personal'),
        (r'\bsyste\s+m\b', 'system'),
        (r'\bsyste\s+ms\b', 'systems'),
        (r'\bpr\s+ovider\b', 'provider'),
        (r'\bpr\s+oviders\b', 'providers'),
        (r'\bimpl\s+ementation\b', 'implementation'),
        (r'\bimp\s+lementation\b', 'implementation'),
        (r'\bimp\s+le\s*ment\s*ed\b', 'implemented'),
        (r'\bcompre\s+hensive\b', 'comprehensive'),
        (r'\bguid\s+ance\b', 'guidance'),
        (r'\bguid\s+elines\b', 'guidelines'),
        (r'\bconstitut\s+e\b', 'constitute'),
        (r'\bconstitut\s+es\b', 'constitutes'),
        (r'\bappropr\s+iat\s*e\b', 'appropriate'),
        (r'\bper\s+mitte\s*d\b', 'permitted'),
        (r'\brequir\s+ement\b', 'requirement'),
        (r'\brequir\s+ements\b', 'requirements'),
        (r'\bhar\s+monis\s*ed\b', 'harmonised'),
        (r'\bhar\s+moniz\s*ed\b', 'harmonized'),
        (r'\bhar\s+monisation\b', 'harmonisation'),
        (r'\bhar\s+monization\b', 'harmonization'),
        (r'\bcompet\s+ent\b', 'competent'),
        (r'\bfundament\s+al\b', 'fundamental'),
        (r'\bclassifi\s+cation\b', 'classification'),
        (r'\bclassifi\s+ed\b', 'classified'),
        (r'\bcategor\s*is\s*ation\b', 'categorisation'),
        (r'\bcategor\s*iz\s*ation\b', 'categorization'),
        (r'\btranspar\s+ency\b', 'transparency'),
        (r'\btranspar\s+ent\b', 'transparent'),
        (r'\bprohibit\s+ed\b', 'prohibited'),
        (r'\bprohibit\s+ion\b', 'prohibition'),
        (r'\bprohibit\s+ions\b', 'prohibitions'),
        (r'\bdeploy\s+ment\b', 'deployment'),
        (r'\boper\s+ation\b', 'operation'),
        (r'\boper\s+ations\b', 'operations'),
        (r'\boper\s+ator\b', 'operator'),
        (r'\boper\s+ators\b', 'operators'),
        (r'\bfinanci\s+al\b', 'financial'),
        (r'\bapplic\s+ation\b', 'application'),
        (r'\bapplic\s+ations\b', 'applications'),
        (r'\binstruc\s+tion\b', 'instruction'),
        (r'\binstruc\s+tions\b', 'instructions'),
        (r'\bdocu\s+ment\b', 'document'),
        (r'\bdocu\s+ments\b', 'documents'),
        (r'\bpar\s+liament\b', 'parliament'),
        (r'\bcounc\s+il\b', 'council'),
        (r'\bcommiss\s+ion\b', 'commission'),
        (r'\bdirect\s+ive\b', 'directive'),
        (r'\bdirect\s+ives\b', 'directives'),
        (r'\bregulat\s+ion\b', 'regulation'),
        (r'\bregulat\s+ions\b', 'regulations'),
        (r'\btrans\s+action\b', 'transaction'),
        (r'\btrans\s+actions\b', 'transactions'),
        (r'\bpay\s+ment\b', 'payment'),
        (r'\bpay\s+ments\b', 'payments'),
        (r'\bser\s+vice\b', 'service'),
        (r'\bser\s+vices\b', 'services'),
        (r'\beff\s+ective\b', 'effective'),
        (r'\beffe\s+ct\b', 'effect'),
        (r'\beffe\s+cts\b', 'effects'),
        (r'\binter\s+mediar\s*y\b', 'intermediary'),
        (r'\binter\s+mediaries\b', 'intermediaries'),
        (r'\bf\s+acilitate\b', 'facilitate'),
        (r'\bex\s+ercise\b', 'exercise'),
        (r'\bex\s+cludes\b', 'excludes'),
        (r'\bex\s+clude\b', 'exclude'),
        (r'\brega\s+rding\b', 'regarding'),
        (r'\binte\s+r\s*mediar\s*y\b', 'intermediary'),
        (r'\bmachi\s+ner\s*y\b', 'machinery'),
        (r'\bincor\s+porating\b', 'incorporating'),
        (r'\bincor\s+porated\b', 'incorporated'),
        (r'\btheref\s+ore\b', 'therefore'),
        (r'\bdiff\s+erent\b', 'different'),
        (r'\bmarke\s+t\b', 'market'),
        (r'\br\s+ules\b', 'rules'),
        (r'\br\s+ule\b', 'rule'),
        (r'\bw\s+ork\b', 'work'),
        (r'\bw\s+ould\b', 'would'),
        (r'\ba\s+warded\b', 'awarded'),
        (r'\bautoma\s+t\s*ed\b', 'automated'),
        (r'\bUni\s+on\b', 'Union'),
        (r'\bU\s+nion\b', 'Union'),
        (r'\bEur\s+opean\b', 'European'),
        (r'\bEur\s+ope\b', 'Europe'),
        (r'\btec\s+hnology\b', 'technology'),
        (r'\btec\s+hnologies\b', 'technologies'),
        (r'\btec\s+hnical\b', 'technical'),
        (r'\bcar\s+r\s*ied\b', 'carried'),
        (r'\bperforma\s+nce\b', 'performance'),
        (r'\bMember\s+Stat\s*e\b', 'Member State'),
        (r'\bexer\s+cise\b', 'exercise'),
        (r'\boff\s+icial\b', 'official'),
        (r'\bcomp\s+ar\s*ing\b', 'comparing'),
        (r'\bcomp\s+ari\s*ng\b', 'comparing'),
        (r'\bst\s+ored\b', 'stored'),
        (r'\bin\s+vestig\s*ation\b', 'investigation'),
        (r'\bin\s+vestig\s*ations\b', 'investigations'),
        (r'\bcr\s+iminal\b', 'criminal'),
        (r'\boffe\s+nces\b', 'offences'),
        (r'\boffe\s+nce\b', 'offence'),
        (r'\bjeopardis\s+e\b', 'jeopardise'),
        (r'\bjeopardiz\s+e\b', 'jeopardize'),
        (r'\binte\s+gr\s*ity\b', 'integrity'),
        (r'\bmonito\s*r\b', 'monitor'),
        (r'\binstr\s+uments\b', 'instruments'),
        (r'\binstr\s+ument\b', 'instrument'),
        (r'\bdeplo\s+yer\b', 'deployer'),
        (r'\bdeplo\s+yers\b', 'deployers'),
        (r'\bst\s+emming\b', 'stemming'),
        (r'\bprot\s+ection\b', 'protection'),
        (r'\bin\s+v\s*olves\b', 'involves'),
        (r'\bin\s+v\s*olve\b', 'involve'),
        (r'\bclar\s+ify\b', 'clarify'),
        (r'\benjo\s+y\b', 'enjoy'),
        (r'\bmark\s+et\b', 'market'),
        (r'\bmark\s+eting\b', 'marketing'),
        (r'\bfur\s+ther\b', 'further'),
        (r'\baf\s+te\s*r\b', 'after'),
        (r'\bcr\s+itical\b', 'critical')
    ]
    for pattern, replacement in word_fixes:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 3. Clean common single-char suffix attachments (e.g. 'collect ed' -> 'collected')
    suffix_pattern = r'\b([a-zA-Z]{3,})\s+(ed|ing|tion|tions|ment|ments|ty|ties|ly|able|ible|ness|ful|less|al|ive|ous|ic|ise|ize|ised|ized|ising|izing)\b'
    text = re.sub(suffix_pattern, r'\1\2', text, flags=re.IGNORECASE)

    # 4. Clean single-letter prefix detached words
    text = re.sub(
        r'\b([a-zA-Z])\s+([a-zA-Z]{2,})\b',
        lambda m: m.group(1) + m.group(2) if m.group(1).lower() in ('r', 'f', 'p', 'd', 'b', 'c', 'g', 'h', 'm', 'n', 's', 't', 'w') and m.group(2).lower() in (
            'ight', 'ights', 'ollo', 'ollow', 'ollowing', 'ollows', 'orgot', 'orgotten',
            'rovider', 'roviders', 'rovision', 'rovisions', 'rotect', 'rotection', 'erson', 'ersonal', 'ersons',
            'ata', 'ave', 'hich', 'ould', 'here', 'hen', 'hose', 'hom', 'hat', 'hese', 'ith', 'ithout', 'ithin',
            'ystem', 'ystems', 'ound', 'ounds', 'eneral', 'econd', 'hird', 'ourth', 'ifth', 'ole', 'oles', 'uch',
            'ame', 'ames', 'art', 'arts', 'articular', 'ublic', 'ublicly', 'rivacy', 'rivate', 'ules', 'ule', 'ork',
            'arded', 'acilitate'
        ) else m.group(0),
        text
    )

    # 5. Clean multi-whitespace and line breaks
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def _normalize_text(text: str) -> str:
    """Normalizes whitespace, casing, and common typographic substitutions (curly quotes, dashes)."""
    if not text:
        return ""
    # Repair kerning spaces first
    t = clean_regulatory_text(text)
    # Normalize unicode quotes and dashes
    t = t.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    t = t.replace("—", "-").replace("–", "-")
    # Normalize all whitespace (including newlines) to single space
    return " ".join(t.lower().split())


def _extract_digits(value: str) -> str:
    """Extracts numeric page digits from strings like 'Page 12', '12', 'p. 12'."""
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
    and list structure for clean UI rendering.
    """
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\\n", "\n")

    # 1. Ensure blank lines before markdown headings (#, ##, ###)
    t = re.sub(r'(?<!\n)\s*(#{1,6}\s+)', r'\n\n\1', t)

    # 2. Ensure blank lines before bullet points (*, -, •)
    t = re.sub(r'(?<!\n)\s*([*•-]\s+)', r'\n\n\1', t)

    # 3. If a heading line has body text attached on the same line without a newline, split it
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
                formatted_lines.append(f"{heading_part}\n\n{body_part}")
                continue
        formatted_lines.append(line)

    t = "\n".join(formatted_lines)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def query_compliance_engine(user_query: str, jurisdictions: Optional[List[str]] = None) -> dict:
    """
    Takes a query, retrieves context from FAISS with optional multi-jurisdictional filtering,
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
        # Build a flexible filter matching document metadata 'jurisdiction' (or filename if unindexed)
        def jurisdiction_filter(metadata: dict) -> bool:
            doc_jurisdiction = str(metadata.get("jurisdiction", "")).strip().upper()
            doc_source = str(metadata.get("source", "")).strip().upper()

            for target in jurisdictions:
                t_clean = target.strip().upper()
                # Direct match or partial match on jurisdiction / source name (e.g. 'EU', 'UK', 'US')
                if doc_jurisdiction and (t_clean in doc_jurisdiction or doc_jurisdiction in t_clean):
                    return True
                # Fallback to source document filename keywords if jurisdiction metadata tag is missing
                tokens = [tok for tok in re.split(r'[^A-Z0-9]+', t_clean) if len(tok) >= 2]
                if any(token in doc_source for token in tokens):
                    return True
            return False

        search_kwargs["filter"] = jurisdiction_filter

    # Search FAISS with filter
    retriever = vector_db.as_retriever(search_kwargs=search_kwargs)
    relevant_docs = retriever.invoke(user_query)

    # Handle edge case: empty vector database or zero retrieval for selected jurisdiction
    if not relevant_docs:
        jurisdiction_label = ", ".join(jurisdictions) if jurisdictions else "All Active Jurisdictions"
        return {
            "risk_category": "Minimal Risk",
            "is_compliant": True,
            "citations": [],
            "executive_summary_markdown": (
                f"### Regulatory Verification ({jurisdiction_label})\n\n"
                f"No matching regulatory restrictions were retrieved from the vector store for the selected jurisdictions: **{jurisdiction_label}**. "
                "Ensure that the regulatory documents for these regions have been ingested into the FAISS index."
            )
        }

    # 3. Construct the context wall with cleaned text
    context_text = ""
    for doc in relevant_docs:
        source_file = doc.metadata.get("source", "Unknown")
        page_num = doc.metadata.get("page", "Unknown")
        doc_jur = doc.metadata.get("jurisdiction", "EU")
        cleaned_page_content = clean_regulatory_text(doc.page_content)
        context_text += f"\n--- [{doc_jur}] {source_file} (Page {page_num}) ---\n{cleaned_page_content}\n"

    # 4. Build the prompt including active target jurisdictions
    jurisdiction_str = ", ".join(jurisdictions) if jurisdictions else "EU, UK, US Regulatory Frameworks"
    system_prompt = (
        f"You are a strict regulatory compliance officer specialized in cross-border Fintech, EU AI Act, GDPR, and PSD2 regulations.\n"
        f"Target Jurisdictions: {jurisdiction_str}.\n\n"
        f"Analyze the user's architectural query strictly against the provided official legal context snippets.\n\n"
        f"STRICT MANDATORY FORMATTING INSTRUCTIONS:\n"
        f"- DO NOT include any introductory sentences, conversational preambles, or greetings (e.g. 'Based on the provided context...').\n"
        f"- DO NOT include any concluding paragraphs, summaries, or sign-offs at the end.\n"
        f"- You MUST output ONLY the following exact Markdown structure:\n\n"
        f"### 🚨 Risk Classification\n"
        f"* **EU AI Act**: [Prohibited / High-Risk / Specific Transparency / Minimal Risk] - [1-sentence justification citing specific Article/Annex].\n"
        f"* **GDPR & PSD2**: [Non-Compliant / High-Risk / Compliant with Controls] - [1-sentence justification citing specific Article/Clause].\n\n"
        f"### 🛡️ Critical Vulnerabilities\n"
        f"* **[Vulnerability Title 1]**: [Detailed description of the legal violation citing specific Articles/Clauses from the context snippets].\n"
        f"* **[Vulnerability Title 2]**: [Detailed description of the legal violation citing specific Articles/Clauses from the context snippets].\n\n"
        f"### ✅ Mandatory Remediation Steps\n"
        f"1. **[Remediation Step 1]**: [Actionable technical or governance requirement to achieve full compliance].\n"
        f"2. **[Remediation Step 2]**: [Actionable technical or governance requirement to achieve full compliance].\n"
        f"3. **[Remediation Step 3]**: [Actionable technical or governance requirement to achieve full compliance].\n"
    )

    messages = [
        ("system", system_prompt),
        ("human", f"TARGET JURISDICTIONS: {jurisdiction_str}\n\nLEGAL CONTEXT SNIPPETS:\n{context_text}\n\nUSER ARCHITECTURAL QUERY:\n{user_query}\n\nPerform the compliance analysis:")
    ]

    # 5. Initialize LLM and force Native Structured Output at the API level
    llm = get_gemini_llm()
    structured_llm = llm.with_structured_output(ComplianceJudgment)

    # 6. Invocation passing NuclearLogger to intercept schema and context to sys.stderr
    nuclear_tracker = NuclearLogger()

    try:
        parsed_obj = structured_llm.invoke(
            messages,
            config={"callbacks": [nuclear_tracker]}
        )
    except Exception as e:
        sys.stderr.write(f"[LLM Error] Structured output invocation failed: {e}\n")
        raise RuntimeError(f"Compliance engine evaluation failed: {e}") from e

    # Convert the validated Pydantic object into a dictionary
    if isinstance(parsed_obj, ComplianceJudgment):
        result_dict = parsed_obj.model_dump()
    elif isinstance(parsed_obj, dict):
        result_dict = parsed_obj
    else:
        result_dict = dict(parsed_obj)

    # 7. Programmatic Deduplication & Context Hydration
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
                doc_page = _extract_digits(doc.metadata.get("page", ""))

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


def _extract_chunk_text(content: Any) -> str:
    """
    Safely extracts plain string text from LangChain message chunk content,
    handling string tokens, list of multimodal parts/dicts, or structured objects.
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


async def astream_compliance_engine(user_query: str, jurisdictions: Optional[List[str]] = None):
    """
    High-speed asynchronous streaming generator for LangChain & Gemini Flash:
    1. Retrieves top 3 context chunks from FAISS with optional multi-jurisdiction filtering (search_kwargs={'k': 3}).
    2. Enforces strict Markdown structure forbidding preambles and postambles.
    3. Yields real-time token chunks via Gemini Flash LLM async streaming (.astream).
    4. Yields citation metadata and final payload.
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
        page_num = doc.metadata.get("page", 1)
        dedup_key = f"{source_file}_{page_num}"
        if dedup_key not in seen_sources:
            seen_sources.add(dedup_key)
            cleaned_snippet = clean_regulatory_text(doc.page_content)
            citations.append({
                "document": source_file,
                "page": str(page_num),
                "quoted_text": cleaned_snippet
            })

    yield {
        "type": "start",
        "jurisdictions": jurisdictions or ["EU (AI Act, GDPR, PSD2)"],
        "citations": citations
    }

    if not relevant_docs:
        jurisdiction_label = ", ".join(jurisdictions) if jurisdictions else "All Active Jurisdictions"
        fallback_msg = (
            f"### 🚨 Risk Classification\n"
            f"* **EU AI Act**: Minimal Risk - No matching regulatory prohibitions found for {jurisdiction_label}.\n"
            f"* **GDPR & PSD2**: Compliant with Controls - No restricted data flows detected.\n\n"
            f"### 🛡️ Critical Vulnerabilities\n"
            f"* **Unindexed Regulatory Framework**: Ensure official legal articles for {jurisdiction_label} are ingested in FAISS.\n\n"
            f"### ✅ Mandatory Remediation Steps\n"
            f"1. **Ingest Regulatory Corpus**: Embed official EU/UK/US compliance texts.\n"
        )
        yield {"type": "token", "content": fallback_msg}
        return

    # 3. Construct the context wall with cleaned text
    context_text = ""
    for doc in relevant_docs:
        source_file = doc.metadata.get("source", "Unknown")
        page_num = doc.metadata.get("page", "Unknown")
        doc_jur = doc.metadata.get("jurisdiction", "EU")
        cleaned_page_content = clean_regulatory_text(doc.page_content)
        context_text += f"\n--- [{doc_jur}] {source_file} (Page {page_num}) ---\n{cleaned_page_content}\n"

    # 4. Strict System Prompt
    jurisdiction_str = ", ".join(jurisdictions) if jurisdictions else "EU, UK, US Regulatory Frameworks"
    system_prompt = (
        f"You are a strict regulatory compliance officer specialized in cross-border Fintech, EU AI Act, GDPR, and PSD2 regulations.\n"
        f"Target Jurisdictions: {jurisdiction_str}.\n\n"
        f"Analyze the user's architectural query strictly against the provided official legal context snippets.\n\n"
        f"STRICT MANDATORY FORMATTING INSTRUCTIONS:\n"
        f"- DO NOT include any introductory sentences, conversational preambles, or greetings (e.g. 'Based on the provided context...').\n"
        f"- DO NOT include any concluding paragraphs, summaries, or sign-offs at the end.\n"
        f"- You MUST output ONLY the following exact Markdown structure:\n\n"
        f"### 🚨 Risk Classification\n"
        f"* **EU AI Act**: [Prohibited / High-Risk / Specific Transparency / Minimal Risk] - [1-sentence justification citing specific Article/Annex].\n"
        f"* **GDPR & PSD2**: [Non-Compliant / High-Risk / Compliant with Controls] - [1-sentence justification citing specific Article/Clause].\n\n"
        f"### 🛡️ Critical Vulnerabilities\n"
        f"* **[Vulnerability Title 1]**: [Detailed description of the legal violation citing specific Articles/Clauses from the context snippets].\n"
        f"* **[Vulnerability Title 2]**: [Detailed description of the legal violation citing specific Articles/Clauses from the context snippets].\n\n"
        f"### ✅ Mandatory Remediation Steps\n"
        f"1. **[Remediation Step 1]**: [Actionable technical or governance requirement to achieve full compliance].\n"
        f"2. **[Remediation Step 2]**: [Actionable technical or governance requirement to achieve full compliance].\n"
        f"3. **[Remediation Step 3]**: [Actionable technical or governance requirement to achieve full compliance].\n"
    )

    messages = [
        ("system", system_prompt),
        ("human", f"TARGET JURISDICTIONS: {jurisdiction_str}\n\nLEGAL CONTEXT SNIPPETS:\n{context_text}\n\nUSER ARCHITECTURAL QUERY:\n{user_query}\n\nPerform the compliance analysis:")
    ]

    llm = get_gemini_llm()
    nuclear_tracker = NuclearLogger()

    async for chunk in llm.astream(messages, config={"callbacks": [nuclear_tracker]}):
        raw_content = getattr(chunk, "content", "")
        token_text = _extract_chunk_text(raw_content)
        if token_text:
            yield {"type": "token", "content": token_text}
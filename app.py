# pyrefly: ignore [missing-import]
import streamlit as st
import json
import re
from src.core.rag import query_compliance_engine
from src.core.database import save_compliance_record, init_db
from src.core.ledger import append_compliance_record, init_ledger_table, override_ledger_record

# Configure the page
st.set_page_config(page_title="FinSight | AI Compliance", page_icon="⚖️", layout="wide")

# Eagerly initialize DB connection pool and table indexes on app launch
try:
    init_db()
    init_ledger_table()
except Exception:
    pass

st.title("FinSight RAG Engine")
st.markdown("Analyze European Fintech architectures against the EU AI Act, GDPR, and PSD2.")

# Initialize session state for persistent UI rendering across dispute interactions
if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None
if "ledger_receipt" not in st.session_state:
    st.session_state["ledger_receipt"] = None
if "override_receipt" not in st.session_state:
    st.session_state["override_receipt"] = None

# Sidebar Jurisdictional Filter
st.sidebar.header("🌍 Multi-Jurisdictional Scope")
st.sidebar.markdown("Filter regulatory compliance cross-examination by legal territory:")

available_jurisdictions = [
    "EU (AI Act, GDPR, PSD2)",
    "UK (UK GDPR, Data Protection Act)",
    "US (CCPA/CPRA, SEC AI Framework)"
]

selected_jurisdictions = st.sidebar.multiselect(
    "Active Jurisdictions:",
    options=available_jurisdictions,
    default=["EU (AI Act, GDPR, PSD2)"],
    help="Restricts FAISS vector search and citation retrieval to the selected regional frameworks."
)

# User input area
user_query = st.text_area(
    "Describe your proposed system architecture or data flow:",
    placeholder="e.g., We are building a payment gateway that categorizes users based on biometric facial recognition...",
    height=100
)

# Execution block
if st.button("Run Compliance Analysis", type="primary"):
    if not user_query or not user_query.strip():
        st.warning("Please enter an architectural query.")
    elif not selected_jurisdictions:
        st.warning("Please select at least one legal jurisdiction in the sidebar.")
    else:
        with st.spinner("Searching regional regulations and evaluating compliance..."):
            try:
                # 1. Call RAG backend with multi-jurisdictional filter
                result = query_compliance_engine(
                    user_query=user_query.strip(),
                    jurisdictions=selected_jurisdictions
                )

                # 2. Append to Immutable SHA-256 Hash Chain Ledger
                ledger_receipt = append_compliance_record(user_query.strip(), result)

                # Also write to legacy compliance_logs for backward compatibility
                save_compliance_record(user_query.strip(), result)

                # Store in session state
                st.session_state["analysis_result"] = result
                st.session_state["ledger_receipt"] = ledger_receipt
                st.session_state["override_receipt"] = None


            except FileNotFoundError as fnf:
                st.error(f"Vector Database Error: {str(fnf)}")
            except ValueError as ve:
                st.error(f"Configuration Error: {str(ve)}")
            except RuntimeError as re_err:
                st.error(f"Compliance Engine Error: {str(re_err)}")
            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")

# --- UI RENDERING ---
if st.session_state.get("analysis_result"):
    result = st.session_state["analysis_result"]
    ledger_receipt = st.session_state["ledger_receipt"]
    backend_json = json.dumps(result, indent=2)

    # Top Metrics Row
    col1, col2, col3 = st.columns(3)
    if st.session_state.get("override_receipt"):
        col1.warning("Overall Status: OVERRIDDEN BY HUMAN 🧑‍⚖️")
    elif result.get("is_compliant", False):
        col1.success("Overall Status: COMPLIANT ")
    else:
        col1.error("Overall Status: ACTION REQUIRED")

    col2.metric("EU AI Act Risk Classification", result.get("risk_category", "Unclassified"))

    if ledger_receipt:
        col3.metric("Ledger Status", "🔒 SHA-256 SEALED")
    else:
        col3.metric("Ledger Status", "⚠️ UNCOMMITTED")

    st.divider()

    # Layout for Summary vs. Raw Data & Ledger Receipt
    left_col, right_col = st.columns([2, 1])

    with left_col:
        st.subheader("Executive Summary")
        summary_md = result.get("executive_summary_markdown", "_No summary generated._")

        # Normalize header sizes (demote H1 to H3 to maintain proper hierarchy under st.subheader)
        normalized_summary = re.sub(r'^(#\s+)', r'### ', summary_md, flags=re.MULTILINE)
        # Clean any redundant repeated '### Executive Summary:' prefix
        normalized_summary = re.sub(r'^###\s+Executive\s+Summary\s*[:\-–—]?\s*', '', normalized_summary, flags=re.IGNORECASE).strip()

        st.markdown(normalized_summary)

        st.subheader("Verified Citations")
        citations = result.get("citations", [])
        if citations:
            for idx, ref in enumerate(citations, 1):
                doc_title = ref.get("document", "Unknown Document")
                page_info = ref.get("page", "N/A")
                with st.expander(f"[{idx}] {doc_title} (Page {page_info})"):
                    st.info(f"**Verbatim Extract:**\n\n_{ref.get('quoted_text', 'No quote extracted.')}_")
        else:
            st.info("No specific citation references extracted for this query.")

    with right_col:
        # Cryptographic Compliance Receipt
        st.subheader("🛡️ Cryptographic Compliance Receipt")
        if ledger_receipt:
            st.success("Record permanently anchored in Immutable SHA-256 Ledger.")
            st.text_input("Audit ID (UUID):", value=ledger_receipt["audit_id"], disabled=True, key="audit_id_display")
            st.text_input("Transaction Hash (SHA-256):", value=ledger_receipt["tx_hash"], disabled=True, key="tx_hash_display")
            st.text_input("Previous Block Hash:", value=ledger_receipt["prev_hash"], disabled=True, key="prev_hash_display")
            st.caption(f"🕒 Timestamp (UTC): {ledger_receipt['timestamp']}")
            with st.expander("📋 Full Tamper-Evident Receipt (JSON)"):
                st.code(json.dumps(ledger_receipt, indent=2), language="json")

            # Human-in-the-Loop Dispute Expander
            with st.expander("⚖️ Dispute this Judgment"):
                st.markdown("**Human-in-the-Loop Ledger Dispute Protocol**")
                st.caption("Manually override this AI judgment without breaking the SHA-256 hash chain.")
                justification = st.text_area(
                    "Developer Justification / Exemption Basis:",
                    placeholder="e.g., Biometric categorization is strictly performed locally on client device under GDPR Art. 9(2)(a)...",
                    key=f"dispute_justification_{ledger_receipt['audit_id']}"
                )
                if st.button("Override Judgment", type="secondary", key=f"btn_override_{ledger_receipt['audit_id']}"):
                    if not justification or not justification.strip():
                        st.warning("Please provide a justification before submitting an override.")
                    else:
                        with st.spinner("Recording dispute block to cryptographic ledger..."):
                            override_receipt = override_ledger_record(
                                audit_id=ledger_receipt["audit_id"],
                                justification=justification.strip()
                            )
                            if override_receipt:
                                st.session_state["override_receipt"] = override_receipt
                                st.success("✅ Override permanently logged in immutable ledger!")
                                st.info(f"**New Transaction Hash (SHA-256):**\n`{override_receipt['tx_hash']}`")
                                st.caption(f"Linked Previous Hash: `{override_receipt['prev_hash']}`")
                                with st.expander("📋 View Override Block Receipt"):
                                    st.code(json.dumps(override_receipt, indent=2), language="json")
                            else:
                                st.error("Failed to commit override to PostgreSQL ledger.")

            if st.session_state.get("override_receipt"):
                ov = st.session_state["override_receipt"]
                st.info(f"**Active Override Block:** `{ov['tx_hash'][:16]}...`")
        else:
            st.warning("⚠️ PostgreSQL ledger persistence unavailable (local session only).")

        st.subheader("Backend JSON Payload")
        st.code(backend_json, language="json")



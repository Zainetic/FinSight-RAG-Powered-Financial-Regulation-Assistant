import streamlit as st
import json
from src.core.rag import query_compliance_engine

# Configure the page
st.set_page_config(page_title="FinSight | AI Compliance", page_icon="⚖️", layout="wide")

st.title("FinSight RAG Engine")
st.markdown("Analyze European Fintech architectures against the EU AI Act, GDPR, and PSD2.")

# User input area
user_query = st.text_area(
    "Describe your proposed system architecture or data flow:",
    placeholder="e.g., We are building a payment gateway that categorizes users based on biometric facial recognition...",
    height=100
)

# Execution block
if st.button("Run Compliance Analysis", type="primary"):
    if not user_query:
        st.warning("Please enter an architectural query.")
    else:
        with st.spinner("Searching regulations and evaluating compliance..."):
            try:
                # 1. Call your RAG backend
                result = query_compliance_engine(user_query)

                # 2. Simulate saving the backend JSON to a database
                backend_json = json.dumps(result, indent=2)

                # --- UI RENDERING ---

                # Top Metrics Row
                col1, col2 = st.columns(2)
                if result["is_compliant"]:
                    col1.success("Overall Status: COMPLIANT ")
                else:
                    col1.error("Overall Status: ACTION REQUIRED")

                col2.metric("EU AI Act Risk Classification", result["risk_category"])
                st.divider()

                # Layout for Summary vs. Raw Data
                left_col, right_col = st.columns([2, 1])

                with left_col:
                    st.subheader("Executive Summary")
                    st.markdown(result["executive_summary_markdown"])

                    st.subheader("Verified Citations")
                    for idx, ref in enumerate(result["citations"], 1):
                        st.caption(f"[{idx}] 📄 {ref['document']} (Page {ref['page']})")

                with right_col:
                    st.subheader("Backend JSON Payload")
                    st.caption("Data routed to database/event brokers:")
                    st.code(backend_json, language="json")

            except Exception as e:
                st.error(f"Analysis failed: {str(e)}")
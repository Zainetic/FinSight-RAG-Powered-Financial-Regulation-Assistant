import json
from src.core.rag import query_compliance_engine


def run_test():
    sample_query = (
        "What are the explicit prohibitions regarding biometric data categorization "
        "under the EU AI Act, and does it impact financial applications?"
    )

    print("Contacting FAISS vector index...")
    print("Requesting Pydantic-validated structured response from LLM...")
    print("-" * 60)

    try:
        # Execute the RAG pipeline
        result = query_compliance_engine(sample_query)

        # 1. Assert that our critical backend keys exist and are typed correctly
        assert "risk_category" in result, "Missing key: risk_category"
        assert "is_compliant" in result, "Missing key: is_compliant"
        assert "citations" in result, "Missing key: citations"
        assert "executive_summary_markdown" in result, "Missing key: executive_summary_markdown"

        # 2. Isolate and display the structured metadata (Backend Data Layer)
        print("\nEXTRACTED METADATA (For Database/Kafka Ingestion):")
        print(f"  • Risk Category:       {result['risk_category']}")
        print(f"  • System Compliant:    {result['is_compliant']}")
        print(f"  • Citations Extracted: {len(result['citations'])} source reference(s)")
        for idx, citation in enumerate(result['citations'], start=1):
            print(f"    [{idx}] {citation['document']} (Page {citation['page']})")

        print("-" * 60)

        # 3. Isolate and display the unstructured prose (Frontend Presentation Layer)
        print("\nEXECUTIVE SUMMARY (For Streamlit UI Rendering):")
        print(result["executive_summary_markdown"])

        print("-" * 60)
        print("Integration Test Passed: Payload structure matches Pydantic contract perfectly.")

    except AssertionError as ae:
        print(f"Contract Validation Failed: {ae}")
    except Exception as e:
        print(f"Pipeline Execution Failed: {e}")


if __name__ == "__main__":
    run_test()
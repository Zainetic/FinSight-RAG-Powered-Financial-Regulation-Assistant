import sys
from src.core.rag import query_compliance_engine


def run_test():
    sample_query = (
        "What are the explicit prohibitions regarding biometric data categorization "
        "under the EU AI Act, and does it impact financial applications?"
    )

    print("Initializing test compliance query...")
    print(f"Question: '{sample_query}'\n")
    print("Contacting FAISS database and streaming context to Mistral (this may take a few seconds)...")
    print("-" * 60)

    try:
        # Run the RAG engine pipeline
        result = query_compliance_engine(sample_query)

        # Print the natural language analysis from Mistral
        print("\nCOMPLIANCE JUDGMENT:")
        print(result["answer"])
        print("-" * 60)

        # Print the extracted citations mapped by FAISS
        print("\nATTACHED EVIDENCE / CITATIONS:")
        for idx, citation in enumerate(result["citations"], 1):
            print(f" [{idx}] Document: {citation['source']} (Page {citation['page']})")

    except Exception as e:
        print(f"\nTest Failed with error: {str(e)}")
        print("\nTroubleshooting checkpoints:")
        print("1. Ensure your .env file has a valid HUGGINGFACEHUB_API_TOKEN.")
        print("2. Verify that 'data/faiss_index/' contains index.faiss and index.pkl.")
        print("3. Check that your internet connection can reach huggingface.co.")


if __name__ == "__main__":
    run_test()
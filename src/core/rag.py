from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from src.core.llm import get_mistral_llm

FAISS_INDEX_DIR = "data/faiss_index"

def query_compliance_engine(user_query: str) -> dict:
    """
    Takes a raw user compliance query, searches local FAISS vectors,
    structures a contextual prompt, and passes it to Mistral for analysis.
    """
    # 1. Re-initialize the local embedding model
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # 2. Load the pre-compiled FAISS vector database from disk
    vector_db = FAISS.load_local(
        FAISS_INDEX_DIR,
        embeddings,
        allow_dangerous_deserialization=True
    )

    # 3. Search for top 3 closest matching text chunks from the regulations
    retriever = vector_db.as_retriever(search_kwargs={"k": 3})
    relevant_docs = retriever.invoke(user_query)

    # 4. Construct the context wall and compile citation dictionaries
    context_text = ""
    citations = []

    for doc in relevant_docs:
        source_file = doc.metadata.get("source", "Unknown Regulation")
        page_num = doc.metadata.get("page", "Unknown Page")

        context_text += f"\n--- EXCERPT FROM {source_file} (Page {page_num}) ---\n{doc.page_content}\n"

        citations.append({
            "source": source_file,
            "page": page_num
        })

    # 5. Build a structured conversational prompt (System + Human)
    messages = [
        (
            "system",
            "You are a strict regulatory compliance officer specialized in European Fintech, GDPR, and AI regulations. "
            "Analyze the user's query strictly against the provided official legal context snippets. "
            "Provide an explicit judgment on whether the proposed architectural behavior is: "
            "COMPLIANT, NON-COMPLIANT / PROHIBITED, or HIGH-RISK. "
            "Do not assume or extrapolate rules outside the provided context snippets."
        ),
        (
            "human",
            f"LEGAL CONTEXT SNIPPETS:\n{context_text}\n\nUSER ARCHITECTURAL QUERY:\n{user_query}\n\nDETAILED COMPLIANCE ANALYSIS:"
        )
    ]

    # 6. Request the final evaluation from Mistral
    llm = get_mistral_llm()
    response = llm.invoke(messages)

    return {
        "answer": response.content.strip(),
        "citations": citations
    }
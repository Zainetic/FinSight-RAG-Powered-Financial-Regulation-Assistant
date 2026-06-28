from pydantic import BaseModel, Field
from typing import List
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from src.core.llm import get_mistral_llm

FAISS_INDEX_DIR = "data/faiss_index"


# --- 1. Define the Pydantic Data Contract ---
class ComplianceCitation(BaseModel):
    document: str = Field(description="The filename of the regulation.")
    page: str = Field(description="The exact page number of the source.")


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
        description="A detailed, human-readable markdown report explaining the legal analysis, using headings and bullet points."
    )


def query_compliance_engine(user_query: str) -> dict:
    """
    Takes a query, retrieves context, and forces Qwen to output a
    validated JSON object matching the ComplianceJudgment schema.
    """
    # 2. Re-initialize the local embedding model and FAISS
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vector_db = FAISS.load_local(
        FAISS_INDEX_DIR,
        embeddings,
        allow_dangerous_deserialization=True
    )

    # 3. Search FAISS
    retriever = vector_db.as_retriever(search_kwargs={"k": 3})
    relevant_docs = retriever.invoke(user_query)

    # 4. Construct the context wall
    context_text = ""
    for doc in relevant_docs:
        source_file = doc.metadata.get("source", "Unknown")
        page_num = doc.metadata.get("page", "Unknown")
        context_text += f"\n--- {source_file} (Page {page_num}) ---\n{doc.page_content}\n"

    # 5. Build the strict prompt
    messages = [
        (
            "system",
            "You are a strict regulatory compliance officer specialized in European Fintech and AI regulations. "
            "Analyze the user's query strictly against the provided official legal context snippets. "
            "You must output a structured JSON object matching the requested schema. "
            "Do not assume rules outside the provided context snippets."
        ),
        (
            "human",
            f"LEGAL CONTEXT SNIPPETS:\n{context_text}\n\nUSER ARCHITECTURAL QUERY:\n{user_query}\n\nPerform the compliance analysis:"
        )
    ]

    # 6. Initialize the LLM and bind the structured Pydantic schema
    llm = get_qwen_llm()
    structured_llm = llm.with_structured_output(ComplianceJudgment)

    # 7. Invoke the model. It automatically returns a validated Pydantic object!
    response_obj = structured_llm.invoke(messages)

    # 8. Convert the Pydantic object back into a standard dictionary
    # so FastAPI can easily return it as a JSON payload to Streamlit
    return response_obj.model_dump()
from pydantic import BaseModel, Field
from typing import List
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.output_parsers import PydanticOutputParser
from src.core.llm import get_qwen_llm

FAISS_INDEX_DIR = "data/faiss_index"


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
        description="A detailed, human-readable markdown report explaining the legal analysis, using headings and bullet points."
    )


def query_compliance_engine(user_query: str) -> dict:
    """
    Takes a query, retrieves context, and uses an output parser to force Qwen
    to return a string conforming to the ComplianceJudgment schema.
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

    # 5. Initialize the Pydantic Output Parser
    parser = PydanticOutputParser(pydantic_object=ComplianceJudgment)

    # 6. Build the prompt, injecting the schema's explicit format instructions
    messages = [
        (
            "system",
            "You are a strict regulatory compliance officer specialized in European Fintech and AI regulations. "
            "Analyze the user's query strictly against the provided official legal context snippets.\n\n"
            "CRITICAL: You must output your complete response as a single, valid JSON object that matches the structural schema defined below. "
            "Do not include any conversational text, explanations, or markdown code blocks (like ```json) outside of the raw JSON payload.\n\n"
            f"{parser.get_format_instructions()}"
        ),
        (
            "human",
            f"LEGAL CONTEXT SNIPPETS:\n{context_text}\n\nUSER ARCHITECTURAL QUERY:\n{user_query}\n\nPerform the compliance analysis:"
        )
    ]

    # 7. Invoke the LLM as a standard text completion engine
    llm = get_qwen_llm()
    raw_response = llm.invoke(messages)

    # 8. Extract the string content and parse it back into a validated dictionary
    try:
        parsed_obj = parser.parse(raw_response.content)
        result_dict = parsed_obj.model_dump()
    except Exception as parse_error:
        # Fallback handling in case the model outputs markdown wrapping code blocks
        clean_content = raw_response.content.strip().lstrip("```json").rstrip("```").strip()
        parsed_obj = parser.parse(clean_content)
        result_dict = parsed_obj.model_dump()

    # --- 9. Programmatic Deduplication ---
    unique_citations = []
    seen_quotes = set()

    for citation in result_dict.get("citations", []):
        # Normalize the string: remove leading/trailing spaces and make it lowercase
        quote_text = citation.get("quoted_text", "").strip().lower()

        # If we haven't seen this exact normalized string before, add it to our clean list
        if quote_text and quote_text not in seen_quotes:
            seen_quotes.add(quote_text)
            unique_citations.append(citation)

    # Overwrite the potentially looping citations with the clean list
    result_dict["citations"] = unique_citations

    # Return the final deduplicated dictionary
    return result_dict
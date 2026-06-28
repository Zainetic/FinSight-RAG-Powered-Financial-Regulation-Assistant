import os
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()


def get_mistral_llm():
    """Initializes the remote Mistral Instruct endpoint using the Conversational API."""
    api_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if not api_token:
        raise ValueError("Critical Error: HUGGINGFACEHUB_API_TOKEN is missing from the environment configuration.")

    # 1. Initialize the base endpoint
    base_llm = HuggingFaceEndpoint(
        repo_id="mistralai/Mistral-7B-Instruct-v0.3",
        max_new_tokens=512,
        temperature=0.1,
        repetition_penalty=1.1,
    )

    # 2. Wrap it to force the "conversational" API route for strict providers
    return ChatHuggingFace(llm=base_llm)
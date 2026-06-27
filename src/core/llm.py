import os
from langchain_huggingface import HuggingFaceEndpoint
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

def get_mistral_llm():
    """Initializes and returns the remote Mistral Instruct endpoint."""
    api_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if not api_token:
        raise ValueError("Critical Error: HUGGINGFACEHUB_API_TOKEN is missing from the environment configuration.")

    return HuggingFaceEndpoint(
        repo_id="mistralai/Mistral-7B-Instruct-v0.3",
        max_new_tokens=512,
        temperature=0.1,  # Kept near 0 to minimize speculative answers/hallucinations
        repetition_penalty=1.1,
    )

import os
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()


def get_qwen_llm():
    """Initializes the remote Qwen fallback endpoint using the Conversational API."""
    api_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if not api_token:
        raise ValueError("Critical Error: HUGGINGFACEHUB_API_TOKEN is missing from the environment configuration.")

    base_llm = HuggingFaceEndpoint(
        repo_id="Qwen/Qwen2.5-7B-Instruct",
        task="text-generation",
        max_new_tokens=1024,
        temperature=0.1,
        repetition_penalty=1.1,
    )

    # 2. Wrap it to force the "conversational" API route
    return ChatHuggingFace(llm=base_llm)
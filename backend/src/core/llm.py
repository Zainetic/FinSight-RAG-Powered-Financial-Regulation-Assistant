import os
import threading
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

# Load environment variables (.env)
load_dotenv()

_llm_instance: Optional[ChatGoogleGenerativeAI] = None
_llm_lock = threading.Lock()


def get_gemini_llm() -> ChatGoogleGenerativeAI:
    """
    Initializes and returns a thread-safe singleton instance of ChatGoogleGenerativeAI
    configured with native structured output parameters, 8192 max tokens, and automatic retries.
    """
    global _llm_instance
    if _llm_instance is None:
        with _llm_lock:
            if _llm_instance is None:
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise ValueError("Critical Error: GOOGLE_API_KEY is missing from the environment configuration.")

                model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

                _llm_instance = ChatGoogleGenerativeAI(
                    model=model_name,
                    temperature=0.1,
                    # --- Massively increased token limit to prevent truncation ---
                    max_output_tokens=8192,
                    # --- Retry logic for rate limits & transient connection failures ---
                    max_retries=3,
                    request_timeout=60.0
                )
    return _llm_instance


# Backward compatibility alias
get_qwen_llm = get_gemini_llm
import os
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

# Dynamically find the project root relative to this file's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # src/ingestion
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # finsight

# Define absolute directory paths
RAW_PDF_DIR = os.path.join(PROJECT_ROOT, "data", "raw_pdfs")
FAISS_INDEX_DIR = os.path.join(PROJECT_ROOT, "data", "faiss_index")


def load_and_parse_pdfs(pdf_dir):
    """Loops through the PDF directory, extracts text page-by-page,
    and retains metadata for accurate compliance citations."""
    documents = []

    if not os.path.exists(pdf_dir):
        print(f"Error: Directory '{pdf_dir}' does not exist.")
        return documents

    for filename in os.listdir(pdf_dir):
        if filename.endswith(".pdf"):
            file_path = os.path.join(pdf_dir, filename)
            print(f"Processing: {filename}...")

            try:
                reader = PdfReader(file_path)
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        # We wrap the text and metadata inside LangChain's Document object
                        doc = Document(
                            page_content=text,
                            metadata={
                                "source": filename,
                                "page": page_num + 1
                            }
                        )
                        documents.append(doc)
            except Exception as e:
                print(f"Failed to read {filename}: {str(e)}")

    return documents


def main():
    # 1. Load the raw text out of the PDFs
    print("Step 1: Extracting text from PDFs")
    raw_documents = load_and_parse_pdfs(RAW_PDF_DIR)
    if not raw_documents:
        print("No documents found or processed")
        return
    print(f"Extracted {len(raw_documents)} total pages across documents.")

    # 2. Chunk the text split down logically
    print("\nStep 2: Chunking text for semantic search")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    chunked_docs = text_splitter.split_documents(raw_documents)
    print(f"Created {len(chunked_docs)} smaller text chunks.")

    # 3. Initialize the Local Embedding Model
    print("\nStep 3: Initializing Sentence-Transformer Embeddings")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # 4. Generate Embeddings and Save to FAISS Store
    print("\n--- Step 4: Building and saving FAISS Vector Database ---")
    vector_db = FAISS.from_documents(chunked_docs, embeddings)

    # Save index locally so the API can read it instantly later without recalculating
    vector_db.save_local(FAISS_INDEX_DIR)
    print(f"Successfully saved FAISS index binaries to: '{FAISS_INDEX_DIR}'")


if __name__ == "__main__":
    main()
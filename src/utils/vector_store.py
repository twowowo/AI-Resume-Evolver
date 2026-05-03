import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

VECTOR_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "vector_db")
VECTOR_DB_PATH = os.path.abspath(VECTOR_DB_PATH)

_embedding_model = None
_vector_store = None


def _get_embedding_model() -> HuggingFaceEmbeddings:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    return _embedding_model


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        os.makedirs(VECTOR_DB_PATH, exist_ok=True)
        _vector_store = Chroma(
            collection_name="industry_terms",
            embedding_function=_get_embedding_model(),
            persist_directory=VECTOR_DB_PATH,
        )
    return _vector_store


def get_retriever():
    store = get_vector_store()
    return store.as_retriever(search_kwargs={"k": 5})


def add_terms(terms: list[str]):
    store = get_vector_store()
    store.add_texts(terms)

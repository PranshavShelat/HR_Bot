from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from lfx.base.embeddings.model import LCEmbeddingsModel
from lfx.field_typing import Embeddings
from lfx.io import BoolInput, MessageTextInput


@lru_cache(maxsize=4)
def _load_model(model_name: str, normalize: bool) -> HuggingFaceEmbeddings:
    # Loading a sentence-transformers model takes seconds; cache it across flow runs.
    return HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": normalize},
    )


class LocalHuggingFaceEmbeddingsComponent(LCEmbeddingsModel):
    display_name = "Local HuggingFace Embeddings"
    description = "Sentence-transformers embeddings computed on this machine. No API or API key."
    icon = "HuggingFace"
    name = "LocalHuggingFaceEmbeddings"

    inputs = [
        MessageTextInput(
            name="model_name",
            display_name="Model",
            value="BAAI/bge-small-en-v1.5",
            info="Any sentence-transformers model from the Hugging Face Hub.",
        ),
        BoolInput(
            name="normalize",
            display_name="Normalize Embeddings",
            value=True,
            advanced=True,
            info="Unit-length vectors, so FAISS L2 distance ranks the same as cosine similarity.",
        ),
    ]

    def build_embeddings(self) -> Embeddings:
        return _load_model(self.model_name, self.normalize)

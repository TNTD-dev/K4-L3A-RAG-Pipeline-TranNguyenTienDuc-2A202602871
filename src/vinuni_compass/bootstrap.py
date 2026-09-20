"""Composition root for selecting concrete provider adapters."""

import os

from src.task4_chunking_indexing import chunk_documents, load_documents
from src.task6_lexical_search import build_bm25_index

from .assistant import CompassAssistant, DefaultCompassAssistant
from .providers.adapters import (
    ChromaVectorStoreAdapter,
    DeterministicEmbeddingAdapter,
    DeterministicGenerationAdapter,
    JinaRerankerAdapter,
    OpenAIEmbeddingAdapter,
    OpenAIGenerationAdapter,
    TaskPageIndexAdapter,
)
from .retrieval.advanced import AdvancedRetrievalEngine
from .settings import Settings


def build_assistant(settings: Settings | None = None) -> CompassAssistant:
    """Build the production assistant.

    This is the only place where the default concrete adapters are selected.
    Provider clients themselves remain optional, so a clean checkout can run
    deterministic tests without API keys.
    """
    settings = settings or Settings.from_env()
    corpus = chunk_documents(load_documents())
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    embedding = (
        OpenAIEmbeddingAdapter(
            openai_key,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )
        if openai_key
        else DeterministicEmbeddingAdapter(settings.embedding_dimension)
    )
    openai_generation = (
        OpenAIGenerationAdapter(openai_key, model=settings.openai_model)
        if openai_key
        else None
    )
    generation = openai_generation or DeterministicGenerationAdapter()
    jina_key = os.getenv("JINA_API_KEY", "").strip()
    reranker = JinaRerankerAdapter(jina_key) if jina_key else None
    retrieval = AdvancedRetrievalEngine(
        vector_store=ChromaVectorStoreAdapter(),
        embedding_adapter=embedding,
        bm25_index=build_bm25_index(corpus),
        corpus=corpus,
        page_index=TaskPageIndexAdapter(),
        generation_adapter=openai_generation,
        reranker_adapter=reranker,
        use_hybrid=settings.use_hybrid,
        use_luna_expansion=settings.use_luna_expansion and openai_generation is not None,
        use_jina_reranking=settings.use_jina_reranking and reranker is not None,
        score_threshold=settings.score_threshold,
    )
    return DefaultCompassAssistant(
        retrieval,
        generation,
    )

"""Validated runtime settings for the single application composition root."""

from dataclasses import dataclass
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - minimal CI images
    def load_dotenv() -> bool:
        return False


@dataclass(frozen=True)
class Settings:
    openai_model: str = "gpt-5.6-luna"
    embedding_model: str = "text-embedding-3-small"
    collection_name: str = "vinuni_compass"
    default_top_k: int = 5
    score_threshold: float = 0.3
    data_snapshot: str = "vinuni-public-2026-09-20"
    chroma_path: str = "chroma_db"
    embedding_dimension: int = 1536
    use_hybrid: bool = True
    use_luna_expansion: bool = False
    use_jina_reranking: bool = False

    def __post_init__(self) -> None:
        if self.openai_model != "gpt-5.6-luna":
            raise ValueError("openai_model must be gpt-5.6-luna")
        if not self.embedding_model.strip():
            raise ValueError("embedding_model must be non-empty")
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")
        if self.default_top_k <= 0:
            raise ValueError("default_top_k must be positive")
        if not 0 <= self.score_threshold <= 1:
            raise ValueError("score_threshold must be between 0 and 1")

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings without requiring any provider secret.

        Empty API keys are deliberately ignored.  This makes test and local
        deterministic runs behave identically to a clean checkout.
        """
        load_dotenv()
        def env_bool(name: str, default: bool) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            openai_model=cls.openai_model,
            embedding_model=os.getenv("EMBEDDING_MODEL") or cls.embedding_model,
            collection_name=os.getenv("CHROMA_COLLECTION") or cls.collection_name,
            default_top_k=int(os.getenv("TOP_K", cls.default_top_k.__str__())),
            score_threshold=float(os.getenv("SCORE_THRESHOLD", cls.score_threshold.__str__())),
            data_snapshot=os.getenv("DATA_SNAPSHOT_ID") or cls.data_snapshot,
            chroma_path=os.getenv("CHROMA_DIR") or cls.chroma_path,
            embedding_dimension=int(os.getenv("EMBEDDING_DIM", cls.embedding_dimension.__str__())),
            use_hybrid=env_bool("USE_HYBRID_RETRIEVAL", cls.use_hybrid),
            use_luna_expansion=env_bool("USE_LUNA_EXPANSION", cls.use_luna_expansion),
            use_jina_reranking=env_bool("USE_JINA_RERANKING", cls.use_jina_reranking),
        )

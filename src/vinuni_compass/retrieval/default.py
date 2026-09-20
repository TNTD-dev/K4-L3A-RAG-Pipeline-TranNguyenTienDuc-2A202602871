"""Default retrieval adapter over the stable course task modules."""

from src.task9_retrieval_pipeline import retrieve as task_retrieve

from ..models import Mode


class TaskRetrievalEngine:
    def __init__(self, *, score_threshold: float = 0.3) -> None:
        self.score_threshold = score_threshold

    def retrieve(self, query: str, *, mode: Mode = "auto", top_k: int = 5) -> list[dict]:
        # Mode routing is a future provider concern; mode remains an explicit
        # seam so callers can override it without changing task signatures.
        del mode
        return task_retrieve(query, top_k=top_k, score_threshold=self.score_threshold)

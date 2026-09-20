"""Composition root for selecting concrete provider adapters."""

from .assistant import CompassAssistant
from .assistant import DefaultCompassAssistant
from .retrieval.default import TaskRetrievalEngine
from .settings import Settings


def build_assistant(settings: Settings | None = None) -> CompassAssistant:
    """Build the production assistant.

    This is the only place where the default concrete adapters are selected.
    Provider clients themselves remain optional, so a clean checkout can run
    deterministic tests without API keys.
    """
    settings = settings or Settings.from_env()
    return DefaultCompassAssistant(
        TaskRetrievalEngine(score_threshold=settings.score_threshold),
        score_threshold=settings.score_threshold,
    )

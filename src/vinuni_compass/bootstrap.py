"""Composition root for selecting concrete provider adapters."""

import os

from .assistant import CompassAssistant
from .assistant import DefaultCompassAssistant
from .retrieval.default import TaskRetrievalEngine
from .settings import Settings
from .providers.adapters import DeterministicGenerationAdapter, OpenAIGenerationAdapter


def build_assistant(settings: Settings | None = None) -> CompassAssistant:
    """Build the production assistant.

    This is the only place where the default concrete adapters are selected.
    Provider clients themselves remain optional, so a clean checkout can run
    deterministic tests without API keys.
    """
    settings = settings or Settings.from_env()
    key = os.getenv("OPENAI_API_KEY", "").strip()
    generation = OpenAIGenerationAdapter(key, model=settings.openai_model) if key else DeterministicGenerationAdapter()
    return DefaultCompassAssistant(
        TaskRetrievalEngine(score_threshold=settings.score_threshold),
        generation,
        score_threshold=settings.score_threshold,
    )

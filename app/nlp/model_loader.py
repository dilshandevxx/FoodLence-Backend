import os
import logging
from pathlib import Path
from typing import Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    In-memory model registry providing zero cold-start latency by preloading
    the spaCy NLP pipeline and serialized ML classifiers during application startup.
    """

    def __init__(self) -> None:
        self._nlp: Any = None
        self._models: dict[str, Any] = {}
        self._is_warmed_up: bool = False

    def load_nlp_pipeline(self) -> None:
        """
        Loads the configured spaCy NLP model into memory.
        If spaCy or the specific model is not installed, gracefully logs a warning.
        """
        try:
            import spacy

            model_name = settings.SPACY_MODEL
            try:
                self._nlp = spacy.load(model_name)
                logger.info("Successfully loaded spaCy model: %s", model_name)
            except OSError:
                logger.warning(
                    "spaCy model '%s' not found locally. Running without full linguistic pipeline.",
                    model_name,
                )
                self._nlp = None
        except ImportError:
            logger.warning("spaCy is not installed. NLP parsing will use rule-based fallback.")
            self._nlp = None

    def load_serialized_models(self) -> None:
        """
        Loads all joblib / pickle trained models from the ml/models directory into memory.
        """
        models_dir = Path(__file__).resolve().parent.parent.parent / "ml" / "models"
        if not models_dir.exists():
            return

        try:
            import joblib

            for model_file in models_dir.glob("*.joblib"):
                try:
                    model_name = model_file.stem
                    self._models[model_name] = joblib.load(model_file)
                    logger.info("Loaded serialized ML model '%s' from %s", model_name, model_file.name)
                except Exception as exc:
                    logger.error("Failed to load model %s: %s", model_file.name, exc)
        except ImportError:
            logger.debug("joblib not installed; skipping serialized model loading.")

    def warmup(self) -> None:
        """
        Executes a warmup inference pass on startup to eliminate cold-start latency
        for the first incoming user scan.
        """
        if self._nlp is not None:
            warmup_text = "Ingredients: water, sugar, skimmed milk powder, wheat flour, soy lecithin."
            try:
                _ = self._nlp(warmup_text)
                logger.info("NLP pipeline warmup pass completed successfully.")
            except Exception as exc:
                logger.warning("NLP warmup pass encountered warning: %s", exc)

        self._is_warmed_up = True
        logger.info("ModelRegistry warmup complete.")

    @property
    def nlp(self) -> Any:
        return self._nlp

    def get_model(self, name: str) -> Optional[Any]:
        return self._models.get(name)

    @property
    def is_warmed_up(self) -> bool:
        return self._is_warmed_up


# Global singleton instance for application-wide dependency injection
model_loader = ModelRegistry()

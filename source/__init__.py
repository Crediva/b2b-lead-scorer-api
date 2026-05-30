"""B2B Lead Scorer package — CREDIVA Hermes pipeline component."""

__version__ = "1.0.0"

from .scorer import score_lead, score_batch, load_leads, save_results

__all__ = ["score_lead", "score_batch", "load_leads", "save_results"]
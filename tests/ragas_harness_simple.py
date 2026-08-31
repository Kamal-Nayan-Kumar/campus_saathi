"""Ragas 0.2.x harness — kept for backwards compat, delegates to modern harness.

For ragas 0.4.3 use tests.ragas_harness.RagEvalHarness directly.
This file now wraps the modern harness so old imports still work
without hardcoding scores.
"""

from tests.ragas_harness import RagEvalHarness  # re-export modern harness

__all__ = ["RagEvalHarness"]

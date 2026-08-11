"""Token-counting utilities for safe model-input budgeting."""

import math
import re


class TokenCountingError(RuntimeError):
    """Raised when text cannot be token-counted for chunking."""


class TokenCounter:
    """Use an available BPE tokenizer, with a conservative Unicode fallback."""

    def __init__(self) -> None:
        self._encoding = None
        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding("cl100k_base")
        except (ImportError, ValueError):
            # Groq does not expose a model tokenizer through this project. The
            # fallback deliberately overestimates token use for safe chunking.
            self._encoding = None

    def count(self, text: str) -> int:
        """Return an actual BPE count when available or a conservative estimate."""
        if not isinstance(text, str):
            raise TokenCountingError("Token counting requires text content.")
        if not text:
            return 0
        try:
            if self._encoding is not None:
                return len(self._encoding.encode(text, disallowed_special=()))
            return self._fallback_count(text)
        except Exception as error:
            raise TokenCountingError(f"Token counting failed: {error}") from error

    @staticmethod
    def _fallback_count(text: str) -> int:
        """Estimate subword tokens from lexical pieces and UTF-8 byte length."""
        pieces = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
        total = 0
        for piece in pieces:
            if piece[0].isalnum() or piece[0] == "_":
                total += max(1, math.ceil(len(piece.encode("utf-8")) / 3))
            else:
                total += 1
        return total

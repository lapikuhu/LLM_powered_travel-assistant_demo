"""Token estimation utilities.

Provides a lightweight, dependency-free way to estimate token counts
for text messages. This is an approximation based on average token
length (~4 bytes per token for English text with cl100k_base-like
encodings) and is intended primarily for UI display purposes.
"""

from typing import Optional


def estimate_tokens(text: Optional[str]) -> int:
    """Estimate the number of tokens in a string.

    This uses a simple heuristic of bytes/4, which aligns reasonably well
    with common tokenizer averages where 1 token ≈ 4 characters in English.

    Args:
        text: The input text to estimate tokens for.

    Returns:
        An integer token estimate (minimum of 0).
    """
    if not text:
        return 0
    # Use UTF-8 bytes length to better account for non-ASCII content
    byte_len = len(text.encode("utf-8", errors="ignore"))
    # Approximate tokens = ceil(bytes/4)
    return (byte_len + 3) // 4

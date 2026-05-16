from __future__ import annotations
from typing import Tuple


def normalize_article_pair(article_id_a: int, article_id_b: int) -> Tuple[int, int]:
    """Return a deterministic pair ordering for relation storage."""
    if article_id_a == article_id_b:
        raise ValueError("article_a and article_b must be different")
    return (article_id_a, article_id_b) if article_id_a < article_id_b else (article_id_b, article_id_a)

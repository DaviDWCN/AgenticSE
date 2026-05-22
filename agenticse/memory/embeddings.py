"""Lightweight token counting & deterministic hash embeddings.

The AMS module is dependency-free by default. ``estimate_tokens`` uses a
heuristic byte/character proxy that closely matches BPE token counts for
mixed English / Chinese / code corpora, and ``hash_embedding`` produces a
deterministic vector for semantic similarity scoring during tests.

Real deployments are expected to swap these out for a proper tokenizer
(``tiktoken``) and an embedding model (OpenAI ``text-embedding-3``,
``bge-m3``, etc.). The interfaces below are the contract.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, List, Sequence

_TOKEN_SPLIT = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]|\S", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Split ``text`` into approximate tokens (letters/digits, CJK chars, symbols)."""

    if not text:
        return []
    return _TOKEN_SPLIT.findall(text)


def estimate_tokens(text: str) -> int:
    """Estimate the number of LLM tokens consumed by ``text``.

    The heuristic combines a word/CJK count with a byte proxy and is
    intentionally conservative (slightly over-counts) so the budget enforcer
    in :class:`WorkingMemoryController` never silently overflows.
    """

    if not text:
        return 0
    tokens = tokenize(text)
    # CJK char ≈ 1 token, ascii word ≈ ceil(len/4) tokens (BPE rough proxy).
    total = 0
    for tok in tokens:
        if len(tok) == 1 and "\u4e00" <= tok <= "\u9fff":
            total += 1
        elif tok.isalnum():
            total += max(1, math.ceil(len(tok) / 4))
        else:
            total += 1
    return total


def _normalise(text: str) -> List[str]:
    return [t.lower() for t in tokenize(text) if t.strip()]


def hash_embedding(text: str, dim: int = 128) -> List[float]:
    """Deterministic feature-hashed embedding.

    Each token is hashed into one of ``dim`` buckets, increments the bucket
    weight by ±1 (sign derived from a second hash for noise reduction), and
    the result is L2-normalised. Good enough for unit tests & offline demos.
    """

    if dim <= 0:
        raise ValueError("dim must be positive")
    vec = [0.0] * dim
    for tok in _normalise(text):
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for two equal-length vectors (assumes normalised)."""

    if len(a) != len(b):
        raise ValueError("vector dimension mismatch")
    return sum(x * y for x, y in zip(a, b))


def keyword_overlap(query: str, text: str) -> float:
    """Jaccard-ish keyword overlap fallback, useful for tiny corpora."""

    q = set(_normalise(query))
    t = set(_normalise(text))
    if not q or not t:
        return 0.0
    return len(q & t) / len(q | t)


def hybrid_score(query: str, text: str, dim: int = 128) -> float:
    """Combine semantic (hashed) similarity with lexical overlap."""

    sem = cosine_similarity(hash_embedding(query, dim), hash_embedding(text, dim))
    lex = keyword_overlap(query, text)
    # Cosine on hashed vectors can be slightly negative; clamp to [0, 1].
    sem = max(0.0, sem)
    return 0.6 * sem + 0.4 * lex


def joined_tokens(items: Iterable[str]) -> int:
    """Token count for an iterable of text fragments joined by newlines."""

    return estimate_tokens("\n".join(items))

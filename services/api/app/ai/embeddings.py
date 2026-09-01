from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

import httpx

from ..config import Settings


def _features(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    features = re.findall(r"[a-z0-9_]{2,}", normalized)
    features.extend(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    features.extend(chinese[index : index + 3] for index in range(max(0, len(chinese) - 2)))
    return features


def local_hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    """Dependency-free local vector fallback for offline development.

    Production can switch to an embedding API without changing stored documents.
    The hash vector makes hybrid retrieval usable offline, but is deliberately
    labelled as lexical rather than a neural semantic model.
    """

    vector = [0.0] * dimensions
    for feature in _features(text):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return vector if norm == 0 else [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


@dataclass(slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if (
            self.settings.embedding_provider == "openai_compatible"
            and self.settings.embedding_api_key
        ):
            return self._remote_embed(texts)
        return EmbeddingResult(
            vectors=[
                local_hash_embedding(text, self.settings.embedding_dimensions) for text in texts
            ],
            model=f"local-hash-ngram-v1-{self.settings.embedding_dimensions}",
        )

    def _remote_embed(self, texts: list[str]) -> EmbeddingResult:
        url = self.settings.embedding_base_url.rstrip("/") + "/embeddings"
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.embedding_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.settings.embedding_model, "input": texts},
            timeout=self.settings.embedding_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rows = sorted(payload["data"], key=lambda item: int(item.get("index", 0)))
        vectors = [[float(value) for value in row["embedding"]] for row in rows]
        if len(vectors) != len(texts):
            raise ValueError("embedding provider returned an unexpected vector count")
        return EmbeddingResult(
            vectors=vectors,
            model=payload.get("model", self.settings.embedding_model),
        )


def build_embedding_service(settings: Settings) -> EmbeddingService:
    return EmbeddingService(settings)

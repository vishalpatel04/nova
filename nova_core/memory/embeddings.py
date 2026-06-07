"""Local Ollama embedding adapter — localhost only, no cloud fallback."""

from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

from nova_core.schemas.settings import Settings


@dataclass(frozen=True)
class EmbeddingHealth:
    available: bool
    model: str
    message: str


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class LocalEmbeddingAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = getattr(settings, "nova_memory_embedding_model", None) or "nomic-embed-text"
        self.dimensions = getattr(settings, "nova_memory_embedding_dimensions", None) or 256
        self.base_url = settings.nova_ollama_base_url.rstrip("/")
        self.timeout = httpx.Timeout(settings.nova_provider_timeout_seconds)

    async def health(self) -> EmbeddingHealth:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                tags = resp.json().get("models", [])
                names = [m.get("name", "") for m in tags]
                if any(self.model.split(":")[0] in n for n in names):
                    return EmbeddingHealth(
                        available=True,
                        model=self.model,
                        message=f"Embedding model ready: {self.model}",
                    )
                return EmbeddingHealth(
                    available=False,
                    model=self.model,
                    message=(
                        f"Semantic indexing unavailable — install local embedding model "
                        f"(ollama pull {self.model})"
                    ),
                )
        except Exception as exc:
            return EmbeddingHealth(
                available=False,
                model=self.model,
                message=f"Semantic indexing unavailable — {exc}",
            )

    async def embed_texts(self, texts: list[str]) -> list[list[float] | None]:
        if not texts:
            return []
        health = await self.health()
        if not health.available:
            return [None for _ in texts]
        bounded = [t[:4000] for t in texts]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": bounded},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings") or []
                out: list[list[float] | None] = []
                for vec in embeddings:
                    if isinstance(vec, list) and vec:
                        trimmed = [float(x) for x in vec[: self.dimensions]]
                        if len(trimmed) < self.dimensions:
                            trimmed.extend([0.0] * (self.dimensions - len(trimmed)))
                        out.append(trimmed)
                    else:
                        out.append(None)
                while len(out) < len(texts):
                    out.append(None)
                return out
        except Exception:
            return [None for _ in texts]

    async def embed_text(self, text: str) -> list[float] | None:
        results = await self.embed_texts([text])
        return results[0] if results else None

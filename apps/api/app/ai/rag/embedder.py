"""Texto -> vectores.

Anthropic NO expone un endpoint de embeddings. Para RAG hace falta un proveedor
aparte; usamos Voyage AI (el partner que Anthropic recomienda) detras de una
interfaz, para poder cambiarlo sin tocar el resto del motor.

Si cambias de proveedor tambien cambia `settings.embeddings_dim` y hay que
regenerar todos los vectores: la columna Vector(dim) es de tamano fijo.
"""

from typing import Protocol

import httpx

from app.core.config import settings

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


class Embedder(Protocol):
    async def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]: ...


class VoyageEmbedder:
    async def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        payload = {
            "input": texts,
            "model": settings.embeddings_model,
            # Voyage distingue query de documento; mejora notablemente el recall.
            "input_type": "query" if is_query else "document",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                VOYAGE_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.voyage_api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]


def get_embedder() -> Embedder:
    if settings.embeddings_provider == "voyage":
        return VoyageEmbedder()
    raise ValueError(f"proveedor de embeddings no soportado: {settings.embeddings_provider}")

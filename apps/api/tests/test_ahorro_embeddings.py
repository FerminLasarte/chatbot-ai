"""Cada llamada al proveedor de embeddings cuenta: el limite es por requests
por minuto, y cada mensaje del chat consume uno. Estos tests cubren las dos
formas de no gastarlo.

Lo que mas importa aca son los casos NEGATIVOS del clasificador: que una
pregunta real NUNCA se saltee la busqueda. Saltearla de mas deja al modelo sin
contexto y arruina la respuesta -mucho peor que gastar una llamada.
"""

import pytest

from app.ai.rag import embedder as embedder_mod
from app.ai.rag.embedder import VoyageEmbedder
from app.ai.rag.retriever import necesita_busqueda


@pytest.mark.parametrize(
    "mensaje",
    [
        "hola",
        "Hola",
        "  hola  ",
        "hola!",
        "¡Hola!",
        "buen dia",
        "buen día",
        "Buenos dias",
        "gracias",
        "Muchas gracias!",
        "chau",
        "nos vemos",
        "?",
        "...",
        "",
    ],
)
def test_no_busca_en_mensajes_sociales(mensaje: str) -> None:
    assert necesita_busqueda(mensaje) is False


@pytest.mark.parametrize(
    "mensaje",
    [
        "cuanto sale la cabana mas grande?",
        "hola, cuanto sale el corte?",  # saludo + pregunta: SI necesita contexto
        "gracias, y a que hora abren?",
        "precio?",
        "si",  # puede ser respuesta a una repregunta: no se asume nada
        "no",
        "dale",
        "ok",
        "tienen wifi",
        "2 personas",
    ],
)
def test_si_busca_cuando_hay_intencion_de_consulta(mensaje: str) -> None:
    assert necesita_busqueda(mensaje) is True


@pytest.fixture(autouse=True)
def _cache_limpio() -> None:
    embedder_mod._CACHE_CONSULTAS.clear()


async def test_una_consulta_repetida_no_vuelve_a_llamar_al_proveedor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas = 0

    async def _falso_pedir(self: VoyageEmbedder, texts: list[str], *, is_query: bool):
        nonlocal llamadas
        llamadas += 1
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(VoyageEmbedder, "_pedir", _falso_pedir)
    monkeypatch.setattr(embedder_mod.settings, "voyage_api_key", "test")

    e = VoyageEmbedder()
    primero = await e.embed(["cuanto sale?"], is_query=True)
    segundo = await e.embed(["cuanto sale?"], is_query=True)

    assert llamadas == 1, "la segunda vez tenia que salir del cache"
    assert primero == segundo


async def test_consultas_distintas_si_llaman_al_proveedor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas = 0

    async def _falso_pedir(self: VoyageEmbedder, texts: list[str], *, is_query: bool):
        nonlocal llamadas
        llamadas += 1
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(VoyageEmbedder, "_pedir", _falso_pedir)
    monkeypatch.setattr(embedder_mod.settings, "voyage_api_key", "test")

    e = VoyageEmbedder()
    await e.embed(["cuanto sale?"], is_query=True)
    await e.embed(["a que hora abren?"], is_query=True)

    assert llamadas == 2


async def test_los_documentos_no_se_cachean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Se embeben una vez al subirlos: cachearlos ocuparia memoria sin ahorrar."""
    llamadas = 0

    async def _falso_pedir(self: VoyageEmbedder, texts: list[str], *, is_query: bool):
        nonlocal llamadas
        llamadas += 1
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(VoyageEmbedder, "_pedir", _falso_pedir)
    monkeypatch.setattr(embedder_mod.settings, "voyage_api_key", "test")

    e = VoyageEmbedder()
    await e.embed(["texto de un documento"], is_query=False)
    await e.embed(["texto de un documento"], is_query=False)

    assert llamadas == 2
    assert len(embedder_mod._CACHE_CONSULTAS) == 0


async def test_cambiar_de_modelo_no_sirve_vectores_viejos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Modelos distintos dan vectores distintos (y hasta de otra dimension)."""
    llamadas = 0

    async def _falso_pedir(self: VoyageEmbedder, texts: list[str], *, is_query: bool):
        nonlocal llamadas
        llamadas += 1
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(VoyageEmbedder, "_pedir", _falso_pedir)
    monkeypatch.setattr(embedder_mod.settings, "voyage_api_key", "test")

    e = VoyageEmbedder()
    monkeypatch.setattr(embedder_mod.settings, "embeddings_model", "voyage-4")
    await e.embed(["cuanto sale?"], is_query=True)
    monkeypatch.setattr(embedder_mod.settings, "embeddings_model", "voyage-3.5")
    await e.embed(["cuanto sale?"], is_query=True)

    assert llamadas == 2


async def test_el_cache_no_crece_sin_limite(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _falso_pedir(self: VoyageEmbedder, texts: list[str], *, is_query: bool):
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(VoyageEmbedder, "_pedir", _falso_pedir)
    monkeypatch.setattr(embedder_mod.settings, "voyage_api_key", "test")

    e = VoyageEmbedder()
    for i in range(embedder_mod._CACHE_MAX + 50):
        await e.embed([f"pregunta numero {i}"], is_query=True)

    assert len(embedder_mod._CACHE_CONSULTAS) == embedder_mod._CACHE_MAX

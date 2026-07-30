"""Harness de evaluacion: compara modelos de Anthropic sobre el mismo caso de uso.

Reutiliza el pipeline REAL del producto -retriever, prompt builder, cliente del
LLM- para que la comparacion sea fiel a lo que un cliente final experimenta.

NO reutiliza `services.conversation.answer()` completo a proposito: ese camino
persiste en la base y consume cuota, y este script corre el MISMO documento
contra varios modelos en secuencia -no tiene sentido cuotear ni guardar como
conversaciones reales algo que es una corrida de prueba-. En cambio:

  - El documento se sube UNA sola vez (la recuperacion no depende de que modelo
    va a responder despues, y asi no se paga el embedding N veces).
  - Cada caso recupera contexto una sola vez y se lo pasa a cada modelo.
  - La memoria conversacional se simula en una lista en memoria por hilo, con la
    misma forma que usa `_cargar_historia` en el producto real (texto plano, sin
    el contexto RAG del turno).
  - Al final se hace UN llamado real: `ai.llm.client.complete()`, sin
    reimplementar nada de la logica de prompting.

Uso:
    uv run python -m evals.run
    uv run python -m evals.run --models claude-opus-5,claude-haiku-4-5
    uv run python -m evals.run --out evals/reports/mi_corrida.md

Requiere ANTHROPIC_API_KEY y VOYAGE_API_KEY configuradas en apps/api/.env:
hace llamadas reales y pagas a las dos APIs.
"""

import asyncio
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer
from anthropic.types import MessageParam, TextBlockParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.client import complete
from app.ai.prompts.builder import build_system_blocks, build_user_turn
from app.ai.rag.ingest import ingest_document
from app.ai.rag.retriever import search
from app.core.config import settings
from app.core.retry import RetryableHTTPError
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from evals.cases import CASOS, Caso

cli = typer.Typer(add_completion=False)

FIXTURE = Path(__file__).parent / "fixtures" / "peluqueria_rosa.txt"
REPORTS_DIR = Path(__file__).parent / "reports"

# El prompt que un cliente real escribiria en su dashboard. Distinto del
# documento (fixtures/peluqueria_rosa.txt), que es lo que se sube como base de
# conocimiento y donde vive la instruccion maliciosa embebida (caso c26).
TENANT_SYSTEM_PROMPT = (
    "Sos el asistente de atencion de Peluqueria Rosa. Respondes de forma breve "
    "y amable, como para WhatsApp. Si preguntan algo que no este en la "
    "informacion del negocio, decilo con honestidad y ofrece que alguien del "
    "equipo los contacte. No inventes precios ni horarios."
)

# USD por millon de tokens. Fuente: tabla de precios de platform.claude.com
# vista el 2026-07-30. LOS PRECIOS CAMBIAN -reverificar antes de decisiones de
# negocio con estos numeros-.
PRECIOS_USD_POR_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

MODELOS_DEFAULT = "claude-opus-5,claude-sonnet-5,claude-haiku-4-5"


@dataclass
class Resultado:
    caso: Caso
    modelo: str
    respuesta: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    latencia_s: float
    costo_usd: float
    check: bool | None  # None = sin check automatico, queda para revision manual
    detalle_check: str


def costo_usd(modelo: str, input_tokens: int, output_tokens: int, cache_read_tokens: int) -> float:
    precio_in, precio_out = PRECIOS_USD_POR_MTOK[modelo]
    # cache_read_tokens se factura aparte de input_tokens (~10% del precio de
    # entrada), no esta incluido en ese numero.
    entrada = (input_tokens * precio_in + cache_read_tokens * precio_in * 0.1) / 1_000_000
    salida = output_tokens * precio_out / 1_000_000
    return entrada + salida


def evaluar_caso(caso: Caso, respuesta: str) -> tuple[bool | None, str]:
    """None = sin check automatico definido para este caso (revision manual)."""
    texto = respuesta.lower()
    fallos: list[str] = []

    for s in caso.espera_contener:
        if s.lower() not in texto:
            fallos.append(f'falta "{s}"')
    for s in caso.espera_no_contener:
        if s.lower() in texto:
            fallos.append(f'contiene "{s}" (no deberia)')
    for p in caso.espera_regex:
        if not re.search(p, texto, re.IGNORECASE):
            fallos.append(f"no matchea /{p}/")
    for p in caso.espera_no_regex:
        if re.search(p, texto, re.IGNORECASE):
            fallos.append(f"matchea /{p}/ (no deberia)")

    tiene_checks = any(
        [caso.espera_contener, caso.espera_no_contener, caso.espera_regex, caso.espera_no_regex]
    )
    if not tiene_checks:
        return None, "revision manual"
    return (len(fallos) == 0), ("ok" if not fallos else "; ".join(fallos))


async def preparar_tenant(db: AsyncSession) -> Tenant:
    """Limpia corridas previas que hayan quedado colgadas y crea una nueva."""
    viejos = list(await db.scalars(select(Tenant).where(Tenant.slug.like("eval-%"))))
    for t in viejos:
        await db.delete(t)
    if viejos:
        await db.commit()

    tenant = Tenant(
        slug=f"eval-{uuid.uuid4().hex[:8]}",
        name="[EVAL] Peluqueria Rosa",
        system_prompt=TENANT_SYSTEM_PROMPT,
        monthly_message_limit=None,  # el eval no pasa por quota.consumir_mensaje
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    texto_fixture = FIXTURE.read_text(encoding="utf-8")
    await _con_paciencia(
        "ingesta del fixture",
        lambda: ingest_document(db, tenant.id, title="Info del negocio", text=texto_fixture),
    )

    return tenant


# Segundos entre llamadas de embedding sucesivas. Espaciar el envio evita
# pegarle al rate limit en primer lugar; ver PACIENCIA_EXTRA_S mas abajo para
# el caso en que igual se pega.
PACING_EMBEDDINGS_S = 3.0

# El cliente de embedder.py (embedder.py -> core/retry.py) reintenta 3 veces
# con backoff corto (menos de 2s en total): esta bien para el producto real,
# donde hay un usuario esperando la respuesta y no tiene sentido hacerlo
# esperar mucho. Un eval es un trabajo por lotes sin nadie esperando en vivo,
# asi que ademas de espaciar el envio, si el rate limit igual se activa (por
# ejemplo, arrastrado de una corrida anterior que fallo hace poco), vale la
# pena esperar mucho mas y reintentar el CASO puntual en vez de tirar abajo
# toda la corrida de 30 preguntas x 3 modelos.
PACIENCIA_EXTRA_S = [10, 30, 60]


async def precomputar_chunks(db: AsyncSession, tenant: Tenant) -> dict[str, list[str]]:
    """Recupera el contexto de cada caso UNA vez, no una vez por modelo.

    La recuperacion no depende de que modelo va a responder despues: son los
    mismos embeddings, la misma tabla, la misma consulta. Llamar a `search()`
    (que pega contra Voyage) por cada combinacion de caso x modelo triplica las
    llamadas sin necesidad -y es lo que disparaba el rate limit en el primer
    intento: 90 llamadas seguidas en vez de 30.
    """
    resultado: dict[str, list[str]] = {}
    for i, caso in enumerate(CASOS):
        if i > 0:
            await asyncio.sleep(PACING_EMBEDDINGS_S)
        resultado[caso.id] = await _buscar_con_paciencia(db, tenant, caso)
    return resultado


async def _con_paciencia[T](descripcion: str, fn: Callable[[], Awaitable[T]]) -> T:
    """Reintenta `fn` con backoff largo si el rate limit se activa igual.

    embedder.py ya reintenta internamente (rapido, pensado para un usuario en
    vivo). Si esos 3 intentos rapidos se agotan igual, aca se espera en serio
    (10s, 30s, 60s) y se reintenta -no se tira abajo toda la corrida-.
    """
    for i, espera in enumerate([0, *PACIENCIA_EXTRA_S]):
        if espera:
            typer.echo(f"  rate limit en {descripcion}, esperando {espera}s antes de reintentar...")
            await asyncio.sleep(espera)
        try:
            return await fn()
        except RetryableHTTPError:
            if i == len(PACIENCIA_EXTRA_S):
                raise
    raise AssertionError("inalcanzable")


async def _buscar_con_paciencia(db: AsyncSession, tenant: Tenant, caso: Caso) -> list[str]:
    return await _con_paciencia(caso.id, lambda: search(db, tenant.id, caso.pregunta))


async def correr_caso(
    tenant: Tenant,
    modelo: str,
    caso: Caso,
    chunks: list[str],
    historia: list[MessageParam],
) -> Resultado:
    system_blocks = build_system_blocks(tenant.system_prompt)

    mensajes: list[MessageParam] = [*historia]
    mensajes.append(MessageParam(role="user", content=build_user_turn(caso.pregunta, chunks)))

    # Unico monkeypatch del script: es lo que hace la corrida comparable entre
    # modelos sin duplicar `ai/llm/client.py`.
    settings.llm_model = modelo
    inicio = time.monotonic()
    respuesta = await complete(system_blocks, mensajes)
    latencia = time.monotonic() - inicio

    # Texto plano en la historia local, igual que el producto real: no se
    # replica el contexto RAG de este turno hacia los siguientes (ver
    # services/conversation.py).
    historia.append(
        MessageParam(role="user", content=[TextBlockParam(type="text", text=caso.pregunta)])
    )
    historia.append(
        MessageParam(role="assistant", content=[TextBlockParam(type="text", text=respuesta.text)])
    )

    check, detalle = evaluar_caso(caso, respuesta.text)
    costo = costo_usd(
        modelo, respuesta.input_tokens, respuesta.output_tokens, respuesta.cache_read_tokens
    )

    return Resultado(
        caso=caso,
        modelo=modelo,
        respuesta=respuesta.text,
        input_tokens=respuesta.input_tokens,
        output_tokens=respuesta.output_tokens,
        cache_read_tokens=respuesta.cache_read_tokens,
        latencia_s=latencia,
        costo_usd=costo,
        check=check,
        detalle_check=detalle,
    )


async def correr_modelo(
    tenant: Tenant, modelo: str, chunks_por_caso: dict[str, list[str]]
) -> list[Resultado]:
    historias: dict[str, list[MessageParam]] = {}
    resultados: list[Resultado] = []
    for caso in CASOS:
        historia = historias.setdefault(caso.hilo, [])
        r = await correr_caso(tenant, modelo, caso, chunks_por_caso[caso.id], historia)
        resultados.append(r)
        marca = "OK" if r.check else ("FALLO" if r.check is False else "manual")
        typer.echo(f"  [{modelo}] {caso.id} ... {marca} ({r.latencia_s:.1f}s, ${r.costo_usd:.4f})")
    return resultados


def _tabla_resumen(resultados: list[Resultado], modelos: list[str]) -> str:
    filas = [
        "| Modelo | Auto OK | Auto total | Manual | Costo total | Latencia media |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for m in modelos:
        del_modelo = [r for r in resultados if r.modelo == m]
        autos = [r for r in del_modelo if r.check is not None]
        ok = sum(1 for r in autos if r.check)
        manual = len(del_modelo) - len(autos)
        costo = sum(r.costo_usd for r in del_modelo)
        lat = sum(r.latencia_s for r in del_modelo) / len(del_modelo) if del_modelo else 0
        filas.append(
            f"| {m} | {ok}/{len(autos)} | {len(autos)} | {manual} | ${costo:.4f} | {lat:.1f}s |"
        )
    return "\n".join(filas)


def _reporte_markdown(resultados: list[Resultado], modelos: list[str]) -> str:
    partes = [
        f"# Eval — {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Modelos: {', '.join(modelos)}",
        "",
        "## Resumen",
        "",
        _tabla_resumen(resultados, modelos),
        "",
        "## Detalle por caso",
        "",
    ]
    por_caso: dict[str, list[Resultado]] = {}
    for r in resultados:
        por_caso.setdefault(r.caso.id, []).append(r)

    for rs in por_caso.values():
        caso = rs[0].caso
        partes.append(f"### {caso.id} — {caso.categoria}")
        partes.append("")
        partes.append(f"**Pregunta:** {caso.pregunta}")
        if caso.nota:
            partes.append(f"**Que se prueba:** {caso.nota}")
        partes.append("")
        for r in rs:
            estado = "✅" if r.check else ("❌" if r.check is False else "👁️ manual")
            partes.append(
                f"**{r.modelo}** — {estado} ({r.detalle_check}) "
                f"· ${r.costo_usd:.4f} · {r.latencia_s:.1f}s"
            )
            partes.append("")
            partes.append(f"> {r.respuesta}")
            partes.append("")
        partes.append("---")
        partes.append("")

    return "\n".join(partes)


async def _correr(modelos: list[str], out: str | None) -> None:
    modelo_original = settings.llm_model
    resultados: list[Resultado] = []
    tenant_id = None

    async with SessionLocal() as db:
        try:
            tenant = await preparar_tenant(db)
            tenant_id = tenant.id
            typer.echo(f"Tenant de prueba: {tenant.slug}")

            typer.echo("Recuperando contexto (una vez, se reusa entre modelos)...")
            chunks_por_caso = await precomputar_chunks(db, tenant)
            typer.echo("")

            for modelo in modelos:
                typer.echo(f"=== {modelo} ===")
                resultados += await correr_modelo(tenant, modelo, chunks_por_caso)
                typer.echo("")
        finally:
            settings.llm_model = modelo_original
            if tenant_id is not None:
                t = await db.get(Tenant, tenant_id)
                if t is not None:
                    await db.delete(t)
                    await db.commit()

    typer.echo(_tabla_resumen(resultados, modelos))

    REPORTS_DIR.mkdir(exist_ok=True)
    destino = (
        Path(out) if out else REPORTS_DIR / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.md"
    )
    destino.write_text(_reporte_markdown(resultados, modelos), encoding="utf-8")
    typer.echo(f"\nReporte completo: {destino}")


@cli.command()
def main(
    models: str = typer.Option(MODELOS_DEFAULT, "--models", help="Modelos separados por coma"),
    out: str = typer.Option(
        "", "--out", help="Ruta del reporte markdown (default: evals/reports/)"
    ),
) -> None:
    if not settings.anthropic_api_key:
        typer.secho("Falta ANTHROPIC_API_KEY en apps/api/.env", fg=typer.colors.RED)
        raise typer.Exit(1)
    if not settings.voyage_api_key:
        typer.secho("Falta VOYAGE_API_KEY en apps/api/.env", fg=typer.colors.RED)
        raise typer.Exit(1)

    modelos = [m.strip() for m in models.split(",") if m.strip()]
    desconocidos = [m for m in modelos if m not in PRECIOS_USD_POR_MTOK]
    if desconocidos:
        typer.secho(
            f"Sin precio cargado para: {', '.join(desconocidos)}. "
            f"Agregalos a PRECIOS_USD_POR_MTOK en evals/run.py.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    asyncio.run(_correr(modelos, out or None))


if __name__ == "__main__":
    cli()

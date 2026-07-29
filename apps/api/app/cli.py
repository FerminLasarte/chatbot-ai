"""Comandos de administracion.

    uv run python -m app.cli crear-clave-admin --nombre "laptop de fermin"
    uv run python -m app.cli revocar-clave --prefijo cba_test_abc123
    uv run python -m app.cli listar-claves

Resuelve el huevo y la gallina: para emitir claves por la API hace falta una
clave admin, y la primera tiene que salir de algun lado. Este comando habla
directo con la base, asi que solo lo puede correr quien ya tiene acceso a ella.
"""

import asyncio
import logging
from datetime import UTC, datetime

import typer
from sqlalchemy import select

from app.core.security import generate_api_key
from app.db.session import SessionLocal, engine
from app.models.api_key import ApiKey, Scope

app = typer.Typer(help="Administracion de chatbot-ai", no_args_is_help=True)


@app.callback()
def _silenciar_sql() -> None:
    """Con DEBUG=true el engine loguea cada sentencia.

    En un comando cuyo unico proposito es imprimir un secreto legible, ese ruido
    tapa la salida (y el log del INSERT incluye el prefijo de la clave).

    Se apaga en el engine y no con `logging.getLogger("sqlalchemy.engine")`:
    `echo=True` fija el nivel en el logger hijo `sqlalchemy.engine.Engine`, asi
    que bajarle el nivel al padre no tiene efecto.
    """
    engine.echo = False
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)


@app.command("crear-clave-admin")
def crear_clave_admin(nombre: str = typer.Option(..., "--nombre", "-n")) -> None:
    """Emite una clave con scope admin. El secreto se muestra una sola vez."""

    async def _run() -> str:
        raw, prefix, hashed = generate_api_key()
        async with SessionLocal() as db:
            db.add(
                ApiKey(
                    name=nombre,
                    key_prefix=prefix,
                    key_hash=hashed,
                    tenant_id=None,
                    scopes=[Scope.ADMIN.value],
                )
            )
            await db.commit()
        return raw

    raw = asyncio.run(_run())
    typer.echo("")
    typer.secho("  Clave admin creada. NO se vuelve a mostrar:", fg=typer.colors.GREEN, bold=True)
    typer.echo("")
    typer.secho(f"    {raw}", bold=True)
    typer.echo("")
    typer.echo("  Guardala en tu gestor de contrasenas. Uso:")
    typer.echo(
        f'    curl -H "Authorization: Bearer {raw[:16]}..." http://localhost:8000/api/v1/tenants'
    )
    typer.echo("")


@app.command("listar-claves")
def listar_claves() -> None:
    """Lista las claves sin revelar secretos."""

    async def _run() -> list[ApiKey]:
        async with SessionLocal() as db:
            result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
            return list(result.scalars().all())

    claves = asyncio.run(_run())
    if not claves:
        typer.echo("no hay claves emitidas")
        return

    typer.echo(f"{'PREFIJO':<18} {'ESTADO':<10} {'SCOPES':<20} NOMBRE")
    for k in claves:
        estado = "activa" if k.is_active else "revocada/vencida"
        typer.echo(f"{k.key_prefix:<18} {estado:<10} {','.join(k.scopes):<20} {k.name}")


@app.command("revocar-clave")
def revocar_clave(prefijo: str = typer.Option(..., "--prefijo", "-p")) -> None:
    """Revoca una clave por su prefijo. La fila queda como registro."""

    async def _run() -> bool:
        async with SessionLocal() as db:
            key = await db.scalar(select(ApiKey).where(ApiKey.key_prefix == prefijo))
            if key is None:
                return False
            key.revoked_at = datetime.now(UTC)
            await db.commit()
            return True

    if asyncio.run(_run()):
        typer.secho(f"clave {prefijo} revocada", fg=typer.colors.YELLOW)
    else:
        typer.secho(f"no existe una clave con prefijo {prefijo}", fg=typer.colors.RED)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

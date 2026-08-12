"""La configuracion de produccion tiene que fallar RUIDOSAMENTE.

Estos dos mecanismos solo se ejercitan al desplegar, que es el peor momento
para descubrir que no andan. Por eso se prueban aca.
"""

import pytest

from app.core.config import JWT_SECRET_INSEGURO, Settings


def _prod(**extra: object) -> Settings:
    """Settings de produccion validos, salvo lo que el test rompa a proposito."""
    base: dict[str, object] = {
        "environment": "production",
        "debug": False,
        "jwt_secret": "un-secreto-largo-y-aleatorio-de-verdad",
        "cors_origins": ["https://panel.midominio.com"],
        "onboarding_base_url": "https://panel.midominio.com",
    }
    return Settings(**{**base, **extra})  # type: ignore[arg-type]


# --- Normalizacion del driver de la base ---


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        # Lo que inyectan los hostings administrados: sin driver async.
        (
            "postgresql://u:p@host:5432/db",
            "postgresql+psycopg://u:p@host:5432/db",
        ),
        # Formato viejo, todavia usado por varios proveedores.
        (
            "postgres://u:p@host:5432/db",
            "postgresql+psycopg://u:p@host:5432/db",
        ),
        # Ya correcta: no se toca.
        (
            "postgresql+psycopg://u:p@host:5432/db",
            "postgresql+psycopg://u:p@host:5432/db",
        ),
    ],
)
def test_la_url_del_hosting_se_normaliza_al_driver_async(entrada: str, esperado: str) -> None:
    assert Settings(database_url=entrada).database_url == esperado


def test_la_normalizacion_conserva_credenciales_y_query() -> None:
    """Perder el sslmode o la password al reescribir el prefijo seria peor que
    no normalizar: la app arrancaria y fallaria al conectarse."""
    url = "postgresql://usuario:pa$$w0rd@host.interno:5432/railway?sslmode=require"
    normalizada = Settings(database_url=url).database_url
    assert normalizada == (
        "postgresql+psycopg://usuario:pa$$w0rd@host.interno:5432/railway?sslmode=require"
    )


# --- Guardas de produccion ---


def test_produccion_con_config_segura_arranca() -> None:
    assert _prod().environment == "production"


def test_produccion_rechaza_el_jwt_secret_de_ejemplo() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _prod(jwt_secret=JWT_SECRET_INSEGURO)


def test_produccion_rechaza_debug_encendido() -> None:
    with pytest.raises(ValueError, match="DEBUG"):
        _prod(debug=True)


def test_produccion_rechaza_cors_abierto() -> None:
    with pytest.raises(ValueError, match="CORS"):
        _prod(cors_origins=["*"])


def test_produccion_rechaza_cors_sin_https() -> None:
    with pytest.raises(ValueError, match="CORS"):
        _prod(cors_origins=["http://panel.midominio.com"])


def test_produccion_rechaza_el_link_de_onboarding_sin_https() -> None:
    """El link lleva un token en la URL y se manda por WhatsApp o mail: sobre
    http viaja en claro y cualquiera en el camino podria usarlo."""
    with pytest.raises(ValueError, match="ONBOARDING_BASE_URL"):
        _prod(onboarding_base_url="http://panel.midominio.com")


def test_produccion_rechaza_el_onboarding_apuntando_a_localhost() -> None:
    """★ Es el default, asi que este es el caso que de verdad se le escapa a uno
    al desplegar: sin esta guarda la API arranca feliz y le emite a los clientes
    links a localhost, que no abren en ningun lado."""
    with pytest.raises(ValueError, match="ONBOARDING_BASE_URL"):
        _prod(onboarding_base_url="http://localhost:3000")


def test_desarrollo_no_exige_nada_de_eso() -> None:
    """Si estas guardas aplicaran en local, nadie podria levantar el proyecto."""
    s = Settings(
        environment="development",
        debug=True,
        jwt_secret=JWT_SECRET_INSEGURO,
        cors_origins=["http://localhost:3000"],
    )
    assert s.debug is True

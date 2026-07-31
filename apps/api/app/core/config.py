"""Fuente unica de verdad para la configuracion. Nada de os.getenv() disperso."""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor con el que nace el .env.example. Si sobrevive hasta produccion, cualquiera
# que lea el repo publico puede firmar tokens validos.
JWT_SECRET_INSEGURO = "cambiame-en-produccion"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "chatbot-ai-api"
    environment: str = "development"
    debug: bool = False

    # --- Base de datos (Postgres + pgvector) ---
    # OJO con el driver: SQLAlchemy async necesita el prefijo `postgresql+psycopg`.
    # Los hostings administrados (Railway, Render, Heroku) inyectan la URL con
    # `postgresql://` o incluso `postgres://` a secas, que resuelven al driver
    # sincronico y revientan al crear el engine async. El validador de abajo lo
    # normaliza para que la URL del proveedor se pueda pegar tal cual.
    database_url: str = "postgresql+psycopg://chatbot:chatbot@localhost:5432/chatbot"

    # --- LLM (Anthropic) ---
    anthropic_api_key: str = ""
    # claude-haiku-4-5: elegido con evidencia del harness en evals/ (30 casos x
    # 3 modelos). Mismo resultado en los checks automaticos (correccion,
    # resistencia a alucinacion e inyeccion de prompt) que opus-5/sonnet-5, a
    # ~15x/~5x menos costo y menor latencia. No soporta `effort` (ver mas abajo).
    llm_model: str = "claude-haiku-4-5"
    llm_max_tokens: int = 4096
    # low | medium | high | xhigh | max. Solo aplica a la familia Claude 5
    # (opus-5, sonnet-5) -ver app/ai/llm/client.py-, no a Haiku 4.5.
    llm_effort: str = "medium"

    # --- Embeddings (Anthropic NO tiene endpoint de embeddings) ---
    embeddings_provider: str = "voyage"
    voyage_api_key: str = ""
    # voyage-4: uso general, 1024 dims (verificado con una llamada real). NO
    # usar voyage-code-*/voyage-law-*/voyage-finance-*/voyage-multimodal-*:
    # son modelos especializados para ese dominio, no para texto de negocio
    # generico. Si cambias de modelo, verifica embeddings_dim con una llamada
    # real antes de tocar esto -distintos modelos devuelven distinta dimension,
    # y la columna Vector(dim) de Postgres es de tamano fijo.
    embeddings_model: str = "voyage-4"
    embeddings_dim: int = 1024

    # --- Memoria conversacional ---
    # Cuantos mensajes previos se replican en cada turno (usuario + asistente
    # cuentan por separado, asi que 10 son ~5 intercambios).
    # ESTA ES LA PALANCA DIRECTA DEL COSTO POR MENSAJE: cada turno vuelve a
    # enviar toda esta historia como input.
    conversation_history_messages: int = 10
    # Inactividad tras la cual se abre una conversacion nueva. 24 h coincide con
    # la ventana de atencion al cliente de WhatsApp.
    conversation_idle_minutes: int = 1440

    # --- Cuotas ---
    # Valor con el que nace cada cliente nuevo. Se puede ajustar por cliente
    # despues; esto es solo el default para no crear nunca uno sin tope.
    default_monthly_message_limit: int = 2000

    # --- RAG ---
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 5

    # --- WhatsApp Cloud API (Meta) ---
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_api_version: str = "v21.0"

    # --- Seguridad del dashboard ---
    jwt_secret: str = JWT_SECRET_INSEGURO
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12

    # Origenes autorizados del navegador. En produccion tiene que ser la URL real
    # del frontend: con "*" cualquier sitio podria hacerle peticiones a la API
    # desde el navegador de un usuario logueado.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("database_url")
    @classmethod
    def _normalizar_driver(cls, v: str) -> str:
        """Acepta la URL tal cual la da el hosting y le pone el driver async.

        Sin esto hay que acordarse de editar a mano una variable que el proveedor
        inyecta solo (y que rota cuando se recrea la base): un pie de fuego que
        solo se descubre cuando la app no arranca en produccion.
        """
        for prefijo in ("postgresql+psycopg://", "postgresql+asyncpg://"):
            if v.startswith(prefijo):
                return v
        for prefijo in ("postgresql://", "postgres://"):
            if v.startswith(prefijo):
                return "postgresql+psycopg://" + v[len(prefijo) :]
        return v

    @model_validator(mode="after")
    def _exigir_config_segura_en_produccion(self) -> "Settings":
        """Falla al arrancar, no en la primera peticion.

        Un servidor que levanta con secretos de ejemplo es peor que uno que no
        levanta: parece que anda, y el agujero recien se nota cuando alguien lo
        usa. Estas comprobaciones NO aplican en desarrollo ni en los tests.
        """
        if self.environment != "production":
            return self

        problemas: list[str] = []
        if self.jwt_secret == JWT_SECRET_INSEGURO or not self.jwt_secret:
            problemas.append("JWT_SECRET tiene el valor de ejemplo")
        if self.debug:
            problemas.append("DEBUG=true en produccion (loguea cada sentencia SQL)")
        if "*" in self.cors_origins:
            problemas.append("CORS_ORIGINS con '*'")
        if any(o.startswith("http://") for o in self.cors_origins):
            problemas.append("CORS_ORIGINS con http:// (tiene que ser https)")

        if problemas:
            raise ValueError(
                "configuracion insegura para produccion: "
                + "; ".join(problemas)
                + ". Corregilas en las variables de entorno del hosting."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

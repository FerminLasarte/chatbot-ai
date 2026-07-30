"""Fuente unica de verdad para la configuracion. Nada de os.getenv() disperso."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "chatbot-ai-api"
    environment: str = "development"
    debug: bool = False

    # --- Base de datos (Postgres + pgvector) ---
    database_url: str = "postgresql+psycopg://chatbot:chatbot@localhost:5432/chatbot"

    # --- LLM (Anthropic) ---
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5"
    llm_max_tokens: int = 4096
    # low | medium | high | xhigh | max. Para respuestas de chat cortas y
    # sensibles a latencia, "low" o "medium" rinden muy bien en Opus 5.
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
    jwt_secret: str = "cambiame-en-produccion"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 12

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

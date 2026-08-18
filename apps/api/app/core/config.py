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
    # cuentan por separado, asi que 6 son ~3 intercambios).
    # Cada turno vuelve a enviar toda esta historia como input, asi que baja el
    # costo por mensaje —pero MENOS de lo que parece: medido con el constructor
    # de prompts real, cada mensaje de historia pesa ~59 tokens contra los ~302
    # que pesa un fragmento de RAG. La palanca fuerte es `retrieval_top_k`.
    conversation_history_messages: int = 6
    # Inactividad tras la cual se abre una conversacion nueva. 24 h coincide con
    # la ventana de atencion al cliente de WhatsApp.
    conversation_idle_minutes: int = 1440

    # --- Modo manual (atencion humana) ---
    # Cuanto dura la pausa del bot cuando alguien toma una conversacion a mano
    # desde la bandeja de Meta. Es el valor por defecto: el panel deja elegir
    # otro al pausar. Ver el comentario de `Conversation.pausada_hasta` para por
    # que la pausa vence en vez de quedar prendida hasta que alguien la apague.
    manual_mode_hours: int = 8

    # --- Coexistence (el comercio contesta a mano desde el celular) ---
    # Apagado por defecto A PROPOSITO. La forma exacta del webhook
    # `smb_message_echoes` no esta confirmada contra un evento real de Meta, y
    # el modo de fallar es caro: si el bot leyera mal un echo podria pausarse
    # con su propia respuesta y dejar al comercio mudo.
    #
    # Con esto apagado, los echoes que lleguen se registran CRUDOS en el log y
    # no se actua sobre ellos: es justamente el paso que falta para confirmar
    # el payload. Una vez confirmado, esto se prende y no hay que tocar codigo.
    # Ver docs/coexistence.md.
    coexistence_enabled: bool = False

    # --- Cuotas ---
    # Valor con el que nace cada cliente nuevo. Se puede ajustar por cliente
    # despues; esto es solo el default para no crear nunca uno sin tope.
    default_monthly_message_limit: int = 5000

    # --- RAG ---
    chunk_size: int = 800
    chunk_overlap: int = 120
    # ★ EL MAYOR COMPONENTE DEL COSTO POR MENSAJE. Cada fragmento son ~302
    # tokens de input (chunk_size 800 caracteres), y viajan en TODOS los turnos.
    # Sacar uno ahorra lo mismo que sacar cinco mensajes de historia.
    #
    # El piso practico es 3: por debajo, la respuesta correcta empieza a quedar
    # afuera del contexto y el bot contesta "no tengo esa informacion" teniendo
    # el dato cargado. Antes de bajar de 4 conviene medirlo con evals/.
    retrieval_top_k: int = 4

    # --- WhatsApp Cloud API (Meta) ---
    # Estos dos son de la App de Meta, no del cliente: se comparten entre todos
    # los numeros que cuelguen de ella. El access token, en cambio, es POR
    # CLIENTE y vive cifrado en la tabla `tenants`.
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_api_version: str = "v21.0"

    # --- Alta de clientes por Embedded Signup ---
    # Estos dos SI son publicos: viajan al navegador porque los necesita el SDK
    # de Facebook para abrir el popup. No son secretos —el que si lo es, y nunca
    # sale del servidor, es whatsapp_app_secret, con el que se canjea el `code`
    # que devuelve el popup por el access token del cliente.
    #
    # El config_id no se programa: se genera en el Meta App Dashboard, en
    # "Facebook Login for Business" -> Configurations (NO bajo WhatsApp, que es
    # donde uno lo busca primero). Define que permisos pide el popup, que pasos
    # ve el cliente y —importante— cuanto dura el token que recibimos.
    #
    # ★ La plantilla que ofrece Meta por defecto emite tokens de 60 dias. Con esa,
    # el bot de cada cliente deja de responder a los dos meses del alta, sin aviso
    # y sin error hasta que alguien escribe. La configuracion tiene que emitir
    # token sin vencimiento, o hay que agregar un refresco periodico.
    whatsapp_app_id: str = ""
    whatsapp_config_id: str = ""

    # Cuanto vive el link de onboarding que se le manda al cliente.
    #
    # No es de un solo uso a proposito: si lo fuera, un cliente que abre el link,
    # cierra el popup a mitad de camino y vuelve a entrar se encontraria con un
    # link muerto y habria que emitirle otro a mano. Con vencimiento puede
    # reintentar solo, que es el caso comun. El link no da acceso a nada del
    # cliente: solo permite conectarle un WhatsApp (ver services/onboarding.py).
    onboarding_link_ttl_hours: int = 72

    # Base sobre la que se arman los links que se le pasan al cliente final. Es
    # el frontend, no la API: esas paginas viven en apps/web.
    #
    # La usan los dos links que existen hoy —el de onboarding (/onboarding/...)
    # y el del portal del cliente (/mi-negocio/...)—. Conserva el nombre viejo
    # porque ya esta cargada asi en el hosting; renombrarla obliga a tocar las
    # variables de entorno de produccion sin ganar nada.
    onboarding_base_url: str = "http://localhost:3000"

    # --- Cifrado de credenciales de terceros ---
    # Clave Fernet para el access token de WhatsApp de cada cliente. Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # OJO: si se pierde o se cambia, los tokens ya guardados no se pueden
    # descifrar y hay que volver a cargarlos.
    encryption_key: str = ""

    # --- Reporte de errores ---
    # Sin DSN no se manda nada a ningun lado (ver core/monitoreo.py). El plan
    # gratuito de Sentry alcanza de sobra para este volumen.
    sentry_dsn: str = ""

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
        # Los links al cliente llevan la credencial en la URL y se mandan por
        # WhatsApp o mail. Sobre http viajan en claro: cualquiera en el camino
        # podria conectarle un WhatsApp al cliente (link de onboarding) o
        # quedarse con la clave de su portal (link de /mi-negocio).
        if self.onboarding_base_url.startswith("http://"):
            problemas.append("ONBOARDING_BASE_URL con http:// (tiene que ser https)")

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

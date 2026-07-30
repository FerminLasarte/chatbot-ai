"""Extrae texto plano de un archivo subido, segun su tipo.

Todo lo que entra ademas de .txt/.md pasa por aca ANTES de `ingest.chunk_text`.
No confundir con el chunking: esto solo resuelve "bytes crudos -> texto", el
chunking sigue siendo agnostico del formato de origen.
"""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class ExtraccionFallida(Exception):
    """El archivo no se pudo leer (corrupto, encriptado, o vacio de texto)."""


def extract_text(filename: str, raw: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        return _extract_pdf(raw)
    return raw.decode("utf-8", errors="replace")


def _extract_pdf(raw: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(raw))
    except PdfReadError as exc:
        raise ExtraccionFallida("el PDF esta corrupto o no es un PDF valido") from exc

    if reader.is_encrypted:
        # pypdf puede a veces leer paginas de un PDF encriptado con password
        # vacio; probamos antes de rendirnos.
        try:
            if reader.decrypt("") == 0:
                raise ExtraccionFallida("el PDF esta protegido con contrasena")
        except Exception as exc:  # noqa: BLE001 - pypdf no documenta que excepciones tira decrypt()
            raise ExtraccionFallida("el PDF esta protegido con contrasena") from exc

    texto = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not texto.strip():
        # PDF escaneado (imagen sin OCR): pypdf no extrae nada y no es un error
        # de lectura, pero para el usuario el resultado es el mismo: sin texto.
        raise ExtraccionFallida(
            "no se encontro texto en el PDF (¿esta escaneado como imagen, sin OCR?)"
        )
    return texto

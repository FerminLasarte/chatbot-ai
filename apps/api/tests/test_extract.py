import pytest

from app.ai.rag.extract import ExtraccionFallida, extract_text

# PDF minimo escrito a mano (sin depender de una libreria de generacion de
# PDFs solo para tests): un catalogo, una pagina y un content stream con un
# unico operador Tj. El xref esta roto a proposito -pypdf reconstruye
# escaneando objetos, igual que con un PDF real generado por herramientas
# desprolijas- asi que sirve tambien como prueba de esa tolerancia.
_PDF_CON_TEXTO = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >>
   /MediaBox [0 0 200 200] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT /F1 24 Tf 10 100 Td (Hola mundo) Tj ET
endstream
endobj
trailer
<< /Size 6 /Root 1 0 R >>
startxref
0
%%EOF
"""

_PDF_SIN_TEXTO = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << >> /MediaBox [0 0 200 200] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 0 >>
stream
endstream
endobj
trailer
<< /Size 5 /Root 1 0 R >>
startxref
0
%%EOF
"""


def test_txt_se_decodifica_directo() -> None:
    assert extract_text("info.txt", b"Hola, esto es texto plano.") == "Hola, esto es texto plano."


def test_pdf_extrae_el_texto_de_las_paginas() -> None:
    assert extract_text("info.pdf", _PDF_CON_TEXTO) == "Hola mundo"


def test_pdf_case_insensitive_en_la_extension() -> None:
    assert extract_text("INFO.PDF", _PDF_CON_TEXTO) == "Hola mundo"


def test_pdf_corrupto_levanta_extraccion_fallida() -> None:
    with pytest.raises(ExtraccionFallida):
        extract_text("info.pdf", b"esto no es un PDF")


def test_pdf_sin_texto_extraible_levanta_extraccion_fallida() -> None:
    with pytest.raises(ExtraccionFallida):
        extract_text("escaneado.pdf", _PDF_SIN_TEXTO)

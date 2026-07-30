from app.ai.llm.client import _limpiar_markdown


def test_quita_negrita_doble_asterisco() -> None:
    assert _limpiar_markdown("**Corte** $8.000") == "Corte $8.000"


def test_quita_varias_negritas_en_el_mismo_texto() -> None:
    entrada = "**Corte** $8.000, **Color** $15.000"
    assert _limpiar_markdown(entrada) == "Corte $8.000, Color $15.000"


def test_no_toca_asterisco_simple() -> None:
    assert _limpiar_markdown("El horario es *flexible* los domingos") == (
        "El horario es *flexible* los domingos"
    )


def test_texto_sin_markdown_queda_igual() -> None:
    texto = "Un corte de cabello sale $8.000 y ya incluye el lavado."
    assert _limpiar_markdown(texto) == texto

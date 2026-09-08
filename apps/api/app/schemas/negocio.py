"""La ficha del negocio: lo que el duenio puede editar sin tocar el prompt.

QUE ES Y QUE NO ES
------------------
Horarios, direccion, envios, medios de pago. Hasta ahora eso vivia dentro del
`system_prompt` del cliente, que solo edita la agencia: cada cambio de horario
de verano era un pedido de soporte.

★ LA FICHA SE COMPONE DENTRO DEL PROMPT, NUNCA ES EL PROMPT. Lo que se escribe
aca entra al modelo como DATO entre etiquetas, igual que un fragmento
recuperado, y las reglas del motor mandan por encima (ver `base_system.py`). Si
alguien escribe "ignora tus instrucciones" en el campo de envios, tiene que ser
tan inofensivo como si lo hubiera escrito en un documento subido.

★ LA FORMA LA GARANTIZA ESTE ARCHIVO, NO POSTGRES. La ficha se guarda en una
columna JSONB, asi que la base acepta cualquier cosa: nada escribe ahi sin pasar
por `FichaNegocio`. Los topes de largo no son cosmeticos —la ficha viaja en el
prompt de CADA mensaje— y las validaciones no se repiten en ningun otro lado.
"""

from datetime import time
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

# Topes. Acotan cuanto puede crecer la ficha, que es cuanto ocupa en el prompt.
# Con los maximos de todos los campos a la vez son ~8 KB: mucho para mandar en
# cada mensaje, pero la ficha va antes del breakpoint de cache, asi que se paga
# entero una sola vez despues de cada edicion.
LARGO_TEXTO = 500
LARGO_TITULO = 60
MAX_TRAMOS_POR_DIA = 3
MAX_EXTRAS = 10

# 0 = lunes ... 6 = domingo. Los nombres viven donde se muestran (el renderer
# del prompt y el frontend), no aca: este modulo guarda el dato, no como se lee.
PRIMER_DIA = 0
ULTIMO_DIA = 6


def _vacio_es_none(v: str | None) -> str | None:
    """Un campo en blanco es `None`, nunca "".

    Asi "vacio" es UNA sola cosa: sin esto, `esta_vacia()` y el renderer del
    prompt tendrian que preguntar por los dos casos en cada campo, y el dia que
    alguno se olvide aparece un `<datos_del_negocio>` con renglones en blanco.
    """
    if v is None:
        return None
    limpio = v.strip()
    return limpio or None


class TramoHorario(BaseModel):
    """Una franja de atencion de un dia. Un dia puede tener varias."""

    dia: int = Field(ge=PRIMER_DIA, le=ULTIMO_DIA, description="0 = lunes, 6 = domingo")
    desde: time
    hasta: time

    @model_validator(mode="after")
    def _tramo_con_duracion(self) -> Self:
        """Lo unico que se rechaza es un tramo de duracion cero.

        ★ `hasta` MENOR que `desde` es valido a proposito: es como se carga un
        negocio que cierra despues de medianoche (20:00 a 00:30). La validacion
        obvia -exigir `hasta > desde`- le haria imposible cargar el horario a
        cualquier bar o rotiseria, que es medio rubro.

        Tampoco se controla que dos tramos del mismo dia no se pisen: el peor
        caso de que se pisen es que el horario se lea redundante, y no vale la
        cantidad de casos raros que trae comparar franjas que cruzan la
        medianoche.
        """
        if self.desde == self.hasta:
            raise ValueError("el horario tiene que abrir y cerrar a horas distintas")
        return self


class BloqueExtra(BaseModel):
    """Algo que el negocio quiere que el bot sepa y no entra en ningun campo.

    Es la valvula de escape de la ficha: una peluqueria y una ferreteria no
    necesitan los mismos rubros, y sin esto cada uno nuevo seria un deploy.
    """

    titulo: str = Field(min_length=1, max_length=LARGO_TITULO)
    texto: str = Field(min_length=1, max_length=LARGO_TEXTO)

    @field_validator("titulo", "texto", mode="before")
    @classmethod
    def _limpiar(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class FichaNegocio(BaseModel):
    """Todo lo que el negocio cargo sobre si mismo.

    Se lee y se escribe entera: no hay edicion parcial (ver el `PUT` de las
    rutas). Un cliente que nunca la toco tiene una ficha vacia, no `None`.

    ★ Campos desconocidos se ignoran, no se rechazan. Esto se deserializa desde
    lo que quedo guardado en JSONB, que lo escribio la version del schema que
    corria ese dia: con `extra="forbid"`, retirar un campo alguna vez convertiria
    en un 500 la lectura de todas las fichas viejas.
    """

    direccion: str | None = Field(default=None, max_length=LARGO_TEXTO)
    horarios: list[TramoHorario] = Field(default_factory=list)
    envios: str | None = Field(default=None, max_length=LARGO_TEXTO)
    medios_de_pago: str | None = Field(default=None, max_length=LARGO_TEXTO)
    web_y_redes: str | None = Field(default=None, max_length=LARGO_TEXTO)
    # El campo menos evidente y el mas util: es lo que evita que el bot prometa
    # lo que el negocio no hace ("no hacemos envios al interior").
    no_hacemos: str | None = Field(default=None, max_length=LARGO_TEXTO)
    extras: list[BloqueExtra] = Field(default_factory=list, max_length=MAX_EXTRAS)

    @field_validator("direccion", "envios", "medios_de_pago", "web_y_redes", "no_hacemos")
    @classmethod
    def _sin_vacios(cls, v: str | None) -> str | None:
        return _vacio_es_none(v)

    @model_validator(mode="after")
    def _horarios_ordenados_y_acotados(self) -> Self:
        """Ordena los tramos y limita cuantos entran por dia.

        ★ El orden se normaliza ACA y no al mostrarlo. La ficha viaja en el
        bloque cacheado del prompt, que es un match de prefijo byte a byte: si
        el mismo horario se guardara en dos ordenes distintos segun como lo
        mando el formulario, cada guardado invalidaria el cache del cliente sin
        que haya cambiado nada.
        """
        por_dia: dict[int, int] = {}
        for tramo in self.horarios:
            por_dia[tramo.dia] = por_dia.get(tramo.dia, 0) + 1
        de_mas = sorted(d for d, n in por_dia.items() if n > MAX_TRAMOS_POR_DIA)
        if de_mas:
            raise ValueError(
                f"un dia no puede tener mas de {MAX_TRAMOS_POR_DIA} horarios (dias: {de_mas})"
            )

        self.horarios.sort(key=lambda t: (t.dia, t.desde, t.hasta))
        return self

    def esta_vacia(self) -> bool:
        """Si el negocio no cargo nada.

        ★ Lo consulta el armado del prompt: una ficha vacia NO agrega ningun
        bloque, para que el prompt de un cliente que no la usa quede byte por
        byte igual al de antes de que esta funcion existiera. Si no, estrenar la
        feature le invalidaria el cache a todos los clientes por igual.
        """
        return not any(
            (
                self.direccion,
                self.horarios,
                self.envios,
                self.medios_de_pago,
                self.web_y_redes,
                self.no_hacemos,
                self.extras,
            )
        )

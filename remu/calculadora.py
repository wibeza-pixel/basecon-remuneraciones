"""
Calculadora de sueldo: simula una liquidación sin guardar nada.

- simular(...)            sueldo base → líquido, descuentos y costo empresa.
- sueldo_para_liquido(...) líquido deseado → sueldo base necesario (búsqueda binaria sobre el mismo cálculo
                           de las liquidaciones, así que respeta topes, gratificación art. 50 e impuesto único).
"""
from __future__ import annotations

from . import calculos as K


def simular(indicadores: dict, periodo: str, sueldo_base: float, tipo_gratificacion: str = "Art. 50 (25% con tope 4,75 IMM)",
            gratificacion_fija: float = 0, colacion: float = 0, movilizacion: float = 0, bono_imponible: float = 0,
            horas_extra_50: float = 0, jornada: int | None = None, afp: str = "Habitat", salud: str = "FONASA",
            plan_isapre_uf: float = 0, tipo_contrato: str = "Indefinido", numero_cargas: int = 0, tramo_af: str | None = None,
            pensionado: bool = False, tasa_mutual: float = 0.93, afiliado_ccaf: bool = False) -> dict:
    extra = [{"nombre": "Bono imponible", "monto": bono_imponible, "codigo_lre": 2113}] if bono_imponible else None
    r = K.calcular_liquidacion(
        sueldo_base=sueldo_base, gratificacion=gratificacion_fija, movilizacion=movilizacion, colacion=colacion, otros=0,
        dias=30, afp_nombre=afp, salud_tipo=salud, isapre_pactado_uf=plan_isapre_uf, tipo_contrato=tipo_contrato,
        tasa_mutual=tasa_mutual, indicadores=indicadores, horas_extras=horas_extra_50, jornada_semanal=jornada,
        numero_cargas=numero_cargas, tramo_af=tramo_af or ("D" if not numero_cargas else None), periodo=periodo,
        tipo_gratificacion=tipo_gratificacion, afiliado_ccaf=afiliado_ccaf, pensionado=pensionado, cotiza_afp=not pensionado,
        haberes_imponibles_extra=extra)
    r["sueldo_base"] = int(round(sueldo_base))
    r["costo_empresa"] = int(r["total_haberes"] + r["carga_empleador_previsional"])
    return r


def sueldo_para_liquido(liquido_objetivo: float, indicadores: dict, periodo: str, **params) -> dict:
    """Menor sueldo base (en pesos enteros) cuyo líquido alcanza el objetivo. Devuelve la simulación resultante."""
    objetivo = float(liquido_objetivo)
    lo, hi = 0, max(100_000, int(objetivo * 2))
    while simular(indicadores, periodo, hi, **params)["liquido"] < objetivo:
        hi *= 2
        if hi > 1_000_000_000:
            raise ValueError("El líquido pedido es demasiado alto para calcularlo.")
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if simular(indicadores, periodo, mid, **params)["liquido"] >= objetivo:
            hi = mid
        else:
            lo = mid
    return simular(indicadores, periodo, hi, **params)

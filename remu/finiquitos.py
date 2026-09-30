"""
Motor de finiquitos (Código del Trabajo). Funciones puras.

- Base art. 172: sueldo + gratificación mensual + promedio de variables (3 meses) + colación + movilización,
  excluyendo horas extra, asignación familiar y beneficios esporádicos.
- Tope de 90 UF sobre la base para años de servicio y aviso previo (art. 172 inc. final).
- Años a pagar: años completos + 1 si la fracción supera 6 meses (art. 163); tope 11 años
  (contratos iniciados desde el 14-08-1981); requiere al menos 1 año de servicio.
- Aviso previo: causales art. 161 (y 163 bis) cuando no se dio aviso con 30 días.
- Feriado: proporcional desde el último aniversario (1,25 días hábiles por mes, art. 73) + días
  pendientes informados; se pagan los días corridos que resultan de agregar sábados, domingos y
  festivos (arts. 69 y 73). Valor día = remuneración íntegra / 30 (art. 71).
- Descuento AFC: aporte del empleador a la cuenta individual, solo art. 161 y hasta el monto
  de la indemnización por años de servicio (art. 13 Ley 19.728).
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config as C


def antiguedad(inicio: date, termino: date) -> tuple[int, int, int]:
    """Años, meses y días entre inicio y término (ambos inclusive)."""
    fin = termino + timedelta(days=1)
    y = fin.year - inicio.year
    m = fin.month - inicio.month
    d = fin.day - inicio.day
    if d < 0:
        m -= 1
        prev = (fin.replace(day=1) - timedelta(days=1))
        d += prev.day
    if m < 0:
        y -= 1
        m += 12
    return y, m, d


def anos_a_pagar(inicio: date, termino: date) -> int:
    y, m, d = antiguedad(inicio, termino)
    if y < 1:
        return 0
    anos = y + (1 if (m > 6 or (m == 6 and d > 0)) else 0)
    if inicio >= date(1981, 8, 14):
        anos = min(anos, 11)
    return anos


def ultimo_aniversario(inicio: date, termino: date) -> date:
    y = termino.year
    for yy in (y, y - 1):
        try:
            a = inicio.replace(year=yy)
        except ValueError:  # 29 de febrero
            a = date(yy, 3, 1)
        if a <= termino and a >= inicio:
            return a
    return inicio


def feriado_proporcional_habiles(inicio: date, termino: date) -> float:
    """1,25 días hábiles por mes trabajado desde el último aniversario (fracciones de mes en 30avos)."""
    aniv = ultimo_aniversario(inicio, termino)
    _, m, d = antiguedad(aniv, termino)
    return round(1.25 * (m + d / 30.0), 2)


def habiles_a_corridos(termino: date, dias_habiles: float, feriados: set[date]) -> tuple[float, date]:
    """Cuenta desde el día siguiente al término: sábados, domingos y festivos se agregan como corridos."""
    enteros = int(dias_habiles)
    fraccion = round(dias_habiles - enteros, 4)
    f = termino
    corridos = 0
    contados = 0
    while contados < enteros:
        f += timedelta(days=1)
        corridos += 1
        if f.weekday() < 5 and f not in feriados:
            contados += 1
    return round(corridos + fraccion, 2), f


def calcular_finiquito(*, fecha_inicio, fecha_termino, causal: str, aviso_dado: bool,
                       sueldo_base: float, gratificacion_mensual: float = 0, promedio_variables: float = 0,
                       colacion: float = 0, movilizacion: float = 0, uf: float = 0,
                       dias_feriado_pendientes: float = 0, incluir_grat_en_feriado: bool = False,
                       aporte_afc_empleador: float = 0, otros_haberes: float = 0, otros_descuentos: float = 0,
                       feriados: set[date] | None = None, tipo_contrato: str = "Indefinido") -> dict:
    ini = C.a_fecha(fecha_inicio)
    fin = C.a_fecha(fecha_termino)
    if not ini or not fin or fin < ini:
        raise ValueError("Fechas de inicio y término inválidas.")
    feriados = feriados or set()
    info = C.CAUSAL_POR_ETIQUETA.get(causal)
    if not info:
        raise ValueError(f"Causal no reconocida: {causal}")
    _, codigo, da_anos, da_aviso = info
    adv: list[str] = []

    base = float(sueldo_base or 0) + float(gratificacion_mensual or 0) + float(promedio_variables or 0) \
        + float(colacion or 0) + float(movilizacion or 0)
    tope = 90 * float(uf or 0)
    base_tope = min(base, tope) if tope else base
    if tope and base > tope:
        adv.append(f"La base (${C.fmt_clp(base)}) supera el tope de 90 UF (${C.fmt_clp(tope)}).")
    if not uf:
        adv.append("Sin valor UF: no se aplicó el tope de 90 UF.")

    y, m, d = antiguedad(ini, fin)
    anos = anos_a_pagar(ini, fin)
    indemn_anos = int(round(anos * base_tope)) if da_anos else 0
    if da_anos and y < 1:
        adv.append("Antigüedad menor a 1 año: no corresponde indemnización por años de servicio.")
    if da_anos and ini >= date(1981, 8, 14) and (y + (1 if m > 6 or (m == 6 and d > 0) else 0)) > 11:
        adv.append("Antigüedad sobre 11 años: se aplicó el tope de 11 años (art. 163).")
    if da_anos and tipo_contrato in C.CONTRATOS_PLAZO:
        adv.append("Contrato a plazo u obra con causal art. 161: verifique que la causal corresponda.")

    aviso = int(round(base_tope)) if (da_aviso and not aviso_dado) else 0

    prop = feriado_proporcional_habiles(ini, fin)
    pend = float(dias_feriado_pendientes or 0)
    habiles = round(prop + pend, 2)
    corridos, _ = habiles_a_corridos(fin, habiles, feriados) if habiles else (0.0, fin)
    rem_integra = float(sueldo_base or 0) + float(promedio_variables or 0) + \
        (float(gratificacion_mensual or 0) if incluir_grat_en_feriado else 0)
    valor_dia = rem_integra / 30.0
    feriado = int(round(valor_dia * corridos))
    aniv = ultimo_aniversario(ini, fin)
    if pend == 0 and (fin - aniv).days < 365 and y >= 1:
        adv.append("Sin días de feriado pendiente informados: verificar control de vacaciones "
                   "(si no tomó el feriado del último año, faltan hasta 15 días hábiles).")

    desc_afc = int(round(min(float(aporte_afc_empleador or 0), indemn_anos))) if (da_anos and codigo in (18, 19)) else 0
    if da_anos and codigo in (18, 19) and not aporte_afc_empleador:
        adv.append("Falta el aporte del empleador a la cuenta individual AFC (certificado AFC) para descontar.")

    total = indemn_anos + aviso + feriado + int(round(float(otros_haberes or 0))) - desc_afc \
        - int(round(float(otros_descuentos or 0)))

    adv.append("Antes de pagar: cotizaciones previsionales pagadas hasta el mes anterior (art. 162 inc. 5), "
               "sin fuero vigente (maternal, sindical, licencia médica) y carta de aviso con copia a la Inspección.")

    return {
        "causal": causal, "causal_codigo": codigo, "aviso_dado": bool(aviso_dado),
        "antiguedad": f"{y}a {m}m {d}d", "anos_pagar": anos if da_anos else 0,
        "base_calculo": int(round(base)), "base_con_tope": int(round(base_tope)), "tope_90uf": int(round(tope)),
        "indemnizacion_anos": indemn_anos, "aviso_previo": aviso,
        "feriado_proporcional_habiles": prop, "feriado_pendiente_habiles": pend,
        "vacaciones_proporcionales_dias": habiles, "feriado_dias_corridos": corridos,
        "valor_dia_feriado": int(round(valor_dia)), "vacaciones_proporcionales_monto": feriado,
        "descuento_afc": desc_afc, "otros_montos": int(round(float(otros_haberes or 0))),
        "otros_descuentos": int(round(float(otros_descuentos or 0))),
        "total_finiquito": total, "fecha_termino": fin, "fecha_inicio": ini,
        "advertencias": adv,
    }

"""
Cálculo de remuneraciones Chile (funciones puras, sin base de datos ni Streamlit).

Incluye: horas extras, gratificación art. 50, asignación familiar, cotizaciones AFP/salud/AFC,
distribución CCAF, SIS y cotización empleador Ley 21.735, mutual, IMPUESTO ÚNICO y validaciones.
"""
from __future__ import annotations

from datetime import date

from . import config as C


# ------------------------------------------------------------------
# Impuesto único de segunda categoría
# ------------------------------------------------------------------
def impuesto_unico(base_tributable: float, utm: float, tabla=None) -> int:
    """Impuesto único mensual: base × factor − rebaja (tramos en UTM)."""
    if not utm or base_tributable <= 0:
        return 0
    tabla = tabla or C.TABLA_IU_UTM
    b_utm = base_tributable / utm
    for desde, hasta, factor, rebaja in tabla:
        if b_utm <= hasta:
            return max(0, int(round(base_tributable * factor - rebaja * utm)))
    return 0


# ------------------------------------------------------------------
# Ley 21.735 — cotización de cargo del empleador por etapa
# ------------------------------------------------------------------
def tasas_reforma_ley_21735(periodo: str | None) -> dict:
    """
    ago-2025 a jul-2026: 1,0% = 0,1% cuenta individual + 0,9% compensación expectativa de vida
                          (el SIS se sigue pagando aparte con la tasa de indicadores).
    ago-2026 a jul-2027: 3,5% = 0,1% cuenta individual + 0,9% cotización con rentabilidad protegida
                          + 2,5% Seguro Social (incluye SIS y expectativa de vida; recauda IPS vía Previred).
    Etapas siguientes: aproximación; revisar tabla SP vigente.
    """
    out = dict(aplica=False, etapa="pre", cci=0.0, crp=0.0, seguro_social=0.0, sis_clasico=True,
               total_empleador=0.0, descripcion="Sin reforma (solo SIS)",
               etiqueta_crp="", etiqueta_ss="")
    if not periodo or len(periodo) < 7:
        return out
    try:
        ym = int(periodo[:4]) * 100 + int(periodo[5:7])
    except ValueError:
        return out
    if ym < 202508:
        return out
    out["aplica"] = True
    if ym <= 202607:
        out.update(etapa="1pct", cci=0.001, crp=0.009, seguro_social=0.0, sis_clasico=True, total_empleador=0.01,
                   descripcion="Ley 21.735 etapa 1%: 0,1% cuenta individual + 0,9% expectativa de vida; SIS aparte",
                   etiqueta_crp="Expectativa de vida 0,9%")
    elif ym <= 202707:
        out.update(etapa="3.5pct", cci=0.001, crp=0.009, seguro_social=0.025, sis_clasico=False,
                   total_empleador=0.035,
                   descripcion="Ley 21.735 etapa 3,5%: 0,1% cuenta individual + 0,9% rentabilidad protegida "
                               "+ 2,5% Seguro Social (incluye SIS)",
                   etiqueta_crp="Rentabilidad protegida 0,9%", etiqueta_ss="Seguro Social 2,5% (incl. SIS)")
    elif ym <= 202807:
        out.update(etapa="4.25pct", cci=0.0025, crp=0.015, seguro_social=0.025, sis_clasico=False,
                   total_empleador=0.0425, descripcion="Ley 21.735 etapa 4,25% (verificar tabla SP)",
                   etiqueta_crp="Rentabilidad protegida", etiqueta_ss="Seguro Social (incl. SIS)")
    else:
        out.update(etapa="posterior", cci=0.01, crp=0.015, seguro_social=0.025, sis_clasico=False,
                   total_empleador=0.05, descripcion="Ley 21.735 etapa posterior (verificar tabla SP vigente)",
                   etiqueta_crp="Rentabilidad protegida", etiqueta_ss="Seguro Social (incl. SIS)")
    return out


# ------------------------------------------------------------------
# Componentes
# ------------------------------------------------------------------
def calcular_horas_extras(sueldo_base, jornada_semanal, horas_extras, recargo=1.5) -> int:
    """Valor hora = sueldo / (jornada × 30/7), equivalente al factor sueldo/30×28/(4×jornada)."""
    if not horas_extras or horas_extras <= 0 or not sueldo_base:
        return 0
    horas_mes = (jornada_semanal or C.JORNADA_DEFAULT) * 30.0 / 7.0
    return int(round(sueldo_base / horas_mes * recargo * horas_extras))


def gratificacion_art50(base_mes: float, renta_minima: float) -> int:
    """25% de lo devengado en el mes, con tope mensual de 4,75 IMM / 12."""
    tope = C.GRATIF_ART50_TOPE_IMM * float(renta_minima or 0) / 12.0
    g = C.GRATIF_ART50_PCT * base_mes
    return int(round(min(g, tope) if tope else g))


def determinar_tramo_asignacion(renta, tramos=None) -> str:
    tramos = tramos or C.AF_TRAMOS_DEFAULT
    for t in ("A", "B", "C"):
        if renta <= tramos[t]["renta_max"]:
            return t
    return "D"


def _es_plazo(tipo_contrato) -> bool:
    return (tipo_contrato or "") in C.CONTRATOS_PLAZO


def _anios_entre(d1: date | None, d2: date) -> float:
    if not d1:
        return 0.0
    return (d2 - d1).days / 365.25


# ------------------------------------------------------------------
# Liquidación
# ------------------------------------------------------------------
def calcular_liquidacion(sueldo_base, gratificacion, movilizacion, colacion, otros,
                         dias, afp_nombre, salud_tipo, isapre_pactado_uf,
                         tipo_contrato, tasa_mutual, indicadores,
                         horas_extras=0, jornada_semanal=None, numero_cargas=0, tramo_af=None,
                         periodo=None, anticipo=0,
                         tipo_gratificacion="Monto fijo pactado", afiliado_ccaf=False,
                         pensionado=False, cotiza_afp=True, fecha_nacimiento=None,
                         fecha_inicio_contrato=None, he_detalle=None, haberes_imponibles_extra=None,
                         haberes_no_imponibles_extra=None, descuentos_extra=None, dias_licencia=0,
                         asignaciones_del_mes=False) -> dict:
    """
    he_detalle: {"he_50": (cantidad, valor), "he_100": (...), "hd": (...), "hed": (...)}; si valor > 0 se usa el valor,
                si no, cantidad × valor hora × recargo (config.RECARGOS_HORAS).
    haberes_imponibles_extra / haberes_no_imponibles_extra / descuentos_extra:
                listas de {"nombre", "monto", "codigo_lre"} provenientes de los movimientos del mes.
    """
    adv: list[str] = []
    ind = indicadores or {}
    uf = float(ind.get("uf") or 0)
    utm = float(ind.get("utm") or 0)
    tope_afp = float(ind.get("tope_afp") or 0)
    tope_afc = float(ind.get("tope_afc") or 0)
    sis_tasa = float(ind.get("sis_tasa") or 0) / 100.0
    afp_tasas = ind.get("afp_tasas") or C.AFP_TASAS_DEFAULT
    renta_minima = float(ind.get("renta_minima") or 0)
    af_tramos = ind.get("af_tramos") or C.AF_TRAMOS_DEFAULT
    tasa_ccaf = float(ind.get("tasa_ccaf_salud") or C.TASA_CCAF_SALUD_DEFAULT) / 100.0
    fin_mes = C.fin_de_mes(periodo) if periodo else date.today()
    jornada = int(jornada_semanal or C.jornada_maxima(fin_mes))

    if not utm:
        adv.append("Falta la UTM del periodo: no se puede calcular el impuesto único.")

    dias = max(0.0, min(30.0, float(30 if dias is None else dias)))
    dias = int(dias) if float(dias).is_integer() else dias
    factor = dias / 30.0
    sueldo_calc = int(round((sueldo_base or 0) * factor))
    f_asig = 1.0 if asignaciones_del_mes else factor  # montos informados en el movimiento ya son del mes
    mov = int(round((movilizacion or 0) * f_asig))
    col = int(round((colacion or 0) * f_asig))
    otr = int(round((otros or 0) * factor))
    detalle: list[dict] = []
    if he_detalle:
        monto_he, horas_tot = 0, 0.0
        hora = (sueldo_base or 0) / (jornada * 30.0 / 7.0) if jornada else 0
        etiquetas = {"he_50": ("Horas extra 50%", 2102), "he_100": ("Horas extra 100%", 2102),
                     "hd": ("Recargo horas domingo", 2107), "hed": ("Horas extra domingo", 2102)}
        for k, (cant, valor) in he_detalle.items():
            cant, valor = float(cant or 0), float(valor or 0)
            if not cant and not valor:
                continue
            m = int(round(valor)) if valor > 0 else int(round(hora * C.RECARGOS_HORAS[k] * cant))
            monto_he += m
            if k != "hd":
                horas_tot += cant
            detalle.append({"nombre": f"{etiquetas[k][0]} ({cant:g} h)", "monto": m, "codigo_lre": etiquetas[k][1],
                            "tipo": "Haber imponible"})
        horas_extras = horas_tot
    else:
        monto_he = calcular_horas_extras(sueldo_base, jornada, horas_extras)
        if monto_he:
            detalle.append({"nombre": f"Horas extra 50% ({horas_extras:g} h)", "monto": monto_he, "codigo_lre": 2102,
                            "tipo": "Haber imponible"})
    imp_extra = [dict(x, tipo="Haber imponible") for x in (haberes_imponibles_extra or []) if float(x.get("monto") or 0)]
    noimp_extra = [dict(x, tipo="Haber no imponible") for x in (haberes_no_imponibles_extra or []) if float(x.get("monto") or 0)]
    desc_extra = [dict(x, tipo="Descuento") for x in (descuentos_extra or []) if float(x.get("monto") or 0)]
    detalle += imp_extra + noimp_extra + desc_extra
    aguinaldo = int(round(sum(float(x["monto"]) for x in imp_extra if x.get("codigo_lre") == 2110)))
    bonos_imp = int(round(sum(float(x["monto"]) for x in imp_extra))) - aguinaldo
    noimp = int(round(sum(float(x["monto"]) for x in noimp_extra)))
    otros_desc = int(round(sum(float(x["monto"]) for x in desc_extra)))

    # --- Gratificación ---
    tg = tipo_gratificacion or "Monto fijo pactado"
    if tg.startswith("Art. 50"):
        grat = gratificacion_art50(sueldo_calc + monto_he + otr + aguinaldo + bonos_imp, renta_minima)
    elif tg.startswith("Sin"):
        grat = 0
    else:
        grat = int(round((gratificacion or 0) * factor))

    total_imponible = sueldo_calc + grat + monto_he + otr + aguinaldo + bonos_imp

    # --- Situación previsional ---
    ed = C.edad(fecha_nacimiento, fin_mes)
    mayor_65 = ed is not None and ed >= 65
    menor_18 = ed is not None and ed < 18
    base_afp = min(total_imponible, tope_afp) if tope_afp else total_imponible
    base_afc = min(total_imponible, tope_afc) if tope_afc else total_imponible

    # --- Asignación familiar (tramo determinado por IPS según promedio del semestre anterior) ---
    cargas = max(0, int(numero_cargas or 0))
    if not tramo_af:
        tramo_af = determinar_tramo_asignacion(total_imponible, af_tramos)
        if cargas:
            adv.append("Tramo de asignación familiar estimado con el imponible del mes; "
                       "debe usarse el tramo asignado por IPS/CCAF (promedio del semestre anterior).")
    monto_carga = (af_tramos.get(tramo_af) or af_tramos.get("D") or {"monto": 0})["monto"]
    asignacion_familiar = int(round(monto_carga * cargas))

    # --- AFP trabajador ---
    tasa_afp = float(afp_tasas.get(afp_nombre, 0) or 0) / 100.0
    if cotiza_afp and not tasa_afp:
        adv.append(f"Sin tasa AFP para '{afp_nombre}' en los indicadores del periodo.")
    afp_monto = int(round(base_afp * tasa_afp)) if cotiza_afp else 0

    # --- Salud ---
    salud_7 = int(round(base_afp * 0.07))
    adicional_isapre = 0
    es_isapre = (salud_tipo or "").upper() == "ISAPRE"
    if es_isapre and isapre_pactado_uf and float(isapre_pactado_uf) > 0:
        adicional_isapre = max(0, int(round(float(isapre_pactado_uf) * uf)) - salud_7)
    salud_ccaf = int(round(base_afp * tasa_ccaf)) if (afiliado_ccaf and not es_isapre) else 0
    salud_fonasa = 0 if es_isapre else salud_7 - salud_ccaf

    # --- SIS y Ley 21.735 (no aplican a pensionados ni a mayores de 65) ---
    ref = tasas_reforma_ley_21735(periodo)
    exento_sis = bool(pensionado) or mayor_65
    if exento_sis:
        reforma_afp_emp = reforma_crp = reforma_seguro_social = sis_monto = 0
        if ref["aplica"] or sis_tasa:
            adv.append("Pensionado o mayor de 65 años: sin SIS ni cotización empleador Ley 21.735.")
    else:
        reforma_afp_emp = int(round(base_afp * ref["cci"])) if ref["aplica"] else 0
        reforma_crp = int(round(base_afp * ref["crp"])) if ref["aplica"] else 0
        reforma_seguro_social = int(round(base_afp * ref["seguro_social"])) if ref["aplica"] else 0
        # Desde ago-2026 el SIS está dentro del 2,5% del Seguro Social: no se registra aparte
        sis_monto = int(round(base_afp * sis_tasa)) if ref["sis_clasico"] else 0

    # --- Seguro de cesantía ---
    antig = _anios_entre(C.a_fecha(fecha_inicio_contrato), fin_mes)
    if pensionado or menor_18:
        afc_trab = afc_emp = 0
        adv.append("Exento de seguro de cesantía (pensionado o menor de 18 años).")
    elif _es_plazo(tipo_contrato):
        afc_trab = 0
        afc_emp = int(round(base_afc * C.AFC_PLAZO_EMP))
    else:
        afc_trab = int(round(base_afc * C.AFC_INDEF_TRAB))
        if antig > 11:
            afc_emp = int(round(base_afc * C.AFC_EMP_DESPUES_11))
            adv.append("Más de 11 años de relación laboral: el empleador aporta solo 0,8% al Fondo Solidario.")
        else:
            afc_emp = int(round(base_afc * C.AFC_INDEF_EMP))

    mutual_monto = int(round(base_afp * float(tasa_mutual or 0) / 100.0))

    # --- Impuesto único ---
    # Base = imponible − cotizaciones obligatorias del trabajador (AFP, salud 7%, AFC).
    # El adicional voluntario de Isapre no rebaja la base.
    base_tributable = max(0, total_imponible - afp_monto - salud_7 - afc_trab)
    iu = impuesto_unico(base_tributable, utm)

    total_haberes = total_imponible + mov + col + asignacion_familiar + noimp
    anticipo_monto = max(0, int(round(float(anticipo or 0))))
    total_imposiciones = afp_monto + salud_7 + adicional_isapre + afc_trab
    total_descuentos = total_imposiciones + iu + anticipo_monto + otros_desc
    liquido = total_haberes - total_descuentos

    # --- Validaciones legales ---
    jmax = C.jornada_maxima(fin_mes)
    if jornada > jmax:
        adv.append(f"Jornada pactada de {jornada} h supera la máxima legal de {jmax} h vigente al {C.fecha_ddmmaaaa(fin_mes)} (Ley 21.561).")
    if renta_minima and sueldo_base:
        minimo = renta_minima if jornada > 30 else renta_minima * jornada / jmax
        if float(sueldo_base) < minimo - 1:
            adv.append(f"Sueldo base ${C.fmt_clp(sueldo_base)} es inferior al ingreso mínimo "
                       f"{'proporcional ' if jornada <= 30 else ''}${C.fmt_clp(minimo)}.")
    if dias_licencia and dias + float(dias_licencia) > 30:
        adv.append(f"Días trabajados ({dias}) más días de licencia ({float(dias_licencia):g}) superan 30: revise el movimiento del mes.")
    if liquido < 0:
        adv.append("El líquido resulta negativo: revise anticipos y descuentos.")

    carga_empleador = reforma_afp_emp + reforma_crp + reforma_seguro_social + sis_monto + afc_emp + mutual_monto

    return {
        "sueldo_calculado": sueldo_calc, "gratificacion": grat, "movilizacion": mov, "colacion": col,
        "otros_haberes": otr, "horas_extras": horas_extras or 0, "monto_horas_extras": monto_he,
        "asignacion_familiar": asignacion_familiar, "tramo_asignacion": tramo_af,
        "total_haberes": total_haberes, "total_imponible": total_imponible,
        "afp_monto": afp_monto, "salud_monto": salud_7, "salud_fonasa": salud_fonasa, "salud_ccaf": salud_ccaf,
        "adicional_isapre": adicional_isapre, "sis_monto": sis_monto,
        "afc_trabajador": afc_trab, "afc_empleador": afc_emp, "mutual_monto": mutual_monto,
        "reforma_afp_emp": reforma_afp_emp, "reforma_crp": reforma_crp,
        "reforma_seguro_social": reforma_seguro_social,
        "aplica_reforma": ref["aplica"], "reforma_etapa": ref["etapa"], "reforma_descripcion": ref["descripcion"],
        "base_tributable": base_tributable, "impuesto_unico": iu,
        "anticipo": anticipo_monto, "otros_descuentos": otros_desc,
        "aguinaldo": aguinaldo, "bonos_imponibles": bonos_imp, "haberes_no_imponibles": noimp,
        "dias_licencia": float(dias_licencia or 0), "detalle": detalle,
        "total_imposiciones": total_imposiciones, "total_descuentos": total_descuentos, "liquido": liquido,
        "base_afp": base_afp, "base_afc": base_afc, "utm": utm, "uf": uf, "renta_minima": renta_minima,
        "carga_empleador_previsional": carga_empleador, "edad": ed, "jornada": jornada,
        "advertencias": adv,
    }


def numero_a_palabras(n) -> str:
    """Número entero a palabras en español (mayúsculas), hasta miles de millones."""
    try:
        n = int(round(float(n)))
    except Exception:
        return str(n)
    if n < 0:
        return "MENOS " + numero_a_palabras(-n)
    if n == 0:
        return "CERO"
    U = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
    ESP = {10: "DIEZ", 11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 15: "QUINCE",
           16: "DIECISEIS", 17: "DIECISIETE", 18: "DIECIOCHO", 19: "DIECINUEVE", 20: "VEINTE"}
    D = ["", "", "VEINTI", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    CEN = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS",
           "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]

    def _999(x):
        if x == 0:
            return ""
        if x == 100:
            return "CIEN"
        c, r = divmod(x, 100)
        partes = [CEN[c]] if c else []
        if r:
            if r in ESP:
                partes.append(ESP[r])
            elif r < 10:
                partes.append(U[r])
            else:
                d, u = divmod(r, 10)
                if d == 2:
                    partes.append("VEINTI" + U[u])
                else:
                    partes.append(D[d] + (" Y " + U[u] if u else ""))
        return " ".join(partes)

    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    out = []
    if millones:
        out.append("UN MILLÓN" if millones == 1 else f"{numero_a_palabras(millones)} MILLONES")
    if miles:
        out.append("MIL" if miles == 1 else f"{_999(miles)} MIL")
    if unidades:
        out.append(_999(unidades))
    return " ".join(out).strip()

"""
Archivo Previred — Formato Estándar Largo Variable por Separador (";"), 105 campos.
Fuente: Previred, "FormatoLargoVariablePorSeparador-Reforma", versión 82 (rige desde remuneraciones
de agosto 2025). Todos los campos van en cada línea; numéricos sin uso = 0 y alfanuméricos sin uso = vacío.

Punto a validar con el validador de Previred antes de la primera carga: el destino de la cotización
Ley 21.735 del 0,1% a cuenta individual (aquí se suma al campo 28) y el uso del campo 29 para el
Seguro Social desde agosto 2026. Están parametrizados en CAMPO_* abajo.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import config as C
from . import db

N_CAMPOS = 105
CCI_SUMA_EN_CAMPO_28 = True   # 0,1% empleador a cuenta individual AFP
CAMPO_SEGURO_SOCIAL = 29      # desde ago-2026, el 2,5% (incluye SIS)
CAMPO_EXPECTATIVA_VIDA = 94   # ago-2025 a jul-2026: 0,9%
CAMPO_RENTABILIDAD_PROTEGIDA = 95  # desde ago-2026: 0,9%

NUMERICOS = set(range(1, 106)) - {2, 3, 4, 5, 6, 11, 14, 16, 17, 18, 25, 37, 41, 46, 51, 52, 53, 54, 56, 57,
                                  76, 104, 105}


def _n(v) -> str:
    try:
        return str(max(0, int(round(float(v or 0)))))
    except (TypeError, ValueError):
        return "0"


def _txt(v, largo=30) -> str:
    s = C.normalizar(v)[:largo]
    return s.replace(";", " ")


def codigo_movimiento(contrato: dict, periodo: str) -> tuple[str, str, str]:
    """Código de movimiento de personal y fechas (Tabla N°7)."""
    ini_mes = date(int(periodo[:4]), int(periodo[5:7]), 1)
    fin_mes = C.fin_de_mes(periodo)
    fi = C.a_fecha(contrato.get("fecha_inicio"))
    ft = C.a_fecha(contrato.get("fecha_termino"))
    if ft and ini_mes <= ft <= fin_mes and not contrato.get("activo", 1):
        return "2", "", C.fecha_ddmmaaaa(ft)
    if fi and ini_mes <= fi <= fin_mes:
        cod = "7" if (contrato.get("tipo_contrato") in C.CONTRATOS_PLAZO) else "1"
        return cod, C.fecha_ddmmaaaa(fi), C.fecha_ddmmaaaa(ft) if (cod == "7" and ft) else ""
    return "0", "", ""


def linea_previred(liq: dict, trab: dict, contrato: dict, empresa: dict, periodo: str) -> list[str]:
    f = {i: ("0" if i in NUMERICOS else "") for i in range(1, N_CAMPOS + 1)}
    num, dv = C.rut_partes(trab.get("rut"))
    ref_etapa = liq.get("reforma_etapa")
    fin_mes = C.fin_de_mes(periodo)
    ed = C.edad(trab.get("fecha_nacimiento"), fin_mes)
    es_isapre = C.normalizar(trab.get("salud")) == "ISAPRE"
    cotiza_afp = bool(trab.get("cotiza_afp", 1))
    pensionado = bool(trab.get("pensionado"))
    if pensionado:
        tipo_trab = "1" if cotiza_afp else "2"
    elif ed is not None and ed >= 65:
        tipo_trab = "3"
    else:
        tipo_trab = "0"
    mov, fdesde, fhasta = codigo_movimiento(contrato, periodo)
    jornada = int(contrato.get("jornada_semanal") or C.JORNADA_DEFAULT)
    ccaf = C.PREVIRED_CCAF.get(C.normalizar(empresa.get("caja_compensacion")), "00")
    mutual = C.PREVIRED_MUTUAL.get(C.normalizar(empresa.get("mutual")), "01")
    base_afp = min(float(liq.get("total_imponible") or 0), float(liq.get("_tope_afp") or 1e18))
    base_afc = min(float(liq.get("total_imponible") or 0), float(liq.get("_tope_afc") or 1e18))
    af = liq.get("asignacion_familiar") or 0
    periodo_mmaaaa = periodo[5:7] + periodo[:4]

    f.update({
        1: num, 2: dv, 3: _txt(trab.get("apellido_paterno")), 4: _txt(trab.get("apellido_materno")),
        5: _txt(trab.get("nombres")), 6: (trab.get("sexo") or "M")[:1].upper(),
        7: "0" if C.normalizar(trab.get("nacionalidad") or "CHILENA").startswith("CHILE") else "1",
        8: "01", 9: periodo_mmaaaa, 10: "0", 11: "AFP" if cotiza_afp else "SIP", 12: tipo_trab,
        13: _n(liq.get("dias_trabajados") or 30), 14: "00", 15: mov, 16: fdesde, 17: fhasta,
        18: (liq.get("tramo_asignacion") or trab.get("tramo_asignacion_familiar") or "D")[:1],
        19: _n(trab.get("numero_cargas")), 22: _n(af), 25: "N",
        26: C.PREVIRED_AFP.get(trab.get("afp"), "00") if cotiza_afp else "00",
        27: _n(base_afp) if cotiza_afp else "0",
        28: _n(float(liq.get("afp_monto") or 0) + (float(liq.get("reforma_afp_emp") or 0) if CCI_SUMA_EN_CAMPO_28 else 0)),
        29: _n(liq.get("sis_monto")),
        64: _n(base_afp) if not es_isapre else "0",
        70: _n(liq.get("salud_fonasa")) if not es_isapre else "0",
        75: C.PREVIRED_SALUD.get(C.normalizar(trab.get("isapre")), "00") if es_isapre else "07",
        77: _n(base_afp) if es_isapre else "0",
        78: "1",
        79: _n(float(liq.get("salud_monto") or 0) + float(liq.get("adicional_isapre") or 0)) if es_isapre else "0",
        80: _n(liq.get("salud_monto")) if es_isapre else "0",
        81: _n(liq.get("adicional_isapre")) if es_isapre else "0",
        83: ccaf, 84: _n(base_afp) if ccaf != "00" else "0",
        90: _n(liq.get("salud_ccaf")),
        93: "2" if jornada <= 30 else "1",
        96: mutual, 97: _n(base_afp) if mutual != "00" else "0",
        98: _n(liq.get("mutual_monto")) if mutual != "00" else "0",
        99: _n(empresa.get("sucursal_mutual") or 0),
        100: _n(base_afc) if (float(liq.get("afc_trabajador") or 0) + float(liq.get("afc_empleador") or 0)) else "0",
        101: _n(liq.get("afc_trabajador")), 102: _n(liq.get("afc_empleador")),
        105: _txt(empresa.get("centro_costo"), 20),
    })
    if mutual == "00":  # ISL
        f[71] = _n(liq.get("mutual_monto"))
    if af:
        if ccaf != "00":
            f[91] = _n(af)
        else:
            f[73] = _n(af)
    # Ley 21.735
    if ref_etapa == "1pct":
        f[CAMPO_EXPECTATIVA_VIDA] = _n(liq.get("reforma_crp"))
    elif ref_etapa in ("3.5pct", "4.25pct", "posterior"):
        f[CAMPO_SEGURO_SOCIAL] = _n(float(liq.get("reforma_seguro_social") or 0) + float(liq.get("sis_monto") or 0))
        f[CAMPO_RENTABILIDAD_PROTEGIDA] = _n(liq.get("reforma_crp"))
    return [f[i] for i in range(1, N_CAMPOS + 1)]


def generar_previred_txt(empresa_id, periodo, ruta) -> dict:
    """Devuelve {'ruta': str|None, 'lineas': n, 'errores': [..]}."""
    from .calculos import tasas_reforma_ley_21735
    conn = db.get_conn()
    try:
        emp = db.row(conn, "SELECT * FROM empresas WHERE id=?", (empresa_id,))
        liqs = db.rows(conn, """
            SELECT l.*, c.fecha_inicio, c.fecha_termino, c.tipo_contrato, c.jornada_semanal, c.activo AS contrato_activo
            FROM liquidaciones l LEFT JOIN contratos c ON l.contrato_id = c.id
            WHERE l.empresa_id = ? AND l.periodo = ?""", (empresa_id, periodo))
        trabs = {t["id"]: t for t in db.rows(conn, "SELECT * FROM trabajadores WHERE empresa_id=?", (empresa_id,))}
        ind = db.get_indicadores(periodo, conn) or {}
    finally:
        conn.close()
    errores, lineas = [], []
    if not emp:
        return {"ruta": None, "lineas": 0, "errores": ["Empresa no encontrada."]}
    etapa = tasas_reforma_ley_21735(periodo)["etapa"]
    for liq in liqs:
        t = trabs.get(liq["trabajador_id"]) or {}
        nombre = f"{t.get('nombres', '')} {t.get('apellido_paterno', '')}".strip()
        if not C.rut_valido(t.get("rut") or ""):
            errores.append(f"{nombre}: RUT inválido ({t.get('rut') or 'vacío'}).")
            continue
        for campo, etiqueta in (("apellido_paterno", "apellido paterno"), ("nombres", "nombres")):
            if len(C.normalizar(t.get(campo))) < 2:
                errores.append(f"{nombre or t.get('rut')}: falta {etiqueta}.")
        if not t.get("apellido_materno"):
            errores.append(f"{nombre}: falta apellido materno (Previred exige al menos 2 letras).")
        liq = dict(liq, reforma_etapa=etapa, _tope_afp=ind.get("tope_afp"), _tope_afc=ind.get("tope_afc"))
        contrato = {"fecha_inicio": liq.get("fecha_inicio"), "fecha_termino": liq.get("fecha_termino"),
                    "tipo_contrato": liq.get("tipo_contrato"), "jornada_semanal": liq.get("jornada_semanal"),
                    "activo": liq.get("contrato_activo", 1)}
        lineas.append(";".join(linea_previred(liq, t, contrato, emp, periodo)))
    if not lineas:
        return {"ruta": None, "lineas": 0, "errores": errores or ["No hay liquidaciones para el periodo."]}
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="latin-1", errors="replace", newline="\r\n") as fh:
        fh.write("\n".join(lineas) + "\n")
    return {"ruta": str(ruta), "lineas": len(lineas), "errores": errores}

"""Procesos que combinan cálculo y base de datos (sin interfaz)."""
from __future__ import annotations

import json

from . import calculos as K
from . import db

CAMPOS_MOV = ["dias_trabajados", "ausencias", "licencia", "licencia_desde", "licencia_hasta", "dias_vacaciones",
              "anticipo", "aguinaldo", "bono_desempeno", "cant_he_50", "valor_he_50", "cant_he_100", "valor_he_100",
              "cant_hd", "valor_hd", "cant_hed", "valor_hed", "colacion", "movilizacion", "observacion"]


def conceptos_empresa(conn, empresa_id, solo_activos=True) -> list[dict]:
    sql = "SELECT * FROM conceptos WHERE empresa_id=?" + (" AND activo=1" if solo_activos else "") + " ORDER BY orden, id"
    return db.rows(conn, sql, (empresa_id,))


def movimientos_periodo(conn, empresa_id, periodo) -> dict[int, dict]:
    out = {}
    for m in db.rows(conn, "SELECT * FROM movimientos WHERE empresa_id=? AND periodo=?", (empresa_id, periodo)):
        m["extras"] = json.loads(m.get("extras") or "{}")
        out[m["trabajador_id"]] = m
    return out


def estado_periodo(conn, empresa_id, periodo) -> dict:
    p = db.row(conn, "SELECT * FROM periodos_rrhh WHERE empresa_id=? AND periodo=?", (empresa_id, periodo))
    return p or {"empresa_id": empresa_id, "periodo": periodo, "estado": "Abierto"}


def guardar_estado_periodo(conn, empresa_id, periodo, estado, usuario=""):
    from datetime import datetime
    db.upsert(conn, "periodos_rrhh", dict(empresa_id=empresa_id, periodo=periodo, estado=estado,
                                          enviado_por=usuario, enviado_at=datetime.now()), ["empresa_id", "periodo"])


def guardar_movimiento(conn, empresa_id, trabajador_id, periodo, valores: dict, extras: dict, usuario=""):
    from datetime import datetime
    d = {k: valores.get(k) for k in CAMPOS_MOV if k in valores}
    d.update(empresa_id=empresa_id, trabajador_id=trabajador_id, periodo=periodo,
             extras=json.dumps({str(k): v for k, v in (extras or {}).items() if v}),
             updated_by=usuario, updated_at=datetime.now())
    db.upsert(conn, "movimientos", d, ["empresa_id", "trabajador_id", "periodo"])


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def entradas_desde_movimiento(mov: dict | None, conceptos: list[dict], contrato: dict, dias_default=30) -> dict:
    """Traduce el movimiento del mes a los parámetros de calcular_liquidacion."""
    if not mov:
        return {"dias": dias_default}
    dias = mov.get("dias_trabajados")
    if dias is None:
        dias = max(0.0, 30 - _n(mov.get("ausencias")) - _n(mov.get("licencia")))
    imp, noimp, desc = [], [], []
    if _n(mov.get("aguinaldo")):
        imp.append({"nombre": "Aguinaldo", "monto": _n(mov["aguinaldo"]), "codigo_lre": 2110})
    if _n(mov.get("bono_desempeno")):
        imp.append({"nombre": "Bono desempeño", "monto": _n(mov["bono_desempeno"]), "codigo_lre": 2113})
    por_id = {str(c["id"]): c for c in conceptos}
    for cid, monto in (mov.get("extras") or {}).items():
        c = por_id.get(str(cid))
        if not c or not _n(monto):
            continue
        item = {"nombre": c["nombre"], "monto": _n(monto), "codigo_lre": c.get("codigo_lre")}
        {"Haber imponible": imp, "Haber no imponible": noimp, "Descuento": desc}.get(c.get("tipo"), imp).append(item)
    he = {k: (mov.get(f"cant_{k}"), mov.get(f"valor_{k}")) for k in ("he_50", "he_100", "hd", "hed")}
    out = {"dias": dias, "he_detalle": he, "haberes_imponibles_extra": imp, "haberes_no_imponibles_extra": noimp,
           "descuentos_extra": desc, "anticipo": _n(mov.get("anticipo")), "dias_licencia": _n(mov.get("licencia"))}
    # Colación y movilización del mes reemplazan a las del contrato solo si se informan
    if _n(mov.get("colacion")):
        out["colacion_mes"] = _n(mov["colacion"])
    if _n(mov.get("movilizacion")):
        out["movilizacion_mes"] = _n(mov["movilizacion"])
    return out


def calcular_periodo(conn, emp, periodo, ind, dias_default=30, he_inp=None, ant_inp=None, dias_inp=None,
                     usar_movimientos=True):
    """
    Calcula y guarda las liquidaciones de todos los contratos activos de la empresa.
    Si existen movimientos del mes (módulo RRHH), se usan; los valores ingresados a mano en la pantalla
    de liquidaciones (he_inp, ant_inp, dias_inp) solo se aplican a trabajadores sin movimiento registrado.
    """
    he_inp, ant_inp, dias_inp = he_inp or {}, ant_inp or {}, dias_inp or {}
    contratos = db.rows(conn, """
        SELECT c.*, t.id AS tid, t.afp, t.salud, t.pactado_salud_uf, t.numero_cargas, t.tramo_asignacion_familiar,
               t.pensionado, t.cotiza_afp, t.fecha_nacimiento
        FROM contratos c JOIN trabajadores t ON c.trabajador_id = t.id
        WHERE c.empresa_id = ? AND c.activo = 1""", (emp["id"],))
    movs = movimientos_periodo(conn, emp["id"], periodo) if usar_movimientos else {}
    conceptos = conceptos_empresa(conn, emp["id"], solo_activos=False) if movs else []
    avisos = {}
    for c in contratos:
        mov = movs.get(c["tid"])
        if mov:
            e = entradas_desde_movimiento(mov, conceptos, c, dias_default)
        else:
            e = {"dias": dias_inp.get(c["tid"], dias_default), "anticipo": ant_inp.get(c["tid"], 0),
                 "horas_extras": he_inp.get(c["tid"], 0)}
        del_mes = "colacion_mes" in e or "movilizacion_mes" in e
        prop = float(e["dias"]) / 30.0 if del_mes else 1.0  # el concepto no informado se prorratea igual
        movil = e.get("movilizacion_mes", _n(c.get("movilizacion")) * prop)
        colac = e.get("colacion_mes", _n(c.get("colacion")) * prop)
        calc = K.calcular_liquidacion(
            c["sueldo_base"], c.get("gratificacion") or 0, movil, colac,
            c.get("otros_haberes") or 0, e["dias"], c["afp"], c["salud"],
            c.get("pactado_salud_uf") or 0, c["tipo_contrato"], emp.get("tasa_mutual") or 0, ind,
            horas_extras=e.get("horas_extras", 0), jornada_semanal=c.get("jornada_semanal"),
            numero_cargas=c.get("numero_cargas") or 0, tramo_af=c.get("tramo_asignacion_familiar") or None,
            periodo=periodo, anticipo=e.get("anticipo", 0),
            tipo_gratificacion=c.get("tipo_gratificacion") or "Monto fijo pactado",
            afiliado_ccaf=bool(emp.get("caja_compensacion")), pensionado=bool(c.get("pensionado")),
            cotiza_afp=bool(c.get("cotiza_afp", 1)), fecha_nacimiento=c.get("fecha_nacimiento"),
            fecha_inicio_contrato=c.get("fecha_inicio"), he_detalle=e.get("he_detalle"),
            haberes_imponibles_extra=e.get("haberes_imponibles_extra"),
            haberes_no_imponibles_extra=e.get("haberes_no_imponibles_extra"),
            descuentos_extra=e.get("descuentos_extra"), dias_licencia=e.get("dias_licencia", 0),
            asignaciones_del_mes=del_mes)
        campos = ["horas_extras", "monto_horas_extras", "sueldo_calculado", "gratificacion",
                  "movilizacion", "colacion", "asignacion_familiar", "otros_haberes", "total_haberes", "total_imponible",
                  "afp_monto", "salud_monto", "salud_fonasa", "salud_ccaf", "adicional_isapre", "sis_monto",
                  "afc_trabajador", "afc_empleador", "mutual_monto", "reforma_afp_emp", "reforma_crp",
                  "reforma_seguro_social", "base_tributable", "impuesto_unico", "anticipo", "total_descuentos",
                  "liquido", "tramo_asignacion", "aguinaldo", "bonos_imponibles", "haberes_no_imponibles",
                  "otros_descuentos", "dias_licencia"]
        data = {k: calc.get(k) for k in campos}
        data.update(empresa_id=emp["id"], trabajador_id=c["tid"], contrato_id=c["id"], periodo=periodo,
                    dias_trabajados=e["dias"], sueldo_base=c["sueldo_base"],
                    dias_vacaciones=_n((mov or {}).get("dias_vacaciones")),
                    detalle=json.dumps(calc["detalle"], ensure_ascii=False),
                    advertencias=json.dumps(calc["advertencias"], ensure_ascii=False))
        db.upsert(conn, "liquidaciones", data, ["empresa_id", "trabajador_id", "periodo"])
        if calc["advertencias"]:
            avisos[c["tid"]] = calc["advertencias"]
    conn.commit()
    return len(contratos), avisos

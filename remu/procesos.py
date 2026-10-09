"""Procesos que combinan cálculo y base de datos (sin interfaz)."""
from __future__ import annotations

import json

from . import calculos as K
from . import config as C
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
               t.pensionado, t.cotiza_afp, t.afp_voluntaria_pensionado, t.fecha_nacimiento
        FROM contratos c JOIN trabajadores t ON c.trabajador_id = t.id
        WHERE c.empresa_id = ? AND c.activo = 1""", (emp["id"],))
    movs = movimientos_periodo(conn, emp["id"], periodo) if usar_movimientos else {}
    conceptos = conceptos_empresa(conn, emp["id"], solo_activos=False) if movs else []
    avisos = {}

    # [v5] Cuotas de prestamos del periodo (incluye p.num_cuotas para el detalle)
    cuotas_prest = db.rows(conn, """
        SELECT c.*, p.tipo, p.descripcion, p.trabajador_id, p.id AS prestamo_id, p.num_cuotas
        FROM prestamos_cuotas c
        JOIN prestamos p ON c.prestamo_id = p.id
        WHERE p.empresa_id = ? AND c.periodo = ? AND p.activo = 1 AND c.estado = 'pendiente'
    """, (emp["id"], periodo))

    for c in contratos:
        mov = movs.get(c["tid"])
        if mov:
            e = entradas_desde_movimiento(mov, conceptos, c, dias_default)
        else:
            e = {"dias": dias_inp.get(c["tid"], dias_default), "anticipo": ant_inp.get(c["tid"], 0),
                 "horas_extras": he_inp.get(c["tid"], 0)}
        del_mes = "colacion_mes" in e or "movilizacion_mes" in e
        prop = float(e["dias"]) / 30.0 if del_mes else 1.0
        movil = e.get("movilizacion_mes", _n(c.get("movilizacion")) * prop)
        colac = e.get("colacion_mes", _n(c.get("colacion")) * prop)

        # [v5] Sumar cuotas del prestamo a descuentos_extra
        # Un unico item por cuota (sin duplicar en detalle)
        desc_ext_actual = list(e.get("descuentos_extra") or [])
        prest_empresa_total = 0.0
        prest_ccaf_total = 0.0
        for cp in cuotas_prest:
            if cp["trabajador_id"] == c["tid"]:
                monto_cp = float(cp["monto"])
                num_cuo = cp.get("numero_cuota", "")
                num_tot = cp.get("num_cuotas", "")
                nombre_completo = f"Cuota prestamo {cp['tipo']} {num_cuo}/{num_tot}".strip()
                if cp.get("descripcion"):
                    nombre_completo += f" - {cp['descripcion']}"
                desc_ext_actual.append({
                    "nombre": nombre_completo,
                    "monto": monto_cp,
                    "codigo_lre": 3188,
                    "tipo": "Descuento",
                })
                if cp["tipo"] == "Empresa":
                    prest_empresa_total += monto_cp
                elif cp["tipo"] == "CCAF":
                    prest_ccaf_total += monto_cp

        calc = K.calcular_liquidacion(
            c["sueldo_base"], c.get("gratificacion") or 0, movil, colac,
            c.get("otros_haberes") or 0, e["dias"], c["afp"], c["salud"],
            c.get("pactado_salud_uf") or 0, c["tipo_contrato"], emp.get("tasa_mutual") or 0, ind,
            horas_extras=e.get("horas_extras", 0), jornada_semanal=c.get("jornada_semanal"),
            numero_cargas=c.get("numero_cargas") or 0, tramo_af=c.get("tramo_asignacion_familiar") or None,
            periodo=periodo, anticipo=e.get("anticipo", 0),
            tipo_gratificacion=c.get("tipo_gratificacion") or "Monto fijo pactado",
            afiliado_ccaf=bool(emp.get("caja_compensacion")), pensionado=bool(c.get("pensionado")),
            cotiza_afp=C.cotiza_afp_efectivo(c), fecha_nacimiento=c.get("fecha_nacimiento"),
            fecha_inicio_contrato=c.get("fecha_inicio"), he_detalle=e.get("he_detalle"),
            haberes_imponibles_extra=e.get("haberes_imponibles_extra"),
            haberes_no_imponibles_extra=e.get("haberes_no_imponibles_extra"),
            descuentos_extra=desc_ext_actual, dias_licencia=e.get("dias_licencia", 0),
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
                    advertencias=json.dumps(calc["advertencias"], ensure_ascii=False),
                    prestamo_empresa=prest_empresa_total,
                    prestamo_ccaf=prest_ccaf_total)
        db.upsert(conn, "liquidaciones", data, ["empresa_id", "trabajador_id", "periodo"])
        if calc["advertencias"]:
            avisos[c["tid"]] = calc["advertencias"]
    conn.commit()

    # [v3] Marcar las cuotas de prestamos como pagadas (ya se descontaron)
    for cp in cuotas_prest:
        marcar_cuota_pagada(conn, cp["id"])
    conn.commit()

    return len(contratos), avisos


# ═══════════════════════════════════════════════════════════════════
# PRÉSTAMOS (Empresa / CCAF)
# ═══════════════════════════════════════════════════════════════════


def crear_prestamo(conn, empresa_id, trabajador_id, tipo, descripcion,
                   monto_total, cuota_mensual, num_cuotas,
                   fecha_inicio, fecha_otorgado=None, usuario="") -> int:
    """Crea un préstamo y genera N cuotas automáticamente."""
    saldo = float(cuota_mensual) * int(num_cuotas) if tipo == "Empresa" else None

    prestamo_id = db.insert(conn, "prestamos", {
        "empresa_id": empresa_id,
        "trabajador_id": trabajador_id,
        "tipo": tipo,
        "descripcion": descripcion or "",
        "monto_total": monto_total,
        "cuota_mensual": cuota_mensual,
        "num_cuotas": num_cuotas,
        "cuota_actual": 1,
        "saldo_pendiente": saldo,
        "fecha_inicio": fecha_inicio,
        "fecha_otorgado": fecha_otorgado,
        "activo": 1,
    })

    year, month = int(fecha_inicio[:4]), int(fecha_inicio[5:7])
    for i in range(1, int(num_cuotas) + 1):
        periodo = f"{year:04d}-{month:02d}"
        db.insert(conn, "prestamos_cuotas", {
            "prestamo_id": prestamo_id,
            "numero_cuota": i,
            "periodo": periodo,
            "monto": cuota_mensual,
            "estado": "pendiente",
        })
        month += 1
        if month > 12:
            month = 1
            year += 1

    conn.commit()
    return prestamo_id


def listar_prestamos(conn, empresa_id, solo_activos=True) -> list:
    """Lista préstamos con info del trabajador."""
    sql = """SELECT p.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno
             FROM prestamos p
             JOIN trabajadores t ON p.trabajador_id = t.id
             WHERE p.empresa_id = ?"""
    if solo_activos:
        sql += " AND p.activo = 1"
    sql += " ORDER BY p.created_at DESC"
    return db.rows(conn, sql, (empresa_id,))


def cuotas_del_periodo(conn, empresa_id, periodo) -> dict:
    """Cuotas pendientes del período, agrupadas por trabajador_id."""
    sql = """SELECT c.*, p.tipo, p.descripcion, p.trabajador_id, p.num_cuotas
             FROM prestamos_cuotas c
             JOIN prestamos p ON c.prestamo_id = p.id
             WHERE p.empresa_id = ? AND c.periodo = ? AND p.activo = 1
                   AND c.estado = 'pendiente'
             ORDER BY p.trabajador_id, c.numero_cuota"""
    cuotas = db.rows(conn, sql, (empresa_id, periodo))
    out = {}
    for c in cuotas:
        out.setdefault(c["trabajador_id"], []).append(c)
    return out


def pausar_cuota(conn, cuota_id) -> None:
    """Marca una cuota como 'pausada'."""
    conn.execute("UPDATE prestamos_cuotas SET estado = 'pausada' WHERE id = ?", (cuota_id,))
    conn.commit()


def marcar_cuota_pagada(conn, cuota_id, fecha=None) -> None:
    """Marca como 'pagada' y actualiza saldo del préstamo."""
    from datetime import date as _date
    fecha = fecha or _date.today()
    cuota = db.row(conn, "SELECT * FROM prestamos_cuotas WHERE id = ?", (cuota_id,))
    if not cuota:
        return
    conn.execute("UPDATE prestamos_cuotas SET estado = 'pagada', fecha_pago = ? WHERE id = ?",
                 (fecha, cuota_id))
    prestamo = db.row(conn, "SELECT * FROM prestamos WHERE id = ?", (cuota["prestamo_id"],))
    if prestamo:
        nuevo_saldo = None
        if prestamo.get("saldo_pendiente") is not None:
            nuevo_saldo = max(0.0, float(prestamo["saldo_pendiente"]) - float(cuota["monto"]))
        nueva_cuota = int(prestamo["cuota_actual"]) + 1
        activo = 1 if nueva_cuota <= int(prestamo["num_cuotas"]) else 0
        conn.execute("""UPDATE prestamos
                        SET saldo_pendiente = ?, cuota_actual = ?, activo = ?
                        WHERE id = ?""",
                     (nuevo_saldo, nueva_cuota, activo, prestamo["id"]))
    conn.commit()


def prestamos_de_trabajador(conn, trabajador_id) -> list:
    """Todos los préstamos de un trabajador."""
    return db.rows(conn, """SELECT * FROM prestamos
                            WHERE trabajador_id = ?
                            ORDER BY created_at DESC""", (trabajador_id,))


def saldo_prestamo(conn, prestamo_id) -> float:
    """Calcula el saldo pendiente de un préstamo."""
    p = db.row(conn, "SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))
    if not p:
        return 0.0
    if p.get("saldo_pendiente") is not None:
        return float(p["saldo_pendiente"])
    pendientes = db.rows(conn, """SELECT SUM(monto) AS total
                                   FROM prestamos_cuotas
                                   WHERE prestamo_id = ? AND estado = 'pendiente'""",
                         (prestamo_id,))
    return float(pendientes[0]["total"] or 0) if pendientes else 0.0
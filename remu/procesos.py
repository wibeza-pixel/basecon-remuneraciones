"""Procesos que combinan cálculo y base de datos (sin interfaz)."""
import json

from . import calculos as K
from . import db


def calcular_periodo(conn, emp, periodo, ind, dias_default=30, he_inp=None, ant_inp=None, dias_inp=None):
    """Calcula y guarda las liquidaciones de todos los contratos activos de la empresa."""
    he_inp, ant_inp, dias_inp = he_inp or {}, ant_inp or {}, dias_inp or {}
    contratos = db.rows(conn, """
        SELECT c.*, t.id AS tid, t.afp, t.salud, t.pactado_salud_uf, t.numero_cargas, t.tramo_asignacion_familiar,
               t.pensionado, t.cotiza_afp, t.fecha_nacimiento
        FROM contratos c JOIN trabajadores t ON c.trabajador_id = t.id
        WHERE c.empresa_id = ? AND c.activo = 1""", (emp["id"],))
    avisos = {}
    for c in contratos:
        calc = K.calcular_liquidacion(
            c["sueldo_base"], c.get("gratificacion") or 0, c.get("movilizacion") or 0, c.get("colacion") or 0,
            c.get("otros_haberes") or 0, dias_inp.get(c["tid"], dias_default), c["afp"], c["salud"],
            c.get("pactado_salud_uf") or 0, c["tipo_contrato"], emp.get("tasa_mutual") or 0, ind,
            horas_extras=he_inp.get(c["tid"], 0), jornada_semanal=c.get("jornada_semanal"),
            numero_cargas=c.get("numero_cargas") or 0, tramo_af=c.get("tramo_asignacion_familiar") or None,
            periodo=periodo, anticipo=ant_inp.get(c["tid"], 0),
            tipo_gratificacion=c.get("tipo_gratificacion") or "Monto fijo pactado",
            afiliado_ccaf=bool(emp.get("caja_compensacion")), pensionado=bool(c.get("pensionado")),
            cotiza_afp=bool(c.get("cotiza_afp", 1)), fecha_nacimiento=c.get("fecha_nacimiento"),
            fecha_inicio_contrato=c.get("fecha_inicio"))
        campos = ["dias_trabajados", "horas_extras", "monto_horas_extras", "sueldo_calculado", "gratificacion",
                  "movilizacion", "colacion", "asignacion_familiar", "otros_haberes", "total_haberes", "total_imponible",
                  "afp_monto", "salud_monto", "salud_fonasa", "salud_ccaf", "adicional_isapre", "sis_monto",
                  "afc_trabajador", "afc_empleador", "mutual_monto", "reforma_afp_emp", "reforma_crp",
                  "reforma_seguro_social", "base_tributable", "impuesto_unico", "anticipo", "total_descuentos",
                  "liquido", "tramo_asignacion"]
        data = {k: calc.get(k) for k in campos}
        data["dias_trabajados"] = dias_inp.get(c["tid"], dias_default)
        data.update(empresa_id=emp["id"], trabajador_id=c["tid"], contrato_id=c["id"], periodo=periodo,
                    sueldo_base=c["sueldo_base"], advertencias=json.dumps(calc["advertencias"], ensure_ascii=False))
        db.upsert(conn, "liquidaciones", data, ["empresa_id", "trabajador_id", "periodo"])
        if calc["advertencias"]:
            avisos[c["tid"]] = calc["advertencias"]
    conn.commit()
    return len(contratos), avisos

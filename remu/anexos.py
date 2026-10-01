"""
Anexos de contrato: genera el documento, lo guarda en el historial del trabajador y (opcionalmente)
actualiza el contrato para que las liquidaciones siguientes usen las nuevas condiciones.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import archivo as A
from . import config as C
from . import db
from . import documentos as D


def validar(contrato: dict, cambios: dict, renta_minima: float = 0, renovaciones_previas: int = 0) -> tuple[list, list]:
    """Devuelve (errores, avisos)."""
    errores, avisos = [], []
    jmax = C.jornada_maxima(date.today())
    if not any(v not in (None, "") for k, v in cambios.items() if k != "horario"):
        errores.append("Indique al menos un cambio.")
    if cambios.get("jornada_semanal") and int(cambios["jornada_semanal"]) > jmax:
        errores.append(f"La jornada supera la máxima legal vigente ({jmax} h, Ley 21.561).")
    sueldo = cambios.get("sueldo_base")
    jornada = int(cambios.get("jornada_semanal") or contrato.get("jornada_semanal") or jmax)
    if sueldo is not None and renta_minima:
        minimo = renta_minima if jornada > 30 else renta_minima * jornada / jmax
        if float(sueldo) < minimo:
            errores.append(f"El sueldo base es inferior al ingreso mínimo (${C.fmt_clp(minimo)}).")
    if sueldo is not None and float(sueldo) < float(contrato.get("sueldo_base") or 0):
        avisos.append("El nuevo sueldo es menor que el actual: una rebaja requiere acuerdo expreso del trabajador.")
    dur = cambios.get("duracion")
    if dur and dur != "indefinido":
        if contrato.get("tipo_contrato") != "Plazo Fijo":
            errores.append("Solo un contrato a plazo fijo se puede prorrogar.")
        elif renovaciones_previas >= 1:
            avisos.append("Segunda renovación de un contrato a plazo fijo: por ley (art. 159 N°4) el contrato pasa a ser "
                          "de duración indefinida. Considere elegir «Pasa a indefinido».")
        if C.a_fecha(dur) and C.a_fecha(contrato.get("fecha_termino")) and C.a_fecha(dur) <= C.a_fecha(contrato["fecha_termino"]):
            errores.append("La nueva fecha de término debe ser posterior a la actual.")
    return errores, avisos


def renovaciones(conn, contrato_id: int) -> int:
    n = 0
    for a in db.rows(conn, "SELECT cambios FROM anexos_contrato WHERE contrato_id=?", (contrato_id,)):
        try:
            d = json.loads(a["cambios"] or "{}").get("duracion")
        except Exception:
            d = None
        if d and d != "indefinido":
            n += 1
    return n


def crear_anexo(conn, empresa: dict, trabajador: dict, contrato: dict, fecha, vigencia, cambios: dict,
                exports_dir, usuario: str = "", aplicar: bool = True) -> dict:
    """Genera el anexo, lo registra, lo guarda en el historial y actualiza el contrato si aplicar=True."""
    cambios = {k: v for k, v in cambios.items() if v not in (None, "")}
    if cambios.get("duracion") and cambios["duracion"] != "indefinido":
        cambios["duracion"] = str(C.a_fecha(cambios["duracion"]))
    ruta = Path(exports_dir) / f"anexo_{C.rut_partes(trabajador['rut'])[0]}_{C.a_fecha(fecha):%Y%m%d}.docx"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    D.generar_anexo_docx(empresa, trabajador, contrato, {"fecha": fecha, "vigencia": vigencia, "cambios": cambios}, str(ruta))
    anexo_id = db.insert(conn, "anexos_contrato", dict(
        contrato_id=contrato["id"], empresa_id=empresa["id"], trabajador_id=trabajador["id"], fecha=C.a_fecha(fecha),
        vigencia=C.a_fecha(vigencia), cambios=json.dumps(cambios, ensure_ascii=False), creado_por=usuario))
    resumen = ", ".join(_resumen(cambios))
    doc_id = A.guardar_archivo(conn, empresa["id"], trabajador["id"], "Anexo de contrato", ruta, fecha=fecha,
                               descripcion=resumen, ref_tabla="anexos_contrato", ref_id=anexo_id, usuario=usuario)
    conn.execute("UPDATE anexos_contrato SET documento_id=? WHERE id=?", (doc_id, anexo_id))
    if aplicar:
        upd = {k: cambios[k] for k in ("sueldo_base", "cargo", "jornada_semanal", "horario", "colacion", "movilizacion",
                                       "lugar_trabajo") if k in cambios}
        if cambios.get("duracion") == "indefinido":
            upd.update(tipo_contrato="Indefinido", fecha_termino=None)
        elif cambios.get("duracion"):
            upd["fecha_termino"] = C.a_fecha(cambios["duracion"])
        if upd:
            sets = ", ".join(f"{k}=?" for k in upd)
            conn.execute(f"UPDATE contratos SET {sets} WHERE id=?", [*upd.values(), contrato["id"]])
        if cambios.get("cargo"):
            conn.execute("UPDATE trabajadores SET cargo=? WHERE id=?", (cambios["cargo"], trabajador["id"]))
    conn.commit()
    return {"anexo_id": anexo_id, "documento_id": doc_id, "ruta": str(ruta), "resumen": resumen}


def _resumen(cb: dict) -> list[str]:
    out = []
    if "sueldo_base" in cb:
        out.append(f"sueldo ${C.fmt_clp(cb['sueldo_base'])}")
    if "cargo" in cb:
        out.append(f"cargo {cb['cargo']}")
    if "jornada_semanal" in cb:
        out.append(f"jornada {cb['jornada_semanal']} h")
    if "colacion" in cb:
        out.append(f"colación ${C.fmt_clp(cb['colacion'])}")
    if "movilizacion" in cb:
        out.append(f"movilización ${C.fmt_clp(cb['movilizacion'])}")
    if "lugar_trabajo" in cb:
        out.append("lugar de trabajo")
    if cb.get("duracion") == "indefinido":
        out.append("pasa a indefinido")
    elif cb.get("duracion"):
        out.append(f"prórroga al {C.fecha_ddmmaaaa(cb['duracion'])}")
    if cb.get("texto_libre"):
        out.append("cláusula adicional")
    return out

"""
Pantallas del módulo RRHH (movimientos del mes) — reemplaza a la app Control RRHH.
Se importa desde app.py; recibe las utilidades de interfaz por parámetro para no duplicar código.
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from remu import config as C
from remu import db
from remu import procesos as PR

COLUMNAS = [  # (campo, etiqueta, tipo)
    ("dias_trabajados", "Días trab.", "num"), ("ausencias", "Ausencias", "num"), ("licencia", "Días licencia", "num"),
    ("licencia_desde", "Licencia desde", "fecha"), ("licencia_hasta", "Licencia hasta", "fecha"),
    ("dias_vacaciones", "Días vacaciones", "num"), ("anticipo", "Anticipo", "num"), ("aguinaldo", "Aguinaldo", "num"),
    ("bono_desempeno", "Bono desempeño", "num"), ("cant_he_50", "HE 50% (h)", "num"),
    ("cant_he_100", "HE 100% (h)", "num"), ("cant_hd", "Hrs domingo", "num"), ("cant_hed", "HE domingo (h)", "num"),
    ("colacion", "Colación mes", "num"), ("movilizacion", "Movilización mes", "num"),
]
COLUMNAS_VALOR = [("valor_he_50", "$ HE 50%"), ("valor_he_100", "$ HE 100%"), ("valor_hd", "$ Hrs domingo"),
                  ("valor_hed", "$ HE domingo")]


def _nombre(t):
    return f"{t.get('apellido_paterno') or ''} {t.get('apellido_materno') or ''}, {t.get('nombres') or ''}".strip(" ,")


def pantalla_movimientos(conn, ctx):
    st.header("Movimientos del mes")
    if st.session_state.get("mov_msg"):
        st.success(st.session_state.pop("mov_msg"))
    st.caption("Asistencia, licencias, horas extra, anticipos, bonos y otros movimientos. "
               "Remuneraciones los toma automáticamente al calcular las liquidaciones.")
    emp = ctx["selector_empresa"](conn, "mov_emp")
    periodo = ctx["input_periodo"](key="mov_per")
    u = ctx["usuario"]()
    puede_rem = "remuneraciones" in ctx["modulos"]()
    est = PR.estado_periodo(conn, emp["id"], periodo)
    estado = est.get("estado") or "Abierto"
    bloqueado = estado != "Abierto" and not puede_rem

    c1, c2, c3 = st.columns([2, 2, 3])
    c1.metric("Estado del periodo", estado)
    if est.get("enviado_por"):
        c2.caption(f"Último cambio: {est['enviado_por']} · {str(est.get('enviado_at') or '')[:16]}")
    trabs = db.rows(conn, "SELECT * FROM trabajadores WHERE empresa_id=? AND activo=1 ORDER BY apellido_paterno, nombres",
                    (emp["id"],))
    if not trabs:
        st.info("No hay trabajadores activos. Agréguelos en **Trabajadores** (puede importarlos desde Excel).")
        return
    conceptos = PR.conceptos_empresa(conn, emp["id"])
    movs = PR.movimientos_periodo(conn, emp["id"], periodo)
    ver_valores = st.toggle("Informar valores en pesos de horas extra (si no, se calculan con el sueldo del contrato)",
                            value=any(float(m.get(k) or 0) for m in movs.values() for k, _ in COLUMNAS_VALOR))

    filas = []
    for t in trabs:
        m = movs.get(t["id"]) or {}
        f = {"id": t["id"], "RUT": t["rut"], "Trabajador": _nombre(t)}
        for k, lab, tipo in COLUMNAS:
            v = m.get(k)
            if tipo == "fecha":
                f[lab] = C.a_fecha(v)
            else:
                f[lab] = float(v) if v is not None else (30.0 if k == "dias_trabajados" else 0.0)
        if ver_valores:
            for k, lab in COLUMNAS_VALOR:
                f[lab] = float(m.get(k) or 0)
        for cpt in conceptos:
            f[f"{cpt['nombre']} ({cpt['tipo'][:4]}.)"] = float((m.get("extras") or {}).get(str(cpt["id"]), 0) or 0)
        f["Observación"] = m.get("observacion") or ""
        filas.append(f)
    df = pd.DataFrame(filas)
    cfg = {"id": None, "RUT": st.column_config.TextColumn(disabled=True),
           "Trabajador": st.column_config.TextColumn(disabled=True, width="medium")}
    for _, lab, tipo in COLUMNAS:
        cfg[lab] = st.column_config.DateColumn(lab, format="DD-MM-YYYY") if tipo == "fecha" else \
            st.column_config.NumberColumn(lab, min_value=0.0, step=0.5 if "Días" in lab or "(h)" in lab or "Hrs" in lab else 1.0)
    if bloqueado:
        st.warning(f"El periodo está **{estado}**: solo Remuneraciones puede modificarlo o reabrirlo.")
    ed = st.data_editor(df, column_config=cfg, hide_index=True, disabled=bloqueado, width="stretch",
                        key=f"mov_ed_{emp['id']}_{periodo}_{ver_valores}")

    tot = ed.drop(columns=["id", "RUT", "Trabajador", "Observación", "Licencia desde", "Licencia hasta"], errors="ignore")
    st.caption("Totales: " + " · ".join(f"{c}: {C.fmt_clp(tot[c].sum()) if tot[c].sum() >= 100 else f'{tot[c].sum():g}'}"
                                        for c in tot.columns if tot[c].sum()))

    avisos = []
    for _, r in ed.iterrows():
        dl = float(r["Días licencia"] or 0)
        if float(r["Días trab."] or 0) + float(r["Ausencias"] or 0) + dl > 30:
            avisos.append(f"{r['Trabajador']}: días trabajados + ausencias + licencia superan 30.")
        if dl and (pd.isna(r["Licencia desde"]) or pd.isna(r["Licencia hasta"])):
            avisos.append(f"{r['Trabajador']}: informe las fechas de la licencia (Previred las exige).")
    ctx["advertencias"](avisos, "Revisar")

    b1, b2, b3, b4 = st.columns(4)
    if not bloqueado and b1.button("💾 Guardar movimientos", type="primary"):
        for _, r in ed.iterrows():
            val = {}
            for k, lab, tipo in COLUMNAS:
                v = r[lab]
                val[k] = (C.a_fecha(v) if not pd.isna(v) else None) if tipo == "fecha" else float(v or 0)
            if ver_valores:
                for k, lab in COLUMNAS_VALOR:
                    val[k] = float(r[lab] or 0)
            else:  # conservar valores informados antes
                for k, _ in COLUMNAS_VALOR:
                    val[k] = float((movs.get(int(r["id"])) or {}).get(k) or 0)
            val["observacion"] = r["Observación"] or ""
            extras = {cpt["id"]: float(r[f"{cpt['nombre']} ({cpt['tipo'][:4]}.)"] or 0) for cpt in conceptos}
            PR.guardar_movimiento(conn, emp["id"], int(r["id"]), periodo, val, extras, u.get("usuario", ""))
        conn.commit()
        st.session_state["mov_msg"] = "Movimientos guardados."
        st.rerun()
    if estado == "Abierto" and b2.button("📤 Enviar a remuneraciones"):
        PR.guardar_estado_periodo(conn, emp["id"], periodo, "Enviado", u.get("usuario", ""))
        conn.commit()
        st.session_state["mov_msg"] = "Periodo enviado. Remuneraciones ya puede calcular las liquidaciones."
        st.rerun()
    if puede_rem and estado != "Abierto" and b3.button("🔓 Reabrir periodo"):
        PR.guardar_estado_periodo(conn, emp["id"], periodo, "Abierto", u.get("usuario", ""))
        conn.commit()
        st.rerun()
    if puede_rem and estado == "Enviado" and b4.button("🔒 Cerrar periodo"):
        PR.guardar_estado_periodo(conn, emp["id"], periodo, "Cerrado", u.get("usuario", ""))
        conn.commit()
        st.rerun()

    # Exportación en el formato de Control RRHH (compatible con carga en otros sistemas)
    buf = io.BytesIO()
    exp = ed.drop(columns=["id"]).copy()
    exp.insert(0, "MES", int(periodo[5:7]))
    exp.insert(0, "AÑO", int(periodo[:4]))
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame([[emp["razon_social"]], [emp["rut"]], [f"Movimientos {C.mes_anio_es(periodo)}"]]).to_excel(
            xw, index=False, header=False, sheet_name="Movimientos")
        exp.to_excel(xw, index=False, startrow=4, sheet_name="Movimientos")
    st.download_button("⬇️ Exportar a Excel", buf.getvalue(),
                       file_name=f"movimientos_{C.rut_partes(emp['rut'])[0]}_{periodo}.xlsx", key="dl_mov")


def pantalla_conceptos(conn, ctx):
    st.header("Conceptos adicionales")
    st.caption("Bonos, asignaciones o descuentos propios de cada empresa. Aparecen como columnas en Movimientos del mes. "
               "El tipo define si es imponible, no imponible o descuento; el código LRE, dónde se informa a la DT.")
    emp = ctx["selector_empresa"](conn, "cpt_emp")
    cps = PR.conceptos_empresa(conn, emp["id"], solo_activos=False)
    todos_codigos = {c: f"{c} — {n}" for t in C.CODIGOS_LRE_CONCEPTO.values() for c, n in t.items()}
    df = pd.DataFrame([{"id": c["id"], "Nombre": c["nombre"], "Tipo": c.get("tipo") or "Haber imponible",
                        "Código LRE": todos_codigos.get(c.get("codigo_lre"), ""), "Activo": bool(c.get("activo", 1)),
                        "Orden": int(c.get("orden") or 0)} for c in cps],
                      columns=["id", "Nombre", "Tipo", "Código LRE", "Activo", "Orden"])
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"cpt_ed_{emp['id']}",
                        column_config={"id": None,
                                       "Tipo": st.column_config.SelectboxColumn(options=C.TIPOS_CONCEPTO, required=True),
                                       "Código LRE": st.column_config.SelectboxColumn(options=list(todos_codigos.values())),
                                       "Activo": st.column_config.CheckboxColumn(default=True),
                                       "Orden": st.column_config.NumberColumn(step=1, default=0)})
    if st.button("💾 Guardar conceptos", type="primary"):
        errores = []
        for _, r in ed.iterrows():
            if not str(r["Nombre"] or "").strip():
                continue
            tipo = r["Tipo"] or "Haber imponible"
            cod = int(str(r["Código LRE"]).split(" ")[0]) if r["Código LRE"] else list(C.CODIGOS_LRE_CONCEPTO[tipo])[0]
            if cod not in C.CODIGOS_LRE_CONCEPTO[tipo]:
                errores.append(f"'{r['Nombre']}': el código {cod} no corresponde a un {tipo.lower()}.")
                continue
            d = dict(empresa_id=emp["id"], nombre=str(r["Nombre"]).strip(), tipo=tipo, codigo_lre=cod,
                     activo=int(bool(r["Activo"]) if not pd.isna(r["Activo"]) else 1),
                     orden=int(r["Orden"] or 0) if not pd.isna(r["Orden"]) else 0)
            if pd.isna(r["id"]):
                db.insert(conn, "conceptos", d)
            else:
                sets = ", ".join(f"{k}=?" for k in d)
                conn.execute(f"UPDATE conceptos SET {sets} WHERE id=? AND empresa_id=?", [*d.values(), int(r["id"]), emp["id"]])
        conn.commit()
        ctx["advertencias"](errores, "No se guardaron")
        if not errores:
            st.success("Conceptos guardados. Para dejar de usar uno, desmárquelo como activo (no se borra para conservar el historial).")


def importar_trabajadores_excel(conn, emp, archivo) -> tuple[int, list[str]]:
    """Columnas aceptadas (formato Control RRHH): CODIGO, RUT, NOMBRE(S), AP PATERNO, AP MATERNO, CARGO, CENTRO COSTO."""
    df = pd.read_excel(archivo, dtype=str).fillna("")
    df.columns = [C.normalizar(c) for c in df.columns]

    def col(r, *nombres):
        for n in nombres:
            if n in r and str(r[n]).strip():
                return str(r[n]).strip()
        return ""
    existentes = {C.rut_partes(t["rut"]) for t in db.rows(conn, "SELECT rut FROM trabajadores WHERE empresa_id=?", (emp["id"],))}
    n, errores = 0, []
    for i, r in df.iterrows():
        rut = col(r, "RUT")
        nombre = col(r, "NOMBRES", "NOMBRE")
        ap = col(r, "AP PATERNO", "APELLIDO PATERNO")
        if not rut and not nombre:
            continue
        if not C.rut_valido(rut):
            errores.append(f"Fila {i + 2}: RUT inválido ({rut}).")
            continue
        if C.rut_partes(rut) in existentes:
            continue
        if not nombre or not ap:
            errores.append(f"Fila {i + 2}: faltan nombres o apellido paterno.")
            continue
        db.insert(conn, "trabajadores", dict(
            empresa_id=emp["id"], rut=rut, nombres=nombre, apellido_paterno=ap,
            apellido_materno=col(r, "AP MATERNO", "APELLIDO MATERNO"), codigo=col(r, "CODIGO"),
            cargo=col(r, "CARGO"), centro_costo=col(r, "CENTRO COSTO")))
        existentes.add(C.rut_partes(rut))
        n += 1
    conn.commit()
    return n, errores


def resumen_movimientos_para_liquidacion(conn, emp, periodo) -> tuple[dict, dict]:
    return PR.movimientos_periodo(conn, emp["id"], periodo), PR.estado_periodo(conn, emp["id"], periodo)


__all__ = ["pantalla_movimientos", "pantalla_conceptos", "importar_trabajadores_excel",
           "resumen_movimientos_para_liquidacion", "date"]

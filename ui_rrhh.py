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


def _resumen_mov(m):
    """Resumen corto de los movimientos NO cero del trabajador."""
    partes = []
    if float(m.get("ausencias") or 0):
        partes.append(f"Aus: {int(float(m['ausencias']))}")
    if float(m.get("licencia") or 0):
        partes.append(f"Lic: {int(float(m['licencia']))}")
    if float(m.get("cant_he_50") or 0):
        partes.append(f"HE 50%: {float(m['cant_he_50']):g}h")
    if float(m.get("cant_he_100") or 0):
        partes.append(f"HE 100%: {float(m['cant_he_100']):g}h")
    if float(m.get("dias_vacaciones") or 0):
        partes.append(f"Vac: {int(float(m['dias_vacaciones']))}")
    if float(m.get("anticipo") or 0):
        partes.append(f"Anticipo: {C.fmt_clp(m['anticipo'])}")
    if float(m.get("bono_desempeno") or 0):
        partes.append(f"Bono: {C.fmt_clp(m['bono_desempeno'])}")
    if float(m.get("aguinaldo") or 0):
        partes.append(f"Aguinaldo: {C.fmt_clp(m['aguinaldo'])}")
    if float(m.get("colacion") or 0):
        partes.append(f"Colación: {C.fmt_clp(m['colacion'])}")
    if float(m.get("movilizacion") or 0):
        partes.append(f"Mov: {C.fmt_clp(m['movilizacion'])}")
    return " | ".join(partes) if partes else "Sin movimientos cargados"


def pantalla_movimientos(conn, ctx):
    st.header("Movimientos del mes")
    if st.session_state.get("mov_msg"):
        st.success(st.session_state.pop("mov_msg"))
    st.caption("Asistencia, licencias, horas extra, anticipos, bonos y otros movimientos. "
               "Remuneraciones los toma automáticamente al calcular las liquidaciones. "
               "Los días trabajados se calculan como 30 menos ausencias y días de licencia al generar la liquidación.")
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
        st.info("No hay trabajadores activos. Agréguelos en **Ficha del Personal** (puede importarlos desde Excel).")
        return
    conceptos = PR.conceptos_empresa(conn, emp["id"])
    movs = PR.movimientos_periodo(conn, emp["id"], periodo)
    cuotas_prestamos = PR.cuotas_del_periodo(conn, emp["id"], periodo)
    ver_valores = st.toggle("Informar valores en pesos de horas extra (si no, se calculan con el sueldo del contrato)",
                            value=any(float(m.get(k) or 0) for m in movs.values() for k, _ in COLUMNAS_VALOR))

    # Buscador
    buscar = st.text_input("🔍 Buscar trabajador (RUT, nombre o apellido)", key="mov_buscar").strip().upper()
    if buscar:
        trabs_filtrados = [t for t in trabs if buscar in (t.get("rut") or "").upper()
                           or buscar in _nombre(t).upper()]
    else:
        trabs_filtrados = trabs

    st.caption(f"Mostrando {len(trabs_filtrados)} de {len(trabs)} trabajadores.")

    if bloqueado:
        st.warning(f"El periodo está **{estado}**: solo Remuneraciones puede modificarlo o reabrirlo.")

    st.divider()

    # Un expander por trabajador
    for t in trabs_filtrados:
        m = movs.get(t["id"]) or {}
        titulo = f"{_nombre(t)} · RUT {t['rut']}"
        resumen = _resumen_mov(m)

        with st.expander(f"{titulo}  —  {resumen}", expanded=False):
            with st.form(f"mov_form_{t['id']}", clear_on_submit=False):
                # ───── Bloque 1: Asistencia ─────
                st.markdown("##### 📅 Asistencia")
                c1, c2, c3, c4 = st.columns(4)
                aus = c1.number_input("Ausencias", min_value=0.0, step=0.5, value=float(m.get("ausencias") or 0),
                                      key=f"aus_{t['id']}")
                lic = c2.number_input("Días licencia", min_value=0.0, step=0.5, value=float(m.get("licencia") or 0),
                                      key=f"lic_{t['id']}")
                lic_desde = c3.date_input("Licencia desde", value=C.a_fecha(m.get("licencia_desde")),
                                          key=f"licd_{t['id']}")
                lic_hasta = c4.date_input("Licencia hasta", value=C.a_fecha(m.get("licencia_hasta")),
                                          key=f"lich_{t['id']}")

                # ───── Bloque 2: Horas extra ─────
                st.markdown("##### ⏰ Horas extra")
                c1, c2, c3, c4 = st.columns(4)
                he50 = c1.number_input("HE 50% (h)", min_value=0.0, step=0.5, value=float(m.get("cant_he_50") or 0),
                                       key=f"he50_{t['id']}")
                he100 = c2.number_input("HE 100% (h)", min_value=0.0, step=0.5, value=float(m.get("cant_he_100") or 0),
                                        key=f"he100_{t['id']}")
                hd = c3.number_input("Hrs domingo", min_value=0.0, step=0.5, value=float(m.get("cant_hd") or 0),
                                     key=f"hd_{t['id']}")
                hed = c4.number_input("HE domingo (h)", min_value=0.0, step=0.5, value=float(m.get("cant_hed") or 0),
                                      key=f"hed_{t['id']}")
                if ver_valores:
                    st.caption("Valores informados (si > 0 se usan; si no, se calculan):")
                    c1, c2, c3, c4 = st.columns(4)
                    vhe50 = c1.number_input("$ HE 50%", min_value=0.0, step=1000.0,
                                            value=float(m.get("valor_he_50") or 0), key=f"vhe50_{t['id']}")
                    vhe100 = c2.number_input("$ HE 100%", min_value=0.0, step=1000.0,
                                             value=float(m.get("valor_he_100") or 0), key=f"vhe100_{t['id']}")
                    vhd = c3.number_input("$ Hrs domingo", min_value=0.0, step=1000.0,
                                          value=float(m.get("valor_hd") or 0), key=f"vhd_{t['id']}")
                    vhed = c4.number_input("$ HE domingo", min_value=0.0, step=1000.0,
                                           value=float(m.get("valor_hed") or 0), key=f"vhed_{t['id']}")

                # ───── Bloque 3: Haberes ─────
                st.markdown("##### 💰 Haberes (mes completo)")
                c1, c2, c3 = st.columns(3)
                col = c1.number_input("Colación (no imponible)", min_value=0.0, step=1000.0,
                                      value=float(m.get("colacion") or 0), key=f"col_{t['id']}")
                mov = c2.number_input("Movilización (no imponible)", min_value=0.0, step=1000.0,
                                      value=float(m.get("movilizacion") or 0), key=f"mov_{t['id']}")
                vac = c3.number_input("Días vacaciones", min_value=0.0, step=0.5,
                                      value=float(m.get("dias_vacaciones") or 0), key=f"vac_{t['id']}")

                # ───── Bloque 4: Otros haberes y descuentos ─────
                st.markdown("##### 🎁 Otros haberes y descuentos")
                c1, c2, c3 = st.columns(3)
                ant = c1.number_input("Anticipo", min_value=0.0, step=1000.0,
                                      value=float(m.get("anticipo") or 0), key=f"ant_{t['id']}")
                agu = c2.number_input("Aguinaldo", min_value=0.0, step=1000.0,
                                      value=float(m.get("aguinaldo") or 0), key=f"agu_{t['id']}")
                bon = c3.number_input("Bono desempeño", min_value=0.0, step=1000.0,
                                      value=float(m.get("bono_desempeno") or 0), key=f"bon_{t['id']}")

                # ───── Conceptos propios de la empresa ─────
                extras_vals = {}
                if conceptos:
                    st.markdown("##### 🏷️ Conceptos propios de la empresa")
                    for cpt in conceptos:
                        v = float((m.get("extras") or {}).get(str(cpt["id"]), 0) or 0)
                        extras_vals[cpt["id"]] = st.number_input(
                            f"{cpt['nombre']} ({cpt['tipo']})", min_value=0.0, step=1000.0, value=v,
                            key=f"cpt_{cpt['id']}_{t['id']}")

                # ───── Observación ─────
                st.markdown("##### 📝 Observación")
                obs = st.text_area("Observación (opcional)", value=m.get("observacion") or "",
                                   key=f"obs_{t['id']}", height=68)

                # ───── Bloque 5: Préstamos vigentes ─────
                cuotas_trab = cuotas_prestamos.get(t["id"], [])
                if cuotas_trab:
                    st.markdown("##### 🏦 Préstamos vigentes este mes")
                    for c in cuotas_trab:
                        icono = "💰" if c["tipo"] == "Empresa" else "🏥"
                        st.caption(f"{icono} **{c['tipo']}** — {c.get('descripcion') or ''}")
                        cc1, cc2, cc3 = st.columns([3, 1, 1])
                        cc1.write(f"Cuota **{c['numero_cuota']}/{c['num_cuotas']}** · **${float(c['monto']):,.0f}**")
                        cc2.checkbox("Incluir", value=True, key=f"incl_{c['id']}")
                       

                # ───── Botón guardar (por trabajador) ─────
                if not bloqueado:
                    if st.form_submit_button("💾 Guardar movimientos de este trabajador", type="primary"):
                        val = {
                            "ausencias": aus, "licencia": lic,
                            "licencia_desde": C.a_fecha(lic_desde) if lic_desde else None,
                            "licencia_hasta": C.a_fecha(lic_hasta) if lic_hasta else None,
                            "cant_he_50": he50, "cant_he_100": he100, "cant_hd": hd, "cant_hed": hed,
                            "colacion": col, "movilizacion": mov, "dias_vacaciones": vac,
                            "anticipo": ant, "aguinaldo": agu, "bono_desempeno": bon,
                            "observacion": obs,
                        }
                        if ver_valores:
                            val.update({"valor_he_50": vhe50, "valor_he_100": vhe100,
                                        "valor_hd": vhd, "valor_hed": vhed})
                        else:
                            for k in ("valor_he_50", "valor_he_100", "valor_hd", "valor_hed"):
                                val[k] = float((movs.get(t["id"]) or {}).get(k) or 0)
                        # Días trabajados se calcula internamente en procesos.py; se conserva el valor anterior si existía
                        val["dias_trabajados"] = float((movs.get(t["id"]) or {}).get("dias_trabajados") or 30.0)

                        PR.guardar_movimiento(conn, emp["id"], t["id"], periodo, val, extras_vals,
                                              u.get("usuario", ""))
                        conn.commit()
                        st.session_state["mov_msg"] = f"Movimientos de {_nombre(t)} guardados."
                        st.rerun()

    # ───── Botones de estado del período ─────
    st.divider()
    b1, b2, b3 = st.columns(3)
    if estado == "Abierto" and b1.button("📤 Enviar a remuneraciones"):
        PR.guardar_estado_periodo(conn, emp["id"], periodo, "Enviado", u.get("usuario", ""))
        conn.commit()
        st.session_state["mov_msg"] = "Periodo enviado. Remuneraciones ya puede calcular las liquidaciones."
        st.rerun()
    if puede_rem and estado != "Abierto" and b2.button("🔓 Reabrir periodo"):
        PR.guardar_estado_periodo(conn, emp["id"], periodo, "Abierto", u.get("usuario", ""))
        conn.commit()
        st.rerun()
    if puede_rem and estado == "Enviado" and b3.button("🔒 Cerrar periodo"):
        PR.guardar_estado_periodo(conn, emp["id"], periodo, "Cerrado", u.get("usuario", ""))
        conn.commit()
        st.rerun()

    # ───── Exportación a Excel ─────
    if trabs_filtrados:
        buf = io.BytesIO()
        filas_exp = []
        for t in trabs_filtrados:
            m = movs.get(t["id"]) or {}
            r = {"RUT": t["rut"], "Trabajador": _nombre(t)}
            for k, lab, tipo in COLUMNAS:
                r[lab] = m.get(k)
            r["Observación"] = m.get("observacion") or ""
            filas_exp.append(r)
        exp = pd.DataFrame(filas_exp)
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
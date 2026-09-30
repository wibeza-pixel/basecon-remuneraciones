"""Libro de remuneraciones (Excel + centralización), LRE (DT), Formulario y certificados 1887."""
from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config as C
from . import db

def generar_libro_remuneraciones(empresa_id, periodo, ruta):  # noqa: C901
    """Genera Libro de Remuneraciones mensual en Excel (formato legal simplificado DT)"""

    conn = db.get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    liqs = conn.execute("""
        SELECT l.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno,
               t.afp, t.salud, c.cargo, c.tipo_contrato
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        LEFT JOIN contratos c ON l.contrato_id = c.id
        WHERE l.empresa_id = ? AND l.periodo = ?
        ORDER BY t.apellido_paterno, t.nombres
    """, (empresa_id, periodo)).fetchall()
    conn.close()

    if not liqs:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = f"Libro {periodo}"

    thin = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF", size=9)
    title_font = Font(bold=True, size=14)
    subtitle_font = Font(bold=True, size=11)

    # Encabezado
    ws.merge_cells('A1:AF1')
    ws['A1'] = "LIBRO DE REMUNERACIONES"
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:AF2')
    ws['A2'] = f"{emp['razon_social']}  |  RUT: {emp['rut']}  |  Periodo: {periodo}"
    ws['A2'].font = subtitle_font
    ws['A2'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A3:AF3')
    ws['A3'] = f"Dirección: {emp.get('direccion') or ''} , {emp.get('comuna') or ''} - {emp.get('ciudad') or ''}"
    ws['A3'].alignment = Alignment(horizontal='center')

    # Columnas Libro de Remuneraciones Chile (incluye HE, Asig. Familiar y Reforma Pensiones)
    headers = [
        "N°", "RUT", "Apellido Paterno", "Apellido Materno", "Nombres", "Cargo",
        "Días Trab.", "Hrs Extras", "Monto HE", "Sueldo Base", "Gratificación",
        "Movilización", "Colación", "Asig. Familiar", "Otros Haberes",
        "Total Haberes", "Total Imponible",
        "AFP", "Salud", "Adic. Isapre", "AFC Trab.", "Base Tributable", "Impuesto Único",
        "Anticipos", "Total Descuentos", "Líquido a Pago",
        "SIS (Emp)", "Mutual (Emp)", "AFC Emp",
        "Ley 21.735 0,1% CCI", "Ley 21.735 0,9% (Exp. vida / CRP)", "Ley 21.735 2,5% Seguro Social"
    ]

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.border = thin

    def _g(liq, key, default=0):
        try:
            return liq[key] if liq[key] is not None else default
        except (KeyError, IndexError, TypeError):
            return default

    for i, liq in enumerate(liqs, 1):
        row = [
            i,
            liq['rut'],
            liq['apellido_paterno'] or "",
            liq['apellido_materno'] or "",
            liq['nombres'] or "",
            liq['cargo'] or "",
            _g(liq, 'dias_trabajados', 30),
            _g(liq, 'horas_extras'),
            _g(liq, 'monto_horas_extras'),
            _g(liq, 'sueldo_base'),
            _g(liq, 'gratificacion'),
            _g(liq, 'movilizacion'),
            _g(liq, 'colacion'),
            _g(liq, 'asignacion_familiar'),
            _g(liq, 'otros_haberes'),
            _g(liq, 'total_haberes'),
            _g(liq, 'total_imponible'),
            _g(liq, 'afp_monto'),
            _g(liq, 'salud_monto'),
            _g(liq, 'adicional_isapre'),
            _g(liq, 'afc_trabajador'),
            _g(liq, 'base_tributable'),
            _g(liq, 'impuesto_unico'),
            _g(liq, 'anticipo'),
            _g(liq, 'total_descuentos'),
            _g(liq, 'liquido'),
            _g(liq, 'sis_monto'),
            _g(liq, 'mutual_monto'),
            _g(liq, 'afc_empleador'),
            _g(liq, 'reforma_afp_emp'),
            _g(liq, 'reforma_crp'),
            _g(liq, 'reforma_seguro_social'),
        ]
        for col, val in enumerate(row, 1):
            cell = ws.cell(row=5 + i, column=col, value=val)
            cell.border = thin
            if col >= 8 and isinstance(val, (int, float)):
                cell.number_format = '#,##0'
            cell.alignment = Alignment(horizontal='center' if col <= 7 else 'right')

    # Totales
    total_row = 6 + len(liqs)
    ws.cell(row=total_row, column=1, value="TOTALES").font = Font(bold=True)
    for col in range(8, len(headers) + 1):
        col_letter = get_column_letter(col)
        cell = ws.cell(row=total_row, column=col,
                       value=f"=SUM({col_letter}6:{col_letter}{5+len(liqs)})")
        cell.font = Font(bold=True)
        cell.number_format = '#,##0'
        cell.border = thin

    # Anchos
    widths = [5, 14, 15, 15, 16, 16, 9, 9, 11, 12, 12, 11, 11, 12, 11,
              12, 12, 10, 10, 11, 10, 12, 11, 11, 12, 12, 14, 11, 10, 12, 14, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.row_dimensions[5].height = 30

    # Pie legal
    pie = total_row + 2
    ws.cell(row=pie, column=1,
            value="Libro de Remuneraciones confeccionado conforme al Art. 54 del Código del Trabajo y normativa de la Dirección del Trabajo.")
    ws.merge_cells(start_row=pie, start_column=1, end_row=pie, end_column=10)

    # ===== Hoja: Asiento de Centralización Contable =====
    _agregar_hoja_asiento_centralizacion(wb, emp, periodo, liqs)

    wb.save(ruta)
    return ruta


def _agregar_hoja_asiento_centralizacion(wb, emp, periodo, liqs):
    """
    Asiento de centralización de remuneraciones (estilo ERP chileno / AVSOFT).
    Debe = gasto + aportes empleador; Haber = retenciones + anticipos + líquido por pagar.
    """

    def _sum(key):
        total = 0.0
        for liq in liqs:
            try:
                v = liq[key]
                total += float(v or 0)
            except (KeyError, TypeError, ValueError):
                pass
        return round(total)

    # Haberes (gasto)
    sueldo = _sum("sueldo_calculado") or _sum("sueldo_base")
    grat = _sum("gratificacion")
    mov = _sum("movilizacion")
    col = _sum("colacion")
    he = _sum("monto_horas_extras")
    af_fam = _sum("asignacion_familiar")
    otros_h = _sum("otros_haberes")

    # Aportes empleador
    afc_emp = _sum("afc_empleador")
    reforma_afp = _sum("reforma_afp_emp")       # 0,1% CCI
    reforma_crp = _sum("reforma_crp")           # 0,9% / seguro vida
    reforma_ss = _sum("reforma_seguro_social")  # 2,5%
    sis = _sum("sis_monto")
    mutual = _sum("mutual_monto")

    # Retenciones trabajador (por AFP / salud)
    afp_total = _sum("afp_monto")
    salud = _sum("salud_monto") + _sum("adicional_isapre")
    afc_trab = _sum("afc_trabajador")
    anticipos = _sum("anticipo")
    impuesto = _sum("impuesto_unico")
    liquido = _sum("liquido")
    salud_ccaf = _sum("salud_ccaf")

    # Desglose AFP por institución
    afp_por = {}
    for liq in liqs:
        try:
            nombre = (liq["afp"] or "AFP").upper()
            afp_por[nombre] = afp_por.get(nombre, 0) + float(liq["afp_monto"] or 0)
        except Exception:
            pass
    afp_por = {k: round(v) for k, v in afp_por.items() if v}

    # Salud: FONASA vs ISAPRE (simplificado: si salud contiene FONASA)
    fonasa = 0
    isapre = 0
    for liq in liqs:
        try:
            mon = float(liq["salud_monto"] or 0) + float(liq["adicional_isapre"] or 0)
            if str(liq["salud"] or "").upper().startswith("FON"):
                fonasa += mon
            else:
                isapre += mon
        except Exception:
            pass
    fonasa, isapre = round(fonasa) - salud_ccaf, round(isapre)

    # Líneas DEBE
    debe_lineas = []
    if sueldo:
        debe_lineas.append(("SUELDO BASE CALC.", sueldo))
    if grat:
        debe_lineas.append(("GRATIFICACION", grat))
    if he:
        debe_lineas.append(("HORAS EXTRAS", he))
    if mov:
        debe_lineas.append(("MOVILIZACION", mov))
    if col:
        debe_lineas.append(("COLACION", col))
    if af_fam:
        debe_lineas.append(("ASIGNACION FAMILIAR (por recuperar IPS/CCAF)", af_fam))
    if otros_h:
        debe_lineas.append(("OTROS HABERES", otros_h))
    if afc_emp:
        debe_lineas.append(("SEGURO DE CESANTIA EMPLEADOR", afc_emp))
    if reforma_afp:
        debe_lineas.append(("APORTE EMPLEADOR CAP.INDIVIDUAL", reforma_afp))
    if reforma_crp:
        debe_lineas.append(("APORTE EMPLEADOR 0,9% (EXP. VIDA / RENT. PROTEGIDA)", reforma_crp))
    if mutual:
        debe_lineas.append(("ACC. DEL TRABAJO", mutual))
    if sis:
        debe_lineas.append(("S.I.S.", sis))
    if reforma_ss:
        debe_lineas.append(("SEGURO SOCIAL", reforma_ss))

    # Líneas HABER
    haber_lineas = []
    for nombre, mon in sorted(afp_por.items()):
        haber_lineas.append((nombre, mon))
    if fonasa:
        haber_lineas.append(("I.P.S. / FONASA", fonasa))
    if isapre:
        haber_lineas.append(("ISAPRE", isapre))
    if salud_ccaf:
        haber_lineas.append(("C.C.A.F. (cotización salud)", salud_ccaf))
    if afc_trab:
        haber_lineas.append(("SEGURO CESANTIA TRABAJADOR", afc_trab))
    if impuesto:
        haber_lineas.append(("IMPUESTO UNICO POR PAGAR", impuesto))
    if anticipos:
        haber_lineas.append(("ANTICIPOS", anticipos))
    if liquido:
        haber_lineas.append(("REMUNERACIONES POR PAGAR", liquido))
    if mutual:
        haber_lineas.append(("MUTUAL DE SEGURIDAD", mutual))
    if reforma_ss:
        haber_lineas.append(("SEGURO SOCIAL (por pagar)", reforma_ss))
    if reforma_afp:
        haber_lineas.append(("APORTE CAP.INDIVIDUAL (por pagar)", reforma_afp))
    if reforma_crp:
        haber_lineas.append(("APORTE 0,9% LEY 21.735 (por pagar)", reforma_crp))
    if sis:
        haber_lineas.append(("S.I.S. (por pagar)", sis))
    if afc_emp:
        haber_lineas.append(("SEGURO CESANTIA EMPLEADOR (por pagar)", afc_emp))

    total_debe = sum(x[1] for x in debe_lineas)
    total_haber = sum(x[1] for x in haber_lineas)

    # Cuadratura: si hay diferencia por redondeo, ajustar REMUNERACIONES POR PAGAR
    dif = total_debe - total_haber
    if 0 < abs(dif) <= 2 and haber_lineas:  # solo redondeos; diferencias mayores quedan a la vista
        # buscar remuneraciones por pagar
        for i, (nom, mon) in enumerate(haber_lineas):
            if "REMUNERACIONES POR PAGAR" in nom:
                haber_lineas[i] = (nom, mon + dif)
                total_haber += dif
                break

    ws = wb.create_sheet("Asiento Centralizacion")
    thin = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    debe_fill = PatternFill("solid", fgColor="FFF2CC")
    haber_fill = PatternFill("solid", fgColor="DDEBF7")
    total_fill = PatternFill("solid", fgColor="E2EFDA")

    ws.merge_cells("A1:D1")
    ws["A1"] = "ASIENTO DE CENTRALIZACIÓN DE REMUNERACIONES"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A1"].alignment = Alignment(horizontal="center")

    ws.merge_cells("A2:D2")
    ws["A2"] = f"{emp.get('razon_social') or ''}  |  RUT: {emp.get('rut') or ''}  |  Periodo: {periodo}"
    ws["A2"].alignment = Alignment(horizontal="center")

    ws.merge_cells("A3:D3")
    ws["A3"] = "Consulta Asiento Remuneraciones (centralización contable)"
    ws["A3"].font = Font(italic=True, size=9)

    for col, h in enumerate(["Descripción", "Debe", "Haber", "Observación"], 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = thin
        cell.alignment = Alignment(horizontal="center")

    row = 6
    # Debe primero
    for desc, mon in debe_lineas:
        ws.cell(row=row, column=1, value=desc).border = thin
        c = ws.cell(row=row, column=2, value=mon)
        c.number_format = '#,##0'
        c.border = thin
        c.fill = debe_fill
        ws.cell(row=row, column=3, value=None).border = thin
        ws.cell(row=row, column=4, value="Gasto / aporte empleador").border = thin
        row += 1

    for desc, mon in haber_lineas:
        ws.cell(row=row, column=1, value=desc).border = thin
        ws.cell(row=row, column=2, value=None).border = thin
        c = ws.cell(row=row, column=3, value=mon)
        c.number_format = '#,##0'
        c.border = thin
        c.fill = haber_fill
        ws.cell(row=row, column=4, value="Retención / pasivo").border = thin
        row += 1

    # Totales
    ws.cell(row=row, column=1, value="TOTALES").font = Font(bold=True)
    ws.cell(row=row, column=1).border = thin
    c1 = ws.cell(row=row, column=2, value=total_debe)
    c1.font = Font(bold=True)
    c1.number_format = '#,##0'
    c1.fill = total_fill
    c1.border = thin
    c2 = ws.cell(row=row, column=3, value=total_haber)
    c2.font = Font(bold=True)
    c2.number_format = '#,##0'
    c2.fill = total_fill
    c2.border = thin
    ws.cell(row=row, column=4, value="Debe = Haber" if total_debe == total_haber else f"Dif: {total_debe - total_haber}").border = thin

    row += 2
    ws.cell(row=row, column=1, value="Nota: Asiento generado automáticamente desde liquidaciones del periodo. Ajustar cuentas contables según plan de cuentas de la empresa.")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)

    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 28


def generar_formulario_1887(empresa_id, anio_tributario, ruta):
    """
    Genera Formulario 1887 (Declaración Jurada Anual Impuesto Único 2ª Categoría)
    basado en el formato del archivo form1887-at2026.xls proporcionado.
    anio_tributario = año de la declaración (ej. 2026 declara rentas 2025)
    """

    conn = db.get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    # Periodo de rentas = año anterior al tributario
    anio_rentas = anio_tributario - 1
    periodos = [f"{anio_rentas}-{m:02d}" for m in range(1, 13)]

    # Agregar liquidaciones del año de rentas por trabajador
    rows = conn.execute("""
        SELECT t.id, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno,
               SUM(l.total_imponible) as renta_total,
               SUM(l.liquido) as liquido_total,
               COUNT(l.id) as meses,
               MAX(c.jornada_semanal) as jornada
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        LEFT JOIN contratos c ON l.contrato_id = c.id
        WHERE l.empresa_id = ? AND l.periodo IN ({})
        GROUP BY t.id, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno
        ORDER BY t.apellido_paterno, t.nombres
    """.format(",".join("?" * 12)), (empresa_id, *periodos)).fetchall()

    # Detalle mensual por trabajador para la grilla de meses
    detalle = {}
    for r in rows:
        tid = r['id']
        meses_data = conn.execute("""
            SELECT periodo, total_imponible, liquido, base_tributable, impuesto_unico
            FROM liquidaciones
            WHERE trabajador_id = ? AND empresa_id = ? AND periodo IN ({})
        """.format(",".join("?" * 12)), (tid, empresa_id, *periodos)).fetchall()
        detalle[tid] = {d['periodo']: d for d in meses_data}

    conn.close()

    if not rows:
        return None

    # Factores de actualización del año de rentas (SP / SII)
    factores = db.get_factores_actualizacion(anio_rentas)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Formulario 1887 AT {anio_tributario}"

    thin = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    bold = Font(bold=True, size=10)
    title_font = Font(bold=True, size=14)
    header_fill = PatternFill("solid", fgColor="D9E2F3")

    # Encabezado Formulario 1887
    ws['A1'] = "FORMULARIO 1887"
    ws['A1'].font = title_font
    ws.merge_cells('A1:N1')

    ws['A3'] = "AÑO TRIBUTARIO:"
    ws['C3'] = anio_tributario
    ws['C3'].font = bold
    ws['E3'] = f"Factores act. rentas {anio_rentas} aplicados"
    ws['E3'].font = Font(italic=True, size=9)

    ws['A5'] = "DECLARANTES"
    ws['A5'].font = bold
    ws['L5'] = f"Fecha de Emisión: {C.fecha_larga()}"

    ws['A7'] = f"R.U.T.: {emp['rut']}     {emp['razon_social']}"
    ws['A8'] = f"Dirección: {emp.get('direccion') or ''}       Comuna: {emp.get('comuna') or ''}"
    ws['A9'] = f"Teléfono: {emp.get('telefono') or ''}"

    ws['A11'] = "INFORMADOS"
    ws['A11'].font = bold

    # Cabeceras columnas principales (basado en form1887-at2026.xls)
    # Nº | RUT | Renta Total Neta Pag. (Art.42 N°1) | Impuesto Unico Retenido | Mayor Retención Solic. (Art.88) |
    # Rta.Total No Gravada | Rta.Total Exenta | Rebaja por Zonas Extremas | 3% Prestamo Tasa 0% | Meses 1-12 | Cant.Hrs Jornada Semana | Nº Certif.
    headers1 = ["Nº", "R.U.T.", "Renta Total Neta Pag. (Art.42 N°1)", "Impuesto Unico Retenido",
                "Mayor Retención Solic. (Art.88)", "Rta.Total No Gravada", "Rta.Total Exenta",
                "Rebaja por Zonas Extremas", "3% Prestamo Tasa 0%", "Meses trabajados",
                "Cant. Hrs Jornada Semana", "Nº Certif."]
    for col, h in enumerate(headers1, 1):
        cell = ws.cell(row=13, column=col, value=h)
        cell.font = Font(bold=True, size=8)
        cell.fill = header_fill
        cell.border = thin
        cell.alignment = Alignment(wrap_text=True, horizontal='center')

    for i, r in enumerate(rows, 1):
        rut = r['rut']
        tid = r['id']
        # Renta total neta ACTUALIZADA: suma (monto_mes × factor_mes) según SII / SP
        # Renta total neta = base tributable (imponible − cotizaciones), actualizada mes a mes
        renta_neta_act = 0.0
        impuesto_act = 0.0
        for per, d in detalle.get(tid, {}).items():
            try:
                mes = int(per.split("-")[1])
            except Exception:
                mes = 12
            fac = factores.get(mes, 1.0)
            renta_neta_act += float(d['base_tributable'] or 0) * fac
            impuesto_act += float(d['impuesto_unico'] or 0) * fac
        renta_neta = int(round(renta_neta_act))
        impuesto = int(round(impuesto_act))
        meses = r['meses'] or 0
        row_data = [
            i, rut, renta_neta, impuesto, 0, 0, 0, 0, 0, meses, float(r['jornada'] or C.JORNADA_DEFAULT), i
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=13 + i, column=col, value=val)
            cell.border = thin
            if col >= 3 and isinstance(val, (int, float)) and col != 10 and col != 11:
                cell.number_format = '#,##0'

    # Totales
    tot_row = 14 + len(rows)
    ws.cell(row=tot_row, column=1, value="TOTALES").font = bold
    for col in [3, 4]:
        col_letter = get_column_letter(col)
        cell = ws.cell(row=tot_row, column=col,
                       value=f"=SUM({col_letter}14:{col_letter}{13+len(rows)})")
        cell.font = bold
        cell.number_format = '#,##0'
        cell.border = thin

    # Segunda sección: detalle mensual (como en el ejemplo)
    det_start = tot_row + 3
    ws.cell(row=det_start, column=1, value="DETALLE MENSUAL DE RENTAS (Renta neta = base tributable, sin actualizar)").font = bold

    meses_nombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    ws.cell(row=det_start + 1, column=1, value="Nº").font = Font(bold=True, size=8)
    ws.cell(row=det_start + 1, column=2, value="RUT").font = Font(bold=True, size=8)
    for m, nombre in enumerate(meses_nombres, 3):
        cell = ws.cell(row=det_start + 1, column=m, value=nombre)
        cell.font = Font(bold=True, size=8)
        cell.fill = header_fill
        cell.border = thin
    ws.cell(row=det_start + 1, column=15, value="TOTAL").font = Font(bold=True, size=8)

    for i, r in enumerate(rows, 1):
        tid = r['id']
        ws.cell(row=det_start + 1 + i, column=1, value=i).border = thin
        ws.cell(row=det_start + 1 + i, column=2, value=r['rut']).border = thin
        total_anio = 0
        for m in range(1, 13):
            per = f"{anio_rentas}-{m:02d}"
            val = 0
            if tid in detalle and per in detalle[tid]:
                val = int(detalle[tid][per]['base_tributable'] or 0)
            total_anio += val
            cell = ws.cell(row=det_start + 1 + i, column=2 + m, value=val if val else "")
            cell.border = thin
            cell.number_format = '#,##0'
        cell = ws.cell(row=det_start + 1 + i, column=15, value=total_anio)
        cell.border = thin
        cell.number_format = '#,##0'
        cell.font = bold

    # Totales mensuales
    trow = det_start + 2 + len(rows)
    ws.cell(row=trow, column=1, value="TOTALES").font = bold
    for m in range(3, 16):
        col_letter = get_column_letter(m)
        cell = ws.cell(row=trow, column=m,
                       value=f"=SUM({col_letter}{det_start+2}:{col_letter}{det_start+1+len(rows)})")
        cell.font = bold
        cell.number_format = '#,##0'
        cell.border = thin

    # Representante
    rep_row = trow + 3
    ws.cell(row=rep_row, column=1, value="Representante Legal:")
    ws.cell(row=rep_row, column=3, value=f"{emp.get('rut_representante') or ''}     {emp.get('representante_legal') or ''}")
    ws.cell(row=rep_row + 1, column=1, value="Casos Informados")
    ws.cell(row=rep_row + 1, column=3, value=len(rows))

    # Anchos
    for col in range(1, 16):
        ws.column_dimensions[get_column_letter(col)].width = 14
    ws.column_dimensions['C'].width = 22
    ws.row_dimensions[13].height = 35

    wb.save(ruta)
    return ruta


def generar_certificados_1887(empresa_id, anio_tributario, ruta_zip):
    """
    Genera Certificados individuales de Sueldos (Certificado 1887) por trabajador
    y los empaqueta en un ZIP. Basado en formato cer1887-2023.xls.
    """
    import tempfile
    import zipfile

    conn = db.get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    anio_rentas = anio_tributario - 1
    periodos = [f"{anio_rentas}-{m:02d}" for m in range(1, 13)]
    meses_nombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

    trabajadores = conn.execute("""
        SELECT DISTINCT t.id, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        WHERE l.empresa_id = ? AND l.periodo IN ({})
        ORDER BY t.apellido_paterno, t.nombres
    """.format(",".join("?" * 12)), (empresa_id, *periodos)).fetchall()

    if not trabajadores:
        conn.close()
        return None

    temp_dir = tempfile.mkdtemp()
    archivos = []

    for idx, trab in enumerate(trabajadores, 1):
        tid = trab['id']
        liqs = conn.execute("""
            SELECT periodo, sueldo_calculado, total_imponible, total_haberes,
                   afp_monto, salud_monto, adicional_isapre, afc_trabajador, total_descuentos, liquido,
                   base_tributable, impuesto_unico
            FROM liquidaciones
            WHERE trabajador_id = ? AND empresa_id = ? AND periodo IN ({})
            ORDER BY periodo
        """.format(",".join("?" * 12)), (tid, empresa_id, *periodos)).fetchall()
        factores = db.get_factores_actualizacion(anio_rentas)
        liq_by_mes = {l['periodo']: l for l in liqs}

        wb = Workbook()
        ws = wb.active
        ws.title = "Certificado Sueldos"

        # Encabezado empresa
        ws['A1'] = emp['razon_social']
        ws['A1'].font = Font(bold=True, size=12)
        ws['A2'] = emp['rut']
        ws['A3'] = f"{emp.get('direccion') or ''}, {emp.get('comuna') or ''}"
        ws['A4'] = emp.get('ciudad') or ""

        ws.merge_cells('A6:H6')
        ws['A6'] = f"CERTIFICADO N° {idx} SOBRE SUELDOS Y OTRAS RENTAS"
        ws['A6'].font = Font(bold=True, size=12)
        ws['A6'].alignment = Alignment(horizontal='center')

        ws['A8'] = f"Certificado Nº: {idx}"
        ws['A9'] = f"{emp.get('ciudad') or 'SANTIAGO'},  {C.fecha_larga()}"

        nombre_completo = f"{trab['apellido_paterno'] or ''} {trab['apellido_materno'] or ''} {trab['nombres'] or ''}".strip()
        ws['A11'] = f"El empleador, Habilitado o Pagador, {emp['razon_social']}, RUT {emp['rut']},"
        ws['A12'] = f"certifica que a don/ña {nombre_completo} RUT Nº: {trab['rut']},"
        ws['A13'] = f"durante el año {anio_rentas}, se le han pagado las siguientes rentas:"

        # Cabecera tabla mensual
        headers = ["Mes", "Renta Imponible", "Cotizaciones (AFP+Salud 7%+AFC)", "Renta Neta (Base Tributable)",
                   "Impuesto Único Retenido", "Factor Actualización", "Renta Neta Actualizada", "Impuesto Actualizado"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=15, column=col, value=h)
            cell.font = Font(bold=True, size=9)
            cell.border = Border(bottom=Side(style='thin'))

        tots = [0] * 7
        for m, nombre in enumerate(meses_nombres, 1):
            per = f"{anio_rentas}-{m:02d}"
            row = 15 + m
            ws.cell(row=row, column=1, value=nombre)
            if per in liq_by_mes:
                l = liq_by_mes[per]
                fac = float(factores.get(m, 1.0))
                imp = int(l['total_imponible'] or 0)
                base = int(l['base_tributable'] or 0)
                iu = int(l['impuesto_unico'] or 0)
                vals = [imp, imp - base, base, iu, fac, int(round(base * fac)), int(round(iu * fac))]
            else:
                vals = [0, 0, 0, 0, float(factores.get(m, 1.0)), 0, 0]
            for c, v in enumerate(vals, 2):
                cell = ws.cell(row=row, column=c, value=v)
                cell.number_format = '0.000' if c == 6 else '#,##0'
            for k in (0, 1, 2, 3, 5, 6):
                tots[k] += vals[k]
        trow = 28
        ws.cell(row=trow, column=1, value="TOTAL").font = Font(bold=True)
        for col, val in enumerate(tots, 2):
            if col == 6:
                continue
            cell = ws.cell(row=trow, column=col, value=val)
            cell.font = Font(bold=True)
            cell.number_format = '#,##0'

        ws['A30'] = "Se extiende el presente certificado en cumplimiento de lo dispuesto en la Resolución Exenta"
        ws['A31'] = "del Servicio de Impuestos Internos sobre certificados de sueldos y otras rentas."
        ws['A33'] = "_______________________________"
        ws['A34'] = f"{emp.get('representante_legal') or 'Representante Legal'}"
        ws['A35'] = f"RUT: {emp.get('rut_representante') or emp['rut']}"
        ws['A36'] = emp['razon_social']

        for col in range(1, 9):
            ws.column_dimensions[get_column_letter(col)].width = 16
        ws.column_dimensions['A'].width = 14

        fname = f"Certificado_1887_{trab['rut'].replace('.', '').replace('-', '')}_{anio_rentas}.xlsx"
        fpath = os.path.join(temp_dir, fname)
        wb.save(fpath)
        archivos.append(fpath)

    conn.close()

    # Empaquetar en ZIP
    with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in archivos:
            zf.write(f, os.path.basename(f))

    # Limpiar temp
    for f in archivos:
        try:
            os.remove(f)
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass

    return ruta_zip


def generar_1887_csv_sii(empresa_id, anio_tributario, ruta):
    """
    Genera CSV para Importador de Datos del SII - Formulario 1887.
    Delimitador punto y coma. Montos enteros sin separador de miles.
    Columnas orientadas a la estructura habitual del importador 1887
    (RUT, nombre, renta neta actualizada, impuesto único, etc.).
    """
    anio_rentas = int(anio_tributario) - 1
    conn = db.get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    # Factores
    fac_rows = conn.execute(
        "SELECT mes, factor FROM factores_actualizacion WHERE anio_rentas=?",
        (anio_rentas,),
    ).fetchall()
    factores = {int(r["mes"]): float(r["factor"]) for r in fac_rows} if fac_rows else {m: 1.0 for m in range(1, 13)}

    periodos = [f"{anio_rentas}-{m:02d}" for m in range(1, 13)]
    trabajadores = conn.execute(f"""
        SELECT DISTINCT t.id, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        WHERE l.empresa_id = ? AND l.periodo IN ({",".join("?"*12)})
        ORDER BY t.apellido_paterno, t.nombres
    """, (empresa_id, *periodos)).fetchall()

    if not trabajadores:
        conn.close()
        return None

    headers = [
        "RUT", "DV", "APELLIDO_PATERNO", "APELLIDO_MATERNO", "NOMBRES",
        "RENTA_TOTAL_NETA_ACTUALIZADA", "IMPUESTO_UNICO_RETENIDO",
        "MAYOR_RETENCION", "RENTA_TOTAL_NO_GRAVADA", "RENTA_EXENTA",
        "COTIZACIONES_PREVISIONALES", "IMPONIBLE_ANUAL",
    ]
    rows = []
    for t in trabajadores:
        t = dict(t)
        dets = conn.execute(f"""
            SELECT periodo, total_imponible, liquido, base_tributable, impuesto_unico,
                   COALESCE(afp_monto,0)+COALESCE(salud_monto,0)+COALESCE(afc_trabajador,0) as cotiz
            FROM liquidaciones
            WHERE trabajador_id=? AND empresa_id=? AND periodo IN ({",".join("?"*12)})
        """, (t["id"], empresa_id, *periodos)).fetchall()
        renta_act = 0.0
        impuesto = 0.0
        cotiz = 0.0
        imponible = 0.0
        for d in dets:
            d = dict(d)
            mes = int(d["periodo"][5:7])
            fac = factores.get(mes, 1.0)
            # renta neta aproximada: líquido o base tributaria según disponibilidad
            base = float(d.get("base_tributable") or 0)
            renta_act += base * fac
            impuesto += float(d.get("impuesto_unico") or 0) * fac
            cotiz += float(d.get("cotiz") or 0)
            imponible += float(d.get("total_imponible") or 0)
        rut_full = (t.get("rut") or "").replace(".", "").replace(" ", "").upper()
        if "-" in rut_full:
            rut_num, dv = rut_full.split("-", 1)
        else:
            rut_num, dv = rut_full, ""
        rows.append([
            rut_num,
            dv,
            t.get("apellido_paterno") or "",
            t.get("apellido_materno") or "",
            t.get("nombres") or "",
            str(int(round(renta_act))),
            str(int(round(impuesto))),
            "0",
            "0",
            "0",
            str(int(round(cotiz))),
            str(int(round(imponible))),
        ])
    conn.close()

    path = Path(ruta)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(headers)
        w.writerows(rows)
    return str(path)


# ------------------------------------------------------------------
# Libro de Remuneraciones Electrónico (DT) — estructura del Suplemento LRE
# ------------------------------------------------------------------
LRE_COLUMNAS = [
    ("Rut trabajador", 1101), ("Fecha inicio contrato", 1102), ("Fecha de término de contrato", 1103),
    ("Causal de término del contrato", 1104), ("Región de prestación de los servicios", 1105),
    ("Comuna de prestación de los servicios", 1106), ("Tipo de impuesto a la renta", 1170),
    ("Técnico extranjero exención de cotizaciones previsionales", 1146), ("Código tipo de jornada", 1107),
    ("Persona con discapacidad/pensionado por invalidez", 1108), ("Pensionado por vejez", 1109),
    ("AFP", 1141), ("IPS (ExINP)", 1142), ("FONASA / ISAPRE", 1143), ("AFC", 1151), ("CCAF", 1110),
    ("Org. Administrador Ley 16.744", 1152), ("Número cargas familiares legales autorizadas", 1111),
    ("Número de cargas familiares maternales", 1112), ("Número de cargas familiares invalidez", 1113),
    ("Tramo asignación familiar", 1114),
] + [(f"Rut organización sindical {i}", 1170 + i) for i in range(1, 11)] + [
    ("Número de días trabajados en el mes", 1115), ("Número días de licencia médica en el mes", 1116),
    ("Número días de vacaciones en el mes", 1117), ("Subsidio trabajador Joven", 1118),
    ("Puesto trabajo pesado", 1154), ("Ahorro previsional voluntario individual", 1155),
    ("Ahorro previsional voluntario colectivo", 1157), ("Indemnización a todo evento (Art 164)", 1131),
    ("Tasa indemnización a todo evento (Art 164)", 1132),
    ("Sueldo", 2101), ("Sobresueldo", 2102), ("Comisiones mensual", 2103), ("Semana corrida mensual (Art 45)", 2104),
    ("Participación mensual", 2105), ("Gratificación mensual", 2106), ("Recargo 30% día domingo (Art. 38)", 2107),
    ("Remuneración variable pagada en vacaciones (Art 71)", 2108),
    ("Remuneración variable pagada en clausura (Art. 38 DFL 2)", 2109), ("Aguinaldo", 2110),
    ("Bonos u otras remuneraciones fijas mensuales", 2111), ("Tratos mensual", 2112),
    ("Bonos u otras remuneraciones variables mensuales o superiores a un mes", 2113),
    ("Ejercicio opción no pactada en contrato (Art. 17 N°8 LIR)", 2114),
    ("Beneficios en especie constitutivos de remuneración", 2115),
    ("Remuneraciones bimestrales (devengo en dos meses)", 2116),
    ("Remuneraciones trimestrales (devengo en tres meses)", 2117),
    ("Remuneraciones cuatrimestrales (devengo en cuatro meses)", 2118),
    ("Remuneraciones semestrales (devengo en seis meses)", 2119),
    ("Remuneraciones anuales (devengo en doce meses)", 2120),
    ("Participación anual (devengo en doce meses)", 2121), ("Gratificación anual (devengo en doce meses)", 2122),
    ("Otras remuneraciones superiores a un mes", 2123), ("Pago por horas de trabajo sindical", 2124),
    ("Sueldo empresarial", 2161),
    ("Subsidio por incapacidad laboral por licencia médica - total mensual", 2201),
    ("Beca de estudio (Art. 17 N°18 LIR)", 2202), ("Gratificaciones de zona (Art.17 N°27)", 2203),
    ("Otros ingresos no constitutivos de renta (Art 17 N°29 LIR)", 2204),
    ("Colación total mensual (Art 41)", 2301), ("Movilización total mensual (Art 41)", 2302),
    ("Viáticos total mensual (Art 41)", 2303), ("Asignación de pérdida de caja total mensual (Art 41)", 2304),
    ("Asignación de desgaste herramientas total mensual (Art 41)", 2305),
    ("Asignación familiar legal total mensual (Art 41)", 2311),
    ("Gastos por causa del trabajo (Art 41 CdT) y gastos de representación (Art. 42 Nº1 LIR)", 2306),
    ("Gastos por cambio de residencia (Art 53)", 2307), ("Sala cuna (Art 203)", 2308),
    ("Asignación trabajo a distancia o teletrabajo", 2309), ("Depósito convenido hasta UF 900", 2347),
    ("Alojamiento por razones de trabajo (Art 17 N°14 LIR)", 2310), ("Asignación de traslación (Art. 17 N°15 LIR)", 2312),
    ("Indemnización por feriado legal", 2313), ("Indemnización años de servicio", 2314),
    ("Indemnización sustitutiva del aviso previo", 2315), ("Indemnización fuero maternal (Art 163 bis)", 2316),
    ("Indemnización a todo evento (Art.164)", 2331),
    ("Indemnizaciones voluntarias tributables", 2417), ("Indemnizaciones contractuales tributables", 2418),
    ("Cotización obligatoria previsional (AFP o IPS)", 3141), ("Cotización obligatoria salud 7%", 3143),
    ("Cotización voluntaria para salud", 3144), ("Cotización AFC -Trabajador", 3151),
    ("Cotizaciones técnico extranjero para seguridad social fuera de Chile", 3146),
    ("Descuento depósito convenido hasta UF 900 anual", 3147),
    ("Cotización ahorro previsional voluntario individual modalidad A", 3155),
    ("Cotización ahorro previsional voluntario individual modalidad B hasta UF 50", 3156),
    ("Cotización ahorro previsional voluntario colectivo modalidad A", 3157),
    ("Cotización ahorro previsional voluntario colectivo modalidad B hasta UF 50", 3158),
    ("Impuesto retenido por remuneraciones", 3161), ("Impuesto retenido por indemnizaciones", 3162),
    ("Mayor retención de impuesto solicitada por el trabajador", 3163),
    ("Impuesto retenido por reliquidación de remuneraciones devengadas en otros períodos mensuales", 3164),
    ("Diferencia de impuesto por reliquidación de remuneraciones devengadas en este período", 3165),
    ("Retención préstamo clase media 2020 (Ley 21.252)", 3166), ("Rebaja zona extrema DL 889", 3167),
] + [(f"Cuota sindical {i}", 3170 + i) for i in range(1, 11)] + [
    ("Crédito social CCAF", 3110), ("Cuota vivienda o educación Art. 58", 3181),
    ("Crédito cooperativas de ahorro (Art 54 Ley Coop.)", 3182),
    ("Otros descuentos autorizados y solicitados por el trabajador", 3183),
    ("Cotización adicional trabajo pesado- trabajador", 3154), ("Donaciones culturales y de reconstrucción", 3184),
    ("Otros descuentos (Art 58)", 3185), ("Pensiones de alimentos", 3186), ("Descuento mujer casada (Art 59)", 3187),
    ("Descuento por anticipos o préstamos", 3188),
    ("Aporte AFC -empleador", 4151), ("Aporte empleador seguro accidentes del trabajo y Ley SANNA (Ley 16.744)", 4152),
    ("Aporte empleador indemnización a todo evento (Art 164)", 4131), ("Aporte adicional trabajo pesado- empleador", 4154),
    ("Aporte empleador seguro invalidez y sobrevivencia", 4155),
    ("Aporte empleador ahorro previsional voluntario colectivo", 4157),
    ("Total haberes", 5201), ("Total haberes imponibles y tributables", 5210),
    ("Total haberes imponibles y no tributables", 5220), ("Total haberes no imponibles y no tributables", 5230),
    ("Total haberes no imponibles y tributables", 5240), ("Total descuentos", 5301),
    ("Total descuentos impuestos a las remuneraciones", 5361),
    ("Total descuentos impuestos por indemnizaciones", 5362),
    ("Total descuentos por cotizaciones del trabajador", 5341), ("Total otros descuentos", 5302),
    ("Total aportes empleador", 5410), ("Total líquido", 5501), ("Total indemnizaciones", 5502),
    ("Total indemnizaciones tributables", 5564), ("Total indemnizaciones no tributables", 5565),
]

# Destino LRE de las cotizaciones Ley 21.735 (criterio usado por proveedores de software mientras la DT no
# publique códigos propios). Cambiar aquí si la DT lo instruye.
LRE_CODIGO_CCI = 4157            # 0,1% cuenta individual
LRE_CODIGO_SEGURO_SOCIAL = 4155  # SIS / expectativa de vida / seguro social / rentabilidad protegida


def generar_lre_csv(empresa_id, periodo, ruta):
    conn = db.get_conn()
    try:
        emp = db.row(conn, "SELECT * FROM empresas WHERE id=?", (empresa_id,))
        if not emp:
            return None
        liqs = db.rows(conn, """
            SELECT l.*, t.rut, t.afp, t.salud, t.isapre, t.numero_cargas, t.tramo_asignacion_familiar,
                   t.pensionado, t.cotiza_afp,
                   c.tipo_contrato, c.fecha_inicio, c.fecha_termino AS contrato_termino, c.jornada_semanal
            FROM liquidaciones l
            JOIN trabajadores t ON l.trabajador_id = t.id
            LEFT JOIN contratos c ON l.contrato_id = c.id
            WHERE l.empresa_id = ? AND l.periodo = ?
            ORDER BY t.apellido_paterno, t.nombres
        """, (empresa_id, periodo))
        fins = db.rows(conn, "SELECT * FROM finiquitos WHERE empresa_id=?", (empresa_id,))
    finally:
        conn.close()
    if not liqs:
        return None

    ini_mes = date(int(periodo[:4]), int(periodo[5:7]), 1)
    fin_mes = C.fin_de_mes(periodo)
    fin_por_trab = {}
    for f in fins:
        ft = C.a_fecha(f.get("fecha_termino"))
        if ft and ini_mes <= ft <= fin_mes:
            fin_por_trab[f["trabajador_id"]] = f

    ccaf = C.LRE_CCAF.get(C.normalizar(emp.get("caja_compensacion")), 0)
    mutual = C.LRE_MUTUAL.get(C.normalizar(emp.get("mutual")), 1)
    headers = [f"{n}({c})" for n, c in LRE_COLUMNAS]
    salida = []
    for l in liqs:
        v = {c: 0 for _, c in LRE_COLUMNAS}
        for c in (1103, 1104, 1132) + tuple(range(1171, 1181)):
            v[c] = ""
        n = lambda x: int(round(float(x or 0)))  # noqa: E731
        fin = fin_por_trab.get(l["trabajador_id"])
        salud_txt = C.normalizar(l.get("salud"))
        es_isapre = salud_txt == "ISAPRE"
        jornada = int(l.get("jornada_semanal") or C.JORNADA_DEFAULT)
        v.update({
            1101: (l.get("rut") or "").replace(".", "").upper(),
            1102: C.fecha_ddmmaaaa(l.get("fecha_inicio"), "/"),
            1105: emp.get("region_codigo") or "", 1106: emp.get("comuna_codigo") or "",
            1170: 1, 1107: 201 if jornada <= 30 else 101, 1108: 0,
            1109: 1 if l.get("pensionado") else 0,
            1141: C.LRE_AFP.get(l.get("afp"), 100) if l.get("cotiza_afp", 1) else 100,
            1142: 0,
            1143: C.LRE_SALUD.get(C.normalizar(l.get("isapre")), 102) if es_isapre else 102,
            1151: 0 if l.get("pensionado") else 1, 1110: ccaf, 1152: mutual,
            1111: n(l.get("numero_cargas")), 1114: l.get("tramo_asignacion") or l.get("tramo_asignacion_familiar") or "D",
            1115: n(l.get("dias_trabajados") or 30),
            2101: n(l.get("sueldo_calculado")), 2102: n(l.get("monto_horas_extras")), 2106: n(l.get("gratificacion")),
            2111: n(l.get("otros_haberes")), 2301: n(l.get("colacion")), 2302: n(l.get("movilizacion")),
            2311: n(l.get("asignacion_familiar")),
            3141: n(l.get("afp_monto")), 3143: n(l.get("salud_monto")), 3144: n(l.get("adicional_isapre")),
            3151: n(l.get("afc_trabajador")), 3161: n(l.get("impuesto_unico")), 3188: n(l.get("anticipo")),
            4151: n(l.get("afc_empleador")), 4152: n(l.get("mutual_monto")),
        })
        v[LRE_CODIGO_SEGURO_SOCIAL] += n(l.get("sis_monto")) + n(l.get("reforma_seguro_social")) + n(l.get("reforma_crp"))
        v[LRE_CODIGO_CCI] += n(l.get("reforma_afp_emp"))
        if fin:
            v[1103] = C.fecha_ddmmaaaa(fin.get("fecha_termino"), "/")
            v[1104] = fin.get("causal_codigo") or ""
            v[2313] = n(fin.get("vacaciones_proporcionales_monto"))
            v[2314] = n(fin.get("indemnizacion_anos")) - n(fin.get("descuento_afc"))
            v[2315] = n(fin.get("aviso_previo"))
        indemn = v[2313] + v[2314] + v[2315]
        v[5210] = v[2101] + v[2102] + v[2106] + v[2111]
        v[5230] = v[2301] + v[2302] + v[2311] + indemn
        v[5201] = v[5210] + v[5230]
        v[5341] = v[3141] + v[3143] + v[3144] + v[3151]
        v[5361] = v[3161]
        v[5302] = v[3188]
        v[5301] = v[5341] + v[5361] + v[5302]
        v[5410] = v[4151] + v[4152] + v[4155] + v[4157]
        v[5502] = indemn
        v[5565] = indemn
        v[5501] = v[5201] - v[5301]
        salida.append([v[c] for _, c in LRE_COLUMNAS])

    path = Path(ruta)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(headers)
        w.writerows(salida)
    return str(path)

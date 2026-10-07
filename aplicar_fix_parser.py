#!/usr/bin/env python3
"""
aplicar_fix_parser.py — Amplía el parser de PDF de Previred
Agrega lectura de: tope_inp, renta_minima, tasa_ccaf_salud, af_tramos.
"""
from pathlib import Path
import shutil
from datetime import datetime
import re
import sys

ARCHIVO = Path("remu/pdf_indicadores.py")


def log(m): print(f"[INFO] {m}")
def ok(m):  print(f"[OK]   {m}")
def err(m): print(f"[ERR]  {m}")


NUEVA_FUNCION = '''def parse_texto(text: str) -> dict:
    uf = _uf(text)
    utm = _utm(text, uf)

    tope_afp_match = re.search(r"afiliados a una AFP.*?\\$\\s*([\\d.]+)", text, re.IGNORECASE | re.DOTALL)
    tope_afp = float(tope_afp_match.group(1).replace(".", "")) if tope_afp_match else None

    tope_afc_match = re.search(r"Seguro de Cesant[ií]a.*?\\$\\s*([\\d.]+)", text, re.IGNORECASE | re.DOTALL)
    tope_afc = float(tope_afc_match.group(1).replace(".", "")) if tope_afc_match else None

    # NUEVO: Tope IPS ex-INP
    tope_inp_match = re.search(r"afiliados al IPS.*?\\$\\s*([\\d.]+)", text, re.IGNORECASE | re.DOTALL)
    if not tope_inp_match:
        tope_inp_match = re.search(r"IPS\\s*\\(?ex-?INP\\)?.*?\\$\\s*([\\d.]+)", text, re.IGNORECASE | re.DOTALL)
    tope_inp = float(tope_inp_match.group(1).replace(".", "")) if tope_inp_match else None

    # NUEVO: Renta mínima imponible (IMM)
    renta_minima = None
    for patron in (
        r"Trab\\.?\\s*Dependientes\\s*e?\\s*Independientes.*?\\$\\s*([\\d.]+)",
        r"RENTAS?\\s+M[IÍ]NIMAS?\\s+IMPONIBLES.*?\\$\\s*([\\d.]+)",
        r"Renta\\s+m[ií]nima.*?\\$\\s*([\\d.]+)",
    ):
        m = re.search(patron, text, re.IGNORECASE | re.DOTALL)
        if m:
            valor = float(m.group(1).replace(".", ""))
            if 300_000 <= valor <= 2_000_000:
                renta_minima = valor
                break

    # NUEVO: Tasa CCAF
    tasa_ccaf = None
    for patron in (
        r"CCAF\\s+([\\d,]+)\\s*%",
        r"CCAF.*?([\\d,]+)\\s*%",
        r"Cajas?\\s+de\\s+Compensaci[oó]n.*?([\\d,]+)\\s*%",
    ):
        m = re.search(patron, text, re.IGNORECASE)
        if m:
            val = float(m.group(1).replace(",", "."))
            if 0.5 <= val <= 7.0:
                tasa_ccaf = val
                break

    # NUEVO: Asignación familiar (tramos A, B, C)
    af_tramos = {}
    for tramo in ["A", "B", "C"]:
        m = re.search(rf"Tramo\\s+{tramo}\\s*:?\\s*\\$?\\s*([\\d.]+)", text, re.IGNORECASE)
        if not m:
            m = re.search(rf"Tramo\\s+{tramo}.*?\\$\\s*([\\d.]+)", text, re.IGNORECASE | re.DOTALL)
        if m:
            af_tramos[tramo] = float(m.group(1).replace(".", ""))

    sis_match = re.search(r"Tasa SIS\\s*([\\d,]+)\\s*%", text, re.IGNORECASE)
    sis = float(sis_match.group(1).replace(",", ".")) if sis_match else None

    afp_tasas = {}
    for afp in ["Capital", "Cuprum", "Habitat", "PlanVital", "Provida", "Modelo", "Uno"]:
        m = re.search(rf"{afp}\\s+([\\d,]+)\\s*%", text)
        if m:
            afp_tasas[afp] = float(m.group(1).replace(",", "."))

    faltantes = [k for k, v in (
        ("uf", uf), ("utm", utm), ("tope_afp", tope_afp), ("tope_afc", tope_afc),
        ("tope_inp", tope_inp), ("renta_minima", renta_minima), ("tasa_ccaf", tasa_ccaf),
    ) if v is None]

    return {
        "uf": uf, "utm": utm, "tope_afp": tope_afp, "tope_afc": tope_afc,
        "tope_inp": tope_inp, "renta_minima": renta_minima,
        "tasa_ccaf_salud": tasa_ccaf, "af_tramos": af_tramos,
        "sis_tasa": sis, "afp_tasas": afp_tasas,
        "faltantes": faltantes,
        "texto_completo": text[:500],
    }
'''


def main():
    if not ARCHIVO.exists():
        err(f"No se encuentra {ARCHIVO.resolve()}")
        sys.exit(1)

    log("Leyendo pdf_indicadores.py...")
    contenido = ARCHIVO.read_text(encoding="utf-8")
    ok(f"Leídas {len(contenido):,} caracteres")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ARCHIVO.with_name(f"pdf_indicadores_backup_{ts}.py")
    shutil.copy(ARCHIVO, backup)
    ok(f"Respaldo: {backup.name}")

    # Buscar la función parse_texto y reemplazarla
    patron = re.compile(
        r"def parse_texto\(text: str\) -> dict:.*?(?=\ndef |\Z)",
        re.DOTALL,
    )

    if not patron.search(contenido):
        err("No se encontró 'def parse_texto(...)' en el archivo")
        sys.exit(1)

    contenido = patron.sub(NUEVA_FUNCION + "\n", contenido, count=1)
    ok("parse_texto reemplazada")

    # Guardar
    log("")
    log("Validando sintaxis...")
    try:
        compile(contenido, str(ARCHIVO), "exec")
        ok("✓ Sintaxis válida")
    except SyntaxError as e:
        err(f"✗ SyntaxError: {e}")
        err(f"   Línea: {e.lineno}")
        err(f"Restaurar: Copy-Item {backup.name} remu\\pdf_indicadores.py -Force")
        sys.exit(1)

    ARCHIVO.write_text(contenido, encoding="utf-8")
    ok("Archivo guardado")

    # Verificación
    log("")
    log("═══════════════════════════════════════════════")
    log("  VERIFICACIÓN FINAL")
    log("═══════════════════════════════════════════════")

    final = ARCHIVO.read_text(encoding="utf-8")
    checks = [
        ('"tope_inp": tope_inp', "Tope IPS ex-INP"),
        ('"renta_minima": renta_minima', "Renta mínima (IMM)"),
        ('"tasa_ccaf_salud": tasa_ccaf', "Tasa CCAF"),
        ('"af_tramos": af_tramos', "Asignación familiar"),
    ]
    todos_ok = True
    for pat, desc in checks:
        if pat in final:
            ok(f"✓ {desc}")
        else:
            err(f"✗ FALTA: {desc}")
            todos_ok = False

    log("")
    if todos_ok:
        ok("🎉 Fix del parser aplicado correctamente")
        ok(f"   Respaldo: {backup.name}")
    else:
        err("⚠ Algunos checks fallaron")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INTERRUMPIDO]")
        sys.exit(1)
    except Exception as e:
        err(f"Error: {e}")
        sys.exit(1)
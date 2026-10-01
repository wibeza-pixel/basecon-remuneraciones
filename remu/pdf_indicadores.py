"""Lectura del PDF de indicadores previsionales de Previred."""
import re

import pdfplumber

MESES = {m: i + 1 for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                         "septiembre", "octubre", "noviembre", "diciembre"])}
_NUM = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?"


def _num(entero: str, dec: str | None = None) -> float:
    return float(entero.replace(".", "") + (("." + dec) if dec else ""))


def _uf(text: str):
    """La UF con la fecha más reciente del PDF ('Al 30 de septiembre del 2026: $ 41.057,22'): es la que Previred
    usa para los topes del periodo. Si el PDF trae una sola UF, se usa esa."""
    encontrados = []
    for m in re.finditer(r"Al\s+(\d{1,2})\s+de\s+([a-záéíóú]+)\s+del?\s+(\d{4})\s*:?\s*\$?\s*" + _NUM, text, re.IGNORECASE):
        mes = MESES.get(m.group(2).lower())
        if mes:
            encontrados.append(((int(m.group(3)), mes, int(m.group(1))), _num(m.group(4), m.group(5))))
    encontrados = [e for e in encontrados if 10_000 < e[1] < 200_000]
    if encontrados:
        return max(encontrados)[1]
    for pat in (r"Valor UF.*?\$\s*" + _NUM, r"\bUF\b.*?\$\s*" + _NUM):
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            return _num(m.group(1), m.group(2))
    return None


def _utm(text: str, uf: float | None):
    """Primer valor después de 'UTM' que sea coherente con la UF (la UTM es ~1,75 UF). Así no se confunde
    con la UF, la UTA ni otros montos cercanos."""
    for m in re.finditer(r"UTM|Unidad Tributaria Mensual", text, re.IGNORECASE):
        ventana = text[m.end(): m.end() + 300]
        for n in re.finditer(r"\$?\s*" + _NUM, ventana):
            v = _num(n.group(1), None)
            if 40_000 <= v <= 300_000 and (not uf or 1.4 <= v / uf <= 2.2):
                return v
    return None


def parse_texto(text: str) -> dict:
    uf = _uf(text)
    utm = _utm(text, uf)

    tope_afp_match = re.search(r"afiliados a una AFP.*?\$\s*([\d.]+)", text, re.IGNORECASE | re.DOTALL)
    tope_afp = float(tope_afp_match.group(1).replace(".", "")) if tope_afp_match else None

    tope_afc_match = re.search(r"Seguro de Cesant[ií]a.*?\$\s*([\d.]+)", text, re.IGNORECASE | re.DOTALL)
    tope_afc = float(tope_afc_match.group(1).replace(".", "")) if tope_afc_match else None

    sis_match = re.search(r"Tasa SIS\s*([\d,]+)\s*%", text, re.IGNORECASE)
    sis = float(sis_match.group(1).replace(",", ".")) if sis_match else None

    afp_tasas = {}
    for afp in ["Capital", "Cuprum", "Habitat", "PlanVital", "Provida", "Modelo", "Uno"]:
        m = re.search(rf"{afp}\s+([\d,]+)\s*%", text)
        if m:
            afp_tasas[afp] = float(m.group(1).replace(",", "."))

    return {
        "uf": uf, "utm": utm, "tope_afp": tope_afp, "tope_afc": tope_afc, "sis_tasa": sis, "afp_tasas": afp_tasas,
        "faltantes": [k for k, v in (("uf", uf), ("utm", utm), ("tope_afp", tope_afp), ("tope_afc", tope_afc)) if v is None],
        "texto_completo": text[:500],
    }


def parse_indicadores_pdf(uploaded_file):
    """Lee el PDF de indicadores Previred y extrae los valores."""
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            text = "".join((page.extract_text() or "") + "\n" for page in pdf.pages)
        return parse_texto(text)
    except Exception as e:
        return {"error": str(e)}

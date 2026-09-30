"""Lectura del PDF de indicadores previsionales de Previred."""
import re

import pdfplumber


def parse_indicadores_pdf(uploaded_file):
    """Lee PDF de indicadores Previred y extrae valores"""
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Extracciones con regex (tolerantes a formato Previred)
        uf = None
        for pat in [
            r'Al 31 de \w+ del \d{4}:\s*\$\s*([\d.]+,\d+)',
            r'Valor UF.*?\$\s*([\d.]+,\d+)',
            r'\bUF\b.*?\$\s*([\d.]+,\d+)',
        ]:
            uf_match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if uf_match:
                uf = float(uf_match.group(1).replace(".", "").replace(",", "."))
                break

        utm = None
        for pat in [
            r'UTM\s*\$?\s*([\d.]+)',
            r'Unidad Tributaria Mensual.*?\$\s*([\d.]+)',
            r'UTM.*?([\d]{2,3}\.[\d]{3})',
        ]:
            utm_match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if utm_match:
                utm = float(utm_match.group(1).replace(".", ""))
                break

        tope_afp_match = re.search(r'afiliados a una AFP.*?\$\s*([\d.]+)', text, re.IGNORECASE | re.DOTALL)
        tope_afp = float(tope_afp_match.group(1).replace(".", "")) if tope_afp_match else None

        tope_afc_match = re.search(r'Seguro de Cesant[ií]a.*?\$\s*([\d.]+)', text, re.IGNORECASE | re.DOTALL)
        tope_afc = float(tope_afc_match.group(1).replace(".", "")) if tope_afc_match else None

        sis_match = re.search(r'Tasa SIS\s*([\d,]+)\s*%', text, re.IGNORECASE)
        sis = float(sis_match.group(1).replace(",", ".")) if sis_match else None

        # AFP tasas
        afp_tasas = {}
        for afp in ["Capital", "Cuprum", "Habitat", "PlanVital", "Provida", "Modelo", "Uno"]:
            m = re.search(rf'{afp}\s+([\d,]+)\s*%', text)
            if m:
                afp_tasas[afp] = float(m.group(1).replace(",", "."))

        return {
            "uf": uf,
            "utm": utm,
            "tope_afp": tope_afp,
            "tope_afc": tope_afc,
            "sis_tasa": sis,
            "afp_tasas": afp_tasas,
            "faltantes": [k for k, v in (("uf", uf), ("utm", utm), ("tope_afp", tope_afp), ("tope_afc", tope_afc)) if v is None],
            "texto_completo": text[:500]
        }
    except Exception as e:
        return {"error": str(e)}

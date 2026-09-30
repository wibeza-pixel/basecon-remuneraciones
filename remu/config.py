"""
Parámetros, tablas de códigos y utilidades comunes.

Todo lo que cambia por ley o por instructivo está aquí (o en la tabla `indicadores`),
no repartido por el código.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
DB_PATH = DATA_DIR / "remuneraciones.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# Impuesto Único de Segunda Categoría — tabla mensual en UTM
# (art. 43 N°1 LIR, tramos vigentes desde la Ley 21.210)
# (desde_utm, hasta_utm, factor, rebaja_utm)
# ------------------------------------------------------------------
TABLA_IU_UTM = [
    (0.0, 13.5, 0.0, 0.0),
    (13.5, 30.0, 0.04, 0.54),
    (30.0, 50.0, 0.08, 1.74),
    (50.0, 70.0, 0.135, 4.49),
    (70.0, 90.0, 0.23, 11.14),
    (90.0, 120.0, 0.304, 17.80),
    (120.0, 310.0, 0.35, 23.32),
    (310.0, float("inf"), 0.40, 38.82),
]

# Asignación familiar (valores por defecto; se sobreescriben con indicadores.af_tramos)
AF_TRAMOS_DEFAULT = {
    "A": {"monto": 22601, "renta_max": 649039},
    "B": {"monto": 13870, "renta_max": 947990},
    "C": {"monto": 4382, "renta_max": 1478539},
    "D": {"monto": 0, "renta_max": 999999999},
}

AFP_TASAS_DEFAULT = {
    "Capital": 11.44, "Cuprum": 11.44, "Habitat": 11.27,
    "PlanVital": 11.16, "Provida": 11.45, "Modelo": 10.58, "Uno": 10.46,
}
AFPS = ["Capital", "Cuprum", "Habitat", "Modelo", "PlanVital", "Provida", "Uno"]

# Distribución del 7% de salud Fonasa cuando la empresa está afiliada a CCAF.
# Fuente: Previred, Formato Largo Variable v82 (campo 90: "Cotización Obligatoria del 5,2%").
# Editable por periodo en Indicadores (columna tasa_ccaf_salud).
TASA_CCAF_SALUD_DEFAULT = 5.2

# Gratificación art. 50: 25% con tope 4,75 IMM anual
GRATIF_ART50_PCT = 0.25
GRATIF_ART50_TOPE_IMM = 4.75
TIPOS_GRATIFICACION = ["Art. 50 (25% con tope 4,75 IMM)", "Monto fijo pactado", "Sin gratificación"]

# Seguro de cesantía (Ley 19.728)
AFC_INDEF_TRAB = 0.006
AFC_INDEF_EMP = 0.024
AFC_PLAZO_EMP = 0.03
AFC_EMP_DESPUES_11 = 0.008  # tras 11 años de cotización el empleador aporta solo al Fondo Solidario

TIPOS_CONTRATO = ["Indefinido", "Plazo Fijo", "Obra o faena"]
CONTRATOS_PLAZO = ("Plazo Fijo", "Obra o faena")


def jornada_maxima(fecha: date) -> int:
    """Jornada ordinaria máxima semanal según Ley 21.561 (40 horas)."""
    if fecha < date(2024, 4, 26):
        return 45
    if fecha < date(2026, 4, 26):
        return 44
    if fecha < date(2028, 4, 26):
        return 42
    return 40


JORNADA_DEFAULT = jornada_maxima(date.today())

# ------------------------------------------------------------------
# Códigos Previred (Formato Largo Variable por Separador, v82)
# ------------------------------------------------------------------
PREVIRED_AFP = {"Cuprum": "03", "Habitat": "05", "Provida": "08", "PlanVital": "29",
                "Capital": "33", "Modelo": "34", "Uno": "35"}
PREVIRED_SALUD = {"SIN ISAPRE": "00", "BANMEDICA": "01", "CONSALUD": "02", "VIDA TRES": "03",
                  "COLMENA": "04", "CRUZ BLANCA": "05", "FONASA": "07", "NUEVA MASVIDA": "10",
                  "ISALUD": "11", "FUNDACION": "12", "CRUZ DEL NORTE": "25", "ESENCIAL": "28"}
PREVIRED_CCAF = {"": "00", "LOS ANDES": "01", "LA ARAUCANA": "02", "LOS HEROES": "03", "18 DE SEPTIEMBRE": "04"}
PREVIRED_MUTUAL = {"ISL": "00", "ACHS": "01", "MUTUAL DE SEGURIDAD": "02", "IST": "03"}

# ------------------------------------------------------------------
# Códigos LRE (Suplemento Libro de Remuneraciones Electrónico, DT)
# ------------------------------------------------------------------
LRE_AFP = {"Provida": 6, "PlanVital": 11, "Cuprum": 13, "Habitat": 14, "Uno": 19, "Capital": 31, "Modelo": 103}
LRE_SALUD = {"FONASA": 102, "CRUZ BLANCA": 1, "BANMEDICA": 3, "COLMENA": 4, "CONSALUD": 9, "VIDA TRES": 12,
             "CRUZ DEL NORTE": 38, "FUNDACION": 40, "NUEVA MASVIDA": 43}
LRE_CCAF = {"": 0, "LOS ANDES": 1, "LA ARAUCANA": 2, "LOS HEROES": 3, "18 DE SEPTIEMBRE": 4}
LRE_MUTUAL = {"ISL": 0, "ACHS": 1, "MUTUAL DE SEGURIDAD": 2, "IST": 3}

ISAPRES = ["BANMEDICA", "COLMENA", "CONSALUD", "CRUZ BLANCA", "CRUZ DEL NORTE", "ESENCIAL",
           "FUNDACION", "ISALUD", "NUEVA MASVIDA", "VIDA TRES"]
CCAFS = ["", "LOS ANDES", "LA ARAUCANA", "LOS HEROES", "18 DE SEPTIEMBRE"]
MUTUALES = ["ACHS", "MUTUAL DE SEGURIDAD", "IST", "ISL"]

# Causales de término: (etiqueta, código LRE, da años de servicio, da aviso previo)
CAUSALES = [
    ("Art. 159 N°1 — Mutuo acuerdo de las partes", 3, False, False),
    ("Art. 159 N°2 — Renuncia del trabajador", 4, False, False),
    ("Art. 159 N°3 — Muerte del trabajador", 5, False, False),
    ("Art. 159 N°4 — Vencimiento del plazo convenido", 6, False, False),
    ("Art. 159 N°5 — Conclusión del trabajo o servicio", 7, False, False),
    ("Art. 159 N°6 — Caso fortuito o fuerza mayor", 8, False, False),
    ("Art. 160 N°1 — Conductas indebidas graves", 24, False, False),
    ("Art. 160 N°3 — No concurrencia a las labores", 12, False, False),
    ("Art. 160 N°4 — Abandono del trabajo", 13, False, False),
    ("Art. 160 N°7 — Incumplimiento grave de las obligaciones", 16, False, False),
    ("Art. 161 inc. 1 — Necesidades de la empresa", 18, True, True),
    ("Art. 161 inc. 2 — Desahucio escrito del empleador", 19, True, True),
    ("Art. 163 bis — Procedimiento concursal de liquidación", 20, True, True),
]
CAUSAL_POR_ETIQUETA = {c[0]: c for c in CAUSALES}

# Feriados legales (para convertir días hábiles de feriado a corridos). Editables en la app.
FERIADOS_DEFAULT = [
    ("2026-01-01", "Año Nuevo"), ("2026-04-03", "Viernes Santo"), ("2026-04-04", "Sábado Santo"),
    ("2026-05-01", "Día del Trabajo"), ("2026-05-21", "Glorias Navales"),
    ("2026-06-21", "Día de los Pueblos Indígenas"), ("2026-06-29", "San Pedro y San Pablo"),
    ("2026-07-16", "Virgen del Carmen"), ("2026-08-15", "Asunción de la Virgen"),
    ("2026-09-18", "Independencia Nacional"), ("2026-09-19", "Glorias del Ejército"),
    ("2026-10-12", "Encuentro de Dos Mundos"), ("2026-10-31", "Iglesias Evangélicas"),
    ("2026-11-01", "Todos los Santos"), ("2026-12-08", "Inmaculada Concepción"), ("2026-12-25", "Navidad"),
    ("2027-01-01", "Año Nuevo"), ("2027-03-26", "Viernes Santo"), ("2027-03-27", "Sábado Santo"),
    ("2027-05-01", "Día del Trabajo"), ("2027-05-21", "Glorias Navales"),
    ("2027-06-21", "Día de los Pueblos Indígenas"), ("2027-06-28", "San Pedro y San Pablo"),
    ("2027-07-16", "Virgen del Carmen"), ("2027-08-15", "Asunción de la Virgen"),
    ("2027-09-18", "Independencia Nacional"), ("2027-09-19", "Glorias del Ejército"),
    ("2027-10-11", "Encuentro de Dos Mundos"), ("2027-10-31", "Iglesias Evangélicas"),
    ("2027-11-01", "Todos los Santos"), ("2027-12-08", "Inmaculada Concepción"), ("2027-12-25", "Navidad"),
]

MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"]


# ------------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------------
def a_fecha(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v)[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def fecha_larga(d=None) -> str:
    """'30 de septiembre de 2026' (independiente del locale del servidor)."""
    d = a_fecha(d) or date.today()
    return f"{d.day} de {MESES_ES[d.month - 1]} de {d.year}"


def fecha_ddmmaaaa(d, sep="-") -> str:
    d = a_fecha(d)
    return d.strftime(f"%d{sep}%m{sep}%Y") if d else ""


def mes_anio_es(periodo: str) -> str:
    try:
        a, m = int(periodo[:4]), int(periodo[5:7])
        return f"{MESES_ES[m - 1].upper()} / {a}"
    except Exception:
        return periodo


def fin_de_mes(periodo: str) -> date:
    import calendar
    a, m = int(periodo[:4]), int(periodo[5:7])
    return date(a, m, calendar.monthrange(a, m)[1])


def fmt_clp(n) -> str:
    try:
        return f"{int(round(float(n or 0))):,}".replace(",", ".")
    except Exception:
        return "0"


def normalizar(s) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.upper().split())


def rut_partes(rut: str) -> tuple[str, str]:
    r = (rut or "").replace(".", "").replace(" ", "").upper()
    if "-" in r:
        num, dv = r.split("-", 1)
    else:
        num, dv = r[:-1], r[-1:]
    return num, dv


def rut_valido(rut: str) -> bool:
    num, dv = rut_partes(rut)
    if not num.isdigit() or not dv:
        return False
    s, m = 0, 2
    for d in reversed(num):
        s += int(d) * m
        m = 2 if m == 7 else m + 1
    r = 11 - s % 11
    esperado = "0" if r == 11 else "K" if r == 10 else str(r)
    return dv == esperado


def edad(fecha_nac, al: date) -> int | None:
    f = a_fecha(fecha_nac)
    if not f:
        return None
    return al.year - f.year - ((al.month, al.day) < (f.month, f.day))

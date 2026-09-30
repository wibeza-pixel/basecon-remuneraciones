from remu.calculos import (calcular_liquidacion, gratificacion_art50, impuesto_unico, numero_a_palabras,
                           tasas_reforma_ley_21735)

UTM = 71649
IND = dict(uf=40864.55, utm=UTM, tope_afp=3676031, tope_afc=5522215, sis_tasa=0.0, renta_minima=553553,
           afp_tasas={"Habitat": 11.27, "Provida": 11.45}, tasa_ccaf_salud=5.2)
IND_JUL = dict(IND, sis_tasa=1.88)


def liq(**kw):
    base = dict(sueldo_base=1_200_000, gratificacion=0, movilizacion=50_000, colacion=50_000, otros=0, dias=30,
                afp_nombre="Habitat", salud_tipo="FONASA", isapre_pactado_uf=0, tipo_contrato="Indefinido",
                tasa_mutual=0.93, indicadores=IND, periodo="2026-08", fecha_inicio_contrato="2023-05-01")
    base.update(kw)
    return calcular_liquidacion(**base)


# --- Impuesto único (tabla mensual en UTM) ---
def test_iu_exento_hasta_13_5_utm():
    assert impuesto_unico(13.5 * UTM, UTM) == 0


def test_iu_segundo_tramo():
    # 1.500.000 × 4% − 0,54 UTM
    assert impuesto_unico(1_500_000, UTM) == round(1_500_000 * 0.04 - 0.54 * UTM)


def test_iu_tramo_13_5_pct():
    assert impuesto_unico(5_000_000, UTM) == round(5_000_000 * 0.135 - 4.49 * UTM)


def test_iu_ultimo_tramo():
    b = 320 * UTM
    assert impuesto_unico(b, UTM) == round(b * 0.40 - 38.82 * UTM)


def test_iu_continuidad_entre_tramos():
    for lim in (30, 50, 70, 90, 120, 310):
        a = impuesto_unico(lim * UTM, UTM)
        b = impuesto_unico(lim * UTM + 1, UTM)
        assert 0 <= b - a <= 1


# --- Liquidación ---
def test_liquidacion_descuenta_impuesto_unico():
    r = liq()
    assert r["impuesto_unico"] == impuesto_unico(r["base_tributable"], UTM)
    assert r["liquido"] == r["total_haberes"] - r["afp_monto"] - r["salud_monto"] - r["afc_trabajador"] - r["impuesto_unico"]


def test_base_tributable_resta_afc_y_no_adicional_isapre():
    r = liq(salud_tipo="ISAPRE", isapre_pactado_uf=5)
    assert r["adicional_isapre"] > 0
    assert r["base_tributable"] == r["total_imponible"] - r["afp_monto"] - r["salud_monto"] - r["afc_trabajador"]


def test_gratificacion_art50_con_tope():
    r = liq(tipo_gratificacion="Art. 50 (25% con tope 4,75 IMM)")
    assert r["gratificacion"] == round(4.75 * 553553 / 12)
    assert gratificacion_art50(400_000, 553553) == 100_000


def test_afc_obra_o_faena_como_plazo_fijo():
    r = liq(tipo_contrato="Obra o faena")
    assert r["afc_trabajador"] == 0 and r["afc_empleador"] == round(r["base_afc"] * 0.03)


def test_afc_mas_de_11_anios():
    r = liq(fecha_inicio_contrato="2010-01-01")
    assert r["afc_empleador"] == round(r["base_afc"] * 0.008)
    assert r["afc_trabajador"] == round(r["base_afc"] * 0.006)


def test_pensionado_sin_afc_ni_sis_ni_reforma():
    r = liq(pensionado=True, indicadores=IND_JUL, periodo="2026-07")
    assert r["afc_trabajador"] == r["afc_empleador"] == 0
    assert r["sis_monto"] == r["reforma_crp"] == r["reforma_afp_emp"] == 0


def test_mayor_65_sin_sis():
    r = liq(fecha_nacimiento="1960-01-01", indicadores=IND_JUL, periodo="2026-07")
    assert r["sis_monto"] == 0


def test_etapa_35_no_duplica_sis():
    r = liq(indicadores=dict(IND, sis_tasa=1.88))
    assert r["sis_monto"] == 0
    assert r["reforma_seguro_social"] == round(r["base_afp"] * 0.025)
    assert r["carga_empleador_previsional"] == (r["reforma_afp_emp"] + r["reforma_crp"] + r["reforma_seguro_social"]
                                                + r["afc_empleador"] + r["mutual_monto"])


def test_etapa_1pct_sis_aparte():
    r = liq(indicadores=IND_JUL, periodo="2026-07")
    assert r["sis_monto"] == round(r["base_afp"] * 0.0188)
    assert r["reforma_crp"] == round(r["base_afp"] * 0.009)
    assert tasas_reforma_ley_21735("2025-07")["aplica"] is False


def test_ccaf_divide_salud_fonasa():
    r = liq(afiliado_ccaf=True)
    assert r["salud_ccaf"] == round(r["base_afp"] * 0.052)
    assert r["salud_fonasa"] + r["salud_ccaf"] == r["salud_monto"]


def test_advertencia_jornada_sobre_maximo():
    r = liq(jornada_semanal=45)
    assert any("Ley 21.561" in a for a in r["advertencias"])


def test_advertencia_sueldo_bajo_minimo():
    r = liq(sueldo_base=400_000)
    assert any("ingreso mínimo" in a for a in r["advertencias"])


def test_tope_imponible():
    r = liq(sueldo_base=6_000_000)
    assert r["base_afp"] == 3676031
    assert r["afp_monto"] == round(3676031 * 0.1127)


def test_horas_extras_42h():
    r = liq(horas_extras=10, jornada_semanal=42)
    assert r["monto_horas_extras"] == round(1_200_000 / (42 * 30 / 7) * 1.5 * 10)


def test_numero_a_palabras():
    assert numero_a_palabras(1_234_567) == "UN MILLON DOSCIENTOS TREINTA Y CUATRO MIL QUINIENTOS SESENTA Y SIETE"
    assert numero_a_palabras(100) == "CIEN"
    assert numero_a_palabras(21) == "VEINTIUN"
    assert numero_a_palabras(2_000_000) == "DOS MILLONES"

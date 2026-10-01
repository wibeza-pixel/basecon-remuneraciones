from remu import calculadora as CALC
from remu import db


def _ind():
    conn = db.get_conn()
    try:
        return db.get_indicadores("2026-08", conn)
    finally:
        conn.close()


def test_simular_cuadra(base_temporal):
    r = CALC.simular(_ind(), "2026-08", 900_000, colacion=50_000, movilizacion=40_000, afp="Habitat")
    assert r["liquido"] == r["total_haberes"] - r["total_descuentos"]
    assert r["costo_empresa"] > r["total_haberes"]
    assert r["gratificacion"] > 0 and r["colacion"] == 50_000


def test_inverso_vuelve_al_sueldo(base_temporal):
    ind = _ind()
    for base in (539_000, 900_000, 1_850_000, 4_200_000):
        p = dict(colacion=40_000, movilizacion=30_000, afp="Modelo", salud="FONASA")
        liq = CALC.simular(ind, "2026-08", base, **p)["liquido"]
        r = CALC.sueldo_para_liquido(liq, ind, "2026-08", **p)
        assert r["liquido"] >= liq
        assert abs(r["sueldo_base"] - base) <= 2, (base, r["sueldo_base"])


def test_inverso_isapre_y_plazo_fijo(base_temporal):
    ind = _ind()
    r = CALC.sueldo_para_liquido(1_000_000, ind, "2026-08", salud="ISAPRE", plan_isapre_uf=4.5, tipo_contrato="Plazo Fijo")
    assert 1_000_000 <= r["liquido"] <= 1_000_010
    assert r["afc_trabajador"] == 0

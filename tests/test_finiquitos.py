from datetime import date

import pytest

from remu import config as C
from remu.finiquitos import anos_a_pagar, antiguedad, calcular_finiquito, feriado_proporcional_habiles, habiles_a_corridos

FER = {C.a_fecha(f) for f, _ in C.FERIADOS_DEFAULT}
N161 = "Art. 161 inc. 1 — Necesidades de la empresa"


def test_antiguedad_y_anos():
    assert antiguedad(date(2023, 5, 1), date(2026, 9, 30)) == (3, 5, 0)
    assert anos_a_pagar(date(2023, 5, 1), date(2026, 9, 30)) == 3
    assert anos_a_pagar(date(2023, 3, 1), date(2026, 9, 30)) == 4      # fracción de 7 meses
    assert anos_a_pagar(date(2023, 4, 1), date(2026, 9, 30)) == 3      # fracción de 6 meses exactos
    assert anos_a_pagar(date(2026, 1, 1), date(2026, 9, 30)) == 0      # menos de un año
    assert anos_a_pagar(date(2000, 1, 1), date(2026, 9, 30)) == 11     # tope


def test_feriado_proporcional_desde_ultimo_aniversario():
    assert feriado_proporcional_habiles(date(2023, 5, 1), date(2026, 9, 30)) == 6.25


def test_habiles_a_corridos_salta_fin_de_semana_y_feriados():
    # desde jueves 01-10-2026: 1,2,5,6,7,8 = 6 hábiles → 8 corridos (+0,25)
    assert habiles_a_corridos(date(2026, 9, 30), 6.25, FER)[0] == 8.25
    # el 12-10-2026 es feriado
    c, fin = habiles_a_corridos(date(2026, 10, 9), 1, FER)
    assert fin == date(2026, 10, 13) and c == 4


def _fin(**kw):
    base = dict(fecha_inicio="2023-05-01", fecha_termino="2026-09-30", causal=N161, aviso_dado=False,
                sueldo_base=1_000_000, gratificacion_mensual=219_115, colacion=50_000, movilizacion=50_000,
                uf=40_000, dias_feriado_pendientes=0, aporte_afc_empleador=500_000, feriados=FER)
    base.update(kw)
    return calcular_finiquito(**base)


def test_finiquito_161_completo():
    r = _fin()
    base = 1_000_000 + 219_115 + 50_000 + 50_000
    assert r["base_calculo"] == base
    assert r["anos_pagar"] == 3
    assert r["indemnizacion_anos"] == 3 * base
    assert r["aviso_previo"] == base
    assert r["descuento_afc"] == 500_000
    assert r["vacaciones_proporcionales_monto"] == round(1_000_000 / 30 * 8.25)
    assert r["total_finiquito"] == r["indemnizacion_anos"] + r["aviso_previo"] + r["vacaciones_proporcionales_monto"] - 500_000


def test_tope_90_uf():
    r = _fin(sueldo_base=5_000_000)
    assert r["base_con_tope"] == 90 * 40_000
    assert r["indemnizacion_anos"] == 3 * 90 * 40_000


def test_renuncia_solo_feriado():
    r = _fin(causal="Art. 159 N°2 — Renuncia del trabajador")
    assert r["indemnizacion_anos"] == r["aviso_previo"] == r["descuento_afc"] == 0
    assert r["total_finiquito"] == r["vacaciones_proporcionales_monto"]


def test_aviso_dado_no_paga_sustitutiva():
    assert _fin(aviso_dado=True)["aviso_previo"] == 0


def test_afc_no_supera_anos_de_servicio():
    r = _fin(fecha_inicio="2025-12-01", aporte_afc_empleador=900_000)
    assert r["indemnizacion_anos"] == 0 and r["descuento_afc"] == 0


def test_advierte_feriado_pendiente():
    assert any("feriado pendiente" in a for a in _fin()["advertencias"])


def test_fechas_invalidas():
    with pytest.raises(ValueError):
        _fin(fecha_termino="2020-01-01")

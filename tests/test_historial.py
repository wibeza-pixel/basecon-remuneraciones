import json
from datetime import date

import pytest
from docx import Document

from remu import anexos as AN
from remu import archivo as A
from remu import config as C
from remu import db


@pytest.fixture
def ctx(base_temporal, tmp_path):
    conn = db.get_conn()
    eid = db.insert(conn, "empresas", dict(rut="76.065.376-4", razon_social="EMPRESA DOCS SPA", comuna="Santiago"))
    tid = db.insert(conn, "trabajadores", dict(empresa_id=eid, rut="12.345.678-5", nombres="ANA", apellido_paterno="ROJAS",
                                               apellido_materno="LAGOS", afp="Habitat", salud="FONASA"))
    cid = db.insert(conn, "contratos", dict(trabajador_id=tid, empresa_id=eid, cargo="VENDEDORA", fecha_inicio="2026-03-01",
                                            fecha_termino="2026-08-31", tipo_contrato="Plazo Fijo", sueldo_base=600_000,
                                            jornada_semanal=42))
    conn.commit()
    emp = db.row(conn, "SELECT * FROM empresas WHERE id=?", (eid,))
    trab = db.row(conn, "SELECT * FROM trabajadores WHERE id=?", (tid,))
    cont = db.row(conn, "SELECT * FROM contratos WHERE id=?", (cid,))
    yield conn, emp, trab, cont, tmp_path
    conn.close()


def test_guardar_listar_y_recuperar_binario(ctx):
    conn, emp, trab, _, _ = ctx
    pdf = b"%PDF-1.4 licencia \x00\xff binario"
    did = A.guardar(conn, emp["id"], trab["id"], "Licencia médica", "licencia.pdf", pdf, fecha="2026-09-10",
                    descripcion="5 días", origen="subido", usuario="cliente")
    conn.commit()
    lista = A.listar(conn, trab["id"])
    assert len(lista) == 1 and lista[0]["mime"] == "application/pdf" and "contenido" not in lista[0]
    assert A.obtener(conn, did)["contenido"] == pdf
    assert A.uso(conn)["bytes"] == len(pdf)


def test_liquidacion_reemplaza_mismo_periodo(ctx):
    conn, emp, trab, _, _ = ctx
    for v in (b"v1", b"v2"):
        A.guardar(conn, emp["id"], trab["id"], "Liquidación", "liq.docx", v, periodo="2026-09", reemplazar=True)
    A.guardar(conn, emp["id"], trab["id"], "Liquidación", "liq.docx", b"ago", periodo="2026-08", reemplazar=True)
    conn.commit()
    liqs = A.listar(conn, trab["id"], "Liquidación")
    assert sorted(l["periodo"] for l in liqs) == ["2026-08", "2026-09"]
    sep = [l for l in liqs if l["periodo"] == "2026-09"][0]
    assert A.obtener(conn, sep["id"])["contenido"] == b"v2"


def test_subida_demasiado_grande(ctx):
    conn, emp, trab, _, _ = ctx
    with pytest.raises(ValueError):
        A.guardar(conn, emp["id"], trab["id"], "Otro", "x.pdf", b"0" * (A.MAX_SUBIDA_MB * 1024 * 1024 + 1), origen="subido")


def test_anexo_genera_guarda_y_actualiza_contrato(ctx):
    conn, emp, trab, cont, tmp = ctx
    cambios = {"sueldo_base": 700_000, "cargo": "JEFA DE LOCAL", "duracion": "indefinido"}
    err, _ = AN.validar(cont, cambios, renta_minima=553_553)
    assert not err
    r = AN.crear_anexo(conn, emp, trab, cont, date(2026, 9, 1), date(2026, 9, 1), cambios, tmp, usuario="admin")
    c2 = db.row(conn, "SELECT * FROM contratos WHERE id=?", (cont["id"],))
    assert c2["sueldo_base"] == 700_000 and c2["cargo"] == "JEFA DE LOCAL"
    assert c2["tipo_contrato"] == "Indefinido" and c2["fecha_termino"] is None
    docs = A.listar(conn, trab["id"], "Anexo de contrato")
    assert len(docs) == 1 and "sueldo $700.000" in docs[0]["descripcion"]
    texto = "\n".join(p.text for p in Document(r["ruta"]).paragraphs)
    assert "ANEXO DE CONTRATO" in texto and "700.000" in texto and "duración indefinida" in texto


def test_anexo_validaciones(ctx):
    conn, emp, trab, cont, tmp = ctx
    err, _ = AN.validar(cont, {}, 553_553)
    assert err
    err, _ = AN.validar(cont, {"sueldo_base": 400_000}, 553_553)
    assert any("mínimo" in e for e in err)
    err, _ = AN.validar(cont, {"jornada_semanal": 45}, 553_553)
    assert any("jornada" in e.lower() for e in err)
    AN.crear_anexo(conn, emp, trab, cont, date(2026, 8, 25), date(2026, 9, 1), {"duracion": "2026-11-30"}, tmp)
    cont = db.row(conn, "SELECT * FROM contratos WHERE id=?", (cont["id"],))
    assert AN.renovaciones(conn, cont["id"]) == 1
    _, av = AN.validar(cont, {"duracion": "2027-02-28"}, 553_553, renovaciones_previas=1)
    assert any("159" in a for a in av)

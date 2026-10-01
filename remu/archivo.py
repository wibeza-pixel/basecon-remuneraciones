"""
Historial de documentos por trabajador.

Los archivos se guardan dentro de la base de datos (BYTEA en Postgres/Supabase, BLOB en SQLite) porque el disco de
Streamlit Cloud se borra en cada reinicio. Se guardan:
- automáticamente al generar contratos, anexos, liquidaciones, comprobantes de feriado y finiquitos;
- a mano, los archivos que el usuario sube (licencias médicas en PDF, contratos firmados escaneados, etc.).

Las liquidaciones se guardan una vez por trabajador y periodo: si se vuelven a generar, reemplazan a la anterior.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import config as C
from . import db

TIPOS_GENERADOS = ["Contrato", "Anexo de contrato", "Liquidación", "Comprobante de vacaciones", "Finiquito"]
TIPOS_SUBIDA = ["Licencia médica", "Contrato firmado", "Anexo firmado", "Finiquito firmado", "Liquidación firmada",
                "Comprobante de vacaciones firmado", "Certificado", "Carta de aviso", "Otro"]
TIPOS = TIPOS_GENERADOS + TIPOS_SUBIDA
EXTENSIONES_SUBIDA = ["pdf", "jpg", "jpeg", "png", "docx", "xlsx"]
MAX_SUBIDA_MB = 5

MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "zip": "application/zip"}


def mime_de(nombre: str) -> str:
    return MIME.get(Path(nombre).suffix.lower().lstrip("."), "application/octet-stream")


def guardar(conn, empresa_id: int, trabajador_id: int, tipo: str, nombre_archivo: str, contenido: bytes,
            periodo: str | None = None, fecha=None, descripcion: str = "", origen: str = "generado",
            ref_tabla: str | None = None, ref_id: int | None = None, usuario: str = "", reemplazar: bool = False) -> int:
    """Guarda un documento. reemplazar=True borra antes los generados del mismo trabajador, tipo y periodo."""
    if not contenido:
        raise ValueError("El archivo está vacío.")
    if origen == "subido" and len(contenido) > MAX_SUBIDA_MB * 1024 * 1024:
        raise ValueError(f"El archivo supera el máximo de {MAX_SUBIDA_MB} MB.")
    if reemplazar:
        conn.execute("DELETE FROM documentos_trabajador WHERE trabajador_id=? AND tipo=? AND origen='generado' "
                     "AND COALESCE(periodo, '')=?", (trabajador_id, tipo, periodo or ""))
    return db.insert(conn, "documentos_trabajador", dict(
        empresa_id=empresa_id, trabajador_id=trabajador_id, tipo=tipo, periodo=periodo,
        fecha=C.a_fecha(fecha) or date.today(), descripcion=descripcion or "", nombre_archivo=nombre_archivo,
        mime=mime_de(nombre_archivo), tamano=len(contenido), contenido=bytes(contenido), origen=origen,
        ref_tabla=ref_tabla, ref_id=ref_id, creado_por=usuario or ""))


def guardar_archivo(conn, empresa_id, trabajador_id, tipo, ruta, **kw) -> int:
    """Guarda un archivo generado en disco (contrato, liquidación, etc.)."""
    ruta = Path(ruta)
    return guardar(conn, empresa_id, trabajador_id, tipo, ruta.name, ruta.read_bytes(), **kw)


def listar(conn, trabajador_id: int, tipo: str | None = None) -> list[dict]:
    """Documentos del trabajador, del más reciente al más antiguo (sin el contenido)."""
    sql = ("SELECT id, tipo, periodo, fecha, descripcion, nombre_archivo, mime, tamano, origen, ref_tabla, ref_id, "
           "creado_por, created_at FROM documentos_trabajador WHERE trabajador_id=?")
    p = [trabajador_id]
    if tipo:
        sql += " AND tipo=?"
        p.append(tipo)
    return db.rows(conn, sql + " ORDER BY fecha DESC, id DESC", p)


def obtener(conn, doc_id: int) -> dict | None:
    d = db.row(conn, "SELECT * FROM documentos_trabajador WHERE id=?", (doc_id,))
    if d and d.get("contenido") is not None:
        d["contenido"] = bytes(d["contenido"])  # Postgres devuelve memoryview
    return d


def eliminar(conn, doc_id: int):
    conn.execute("DELETE FROM documentos_trabajador WHERE id=?", (doc_id,))


def uso(conn, empresa_ids: list[int] | None = None) -> dict:
    """Espacio usado por los documentos (para controlar el límite del plan de la base)."""
    sql = "SELECT COUNT(*) AS n, COALESCE(SUM(tamano), 0) AS bytes FROM documentos_trabajador"
    p: list = []
    if empresa_ids is not None:
        if not empresa_ids:
            return {"n": 0, "bytes": 0}
        sql += f" WHERE empresa_id IN ({','.join('?' * len(empresa_ids))})"
        p = list(empresa_ids)
    r = db.row(conn, sql, p) or {}
    return {"n": int(r.get("n") or 0), "bytes": int(r.get("bytes") or 0)}


def tamano_legible(n) -> str:
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}".replace(".", ",")
        n /= 1024

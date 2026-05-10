from collections import Counter
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2 import sql

from core.storage import open_db


router = APIRouter(tags=["db-checkdublicateanddelete-esri"])

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AnalyzeReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_name: str
    field_name: str


class DeleteReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_name: str
    row_ref: str


def _get_db_connection_by_name(conn_name: str):
    con = open_db()
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT "No","Conn_Name","Database","Host","Port","UserName","Password","DbType"
            FROM "db_connections"
            WHERE "Conn_Name" = ?
            ORDER BY "No" DESC
            LIMIT 1
            """,
            (conn_name,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def _normalize_db_type(v: str) -> str:
    s = (v or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_esri_dbtype(v: str) -> bool:
    return _normalize_db_type(v) in (
        "esri geodatabase",
        "enterprise geodatabase",
        "esri enterprise geodatabase",
        "esri",
    )


def _validate_esri_conn(conn_name: str):
    info = _get_db_connection_by_name(conn_name)
    if not info:
        return None, {
            "ok": False,
            "message": "Baglanti bulunamadi.",
            "debug": conn_name,
        }
    if not _is_esri_dbtype(str(info.get("DbType") or "")):
        return None, {
            "ok": False,
            "message": "Secilen baglanti Esri Geodatabase degil.",
            "debug": f"DbType={info.get('DbType')}",
        }
    return info, None


def _connect_db(info: dict):
    return psycopg2.connect(
        host=info.get("Host"),
        port=str(info.get("Port")),
        user=info.get("UserName"),
        password=info.get("Password") or "",
        database=info.get("Database"),
    )


def _is_valid_ident(name: str) -> bool:
    return bool(_IDENT_RE.match((name or "").strip()))


def _dataset_exists(cur, schema_name: str, dataset_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = %s
        LIMIT 1
        """,
        (schema_name, dataset_name),
    )
    return bool(cur.fetchone())


def _get_pk_column(cur, schema_name: str, dataset_name: str) -> str | None:
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        LIMIT 1
        """,
        (schema_name, dataset_name),
    )
    r = cur.fetchone()
    if not r:
        return None
    return (r[0] or "").strip() or None


def _list_columns(cur, schema_name: str, dataset_name: str) -> list[dict]:
    cur.execute(
        """
        SELECT
            c.column_name,
            c.data_type,
            c.udt_name
        FROM information_schema.columns c
        WHERE c.table_schema = %s
          AND c.table_name = %s
        ORDER BY c.ordinal_position
        """,
        (schema_name, dataset_name),
    )
    rows = cur.fetchall()

    out = []
    for r in rows:
        row = tuple(list(r) + [None] * 3)[:3]
        col_name, data_type, udt_name = row
        col_name = (col_name or "").strip()
        if not col_name:
            continue
        udt = (udt_name or "").strip().lower()
        out.append(
            {
                "name": col_name,
                "data_type": (data_type or "").strip().lower(),
                "udt_name": udt,
                "is_geometry": udt in ("geometry", "st_geometry"),
            }
        )
    return out


@router.get("/dbcheckdublicateanddeleteesri-schemas")
def dbcheckdublicateanddeleteesri_schemas(conn_name: str):
    conn_name = (conn_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_db(info)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('information_schema')
                  AND schema_name NOT LIKE 'pg_%'
                ORDER BY schema_name
                """
            )
            schemas = [r[0] for r in cur.fetchall() if r and r[0]]
            cur.close()
        finally:
            conn.close()
        return {"ok": True, "data": schemas, "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": "Semalar okunamadi.", "debug": str(e)}


@router.get("/dbcheckdublicateanddeleteesri-datasets")
def dbcheckdublicateanddeleteesri_datasets(conn_name: str, schema_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_db(info)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                (schema_name,),
            )
            datasets = [r[0] for r in cur.fetchall() if r and r[0]]
            cur.close()
        finally:
            conn.close()
        return {"ok": True, "data": datasets, "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": "Veri setleri okunamadi.", "debug": str(e)}


@router.get("/dbcheckdublicateanddeleteesri-fields")
def dbcheckdublicateanddeleteesri_fields(conn_name: str, schema_name: str, dataset_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()
    dataset_name = (dataset_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_db(info)
        try:
            cur = conn.cursor()
            if not _dataset_exists(cur, schema_name, dataset_name):
                return {
                    "ok": False,
                    "data": [],
                    "message": "Secilen veri seti bulunamadi.",
                    "debug": f"{schema_name}.{dataset_name}",
                }
            columns = _list_columns(cur, schema_name, dataset_name)
            fields = [c["name"] for c in columns if not c.get("is_geometry")]
            cur.close()
        finally:
            conn.close()
        return {"ok": True, "data": fields, "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": "Alanlar okunamadi.", "debug": str(e)}


@router.post("/dbcheckdublicateanddeleteesri-analyze")
def dbcheckdublicateanddeleteesri_analyze(req: AnalyzeReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_name = (req.dataset_name or "").strip()
    field_name = (req.field_name or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name bos olamaz")
    if not field_name:
        raise HTTPException(status_code=400, detail="field_name bos olamaz")

    if not _is_valid_ident(schema_name) or not _is_valid_ident(dataset_name):
        return {"ok": False, "message": "Sema veya veri seti adi gecersiz.", "debug": "ident"}

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    conn = None
    cur = None
    try:
        conn = _connect_db(info)
        cur = conn.cursor()

        if not _dataset_exists(cur, schema_name, dataset_name):
            return {
                "ok": False,
                "message": "Secilen veri seti bulunamadi.",
                "debug": f"{schema_name}.{dataset_name}",
            }

        columns = _list_columns(cur, schema_name, dataset_name)
        col_names = [c["name"] for c in columns]
        chk_fields = [c["name"] for c in columns if not c.get("is_geometry")]

        if field_name not in col_names:
            return {"ok": False, "message": "Secilen alan veri setinde yok.", "debug": field_name}
        if field_name not in chk_fields:
            return {
                "ok": False,
                "message": "Geometri alani tekrarlı kontrol icin kullanilamaz.",
                "debug": field_name,
            }

        pk_col = _get_pk_column(cur, schema_name, dataset_name)

        select_parts = [sql.SQL("t.ctid::text AS _row_ctid")]
        if pk_col:
            select_parts.append(
                sql.SQL("t.{}::text AS _row_pk").format(sql.Identifier(pk_col))
            )

        for c in col_names:
            select_parts.append(
                sql.SQL("t.{}::text AS {}").format(
                    sql.Identifier(c),
                    sql.Identifier(c),
                )
            )

        q = sql.SQL("SELECT {} FROM {}.{} t").format(
            sql.SQL(", ").join(select_parts),
            sql.Identifier(schema_name),
            sql.Identifier(dataset_name),
        )
        cur.execute(q)
        all_rows = cur.fetchall()

        base_offset = 1 + (1 if pk_col else 0)
        idx_map = {name: i for i, name in enumerate(col_names)}
        target_idx = base_offset + idx_map[field_name]

        values = []
        for r in all_rows:
            raw = r[target_idx]
            v = (raw or "").strip()
            if v:
                values.append(v)
        counts = Counter(values)

        out_rows = []
        for r in all_rows:
            dup_val = (r[target_idx] or "").strip()
            if not dup_val:
                continue
            grp_count = int(counts.get(dup_val, 0))
            if grp_count <= 1:
                continue

            row_ctid = (r[0] or "").strip()
            row_pk = ""
            if pk_col:
                row_pk = (r[1] or "").strip()

            if row_pk:
                row_ref = f"pk:{row_pk}"
                record_id = row_pk
            else:
                row_ref = f"ctid:{row_ctid}"
                record_id = row_ctid

            all_values = {}
            for name, i in idx_map.items():
                val = r[base_offset + i]
                all_values[name] = "" if val is None else str(val)

            out_rows.append(
                {
                    "record_id": record_id,
                    "feature_type": dataset_name,
                    "value": dup_val,
                    "group_count": grp_count,
                    "all_values": all_values,
                    "row_ref": row_ref,
                }
            )

        out_rows.sort(key=lambda x: (str(x.get("value") or "").lower(), str(x.get("record_id") or "")))
        duplicate_groups = len({str(r.get("value") or "") for r in out_rows})

        return {
            "ok": True,
            "message": "",
            "data": {
                "rows": out_rows,
                "duplicate_row_count": len(out_rows),
                "duplicate_group_count": duplicate_groups,
                "feature_count": len(all_rows),
                "pk_column": pk_col or "",
            },
        }
    except Exception as e:
        return {"ok": False, "message": "Analiz basarisiz.", "debug": str(e), "data": None}
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass


@router.post("/dbcheckdublicateanddeleteesri-delete")
def dbcheckdublicateanddeleteesri_delete(req: DeleteReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_name = (req.dataset_name or "").strip()
    row_ref = (req.row_ref or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name bos olamaz")
    if not row_ref:
        raise HTTPException(status_code=400, detail="row_ref bos olamaz")

    if not _is_valid_ident(schema_name) or not _is_valid_ident(dataset_name):
        return {"ok": False, "message": "Sema veya veri seti adi gecersiz.", "debug": "ident"}

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    conn = None
    cur = None
    try:
        conn = _connect_db(info)
        cur = conn.cursor()

        if not _dataset_exists(cur, schema_name, dataset_name):
            return {
                "ok": False,
                "message": "Secilen veri seti bulunamadi.",
                "debug": f"{schema_name}.{dataset_name}",
            }

        pk_col = _get_pk_column(cur, schema_name, dataset_name)

        deleted = 0
        if row_ref.startswith("pk:"):
            if not pk_col:
                return {
                    "ok": False,
                    "message": "Veri setinde primary key alani yok, pk ile silinemedi.",
                    "debug": row_ref,
                }
            pk_val = row_ref[3:]
            cur.execute(
                sql.SQL("DELETE FROM {}.{} WHERE {}::text = %s").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(pk_col),
                ),
                (pk_val,),
            )
            deleted = cur.rowcount or 0
        elif row_ref.startswith("ctid:"):
            ctid_val = row_ref[5:]
            cur.execute(
                sql.SQL("DELETE FROM {}.{} WHERE ctid = %s::tid").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                ),
                (ctid_val,),
            )
            deleted = cur.rowcount or 0
        else:
            return {"ok": False, "message": "row_ref formati gecersiz.", "debug": row_ref}

        if deleted < 1:
            conn.rollback()
            return {
                "ok": False,
                "message": "Silinecek kayit bulunamadi.",
                "debug": row_ref,
            }

        conn.commit()
        return {"ok": True, "message": "Kayit silindi.", "data": {"row_ref": row_ref}}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "message": "Kayit silinemedi.", "debug": str(e), "data": None}
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import re

import psycopg2
from psycopg2 import sql

from core.storage import open_db


router = APIRouter(tags=["db-deletefeature"])

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DeleteDatasetsReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_names: list[str] = Field(default_factory=list)


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


def _validate_postgis_conn(conn_name: str):
    info = _get_db_connection_by_name(conn_name)
    if not info:
        return None, {
            "ok": False,
            "message": "Baglanti bulunamadi.",
            "debug": conn_name,
        }
    if _normalize_db_type(str(info.get("DbType") or "")) != "postgis":
        return None, {
            "ok": False,
            "message": "Secilen baglanti PostGIS degil (DbType=PostGIS olmali).",
            "debug": f"DbType={info.get('DbType')}",
        }
    return info, None


def _connect_postgis(info: dict):
    return psycopg2.connect(
        host=info.get("Host"),
        port=str(info.get("Port")),
        user=info.get("UserName"),
        password=info.get("Password") or "",
        database=info.get("Database"),
    )


def _is_valid_ident(name: str) -> bool:
    return bool(_IDENT_RE.match((name or "").strip()))


@router.get("/dbdeletefeature-schemas")
def dbdeletefeature_schemas(conn_name: str):
    conn_name = (conn_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_postgis(info)
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


@router.get("/dbdeletefeature-datasets")
def dbdeletefeature_datasets(conn_name: str, schema_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not _is_valid_ident(schema_name):
        return {"ok": False, "data": [], "message": "Sema adi gecersiz.", "debug": schema_name}

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_postgis(info)
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


@router.post("/dbdeletefeature-delete-datasets")
def dbdeletefeature_delete_datasets(req: DeleteDatasetsReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_names = [str(x or "").strip() for x in (req.dataset_names or [])]
    dataset_names = [x for x in dataset_names if x]

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_names:
        raise HTTPException(status_code=400, detail="dataset_names bos olamaz")

    if not _is_valid_ident(schema_name):
        return {"ok": False, "message": "Sema adi gecersiz.", "debug": schema_name}

    invalid = [n for n in dataset_names if not _is_valid_ident(n)]
    if invalid:
        return {
            "ok": False,
            "message": "Veri seti adlarindan bazilari gecersiz.",
            "debug": ", ".join(invalid),
        }

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    conn = None
    cur = None
    try:
        conn = _connect_postgis(info)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            """,
            (schema_name,),
        )
        existing = {r[0] for r in cur.fetchall() if r and r[0]}

        missing = [n for n in dataset_names if n not in existing]
        to_delete = [n for n in dataset_names if n in existing]

        deleted = []
        for table_name in to_delete:
            cur.execute(
                sql.SQL("DROP TABLE {}.{} CASCADE").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                )
            )
            deleted.append(table_name)

        conn.commit()

        msg = f"{len(deleted)} veri seti silindi."
        if missing:
            msg += f" {len(missing)} veri seti bulunamadi."

        return {
            "ok": True,
            "message": msg,
            "data": {
                "deleted": deleted,
                "missing": missing,
                "schema_name": schema_name,
            },
            "debug": "",
        }
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "message": "Veri setleri silinemedi.", "debug": str(e), "data": None}
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

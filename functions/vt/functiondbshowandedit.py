import os
import sqlite3
from platformdirs import user_data_dir

APP_NAME = "DBManagement"
ORG_NAME = "Zumimuhendislik"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS "vt_connections" (
    "No"        INTEGER NOT NULL UNIQUE,
    "Conn_Name" TEXT NOT NULL,
    "Database"  TEXT NOT NULL,
    "Host"      TEXT NOT NULL,
    "Port"      INTEGER NOT NULL,
    "UserName"  TEXT NOT NULL,
    "Password"  TEXT NOT NULL,
    "DbType"    TEXT NOT NULL,
    PRIMARY KEY("No" AUTOINCREMENT)
);
"""


def storage_dir(app_name=APP_NAME, org_name=ORG_NAME) -> str:
    base = user_data_dir(app_name, org_name)
    os.makedirs(base, exist_ok=True)
    return base


def db_path() -> str:
    return os.path.join(storage_dir(), "app_informations.db")


def _ensure_db_and_table(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    try:
        cur = con.cursor()
        cur.execute(CREATE_TABLE_SQL)
        con.commit()
    finally:
        con.close()


def list_connections():
    """
    Sol listede gösterilecek kayıtlar.
    Dönüş: [{"No":1,"Conn_Name":"..","DbType":".."}, ...]
    """
    path = db_path()
    _ensure_db_and_table(path)

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT "No","Conn_Name","DbType"
            FROM "vt_connections"
            ORDER BY "No" DESC
        """
        )
        rows = cur.fetchall()
        return {"ok": True, "data": [dict(r) for r in rows], "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": str(e)}
    finally:
        con.close()


def get_connection(no: int):
    """
    Seçilen kaydın detayları.
    """
    path = db_path()
    _ensure_db_and_table(path)

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT "No","Conn_Name","Database","Host","Port","UserName","Password","DbType"
            FROM "vt_connections"
            WHERE "No" = ?
        """,
            (no,),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "data": None, "message": "Kayıt bulunamadı."}
        return {"ok": True, "data": dict(row), "message": ""}
    except Exception as e:
        return {"ok": False, "data": None, "message": str(e)}
    finally:
        con.close()


def update_connection(
    no: int,
    conn_name: str,
    database: str,
    host: str,
    port: str,
    user: str,
    password: str,
    db_type: str,
):
    """
    Güncelleme işlemi.
    """
    path = db_path()
    _ensure_db_and_table(path)

    try:
        port_int = int(port)
    except Exception:
        return {"ok": False, "message": "Port sayısal olmalıdır."}

    con = sqlite3.connect(path)
    try:
        cur = con.cursor()
        cur.execute(
            """
            UPDATE "vt_connections"
            SET
                "Conn_Name" = ?,
                "Database"  = ?,
                "Host"      = ?,
                "Port"      = ?,
                "UserName"  = ?,
                "Password"  = ?,
                "DbType"    = ?
            WHERE "No" = ?
        """,
            (conn_name, database, host, port_int, user, password, db_type, no),
        )
        con.commit()

        if cur.rowcount == 0:
            return {"ok": False, "message": "Güncellenecek kayıt bulunamadı."}

        return {"ok": True, "message": "Güncelleme kaydedildi."}
    except Exception as e:
        return {"ok": False, "message": str(e)}
    finally:
        con.close()

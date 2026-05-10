import json
import os
import sys
from platformdirs import user_data_dir

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_NAME = "DBManagement"
ORG_NAME = "Zumimuhendislik"

def storage_dir(app_name=APP_NAME, org_name=ORG_NAME) -> str:
    base = user_data_dir(app_name, org_name)
    os.makedirs(base, exist_ok=True)
    return base

def fatal_import_error(e):
    payload = {
        "ok": False,
        "title": "Python Modül Hatası",
        "message": f"Gerekli Python modülü yüklenmemiş veya erişilemiyor:\n{str(e)}",
        "is_save_enabled": False
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    raise SystemExit(3)

try:
    import psycopg2
except Exception as e:
    fatal_import_error(e)

try:
    import sqlite3
except Exception as e:
    fatal_import_error(e)

def _result(ok: bool, title: str, message: str, is_save_enabled: bool):
    return {
        "ok": ok,
        "title": title,
        "message": message,
        "is_save_enabled": is_save_enabled,
    }

def check_connection(host: str, port: str, user: str, password: str, database: str):
    try:
        conn = psycopg2.connect(
            host=host,
            port=str(port),
            user=user,
            password=password,
            database=database
        )
        conn.close()
        return _result(True, "Başarılı", "Veritabanı bağlantısı başarılı!", True)
    except Exception as e:
        return _result(False, "Hata", f"Veritabanı bağlantısı sağlanamadı.\nHata: {str(e)}", False)

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

def _ensure_db_and_table(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(CREATE_TABLE_SQL)
        con.commit()
    finally:
        con.close()

def save_connection(conn_name: str, host: str, port: str, user: str, password: str, database: str, db_type: str):
    try:
        base_dir = storage_dir()  # <-- düzeltildi (fonksiyon çağrısı)
        db_path = os.path.join(base_dir, "app_informations.db")

        _ensure_db_and_table(db_path)

        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO "vt_connections"
                ("Conn_Name", "Database", "Host", "Port", "UserName", "Password", "DbType")
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (conn_name, database, host, int(port), user, password, db_type)
            )
            con.commit()
        finally:
            con.close()

        return _result(
            True,
            "Başarılı",
            f"Bağlantı bilgileri kaydedildi.\nDosya: {db_path}",
            False
        )

    except Exception as e:
        return _result(False, "Hata", f"Bağlantı bilgileri kayıt edilemedi.\nHata: {str(e)}", True)

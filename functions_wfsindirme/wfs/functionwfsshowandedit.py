import os
import sqlite3
import requests
from platformdirs import user_data_dir

APP_NAME = "DBManagement"
ORG_NAME = "Zumimuhendislik"
DB_FILENAME = "app_informations.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS "wfs_connections" (
    "No"        INTEGER PRIMARY KEY AUTOINCREMENT,
    "Conn_Name" TEXT NOT NULL,
    "UrlAdress" TEXT NOT NULL,
    "UserName"  TEXT,
    "Password"  TEXT
);
"""

def storage_dir(app_name: str = APP_NAME, org_name: str = ORG_NAME) -> str:
    base = user_data_dir(app_name, org_name)
    os.makedirs(base, exist_ok=True)
    return base

def db_path() -> str:
    return os.path.join(storage_dir(), DB_FILENAME)

def _ensure_db_and_table(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    try:
        cur = con.cursor()
        cur.execute(CREATE_TABLE_SQL)
        con.commit()
    finally:
        con.close()

def _result(ok: bool, title: str, message: str, is_save_enabled: bool = False, data=None):
    return {"ok": ok, "title": title, "message": message, "is_save_enabled": is_save_enabled, "data": data}

def list_wfs_connections():
    """
    Sol listede gösterim için.
    Dönüş: {"ok": True, "data": [{"No":..,"Conn_Name":..,"UrlAdress":..}, ...], "message":""}
    """
    path = db_path()
    _ensure_db_and_table(path)

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT "No","Conn_Name","UrlAdress","UserName"
            FROM "wfs_connections"
            ORDER BY "No" DESC
        """)
        rows = cur.fetchall()
        return {"ok": True, "data": [dict(r) for r in rows], "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": str(e)}
    finally:
        con.close()

def get_wfs_connection(no: int):
    path = db_path()
    _ensure_db_and_table(path)

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT "No","Conn_Name","UrlAdress","UserName","Password"
            FROM "wfs_connections"
            WHERE "No" = ?
        """, (no,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "data": None, "message": "Kayıt bulunamadı."}
        return {"ok": True, "data": dict(row), "message": ""}
    except Exception as e:
        return {"ok": False, "data": None, "message": str(e)}
    finally:
        con.close()

def update_wfs_connection(no: int, conn_name: str, urladress: str, username: str, password: str):
    conn_name = (conn_name or "").strip()
    urladress = (urladress or "").strip()
    username = (username or "").strip()
    password = password or ""

    if not conn_name:
        return {"ok": False, "message": "Bağlantı adı boş olamaz."}
    if not urladress:
        return {"ok": False, "message": "URL boş olamaz."}

    path = db_path()
    _ensure_db_and_table(path)

    con = sqlite3.connect(path)
    try:
        cur = con.cursor()
        cur.execute("""
            UPDATE "wfs_connections"
            SET "Conn_Name" = ?, "UrlAdress" = ?, "UserName" = ?, "Password" = ?
            WHERE "No" = ?
        """, (conn_name, urladress, username, password, no))
        con.commit()
        if cur.rowcount == 0:
            return {"ok": False, "message": "Güncellenecek kayıt bulunamadı."}
        return {"ok": True, "message": "Güncelleme kaydedildi."}
    except Exception as e:
        return {"ok": False, "message": str(e)}
    finally:
        con.close()

def wfs_test_connection(urladress: str, username: str = "", password: str = "", timeout: int = 10):
    """
    GetCapabilities ile WFS test.
    username/password boşsa auth kullanmaz.
    """
    urladress = (urladress or "").strip()
    username = (username or "").strip()
    password = password or ""

    if not urladress:
        return _result(False, "Hata", "Bağlantı adresi (URL) giriniz.", False)

    try:
        params = {"service": "WFS", "request": "GetCapabilities"}
        kwargs = {"params": params, "timeout": timeout}
        if username and password:
            kwargs["auth"] = (username, password)

        resp = requests.get(urladress, **kwargs)

        if resp.status_code == 200 and "WFS_Capabilities" in (resp.text or ""):
            return _result(True, "Başarılı", "WFS bağlantısı başarılı!", True)

        return _result(False, "Hata", f"WFS bağlantısı başarısız.\nDurum: {resp.status_code}", False)

    except Exception as e:
        return _result(False, "Hata", f"Bağlantı sağlanamadı.\nHata: {str(e)}", False)

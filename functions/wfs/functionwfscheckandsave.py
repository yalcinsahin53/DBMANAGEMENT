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

def _result(ok: bool, title: str, message: str, is_save_enabled: bool):
    return {
        "ok": ok,
        "title": title,
        "message": message,
        "is_save_enabled": is_save_enabled,
    }

def wfs_check_connection(urladress: str, username: str = "", password: str = "", timeout: int = 10):
    """
    WFS GetCapabilities isteği ile bağlantı kontrolü.
    Username/password boşsa auth uygulanmaz.
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

        # Başarılı kabul kriteri: 200 + WFS_Capabilities ibaresi
        if resp.status_code == 200 and "WFS_Capabilities" in (resp.text or ""):
            return _result(True, "Başarılı", "WFS bağlantısı başarılı!", True)

        return _result(
            False,
            "Hata",
            f"WFS bağlantısı başarısız.\nDurum: {resp.status_code}",
            False,
        )

    except Exception as e:
        return _result(False, "Hata", f"Bağlantı sağlanamadı.\nHata: {str(e)}", False)

def wfs_save_connection(conn_name: str, urladress: str, username: str = "", password: str = ""):
    """
    wfs_connections tablosuna kayıt.
    """
    conn_name = (conn_name or "").strip()
    urladress = (urladress or "").strip()
    username = (username or "").strip()
    password = password or ""

    if not conn_name:
        return _result(False, "Hata", "Bağlantı adı giriniz.", True)
    if not urladress:
        return _result(False, "Hata", "Bağlantı adresi (URL) giriniz.", True)

    path = db_path()
    try:
        _ensure_db_and_table(path)

        con = sqlite3.connect(path)
        try:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO "wfs_connections" ("Conn_Name","UrlAdress","UserName","Password")
                VALUES (?, ?, ?, ?)
                """,
                (conn_name, urladress, username, password),
            )
            con.commit()
        finally:
            con.close()

        return _result(True, "Başarılı", f"Bilgiler kaydedildi.\nDosya: {path}", False)

    except Exception as e:
        return _result(False, "Hata", f"Kayıt yapılamadı.\nHata: {str(e)}", True)

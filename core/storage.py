# core/storage.py
import os
import sqlite3
from platformdirs import user_data_dir

APP_NAME = "DBManagement"
ORG_NAME = "Zumimuhendislik"

CREATE_DB_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS "db_connections" (
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

CREATE_WFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS "wfs_connections" (
    "No"        INTEGER PRIMARY KEY AUTOINCREMENT,
    "Conn_Name" TEXT NOT NULL,
    "UrlAdress" TEXT NOT NULL,
    "UserName"  TEXT,
    "Password"  TEXT
);
"""

def storage_dir(app_name=APP_NAME, org_name=ORG_NAME) -> str:
    base = user_data_dir(app_name, org_name)
    os.makedirs(base, exist_ok=True)
    return base

def db_path() -> str:
    return os.path.join(storage_dir(), "app_informations.db")

def ensure_db_and_tables():
    """Uygulama db dosyasını ve gerekli tabloları oluşturur."""
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    try:
        cur = con.cursor()
        cur.execute(CREATE_DB_TABLE_SQL)
        cur.execute(CREATE_WFS_TABLE_SQL)
        con.commit()
    finally:
        con.close()
    return path

def open_db():
    """Row dict dönüşümü için row_factory ayarlı connection döndürür."""
    path = ensure_db_and_tables()
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con

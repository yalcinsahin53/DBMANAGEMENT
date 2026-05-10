import sqlite3
import psycopg2
from core.storage import ensure_db_and_tables, db_path
# core/db_service.py
from core.storage import open_db

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
            database=database,
            connect_timeout=5,
        )
        conn.close()
        return _result(True, "Başarılı", "Veritabanı bağlantısı başarılı!", True)
    except Exception as e:
        return _result(False, "Hata", f"Veritabanı bağlantısı sağlanamadı.\nHata: {str(e)}", False)

def save_connection(conn_name: str, host: str, port: str, user: str, password: str, database: str, db_type: str):
    try:
        ensure_db_and_tables()
        path = db_path()

        con = sqlite3.connect(path)
        try:
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO "db_connections"
                ("Conn_Name", "Database", "Host", "Port", "UserName", "Password", "DbType")
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (conn_name, database, host, int(port), user, password, db_type)
            )
            con.commit()
        finally:
            con.close()

        return _result(True, "Başarılı", f"Bağlantı bilgileri kaydedildi.\nDosya: {path}", False)

    except Exception as e:
        return _result(False, "Hata", f"Bağlantı bilgileri kayıt edilemedi.\nHata: {str(e)}", True)

def list_db_connections():
    """
    Sol listede gösterilecek kayıtlar.
    Dönüş: {"ok": True, "data": [{"No":..,"Conn_Name":..,"DbType":..},...], "message": ""}
    """
    con = open_db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT "No","Conn_Name","DbType"
            FROM "db_connections"
            ORDER BY "No" DESC
        """)
        rows = cur.fetchall()
        return {"ok": True, "data": [dict(r) for r in rows], "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": str(e)}
    finally:
        con.close()

def get_db_connection(no: int):
    """
    Seçilen kaydın detayları.
    """
    con = open_db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT "No","Conn_Name","Database","Host","Port","UserName","Password","DbType"
            FROM "db_connections"
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

def update_db_connection(no: int, conn_name: str, database: str, host: str, port: str,
                         user: str, password: str, db_type: str):
    """
    Güncelleme işlemi.
    """
    try:
        port_int = int(port)
    except Exception:
        return {"ok": False, "message": "Port sayısal olmalıdır."}

    con = open_db()
    try:
        cur = con.cursor()
        cur.execute("""
            UPDATE "db_connections"
            SET
                "Conn_Name" = ?,
                "Database"  = ?,
                "Host"      = ?,
                "Port"      = ?,
                "UserName"  = ?,
                "Password"  = ?,
                "DbType"    = ?
            WHERE "No" = ?
        """, (conn_name, database, host, port_int, user, password, db_type, no))
        con.commit()

        if cur.rowcount == 0:
            return {"ok": False, "message": "Güncellenecek kayıt bulunamadı."}

        return {"ok": True, "message": "Güncelleme kaydedildi."}
    except Exception as e:
        return {"ok": False, "message": str(e)}
    finally:
        con.close()

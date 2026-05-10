import os
import sqlite3
import requests
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
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


def list_wfs_connections() -> Dict[str, Any]:
    path = db_path()
    _ensure_db_and_table(path)

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT "No","Conn_Name","UrlAdress","UserName","Password"
            FROM "wfs_connections"
            ORDER BY "No" DESC
            """
        )
        rows = cur.fetchall()
        data = [dict(r) for r in rows]
        return {"ok": True, "data": data, "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": str(e)}
    finally:
        con.close()


def get_wfs_connection_by_name(conn_name: str) -> Dict[str, Any]:
    conn_name = (conn_name or "").strip()
    if not conn_name:
        return {"ok": False, "data": None, "message": "Bağlantı adı boş."}

    path = db_path()
    _ensure_db_and_table(path)

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT "No","Conn_Name","UrlAdress","UserName","Password"
            FROM "wfs_connections"
            WHERE "Conn_Name" = ?
            """,
            (conn_name,),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "data": None, "message": "Bağlantı bulunamadı."}
        return {"ok": True, "data": dict(row), "message": ""}
    except Exception as e:
        return {"ok": False, "data": None, "message": str(e)}
    finally:
        con.close()


def _auth(username: str, password: str):
    username = (username or "").strip()
    password = password or ""
    return (username, password) if (username and password) else None


def _local(tag: str) -> str:
    if not tag:
        return ""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def _parse_typenames_from_capabilities(xml_bytes: bytes) -> List[str]:
    root = ET.fromstring(xml_bytes)

    # WFS 1.x klasik
    names = [
        n.text
        for n in root.findall(
            ".//{http://www.opengis.net/wfs}FeatureType/{http://www.opengis.net/wfs}Name"
        )
    ]

    # WFS 2.0 klasik
    if not names:
        names = [
            n.text
            for n in root.findall(
                ".//{http://www.opengis.net/wfs/2.0}FeatureType/{http://www.opengis.net/wfs/2.0}Name"
            )
        ]

    # Namespace bağımsız fallback
    if not names:
        tmp = []
        for ft_el in root.iter():
            if _local(ft_el.tag) == "FeatureType":
                for child in list(ft_el):
                    if _local(child.tag) == "Name" and child.text:
                        tmp.append(child.text)
        names = tmp

    return sorted([x.strip() for x in names if x and x.strip()])


def wfs_get_typenames(
    url: str, username: str = "", password: str = "", timeout: int = 20
) -> Dict[str, Any]:
    """
    GetCapabilities -> typeName listesi
    """
    url = (url or "").strip()
    if not url:
        return {"ok": False, "data": [], "message": "URL boş.", "debug": ""}

    params = {"service": "WFS", "request": "GetCapabilities"}
    try:
        resp = requests.get(
            url,
            params=params,
            timeout=timeout,
            auth=_auth(username, password),
            allow_redirects=True,
        )

        ct = resp.headers.get("Content-Type") or ""
        head = ""
        try:
            head = (resp.text or "")[:200]
        except Exception:
            head = "<text okunamadı>"

        debug = (
            f"HTTP={resp.status_code}\n"
            f"Content-Type={ct}\n"
            f"Final-URL={resp.url}\n"
            f"First200={head}"
        )

        if resp.status_code != 200 or not resp.content:
            return {
                "ok": False,
                "data": [],
                "message": f"GetCapabilities başarısız (HTTP {resp.status_code}).",
                "debug": debug,
            }

        try:
            typenames = _parse_typenames_from_capabilities(resp.content)
        except Exception as e:
            return {
                "ok": False,
                "data": [],
                "message": f"Capabilities XML parse edilemedi: {e}",
                "debug": debug,
            }

        if not typenames:
            return {
                "ok": False,
                "data": [],
                "message": "TypeName bulunamadı (servis auth istiyor olabilir veya farklı içerik döndürüyor olabilir).",
                "debug": debug,
            }

        return {"ok": True, "data": typenames, "message": "", "debug": debug}

    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "data": [],
            "message": "GetCapabilities zaman aşımı.",
            "debug": "TIMEOUT",
        }
    except Exception as e:
        return {
            "ok": False,
            "data": [],
            "message": "GetCapabilities çağrısında hata.",
            "debug": str(e),
        }


def fetch_typenames_for_connection(conn_name: str) -> Dict[str, Any]:
    """
    conn_name -> DB’den URL/User/Pass al -> GetCapabilities -> typenames
    """
    cres = get_wfs_connection_by_name(conn_name)
    if not cres.get("ok"):
        return {
            "ok": False,
            "data": [],
            "message": cres.get("message", ""),
            "debug": "",
        }

    c = cres["data"] or {}
    url = (c.get("UrlAdress") or "").strip()
    usr = c.get("UserName") or ""
    pwd = c.get("Password") or ""

    if not url:
        return {
            "ok": False,
            "data": [],
            "message": "Seçilen bağlantıda UrlAdress boş.",
            "debug": "",
        }

    return wfs_get_typenames(url, usr, pwd)

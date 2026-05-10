# core/wfs_service.py
from __future__ import annotations
import re
import json
import datetime
import hashlib
import io
import zipfile
import requests
import sqlite3
import xml.etree.ElementTree as ET

from core.storage import open_db, db_path, ensure_db_and_tables


def _result(
    ok: bool,
    title: str,
    message: str,
    is_save_enabled: bool = False,
    data=None,
    debug: str = "",
):
    return {
        "ok": ok,
        "title": title,
        "message": message,
        "is_save_enabled": is_save_enabled,
        "data": data,
        "debug": debug,
    }


# -------------------------------------------------------------------
# Mevcut: CHECK / SAVE
# -------------------------------------------------------------------
def wfs_check_connection(
    urladress: str, username: str = "", password: str = "", timeout: int = 10
):
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

        # basic auth sadece ikisi de doluysa
        if username and password:
            kwargs["auth"] = (username, password)

        resp = requests.get(urladress, **kwargs)

        # Basit kabul kriteri
        text = resp.text or ""
        if resp.status_code == 200 and (
            "WFS_Capabilities" in text or "Wfs_Capabilities" in text
        ):
            return _result(True, "Başarılı", "WFS bağlantısı başarılı!", True)

        return _result(
            False,
            "Hata",
            f"WFS bağlantısı başarısız.\nDurum: {resp.status_code}",
            False,
        )

    except Exception as e:
        return _result(False, "Hata", f"Bağlantı sağlanamadı.\nHata: {str(e)}", False)


def wfs_save_connection(
    conn_name: str, urladress: str, username: str = "", password: str = ""
):
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

    try:
        ensure_db_and_tables()
        con = open_db()
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

        return _result(
            True, "Başarılı", f"Bilgiler kaydedildi.\nDosya: {db_path()}", False
        )

    except Exception as e:
        return _result(False, "Hata", f"Kayıt yapılamadı.\nHata: {str(e)}", True)


def _get_wfs_conn(conn_name: str):
    ensure_db_and_tables()
    con = open_db()
    try:
        cur = con.cursor()
        cur.execute(
            """SELECT "Conn_Name","UrlAdress","UserName","Password"
               FROM "wfs_connections"
               WHERE "Conn_Name" = ?""",
            (conn_name,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def list_wfs_connections():
    ensure_db_and_tables()
    con = open_db()
    try:
        cur = con.cursor()
        cur.execute(
            """SELECT "No","Conn_Name" FROM "wfs_connections" ORDER BY "No" DESC"""
        )
        rows = [dict(r) for r in cur.fetchall()]
        return _result(True, "OK", "", data=rows)
    except Exception as e:
        return _result(
            False, "Hata", "WFS bağlantıları okunamadı.", data=[], debug=str(e)
        )
    finally:
        con.close()


def _requests_kwargs(username: str, password: str, timeout: int):
    kw = {"timeout": timeout}
    if (username or "").strip() and (password or ""):
        kw["auth"] = ((username or "").strip(), password or "")
    return kw


def _local(tag: str) -> str:
    if not tag:
        return ""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def _parse_typenames(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    names = []
    for ft_el in root.iter():
        if _local(ft_el.tag) == "FeatureType":
            for child in ft_el:
                if _local(child.tag) == "Name" and (child.text or "").strip():
                    names.append(child.text.strip())
    return sorted(set(names))


def fetch_typenames_for_connection(conn_name: str):
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=[], debug=conn_name
        )

    url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    if not url:
        return _result(False, "Hata", "UrlAdress boş.", data=[], debug=str(info))

    try:
        params = {"service": "WFS", "request": "GetCapabilities"}
        resp = requests.get(url, params=params, **_requests_kwargs(user, pwd, 20))
        if resp.status_code != 200 or not resp.content:
            return _result(
                False,
                "Hata",
                f"GetCapabilities başarısız (HTTP {resp.status_code}).",
                data=[],
                debug=resp.text[:400],
            )

        typenames = _parse_typenames(resp.content)
        if not typenames:
            return _result(
                False,
                "Bilgi",
                "Bu servisten typeName okunamadı.",
                data=[],
                debug=resp.text[:600],
            )

        return _result(True, "OK", "", data=typenames)

    except Exception as e:
        return _result(False, "Hata", "Capabilities okunamadı.", data=[], debug=str(e))


def _geom_label_from_xsd_type(xsd_type: str) -> str:
    t = (xsd_type or "").lower()
    # ör: gml:polygonpropertytype, gml:multisurfacepropertytype, gml:linestringpropertytype...
    if "point" in t:
        return "Point"
    if "line" in t or "curve" in t:
        return "Line"
    if "polygon" in t or "surface" in t:
        return "Polygon"
    return "Unknown"


def _infer_geom_for_typename(base_url: str, typename: str, user: str, pwd: str) -> str:
    resp, err = _describe_feature_type(base_url, typename, user, pwd)
    if not resp:
        return "Unknown"

    try:
        root = ET.fromstring(resp.content)
    except Exception:
        return "Unknown"

    XSD = "{http://www.w3.org/2001/XMLSchema}"

    # sequence altındaki elementler daha “feature attributes” gibi olur
    for seq in root.findall(f".//{XSD}sequence"):
        for el in seq.findall(f"{XSD}element"):
            etype = el.get("type", "")  # gml:PointPropertyType vb.
            # geometry elemanı çoğu zaman gml:*PropertyType olur
            if "gml:" in etype.lower() or "gml/" in etype.lower():
                return _geom_label_from_xsd_type(etype)

    # fallback: tüm elementlerde gez
    for el in root.findall(f".//{XSD}element"):
        etype = el.get("type", "")
        if "gml:" in etype.lower() or "gml/" in etype.lower():
            return _geom_label_from_xsd_type(etype)

    return "Unknown"


def fetch_typenames_with_geom(conn_name: str):
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=[], debug=conn_name
        )

    url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    # önce normal typenames
    base = fetch_typenames_for_connection(conn_name)
    if not base.get("ok"):
        return base

    typenames = base.get("data") or []
    out = []
    for tn in typenames:
        geom = _infer_geom_for_typename(url, tn, user, pwd)
        out.append({"name": tn, "geom": geom})

    return _result(True, "OK", "", data=out)


def _describe_feature_type(base_url: str, typename: str, user: str, pwd: str):
    attempts = [
        {"service": "WFS", "request": "DescribeFeatureType", "typename": typename},
        {
            "service": "WFS",
            "request": "DescribeFeatureType",
            "version": "1.1.0",
            "typename": typename,
        },
        {
            "service": "WFS",
            "request": "DescribeFeatureType",
            "version": "2.0.0",
            "typenames": typename,
        },
    ]
    last_err = ""
    for p in attempts:
        try:
            r = requests.get(base_url, params=p, **_requests_kwargs(user, pwd, 25))
            if r.status_code == 200 and r.content:
                return r, ""
            last_err = f"HTTP {r.status_code} params={p}"
        except Exception as e:
            last_err = f"{e} params={p}"
    return None, last_err


def fetch_fieldnames(conn_name: str, typename: str):
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=[], debug=conn_name
        )

    url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    if not url:
        return _result(False, "Hata", "UrlAdress boş.", data=[], debug=str(info))

    resp, err = _describe_feature_type(url, typename, user, pwd)
    if not resp:
        return _result(
            False, "Hata", "DescribeFeatureType başarısız.", data=[], debug=err
        )

    try:
        root = ET.fromstring(resp.content)
    except Exception as e:
        return _result(False, "Hata", "XSD parse edilemedi.", data=[], debug=str(e))

    XSD = "{http://www.w3.org/2001/XMLSchema}"
    elements = []

    for seq in root.findall(f".//{XSD}sequence"):
        for el in seq.findall(f"{XSD}element"):
            name = el.get("name")
            if name:
                elements.append(name)

    if not elements:
        for el in root.findall(f".//{XSD}element"):
            name = el.get("name")
            if name:
                elements.append(name)

    uniq = []
    seen = set()
    for n in elements:
        if n not in seen:
            uniq.append(n)
            seen.add(n)

    if not uniq:
        return _result(
            False, "Bilgi", "Alan adı bulunamadı.", data=[], debug=resp.text[:600]
        )

    return _result(True, "OK", "", data=uniq)


def _friendly_xsd_type(xsd_type: str) -> str:
    t = (xsd_type or "").lower()

    # geometry
    if "gml:" in t or "gml/" in t:
        # biraz daha açıklayıcı dön
        g = _geom_label_from_xsd_type(xsd_type)
        return f"geometry:{g}"

    # xsd primitive normalize
    if "string" in t:
        return "string"
    if "long" in t:
        return "long"
    if "int" in t or "integer" in t or "short" in t:
        return "integer"
    if "double" in t or "decimal" in t or "float" in t:
        return "double"
    if "boolean" in t:
        return "boolean"
    if "dateTime".lower() in t:
        return "dateTime"
    if t.endswith(":date") or "date" in t:
        return "date"

    # bilinmeyen -> ham type
    return xsd_type or "unknown"


def fetch_fieldinfo(conn_name: str, typename: str):
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=[], debug=conn_name
        )

    url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    resp, err = _describe_feature_type(url, typename, user, pwd)
    if not resp:
        return _result(
            False, "Hata", "DescribeFeatureType başarısız.", data=[], debug=err
        )

    try:
        root = ET.fromstring(resp.content)
    except Exception as e:
        return _result(False, "Hata", "XSD parse edilemedi.", data=[], debug=str(e))

    XSD = "{http://www.w3.org/2001/XMLSchema}"
    out = []

    # sequence -> alanlar
    seqs = root.findall(f".//{XSD}sequence")
    if seqs:
        for seq in seqs:
            for el in seq.findall(f"{XSD}element"):
                name = el.get("name")
                etype = el.get("type", "")
                if name:
                    out.append({"name": name, "type": _friendly_xsd_type(etype)})
    else:
        # fallback
        for el in root.findall(f".//{XSD}element"):
            name = el.get("name")
            etype = el.get("type", "")
            if name:
                out.append({"name": name, "type": _friendly_xsd_type(etype)})

    # uniq by name, preserve order
    uniq = []
    seen = set()
    for item in out:
        n = item["name"]
        if n in seen:
            continue
        seen.add(n)
        uniq.append(item)

    if not uniq:
        return _result(
            False, "Bilgi", "Alan adı bulunamadı.", data=[], debug=resp.text[:600]
        )

    return _result(True, "OK", "", data=uniq)


def _wfs_count_features(
    base_url: str, typename: str, user: str, pwd: str
) -> int | None:
    attempts = [
        {
            "service": "WFS",
            "request": "GetFeature",
            "version": "2.0.0",
            "typenames": typename,
            "resultType": "hits",
        },
        {
            "service": "WFS",
            "request": "GetFeature",
            "version": "1.1.0",
            "typename": typename,
            "resultType": "hits",
        },
        {
            "service": "WFS",
            "request": "GetFeature",
            "typename": typename,
            "resultType": "hits",
        },
    ]
    for p in attempts:
        try:
            r = requests.get(base_url, params=p, **_requests_kwargs(user, pwd, 25))
            if r.status_code != 200 or not r.content:
                continue
            root = ET.fromstring(r.content)
            for attr in ("numberMatched", "numberOfFeatures", "totalFeatures"):
                val = root.attrib.get(attr)
                if val and val.isdigit():
                    return int(val)
        except Exception:
            continue
    return None


def count_features(conn_name: str, typename: str):
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=None, debug=conn_name
        )

    url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    try:
        c = _wfs_count_features(url, typename, user, pwd)
        return _result(True, "OK", "", data={"count": c})
    except Exception as e:
        return _result(
            False, "Hata", "Kayıt sayısı alınamadı.", data={"count": None}, debug=str(e)
        )


def _getfeature_gml(
    base_url: str,
    typename: str,
    user: str,
    pwd: str,
    cql_filter: str | None = None,
):

    auth_kw = _requests_kwargs(user, pwd, 60)
    output_candidates = [
        "application/gml+xml; version=3.2",
        "text/xml; subtype=gml/3.2",
        "GML3",
        "GML2",
    ]

    def _mk_params(d: dict) -> dict:
        if cql_filter:
            # GeoServer vb.
            d["CQL_FILTER"] = cql_filter

            # CQL desteklemeyen WFS için fallback
            ogc_xml = _cql_to_ogc_filter_xml(cql_filter)
            if ogc_xml:
                # Birçok WFS implementasyonu FILTER bekler
                d["FILTER"] = ogc_xml

        return d

    attempts = []
    for of in output_candidates:

        p = {
            "service": "WFS",
            "request": "GetFeature",
            "version": "2.0.0",
            "typenames": typename,
            "outputFormat": of,
            "count": 100000,
        }
        p = _mk_params(p)
        attempts.append(p)

        p = {
            "service": "WFS",
            "request": "GetFeature",
            "version": "1.1.0",
            "typename": typename,
            "outputFormat": of,
            "maxFeatures": 100000,
        }
        p = _mk_params(p)
        attempts.append(p)

        p = {
            "service": "WFS",
            "request": "GetFeature",
            "typename": typename,
            "outputFormat": of,
        }
        p = _mk_params(p)
        attempts.append(p)

    last = ""

    def _try_request(method: str, params: dict):
        if method == "POST":
            # Parametreleri body'de gönderiyoruz -> URL limitine takılmaz
            return requests.post(base_url, data=params, **auth_kw)
        return requests.get(base_url, params=params, **auth_kw)

    last = ""
    for p in attempts:
        try:
            # 1) Filtre varsa POST'u önce dene (URL şişmesi problemini kökten çözer)
            if cql_filter:
                r = _try_request("POST", p)
                if r.status_code == 200 and r.content:
                    if _is_ows_exception(r.content):
                        last = f"OWS Exception (POST) params={p} body={r.text[:300]}"
                    else:
                        used = "&".join(f"{k}={v}" for k, v in p.items())
                        return r.content, used + " [POST]"

            # 2) POST başarısızsa GET dene
            r = _try_request("GET", p)

            if r.status_code == 200 and r.content:
                if _is_ows_exception(r.content):
                    last = f"OWS Exception (GET) params={p} body={r.text[:300]}"
                    continue

                used = "&".join(f"{k}={v}" for k, v in p.items())
                return r.content, used + " [GET]"

            last = f"HTTP {r.status_code} {r.text[:200]}"

        except Exception as e:
            last = str(e)

    raise Exception(f"GetFeature başarısız: {last}")


def _parse_getfeature_output_formats_from_capabilities(xml_bytes: bytes) -> list[str]:
    """
    WFS 1.0/1.1/2.0 GetCapabilities içinden GetFeature outputFormat adaylarını toplar.
    """
    try:
        root = ET.fromstring(xml_bytes or b"")
    except Exception:
        return []

    values = []

    # WFS 1.1/2.0 (OWS): Operation name="GetFeature" -> Parameter name="outputFormat" -> Value/AllowedValue
    for op in root.iter():
        if _local(op.tag) != "Operation":
            continue
        if (op.attrib.get("name") or "").strip().lower() != "getfeature":
            continue
        for prm in op.iter():
            if _local(prm.tag) != "Parameter":
                continue
            if (prm.attrib.get("name") or "").strip().lower() != "outputformat":
                continue
            for v in prm.iter():
                if _local(v.tag) not in ("Value", "AllowedValue"):
                    continue
                t = (v.text or "").strip()
                if t:
                    values.append(t)

    # WFS 1.0: Capability/Request/GetFeature/ResultFormat/* (tag name format adı olabilir)
    for gf in root.iter():
        if _local(gf.tag) != "GetFeature":
            continue
        for child in gf.iter():
            if _local(child.tag) != "ResultFormat":
                continue
            for fmt_el in list(child):
                # <GML2/> gibi boş elemanlarda tag adını format olarak al
                tag_fmt = _local(fmt_el.tag)
                txt_fmt = (fmt_el.text or "").strip()
                if tag_fmt:
                    values.append(tag_fmt)
                if txt_fmt:
                    values.append(txt_fmt)

    # uniq preserve order
    uniq = []
    seen = set()
    for v in values:
        key = v.strip()
        if not key:
            continue
        low = key.lower()
        if low in seen:
            continue
        seen.add(low)
        uniq.append(key)
    return uniq


def _get_getfeature_output_formats(base_url: str, user: str, pwd: str) -> list[str]:
    attempts = [
        {"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"},
        {"service": "WFS", "request": "GetCapabilities", "version": "1.1.0"},
        {"service": "WFS", "request": "GetCapabilities"},
    ]
    for p in attempts:
        try:
            r = requests.get(base_url, params=p, **_requests_kwargs(user, pwd, 30))
            if r.status_code != 200 or not r.content:
                continue
            fmts = _parse_getfeature_output_formats_from_capabilities(r.content)
            if fmts:
                return fmts
        except Exception:
            continue
    return []


def _shape_candidates_from_supported_formats(supported_formats: list[str]) -> list[str]:
    if not supported_formats:
        return []
    shp_like = []
    generic_zip = []
    for raw in supported_formats:
        s = (raw or "").strip()
        low = s.lower()
        if not s:
            continue
        # Geopackage zip -> SHP değil, ele.
        if "geopackage" in low or "gpkg" in low:
            continue

        # SHP olabilecek net varyasyonları yakala.
        if "shape" in low or "shp" in low:
            shp_like.append(s)
            continue

        # Bazı servisler SHP için sadece generic zip dönebiliyor.
        if low in ("application/zip", "application/x-zip-compressed", "zip"):
            generic_zip.append(s)
    # uniq preserve
    uniq = []
    seen = set()
    for v in shp_like + generic_zip:
        k = v.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(v)
    return uniq


def _looks_like_zip_bytes(content: bytes) -> bool:
    if not content:
        return False
    try:
        return zipfile.is_zipfile(io.BytesIO(content))
    except Exception:
        return False


def _dbf_record_count(dbf_bytes: bytes) -> int | None:
    # DBF header: byte[4:8] -> record count (little-endian uint32)
    if not dbf_bytes or len(dbf_bytes) < 8:
        return None
    return int.from_bytes(dbf_bytes[4:8], byteorder="little", signed=False)


def _shp_zip_record_count(zip_bytes: bytes) -> int | None:
    if not _looks_like_zip_bytes(zip_bytes):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".dbf"):
                    return _dbf_record_count(zf.read(name))
    except Exception:
        return None
    return None


def _wfs_count_features_filtered(
    base_url: str, typename: str, user: str, pwd: str, cql_filter: str
) -> int | None:
    cql_filter = (cql_filter or "").strip()
    if not cql_filter:
        return None

    ogc_xml = _cql_to_ogc_filter_xml(cql_filter)
    attempts = []

    def _add_attempts(filter_mode: str):
        p = {
            "service": "WFS",
            "request": "GetFeature",
            "version": "2.0.0",
            "typenames": typename,
            "resultType": "hits",
        }
        if filter_mode in ("cql", "both"):
            p["CQL_FILTER"] = cql_filter
        if filter_mode in ("ogc", "both") and ogc_xml:
            p["FILTER"] = ogc_xml
        attempts.append(p)

        p = {
            "service": "WFS",
            "request": "GetFeature",
            "version": "1.1.0",
            "typename": typename,
            "resultType": "hits",
        }
        if filter_mode in ("cql", "both"):
            p["CQL_FILTER"] = cql_filter
        if filter_mode in ("ogc", "both") and ogc_xml:
            p["FILTER"] = ogc_xml
        attempts.append(p)

        p = {
            "service": "WFS",
            "request": "GetFeature",
            "typename": typename,
            "resultType": "hits",
        }
        if filter_mode in ("cql", "both"):
            p["CQL_FILTER"] = cql_filter
        if filter_mode in ("ogc", "both") and ogc_xml:
            p["FILTER"] = ogc_xml
        attempts.append(p)

    _add_attempts("cql")
    _add_attempts("ogc")
    _add_attempts("both")

    for p in attempts:
        try:
            r = requests.get(base_url, params=p, **_requests_kwargs(user, pwd, 25))
            if r.status_code != 200 or not r.content or _is_ows_exception(r.content):
                continue
            root = ET.fromstring(r.content)
            for attr in ("numberMatched", "numberOfFeatures", "totalFeatures"):
                val = root.attrib.get(attr)
                if val and val.isdigit():
                    return int(val)
        except Exception:
            continue
    return None


def _extract_member_features_and_ids(gml_bytes: bytes) -> tuple[int, list[str]]:
    """
    GML içinden featureMember/member düğümlerini sayar ve feature id'lerini toplar.
    """
    if not gml_bytes:
        return 0, []
    try:
        root = ET.fromstring(gml_bytes)
    except Exception:
        return 0, []

    features = []
    for el in root.iter():
        if _local(el.tag) in ("member", "featureMember"):
            for child in list(el):
                features.append(child)
                break

    ids = []
    for f in features:
        fid = (
            f.attrib.get("{http://www.opengis.net/gml}id")
            or f.attrib.get("gml:id")
            or f.attrib.get("fid")
            or f.attrib.get("id")
        )
        if fid:
            ids.append(str(fid))

    # uniq preserve order
    uniq_ids = []
    seen = set()
    for v in ids:
        if v in seen:
            continue
        seen.add(v)
        uniq_ids.append(v)

    return len(features), uniq_ids


def _getfeature_shape_zip(
    base_url: str,
    typename: str,
    user: str,
    pwd: str,
    cql_filter: str | None = None,
    output_candidates_override: list[str] | None = None,
    expected_filtered_count: int | None = None,
    feature_ids: list[str] | None = None,
):
    auth_kw = _requests_kwargs(user, pwd, 120)
    output_candidates = output_candidates_override or [
        "shape-zip",
        "SHAPE-ZIP",
        "application/zip",
        "application/x-zip-compressed",
        "shapezip",
        "application/x-shapefile",
        "shp",
    ]

    ids = [str(x).strip() for x in (feature_ids or []) if str(x).strip()]
    if len(ids) > 1000:
        # Aşırı büyük listelerde body/query şişmesini önle
        ids = ids[:1000]
    ids_csv = ",".join(ids) if ids else ""

    def _mk_params(d: dict, filter_mode: str = "both", version_hint: str = "") -> dict:
        if cql_filter and filter_mode != "ids_only":
            if filter_mode in ("cql", "both"):
                d["CQL_FILTER"] = cql_filter
            if filter_mode in ("ogc", "both"):
                ogc_xml = _cql_to_ogc_filter_xml(cql_filter)
                if ogc_xml:
                    d["FILTER"] = ogc_xml
        if ids_csv:
            v = (version_hint or "").strip()
            if v == "2.0.0":
                d["resourceID"] = ids_csv
            else:
                d["FEATUREID"] = ids_csv
        return d

    attempts = []
    # Filtreli SHP taleplerinde bazı servisler CQL veya FILTER'dan sadece birini kabul eder.
    # Feature id üretilebildiyse en hızlı ve en deterministik deneme olarak önce ids_only deneriz.
    filter_modes = ["cql", "ogc", "both"] if cql_filter else ["both"]
    if cql_filter and ids_csv:
        filter_modes = ["ids_only"] + filter_modes
    for filter_mode in filter_modes:
        for of in output_candidates:
            p = {
                "service": "WFS",
                "request": "GetFeature",
                "version": "2.0.0",
                "typenames": typename,
                "outputFormat": of,
                "count": 100000,
            }
            attempts.append(
                _mk_params(p, filter_mode=filter_mode, version_hint="2.0.0")
            )

            p = {
                "service": "WFS",
                "request": "GetFeature",
                "version": "1.1.0",
                "typename": typename,
                "outputFormat": of,
                "maxFeatures": 100000,
            }
            attempts.append(
                _mk_params(p, filter_mode=filter_mode, version_hint="1.1.0")
            )

            p = {
                "service": "WFS",
                "request": "GetFeature",
                "typename": typename,
                "outputFormat": of,
            }
            attempts.append(_mk_params(p, filter_mode=filter_mode, version_hint="1.0.0"))

    last = ""

    def _try_request(method: str, params: dict):
        if method == "POST":
            return requests.post(base_url, data=params, **auth_kw)
        return requests.get(base_url, params=params, **auth_kw)

    for p in attempts:
        try:
            if cql_filter:
                r = _try_request("POST", p)
                if r.status_code == 200 and r.content:
                    if _is_ows_exception(r.content):
                        last = f"OWS Exception (POST) params={p} body={r.text[:300]}"
                    elif _looks_like_zip_bytes(r.content):
                        if cql_filter and expected_filtered_count is not None:
                            got_count = _shp_zip_record_count(r.content)
                            if got_count is None:
                                last = (
                                    "POST zip döndü ama DBF kayıt sayısı okunamadı. "
                                    f"params={p}"
                                )
                                continue
                            if got_count != expected_filtered_count:
                                last = (
                                    "POST zip filtre sonucu uyuşmadı. "
                                    f"expected={expected_filtered_count}, got={got_count}, params={p}"
                                )
                                continue
                        used = "&".join(f"{k}={v}" for k, v in p.items())
                        return r.content, used + " [POST]"
                    else:
                        last = (
                            f"POST yanıtı zip değil. params={p} "
                            f"content-type={r.headers.get('content-type', '')}"
                        )

            r = _try_request("GET", p)
            if r.status_code == 200 and r.content:
                if _is_ows_exception(r.content):
                    last = f"OWS Exception (GET) params={p} body={r.text[:300]}"
                    continue
                if _looks_like_zip_bytes(r.content):
                    if cql_filter and expected_filtered_count is not None:
                        got_count = _shp_zip_record_count(r.content)
                        if got_count is None:
                            last = (
                                "GET zip döndü ama DBF kayıt sayısı okunamadı. "
                                f"params={p}"
                            )
                            continue
                        if got_count != expected_filtered_count:
                            last = (
                                "GET zip filtre sonucu uyuşmadı. "
                                f"expected={expected_filtered_count}, got={got_count}, params={p}"
                            )
                            continue
                    used = "&".join(f"{k}={v}" for k, v in p.items())
                    return r.content, used + " [GET]"
                last = (
                    f"GET yanıtı zip değil. params={p} "
                    f"content-type={r.headers.get('content-type', '')}"
                )
                continue

            last = f"HTTP {r.status_code} {r.text[:200]}"
        except Exception as e:
            last = str(e)

    raise Exception(f"GetFeature (SHP) başarısız: {last}")


def download_xsd_bytes(conn_name: str, typename: str):
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=None, debug=conn_name
        )

    url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    if not url:
        return _result(False, "Hata", "UrlAdress boş.", data=None, debug=str(info))

    resp, err = _describe_feature_type(url, typename, user, pwd)
    if not resp or not resp.content:
        return _result(
            False, "Hata", "DescribeFeatureType başarısız.", data=None, debug=err
        )

    # WFS bazen XSD yerine ExceptionReport döndürür -> kontrol
    if _is_ows_exception(resp.content):
        return _result(
            False,
            "WFS Hatası",
            "Sunucu XSD döndürmedi; OWS ExceptionReport döndürdü.",
            data=None,
            debug=resp.text[:800],
        )

    safe_typename = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", typename)
    ts = datetime.datetime.now().strftime("%Y%m%d")
    filename = f"{safe_typename}_{ts}.xsd"

    return _result(True, "OK", "", data={"filename": filename, "bytes": resp.content})


def download_gml_bytes(conn_name: str, typename: str, cql_filter: str | None = None):
    return download_vector_bytes(
        conn_name=conn_name,
        typename=typename,
        vector_format="gml",
        cql_filter=cql_filter,
    )


def download_vector_bytes(
    conn_name: str,
    typename: str,
    vector_format: str = "gml",
    cql_filter: str | None = None,
):
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=None, debug=conn_name
        )

    url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    fmt = (vector_format or "gml").strip().lower()

    try:
        safe_typename = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", typename)
        ts = datetime.datetime.now().strftime("%Y%m%d")

        if fmt == "shp":
            supported_formats = _get_getfeature_output_formats(url, user, pwd)
            shp_candidates = _shape_candidates_from_supported_formats(supported_formats)
            expected_filtered_count = None
            filtered_feature_ids: list[str] = []
            if (cql_filter or "").strip():
                # 1) En güvenilir yol: filtreli GML'den gerçek feature sayısı + id listesi üret.
                try:
                    gml_bytes, _ = _getfeature_gml(
                        url, typename, user, pwd, cql_filter=cql_filter
                    )
                    cnt, ids = _extract_member_features_and_ids(gml_bytes)
                    expected_filtered_count = cnt
                    filtered_feature_ids = ids
                except Exception:
                    # 2) Fallback: resultType=hits
                    expected_filtered_count = _wfs_count_features_filtered(
                        url, typename, user, pwd, cql_filter
                    )
                    filtered_feature_ids = []

                # Filtreli SHP'de doğrulama yapamıyorsak yanlış dataset döndürmektense hata ver.
                if expected_filtered_count is None:
                    return _result(
                        False,
                        "Hata",
                        "Filtreli SHP indirimi doğrulanamadı.",
                        data=None,
                        debug=(
                            "Filtreli kayıt sayısı hesaplanamadı. "
                            "Servis filtre parametrelerini desteklemiyor olabilir."
                        ),
                    )
                if expected_filtered_count == 0:
                    return _result(
                        False,
                        "Bilgi",
                        "Filtreye uygun kayıt bulunamadı.",
                        data=None,
                        debug=f"cql_filter={cql_filter}",
                    )
            # Capabilities adaylarını kullanırken bilinen SHP fallback'lerini de koru.
            default_shp_candidates = [
                "shape-zip",
                "SHAPE-ZIP",
                "application/x-shapefile",
                "shapezip",
                "shp",
                "application/zip",
                "application/x-zip-compressed",
            ]
            if shp_candidates:
                seen = {c.lower() for c in shp_candidates}
                candidates = shp_candidates + [
                    c for c in default_shp_candidates if c.lower() not in seen
                ]
            else:
                candidates = None

            content, used_params = _getfeature_shape_zip(
                url,
                typename,
                user,
                pwd,
                cql_filter=cql_filter,
                output_candidates_override=candidates,
                expected_filtered_count=expected_filtered_count,
                feature_ids=filtered_feature_ids,
            )
            filename = f"{safe_typename}_{ts}.zip"
            return _result(
                True,
                "OK",
                "",
                data={
                    "filename": filename,
                    "bytes": content,
                    "used_params": used_params,
                    "vector_format": "shp",
                },
            )

        if fmt != "gml":
            return _result(
                False,
                "Hata",
                "Desteklenmeyen vektör formatı. (gml/shp)",
                data=None,
                debug=f"vector_format={vector_format!r}",
            )

        content, used_params = _getfeature_gml(
            url, typename, user, pwd, cql_filter=cql_filter
        )
        filename = f"{safe_typename}_{ts}.gml"
        return _result(
            True,
            "OK",
            "",
            data={
                "filename": filename,
                "bytes": content,
                "used_params": used_params,
                "vector_format": "gml",
            },
        )
    except Exception as e:
        vlabel = "SHP" if fmt == "shp" else "GML"
        if fmt == "shp":
            # SHP desteklenmiyorsa kullanıcıya daha net mesaj göster.
            supported_formats = _get_getfeature_output_formats(url, user, pwd)
            if supported_formats:
                shp_candidates = _shape_candidates_from_supported_formats(supported_formats)
                has_any_zip = any("zip" in (f or "").lower() for f in supported_formats)
                if not shp_candidates and not has_any_zip:
                    return _result(
                        False,
                        "Hata",
                        "Bu WFS servisinde SHP çıktısı desteklenmiyor.",
                        data=None,
                        debug="Desteklenen outputFormat değerleri: "
                        + ", ".join(supported_formats[:40]),
                    )
        return _result(
            False,
            "Hata",
            f"{vlabel} indirilemedi(Servis Hatası).",
            data=None,
            debug=str(e),
        )


def fetch_field_values_all(conn_name: str, typename: str, field: str):
    # Basit: JSON/GeoJSON dene; olmazsa GML parse’e düş.
    info = _get_wfs_conn(conn_name)
    if not info:
        return _result(
            False, "Hata", "Bağlantı kaydı bulunamadı.", data=[], debug=conn_name
        )

    base_url = (info.get("UrlAdress") or "").strip()
    user = (info.get("UserName") or "").strip()
    pwd = info.get("Password") or ""

    auth = _requests_kwargs(user, pwd, 45)
    outs = ["application/json", "application/geo+json", "json", "GeoJSON"]
    PAGE_SIZE = 1000
    HARD_CAP = 200_000

    def try_json():
        for out in outs:
            last_hash = None
            values = []
            start = 0
            while start < HARD_CAP:
                params = {
                    "service": "WFS",
                    "request": "GetFeature",
                    "version": "2.0.0",
                    "typenames": typename,
                    "count": PAGE_SIZE,
                    "startIndex": start,
                    "outputFormat": out,
                    "propertyName": field,
                }
                r = requests.get(base_url, params=params, **auth)
                if r.status_code != 200 or not r.content:
                    break
                cur_hash = hashlib.md5(r.content).hexdigest()
                if last_hash and cur_hash == last_hash:
                    break
                last_hash = cur_hash

                try:
                    data = r.json()
                except Exception:
                    break

                feats = data.get("features") or []
                if not feats:
                    break

                for f in feats:
                    v = (f.get("properties") or {}).get(field)
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v, ensure_ascii=False)
                    values.append(v)

                if len(feats) < PAGE_SIZE:
                    break
                start += PAGE_SIZE

            if values:
                return values
        return None

    def try_gml():
        params = {
            "service": "WFS",
            "request": "GetFeature",
            "version": "2.0.0",
            "typenames": typename,
            "count": 20000,
        }
        r = requests.get(base_url, params=params, **auth)
        if r.status_code != 200 or not r.content:
            return []

        root = ET.fromstring(r.content)

        vals = []
        for el in root.iter():
            if _local(el.tag) == field:
                vals.append(el.text)
        return vals

    try:
        vals = try_json()
        if vals is None:
            vals = try_gml()
        # tekrarlı değerler de dönsün
        vals = ["" if v is None else str(v) for v in vals]
        return _result(True, "OK", "", data=vals)
    except Exception as e:
        return _result(
            False, "Hata", "Alan değerleri alınamadı.", data=[], debug=str(e)
        )


def _cql_to_ogc_filter_xml(cql_filter: str) -> str | None:
    """
    UI'nın ürettiği kontrollü formatı destekler:

      (FIELD = 'value')
      (FIELD IN ('a','b',...))
      ( ... ) AND ( ... ) AND ( ... )

    NOT: Genel CQL parser değil; sadece bizim format.
    OGC Filter 1.1 (ogc:Filter) üretir.
    """
    s = (cql_filter or "").strip()
    if not s:
        return None

    def _xml_escape(v: str) -> str:
        return (v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _split_top_level_and(expr: str) -> list[str]:
        # Parantez derinliğine göre top-level " AND " split
        parts = []
        buf = []
        depth = 0
        i = 0
        while i < len(expr):
            ch = expr[i]
            if ch == "(":
                depth += 1
                buf.append(ch)
                i += 1
                continue
            if ch == ")":
                depth = max(0, depth - 1)
                buf.append(ch)
                i += 1
                continue

            # sadece depth==0 iken AND ayır
            if depth == 0 and expr[i : i + 5].upper() == " AND ":
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                i += 5
                continue

            buf.append(ch)
            i += 1

        tail = "".join(buf).strip()
        if tail:
            parts.append(tail)
        return parts

    def _strip_outer_parens(x: str) -> str:
        x = (x or "").strip()
        if x.startswith("(") and x.endswith(")"):
            return x[1:-1].strip()
        return x

    def _expr_to_ogc(expr: str) -> str | None:
        expr = _strip_outer_parens(expr)

        # FIELD = 'value'
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'((?:''|[^'])*)'$", expr)
        if m:
            field = m.group(1)
            value = m.group(2).replace("''", "'")
            value = _xml_escape(value)
            return f"""<ogc:PropertyIsEqualTo>
  <ogc:PropertyName>{field}</ogc:PropertyName>
  <ogc:Literal>{value}</ogc:Literal>
</ogc:PropertyIsEqualTo>"""

        # FIELD IN ('a','b',...)
        m = re.match(
            r"^([A-Za-z_][A-Za-z0-9_]*)\s+IN\s+\((.*)\)$", expr, flags=re.IGNORECASE
        )
        if m:
            field = m.group(1)
            inside = m.group(2).strip()

            vals = re.findall(r"'((?:''|[^'])*)'", inside)  # '' escape
            if not vals:
                return None

            nodes = []
            for v in vals:
                v = v.replace("''", "'")
                v = _xml_escape(v)
                nodes.append(
                    f"""<ogc:PropertyIsEqualTo>
  <ogc:PropertyName>{field}</ogc:PropertyName>
  <ogc:Literal>{v}</ogc:Literal>
</ogc:PropertyIsEqualTo>"""
                )

            if len(nodes) == 1:
                return nodes[0]

            inner = "\n".join("  " + n.replace("\n", "\n  ") for n in nodes)
            return f"""<ogc:Or>
{inner}
</ogc:Or>"""

        return None

    # 1) AND split
    parts = _split_top_level_and(s)

    # 2) her parçayı OGC node'a çevir
    nodes = []
    for p in parts:
        n = _expr_to_ogc(p)
        if not n:
            return None
        nodes.append(n)

    # 3) tek node ise direkt, çoksa And içine al
    if len(nodes) == 1:
        inner = nodes[0]
    else:
        inner_nodes = "\n".join("  " + n.replace("\n", "\n  ") for n in nodes)
        inner = f"""<ogc:And>
{inner_nodes}
</ogc:And>"""

    return f"""<ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">
{inner}
</ogc:Filter>"""


def _cql_term_to_ogc_predicate(expr: str) -> str | None:
    expr = (expr or "").strip()

    # FIELD = 'value'
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'(.*)'$", expr)
    if m:
        field = m.group(1)
        value = m.group(2).replace("''", "'")
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"""  <ogc:PropertyIsEqualTo>
    <ogc:PropertyName>{field}</ogc:PropertyName>
    <ogc:Literal>{value}</ogc:Literal>
  </ogc:PropertyIsEqualTo>"""

    # FIELD IN ('a','b',...)
    m = re.match(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s+IN\s+\((.*)\)$", expr, flags=re.IGNORECASE
    )
    if m:
        field = m.group(1)
        inside = m.group(2).strip()
        vals = re.findall(r"'((?:''|[^'])*)'", inside)  # '' escape
        if not vals:
            return None

        eqs = []
        for v in vals:
            v = v.replace("''", "'")
            v = v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            eqs.append(
                f"""    <ogc:PropertyIsEqualTo>
      <ogc:PropertyName>{field}</ogc:PropertyName>
      <ogc:Literal>{v}</ogc:Literal>
    </ogc:PropertyIsEqualTo>"""
            )

        if len(eqs) == 1:
            return eqs[0].replace("    ", "  ", 1)  # ufak indent düzeltmesi (opsiyonel)

        return "  <ogc:Or>\n" + "\n".join(eqs) + "\n  </ogc:Or>"

    return None


def _is_ows_exception(xml_bytes: bytes) -> bool:
    if not xml_bytes:
        return False
    head = xml_bytes[:2000].lower()
    # OWS ExceptionReport farklı varyasyonlarla gelebilir
    return b"exceptionreport" in head or b"<exception" in head

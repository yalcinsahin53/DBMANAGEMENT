# services/api_client.py
from __future__ import annotations
import time
from typing import Any, Dict, Optional
import requests
import re
import datetime


class LocalAPIClient:
    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}"

    def wait_ready(self, timeout_sec: float = 3.0) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout_sec:
            try:
                r = requests.get(f"{self.base}/health", timeout=0.5)
                if r.ok:
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    # ----------------------------
    # Internal helpers
    # ----------------------------
    def _safe_json(self, resp: requests.Response) -> Dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            return {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        url = f"{self.base}{path}"
        try:
            resp = requests.request(method, url, json=json, timeout=timeout)
        except Exception as ex:
            # Ağ/bağlantı hatası: UI tarafında gösterilecek ortak format
            return {
                "ok": False,
                "title": "API Bağlantı Hatası",
                "message": f"Local API'ye erişilemedi.\n{ex}",
                "is_save_enabled": False,
                "data": None,
            }

        data = self._safe_json(resp)

        # HTTP hata ise (400/500) -> detail varsa al, yoksa raw text
        if not resp.ok:
            detail = None
            if isinstance(data, dict):
                detail = data.get("detail") or data.get("message")
            if not detail:
                detail = resp.text.strip() or f"HTTP {resp.status_code}"

            return {
                "ok": False,
                "title": "API Hatası",
                "message": str(detail),
                "is_save_enabled": False,
                "data": data.get("data") if isinstance(data, dict) else None,
            }

        # OK ise JSON dict döner (endpoint'e göre)
        if isinstance(data, dict) and data:
            return data

        # Endpoint boş döndüyse
        return {"ok": True}

    # ----------------------------
    # DB API methods
    # ----------------------------
    def db_check(
        self, host: str, port: str, user: str, password: str, database: str
    ) -> Dict[str, Any]:
        payload = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }
        res = self._request("POST", "/api/v1/db/check", json=payload, timeout=10)

        # UI uyumu: title/message/is_save_enabled garanti olsun
        if "title" not in res:
            res["title"] = "Bilgi" if res.get("ok") else "Hata"
        if "message" not in res:
            res["message"] = ""
        if "is_save_enabled" not in res:
            res["is_save_enabled"] = bool(res.get("ok"))
        return res

    def db_save(
        self,
        conn_name: str,
        host: str,
        port: str,
        user: str,
        password: str,
        database: str,
        db_type: str,
    ) -> Dict[str, Any]:
        payload = {
            "conn_name": conn_name,
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "db_type": db_type,
        }
        res = self._request("POST", "/api/v1/db/save", json=payload, timeout=10)

        if "title" not in res:
            res["title"] = "Başarılı" if res.get("ok") else "Hata"
        if "message" not in res:
            res["message"] = ""
        if "is_save_enabled" not in res:
            # save sonrası genelde tekrar kaydet kapalı
            res["is_save_enabled"] = False
        return res

    def db_list(self) -> Dict[str, Any]:
        # {"ok": True, "data": [...], "message": ""}
        res = self._request("GET", "/api/v1/db/list", timeout=10)
        if "data" not in res:
            res["data"] = []
        if "message" not in res:
            res["message"] = res.get("message", "")
        if "ok" not in res:
            res["ok"] = True
        return res

    def db_get(self, no: int) -> Dict[str, Any]:
        res = self._request("GET", f"/api/v1/db/get/{no}", timeout=10)
        if "message" not in res:
            res["message"] = ""
        return res

    def db_update(
        self,
        no: int,
        conn_name: str,
        database: str,
        host: str,
        port: str,
        user: str,
        password: str,
        db_type: str,
    ) -> Dict[str, Any]:
        payload = {
            "no": no,
            "conn_name": conn_name,
            "database": database,
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "db_type": db_type,
        }
        res = self._request("POST", "/api/v1/db/update", json=payload, timeout=10)
        # update endpoint'i: {"ok": bool, "message": "..."}
        if "ok" not in res:
            res["ok"] = True
        if "message" not in res:
            res["message"] = "Güncelleme tamamlandı."
        return res

    def wfs_check(
        self, urladress: str, username: str = "", password: str = "", timeout: int = 10
    ):
        payload = {
            "urladress": urladress,
            "username": username,
            "password": password,
            "timeout": timeout,
        }
        res = self._request(
            "POST", "/api/v1/wfs/check", json=payload, timeout=timeout + 5
        )

        # UI uyumu
        if "title" not in res:
            res["title"] = "Başarılı" if res.get("ok") else "Hata"
        if "message" not in res:
            res["message"] = ""
        if "is_save_enabled" not in res:
            res["is_save_enabled"] = bool(res.get("ok"))
        return res

    def wfs_save(
        self, conn_name: str, urladress: str, username: str = "", password: str = ""
    ):
        payload = {
            "conn_name": conn_name,
            "urladress": urladress,
            "username": username,
            "password": password,
        }
        res = self._request("POST", "/api/v1/wfs/save", json=payload, timeout=10)

        if "title" not in res:
            res["title"] = "Başarılı" if res.get("ok") else "Hata"
        if "message" not in res:
            res["message"] = ""
        if "is_save_enabled" not in res:
            res["is_save_enabled"] = False
        return res

    # ----------------------------
    # WFS API methods (FIXED)
    # ----------------------------
    def wfs_list(self) -> Dict[str, Any]:
        # Beklenen: {"ok": True, "data": [...], "message": "", "debug": ""}
        res = self._request("GET", "/api/v1/wfs/list", timeout=10)

        # Normalize
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "title" not in res:
            res["title"] = "OK" if res.get("ok") else "Hata"

        return res

    def wfs_typenames(self, conn_name: str) -> Dict[str, Any]:
        # GET endpoint; query paramları path'e ekliyoruz
        path = f"/api/v1/wfs/typenames?conn_name={requests.utils.quote(conn_name)}"

        print("WFS TYPENAMES PATH:", self.base + path)

        res = self._request("GET", path, timeout=30)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "title" not in res:
            res["title"] = "OK" if res.get("ok") else "Hata"
        return res

    def wfs_fields(self, conn_name: str, typename: str) -> Dict[str, Any]:
        q1 = requests.utils.quote(conn_name)
        q2 = requests.utils.quote(typename)
        path = f"/api/v1/wfs/fields?conn_name={q1}&typename={q2}"
        res = self._request("GET", path, timeout=45)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "title" not in res:
            res["title"] = "OK" if res.get("ok") else "Hata"
        return res

    def wfs_count(self, conn_name: str, typename: str) -> Dict[str, Any]:
        q1 = requests.utils.quote(conn_name)
        q2 = requests.utils.quote(typename)
        path = f"/api/v1/wfs/count?conn_name={q1}&typename={q2}"
        res = self._request("GET", path, timeout=30)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = {"count": None}
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "title" not in res:
            res["title"] = "OK" if res.get("ok") else "Hata"
        return res

    def wfs_field_values(
        self, conn_name: str, typename: str, field: str
    ) -> Dict[str, Any]:
        q1 = requests.utils.quote(conn_name)
        q2 = requests.utils.quote(typename)
        q3 = requests.utils.quote(field)
        path = f"/api/v1/wfs/field-values?conn_name={q1}&typename={q2}&field={q3}"
        res = self._request("GET", path, timeout=120)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "title" not in res:
            res["title"] = "OK" if res.get("ok") else "Hata"
        return res

    def wfs_download_vector_bytes(
        self,
        conn_name: str,
        typename: str,
        vector_format: str = "gml",
        timeout: int = 180,
        cql_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        fmt = (vector_format or "gml").strip().lower()
        if fmt not in ("gml", "shp"):
            return {
                "ok": False,
                "title": "Hata",
                "message": "Desteklenmeyen vektör formatı. (gml/shp)",
                "debug": f"vector_format={vector_format!r}",
            }

        url = f"{self.base}/api/v1/wfs/download-vector"
        params = {"conn_name": conn_name, "typename": typename, "vector_format": fmt}
        if cql_filter:
            params["cql_filter"] = cql_filter

        try:
            r = requests.get(url, params=params, timeout=timeout)
        except Exception as ex:
            return {
                "ok": False,
                "title": "API Bağlantı Hatası",
                "message": f"Vektör veri indirilemedi.\n{ex}",
                "debug": str(ex),
            }

        if not r.ok:

            try:
                j = r.json()

                detail = j.get("detail", j)
                if isinstance(detail, dict):
                    msg = detail.get("message") or "API hatası"
                    dbg = detail.get("debug") or ""
                    ttl = detail.get("title") or "API Hatası"
                    return {
                        "ok": False,
                        "title": ttl,
                        "message": msg,
                        "debug": dbg or r.text[:800],
                    }
                return {
                    "ok": False,
                    "title": "API Hatası",
                    "message": str(detail),
                    "debug": r.text[:800],
                }

            except Exception:
                return {
                    "ok": False,
                    "title": "API Hatası",
                    "message": f"HTTP {r.status_code}",
                    "debug": r.text[:400],
                }

        # r.ok True olsa bile içerik ExceptionReport olabilir
        head = (r.content or b"")[:2000].lower()
        if b"exceptionreport" in head or b"<exception" in head:
            return {
                "ok": False,
                "title": "WFS Hatası",
                "message": "Sunucu vektör veri döndürmedi; OWS ExceptionReport döndürdü (muhtemelen outputFormat desteklenmiyor).",
                "debug": r.text[:800],
            }

        cd = r.headers.get("content-disposition", "")
        filename = "wfs_export.zip" if fmt == "shp" else "wfs_export.gml"
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip().strip('"')

        return {"ok": True, "filename": filename, "bytes": r.content, "vector_format": fmt}

    def wfs_download_gml_bytes(
        self,
        conn_name: str,
        typename: str,
        timeout: int = 180,
        cql_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.wfs_download_vector_bytes(
            conn_name=conn_name,
            typename=typename,
            vector_format="gml",
            timeout=timeout,
            cql_filter=cql_filter,
        )

    def wfs_download_xsd_bytes(
        self, conn_name: str, typename: str, timeout: int = 60
    ) -> dict:
        url = f"{self.base}/api/v1/wfs/download-xsd"
        params = {"conn_name": conn_name, "typename": typename}

        try:
            r = requests.get(url, params=params, timeout=timeout)
        except Exception as ex:
            return {
                "ok": False,
                "title": "API Bağlantı Hatası",
                "message": f"XSD indirilemedi.\n{ex}",
                "debug": str(ex),
            }

        if not r.ok:
            try:
                j = r.json()
                detail = j.get("detail", j)
                if isinstance(detail, dict):
                    return {
                        "ok": False,
                        "title": detail.get("title") or "API Hatası",
                        "message": detail.get("message") or "XSD indirilemedi.",
                        "debug": detail.get("debug") or r.text[:800],
                    }
                return {
                    "ok": False,
                    "title": "API Hatası",
                    "message": str(detail),
                    "debug": r.text[:800],
                }
            except Exception:
                return {
                    "ok": False,
                    "title": "API Hatası",
                    "message": f"HTTP {r.status_code}",
                    "debug": r.text[:400],
                }

        cd = r.headers.get("content-disposition", "")
        filename = "schema.xsd"
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip().strip('"')

        # content ExceptionReport olabilir (ek kontrol)
        head = (r.content or b"")[:2000].lower()
        if b"exceptionreport" in head or b"<exception" in head:
            return {
                "ok": False,
                "title": "WFS Hatası",
                "message": "Sunucu XSD döndürmedi; ExceptionReport döndürdü.",
                "debug": r.text[:800],
            }

        return {"ok": True, "filename": filename, "bytes": r.content}

    def wfs_typenames_meta(self, conn_name: str) -> Dict[str, Any]:
        q1 = requests.utils.quote(conn_name)
        path = f"/api/v1/wfs/typenames-meta?conn_name={q1}"
        return self._request("GET", path, timeout=60)

    def wfs_fields_meta(self, conn_name: str, typename: str) -> Dict[str, Any]:
        q1 = requests.utils.quote(conn_name)
        q2 = requests.utils.quote(typename)
        path = f"/api/v1/wfs/fields-meta?conn_name={q1}&typename={q2}"
        return self._request("GET", path, timeout=60)

    # services/api_client.py içine ekle
    def postgis_create_schema(self, conn_name: str, schema_name: str) -> dict:
        payload = {"conn_name": conn_name, "schema_name": schema_name}
        res = self._request(
            "POST", "/api/v1/db/create-postgis", json=payload, timeout=20
        )

        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""

        return res

    def postgis_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name)
        path = f"/api/v1/db/postgis-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createfeature_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name)
        path = f"/api/v1/db/createfeature-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createfeature_create_dataset(
        self,
        conn_name: str,
        schema_name: str,
        dataset_name: str,
        dataset_alias: str,
        geometry_type: str,
        geometry_column: str,
        srid: int | None,
        fields: list[dict],
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "dataset_alias": dataset_alias,
            "geometry_type": geometry_type,
            "geometry_column": geometry_column,
            "srid": srid,
            "fields": fields or [],
        }
        res = self._request(
            "POST", "/api/v1/db/createfeature-dataset", json=payload, timeout=120
        )

        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def createesrifeature_create_dataset(
        self,
        conn_name: str,
        schema_name: str,
        dataset_name: str,
        dataset_alias: str,
        geometry_type: str,
        geometry_column: str,
        srid: int | None,
        fields: list[dict],
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "dataset_alias": dataset_alias,
            "geometry_type": geometry_type,
            "geometry_column": geometry_column,
            "srid": srid,
            "fields": fields or [],
        }
        res = self._request(
            "POST", "/api/v1/db/createesrifeature-dataset", json=payload, timeout=180
        )

        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def createandeditfield_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name or "")
        path = f"/api/v1/db/createandeditfield-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createandeditfield_list_datasets(self, conn_name: str, schema_name: str) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = f"/api/v1/db/createandeditfield-datasets?conn_name={q1}&schema_name={q2}"
        res = self._request("GET", path, timeout=45)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createandeditfield_list_fields(
        self, conn_name: str, schema_name: str, dataset_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        q3 = requests.utils.quote(dataset_name or "")
        path = (
            "/api/v1/db/createandeditfield-fields"
            f"?conn_name={q1}&schema_name={q2}&dataset_name={q3}"
        )
        res = self._request("GET", path, timeout=60)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createandeditfield_add_field(
        self,
        conn_name: str,
        schema_name: str,
        dataset_name: str,
        field: dict,
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "field": field or {},
        }
        res = self._request(
            "POST", "/api/v1/db/createandeditfield-add-field", json=payload, timeout=60
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def createandeditfield_update_field(
        self,
        conn_name: str,
        schema_name: str,
        dataset_name: str,
        old_field_name: str,
        field: dict,
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "old_field_name": old_field_name,
            "field": field or {},
        }
        res = self._request(
            "POST",
            "/api/v1/db/createandeditfield-update-field",
            json=payload,
            timeout=90,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def createandeditfield_delete_field(
        self, conn_name: str, schema_name: str, dataset_name: str, field_name: str
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "field_name": field_name,
        }
        res = self._request(
            "POST",
            "/api/v1/db/createandeditfield-delete-field",
            json=payload,
            timeout=45,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def createandeditfieldesri_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name or "")
        path = f"/api/v1/db/createandeditfieldesri-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createandeditfieldesri_list_datasets(
        self, conn_name: str, schema_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = (
            f"/api/v1/db/createandeditfieldesri-datasets?conn_name={q1}&schema_name={q2}"
        )
        res = self._request("GET", path, timeout=45)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createandeditfieldesri_list_fields(
        self, conn_name: str, schema_name: str, dataset_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        q3 = requests.utils.quote(dataset_name or "")
        path = (
            "/api/v1/db/createandeditfieldesri-fields"
            f"?conn_name={q1}&schema_name={q2}&dataset_name={q3}"
        )
        res = self._request("GET", path, timeout=60)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def createandeditfieldesri_add_field(
        self,
        conn_name: str,
        schema_name: str,
        dataset_name: str,
        field: dict,
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "field": field or {},
        }
        res = self._request(
            "POST",
            "/api/v1/db/createandeditfieldesri-add-field",
            json=payload,
            timeout=60,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def createandeditfieldesri_update_field(
        self,
        conn_name: str,
        schema_name: str,
        dataset_name: str,
        old_field_name: str,
        field: dict,
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "old_field_name": old_field_name,
            "field": field or {},
        }
        res = self._request(
            "POST",
            "/api/v1/db/createandeditfieldesri-update-field",
            json=payload,
            timeout=90,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def createandeditfieldesri_delete_field(
        self, conn_name: str, schema_name: str, dataset_name: str, field_name: str
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "field_name": field_name,
        }
        res = self._request(
            "POST",
            "/api/v1/db/createandeditfieldesri-delete-field",
            json=payload,
            timeout=45,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def dbcheckdublicateanddelete_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name or "")
        path = f"/api/v1/db/dbcheckdublicateanddelete-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddelete_list_datasets(self, conn_name: str, schema_name: str) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = f"/api/v1/db/dbcheckdublicateanddelete-datasets?conn_name={q1}&schema_name={q2}"
        res = self._request("GET", path, timeout=45)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddelete_list_fields(
        self, conn_name: str, schema_name: str, dataset_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        q3 = requests.utils.quote(dataset_name or "")
        path = (
            "/api/v1/db/dbcheckdublicateanddelete-fields"
            f"?conn_name={q1}&schema_name={q2}&dataset_name={q3}"
        )
        res = self._request("GET", path, timeout=60)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddelete_analyze(
        self, conn_name: str, schema_name: str, dataset_name: str, field_name: str
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "field_name": field_name,
        }
        res = self._request(
            "POST",
            "/api/v1/db/dbcheckdublicateanddelete-analyze",
            json=payload,
            timeout=120,
        )
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = {"rows": [], "duplicate_row_count": 0, "duplicate_group_count": 0, "feature_count": 0}
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddelete_delete(
        self, conn_name: str, schema_name: str, dataset_name: str, row_ref: str
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "row_ref": row_ref,
        }
        res = self._request(
            "POST",
            "/api/v1/db/dbcheckdublicateanddelete-delete",
            json=payload,
            timeout=60,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def dbcheckdublicateanddeleteesri_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name or "")
        path = f"/api/v1/db/dbcheckdublicateanddeleteesri-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddeleteesri_list_datasets(
        self, conn_name: str, schema_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = (
            "/api/v1/db/dbcheckdublicateanddeleteesri-datasets"
            f"?conn_name={q1}&schema_name={q2}"
        )
        res = self._request("GET", path, timeout=45)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddeleteesri_list_fields(
        self, conn_name: str, schema_name: str, dataset_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        q3 = requests.utils.quote(dataset_name or "")
        path = (
            "/api/v1/db/dbcheckdublicateanddeleteesri-fields"
            f"?conn_name={q1}&schema_name={q2}&dataset_name={q3}"
        )
        res = self._request("GET", path, timeout=60)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddeleteesri_analyze(
        self, conn_name: str, schema_name: str, dataset_name: str, field_name: str
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "field_name": field_name,
        }
        res = self._request(
            "POST",
            "/api/v1/db/dbcheckdublicateanddeleteesri-analyze",
            json=payload,
            timeout=120,
        )
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = {
                "rows": [],
                "duplicate_row_count": 0,
                "duplicate_group_count": 0,
                "feature_count": 0,
            }
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbcheckdublicateanddeleteesri_delete(
        self, conn_name: str, schema_name: str, dataset_name: str, row_ref: str
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_name": dataset_name,
            "row_ref": row_ref,
        }
        res = self._request(
            "POST",
            "/api/v1/db/dbcheckdublicateanddeleteesri-delete",
            json=payload,
            timeout=60,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def dbdeletefeature_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name or "")
        path = f"/api/v1/db/dbdeletefeature-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbdeletefeature_list_datasets(self, conn_name: str, schema_name: str) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = f"/api/v1/db/dbdeletefeature-datasets?conn_name={q1}&schema_name={q2}"
        res = self._request("GET", path, timeout=60)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbdeletefeature_delete_datasets(
        self, conn_name: str, schema_name: str, dataset_names: list[str]
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_names": dataset_names or [],
        }
        res = self._request(
            "POST",
            "/api/v1/db/dbdeletefeature-delete-datasets",
            json=payload,
            timeout=120,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def dbdeletefeatureesri_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name or "")
        path = f"/api/v1/db/dbdeletefeatureesri-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbdeletefeatureesri_list_datasets(
        self, conn_name: str, schema_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = f"/api/v1/db/dbdeletefeatureesri-datasets?conn_name={q1}&schema_name={q2}"
        res = self._request("GET", path, timeout=60)
        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def dbdeletefeatureesri_delete_datasets(
        self, conn_name: str, schema_name: str, dataset_names: list[str]
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "dataset_names": dataset_names or [],
        }
        res = self._request(
            "POST",
            "/api/v1/db/dbdeletefeatureesri-delete-datasets",
            json=payload,
            timeout=120,
        )
        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        if "data" not in res:
            res["data"] = None
        return res

    def postgis_dbmatch_vector_structure(self, file_path: str) -> dict:
        q = requests.utils.quote(file_path or "")
        path = f"/api/v1/db/dbmatch-vector-structure?file_path={q}"
        res = self._request("GET", path, timeout=120)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = {"layers": [], "file_name": ""}
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def postgis_dbmatch_schema_tables(self, conn_name: str, schema_name: str) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = f"/api/v1/db/dbmatch-schema-tables?conn_name={q1}&schema_name={q2}"
        res = self._request("GET", path, timeout=60)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def postgis_dbmatch_table_columns(self, conn_name: str, schema_name: str, table_name: str) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        q3 = requests.utils.quote(table_name or "")
        path = (
            "/api/v1/db/dbmatch-table-columns"
            f"?conn_name={q1}&schema_name={q2}&table_name={q3}"
        )
        res = self._request("GET", path, timeout=60)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def postgis_dbmatch_load(
        self,
        conn_name: str,
        schema_name: str,
        file_path: str,
        layer_mappings: list[dict],
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "file_path": file_path,
            "layer_mappings": layer_mappings or [],
        }
        res = self._request(
            "POST", "/api/v1/db/dbmatch-load-postgis", json=payload, timeout=7200
        )

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = {"results": [], "success_count": 0, "failed_count": 0}
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def esri_dbmatch_vector_structure(self, file_path: str) -> dict:
        q = requests.utils.quote(file_path or "")
        path = f"/api/v1/db/dbmatchesri-vector-structure?file_path={q}"
        res = self._request("GET", path, timeout=120)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = {"layers": [], "file_name": ""}
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def esri_dbmatch_schema_tables(self, conn_name: str, schema_name: str) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        path = f"/api/v1/db/dbmatchesri-schema-tables?conn_name={q1}&schema_name={q2}"
        res = self._request("GET", path, timeout=60)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def esri_dbmatch_table_columns(
        self, conn_name: str, schema_name: str, table_name: str
    ) -> dict:
        q1 = requests.utils.quote(conn_name or "")
        q2 = requests.utils.quote(schema_name or "")
        q3 = requests.utils.quote(table_name or "")
        path = (
            "/api/v1/db/dbmatchesri-table-columns"
            f"?conn_name={q1}&schema_name={q2}&table_name={q3}"
        )
        res = self._request("GET", path, timeout=60)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def esri_dbmatch_load(
        self,
        conn_name: str,
        schema_name: str,
        file_path: str,
        layer_mappings: list[dict],
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "file_path": file_path,
            "layer_mappings": layer_mappings or [],
        }
        res = self._request("POST", "/api/v1/db/dbmatch-load-esri", json=payload, timeout=7200)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = {"results": [], "success_count": 0, "failed_count": 0}
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def postgis_import_vector(
        self, conn_name: str, schema_name: str, file_path: str, manual_epsg: int | None = None
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "file_path": file_path,
            "manual_epsg": manual_epsg,
        }
        res = self._request(
            "POST", "/api/v1/db/import-vector-postgis", json=payload, timeout=7200
        )

        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def postgis_create_features_from_xsd(
        self, conn_name: str, schema_name: str, xsd_path: str
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "xsd_path": xsd_path,
        }
        res = self._request(
            "POST", "/api/v1/db/create-feature-from-xsd-postgis", json=payload, timeout=7200
        )

        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def esri_create_features_from_xsd(
        self,
        conn_name: str,
        schema_name: str,
        xsd_path: str,
        manual_epsg: int | None = None,
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "xsd_path": xsd_path,
            "manual_epsg": manual_epsg,
        }
        res = self._request(
            "POST", "/api/v1/db/create-feature-from-xsd-esri", json=payload, timeout=7200
        )

        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def esri_db_list_schemas(self, conn_name: str) -> dict:
        q = requests.utils.quote(conn_name)
        path = f"/api/v1/db/esri-db-schemas?conn_name={q}"
        res = self._request("GET", path, timeout=30)

        if "ok" not in res:
            res["ok"] = False
        if "data" not in res or res["data"] is None:
            res["data"] = []
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

    def esri_db_import_vector(
        self, conn_name: str, schema_name: str, file_path: str, manual_epsg: int | None = None
    ) -> dict:
        payload = {
            "conn_name": conn_name,
            "schema_name": schema_name,
            "file_path": file_path,
            "manual_epsg": manual_epsg,
        }
        res = self._request(
            "POST", "/api/v1/db/import-vector-esri-db-stg", json=payload, timeout=1800
        )

        if "ok" not in res:
            res["ok"] = False
        if "message" not in res:
            res["message"] = ""
        if "debug" not in res:
            res["debug"] = ""
        return res

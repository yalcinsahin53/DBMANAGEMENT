from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import base64
import os
import re
import shutil
import subprocess
import sys
import importlib.util
import json

import psycopg2
from psycopg2 import sql

from core.storage import open_db


router = APIRouter(tags=["db-createesrifeature"])

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CreateEsriFeatureFieldReq(BaseModel):
    name: str
    alias: str = ""
    data_type: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True


class CreateEsriFeatureDatasetReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_name: str
    dataset_alias: str = ""
    geometry_type: str = "none"
    geometry_column: str = "shape"
    srid: int | None = 4326
    fields: list[CreateEsriFeatureFieldReq] = Field(default_factory=list)


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


def _is_esri_dbtype(v: str) -> bool:
    return _normalize_db_type(v) in (
        "esri geodatabase",
        "enterprise geodatabase",
        "esri enterprise geodatabase",
        "esri",
    )


def _validate_esri_conn(conn_name: str):
    info = _get_db_connection_by_name(conn_name)
    if not info:
        return None, {"ok": False, "message": "Bağlantı bulunamadı.", "debug": conn_name}

    if not _is_esri_dbtype(info.get("DbType")):
        return None, {
            "ok": False,
            "message": "Seçilen bağlantı Esri Geodatabase değil (DbType=Esri Geodatabase olmalı).",
            "debug": f"DbType={info.get('DbType')}",
        }
    return info, None


def _connect_db(info: dict):
    return psycopg2.connect(
        host=info.get("Host"),
        port=str(info.get("Port")),
        user=info.get("UserName"),
        password=info.get("Password") or "",
        database=info.get("Database"),
    )


def _candidate_arcgis_python_paths() -> list[str]:
    candidates: list[str] = []
    for exe_name in ("propy", "propy.bat", "python.exe"):
        found = shutil.which(exe_name)
        if found:
            candidates.append(found)
    for env_name in (
        "ARCGIS_PRO_PYTHON",
        "ARCGIS_PRO_PYTHON_EXE",
        "ARCMAP_PYTHON",
        "ARCMAP_PYTHON_EXE",
        "ARCGIS_DESKTOP_PYTHON",
        "ARCGIS_DESKTOP_PYTHON_EXE",
    ):
        v = (os.environ.get(env_name) or "").strip()
        if v:
            candidates.append(v)

    current_exe = sys.executable
    if current_exe:
        candidates.append(current_exe)

    program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
    candidates.extend(
        [
            os.path.join(
                program_files,
                "ArcGIS",
                "Pro",
                "bin",
                "Python",
                "envs",
                "arcgispro-py3",
                "python.exe",
            ),
            os.path.join(
                program_files,
                "ArcGIS",
                "Pro",
                "bin",
                "Python",
                "Scripts",
                "propy.bat",
            ),
            r"C:\Python27\ArcGIS10.8\python.exe",
            r"C:\Python27\ArcGIS10.8\pythonw.exe",
            r"C:\Python27\ArcGIS10.7\python.exe",
            r"C:\Python27\ArcGISx6410.8\python.exe",
            r"C:\Python27\ArcGISx6410.7\python.exe",
        ]
    )
    uniq = []
    seen = set()
    for c in candidates:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


def _can_import_arcpy_with(executable: str) -> bool:
    if not executable:
        return False

    lower_exec = executable.lower()
    if lower_exec.endswith(".bat") or lower_exec.endswith(".cmd"):
        cmd = ["cmd", "/c", executable, "-c", "import arcpy"]
    else:
        cmd = [executable, "-c", "import arcpy"]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _find_arcgis_python() -> str | None:
    try:
        if importlib.util.find_spec("arcpy") is not None and sys.executable:
            return sys.executable
    except Exception:
        pass

    for candidate in _candidate_arcgis_python_paths():
        try:
            if (
                candidate
                and os.path.exists(candidate)
                and candidate != sys.executable
                and _can_import_arcpy_with(candidate)
            ):
                return candidate
        except Exception:
            continue
    return None


def _is_valid_ident(name: str) -> bool:
    return bool(_IDENT_RE.match((name or "").strip()))


def _normalize_field_type(v: str) -> str:
    s = (v or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    aliases = {
        "string": "varchar",
        "character varying": "varchar",
        "char varying": "varchar",
        "character": "char",
        "bpchar": "char",
        "int": "integer",
        "long": "bigint",
        "decimal": "numeric",
        "double": "double precision",
        "float": "double precision",
        "bool": "boolean",
        "datetime": "timestamp",
        "timestamp without time zone": "timestamp",
    }
    return aliases.get(s, s)


def _resolve_field_sql_type(
    data_type: str,
    length: int | None,
    precision: int | None,
    scale: int | None,
) -> tuple[str | None, str]:
    t = _normalize_field_type(data_type)

    if t == "varchar":
        ln = 255 if length is None else int(length)
        if ln < 1 or ln > 10485760:
            return None, "Karakter sayısı 1-10485760 arasında olmalı."
        return f"varchar({ln})", ""

    if t == "char":
        ln = 1 if length is None else int(length)
        if ln < 1 or ln > 10485760:
            return None, "Karakter sayısı 1-10485760 arasında olmalı."
        return f"char({ln})", ""

    if t == "numeric":
        p = None if precision is None else int(precision)
        s = None if scale is None else int(scale)

        if s is not None and p is None:
            return None, "Scale girildiyse precision da girilmelidir."
        if p is None:
            return "numeric", ""
        if p < 1 or p > 1000:
            return None, "Precision 1-1000 arasında olmalı."
        if s is None:
            return f"numeric({p})", ""
        if s < 0:
            return None, "Scale 0 veya daha büyük olmalı."
        if s > p:
            return None, "Scale precision değerinden büyük olamaz."
        return f"numeric({p},{s})", ""

    if t in (
        "text",
        "integer",
        "bigint",
        "double precision",
        "boolean",
        "date",
        "timestamp",
    ):
        if t == "timestamp":
            return "timestamp without time zone", ""
        return t, ""

    return None, f"Desteklenmeyen alan tipi: {data_type}"


def _is_esri_addfield_supported_type(data_type: str) -> bool:
    t = _normalize_field_type(data_type)
    return t in (
        "text",
        "varchar",
        "char",
        "integer",
        "numeric",
        "double precision",
        "date",
        "timestamp",
    )


def _normalize_geometry_type(v: str) -> tuple[str | None, str]:
    s = (v or "").strip().lower()
    s = s.replace("_", "").replace("-", "").replace(" ", "")
    mapping = {
        "none": None,
        "nogeometry": None,
        "point": "Point",
        "multipoint": "MultiPoint",
        "linestring": "LineString",
        "multilinestring": "MultiLineString",
        "polygon": "Polygon",
        "multipolygon": "MultiPolygon",
        "geometry": "Geometry",
    }
    if s not in mapping:
        return None, f"Geçersiz geometri tipi: {v}"
    return mapping[s], ""


def _find_st_geometry_schema(cur) -> str | None:
    cur.execute(
        """
        SELECT n.nspname
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = 'st_geometry'
        ORDER BY CASE WHEN n.nspname = 'sde' THEN 0 ELSE 1 END, n.nspname
        LIMIT 1
        """
    )
    row = cur.fetchone()
    return row[0] if row else None


def _arcgis_register_geometry_type(geom_type: str) -> str:
    mapping = {
        "Point": "POINT",
        "MultiPoint": "MULTIPOINT",
        "LineString": "POLYLINE",
        "MultiLineString": "POLYLINE",
        "Polygon": "POLYGON",
        "MultiPolygon": "POLYGON",
        "Geometry": "POLYGON",
    }
    return mapping.get(geom_type, geom_type.upper())


def _register_with_geodatabase(
    info: dict,
    schema_name: str,
    dataset_name: str,
    geometry_column: str | None,
    geom_type: str | None,
    srid: int | None,
    objectid_field: str | None = None,
    dataset_alias: str = "",
    fields: list[dict] | None = None,
    field_aliases: dict | None = None,
    skip_register: bool = False,
) -> tuple[bool, str, dict]:
    arcgis_python = _find_arcgis_python()
    if not arcgis_python:
        return (
            False,
            "ArcGIS Pro/ArcMap Python bulunamadi veya bulunan yorumlayicilarda arcpy import edilemedi. "
            "ARCGIS_PRO_PYTHON_EXE ya da ARCMAP_PYTHON_EXE degiskeni ile dogru python yolunu tanimlayin.",
            {},
        )

    script_path = Path(__file__).resolve().parent.parent / "scripts" / "register_with_geodatabase.py"
    if not script_path.exists():
        return False, f"Register helper bulunamadi: {script_path}", {}

    cmd = [
        arcgis_python,
        str(script_path),
        "--host",
        str(info.get("Host") or ""),
        "--port",
        str(info.get("Port") or ""),
        "--database",
        str(info.get("Database") or ""),
        "--user",
        str(info.get("UserName") or ""),
        "--password",
        str(info.get("Password") or ""),
        "--schema",
        schema_name,
        "--dataset",
        dataset_name,
    ]
    if (objectid_field or "").strip():
        cmd.extend(["--objectid", (objectid_field or "").strip()])
    if skip_register:
        cmd.append("--skip-register")
    if geom_type and geometry_column:
        cmd.extend(
            [
                "--shape-field",
                geometry_column,
                "--geometry-type",
                _arcgis_register_geometry_type(geom_type),
                "--srid",
                str(srid or 4326),
            ]
        )
    if (dataset_alias or "").strip():
        cmd.extend(["--dataset-alias", dataset_alias.strip()])
    if fields:
        try:
            raw = json.dumps(fields, ensure_ascii=False).encode("utf-8")
            cmd.extend(["--fields-json-b64", base64.b64encode(raw).decode("ascii")])
        except Exception:
            pass
    if field_aliases:
        try:
            raw = json.dumps(field_aliases, ensure_ascii=False).encode("utf-8")
            cmd.extend(
                [
                    "--field-aliases-json-b64",
                    base64.b64encode(raw).decode("ascii"),
                ]
            )
        except Exception:
            pass

    run_cmd = cmd
    lower_exec = arcgis_python.lower()
    if lower_exec.endswith(".bat") or lower_exec.endswith(".cmd"):
        run_cmd = ["cmd", "/c", *cmd]

    try:
        proc = subprocess.run(
            run_cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Register With Geodatabase zaman asimina ugradi.", {}
    except Exception as e:
        return False, str(e), {}

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    payload = None
    if stdout:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                break
            except Exception:
                continue

    if proc.returncode == 0 and isinstance(payload, dict) and payload.get("ok"):
        return True, "", payload

    debug = ""
    if isinstance(payload, dict):
        debug = payload.get("debug") or payload.get("message") or ""
    if not debug:
        debug = (stderr or stdout or "").strip()
    return False, debug[:4000], payload if isinstance(payload, dict) else {}


@router.post("/createesrifeature-dataset")
def createesrifeature_dataset(req: CreateEsriFeatureDatasetReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_name = (req.dataset_name or "").strip()
    dataset_alias = (req.dataset_alias or "").strip()
    geometry_column = (req.geometry_column or "shape").strip() or "shape"

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name boş olamaz")
    if not _is_valid_ident(dataset_name):
        return {
            "ok": False,
            "message": "Veri seti adı geçersiz. Sadece harf, rakam ve '_' kullanılmalı.",
            "debug": dataset_name,
        }

    geom_type, geom_err = _normalize_geometry_type(req.geometry_type)
    if geom_err:
        return {"ok": False, "message": geom_err, "debug": req.geometry_type}

    if geom_type:
        if not _is_valid_ident(geometry_column):
            return {
                "ok": False,
                "message": "Geometri kolonu adı geçersiz.",
                "debug": geometry_column,
            }

    srid = None
    if geom_type:
        if req.srid is None:
            srid = 4326
        else:
            srid = int(req.srid)
            if srid <= 0:
                return {
                    "ok": False,
                    "message": "SRID pozitif bir sayı olmalı.",
                    "debug": str(req.srid),
                }

    prepared_fields = []
    seen_fields = set()
    reserved = {"objectid"}
    if geom_type:
        reserved.add(geometry_column.lower())

    for raw in (req.fields or []):
        col_name = (raw.name or "").strip()
        alias = (raw.alias or "").strip()
        if not col_name:
            return {"ok": False, "message": "Alan adı boş olamaz.", "debug": ""}
        if not _is_valid_ident(col_name):
            return {"ok": False, "message": f"Geçersiz alan adı: {col_name}", "debug": col_name}

        col_key = col_name.lower()
        if col_key in seen_fields:
            return {
                "ok": False,
                "message": f"Aynı alan adı tekrarlandı: {col_name}",
                "debug": col_name,
            }
        if col_key in reserved:
            return {
                "ok": False,
                "message": f"'{col_name}' alan adı sistemde ayrılmıştır.",
                "debug": col_name,
            }

        sql_type, type_err = _resolve_field_sql_type(
            raw.data_type, raw.length, raw.precision, raw.scale
        )
        if type_err:
            return {"ok": False, "message": type_err, "debug": f"{col_name}: {raw.data_type}"}
        if not _is_esri_addfield_supported_type(raw.data_type):
            return {
                "ok": False,
                "message": (
                    "Esri DB veri seti olusturma akisinda bu alan tipi desteklenmiyor. "
                    "Desteklenen tipler: text, varchar, char, integer, numeric, "
                    "double precision, date, timestamp"
                ),
                "debug": f"{col_name}: {raw.data_type}",
            }

        prepared_fields.append(
            {
                "name": col_name,
                "alias": alias,
                "data_type": raw.data_type,
                "length": raw.length,
                "precision": raw.precision,
                "scale": raw.scale,
                "sql_type": sql_type,
                "nullable": bool(raw.nullable),
            }
        )
        seen_fields.add(col_key)

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    conn = None
    cur = None
    try:
        conn = _connect_db(info)
        cur = conn.cursor()

        cur.execute(
            """
            SELECT 1
            FROM information_schema.schemata
            WHERE schema_name = %s
            LIMIT 1
            """,
            (schema_name,),
        )
        if not cur.fetchone():
            return {"ok": False, "message": "Seçilen şema bulunamadı.", "debug": schema_name}

        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
            LIMIT 1
            """,
            (schema_name, dataset_name),
        )
        if cur.fetchone():
            return {
                "ok": False,
                "message": "Aynı isimde veri seti zaten mevcut.",
                "debug": f"{schema_name}.{dataset_name}",
            }

        st_schema = None
        if geom_type:
            st_schema = _find_st_geometry_schema(cur)
            if not st_schema:
                return {
                    "ok": False,
                    "message": "Seçilen veritabanında ST_Geometry tipi bulunamadı.",
                    "debug": "Esri ST_Geometry kurulumunu kontrol edin.",
                }

        column_defs = []

        if geom_type:
            column_defs.append(
                sql.SQL("{} {}.st_geometry").format(
                    sql.Identifier(geometry_column),
                    sql.Identifier(st_schema),
                )
            )

        used_placeholder = False
        if column_defs:
            create_cols_sql = sql.SQL(", ").join(column_defs)
        else:
            used_placeholder = True
            create_cols_sql = sql.SQL("{} smallint").format(
                sql.Identifier("__tmp_dbm_placeholder")
            )

        cur.execute(
            sql.SQL("CREATE TABLE {}.{} ({})").format(
                sql.Identifier(schema_name),
                sql.Identifier(dataset_name),
                create_cols_sql,
            )
        )
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        msg = "Esri DB veri seti oluşturulamadı."
        err_text = str(e).lower()
        if "permission denied for schema" in err_text:
            msg = "Secilen semada veri seti olusturma yetkiniz yok."
        return {
            "ok": False,
            "message": msg,
            "debug": str(e),
        }
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

    conn = None
    cur = None
    try:
        conn = _connect_db(info)
        cur = conn.cursor()
        requested_field_aliases = {
            f["name"]: f["alias"]
            for f in prepared_fields
            if (f.get("alias") or "").strip()
        }

        ok, reg_debug, reg_payload = _register_with_geodatabase(
            info,
            schema_name,
            dataset_name,
            geometry_column if geom_type else None,
            geom_type,
            srid,
            dataset_alias=dataset_alias,
            fields=prepared_fields,
            field_aliases=requested_field_aliases,
        )
        if not ok:
            try:
                cleanup_conn = _connect_db(info)
                try:
                    cleanup_cur = cleanup_conn.cursor()
                    cleanup_cur.execute(
                        sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(
                            sql.Identifier(schema_name),
                            sql.Identifier(dataset_name),
                        )
                    )
                    cleanup_conn.commit()
                    cleanup_cur.close()
                finally:
                    cleanup_conn.close()
            except Exception:
                pass
            return {
                "ok": False,
                "message": "Veri seti olusturuldu ancak geodatabase kaydi tamamlanamadi.",
                "debug": reg_debug,
            }

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
        conn = _connect_db(info)
        cur = conn.cursor()

        if not geom_type and used_placeholder:
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} DROP COLUMN {}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier("__tmp_dbm_placeholder"),
                )
            )

        if dataset_alias:
            cur.execute(
                sql.SQL("COMMENT ON TABLE {}.{} IS %s").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                ),
                (f"alias={dataset_alias}",),
            )

        for f in prepared_fields:
            if f["alias"]:
                cur.execute(
                    sql.SQL("COMMENT ON COLUMN {}.{}.{} IS %s").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(dataset_name),
                        sql.Identifier(f["name"]),
                    ),
                    (f"alias={f['alias']}",),
                )
            if not f["nullable"]:
                cur.execute(
                    sql.SQL("ALTER TABLE {}.{} ALTER COLUMN {} SET NOT NULL").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(dataset_name),
                        sql.Identifier(f["name"]),
                    )
                )

        conn.commit()

        return {
            "ok": True,
            "message": "Esri DB feature class olusturuldu ve geodatabase kaydi tamamlandi.",
            "data": {
                "schema": schema_name,
                "dataset": dataset_name,
                "dataset_alias": dataset_alias or None,
                "geometry_type": geom_type,
                "geometry_column": geometry_column if geom_type else None,
                "srid": srid if geom_type else None,
                "field_count": len(prepared_fields),
                "storage": "st_geometry" if geom_type else "table",
                "registered": True,
                "requested_field_aliases": requested_field_aliases,
                "verified_field_aliases": {
                    name: ((reg_payload or {}).get("persisted_field_aliases") or {}).get(name, "")
                    for name in requested_field_aliases.keys()
                },
            },
        }
    except Exception as e:
        if conn:
            conn.rollback()
        msg = "Esri DB veri seti oluşturulamadı."
        err_text = str(e).lower()
        if "permission denied for schema" in err_text:
            msg = "Secilen semada veri seti olusturma yetkiniz yok."
        return {
            "ok": False,
            "message": msg,
            "debug": str(e),
        }
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

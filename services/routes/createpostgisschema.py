# services/routes/createpostgisschema.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
import psycopg2
from psycopg2 import sql

from core.storage import open_db


router = APIRouter(tags=["db-schema"])


class CreatePostgisSchemaReq(BaseModel):
    conn_name: str
    schema_name: str


class ImportVectorToPostgisReq(BaseModel):
    conn_name: str
    schema_name: str
    file_path: str
    manual_epsg: int | None = None


class ImportVectorToEsriDbReq(BaseModel):
    conn_name: str
    schema_name: str
    file_path: str


class CreateFeatureFromXsdReq(BaseModel):
    conn_name: str
    schema_name: str
    xsd_path: str


class DbMatchLayerMapReq(BaseModel):
    source_layer: str
    target_table: str
    field_mapping: dict[str, str] = Field(default_factory=dict)


class DbMatchLoadReq(BaseModel):
    conn_name: str
    schema_name: str
    file_path: str
    layer_mappings: list[DbMatchLayerMapReq] = Field(default_factory=list)


def _get_db_connection_by_name(conn_name: str):
    """
    db_connections tablosundan Conn_Name ile en güncel bağlantıyı döndürür.
    Dönüş: dict veya None
    """
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


def _sanitize_table_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "vector_data"
    if s[0].isdigit():
        s = f"t_{s}"
    return s[:55]


def _connect_postgis(info: dict):
    return psycopg2.connect(
        host=info.get("Host"),
        port=str(info.get("Port")),
        user=info.get("UserName"),
        password=info.get("Password") or "",
        database=info.get("Database"),
    )


def _normalize_db_type(v: str) -> str:
    s = (v or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_esri_dbtype(v: str) -> bool:
    s = _normalize_db_type(v)
    return s in (
        "esri geodatabase",
        "enterprise geodatabase",
        "esri enterprise geodatabase",
        "esri",
    )


def _validate_postgis_conn(conn_name: str):
    info = _get_db_connection_by_name(conn_name)
    if not info:
        return None, {
            "ok": False,
            "message": "Bağlantı bulunamadı.",
            "debug": conn_name,
        }

    db_type = (info.get("DbType") or "").strip().lower()
    if db_type != "postgis":
        return None, {
            "ok": False,
            "message": "Seçilen bağlantı PostGIS değil (DbType=PostGIS olmalı).",
            "debug": f"DbType={info.get('DbType')}",
        }
    return info, None


def _validate_esri_conn(conn_name: str):
    info = _get_db_connection_by_name(conn_name)
    if not info:
        return None, {
            "ok": False,
            "message": "Bağlantı bulunamadı.",
            "debug": conn_name,
        }

    db_type = info.get("DbType")
    if not _is_esri_dbtype(db_type):
        return None, {
            "ok": False,
            "message": "Seçilen bağlantı Esri Geodatabase değil (DbType=Esri Geodatabase olmalı).",
            "debug": f"DbType={db_type}",
        }
    return info, None


def _ensure_ogr2ogr():
    exe = shutil.which("ogr2ogr")
    if exe:
        return exe
    return None


def _build_gdal_env(ogr2ogr_exe: str):
    env = os.environ.copy()
    exe_dir = Path(ogr2ogr_exe).resolve().parent

    # Aynı makinada birden fazla PROJ/GDAL kurulu olabildiği için
    # ogr2ogr ile uyumlu veri dizinlerini zorunlu olarak bu kurulumdan seç.
    proj_candidates = [
        exe_dir / "projlib",
        exe_dir / "proj",
        exe_dir / "share" / "proj",
        exe_dir.parent / "share" / "proj",
    ]
    selected_proj = None
    for c in proj_candidates:
        if (c / "proj.db").exists():
            selected_proj = c
            break
    if selected_proj:
        env["PROJ_LIB"] = str(selected_proj)
        env["PROJ_DATA"] = str(selected_proj)

    gdal_candidates = [
        exe_dir / "gdal-data",
        exe_dir / "share" / "gdal",
        exe_dir.parent / "share" / "gdal",
    ]
    selected_gdal = None
    for c in gdal_candidates:
        if c.exists():
            selected_gdal = c
            break
    if selected_gdal:
        env["GDAL_DATA"] = str(selected_gdal)

    current_path = env.get("PATH") or ""
    exe_dir_s = str(exe_dir)
    if exe_dir_s and exe_dir_s not in current_path.split(os.pathsep):
        env["PATH"] = exe_dir_s + (os.pathsep + current_path if current_path else "")

    return env


def _ensure_ogrinfo(ogr2ogr_exe: str):
    exe_path = Path(ogr2ogr_exe).resolve()
    suffix = exe_path.suffix
    candidates = []
    if suffix:
        candidates.append(exe_path.with_name(f"ogrinfo{suffix}"))
    candidates.append(exe_path.with_name("ogrinfo"))
    candidates.append(exe_path.with_name("ogrinfo.exe"))

    for c in candidates:
        if c.exists():
            return str(c)

    return shutil.which("ogrinfo")


def _list_layers_with_ogrinfo(ogrinfo_exe: str, src: Path, gdal_env: dict):
    cmd = [ogrinfo_exe, "-ro", "-so", str(src)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=gdal_env,
        )
    except Exception as e:
        return [], f"ogrinfo çalıştırılamadı: {e}"

    output = "\n".join(
        [(proc.stdout or "").strip(), (proc.stderr or "").strip()]
    ).strip()
    if proc.returncode != 0:
        return [], f"ogrinfo hata kodu={proc.returncode}: {output[:800]}"

    layers = []
    seen = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        m = re.match(r"^\d+\s*:\s*(.+?)\s*(?:\(|$)", line)
        if not m:
            continue
        layer_name = (m.group(1) or "").strip()
        if not layer_name or layer_name in seen:
            continue
        seen.add(layer_name)
        layers.append(layer_name)

    return layers, ""


def _list_layers_from_gfs(src: Path):
    gfs_path = src.with_suffix(".gfs")
    if not gfs_path.exists() or not gfs_path.is_file():
        return []

    try:
        tree = ET.parse(gfs_path)
        root = tree.getroot()
    except Exception:
        return []

    layers = []
    seen = set()
    for el in root.findall("./GMLFeatureClass/Name"):
        nm = (el.text or "").strip()
        if not nm or nm in seen:
            continue
        seen.add(nm)
        layers.append(nm)
    return layers


def _resolve_vector_layers(ogr2ogr_exe: str, src: Path, gdal_env: dict):
    notes = []
    layers = []

    ogrinfo_exe = _ensure_ogrinfo(ogr2ogr_exe)
    if ogrinfo_exe:
        layers, err = _list_layers_with_ogrinfo(ogrinfo_exe, src, gdal_env)
        if err:
            notes.append(err)
    else:
        notes.append("ogrinfo bulunamadı")

    if not layers:
        gfs_layers = _list_layers_from_gfs(src)
        if gfs_layers:
            layers = gfs_layers
            notes.append("katmanlar .gfs dosyasından alındı")

    if not layers:
        layers = [src.stem]
        notes.append("katman listesi bulunamadı, tek katman varsayıldı")

    return layers, notes


def _dbmatch_normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())


def _dbmatch_parse_fields_from_ogrinfo_output(output: str):
    fields = []
    seen = set()
    geom_column = None

    skip_prefixes = {
        "layer name",
        "geometry",
        "feature count",
        "extent",
        "layer srs wkt",
        "fid column",
        "geometry column",
        "metadata",
    }

    for raw_line in (output or "").splitlines():
        line = (raw_line or "").strip()
        if not line:
            continue

        m_geom = re.match(r"^Geometry\s+Column\s*=\s*(.+)$", line, flags=re.IGNORECASE)
        if m_geom:
            geom_column = (m_geom.group(1) or "").strip().strip('"')
            continue

        lowered = line.lower()
        if any(lowered.startswith(p) for p in skip_prefixes):
            continue

        m_field = re.match(
            r"^([^:]+?)\s*:\s*([A-Za-z0-9_ ]+)(?:\s*\([^)]*\))?\s*$", line
        )
        if not m_field:
            continue

        field_name = (m_field.group(1) or "").strip().strip('"')
        if not field_name:
            continue

        key = field_name.lower()
        if key in seen:
            continue
        seen.add(key)
        fields.append(field_name)

    return fields, geom_column


def _dbmatch_list_layer_fields(ogr2ogr_exe: str, src: Path, layer_name: str | None, gdal_env: dict):
    notes = []
    ogrinfo_exe = _ensure_ogrinfo(ogr2ogr_exe)
    if not ogrinfo_exe:
        return [], None, ["ogrinfo bulunamadı"]

    # Önce JSON modunu deneriz (alan tipleri için daha güvenilir).
    cmd_json = [ogrinfo_exe, "-ro", "-json", "-so", str(src)]
    if layer_name:
        cmd_json.append(layer_name)

    try:
        proc_json = subprocess.run(
            cmd_json,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=gdal_env,
        )
        output_json = "\n".join(
            [(proc_json.stdout or "").strip(), (proc_json.stderr or "").strip()]
        ).strip()

        if proc_json.returncode == 0 and output_json:
            payload = json.loads(output_json)
            layers = payload.get("layers") if isinstance(payload, dict) else None
            layer_obj = layers[0] if isinstance(layers, list) and layers else {}
            fields = []
            seen = set()
            for fld in (layer_obj.get("fields") or []):
                name = (fld or {}).get("name") if isinstance(fld, dict) else None
                if not name:
                    continue
                k = str(name).lower()
                if k in seen:
                    continue
                seen.add(k)
                fields.append(str(name))

            geom_column = None
            geom_fields = layer_obj.get("geometryFields") if isinstance(layer_obj, dict) else []
            if isinstance(geom_fields, list) and geom_fields:
                first_geom = geom_fields[0]
                if isinstance(first_geom, dict):
                    geom_column = (first_geom.get("name") or "").strip() or None

            if fields:
                return fields, geom_column, notes
    except Exception as e:
        notes.append(f"ogrinfo json parse başarısız: {e}")

    # Fallback: düz metin parse.
    cmd_text = [ogrinfo_exe, "-ro", "-so", str(src)]
    if layer_name:
        cmd_text.append(layer_name)

    try:
        proc_text = subprocess.run(
            cmd_text,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=gdal_env,
        )
    except Exception as e:
        return [], None, notes + [f"ogrinfo çalıştırılamadı: {e}"]

    output = "\n".join(
        [(proc_text.stdout or "").strip(), (proc_text.stderr or "").strip()]
    ).strip()
    if proc_text.returncode != 0:
        return [], None, notes + [f"ogrinfo hata kodu={proc_text.returncode}: {output[:800]}"]

    fields, geom_column = _dbmatch_parse_fields_from_ogrinfo_output(output)
    return fields, geom_column, notes


def _dbmatch_collect_vector_structure(ogr2ogr_exe: str, src: Path, gdal_env: dict):
    ext = src.suffix.lower()
    notes = []

    if ext in (".gml", ".xml"):
        layer_names, resolve_notes = _resolve_vector_layers(ogr2ogr_exe, src, gdal_env)
        notes.extend(resolve_notes)
    elif ext == ".shp":
        layer_names = [src.stem]
    else:
        layer_names = []
        ogrinfo_exe = _ensure_ogrinfo(ogr2ogr_exe)
        if ogrinfo_exe:
            layers, err = _list_layers_with_ogrinfo(ogrinfo_exe, src, gdal_env)
            if err:
                notes.append(err)
            layer_names = layers
        if not layer_names:
            layer_names = [src.stem]
            notes.append("katman listesi bulunamadı, dosya adı tek katman olarak kullanıldı")

    # Tekilleştir (sıra korunsun)
    uniq_layers = []
    seen = set()
    for name in layer_names:
        nm = (name or "").strip()
        if not nm:
            continue
        key = nm.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_layers.append(nm)

    structures = []
    for layer_name in uniq_layers:
        fields, geom_col, field_notes = _dbmatch_list_layer_fields(
            ogr2ogr_exe, src, layer_name, gdal_env
        )
        for n in field_notes:
            notes.append(f"{layer_name}: {n}")
        structures.append(
            {
                "name": layer_name,
                "fields": fields,
                "geometry_column": geom_col,
            }
        )

    return structures, notes


def _dbmatch_list_schema_tables(info: dict, schema_name: str):
    conn = None
    cur = None
    try:
        conn = _connect_postgis(info)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type IN ('BASE TABLE', 'FOREIGN TABLE')
            ORDER BY table_name
            """,
            (schema_name,),
        )
        return [r[0] for r in cur.fetchall() if r and r[0]]
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _dbmatch_list_table_columns(info: dict, schema_name: str, table_name: str):
    conn = None
    cur = None
    out = []
    try:
        conn = _connect_postgis(info)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table_name),
        )
        rows = cur.fetchall()
        for row in rows:
            col_name = row[0]
            data_type = row[1]
            udt_name = row[2]
            is_nullable = row[3]
            is_geometry = (
                (udt_name or "").strip().lower() in ("geometry", "st_geometry")
                or (data_type or "").strip().upper() == "USER-DEFINED"
                and (udt_name or "").strip().lower() in ("geometry", "st_geometry")
            )
            out.append(
                {
                    "name": col_name,
                    "data_type": data_type,
                    "udt_name": udt_name,
                    "is_nullable": is_nullable,
                    "is_geometry": bool(is_geometry),
                }
            )
        return out
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _dbmatch_get_target_srid(cur, schema_name: str, table_name: str, geom_column: str | None):
    if not geom_column:
        return None

    try:
        cur.execute(
            """
            SELECT srid
            FROM geometry_columns
            WHERE f_table_schema = %s
              AND f_table_name = %s
              AND f_geometry_column = %s
            LIMIT 1
            """,
            (schema_name, table_name, geom_column),
        )
        row = cur.fetchone()
        if row and row[0] is not None and int(row[0]) > 0:
            return int(row[0])
    except Exception:
        pass

    try:
        cur.execute(
            "SELECT Find_SRID(%s, %s, %s)",
            (schema_name, table_name, geom_column),
        )
        row = cur.fetchone()
        if row and row[0] is not None and int(row[0]) > 0:
            return int(row[0])
    except Exception:
        pass

    return None


def _dbmatch_drop_table_if_exists(cur, schema_name: str, table_name: str):
    cur.execute(
        sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
        )
    )


def _extract_epsg_from_text(text: str):
    content = (text or "").strip()
    if not content:
        return None

    def _is_datum_like(code: int) -> bool:
        # EPSG geodetic datum kodları çoğunlukla bu aralıkta.
        return 6000 <= code <= 6999

    def _pick_valid(codes: list[str]):
        vals = []
        for c in codes:
            try:
                vals.append(int(c))
            except Exception:
                continue
        if not vals:
            return None
        non_datum = [v for v in vals if not _is_datum_like(v)]
        if non_datum:
            return f"EPSG:{non_datum[-1]}"
        return None

    # 1) srsName/URN/URL gibi güçlü göstergeler
    strong_codes = []
    strong_patterns = [
        r"urn:ogc:def:crs:epsg(?::[^:]+)*::(\d{3,7})",
        r"/EPSG/\d+/(\d{3,7})\b",
        r"\bEPSG\s*::\s*(\d{3,7})\b",
        r"\bEPSG\s*[:/]\s*(\d{3,7})\b",
    ]
    for p in strong_patterns:
        for m in re.finditer(p, content, flags=re.IGNORECASE):
            strong_codes.append(m.group(1))
    picked = _pick_valid(strong_codes)
    if picked:
        return picked

    # 2) WKT AUTHORITY/ID eşleşmelerinde DATUM/ELLIPSOID bağlamını ele.
    auth_codes = []
    for m in re.finditer(
        r'AUTHORITY\["EPSG","(\d{3,7})"\]', content, flags=re.IGNORECASE
    ):
        code = m.group(1)
        ctx = content[max(0, m.start() - 120) : m.start()].upper()
        if any(k in ctx for k in ("DATUM[", "SPHEROID[", "ELLIPSOID[", "PRIMEM[")):
            continue
        auth_codes.append(code)
    for m in re.finditer(r'ID\["EPSG",\s*(\d{3,7})\]', content, flags=re.IGNORECASE):
        code = m.group(1)
        ctx = content[max(0, m.start() - 120) : m.start()].upper()
        if any(k in ctx for k in ("DATUM[", "SPHEROID[", "ELLIPSOID[", "PRIMEM[")):
            continue
        auth_codes.append(code)
    picked = _pick_valid(auth_codes)
    if picked:
        return picked

    u = content.upper()
    if "CRS84" in u:
        return "EPSG:4326"

    # ESRI .prj içinde authority yoksa yaygın WGS84 isimleri için fallback.
    if "PROJCS[" in u:
        m = re.search(r"WGS[_\s]*1984[_\s]*UTM[_\s]*ZONE[_\s]*(\d{1,2})([NS])", u)
        if m:
            zone = int(m.group(1))
            hemi = m.group(2)
            if 1 <= zone <= 60:
                return f"EPSG:{32600 + zone if hemi == 'N' else 32700 + zone}"
    else:
        if "GCS_WGS_1984" in u or "WGS 84" in u or "WGS_1984" in u:
            return "EPSG:4326"

    return None


def _extract_epsg_code(srs_text: str | None):
    s = (srs_text or "").strip()
    m = re.search(r"EPSG\s*:\s*(\d{3,7})$", s, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _load_srs_defs_from_db(info: dict, epsg_codes: list[int]):
    out = {}
    if not epsg_codes:
        return out
    uniq_codes = sorted({c for c in epsg_codes if isinstance(c, int)})
    if not uniq_codes:
        return out

    conn = _connect_postgis(info)
    try:
        cur = conn.cursor()
        for code in uniq_codes:
            cur.execute(
                """
                SELECT srtext, proj4text
                FROM spatial_ref_sys
                WHERE srid = %s OR (auth_name = 'EPSG' AND auth_srid = %s)
                ORDER BY CASE WHEN srid = %s THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (code, code, code),
            )
            row = cur.fetchone()
            if not row:
                continue
            srtext = (row[0] or "").strip()
            proj4 = (row[1] or "").strip()
            if srtext:
                out[code] = srtext
            elif proj4:
                out[code] = proj4
        cur.close()
    finally:
        conn.close()
    return out


def _is_srs_processing_error(text: str):
    t = (text or "").lower()
    return (
        "failed to process srs definition" in t
        or "crs not found" in t
        or "proj_create_from_database" in t
    )


def _remove_a_srs_from_cmd(cmd: list[str]):
    out = []
    i = 0
    n = len(cmd)
    while i < n:
        if cmd[i] == "-a_srs":
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out


def _is_geometry_type_mismatch_error(text: str):
    t = (text or "").lower()
    return (
        ("geometry type (" in t and "does not match column type" in t)
        or (
            "geometry to be inserted is of type" in t
            and "layer geometry type is" in t
        )
    )


def _add_promote_to_multi_to_cmd(cmd: list[str]):
    out = list(cmd)
    if "-nlt" in out:
        idx = out.index("-nlt")
        if idx + 1 < len(out):
            out[idx + 1] = "PROMOTE_TO_MULTI"
        else:
            out.extend(["-nlt", "PROMOTE_TO_MULTI"])
    else:
        out.extend(["-nlt", "PROMOTE_TO_MULTI"])

    if "-overwrite" not in out:
        out.append("-overwrite")
    return out


def _drop_table_if_exists(info: dict, schema_name: str, table_name: str):
    conn = _connect_postgis(info)
    try:
        cur = conn.cursor()
        cur.execute(
            sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
            )
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _extract_epsg_from_xml_or_prj(src: Path):
    ext = src.suffix.lower()
    if ext in (".gml", ".xml"):
        try:
            root = ET.parse(src).getroot()
            for el in root.iter():
                for attr_name, attr_val in (el.attrib or {}).items():
                    an = (attr_name or "").lower()
                    if "srs" not in an:
                        continue
                    epsg = _extract_epsg_from_text(attr_val or "")
                    if epsg:
                        return epsg
        except Exception:
            return None
        return None

    if ext == ".shp":
        prj = src.with_suffix(".prj")
        if prj.exists() and prj.is_file():
            try:
                txt = prj.read_text(encoding="utf-8", errors="ignore")
                return _extract_epsg_from_text(txt)
            except Exception:
                return None
    return None


def _detect_source_srs(
    ogr2ogr_exe: str, src: Path, source_layer: str | None, gdal_env: dict
):
    notes = []
    srs = None

    ogrinfo_exe = _ensure_ogrinfo(ogr2ogr_exe)
    if ogrinfo_exe:
        cmd = [ogrinfo_exe, "-ro", "-so", str(src)]
        if source_layer:
            cmd.append(source_layer)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                env=gdal_env,
            )
            out = "\n".join(
                [(proc.stdout or "").strip(), (proc.stderr or "").strip()]
            ).strip()
            if proc.returncode == 0:
                srs = _extract_epsg_from_text(out)
            else:
                notes.append(f"ogrinfo SRS sorgusu başarısız (code={proc.returncode})")
        except Exception as e:
            notes.append(f"ogrinfo SRS sorgusu çalıştırılamadı: {e}")
    else:
        notes.append("ogrinfo bulunamadı")

    # Layer belirtilmeden EPSG bulunamadıysa tek katman varsayımıyla dosya adı denenir.
    if not srs and not source_layer and ogrinfo_exe:
        guessed_layer = src.stem
        cmd = [ogrinfo_exe, "-ro", "-so", str(src), guessed_layer]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                env=gdal_env,
            )
            out = "\n".join(
                [(proc.stdout or "").strip(), (proc.stderr or "").strip()]
            ).strip()
            if proc.returncode == 0:
                srs = _extract_epsg_from_text(out)
                if srs:
                    notes.append(
                        f"SRS layer adı varsayımıyla tespit edildi ({guessed_layer})"
                    )
        except Exception:
            pass

    if not srs:
        srs = _extract_epsg_from_xml_or_prj(src)
        if srs:
            notes.append("SRS dosya içeriğinden tespit edildi")

    return srs, notes


def _build_import_jobs(src: Path, ext: str, layer_names: list[str]):
    file_base = _sanitize_table_name(src.stem)
    is_multi_gml = ext in (".gml", ".xml") and len(layer_names) > 1

    jobs = []
    used = set()
    if is_multi_gml:
        for i, layer in enumerate(layer_names, start=1):
            layer_base = _sanitize_table_name(layer) or f"layer_{i}"
            # Çok katmanlı GML/XML'de hedef tablo adı doğrudan katman adından üretilir.
            base = layer_base
            candidate = base
            k = 2
            while candidate in used:
                suffix = f"_{k}"
                candidate = f"{base[: max(1, 55 - len(suffix))]}{suffix}"
                k += 1
            used.add(candidate)
            jobs.append({"source_layer": layer, "table_name": candidate})
        return jobs, True

    if ext in (".gml", ".xml") and layer_names:
        single_base = _sanitize_table_name(layer_names[0]) or file_base
        jobs.append({"source_layer": layer_names[0], "table_name": single_base})
        return jobs, False

    source_layer = src.stem if ext == ".shp" else None
    jobs.append({"source_layer": source_layer, "table_name": file_base})
    return jobs, False


def _xsd_tag_local(tag: str) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def _xsd_parse_occurs(raw: str | None, default: int = 1):
    v = (raw or "").strip()
    if not v:
        return default
    if v.lower() == "unbounded":
        return None
    try:
        iv = int(v)
        if iv < 0:
            return default
        return iv
    except Exception:
        return default


def _xsd_to_bool(raw: str | None, default: bool = False) -> bool:
    v = (raw or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes")


def _xsd_local_type_name(type_name: str | None) -> str:
    t = (type_name or "").strip()
    if not t:
        return ""
    if ":" in t:
        return t.split(":", 1)[1]
    return t


def _xsd_geom_pg_type(xsd_type: str) -> str:
    t = (xsd_type or "").lower()
    if "multipolygon" in t or "multisurface" in t:
        return "geometry(MultiPolygon)"
    if "polygon" in t:
        return "geometry(Polygon)"
    if "multilinestring" in t or "multicurve" in t:
        return "geometry(MultiLineString)"
    if "linestring" in t or "curve" in t:
        return "geometry(LineString)"
    if "multipoint" in t:
        return "geometry(MultiPoint)"
    if "point" in t:
        return "geometry(Point)"
    return "geometry(Geometry)"


def _xsd_primitive_pg_type(xsd_type: str) -> str:
    t = (xsd_type or "").lower()
    if ":" in t:
        t = t.split(":", 1)[1]
    t = t.strip()

    if "string" in t:
        return "text"
    if t in ("nonnegativeinteger", "unsignedint", "unsignedshort", "positiveinteger"):
        return "bigint"
    if t in ("unsignedlong",):
        return "numeric"
    if "long" in t:
        return "bigint"
    if "int" in t or "integer" in t or "short" in t:
        return "integer"
    if "double" in t or "decimal" in t or "float" in t:
        return "double precision"
    if "boolean" in t:
        return "boolean"
    if "datetime" in t:
        return "timestamp without time zone"
    if t.endswith(":date") or " date" in t or "date" in t:
        return "date"
    if "time" in t:
        return "time without time zone"
    return "text"


def _xsd_parse_simple_type_defs_from_root(root: ET.Element) -> tuple[dict, list[str]]:
    notes = []
    raw_defs = {}
    for ch in list(root):
        if _xsd_tag_local(ch.tag) != "simpleType":
            continue
        nm = (ch.get("name") or "").strip()
        if not nm:
            continue

        restriction = None
        union_el = None
        list_el = None
        for sub in list(ch):
            loc = _xsd_tag_local(sub.tag)
            if loc == "restriction":
                restriction = sub
            elif loc == "union":
                union_el = sub
            elif loc == "list":
                list_el = sub

        if union_el is not None:
            notes.append(
                f"simpleType '{nm}': union desteği yok, text olarak ele alınacak."
            )
            raw_defs[nm] = {
                "name": nm,
                "base_local": "string",
                "enumerations": [],
                "facets": {},
                "unsupported_union": True,
            }
            continue
        if list_el is not None:
            notes.append(
                f"simpleType '{nm}': list desteği yok, text olarak ele alınacak."
            )
            raw_defs[nm] = {
                "name": nm,
                "base_local": "string",
                "enumerations": [],
                "facets": {},
                "unsupported_list": True,
            }
            continue

        if restriction is None:
            raw_defs[nm] = {
                "name": nm,
                "base_local": "string",
                "enumerations": [],
                "facets": {},
            }
            continue

        base_local = _xsd_local_type_name(restriction.get("base")) or "string"
        enums = []
        facets = {}
        for rc in list(restriction):
            tag = _xsd_tag_local(rc.tag)
            val = (rc.get("value") or "").strip()
            if not val:
                continue
            if tag == "enumeration":
                enums.append(val)
                continue
            if tag in (
                "length",
                "minLength",
                "maxLength",
                "minInclusive",
                "maxInclusive",
                "minExclusive",
                "maxExclusive",
                "pattern",
                "fractionDigits",
                "totalDigits",
            ):
                facets[tag] = val

        raw_defs[nm] = {
            "name": nm,
            "base_local": base_local,
            "enumerations": enums,
            "facets": facets,
        }

    resolved = {}
    resolving = set()

    def _resolve(st_name: str):
        if st_name in resolved:
            return resolved[st_name]
        if st_name in resolving:
            return {
                "name": st_name,
                "base_local": "string",
                "pg_base_type": "text",
                "enumerations": [],
                "facets": {},
                "is_domain_candidate": False,
                "domain_name": None,
            }
        resolving.add(st_name)
        cur = raw_defs.get(st_name) or {}
        base_local = (cur.get("base_local") or "string").strip()

        parent = None
        if base_local in raw_defs:
            parent = _resolve(base_local)

        if parent:
            merged_enums = list(parent.get("enumerations") or [])
            if cur.get("enumerations"):
                merged_enums = list(cur.get("enumerations") or [])

            merged_facets = dict(parent.get("facets") or {})
            merged_facets.update(cur.get("facets") or {})
            resolved_base = parent.get("base_local") or "string"
        else:
            merged_enums = list(cur.get("enumerations") or [])
            merged_facets = dict(cur.get("facets") or {})
            resolved_base = base_local

        pg_base = _xsd_primitive_pg_type(resolved_base)
        is_domain_candidate = bool(merged_enums) or bool(merged_facets)
        domain_name = None
        if is_domain_candidate:
            domain_name = _sanitize_table_name(f"{st_name}")

        item = {
            "name": st_name,
            "base_local": resolved_base,
            "pg_base_type": pg_base,
            "enumerations": merged_enums,
            "facets": merged_facets,
            "is_domain_candidate": is_domain_candidate,
            "domain_name": domain_name,
        }
        resolved[st_name] = item
        resolving.remove(st_name)
        return item

    for nm in raw_defs.keys():
        _resolve(nm)

    return resolved, notes


def _xsd_field_def_from_element(
    el: ET.Element,
    simple_types: dict | None = None,
    global_elements: dict | None = None,
) -> dict | None:
    name = (el.get("name") or "").strip()
    if not name:
        ref_name = _xsd_local_type_name(el.get("ref"))
        if ref_name:
            name = ref_name

    ref_type = ""
    if not (el.get("type") or "").strip() and name and global_elements:
        ge = global_elements.get(name)
        if ge is not None:
            ref_type = (ge.get("type") or "").strip()

    if not name:
        return None

    xsd_type = (el.get("type") or ref_type or "").strip()
    local_type = _xsd_local_type_name(xsd_type)

    min_occurs = _xsd_parse_occurs(el.get("minOccurs"), default=1)
    max_occurs = _xsd_parse_occurs(el.get("maxOccurs"), default=1)
    nillable = _xsd_to_bool(el.get("nillable"), default=False)
    is_required = (min_occurs or 0) > 0 and not nillable
    is_multi = (max_occurs is None) or ((max_occurs or 1) > 1)

    is_geom = False
    pg_type = "text"
    domain_name = None
    simple_type_name = None

    if xsd_type and ("gml:" in xsd_type.lower() or "gml/" in xsd_type.lower()):
        is_geom = True
        pg_type = _xsd_geom_pg_type(xsd_type)
    elif xsd_type:
        if simple_types and local_type in simple_types:
            st = simple_types.get(local_type) or {}
            simple_type_name = local_type
            domain_name = st.get("domain_name")
            pg_type = (st.get("pg_base_type") or "text").strip()
        else:
            pg_type = _xsd_primitive_pg_type(xsd_type)
    else:
        pg_type = "text"

    if is_multi and not is_geom:
        # maxOccurs>1 alanlarda kolon yapısında veri kaybı olmaması için JSONB tutulur.
        pg_type = "jsonb"
        domain_name = None

    return {
        "name": name,
        "xsd_type": xsd_type or "unknown",
        "local_type": local_type or "",
        "is_geometry": is_geom,
        "pg_type": pg_type,
        "domain_name": domain_name,
        "simple_type_name": simple_type_name,
        "is_required": is_required,
        "is_multi": is_multi,
    }


def _xsd_field_def_from_attribute(
    attr: ET.Element,
    simple_types: dict | None = None,
) -> dict | None:
    name = (attr.get("name") or "").strip()
    if not name:
        ref_name = _xsd_local_type_name(attr.get("ref"))
        if ref_name:
            name = ref_name
    if not name:
        return None

    xsd_type = (attr.get("type") or "").strip()
    local_type = _xsd_local_type_name(xsd_type)
    use_required = (attr.get("use") or "").strip().lower() == "required"

    is_geom = False
    pg_type = "text"
    domain_name = None
    simple_type_name = None

    if xsd_type and ("gml:" in xsd_type.lower() or "gml/" in xsd_type.lower()):
        is_geom = True
        pg_type = _xsd_geom_pg_type(xsd_type)
    elif xsd_type:
        if simple_types and local_type in simple_types:
            st = simple_types.get(local_type) or {}
            simple_type_name = local_type
            domain_name = st.get("domain_name")
            pg_type = (st.get("pg_base_type") or "text").strip()
        else:
            pg_type = _xsd_primitive_pg_type(xsd_type)

    return {
        "name": name,
        "xsd_type": xsd_type or "unknown",
        "local_type": local_type or "",
        "is_geometry": is_geom,
        "pg_type": pg_type,
        "domain_name": domain_name,
        "simple_type_name": simple_type_name,
        "is_required": use_required,
        "is_multi": False,
    }


def _xsd_collect_elements_from_container(container: ET.Element) -> list[ET.Element]:
    out = []
    for n in container.iter():
        if _xsd_tag_local(n.tag) != "element":
            continue
        if not (n.get("name") or "").strip():
            continue
        out.append(n)
    return out


def _xsd_collect_attributes_from_container(container: ET.Element) -> list[ET.Element]:
    out = []
    for n in container.iter():
        if _xsd_tag_local(n.tag) != "attribute":
            continue
        nm = (n.get("name") or "").strip()
        rf = (n.get("ref") or "").strip()
        if not nm and not rf:
            continue
        out.append(n)
    return out


def _xsd_parse_dataset_defs_from_root(
    root: ET.Element,
    simple_types: dict | None = None,
) -> tuple[list[dict], list[str]]:
    notes: list[str] = []
    if _xsd_tag_local(root.tag) != "schema":
        notes.append("Dosya kök etiketi 'schema' değil; yine de parse denendi.")

    top_elements = [
        ch
        for ch in list(root)
        if _xsd_tag_local(ch.tag) == "element" and (ch.get("name") or "").strip()
    ]
    complex_types = {}
    for ch in list(root):
        if _xsd_tag_local(ch.tag) != "complexType":
            continue
        nm = (ch.get("name") or "").strip()
        if nm:
            complex_types[nm] = ch

    global_elements = {}
    for ch in top_elements:
        nm = (ch.get("name") or "").strip()
        if nm:
            global_elements[nm] = ch

    cache: dict[str, list[dict]] = {}
    active: set[str] = set()

    def collect_fields(type_local_name: str) -> list[dict]:
        tname = (type_local_name or "").strip()
        if not tname:
            return []
        if tname in cache:
            return list(cache[tname])
        if tname in active:
            return []
        active.add(tname)

        ct = complex_types.get(tname)
        if ct is None:
            active.remove(tname)
            cache[tname] = []
            return []

        fields: list[dict] = []

        cc = None
        for c in list(ct):
            if _xsd_tag_local(c.tag) == "complexContent":
                cc = c
                break

        if cc is not None:
            for child in list(cc):
                loc = _xsd_tag_local(child.tag)
                if loc not in ("extension", "restriction"):
                    continue
                base = _xsd_local_type_name(child.get("base"))
                if base:
                    fields.extend(collect_fields(base))
                for el in _xsd_collect_elements_from_container(child):
                    fd = _xsd_field_def_from_element(
                        el, simple_types=simple_types, global_elements=global_elements
                    )
                    if fd:
                        fields.append(fd)
                for at in _xsd_collect_attributes_from_container(child):
                    fd = _xsd_field_def_from_attribute(at, simple_types=simple_types)
                    if fd:
                        fields.append(fd)
        else:
            for el in _xsd_collect_elements_from_container(ct):
                fd = _xsd_field_def_from_element(
                    el, simple_types=simple_types, global_elements=global_elements
                )
                if fd:
                    fields.append(fd)
            for at in _xsd_collect_attributes_from_container(ct):
                fd = _xsd_field_def_from_attribute(at, simple_types=simple_types)
                if fd:
                    fields.append(fd)

        uniq = []
        seen = set()
        for f in fields:
            key = (f.get("name") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            uniq.append(f)

        cache[tname] = uniq
        active.remove(tname)
        return list(uniq)

    dataset_defs = []
    used_table_names = set()

    for el in top_elements:
        el_name = (el.get("name") or "").strip()
        tname = _xsd_local_type_name(el.get("type"))
        if not el_name or not tname:
            continue
        if el_name.lower().startswith("abstract"):
            continue
        if el_name.lower().endswith("type"):
            continue

        ct = complex_types.get(tname)
        if ct is None:
            continue
        if str(ct.get("abstract") or "").strip().lower() in ("true", "1"):
            continue

        fields = collect_fields(tname)
        if not fields:
            continue

        has_geom = any(bool(f.get("is_geometry")) for f in fields)
        if not has_geom:
            # Geometri içermeyen tipleri feature set olarak atla.
            continue

        table_base = _sanitize_table_name(el_name)
        candidate = table_base
        i = 2
        while candidate in used_table_names:
            suffix = f"_{i}"
            candidate = f"{table_base[: max(1, 55 - len(suffix))]}{suffix}"
            i += 1
        used_table_names.add(candidate)

        dataset_defs.append(
            {
                "element_name": el_name,
                "type_name": tname,
                "table_name": candidate,
                "fields": fields,
            }
        )

    if not dataset_defs:
        notes.append("XSD içinde oluşturulabilir feature dataset bulunamadı.")
    return dataset_defs, notes


def _xsd_parse_dataset_defs(xsd_path: Path) -> tuple[list[dict], list[str]]:
    try:
        root = ET.parse(xsd_path).getroot()
    except Exception as e:
        raise ValueError(f"XSD parse edilemedi: {e}") from e

    simple_types, st_notes = _xsd_parse_simple_type_defs_from_root(root)
    ds, ds_notes = _xsd_parse_dataset_defs_from_root(root, simple_types=simple_types)
    return ds, st_notes + ds_notes


def _xsd_parse_schema_model(xsd_path: Path) -> tuple[list[dict], dict, list[str]]:
    try:
        root = ET.parse(xsd_path).getroot()
    except Exception as e:
        raise ValueError(f"XSD parse edilemedi: {e}") from e

    simple_types, st_notes = _xsd_parse_simple_type_defs_from_root(root)
    ds, ds_notes = _xsd_parse_dataset_defs_from_root(root, simple_types=simple_types)
    return ds, simple_types, st_notes + ds_notes


def _xsd_build_sql_columns(fields: list[dict]) -> tuple[list[dict], bool]:
    cols = []
    used = {"id"}
    has_geom = False
    for f in fields:
        raw_name = (f.get("name") or "").strip()
        if not raw_name:
            continue
        base = _sanitize_table_name(raw_name)
        if not base:
            continue
        if base == "id":
            base = "id_"
        col = base
        i = 2
        while col in used:
            suffix = f"_{i}"
            col = f"{base[: max(1, 55 - len(suffix))]}{suffix}"
            i += 1
        used.add(col)

        pg_type = (f.get("pg_type") or "text").strip()
        is_geom = bool(f.get("is_geometry"))
        if is_geom:
            has_geom = True
        cols.append(
            {
                "column_name": col,
                "source_name": raw_name,
                "xsd_type": f.get("xsd_type") or "unknown",
                "pg_type": pg_type,
                "is_geometry": is_geom,
                "domain_name": f.get("domain_name"),
                "simple_type_name": f.get("simple_type_name"),
                "is_required": bool(f.get("is_required")),
                "is_multi": bool(f.get("is_multi")),
            }
        )

    return cols, has_geom


def _xsd_domain_defs_from_simple_types(simple_types: dict) -> list[dict]:
    out = []
    used = set()
    for _, st in (simple_types or {}).items():
        if not st or not st.get("is_domain_candidate"):
            continue
        domain_name = _sanitize_table_name(
            st.get("domain_name") or f"dom_{st.get('name') or 'type'}"
        )
        base = (st.get("pg_base_type") or "text").strip()
        enums = list(st.get("enumerations") or [])
        facets = dict(st.get("facets") or {})

        if domain_name in used:
            continue
        used.add(domain_name)
        out.append(
            {
                "simple_type_name": st.get("name"),
                "domain_name": domain_name,
                "base_type": base,
                "enumerations": enums,
                "facets": facets,
            }
        )
    return out


def _xsd_safe_int(raw):
    try:
        return int(str(raw).strip())
    except Exception:
        return None


def _xsd_safe_num(raw):
    s = str(raw).strip()
    if not s:
        return None
    try:
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        try:
            return float(s)
        except Exception:
            return None


def _xsd_build_domain_checks(domain_def: dict) -> list[sql.Composable]:
    checks: list[sql.Composable] = []
    enums = list(domain_def.get("enumerations") or [])
    facets = dict(domain_def.get("facets") or {})
    base_type = (domain_def.get("base_type") or "").strip().lower()
    is_textual = base_type in ("text",) or ("char" in base_type)
    is_numeric = base_type in (
        "smallint",
        "integer",
        "bigint",
        "numeric",
        "real",
        "double precision",
    )

    if enums:
        checks.append(
            sql.SQL("VALUE IN ({})").format(
                sql.SQL(", ").join([sql.Literal(v) for v in enums])
            )
        )

    length_val = _xsd_safe_int(facets.get("length"))
    min_len = _xsd_safe_int(facets.get("minLength"))
    max_len = _xsd_safe_int(facets.get("maxLength"))
    if is_textual:
        if length_val is not None:
            checks.append(
                sql.SQL("char_length(VALUE) = {}").format(sql.Literal(length_val))
            )
        else:
            if min_len is not None:
                checks.append(
                    sql.SQL("char_length(VALUE) >= {}").format(sql.Literal(min_len))
                )
            if max_len is not None:
                checks.append(
                    sql.SQL("char_length(VALUE) <= {}").format(sql.Literal(max_len))
                )

    pattern = (facets.get("pattern") or "").strip()
    if pattern and is_textual:
        checks.append(sql.SQL("VALUE ~ {}").format(sql.Literal(pattern)))

    min_inc = _xsd_safe_num(facets.get("minInclusive"))
    max_inc = _xsd_safe_num(facets.get("maxInclusive"))
    min_exc = _xsd_safe_num(facets.get("minExclusive"))
    max_exc = _xsd_safe_num(facets.get("maxExclusive"))
    if is_numeric:
        if min_inc is not None:
            checks.append(sql.SQL("VALUE >= {}").format(sql.Literal(min_inc)))
        if max_inc is not None:
            checks.append(sql.SQL("VALUE <= {}").format(sql.Literal(max_inc)))
        if min_exc is not None:
            checks.append(sql.SQL("VALUE > {}").format(sql.Literal(min_exc)))
        if max_exc is not None:
            checks.append(sql.SQL("VALUE < {}").format(sql.Literal(max_exc)))

    return checks


@router.post("/create-postgis")
def create_postgis_schema(req: CreatePostgisSchemaReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_postgis(info)
        try:
            cur = conn.cursor()
            # Aynı isimli şema varsa kullanıcıyı uyar.
            cur.execute(
                """
                SELECT 1
                FROM information_schema.schemata
                WHERE schema_name = %s
                LIMIT 1
                """,
                (schema_name,),
            )
            if cur.fetchone():
                cur.close()
                return {
                    "ok": False,
                    "message": "Şema İsmi Mevcut, Yeni Şema Seçiniz",
                    "debug": f"schema_name={schema_name}",
                }

            # ✅ güvenli identifier
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
            conn.commit()
            cur.close()
        finally:
            conn.close()

        return {
            "ok": True,
            "message": f"'{schema_name}' şeması oluşturuldu.",
        }
    except Exception as e:
        if getattr(e, "pgcode", "") == "42P06":  # duplicate_schema
            return {
                "ok": False,
                "message": "Şema İsmi Mevcuttr, Yeni Şema Seçiniz",
                "debug": f"schema_name={schema_name}",
            }
        return {"ok": False, "message": "Şema oluşturulamadı.", "debug": str(e)}


@router.get("/postgis-schemas")
def list_postgis_schemas(conn_name: str):
    conn_name = (conn_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_postgis(info)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('information_schema')
                  AND schema_name NOT LIKE 'pg_%'
                ORDER BY schema_name
                """
            )
            rows = [r[0] for r in cur.fetchall() if r and r[0]]
            cur.close()
        finally:
            conn.close()

        return {"ok": True, "data": rows, "message": ""}
    except Exception as e:
        return {
            "ok": False,
            "data": [],
            "message": "Şemalar okunamadı.",
            "debug": str(e),
        }


@router.get("/dbmatch-vector-structure")
def dbmatch_vector_structure(file_path: str):
    file_path = (file_path or "").strip()
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path boş olamaz")

    src = Path(file_path)
    if not src.exists():
        return {"ok": False, "message": "Dosya bulunamadı.", "debug": file_path}
    if not src.is_file():
        return {"ok": False, "message": "Geçersiz dosya yolu.", "debug": file_path}

    ogr2ogr_exe = _ensure_ogr2ogr()
    if not ogr2ogr_exe:
        return {
            "ok": False,
            "message": "Katman analizi için 'ogr2ogr/ogrinfo' bulunamadı.",
            "debug": "GDAL/ogr2ogr kurulu değil veya PATH içinde değil.",
        }

    try:
        gdal_env = _build_gdal_env(ogr2ogr_exe)
        layers, notes = _dbmatch_collect_vector_structure(ogr2ogr_exe, src, gdal_env)
        if not layers:
            return {
                "ok": False,
                "message": "Dosyada okunabilir katman bulunamadı.",
                "debug": "; ".join(notes[:20]),
            }
        return {
            "ok": True,
            "message": "",
            "data": {"layers": layers, "file_name": src.name},
            "debug": "; ".join(notes[:20]),
        }
    except Exception as e:
        return {
            "ok": False,
            "message": "Katman analizi başarısız.",
            "debug": str(e),
        }


@router.get("/dbmatch-schema-tables")
def dbmatch_schema_tables(conn_name: str, schema_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    try:
        tables = _dbmatch_list_schema_tables(info, schema_name)
        return {"ok": True, "message": "", "data": tables}
    except Exception as e:
        return {
            "ok": False,
            "message": "Tablo listesi alınamadı.",
            "data": [],
            "debug": str(e),
        }


@router.get("/dbmatch-table-columns")
def dbmatch_table_columns(conn_name: str, schema_name: str, table_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()
    table_name = (table_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name boş olamaz")

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    try:
        cols = _dbmatch_list_table_columns(info, schema_name, table_name)
        if not cols:
            return {
                "ok": False,
                "message": "Seçilen tabloda kolon bulunamadı.",
                "data": [],
                "debug": f"{schema_name}.{table_name}",
            }
        return {"ok": True, "message": "", "data": cols}
    except Exception as e:
        return {
            "ok": False,
            "message": "Kolon listesi alınamadı.",
            "data": [],
            "debug": str(e),
        }


@router.post("/dbmatch-load-postgis")
def dbmatch_load_postgis(req: DbMatchLoadReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    file_path = (req.file_path or "").strip()
    layer_mappings = req.layer_mappings or []

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path boş olamaz")
    if not layer_mappings:
        return {"ok": False, "message": "Aktarım için katman eşleştirmesi bulunamadı.", "data": []}

    src = Path(file_path)
    if not src.exists():
        return {"ok": False, "message": "Dosya bulunamadı.", "debug": file_path}
    if not src.is_file():
        return {"ok": False, "message": "Geçersiz dosya yolu.", "debug": file_path}

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    ogr2ogr_exe = _ensure_ogr2ogr()
    if not ogr2ogr_exe:
        return {
            "ok": False,
            "message": "Aktarım için 'ogr2ogr' bulunamadı.",
            "debug": "GDAL/ogr2ogr kurulu değil veya PATH içinde değil.",
        }

    gdal_env = _build_gdal_env(ogr2ogr_exe)
    pg_dsn = (
        f"PG:host={info.get('Host')} "
        f"port={info.get('Port')} "
        f"dbname={info.get('Database')} "
        f"user={info.get('UserName')} "
        f"password={info.get('Password') or ''}"
    )

    conn = None
    cur = None
    results = []
    success_count = 0
    fail_count = 0
    global_notes = []

    try:
        conn = _connect_postgis(info)
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
            return {
                "ok": False,
                "message": "Seçilen şema bulunamadı.",
                "debug": f"schema_name={schema_name}",
            }

        cur.execute(
            """
            SELECT 1
            FROM pg_extension
            WHERE extname = 'postgis'
            LIMIT 1
            """
        )
        if not cur.fetchone():
            return {
                "ok": False,
                "message": "Seçilen veritabanında PostGIS eklentisi etkin değil.",
                "debug": "CREATE EXTENSION postgis; komutu ilgili veritabanında çalıştırılmalı.",
            }

        for idx, lm in enumerate(layer_mappings, start=1):
            source_layer = (lm.source_layer or "").strip()
            target_table = (lm.target_table or "").strip()
            raw_mapping = dict(lm.field_mapping or {})
            tmp_table = f"_tmp_dbmatch_{uuid.uuid4().hex[:12]}"

            if not target_table:
                fail_count += 1
                results.append(
                    {
                        "layer": source_layer,
                        "table": target_table,
                        "ok": False,
                        "message": "Hedef tablo seçilmedi.",
                    }
                )
                continue

            try:
                cur.execute(
                    """
                    SELECT column_name, data_type, udt_name, is_nullable, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema_name, target_table),
                )
                target_rows = cur.fetchall()
                if not target_rows:
                    raise Exception(f"Hedef tablo bulunamadı: {schema_name}.{target_table}")

                target_attr_cols = {}
                target_geom_col = None
                for row in target_rows:
                    col_name = row[0]
                    data_type = row[1]
                    udt_name = row[2]
                    is_geom = (udt_name or "").strip().lower() in ("geometry", "st_geometry")
                    if is_geom and not target_geom_col:
                        target_geom_col = col_name
                    if not is_geom:
                        target_attr_cols[col_name.lower()] = col_name

                mapping = {}
                used_targets = set()
                invalid_targets = []
                duplicate_targets = []
                for src_field, tgt_col in raw_mapping.items():
                    src_name = (src_field or "").strip()
                    tgt_name = (tgt_col or "").strip()
                    if not src_name or not tgt_name:
                        continue

                    tgt_key = tgt_name.lower()
                    if tgt_key in used_targets:
                        duplicate_targets.append(tgt_name)
                        continue

                    if tgt_key not in target_attr_cols:
                        invalid_targets.append(tgt_name)
                        continue

                    used_targets.add(tgt_key)
                    mapping[src_name] = target_attr_cols[tgt_key]

                if duplicate_targets:
                    raise Exception(
                        "Aynı hedef kolona birden fazla kaynak alan eşleştirildi: "
                        + ", ".join(sorted(set(duplicate_targets)))
                    )
                if invalid_targets:
                    raise Exception(
                        "Tabloda bulunmayan hedef kolonlar seçildi: "
                        + ", ".join(sorted(set(invalid_targets)))
                    )
                if not mapping and not target_geom_col:
                    raise Exception("Ne alan eşleştirmesi ne de hedef geometri kolonu bulundu.")

                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(target_table),
                    )
                )
                row_before = cur.fetchone()
                count_before = int(row_before[0] or 0) if row_before else 0

                detected_srs, srs_notes = _detect_source_srs(
                    ogr2ogr_exe,
                    src,
                    source_layer or None,
                    gdal_env,
                )
                if srs_notes:
                    global_notes.extend([f"{source_layer or target_table}: {n}" for n in srs_notes])

                target_srid = _dbmatch_get_target_srid(
                    cur, schema_name, target_table, target_geom_col
                )

                cmd = [ogr2ogr_exe, "-f", "PostgreSQL", pg_dsn, str(src)]
                if source_layer:
                    cmd.append(source_layer)
                cmd += [
                    "-nln",
                    f"{schema_name}.{tmp_table}",
                    "-overwrite",
                    "-lco",
                    "GEOMETRY_NAME=geom_tmp",
                    "-lco",
                    "FID=id",
                    "-lco",
                    "PRECISION=NO",
                    "-skipfailures",
                ]
                if target_srid:
                    cmd += ["-t_srs", f"EPSG:{target_srid}"]
                if detected_srs:
                    cmd += ["-a_srs", detected_srs]

                try:
                    proc = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=900,
                        check=False,
                        env=gdal_env,
                    )
                except subprocess.TimeoutExpired:
                    raise Exception("ogr2ogr timeout (900sn).")
                except Exception as e:
                    raise Exception(f"ogr2ogr çalıştırılamadı: {e}")

                proc_text = (proc.stderr or proc.stdout or "").strip()
                if proc.returncode != 0 and detected_srs and _is_srs_processing_error(proc_text):
                    retry_cmd = _remove_a_srs_from_cmd(cmd)
                    try:
                        proc_retry = subprocess.run(
                            retry_cmd,
                            capture_output=True,
                            text=True,
                            timeout=900,
                            check=False,
                            env=gdal_env,
                        )
                    except subprocess.TimeoutExpired:
                        raise Exception("ogr2ogr timeout (retry, no -a_srs).")
                    except Exception as e:
                        raise Exception(f"ogr2ogr retry çalıştırılamadı: {e}")

                    if proc_retry.returncode == 0:
                        proc = proc_retry
                        proc_text = (proc.stderr or proc.stdout or "").strip()
                    else:
                        proc_text = (
                            (proc.stderr or proc.stdout or "").strip()
                            + "\n--- retry(no -a_srs) ---\n"
                            + (proc_retry.stderr or proc_retry.stdout or "").strip()
                        )

                if proc.returncode != 0:
                    raise Exception(f"ogr2ogr hata: {proc_text[:1600]}")

                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema_name, tmp_table),
                )
                tmp_cols = [r[0] for r in cur.fetchall() if r and r[0]]
                if not tmp_cols:
                    raise Exception("Geçici tabloda kolon bulunamadı.")

                tmp_exact = {c: c for c in tmp_cols}
                tmp_lower = {c.lower(): c for c in tmp_cols}
                tmp_norm = {}
                for c in tmp_cols:
                    n = _dbmatch_normalize_name(c)
                    if n and n not in tmp_norm:
                        tmp_norm[n] = c

                def _resolve_tmp_col(source_name: str):
                    if source_name in tmp_exact:
                        return tmp_exact[source_name]
                    k = source_name.lower()
                    if k in tmp_lower:
                        return tmp_lower[k]
                    return tmp_norm.get(_dbmatch_normalize_name(source_name))

                insert_cols = []
                select_exprs = []

                tmp_geom_col = _resolve_tmp_col("geom_tmp")
                if target_geom_col and tmp_geom_col:
                    insert_cols.append(target_geom_col)
                    select_exprs.append(
                        sql.SQL("t.{}").format(sql.Identifier(tmp_geom_col))
                    )

                missing_sources = []
                for src_name, tgt_name in mapping.items():
                    src_col = _resolve_tmp_col(src_name)
                    if not src_col:
                        missing_sources.append(src_name)
                        continue
                    insert_cols.append(tgt_name)
                    select_exprs.append(
                        sql.SQL("t.{}").format(sql.Identifier(src_col))
                    )

                if missing_sources:
                    global_notes.append(
                        f"{source_layer or target_table}: bazı kaynak alanlar geçici tabloda bulunamadı -> "
                        + ", ".join(missing_sources[:20])
                    )

                if not insert_cols:
                    raise Exception("Aktarılacak geçerli kolon bulunamadı.")

                cur.execute(
                    sql.SQL("INSERT INTO {}.{} ({}) SELECT {} FROM {}.{} t").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(target_table),
                        sql.SQL(", ").join([sql.Identifier(c) for c in insert_cols]),
                        sql.SQL(", ").join(select_exprs),
                        sql.Identifier(schema_name),
                        sql.Identifier(tmp_table),
                    )
                )

                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(target_table),
                    )
                )
                row_after = cur.fetchone()
                count_after = int(row_after[0] or 0) if row_after else count_before
                inserted = max(0, count_after - count_before)

                _dbmatch_drop_table_if_exists(cur, schema_name, tmp_table)
                conn.commit()

                success_count += 1
                results.append(
                    {
                        "layer": source_layer,
                        "table": target_table,
                        "ok": True,
                        "inserted": inserted,
                        "mapped_field_count": len(mapping),
                        "geometry_column": target_geom_col,
                        "srs": detected_srs,
                    }
                )

            except Exception as layer_error:
                conn.rollback()
                try:
                    _dbmatch_drop_table_if_exists(cur, schema_name, tmp_table)
                    conn.commit()
                except Exception:
                    conn.rollback()

                fail_count += 1
                results.append(
                    {
                        "layer": source_layer,
                        "table": target_table,
                        "ok": False,
                        "message": str(layer_error),
                    }
                )

        if success_count == 0:
            return {
                "ok": False,
                "message": "Hiçbir katman aktarılamadı.",
                "data": {"results": results, "success_count": success_count, "failed_count": fail_count},
                "debug": "\n".join(global_notes[:30]),
            }

        msg = f"{success_count} katman başarıyla aktarıldı."
        if fail_count > 0:
            msg += f" {fail_count} katman aktarımında hata var."

        return {
            "ok": True,
            "message": msg,
            "data": {"results": results, "success_count": success_count, "failed_count": fail_count},
            "debug": "\n".join(global_notes[:30]),
        }

    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "ok": False,
            "message": "Eşleme ile aktarım işlemi başarısız.",
            "debug": str(e),
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@router.post("/create-feature-from-xsd-postgis")
def create_feature_from_xsd_postgis(req: CreateFeatureFromXsdReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    xsd_path = (req.xsd_path or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")
    if not xsd_path:
        raise HTTPException(status_code=400, detail="xsd_path boş olamaz")

    src = Path(xsd_path)
    if not src.exists():
        return {"ok": False, "message": "XSD dosyası bulunamadı.", "debug": xsd_path}
    if not src.is_file():
        return {"ok": False, "message": "Geçersiz XSD dosya yolu.", "debug": xsd_path}
    if src.suffix.lower() != ".xsd":
        return {
            "ok": False,
            "message": "Desteklenmeyen dosya formatı. (.xsd olmalı)",
            "debug": f"ext={src.suffix.lower()}",
        }

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    try:
        dataset_defs, simple_types, parse_notes = _xsd_parse_schema_model(src)
    except Exception as e:
        return {"ok": False, "message": "XSD dosyası çözümlenemedi.", "debug": str(e)}

    if not dataset_defs:
        return {
            "ok": False,
            "message": "XSD içinde oluşturulabilir veri seti bulunamadı.",
            "debug": "; ".join(parse_notes[:10]),
        }

    domain_defs = _xsd_domain_defs_from_simple_types(simple_types)

    conn = None
    cur = None
    try:
        conn = _connect_postgis(info)
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
            return {
                "ok": False,
                "message": "Seçilen şema bulunamadı.",
                "debug": f"schema_name={schema_name}",
            }

        cur.execute(
            """
            SELECT 1
            FROM pg_extension
            WHERE extname = 'postgis'
            LIMIT 1
            """
        )
        if not cur.fetchone():
            return {
                "ok": False,
                "message": "Seçilen veritabanında PostGIS eklentisi etkin değil.",
                "debug": "CREATE EXTENSION postgis; komutu ilgili veritabanında çalıştırılmalı.",
            }

        existing_domains = []
        for d in domain_defs:
            dname = d.get("domain_name")
            if not dname:
                continue
            cur.execute(
                """
                SELECT 1
                FROM information_schema.domains
                WHERE domain_schema = %s AND domain_name = %s
                LIMIT 1
                """,
                (schema_name, dname),
            )
            if cur.fetchone():
                existing_domains.append(dname)

        if existing_domains:
            if len(existing_domains) == 1:
                return {
                    "ok": False,
                    "message": "Aynı isimde domain mevcut. Hedef şema temizlenmeli veya farklı şema seçilmeli.",
                    "debug": f"{schema_name}.{existing_domains[0]}",
                }
            return {
                "ok": False,
                "message": "Bazı domain adları hedef şemada zaten mevcut. İşlem başlatılmadı.",
                "debug": ", ".join(
                    [f"{schema_name}.{d}" for d in existing_domains[:30]]
                ),
            }

        existing_tables = []
        for ds in dataset_defs:
            tname = ds.get("table_name")
            if not tname:
                continue
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                LIMIT 1
                """,
                (schema_name, tname),
            )
            if cur.fetchone():
                existing_tables.append(tname)

        if existing_tables:
            if len(existing_tables) == 1:
                return {
                    "ok": False,
                    "message": "Aynı isimde tablo mevcut. XSD içeriğini veya hedef şemayı değiştirin.",
                    "debug": f"{schema_name}.{existing_tables[0]}",
                }
            return {
                "ok": False,
                "message": "Bazı tablo adları hedef şemada zaten mevcut. İşlem başlatılmadı.",
                "debug": ", ".join(
                    [f"{schema_name}.{t}" for t in existing_tables[:30]]
                ),
            }

        created_domains = []
        for d in domain_defs:
            dname = d.get("domain_name")
            base_type = (d.get("base_type") or "text").strip()
            facets = dict(d.get("facets") or {})
            if not dname:
                continue

            # Güvenli tip kümesi dışına çıkılmaması için sadece bilinen tipleri geçir.
            if base_type not in (
                "text",
                "bigint",
                "integer",
                "double precision",
                "boolean",
                "timestamp without time zone",
                "date",
                "time without time zone",
                "numeric",
            ):
                base_type = "text"

            # Numeric kısıtları tip seviyesine de yansıtılır.
            base_render = base_type
            if base_type == "numeric":
                total_digits = _xsd_safe_int(facets.get("totalDigits"))
                fraction_digits = _xsd_safe_int(facets.get("fractionDigits"))
                if (
                    total_digits is not None
                    and total_digits > 0
                    and fraction_digits is not None
                    and fraction_digits >= 0
                    and total_digits >= fraction_digits
                ):
                    base_render = f"numeric({total_digits},{fraction_digits})"
                elif total_digits is not None and total_digits > 0:
                    base_render = f"numeric({total_digits})"

            stmt = sql.SQL("CREATE DOMAIN {}.{} AS {}").format(
                sql.Identifier(schema_name),
                sql.Identifier(dname),
                sql.SQL(base_render),
            )
            cur.execute(stmt)
            checks = _xsd_build_domain_checks(
                {
                    "enumerations": d.get("enumerations"),
                    "facets": d.get("facets"),
                    "base_type": base_type,
                }
            )
            for i, chk in enumerate(checks, start=1):
                cname_base = _sanitize_table_name(f"{dname}")[:58]
                if not cname_base:
                    cname_base = f"{dname[:40]}"
                alter_stmt = sql.SQL(
                    "ALTER DOMAIN {}.{} ADD CONSTRAINT {} CHECK ({})"
                ).format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dname),
                    sql.Identifier(cname_base),
                    chk,
                )
                cur.execute(alter_stmt)

            created_domains.append(
                {
                    "domain": dname,
                    "simple_type": d.get("simple_type_name"),
                    "base_type": base_render,
                    "enum_count": len(d.get("enumerations") or []),
                    "check_count": len(checks),
                }
            )

        created = []
        for ds in dataset_defs:
            tname = ds.get("table_name")
            fields = ds.get("fields") or []
            columns, has_geom = _xsd_build_sql_columns(fields)
            if not tname or not has_geom:
                continue

            col_defs = [
                sql.SQL("{} {}").format(
                    sql.Identifier("id"),
                    sql.SQL("bigserial primary key"),
                )
            ]
            for c in columns:
                col_name = c.get("column_name")
                pg_type = (c.get("pg_type") or "text").strip()
                domain_name = (c.get("domain_name") or "").strip()
                is_required = bool(c.get("is_required"))
                if not col_name:
                    continue

                if domain_name:
                    col_type_sql = sql.SQL("{}.{}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(domain_name),
                    )
                else:
                    col_type_sql = sql.SQL(pg_type)

                col_def = sql.SQL("{} {}").format(
                    sql.Identifier(col_name),
                    col_type_sql,
                )
                if is_required:
                    col_def = sql.Composed([col_def, sql.SQL(" NOT NULL")])
                col_defs.append(col_def)

            if len(col_defs) == 1:
                continue

            create_sql = sql.SQL("CREATE TABLE {}.{} ({})").format(
                sql.Identifier(schema_name),
                sql.Identifier(tname),
                sql.SQL(", ").join(col_defs),
            )
            cur.execute(create_sql)
            created.append(
                {
                    "table": tname,
                    "element_name": ds.get("element_name"),
                    "type_name": ds.get("type_name"),
                    "column_count": len(col_defs),
                    "domain_column_count": len(
                        [c for c in columns if (c.get("domain_name") or "").strip()]
                    ),
                }
            )

        if not created:
            conn.rollback()
            return {
                "ok": False,
                "message": "XSD çözümlendi ancak oluşturulabilir tablo bulunamadı.",
                "debug": "Tüm dataset tanımları geometri içermiyor veya kolon üretilemedi.",
            }

        conn.commit()

        msg = (
            f"'{src.name}' dosyasından {len(created)} veri seti oluşturuldu."
            f"\nDomain oluşturma: {len(created_domains)} adet"
        )
        if parse_notes:
            msg += "\nNot: " + "; ".join(parse_notes[:4])
        lines = [
            f"- {schema_name}.{it['table']} ({it['column_count']} kolon, domainli={it['domain_column_count']})"
            for it in created[:20]
        ]
        if lines:
            msg += "\n" + "\n".join(lines)

        return {
            "ok": True,
            "message": msg,
            "data": {
                "schema": schema_name,
                "tables": created,
                "domains": created_domains,
            },
        }
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "ok": False,
            "message": "XSD'den veri seti oluşturulamadı.",
            "debug": str(e),
        }
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@router.post("/import-vector-postgis")
def import_vector_to_postgis(req: ImportVectorToPostgisReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    file_path = (req.file_path or "").strip()
    manual_epsg = req.manual_epsg

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path boş olamaz")
    if manual_epsg is not None:
        try:
            manual_epsg = int(manual_epsg)
            if manual_epsg <= 0:
                raise ValueError
        except Exception:
            return {
                "ok": False,
                "message": "Manuel EPSG kodu geçersiz.",
                "debug": str(req.manual_epsg),
            }

    src = Path(file_path)
    if not src.exists():
        return {"ok": False, "message": "Dosya bulunamadı.", "debug": file_path}
    if not src.is_file():
        return {"ok": False, "message": "Geçersiz dosya yolu.", "debug": file_path}

    ext = src.suffix.lower()
    if ext not in (".gml", ".xml", ".shp"):
        return {
            "ok": False,
            "message": "Desteklenmeyen dosya formatı. (gml/shp/xml)",
            "debug": f"ext={ext}",
        }

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

    # ogr2ogr yoksa açık uyarı ver.
    ogr2ogr_exe = _ensure_ogr2ogr()
    if not ogr2ogr_exe:
        return {
            "ok": False,
            "message": "Aktarım için 'ogr2ogr' bulunamadı.",
            "debug": "GDAL/ogr2ogr kurulu değil veya PATH içinde değil.",
        }

    gdal_env = _build_gdal_env(ogr2ogr_exe)
    layer_names = []
    discovery_notes = []
    if ext in (".gml", ".xml"):
        layer_names, discovery_notes = _resolve_vector_layers(
            ogr2ogr_exe, src, gdal_env
        )
    else:
        layer_names = [src.stem]
    import_jobs, is_multi_gml = _build_import_jobs(src, ext, layer_names)

    srs_notes = []
    missing_srs = []
    for job in import_jobs:
        detected_srs, notes = _detect_source_srs(
            ogr2ogr_exe,
            src,
            job.get("source_layer"),
            gdal_env,
        )
        used_manual_epsg = False
        if not detected_srs and manual_epsg is not None:
            detected_srs = f"EPSG:{manual_epsg}"
            used_manual_epsg = True
        job["detected_srs"] = detected_srs
        job["used_manual_epsg"] = used_manual_epsg
        if notes:
            srs_notes.extend(notes)
        if not detected_srs:
            layer_txt = job.get("source_layer") or "<varsayılan>"
            missing_srs.append(f"{layer_txt} -> {schema_name}.{job['table_name']}")

    if missing_srs:
        return {
            "ok": False,
            "message": "Koordinat sistemi (EPSG) tespit edilemedi. Lütfen EPSG kodu giriniz.",
            "debug": "\n".join(missing_srs[:30]),
            "requires_epsg": True,
        }

    try:
        conn = _connect_postgis(info)
        try:
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
                cur.close()
                return {
                    "ok": False,
                    "message": "Seçilen şema bulunamadı.",
                    "debug": f"schema_name={schema_name}",
                }

            cur.execute(
                """
                SELECT 1
                FROM pg_extension
                WHERE extname = 'postgis'
                LIMIT 1
                """
            )
            if not cur.fetchone():
                cur.close()
                return {
                    "ok": False,
                    "message": "Seçilen veritabanında PostGIS eklentisi etkin değil.",
                    "debug": "CREATE EXTENSION postgis; komutu ilgili veritabanında çalıştırılmalı.",
                }

            existing = []
            for job in import_jobs:
                table_name = job["table_name"]
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    LIMIT 1
                    """,
                    (schema_name, table_name),
                )
                if cur.fetchone():
                    existing.append(table_name)

            if existing:
                cur.close()
                if len(existing) == 1:
                    return {
                        "ok": False,
                        "message": "Aynı isimde tablo mevcut. Dosya adını değiştirip tekrar deneyin.",
                        "debug": f"{schema_name}.{existing[0]}",
                    }
                return {
                    "ok": False,
                    "message": "Bazı katman tabloları zaten mevcut. Lütfen mevcut tabloları silin veya farklı dosya adı kullanın.",
                    "debug": ", ".join([f"{schema_name}.{t}" for t in existing[:30]]),
                }

            cur.close()
        finally:
            conn.close()
    except Exception as e:
        return {"ok": False, "message": "Şema kontrolü başarısız.", "debug": str(e)}

    pg_dsn = (
        f"PG:host={info.get('Host')} "
        f"port={info.get('Port')} "
        f"dbname={info.get('Database')} "
        f"user={info.get('UserName')} "
        f"password={info.get('Password') or ''}"
    )

    epsg_codes = []
    for job in import_jobs:
        c = _extract_epsg_code(job.get("detected_srs"))
        if c is not None:
            epsg_codes.append(c)

    db_srs_defs = {}
    if epsg_codes:
        try:
            db_srs_defs = _load_srs_defs_from_db(info, epsg_codes)
        except Exception as e:
            srs_notes.append(f"spatial_ref_sys sorgulanamadı: {e}")

    imported_tables = []
    srs_fallback_tables = []
    promoted_multi_tables = []
    for job in import_jobs:
        table_name = job["table_name"]
        epsg_code = _extract_epsg_code(job.get("detected_srs"))
        cmd_srs = db_srs_defs.get(epsg_code) if epsg_code is not None else None
        if not cmd_srs:
            cmd_srs = job["detected_srs"]

        cmd = [
            ogr2ogr_exe,
            "-f",
            "PostgreSQL",
            pg_dsn,
            str(src),
        ]

        if is_multi_gml and job.get("source_layer"):
            cmd.append(job["source_layer"])

        cmd += [
            "-nln",
            f"{schema_name}.{table_name}",
            "-a_srs",
            cmd_srs,
            "-lco",
            "GEOMETRY_NAME=geom",
            "-lco",
            "FID=id",
            "-lco",
            "PRECISION=NO",
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=900 if is_multi_gml else 600,
                check=False,
                env=gdal_env,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": "Aktarım zaman aşımına uğradı.",
                "debug": f"ogr2ogr timeout | tablo={schema_name}.{table_name}",
            }
        except Exception as e:
            return {
                "ok": False,
                "message": "Aktarım komutu çalıştırılamadı.",
                "debug": str(e),
            }

        proc_text = (proc.stderr or proc.stdout or "").strip()
        if proc.returncode != 0 and _is_srs_processing_error(proc_text):
            retry_cmd = _remove_a_srs_from_cmd(cmd)
            try:
                proc_retry = subprocess.run(
                    retry_cmd,
                    capture_output=True,
                    text=True,
                    timeout=900 if is_multi_gml else 600,
                    check=False,
                    env=gdal_env,
                )
            except subprocess.TimeoutExpired:
                return {
                    "ok": False,
                    "message": "Aktarım zaman aşımına uğradı.",
                    "debug": f"ogr2ogr timeout (retry) | tablo={schema_name}.{table_name}",
                }
            except Exception as e:
                return {
                    "ok": False,
                    "message": "Aktarım komutu çalıştırılamadı.",
                    "debug": str(e),
                }

            if proc_retry.returncode == 0:
                proc = proc_retry
                srs_fallback_tables.append(f"{schema_name}.{table_name}")
            else:
                proc_text = (
                    (proc.stderr or proc.stdout or "").strip()
                    + "\n--- retry(no -a_srs) ---\n"
                    + (proc_retry.stderr or proc_retry.stdout or "").strip()
                )
                proc.returncode = proc_retry.returncode

        if proc.returncode != 0 and _is_geometry_type_mismatch_error(proc_text):
            try:
                _drop_table_if_exists(info, schema_name, table_name)
            except Exception:
                pass

            promote_cmd = _add_promote_to_multi_to_cmd(cmd)
            try:
                proc_retry = subprocess.run(
                    promote_cmd,
                    capture_output=True,
                    text=True,
                    timeout=900 if is_multi_gml else 600,
                    check=False,
                    env=gdal_env,
                )
            except subprocess.TimeoutExpired:
                return {
                    "ok": False,
                    "message": "Aktarım zaman aşımına uğradı.",
                    "debug": f"ogr2ogr timeout (retry promote_to_multi) | tablo={schema_name}.{table_name}",
                }
            except Exception as e:
                return {
                    "ok": False,
                    "message": "Aktarım komutu çalıştırılamadı.",
                    "debug": str(e),
                }

            if proc_retry.returncode == 0:
                proc = proc_retry
                promoted_multi_tables.append(f"{schema_name}.{table_name}")
            else:
                proc_text = (
                    (proc.stderr or proc.stdout or "").strip()
                    + "\n--- retry(promote_to_multi) ---\n"
                    + (proc_retry.stderr or proc_retry.stdout or "").strip()
                )
                proc.returncode = proc_retry.returncode

        if proc.returncode != 0:
            layer_info = (
                f" layer={job.get('source_layer')}" if job.get("source_layer") else ""
            )
            return {
                "ok": False,
                "message": "Vektör veri PostGIS'e aktarılamadı.",
                "debug": f"tablo={schema_name}.{table_name}{layer_info}\n{proc_text[:2500]}",
            }

        imported_tables.append(
            {
                "table": table_name,
                "source_layer": job.get("source_layer"),
                "srs": job.get("detected_srs"),
                "used_manual_epsg": bool(job.get("used_manual_epsg")),
                "srs_applied": (
                    False
                    if f"{schema_name}.{table_name}" in srs_fallback_tables
                    else True
                ),
                "promoted_to_multi": (
                    True
                    if f"{schema_name}.{table_name}" in promoted_multi_tables
                    else False
                ),
            }
        )

    table_stats = []
    try:
        conn = _connect_postgis(info)
        try:
            cur = conn.cursor()
            for it in imported_tables:
                tname = it["table"]
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    LIMIT 1
                    """,
                    (schema_name, tname),
                )
                exists = bool(cur.fetchone())
                row_count = None
                if exists:
                    cur.execute(
                        sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                            sql.Identifier(schema_name),
                            sql.Identifier(tname),
                        )
                    )
                    row = cur.fetchone()
                    row_count = int(row[0]) if row and row[0] is not None else None
                table_stats.append(
                    {
                        "table": tname,
                        "source_layer": it.get("source_layer"),
                        "srs": it.get("srs"),
                        "used_manual_epsg": bool(it.get("used_manual_epsg")),
                        "srs_applied": it.get("srs_applied", True),
                        "promoted_to_multi": it.get("promoted_to_multi", False),
                        "exists": exists,
                        "count": row_count,
                    }
                )

            cur.close()
        finally:
            conn.close()
    except Exception:
        table_stats = [
            {
                "table": it["table"],
                "source_layer": it.get("source_layer"),
                "srs": it.get("srs"),
                "used_manual_epsg": bool(it.get("used_manual_epsg")),
                "srs_applied": it.get("srs_applied", True),
                "promoted_to_multi": it.get("promoted_to_multi", False),
                "exists": False,
                "count": None,
            }
            for it in imported_tables
        ]

    if any(not s.get("exists") for s in table_stats):
        missing = [s["table"] for s in table_stats if not s.get("exists")]
        return {
            "ok": False,
            "message": "Aktarım komutu çalıştı ama bazı hedef tablolar oluşmadı.",
            "debug": ", ".join([f"{schema_name}.{m}" for m in missing[:30]]),
        }

    if len(table_stats) == 1 and (table_stats[0].get("count") == 0):
        return {
            "ok": False,
            "message": "Aktarım tamamlandı fakat tabloya kayıt yazılmadı.",
            "debug": f"{schema_name}.{table_stats[0].get('table')}",
        }

    if len(table_stats) == 1:
        only = table_stats[0]
        msg = f"'{src.name}' veri seti '{schema_name}.{only['table']}' tablosuna aktarıldı."
        if only.get("count") is not None:
            msg += f"\nKayıt sayısı: {only['count']}"
        if only.get("srs"):
            msg += f"\nKoordinat sistemi: {only['srs']}"
        if only.get("used_manual_epsg", False):
            msg += "\nNot: Koordinat sistemi kullanıcı tarafından girilen EPSG kodu ile atandı."
        if not only.get("srs_applied", True):
            msg += "\nNot: EPSG tanımı PROJ içinde bulunamadığı için CRS metadata kaynağından okunarak/yedek modda aktarıldı."
        if only.get("promoted_to_multi", False):
            msg += "\nNot: Geometri tip uyumsuzluğu nedeniyle hedef geometri tipi multi olarak oluşturuldu."
        if srs_notes:
            msg += "\nNot: " + "; ".join(srs_notes[:2])
        return {
            "ok": True,
            "message": msg,
            "data": {
                "schema": schema_name,
                "table": only["table"],
                "count": only.get("count"),
                "srs": only.get("srs"),
                "tables": table_stats,
            },
        }

    non_empty = [s for s in table_stats if (s.get("count") or 0) > 0]
    if not non_empty:
        return {
            "ok": False,
            "message": "Aktarım tamamlandı fakat katman tablolarına kayıt yazılamadı.",
            "debug": ", ".join(
                [
                    f"{schema_name}.{s['table']}={s.get('count')}"
                    for s in table_stats[:30]
                ]
            ),
        }

    msg = f"'{src.name}' dosyasındaki {len(table_stats)} katman PostGIS'e aktarıldı."
    msg += f"\nDolu tablo sayısı: {len(non_empty)}"
    if discovery_notes:
        msg += "\nNot: " + "; ".join(discovery_notes[:3])
    if srs_notes:
        msg += "\nSRS Notu: " + "; ".join(srs_notes[:3])
    if srs_fallback_tables:
        msg += "\nSRS Yedek Mod: " + ", ".join(srs_fallback_tables[:10])
    if promoted_multi_tables:
        msg += "\nGeometri Multi Mod: " + ", ".join(promoted_multi_tables[:10])
    lines = []
    for s in table_stats[:20]:
        layer_txt = f" (layer: {s['source_layer']})" if s.get("source_layer") else ""
        srs_txt = f" | {s['srs']}" if s.get("srs") else ""
        mode_txt = " | srs=ok" if s.get("srs_applied", True) else " | srs=yedek"
        manual_txt = " | srs=manuel" if s.get("used_manual_epsg", False) else ""
        geom_txt = " | geom=multi" if s.get("promoted_to_multi", False) else ""
        lines.append(
            f"- {schema_name}.{s['table']}{layer_txt}{srs_txt}{mode_txt}{manual_txt}{geom_txt} -> {s.get('count', 'bilinmiyor')} kayıt"
        )
    if lines:
        msg += "\n" + "\n".join(lines)

    return {
        "ok": True,
        "message": msg,
        "data": {"schema": schema_name, "tables": table_stats},
    }


@router.get("/esri-db-schemas")
def list_esri_db_schemas(conn_name: str):
    conn_name = (conn_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_postgis(info)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('information_schema')
                  AND schema_name NOT LIKE 'pg_%'
                ORDER BY schema_name
                """
            )
            rows = [r[0] for r in cur.fetchall() if r and r[0]]
            cur.close()
        finally:
            conn.close()

        return {"ok": True, "data": rows, "message": ""}
    except Exception as e:
        return {
            "ok": False,
            "data": [],
            "message": "Şemalar okunamadı.",
            "debug": str(e),
        }


@router.post("/import-vector-esri-db")
def import_vector_to_esri_db(req: ImportVectorToEsriDbReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    file_path = (req.file_path or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name boş olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name boş olamaz")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path boş olamaz")

    src = Path(file_path)
    if not src.exists():
        return {"ok": False, "message": "Dosya bulunamadı.", "debug": file_path}
    if not src.is_file():
        return {"ok": False, "message": "Geçersiz dosya yolu.", "debug": file_path}

    ext = src.suffix.lower()
    if ext not in (".gml", ".xml", ".shp"):
        return {
            "ok": False,
            "message": "Desteklenmeyen dosya formatı. (gml/shp/xml)",
            "debug": f"ext={ext}",
        }

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    table_name = _sanitize_table_name(src.stem)
    ogr2ogr_exe = _ensure_ogr2ogr()
    if not ogr2ogr_exe:
        return {
            "ok": False,
            "message": "Aktarım için 'ogr2ogr' bulunamadı.",
            "debug": "GDAL/ogr2ogr kurulu değil veya PATH içinde değil.",
        }

    st_schema = None
    try:
        conn = _connect_postgis(info)
        try:
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
                cur.close()
                return {
                    "ok": False,
                    "message": "Seçilen şema bulunamadı.",
                    "debug": f"schema_name={schema_name}",
                }

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
            if not row:
                cur.close()
                return {
                    "ok": False,
                    "message": "Seçilen veritabanında ST_Geometry tipi bulunamadı.",
                    "debug": "Esri ST_Geometry kurulumunu kontrol edin.",
                }
            st_schema = row[0]

            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                LIMIT 1
                """,
                (schema_name, table_name),
            )
            if cur.fetchone():
                cur.close()
                return {
                    "ok": False,
                    "message": "Aynı isimde tablo mevcut. Dosya adını değiştirip tekrar deneyin.",
                    "debug": f"{schema_name}.{table_name}",
                }
            cur.close()
        finally:
            conn.close()
    except Exception as e:
        return {"ok": False, "message": "Şema kontrolü başarısız.", "debug": str(e)}

    pg_dsn = (
        f"PG:host={info.get('Host')} "
        f"port={info.get('Port')} "
        f"dbname={info.get('Database')} "
        f"user={info.get('UserName')} "
        f"password={info.get('Password') or ''}"
    )

    gdal_env = _build_gdal_env(ogr2ogr_exe)
    detected_srs, srs_notes = _detect_source_srs(ogr2ogr_exe, src, None, gdal_env)
    if not detected_srs:
        return {
            "ok": False,
            "message": "Koordinat sistemi (EPSG) tespit edilemedi. Kaynak veride CRS/SRS bilgisi tanımlı olmalı.",
            "debug": f"dosya={src.name}",
        }

    epsg_code = _extract_epsg_code(detected_srs)
    cmd_srs = detected_srs
    if epsg_code is not None:
        try:
            db_defs = _load_srs_defs_from_db(info, [epsg_code])
            cmd_srs = db_defs.get(epsg_code) or detected_srs
        except Exception as e:
            srs_notes.append(f"spatial_ref_sys sorgulanamadı: {e}")

    column_types = f"wkb_geometry={st_schema}.st_geometry"
    cmd = [
        ogr2ogr_exe,
        "-f",
        "PostgreSQL",
        pg_dsn,
        str(src),
        "-nln",
        f"{schema_name}.{table_name}",
        "-a_srs",
        cmd_srs,
        "-lco",
        "FID=objectid",
        "-lco",
        "GEOMETRY_NAME=wkb_geometry",
        "-lco",
        f"COLUMN_TYPES={column_types}",
        "-lco",
        "PRECISION=NO",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            env=gdal_env,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "message": "Aktarım zaman aşımına uğradı.",
            "debug": "ogr2ogr timeout (900sn).",
        }
    except Exception as e:
        return {
            "ok": False,
            "message": "Aktarım komutu çalıştırılamadı.",
            "debug": str(e),
        }

    used_srs_fallback = False
    proc_text = (proc.stderr or proc.stdout or "").strip()
    if proc.returncode != 0 and _is_srs_processing_error(proc_text):
        retry_cmd = _remove_a_srs_from_cmd(cmd)
        try:
            proc_retry = subprocess.run(
                retry_cmd,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
                env=gdal_env,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": "Aktarım zaman aşımına uğradı.",
                "debug": "ogr2ogr timeout (retry, no -a_srs).",
            }
        except Exception as e:
            return {
                "ok": False,
                "message": "Aktarım komutu çalıştırılamadı.",
                "debug": str(e),
            }

        if proc_retry.returncode == 0:
            proc = proc_retry
            used_srs_fallback = True
        else:
            proc_text = (
                (proc.stderr or proc.stdout or "").strip()
                + "\n--- retry(no -a_srs) ---\n"
                + (proc_retry.stderr or proc_retry.stdout or "").strip()
            )
            proc.returncode = proc_retry.returncode

    if proc.returncode != 0:
        return {
            "ok": False,
            "message": "Vektör veri ESRI DB'ye aktarılamadı.",
            "debug": proc_text[:2500],
        }

    row_count = None
    table_exists = False
    try:
        conn = _connect_postgis(info)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                LIMIT 1
                """,
                (schema_name, table_name),
            )
            table_exists = bool(cur.fetchone())

            if table_exists:
                # İçe aktarım başarılıysa geometry kolonunu Esri tarafında yaygın isim olan shape'a taşı.
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s AND column_name = 'wkb_geometry'
                    LIMIT 1
                    """,
                    (schema_name, table_name),
                )
                has_wkb_geometry = bool(cur.fetchone())
                if has_wkb_geometry:
                    cur.execute(
                        sql.SQL("ALTER TABLE {}.{} RENAME COLUMN {} TO {}").format(
                            sql.Identifier(schema_name),
                            sql.Identifier(table_name),
                            sql.Identifier("wkb_geometry"),
                            sql.Identifier("shape"),
                        )
                    )
                    conn.commit()

                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name),
                    )
                )
                row = cur.fetchone()
                row_count = int(row[0]) if row and row[0] is not None else None

            cur.close()
        finally:
            conn.close()
    except Exception as e:
        return {
            "ok": False,
            "message": "Aktarım sonrası kontrol başarısız.",
            "debug": str(e),
        }

    if not table_exists:
        return {
            "ok": False,
            "message": "Aktarım komutu çalıştı ama hedef tablo oluşmadı.",
            "debug": (proc.stderr or proc.stdout or "").strip()[:2500],
        }

    if row_count == 0:
        return {
            "ok": False,
            "message": "Aktarım tamamlandı fakat tabloya kayıt yazılmadı.",
            "debug": (proc.stderr or proc.stdout or "").strip()[:2500],
        }

    msg = f"'{src.name}' veri seti '{schema_name}.{table_name}' tablosuna ESRI DB için aktarıldı."
    if row_count is not None:
        msg += f"\nKayıt sayısı: {row_count}"
    msg += f"\nKoordinat sistemi: {detected_srs}"
    if used_srs_fallback:
        msg += "\nNot: EPSG tanımı PROJ içinde bulunamadığı için CRS metadata yedek modda işlendi."
    if srs_notes:
        msg += "\nNot: " + "; ".join(srs_notes[:2])

    return {
        "ok": True,
        "message": msg,
        "data": {
            "schema": schema_name,
            "table": table_name,
            "count": row_count,
            "srs": detected_srs,
        },
    }

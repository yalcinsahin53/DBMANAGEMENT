from pathlib import Path
import json
import subprocess

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2 import sql

from services.routes.createesrifeature import _register_with_geodatabase
from services.routes.createpostgisschema import (
    _add_promote_to_multi_to_cmd,
    _build_gdal_env,
    _build_import_jobs,
    _detect_source_srs,
    _drop_table_if_exists,
    _ensure_ogr2ogr,
    _ensure_ogrinfo,
    _extract_epsg_code,
    _is_geometry_type_mismatch_error,
    _is_srs_processing_error,
    _load_srs_defs_from_db,
    _remove_a_srs_from_cmd,
    _resolve_vector_layers,
    _sanitize_table_name,
    _validate_esri_conn,
    _connect_postgis,
)


router = APIRouter(tags=["esri-import"])


class ImportVectorToEsriDbReqV2(BaseModel):
    conn_name: str
    schema_name: str
    file_path: str
    manual_epsg: int | None = None


def _detect_arcgis_geom_type(
    ogr2ogr_exe: str, src: Path, layer_name: str | None, gdal_env: dict
) -> str | None:
    ogrinfo_exe = _ensure_ogrinfo(ogr2ogr_exe)
    if not ogrinfo_exe:
        return None

    cmd = [ogrinfo_exe, "-ro", "-json", "-so", str(src)]
    if layer_name:
        cmd.append(layer_name)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=gdal_env,
        )
    except Exception:
        return None

    if proc.returncode != 0:
        return None

    raw = ((proc.stdout or "").strip() or (proc.stderr or "").strip()).strip()
    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except Exception:
        return None

    layer_obj = {}
    if isinstance(payload, dict):
        layers = payload.get("layers")
        if isinstance(layers, list) and layers:
            layer_obj = layers[0] if isinstance(layers[0], dict) else {}

    gtype = ""
    geom_fields = layer_obj.get("geometryFields") if isinstance(layer_obj, dict) else []
    if isinstance(geom_fields, list) and geom_fields:
        first = geom_fields[0]
        if isinstance(first, dict):
            gtype = str(first.get("type") or "").strip().lower()

    if not gtype:
        return None

    t = gtype.replace(" ", "")
    if "multipoint" in t:
        return "MULTIPOINT"
    if "point" in t:
        return "POINT"
    if "line" in t or "curve" in t:
        return "POLYLINE"
    if "polygon" in t or "surface" in t:
        return "POLYGON"
    return None


def _pick_or_create_objectid_field(info: dict, schema_name: str, table_name: str):
    conn = _connect_postgis(info)
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                a.attname AS col_name,
                t.typname AS udt_name,
                i.indisprimary AS is_primary
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            JOIN pg_type t ON t.oid = a.atttypid
            LEFT JOIN pg_index i
              ON i.indrelid = c.oid
             AND a.attnum = ANY(i.indkey)
             AND i.indisprimary = TRUE
            WHERE n.nspname = %s
              AND c.relname = %s
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            (schema_name, table_name),
        )
        rows = cur.fetchall() or []
        cols = [
            {
                "name": str(r[0] or ""),
                "udt": str(r[1] or "").lower(),
                "is_primary": bool(r[2]),
            }
            for r in rows
            if r and r[0]
        ]

        for c in cols:
            if c["is_primary"] and c["udt"] == "int4":
                cur.close()
                conn.commit()
                return c["name"], ""

        oid_col = "dbm_objectid"
        existing_dbm_oid = None
        for c in cols:
            if c["name"].lower() == oid_col:
                existing_dbm_oid = c
                break

        if existing_dbm_oid and existing_dbm_oid["udt"] == "int4":
            idx_name = f"ux_{table_name}_dbm_objectid"
            if len(idx_name) > 63:
                idx_name = idx_name[:63]
            cur.execute(
                sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {}.{} ({})").format(
                    sql.Identifier(idx_name),
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(oid_col),
                )
            )
            conn.commit()
            cur.close()
            return oid_col, "register icin mevcut dbm_objectid alani kullanildi."

        cur.execute(
            sql.SQL("ALTER TABLE {}.{} ADD COLUMN {} SERIAL").format(
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
                sql.Identifier(oid_col),
            )
        )
        idx_name = f"ux_{table_name}_dbm_objectid"
        if len(idx_name) > 63:
            idx_name = idx_name[:63]
        cur.execute(
            sql.SQL("CREATE UNIQUE INDEX {} ON {}.{} ({})").format(
                sql.Identifier(idx_name),
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
                sql.Identifier(oid_col),
            )
        )
        conn.commit()
        cur.close()
        return oid_col, "register icin dbm_objectid alani otomatik olusturuldu."
    finally:
        conn.close()


def _normalize_columns_for_esri_register(
    info: dict,
    schema_name: str,
    table_name: str,
    protected_cols: set[str] | None = None,
):
    protected = {c.lower() for c in (protected_cols or set())}
    converted = []

    # ArcMap 10.8 register adiminda en sorunsuz tipler.
    # ArcMap 10.8 RegisterWithGeodatabase adiminda guvenli kabul edilen dar tip seti.
    # Daha genis tipler (int8, numeric, timestamp, bool, json, uuid, vb.) text'e donusturulur.
    supported_udt = {"int2", "int4", "float4", "float8", "varchar", "bpchar", "text", "date"}

    conn = _connect_postgis(info)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table_name),
        )
        rows = cur.fetchall() or []
        for row in rows:
            col_name = str(row[0] or "")
            udt_name = str(row[1] or "").lower()
            if not col_name:
                continue
            if col_name.lower() in protected:
                continue
            if udt_name in ("geometry", "st_geometry"):
                continue
            if udt_name in supported_udt:
                continue

            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ALTER COLUMN {} TYPE text USING {}::text").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(col_name),
                    sql.Identifier(col_name),
                )
            )
            converted.append(f"{col_name}:{udt_name}->text")

        if converted:
            conn.commit()
        else:
            conn.rollback()
        cur.close()
        return converted
    finally:
        conn.close()


def _list_columns_with_types(info: dict, schema_name: str, table_name: str):
    out = []
    conn = _connect_postgis(info)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table_name),
        )
        rows = cur.fetchall() or []
        for row in rows:
            col_name = str(row[0] or "")
            udt_name = str(row[1] or "")
            if col_name:
                out.append(f"{col_name}:{udt_name}")
        cur.close()
    finally:
        conn.close()
    return out


def _is_esri_srid_not_found_error(text: str) -> bool:
    t = (text or "").lower()
    return (
        "error getting spatial references for srid" in t
        or ("spatial references" in t and "srid" in t)
    )


def _is_esri_wkb_range_error(text: str) -> bool:
    t = (text or "").lower()
    return (
        "error converting shape from wkb" in t
        and "valid coordinate range" in t
    )


def _is_register_001050_error(text: str) -> bool:
    t = (text or "").lower()
    return (
        "error 001050" in t
        or "either registered with geodatabase already or cannot open the dataset" in t
    )


def _validate_esri_srid_support(info: dict, st_schema: str, srid: int):
    conn = _connect_postgis(info)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                sql.SQL(
                    "SELECT {}.st_geomfromwkb(decode('010100000000000000000000000000000000000000','hex'), %s) IS NOT NULL"
                ).format(
                    sql.Identifier(st_schema),
                ),
                (int(srid),),
            )
            cur.fetchone()
            conn.rollback()
            cur.close()
            return True, ""
        except Exception as e:
            conn.rollback()
            cur.close()
            msg = str(e)
            if _is_esri_srid_not_found_error(msg):
                return False, msg
            raise
    finally:
        conn.close()


def _ensure_st_geometry_shape_column(
    info: dict,
    schema_name: str,
    table_name: str,
    st_schema: str,
    srid: int,
):
    conn = _connect_postgis(info)
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND column_name = 'shape'
            LIMIT 1
            """,
            (schema_name, table_name),
        )
        shape_row = cur.fetchone()
        shape_udt = (shape_row[0] or "").lower() if shape_row else ""
        if shape_udt == "st_geometry":
            cur.close()
            conn.commit()
            return ""

        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table_name),
        )
        col_rows = cur.fetchall() or []
        col_map = {
            str(r[0] or "").lower(): str(r[1] or "").lower()
            for r in col_rows
            if r and r[0]
        }

        # Bazi akislarda ogr2ogr kolonu dogrudan st_geometry olarak acabilir.
        if col_map.get("wkb_geometry") == "st_geometry":
            if "shape" not in col_map:
                cur.execute(
                    sql.SQL("ALTER TABLE {}.{} RENAME COLUMN {} TO {}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name),
                        sql.Identifier("wkb_geometry"),
                        sql.Identifier("shape"),
                    )
                )
            conn.commit()
            cur.close()
            return "wkb_geometry:st_geometry -> shape:st_geometry (dogrudan) uygulandi."

        if col_map.get("geom") == "st_geometry":
            if "shape" not in col_map:
                cur.execute(
                    sql.SQL("ALTER TABLE {}.{} RENAME COLUMN {} TO {}").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name),
                        sql.Identifier("geom"),
                        sql.Identifier("shape"),
                    )
                )
            conn.commit()
            cur.close()
            return "geom:st_geometry -> shape:st_geometry (dogrudan) uygulandi."

        source_col = None
        for cand in ("wkb_geometry", "shape", "geom"):
            if col_map.get(cand) == "bytea":
                source_col = cand
                break

        if not source_col:
            raise RuntimeError(
                "Beklenen bytea geometri kolonu bulunamadi "
                f"(kolonlar={', '.join([f'{k}:{v}' for k, v in col_map.items()])})."
            )

        if source_col == "shape":
            tmp_col = "__dbm_shape_stg"
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} DROP COLUMN IF EXISTS {}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(tmp_col),
                )
            )
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ADD COLUMN {} {}.st_geometry").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(tmp_col),
                    sql.Identifier(st_schema),
                )
            )
            cur.execute(
                sql.SQL(
                    "UPDATE {}.{} SET {} = {}.st_geomfromwkb({}, %s) WHERE {} IS NOT NULL"
                ).format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(tmp_col),
                    sql.Identifier(st_schema),
                    sql.Identifier(source_col),
                    sql.Identifier(source_col),
                ),
                (int(srid),),
            )
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} DROP COLUMN {}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier("shape"),
                )
            )
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} RENAME COLUMN {} TO {}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(tmp_col),
                    sql.Identifier("shape"),
                )
            )
        else:
            cur.execute(
                sql.SQL(
                    "ALTER TABLE {}.{} ADD COLUMN IF NOT EXISTS {} {}.st_geometry"
                ).format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier("shape"),
                    sql.Identifier(st_schema),
                )
            )
            cur.execute(
                sql.SQL(
                    "UPDATE {}.{} SET {} = {}.st_geomfromwkb({}, %s) WHERE {} IS NOT NULL"
                ).format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier("shape"),
                    sql.Identifier(st_schema),
                    sql.Identifier(source_col),
                    sql.Identifier(source_col),
                ),
                (int(srid),),
            )
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} DROP COLUMN {}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name),
                    sql.Identifier(source_col),
                )
            )

        conn.commit()
        cur.close()
        return f"{source_col}:bytea -> shape:st_geometry donusumu uygulandi."
    finally:
        conn.close()


@router.post("/import-vector-esri-db-stg")
def import_vector_to_esri_db_stg(req: ImportVectorToEsriDbReqV2):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    file_path = (req.file_path or "").strip()
    manual_epsg = req.manual_epsg

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path bos olamaz")
    if manual_epsg is not None:
        try:
            manual_epsg = int(manual_epsg)
            if manual_epsg <= 0:
                raise ValueError
        except Exception:
            return {
                "ok": False,
                "message": "Manuel EPSG kodu gecersiz.",
                "debug": str(req.manual_epsg),
            }

    src = Path(file_path)
    if not src.exists():
        return {"ok": False, "message": "Dosya bulunamadi.", "debug": file_path}
    if not src.is_file():
        return {"ok": False, "message": "Gecersiz dosya yolu.", "debug": file_path}

    ext = src.suffix.lower()
    if ext not in (".gml", ".xml", ".shp"):
        return {
            "ok": False,
            "message": "Desteklenmeyen dosya formati. (gml/shp/xml)",
            "debug": f"ext={ext}",
        }

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    ogr2ogr_exe = _ensure_ogr2ogr()
    if not ogr2ogr_exe:
        return {
            "ok": False,
            "message": "Aktarim icin 'ogr2ogr' bulunamadi.",
            "debug": "GDAL/ogr2ogr kurulu degil veya PATH icinde degil.",
        }

    gdal_env = _build_gdal_env(ogr2ogr_exe)
    layer_names = []
    discovery_notes = []
    if ext in (".gml", ".xml"):
        layer_names, discovery_notes = _resolve_vector_layers(ogr2ogr_exe, src, gdal_env)
    else:
        layer_names = [src.stem]

    import_jobs, is_multi_gml = _build_import_jobs(src, ext, layer_names)
    for job in import_jobs:
        if not job.get("table_name"):
            job["table_name"] = _sanitize_table_name(job.get("source_layer") or src.stem)

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
                    "message": "Secilen sema bulunamadi.",
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
                    "message": "Secilen veritabaninda ST_Geometry tipi bulunamadi.",
                    "debug": "Esri ST_Geometry kurulumunu kontrol edin.",
                }
            st_schema = row[0]

            existing = []
            for job in import_jobs:
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                    LIMIT 1
                    """,
                    (schema_name, job["table_name"]),
                )
                if cur.fetchone():
                    existing.append(job["table_name"])

            cur.close()
            if existing:
                return {
                    "ok": False,
                    "message": "Bazi hedef tablolar zaten mevcut. Once silin veya farkli adla tekrar deneyin.",
                    "debug": ", ".join([f"{schema_name}.{t}" for t in existing[:30]]),
                }
        finally:
            conn.close()
    except Exception as e:
        return {"ok": False, "message": "Sema kontrolu basarisiz.", "debug": str(e)}

    pg_dsn = (
        f"PG:host={info.get('Host')} "
        f"port={info.get('Port')} "
        f"dbname={info.get('Database')} "
        f"user={info.get('UserName')} "
        f"password={info.get('Password') or ''}"
    )

    imported = []
    srs_fallback_tables = []
    promoted_multi_tables = []
    for job in import_jobs:
        table_name = job["table_name"]
        layer_name = job.get("source_layer")

        source_srs, srs_notes = _detect_source_srs(ogr2ogr_exe, src, layer_name, gdal_env)
        source_srs = (source_srs or "").strip()
        detected_srs = source_srs
        used_manual_epsg = False
        # Kullanici manuel EPSG girdiyse her zaman kaynak tespitini override et.
        if manual_epsg is not None:
            epsg_code = int(manual_epsg)
            detected_srs = f"EPSG:{epsg_code}"
            used_manual_epsg = True
        else:
            if not detected_srs:
                return {
                    "ok": False,
                    "message": "Koordinat sistemi (EPSG) tespit edilemedi. Lutfen EPSG kodu giriniz.",
                    "debug": f"layer={layer_name or '<varsayilan>'} tablo={schema_name}.{table_name}",
                    "requires_epsg": True,
                }
            epsg_code = _extract_epsg_code(detected_srs)
            if epsg_code is None:
                return {
                    "ok": False,
                    "message": "EPSG kodu tespit edilemedi. Lutfen EPSG kodu giriniz.",
                    "debug": f"layer={layer_name or '<varsayilan>'} srs={detected_srs}",
                    "requires_epsg": True,
                }

        try:
            srid_ok, srid_debug = _validate_esri_srid_support(info, st_schema, epsg_code)
        except Exception as e:
            return {
                "ok": False,
                "message": "EPSG dogrulama kontrolu basarisiz.",
                "debug": str(e),
            }
        if not srid_ok:
            src_txt = (
                "kullanicinin girdigi EPSG"
                if manual_epsg is not None
                else "kaynak veriden tespit edilen EPSG"
            )
            return {
                "ok": False,
                "message": (
                    f"ST_Geometry bu SRID'i desteklemiyor (EPSG:{epsg_code}). "
                    "Lutfen farkli bir EPSG kodu giriniz."
                ),
                "debug": f"{src_txt}={epsg_code}\n{srid_debug}",
                "requires_epsg": True,
            }

        cmd_srs = detected_srs
        try:
            db_defs = _load_srs_defs_from_db(info, [epsg_code])
            cmd_srs = db_defs.get(epsg_code) or detected_srs
        except Exception as e:
            srs_notes.append(f"spatial_ref_sys sorgulanamadi: {e}")

        geom_arcgis_type = _detect_arcgis_geom_type(ogr2ogr_exe, src, layer_name, gdal_env)
        if not geom_arcgis_type:
            geom_arcgis_type = "POLYGON"

        column_types = f"wkb_geometry={st_schema}.st_geometry"
        cmd = [ogr2ogr_exe, "-f", "PostgreSQL", pg_dsn, str(src)]
        if is_multi_gml and layer_name:
            cmd.append(layer_name)
        cmd += [
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
                timeout=900 if is_multi_gml else 600,
                check=False,
                env=gdal_env,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "message": "Aktarim zaman asimina ugradi.",
                "debug": f"ogr2ogr timeout | tablo={schema_name}.{table_name}",
            }
        except Exception as e:
            return {
                "ok": False,
                "message": "Aktarim komutu calistirilamadi.",
                "debug": str(e),
            }

        proc_text = (proc.stderr or proc.stdout or "").strip()
        if proc.returncode != 0 and _is_srs_processing_error(proc_text):
            retry_cmd = _remove_a_srs_from_cmd(cmd)
            proc_retry = subprocess.run(
                retry_cmd,
                capture_output=True,
                text=True,
                timeout=900 if is_multi_gml else 600,
                check=False,
                env=gdal_env,
            )
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
            retry_cmd = _add_promote_to_multi_to_cmd(cmd)
            proc_retry = subprocess.run(
                retry_cmd,
                capture_output=True,
                text=True,
                timeout=900 if is_multi_gml else 600,
                check=False,
                env=gdal_env,
            )
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
            return {
                "ok": False,
                "message": "Vektor veri ESRI DB'ye aktarilamadi.",
                "debug": f"tablo={schema_name}.{table_name}\n{proc_text[:2500]}",
            }

        row_count = None
        shape_conversion_note = ""
        try:
            conn = _connect_postgis(info)
            try:
                cur = conn.cursor()

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
                "message": "Aktarim sonrasi kontrol basarisiz.",
                "debug": str(e),
            }

        try:
            shape_conversion_note = _ensure_st_geometry_shape_column(
                info=info,
                schema_name=schema_name,
                table_name=table_name,
                st_schema=st_schema,
                srid=epsg_code,
            )
        except Exception as e:
            try:
                _drop_table_if_exists(info, schema_name, table_name)
            except Exception:
                pass
            if _is_esri_srid_not_found_error(str(e)):
                return {
                    "ok": False,
                    "message": (
                        f"ST_Geometry bu SRID'i desteklemiyor (EPSG:{epsg_code}). "
                        "Lutfen farkli bir EPSG kodu giriniz."
                    ),
                    "debug": str(e),
                    "requires_epsg": True,
                }
            if _is_esri_wkb_range_error(str(e)):
                dbg = str(e)
                if source_srs:
                    dbg += f"\nkaynak_srs={source_srs}"
                else:
                    dbg += "\nkaynak_srs=tespit_edilemedi (SHP icin .prj dosyasini kontrol edin)"
                dbg += f"\nhedef_epsg={epsg_code}"
                if manual_epsg is not None:
                    msg = (
                        f"Secilen EPSG ({epsg_code}) koordinat degerleri ile uyusmuyor. "
                        "Lutfen dogru EPSG kodunu kullanin."
                    )
                    return {
                        "ok": False,
                        "message": msg,
                        "debug": dbg,
                        "requires_epsg": False,
                    }
                return {
                    "ok": False,
                    "message": (
                        f"WKB -> ST_Geometry donusumunde SRID/EPSG uyumsuzlugu olustu (EPSG:{epsg_code}). "
                        "Lutfen farkli bir EPSG kodu giriniz."
                    ),
                    "debug": dbg,
                    "requires_epsg": True,
                }
            return {
                "ok": False,
                "message": "ST_Geometry kolon donusumu basarisiz.",
                "debug": str(e),
            }

        try:
            objectid_field, oid_note = _pick_or_create_objectid_field(
                info, schema_name, table_name
            )
        except Exception as e:
            return {
                "ok": False,
                "message": "Register icin objectid alani hazirlanamadi.",
                "debug": str(e),
            }

        try:
            converted_cols = _normalize_columns_for_esri_register(
                info,
                schema_name,
                table_name,
                protected_cols={objectid_field, "shape"},
            )
        except Exception as e:
            return {
                "ok": False,
                "message": "Register oncesi alan tipi kontrolu basarisiz.",
                "debug": str(e),
            }

        register_attempts = []

        ok, reg_debug, _ = _register_with_geodatabase(
            info=info,
            schema_name=schema_name,
            dataset_name=table_name,
            geometry_column="shape",
            geom_type=geom_arcgis_type,
            srid=epsg_code,
            objectid_field=objectid_field,
        )
        register_attempts.append(
            f"attempt#1 objectid+shape => {'OK' if ok else 'FAIL'} | {reg_debug or ''}".strip()
        )
        if not ok and "invalid field type" in (reg_debug or "").lower():
            try:
                oid_field, _ = _pick_or_create_objectid_field(info, schema_name, table_name)
                _normalize_columns_for_esri_register(
                    info,
                    schema_name,
                    table_name,
                    protected_cols={oid_field, "shape"},
                )
                ok, reg_debug, _ = _register_with_geodatabase(
                    info=info,
                    schema_name=schema_name,
                    dataset_name=table_name,
                    geometry_column="shape",
                    geom_type=geom_arcgis_type,
                    srid=epsg_code,
                    objectid_field=oid_field,
                )
                register_attempts.append(
                    f"attempt#2 normalize+objectid+shape => {'OK' if ok else 'FAIL'} | {reg_debug or ''}".strip()
                )
            except Exception as e:
                reg_debug = f"{reg_debug}\n{e}".strip()
                register_attempts.append(
                    f"attempt#2 normalize+objectid+shape => FAIL | {e}".strip()
                )
        # createfeatureesri akisinda oldugu gibi objectid parametresi vermeden register
        # denemesi bu hata sinifi icin daha stabil calisiyor.
        if not ok:
            try:
                ok, reg_debug, _ = _register_with_geodatabase(
                    info=info,
                    schema_name=schema_name,
                    dataset_name=table_name,
                    geometry_column="shape",
                    geom_type=geom_arcgis_type,
                    srid=epsg_code,
                    objectid_field=None,
                )
                register_attempts.append(
                    f"attempt#3 shape-only (objectid yok) => {'OK' if ok else 'FAIL'} | {reg_debug or ''}".strip()
                )
            except Exception as e:
                reg_debug = f"{reg_debug}\n{e}".strip()
                register_attempts.append(
                    f"attempt#3 shape-only (objectid yok) => FAIL | {e}".strip()
                )
        # Bazı ArcMap/DB sürümlerinde shape/objectid parametreleri ile register başarısız
        # olurken "dataset-only register" başarılı olabiliyor.
        if not ok:
            try:
                ok, reg_debug, _ = _register_with_geodatabase(
                    info=info,
                    schema_name=schema_name,
                    dataset_name=table_name,
                    geometry_column=None,
                    geom_type=None,
                    srid=None,
                    objectid_field=None,
                )
                register_attempts.append(
                    f"attempt#4 dataset-only register => {'OK' if ok else 'FAIL'} | {reg_debug or ''}".strip()
                )
            except Exception as e:
                reg_debug = f"{reg_debug}\n{e}".strip()
                register_attempts.append(
                    f"attempt#4 dataset-only register => FAIL | {e}".strip()
                )
        # 001050 sinifinda ArcGIS tarafinda dataset acilabiliyorsa tabloyu silmeyelim;
        # en azindan kullaniciya veriyi koruyarak ayristirma imkani verelim.
        if (not ok) and _is_register_001050_error(reg_debug or ""):
            try:
                verify_ok, verify_debug, _ = _register_with_geodatabase(
                    info=info,
                    schema_name=schema_name,
                    dataset_name=table_name,
                    geometry_column=None,
                    geom_type=None,
                    srid=None,
                    objectid_field=None,
                    skip_register=True,
                )
                register_attempts.append(
                    f"attempt#5 skip-register verify => {'OK' if verify_ok else 'FAIL'} | {verify_debug or ''}".strip()
                )
                if verify_ok:
                    ok = True
                    reg_debug = (
                        (reg_debug or "")
                        + "\nRegister 001050 alindi; dataset ArcGIS tarafinda acilabildigi icin mevcut durum kabul edildi."
                    ).strip()
            except Exception as e:
                register_attempts.append(f"attempt#5 skip-register verify => FAIL | {e}".strip())
        if not ok:
            try:
                col_debug = _list_columns_with_types(info, schema_name, table_name)
                reg_debug = (
                    f"{reg_debug}\nobjectid_field={objectid_field}\n"
                    f"columns={', '.join(col_debug[:120])}"
                ).strip()
            except Exception:
                pass
            try:
                if register_attempts:
                    reg_debug = (
                        f"{reg_debug}\nregister_attempts:\n- "
                        + "\n- ".join(register_attempts)
                    ).strip()
            except Exception:
                pass
            try:
                _drop_table_if_exists(info, schema_name, table_name)
            except Exception:
                pass
            return {
                "ok": False,
                "message": "Veri seti olusturuldu ancak geodatabase kaydi tamamlanamadi.",
                "debug": reg_debug,
            }

        imported.append(
            {
                "table": table_name,
                "source_layer": layer_name,
                "count": row_count,
                "srs": detected_srs,
                "srs_applied": (
                    False
                    if f"{schema_name}.{table_name}" in srs_fallback_tables
                    else True
                ),
                "used_manual_epsg": used_manual_epsg,
                "objectid_field": objectid_field,
                "objectid_note": oid_note,
                "shape_conversion_note": shape_conversion_note,
                "converted_columns": converted_cols,
                "promoted_to_multi": (
                    True
                    if f"{schema_name}.{table_name}" in promoted_multi_tables
                    else False
                ),
            }
        )

    if not imported:
        return {
            "ok": False,
            "message": "Aktarim tamamlandi fakat hedef tablolar olusmadi.",
            "debug": src.name,
        }

    if len(imported) == 1:
        it = imported[0]
        msg = f"'{src.name}' veri seti '{schema_name}.{it['table']}' tablosuna ESRI DB icin aktarildi."
        if it.get("count") is not None:
            msg += f"\nKayit sayisi: {it['count']}"
        if it.get("srs"):
            msg += f"\nKoordinat sistemi: {it['srs']}"
        if not it.get("srs_applied", True):
            msg += "\nNot: EPSG tanimi PROJ icinde bulunamadigi icin CRS metadata yedek modda islendi."
        if it.get("used_manual_epsg", False):
            msg += "\nNot: Koordinat sistemi kullanicinin girdigi EPSG kodu ile atandi."
        if it.get("objectid_note"):
            msg += f"\nNot: {it.get('objectid_note')}"
        if it.get("shape_conversion_note"):
            msg += f"\nNot: {it.get('shape_conversion_note')}"
        if it.get("converted_columns"):
            msg += "\nNot: Register uyumlulugu icin alan tipleri donusturuldu."
        if it.get("promoted_to_multi", False):
            msg += "\nNot: Geometri tip uyumsuzlugu nedeniyle hedef geometri tipi multi olarak olusturuldu."
        return {
            "ok": True,
            "message": msg,
            "data": {
                "schema": schema_name,
                "table": it["table"],
                "count": it.get("count"),
                "srs": it.get("srs"),
                "tables": imported,
                "notes": discovery_notes,
            },
        }

    msg = f"'{src.name}' dosyasindaki {len(imported)} katman ESRI DB'ye aktarildi."
    lines = []
    for it in imported[:20]:
        layer_txt = f" (layer: {it['source_layer']})" if it.get("source_layer") else ""
        srs_txt = f" | {it['srs']}" if it.get("srs") else ""
        mode_txt = " | srs=ok" if it.get("srs_applied", True) else " | srs=yedek"
        manual_txt = " | srs=manuel" if it.get("used_manual_epsg", False) else ""
        conv_txt = " | field=cast" if it.get("converted_columns") else ""
        geom_txt = " | geom=multi" if it.get("promoted_to_multi", False) else ""
        lines.append(
            f"- {schema_name}.{it['table']}{layer_txt}{srs_txt}{mode_txt}{manual_txt}{conv_txt}{geom_txt} -> {it.get('count', 'bilinmiyor')} kayit"
        )
    if lines:
        msg += "\n" + "\n".join(lines)
    if discovery_notes:
        msg += "\nNot: " + "; ".join(discovery_notes[:3])

    return {
        "ok": True,
        "message": msg,
        "data": {"schema": schema_name, "tables": imported},
    }

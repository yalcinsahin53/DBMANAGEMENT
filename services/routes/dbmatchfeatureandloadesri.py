from pathlib import Path
import re
import subprocess
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import psycopg2
from psycopg2 import sql

from core.storage import open_db
from services.routes.createpostgisschema import (
    _build_gdal_env,
    _dbmatch_collect_vector_structure,
    _dbmatch_drop_table_if_exists,
    _dbmatch_get_target_srid,
    _dbmatch_normalize_name,
    _detect_source_srs,
    _ensure_ogr2ogr,
    _extract_epsg_code,
    _is_srs_processing_error,
    _remove_a_srs_from_cmd,
)


router = APIRouter(tags=["db-matchfeatureandload-esri"])


class DbMatchLayerMapReq(BaseModel):
    source_layer: str
    target_table: str
    field_mapping: dict[str, str] = Field(default_factory=dict)


class DbMatchLoadEsriReq(BaseModel):
    conn_name: str
    schema_name: str
    file_path: str
    layer_mappings: list[DbMatchLayerMapReq] = Field(default_factory=list)


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
    s = _normalize_db_type(v)
    return s in (
        "esri geodatabase",
        "enterprise geodatabase",
        "esri enterprise geodatabase",
        "esri",
    )


def _validate_esri_conn(conn_name: str):
    info = _get_db_connection_by_name(conn_name)
    if not info:
        return None, {
            "ok": False,
            "message": "Baglanti bulunamadi.",
            "debug": conn_name,
        }
    if not _is_esri_dbtype(str(info.get("DbType") or "")):
        return None, {
            "ok": False,
            "message": "Secilen baglanti Esri Geodatabase degil.",
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
    return row[0] if row and row[0] else None


def _list_schema_tables(info: dict, schema_name: str):
    conn = _connect_db(info)
    try:
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
        rows = [r[0] for r in cur.fetchall() if r and r[0]]
        cur.close()
        return rows
    finally:
        conn.close()


def _list_table_columns(info: dict, schema_name: str, table_name: str):
    conn = _connect_db(info)
    try:
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
        out = []
        for row in cur.fetchall() or []:
            col_name, data_type, udt_name, is_nullable, _ = row
            udt_l = (udt_name or "").strip().lower()
            is_geom = udt_l in ("st_geometry", "geometry")
            out.append(
                {
                    "name": col_name,
                    "data_type": data_type,
                    "udt_name": udt_name,
                    "is_nullable": is_nullable,
                    "is_geometry": bool(is_geom),
                }
            )
        cur.close()
        return out
    finally:
        conn.close()


def _get_target_srid_for_any_geometry(
    cur,
    schema_name: str,
    table_name: str,
    geom_column: str | None,
    geom_udt: str | None,
    st_schema: str | None,
):
    if not geom_column:
        return None

    udt = (geom_udt or "").strip().lower()

    if udt == "geometry":
        return _dbmatch_get_target_srid(cur, schema_name, table_name, geom_column)

    if udt != "st_geometry" or not st_schema:
        return None

    # st_geometry: once mevcut kayitlardan SRID okumayi dene.
    try:
        cur.execute(
            sql.SQL(
                "SELECT {}.st_srid({}) FROM {}.{} WHERE {} IS NOT NULL LIMIT 1"
            ).format(
                sql.Identifier(st_schema),
                sql.Identifier(geom_column),
                sql.Identifier(schema_name),
                sql.Identifier(table_name),
                sql.Identifier(geom_column),
            )
        )
        row = cur.fetchone()
        if row and row[0] is not None and int(row[0]) > 0:
            return int(row[0])
    except Exception:
        pass

    return None


@router.get("/dbmatchesri-vector-structure")
def dbmatchesri_vector_structure(file_path: str):
    file_path = (file_path or "").strip()
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path bos olamaz")

    src = Path(file_path)
    if not src.exists():
        return {"ok": False, "message": "Dosya bulunamadi.", "debug": file_path}
    if not src.is_file():
        return {"ok": False, "message": "Gecersiz dosya yolu.", "debug": file_path}

    ogr2ogr_exe = _ensure_ogr2ogr()
    if not ogr2ogr_exe:
        return {
            "ok": False,
            "message": "Katman analizi icin 'ogr2ogr/ogrinfo' bulunamadi.",
            "debug": "GDAL/ogr2ogr kurulu degil veya PATH icinde degil.",
        }

    try:
        gdal_env = _build_gdal_env(ogr2ogr_exe)
        layers, notes = _dbmatch_collect_vector_structure(ogr2ogr_exe, src, gdal_env)
        if not layers:
            return {
                "ok": False,
                "message": "Dosyada okunabilir katman bulunamadi.",
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
            "message": "Katman analizi basarisiz.",
            "debug": str(e),
        }


@router.get("/dbmatchesri-schema-tables")
def dbmatchesri_schema_tables(conn_name: str, schema_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        tables = _list_schema_tables(info, schema_name)
        return {"ok": True, "message": "", "data": tables}
    except Exception as e:
        return {
            "ok": False,
            "message": "Tablo listesi alinamadi.",
            "data": [],
            "debug": str(e),
        }


@router.get("/dbmatchesri-table-columns")
def dbmatchesri_table_columns(conn_name: str, schema_name: str, table_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()
    table_name = (table_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not table_name:
        raise HTTPException(status_code=400, detail="table_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        cols = _list_table_columns(info, schema_name, table_name)
        if not cols:
            return {
                "ok": False,
                "message": "Secilen tabloda kolon bulunamadi.",
                "data": [],
                "debug": f"{schema_name}.{table_name}",
            }
        return {"ok": True, "message": "", "data": cols}
    except Exception as e:
        return {
            "ok": False,
            "message": "Kolon listesi alinamadi.",
            "data": [],
            "debug": str(e),
        }


@router.post("/dbmatch-load-esri")
def dbmatch_load_esri(req: DbMatchLoadEsriReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    file_path = (req.file_path or "").strip()
    layer_mappings = req.layer_mappings or []

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path bos olamaz")
    if not layer_mappings:
        return {"ok": False, "message": "Aktarim icin katman eslestirmesi bulunamadi.", "data": []}

    src = Path(file_path)
    if not src.exists():
        return {"ok": False, "message": "Dosya bulunamadi.", "debug": file_path}
    if not src.is_file():
        return {"ok": False, "message": "Gecersiz dosya yolu.", "debug": file_path}

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
            return {
                "ok": False,
                "message": "Secilen sema bulunamadi.",
                "debug": f"schema_name={schema_name}",
            }

        st_schema = _find_st_geometry_schema(cur)

        for lm in layer_mappings:
            source_layer = (lm.source_layer or "").strip()
            target_table = (lm.target_table or "").strip()
            raw_mapping = dict(lm.field_mapping or {})
            tmp_table = f"_tmp_dbmatchesri_{uuid.uuid4().hex[:12]}"

            if not target_table:
                fail_count += 1
                results.append(
                    {
                        "layer": source_layer,
                        "table": target_table,
                        "ok": False,
                        "message": "Hedef tablo secilmedi.",
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
                    raise Exception(f"Hedef tablo bulunamadi: {schema_name}.{target_table}")

                target_attr_cols = {}
                target_geom_col = None
                target_geom_udt = None
                for row in target_rows:
                    col_name = row[0]
                    udt_name = row[2]
                    udt_l = (udt_name or "").strip().lower()
                    is_geom = udt_l in ("geometry", "st_geometry")
                    if is_geom and not target_geom_col:
                        target_geom_col = col_name
                        target_geom_udt = udt_l
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
                        "Ayni hedef kolona birden fazla kaynak alan eslestirildi: "
                        + ", ".join(sorted(set(duplicate_targets)))
                    )
                if invalid_targets:
                    raise Exception(
                        "Tabloda bulunmayan hedef kolonlar secildi: "
                        + ", ".join(sorted(set(invalid_targets)))
                    )
                if not mapping and not target_geom_col:
                    raise Exception("Ne alan eslestirmesi ne de hedef geometri kolonu bulundu.")

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

                target_srid = _get_target_srid_for_any_geometry(
                    cur,
                    schema_name,
                    target_table,
                    target_geom_col,
                    target_geom_udt,
                    st_schema,
                )

                if not target_srid:
                    detected_epsg = _extract_epsg_code(detected_srs)
                    if detected_epsg:
                        target_srid = int(detected_epsg)

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
                    "GEOM_TYPE=BYTEA",
                    "-lco",
                    "FID=id",
                    "-lco",
                    "PRECISION=NO",
                    "-skipfailures",
                ]
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
                    raise Exception(f"ogr2ogr calistirilamadi: {e}")

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
                        raise Exception(f"ogr2ogr retry calistirilamadi: {e}")

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
                    SELECT column_name, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema_name, tmp_table),
                )
                tmp_rows = cur.fetchall() or []
                tmp_cols = [r[0] for r in tmp_rows if r and r[0]]
                tmp_udt = {str(r[0] or ""): str(r[1] or "").lower() for r in tmp_rows if r and r[0]}
                if not tmp_cols:
                    raise Exception("Gecici tabloda kolon bulunamadi.")

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
                select_params: list[object] = []

                tmp_geom_col = _resolve_tmp_col("geom_tmp") or _resolve_tmp_col("wkb_geometry")
                if target_geom_col and tmp_geom_col:
                    geom_udt = (target_geom_udt or "").lower()
                    tmp_geom_udt = (tmp_udt.get(tmp_geom_col) or "").lower()

                    if not target_srid:
                        raise Exception(
                            "Hedef geometri kolonu icin SRID belirlenemedi. "
                            "Kaynak katmanda EPSG/SRS bilgisi olmali veya hedef tabloda SRID tanimli olmali."
                        )

                    insert_cols.append(target_geom_col)
                    if geom_udt == "st_geometry":
                        if not st_schema:
                            raise Exception("ST_Geometry semasi bulunamadi.")
                        if tmp_geom_udt == "bytea":
                            select_exprs.append(
                                sql.SQL("{}.st_geomfromwkb(t.{}, %s)").format(
                                    sql.Identifier(st_schema),
                                    sql.Identifier(tmp_geom_col),
                                )
                            )
                            select_params.append(int(target_srid))
                        else:
                            select_exprs.append(
                                sql.SQL("{}.st_geomfromwkb(ST_AsBinary(t.{}), %s)").format(
                                    sql.Identifier(st_schema),
                                    sql.Identifier(tmp_geom_col),
                                )
                            )
                            select_params.append(int(target_srid))
                    elif geom_udt == "geometry":
                        if tmp_geom_udt == "bytea":
                            select_exprs.append(
                                sql.SQL("ST_GeomFromWKB(t.{}, %s)").format(
                                    sql.Identifier(tmp_geom_col)
                                )
                            )
                            select_params.append(int(target_srid))
                        else:
                            select_exprs.append(sql.SQL("t.{}").format(sql.Identifier(tmp_geom_col)))
                    else:
                        raise Exception(
                            f"Desteklenmeyen hedef geometri tipi: {target_geom_udt or '-'}"
                        )

                missing_sources = []
                for src_name, tgt_name in mapping.items():
                    src_col = _resolve_tmp_col(src_name)
                    if not src_col:
                        missing_sources.append(src_name)
                        continue
                    insert_cols.append(tgt_name)
                    select_exprs.append(sql.SQL("t.{}").format(sql.Identifier(src_col)))

                if missing_sources:
                    global_notes.append(
                        f"{source_layer or target_table}: bazi kaynak alanlar gecici tabloda bulunamadi -> "
                        + ", ".join(missing_sources[:20])
                    )

                if not insert_cols:
                    raise Exception("Aktarilacak gecerli kolon bulunamadi.")

                query = sql.SQL("INSERT INTO {}.{} ({}) SELECT {} FROM {}.{} t").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(target_table),
                    sql.SQL(", ").join([sql.Identifier(c) for c in insert_cols]),
                    sql.SQL(", ").join(select_exprs),
                    sql.Identifier(schema_name),
                    sql.Identifier(tmp_table),
                )
                if select_params:
                    cur.execute(query, tuple(select_params))
                else:
                    cur.execute(query)

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
                "message": "Hicbir katman aktarilamadi.",
                "data": {"results": results, "success_count": success_count, "failed_count": fail_count},
                "debug": "\n".join(global_notes[:30]),
            }

        msg = f"{success_count} katman basariyla aktarildi."
        if fail_count > 0:
            msg += f" {fail_count} katman aktariminda hata var."

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
            "message": "Esri DB esleme ile aktarim islemi basarisiz.",
            "data": {"results": results, "success_count": success_count, "failed_count": fail_count},
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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import re
import unicodedata

import psycopg2
from psycopg2 import sql

from core.storage import open_db
from services.routes.createesrifeature import (
    _is_esri_addfield_supported_type,
    _register_with_geodatabase,
)


router = APIRouter(tags=["db-createandeditfield-esri"])

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FieldSpecReq(BaseModel):
    name: str
    alias: str = ""
    data_type: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True


class AddFieldReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_name: str
    field: FieldSpecReq


class UpdateFieldReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_name: str
    old_field_name: str
    field: FieldSpecReq


class DeleteFieldReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_name: str
    field_name: str


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
            return None, "Karakter sayisi 1-10485760 arasinda olmali."
        return f"varchar({ln})", ""

    if t == "char":
        ln = 1 if length is None else int(length)
        if ln < 1 or ln > 10485760:
            return None, "Karakter sayisi 1-10485760 arasinda olmali."
        return f"char({ln})", ""

    if t == "numeric":
        p = None if precision is None else int(precision)
        s = None if scale is None else int(scale)
        if s is not None and p is None:
            return None, "Scale girildiyse precision da girilmelidir."
        if p is None:
            return "numeric", ""
        if p < 1 or p > 1000:
            return None, "Precision 1-1000 arasinda olmali."
        if s is None:
            return f"numeric({p})", ""
        if s < 0:
            return None, "Scale 0 veya daha buyuk olmali."
        if s > p:
            return None, "Scale precision degerinden buyuk olamaz."
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


def _parse_alias_from_comment(comment_txt: str | None) -> str:
    txt = (comment_txt or "").strip()
    if not txt:
        return ""
    if txt.lower().startswith("alias="):
        return txt[6:].strip()
    return txt


def _dataset_exists(cur, schema_name: str, dataset_name: str) -> bool:
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
    return bool(cur.fetchone())


def _list_fields(cur, schema_name: str, dataset_name: str) -> list[dict]:
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY'
        """,
        (schema_name, dataset_name),
    )
    pk_cols = {r[0] for r in cur.fetchall() if r and r[0]}

    cur.execute(
        """
        SELECT
            c.column_name,
            c.ordinal_position,
            c.data_type,
            c.udt_name,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.is_nullable,
            c.is_identity,
            d.description AS comment_txt
        FROM information_schema.columns c
        LEFT JOIN pg_catalog.pg_namespace n
          ON n.nspname = c.table_schema
        LEFT JOIN pg_catalog.pg_class cls
          ON cls.relnamespace = n.oid
         AND cls.relname = c.table_name
        LEFT JOIN pg_catalog.pg_description d
          ON d.objoid = cls.oid
         AND d.objsubid = c.ordinal_position
        WHERE c.table_schema = %s
          AND c.table_name = %s
        ORDER BY c.ordinal_position
        """,
        (schema_name, dataset_name),
    )
    rows = cur.fetchall()
    out = []
    for r in rows:
        # Bazi ortamlarda satir tuple uzunlugu beklenenden kisa gelebiliyor.
        # Bu nedenle indeks erisimi yerine pad+unpack ile guvenli okuyoruz.
        row = tuple(list(r) + [None] * 10)[:10]
        (
            col_name,
            _ordinal_position,
            data_type_raw,
            udt_name_raw,
            char_len,
            num_precision,
            num_scale,
            is_nullable_raw,
            is_identity_raw,
            comment_txt,
        ) = row

        if not col_name:
            continue

        data_type = (data_type_raw or "").strip().lower()
        udt_name = (udt_name_raw or "").strip().lower()
        is_geom = udt_name in ("geometry", "st_geometry")
        type_key = data_type
        if is_geom:
            type_key = "geometry"
        elif data_type == "character varying":
            type_key = "varchar"
        elif data_type == "character":
            type_key = "char"
        elif data_type == "timestamp without time zone":
            type_key = "timestamp"
        elif data_type in ("double precision", "text", "integer", "bigint", "numeric", "boolean", "date"):
            type_key = data_type

        is_pk = col_name in pk_cols
        is_identity = str(is_identity_raw or "").upper() == "YES"
        is_system = is_pk or is_identity or col_name.lower() == "id"
        out.append(
            {
                "name": col_name,
                "alias": _parse_alias_from_comment(comment_txt),
                "data_type": type_key,
                "length": char_len,
                "precision": num_precision,
                "scale": num_scale,
                "nullable": str(is_nullable_raw).upper() == "YES",
                "is_geometry": is_geom,
                "is_primary_key": is_pk,
                "is_identity": is_identity,
                "is_system": is_system,
            }
        )
    return out


def _find_field(fields: list[dict], field_name: str) -> dict | None:
    key = (field_name or "").strip().lower()
    for f in fields:
        if (f.get("name") or "").strip().lower() == key:
            return f
    return None


def _norm_alias_text(value: str | None) -> str:
    txt = str(value or "")
    txt = unicodedata.normalize("NFC", txt)
    return txt.strip()


def _lookup_persisted_alias(
    persisted_aliases: dict | None,
    field_name: str,
) -> str:
    target = (field_name or "").strip().lower()
    if not target:
        return ""
    # 1) Dogrudan eslesme
    for key, val in (persisted_aliases or {}).items():
        if str(key or "").strip().lower() == target:
            return str(val or "")
    # 2) Bazi ArcGIS ortamlari nitelikli ad donebilir (schema.table.field)
    for key, val in (persisted_aliases or {}).items():
        k = str(key or "").strip().lower()
        if not k:
            continue
        if k.split(".")[-1] == target:
            return str(val or "")
    return ""


def _apply_field_aliases_with_arcgis(
    info: dict,
    schema_name: str,
    dataset_name: str,
    field_aliases: dict | None,
) -> tuple[bool, str, dict]:
    cleaned = {}
    for key, val in (field_aliases or {}).items():
        field_name = str(key or "").strip()
        alias_name = str(val or "").strip()
        if not field_name or not alias_name:
            continue
        cleaned[field_name] = alias_name

    if not cleaned:
        return True, "", {}

    ok, reg_debug, reg_payload = _register_with_geodatabase(
        info=info,
        schema_name=schema_name,
        dataset_name=dataset_name,
        geometry_column=None,
        geom_type=None,
        srid=None,
        field_aliases=cleaned,
        skip_register=True,
    )
    payload = reg_payload if isinstance(reg_payload, dict) else {}
    if not ok:
        return False, reg_debug, payload

    persisted = payload.get("persisted_field_aliases") or {}
    mismatches = []
    for field_name, expected_alias in cleaned.items():
        actual_alias = _lookup_persisted_alias(persisted, field_name)
        if _norm_alias_text(actual_alias) != _norm_alias_text(expected_alias):
            mismatches.append(
                f"{field_name} -> beklenen='{expected_alias}', okunan='{actual_alias}'"
            )

    if mismatches:
        return (
            False,
            "Alan alias dogrulamasi basarisiz. " + "; ".join(mismatches),
            payload,
        )

    return True, "", payload


@router.get("/createandeditfieldesri-schemas")
def createandeditfieldesri_schemas(conn_name: str):
    conn_name = (conn_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_db(info)
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
            schemas = [r[0] for r in cur.fetchall() if r and r[0]]
            cur.close()
        finally:
            conn.close()
        return {"ok": True, "data": schemas, "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": "Semalar okunamadi.", "debug": str(e)}


@router.get("/createandeditfieldesri-datasets")
def createandeditfieldesri_datasets(conn_name: str, schema_name: str):
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
        conn = _connect_db(info)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                (schema_name,),
            )
            datasets = [r[0] for r in cur.fetchall() if r and r[0]]
            cur.close()
        finally:
            conn.close()
        return {"ok": True, "data": datasets, "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": "Veri setleri okunamadi.", "debug": str(e)}


@router.get("/createandeditfieldesri-fields")
def createandeditfieldesri_fields(conn_name: str, schema_name: str, dataset_name: str):
    conn_name = (conn_name or "").strip()
    schema_name = (schema_name or "").strip()
    dataset_name = (dataset_name or "").strip()
    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        conn = _connect_db(info)
        try:
            cur = conn.cursor()
            if not _dataset_exists(cur, schema_name, dataset_name):
                return {
                    "ok": False,
                    "data": [],
                    "message": "Secilen veri seti bulunamadi.",
                    "debug": f"{schema_name}.{dataset_name}",
                }
            fields = _list_fields(cur, schema_name, dataset_name)
            cur.close()
        finally:
            conn.close()
        return {"ok": True, "data": fields, "message": ""}
    except Exception as e:
        return {"ok": False, "data": [], "message": "Alanlar okunamadi.", "debug": str(e)}


@router.post("/createandeditfieldesri-add-field")
def createandeditfieldesri_add_field(req: AddFieldReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_name = (req.dataset_name or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name bos olamaz")

    field_name = (req.field.name or "").strip()
    field_alias = (req.field.alias or "").strip()
    if not field_name:
        return {"ok": False, "message": "Alan adi bos olamaz.", "debug": ""}
    if not _is_valid_ident(field_name):
        return {"ok": False, "message": "Alan adi gecersiz.", "debug": field_name}

    if not _is_esri_addfield_supported_type(req.field.data_type):
        return {
            "ok": False,
            "message": (
                "Bu Esri akışında alan tipi desteklenmiyor. "
                "Desteklenen tipler: text, varchar, char, integer, numeric, "
                "double precision, date, timestamp"
            ),
            "debug": req.field.data_type,
        }

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    conn = None
    cur = None
    try:
        conn = _connect_db(info)
        cur = conn.cursor()
        if not _dataset_exists(cur, schema_name, dataset_name):
            return {
                "ok": False,
                "message": "Secilen veri seti bulunamadi.",
                "debug": f"{schema_name}.{dataset_name}",
            }
        existing = _list_fields(cur, schema_name, dataset_name)
        if _find_field(existing, field_name):
            return {"ok": False, "message": "Ayni alan adi zaten mevcut.", "debug": field_name}

        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "message": "Alan eklenemedi.", "debug": str(e)}
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

    # Esri tarafinda alan ekleme/alias uygulama arcpy uzerinden yapilir.
    # SQL ile dogrudan kolon acmak ArcGIS tarafinda gorunum tutarsizligi yaratabilir.
    arcgis_field = {
        "name": field_name,
        "alias": field_alias,
        "data_type": req.field.data_type,
        "length": req.field.length,
        "precision": req.field.precision,
        "scale": req.field.scale,
        "nullable": bool(req.field.nullable),
    }
    requested_aliases = {field_name: field_alias} if field_alias else None
    ok, reg_debug, reg_payload = _register_with_geodatabase(
        info=info,
        schema_name=schema_name,
        dataset_name=dataset_name,
        geometry_column=None,
        geom_type=None,
        srid=None,
        fields=[arcgis_field],
        field_aliases=requested_aliases,
        skip_register=True,
    )
    if not ok:
        return {
            "ok": False,
            "message": "Yeni alan ArcGIS tarafinda eklenemedi.",
            "debug": reg_debug,
        }

    persisted_aliases = (reg_payload or {}).get("persisted_field_aliases") or {}
    verified_alias = _lookup_persisted_alias(persisted_aliases, field_name)

    # Uygulama icindeki alan listesinde alias'in gorunmesi icin yorum bilgisini senkron tut.
    comment_warning = ""
    if field_alias:
        conn = None
        cur = None
        try:
            conn = _connect_db(info)
            cur = conn.cursor()
            cur.execute(
                sql.SQL("COMMENT ON COLUMN {}.{}.{} IS %s").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(field_name),
                ),
                (f"alias={field_alias}",),
            )
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            comment_warning = str(e)
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

    message = "Yeni alan eklendi."
    debug = ""
    if field_alias:
        # ArcGIS helper zaten kendi icinde alias uygulama + dogrulama yapiyor.
        # Buradaki mesaji yalnizca bilgilendirme icin tutuyoruz; sahte uyari uretmeyelim.
        message = "Yeni alan eklendi ve alias uygulandi."
        if verified_alias and _norm_alias_text(verified_alias) != _norm_alias_text(field_alias):
            debug = (
                f"Alias bilgi notu | beklenen_alias={field_alias} | "
                f"okunan_alias={verified_alias or '-'}"
            )
    if comment_warning:
        if debug:
            debug += " | "
        debug += f"COMMENT senkron uyarisi: {comment_warning}"

    return {
        "ok": True,
        "message": message,
        "debug": debug,
        "data": {
            "field_name": field_name,
            "alias_applied": bool(field_alias),
            "verified_alias": verified_alias or None,
        },
    }


@router.post("/createandeditfieldesri-update-field")
def createandeditfieldesri_update_field(req: UpdateFieldReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_name = (req.dataset_name or "").strip()
    old_field_name = (req.old_field_name or "").strip()
    new_name = (req.field.name or "").strip()
    new_alias = (req.field.alias or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name bos olamaz")
    if not old_field_name:
        raise HTTPException(status_code=400, detail="old_field_name bos olamaz")
    if not new_name:
        return {"ok": False, "message": "Alan adi bos olamaz.", "debug": ""}
    if not _is_valid_ident(new_name):
        return {"ok": False, "message": "Alan adi gecersiz.", "debug": new_name}

    sql_type, type_err = _resolve_field_sql_type(
        req.field.data_type, req.field.length, req.field.precision, req.field.scale
    )
    if type_err:
        return {"ok": False, "message": type_err, "debug": req.field.data_type}

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    conn = None
    cur = None
    try:
        conn = _connect_db(info)
        cur = conn.cursor()
        if not _dataset_exists(cur, schema_name, dataset_name):
            return {
                "ok": False,
                "message": "Secilen veri seti bulunamadi.",
                "debug": f"{schema_name}.{dataset_name}",
            }

        fields = _list_fields(cur, schema_name, dataset_name)
        old_f = _find_field(fields, old_field_name)
        if not old_f:
            return {"ok": False, "message": "Guncellenecek alan bulunamadi.", "debug": old_field_name}
        if old_f.get("is_system"):
            return {"ok": False, "message": "Sistem alani guncellenemez.", "debug": old_field_name}
        if old_f.get("is_geometry"):
            return {"ok": False, "message": "Geometri alani bu ekrandan guncellenemez.", "debug": old_field_name}

        conflict = _find_field(fields, new_name)
        if conflict and (conflict.get("name") or "").lower() != old_field_name.lower():
            return {"ok": False, "message": "Hedef alan adi zaten mevcut.", "debug": new_name}

        active_name = old_field_name
        if old_field_name.lower() != new_name.lower():
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} RENAME COLUMN {} TO {}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(old_field_name),
                    sql.Identifier(new_name),
                )
            )
            active_name = new_name

        cur.execute(
            sql.SQL("ALTER TABLE {}.{} ALTER COLUMN {} TYPE {} USING {}::{}").format(
                sql.Identifier(schema_name),
                sql.Identifier(dataset_name),
                sql.Identifier(active_name),
                sql.SQL(sql_type),
                sql.Identifier(active_name),
                sql.SQL(sql_type),
            )
        )

        if req.field.nullable:
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ALTER COLUMN {} DROP NOT NULL").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(active_name),
                )
            )
        else:
            cur.execute(
                sql.SQL("ALTER TABLE {}.{} ALTER COLUMN {} SET NOT NULL").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(active_name),
                )
            )

        if new_alias:
            cur.execute(
                sql.SQL("COMMENT ON COLUMN {}.{}.{} IS %s").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(active_name),
                ),
                (f"alias={new_alias}",),
            )
        else:
            cur.execute(
                sql.SQL("COMMENT ON COLUMN {}.{}.{} IS NULL").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(active_name),
                )
            )

        conn.commit()

        if not new_alias:
            return {
                "ok": True,
                "message": "Alan guncellendi.",
                "data": {
                    "field_name": active_name,
                    "alias_applied": None,
                    "verified_alias": None,
                },
            }

        alias_ok, alias_debug, alias_payload = _apply_field_aliases_with_arcgis(
            info,
            schema_name,
            dataset_name,
            {active_name: new_alias},
        )
        persisted = (alias_payload or {}).get("persisted_field_aliases") or {}
        verified_alias = _lookup_persisted_alias(persisted, active_name)

        if not alias_ok:
            return {
                "ok": True,
                "message": "Alan guncellendi ancak alias ArcGIS tarafina uygulanamadi.",
                "debug": alias_debug,
                "data": {
                    "field_name": active_name,
                    "alias_applied": False,
                    "verified_alias": verified_alias,
                },
            }

        return {
            "ok": True,
            "message": "Alan guncellendi ve alias uygulandi.",
            "data": {
                "field_name": active_name,
                "alias_applied": True,
                "verified_alias": verified_alias,
            },
        }
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "message": "Alan guncellenemedi.", "debug": str(e)}
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


@router.post("/createandeditfieldesri-delete-field")
def createandeditfieldesri_delete_field(req: DeleteFieldReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_name = (req.dataset_name or "").strip()
    field_name = (req.field_name or "").strip()

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not dataset_name:
        raise HTTPException(status_code=400, detail="dataset_name bos olamaz")
    if not field_name:
        raise HTTPException(status_code=400, detail="field_name bos olamaz")

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    conn = None
    cur = None
    try:
        conn = _connect_db(info)
        cur = conn.cursor()
        if not _dataset_exists(cur, schema_name, dataset_name):
            return {
                "ok": False,
                "message": "Secilen veri seti bulunamadi.",
                "debug": f"{schema_name}.{dataset_name}",
            }
        fields = _list_fields(cur, schema_name, dataset_name)
        target = _find_field(fields, field_name)
        if not target:
            return {"ok": False, "message": "Silinecek alan bulunamadi.", "debug": field_name}
        if target.get("is_system"):
            return {"ok": False, "message": "Sistem alani silinemez.", "debug": field_name}

        cur.execute(
            sql.SQL("ALTER TABLE {}.{} DROP COLUMN {}").format(
                sql.Identifier(schema_name),
                sql.Identifier(dataset_name),
                sql.Identifier(field_name),
            )
        )
        conn.commit()
        return {"ok": True, "message": "Alan silindi.", "data": {"field_name": field_name}}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "message": "Alan silinemedi.", "debug": str(e)}
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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import re

import psycopg2
from psycopg2 import sql

from core.storage import open_db


router = APIRouter(tags=["db-createfeature"])

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CreateFeatureFieldReq(BaseModel):
    name: str
    alias: str = ""
    data_type: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True


class CreateFeatureDatasetReq(BaseModel):
    conn_name: str
    schema_name: str
    dataset_name: str
    dataset_alias: str = ""
    geometry_type: str = "none"
    geometry_column: str = "geom"
    srid: int | None = 4326
    fields: list[CreateFeatureFieldReq] = Field(default_factory=list)


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


def _validate_postgis_conn(conn_name: str):
    info = _get_db_connection_by_name(conn_name)
    if not info:
        return None, {
            "ok": False,
            "message": "Bağlantı bulunamadı.",
            "debug": conn_name,
        }

    if _normalize_db_type(str(info.get("DbType") or "")) != "postgis":
        return None, {
            "ok": False,
            "message": "Seçilen bağlantı PostGIS değil (DbType=PostGIS olmalı).",
            "debug": f"DbType={info.get('DbType')}",
        }
    return info, None


def _connect_postgis(info: dict):
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


def _ensure_id_immutable_trigger(cur, schema_name: str, table_name: str):
    fn_name = "__dbm_lock_id_immutable"
    trg_name = "trg_lock_id_immutable"

    cur.execute(
        sql.SQL(
            """
            CREATE OR REPLACE FUNCTION {}.{}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.id IS DISTINCT FROM OLD.id THEN
                    RAISE EXCEPTION 'id alani degistirilemez';
                END IF;
                RETURN NEW;
            END;
            $$;
            """
        ).format(sql.Identifier(schema_name), sql.Identifier(fn_name))
    )

    cur.execute(
        sql.SQL("DROP TRIGGER IF EXISTS {} ON {}.{}").format(
            sql.Identifier(trg_name),
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
        )
    )
    cur.execute(
        sql.SQL(
            "CREATE TRIGGER {} BEFORE UPDATE ON {}.{} "
            "FOR EACH ROW EXECUTE FUNCTION {}.{}()"
        ).format(
            sql.Identifier(trg_name),
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
            sql.Identifier(schema_name),
            sql.Identifier(fn_name),
        )
    )


@router.get("/createfeature-schemas")
def createfeature_schemas(conn_name: str):
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


@router.post("/createfeature-dataset")
def createfeature_dataset(req: CreateFeatureDatasetReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    dataset_name = (req.dataset_name or "").strip()
    dataset_alias = (req.dataset_alias or "").strip()
    geometry_column = (req.geometry_column or "").strip()

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
        if not geometry_column:
            return {"ok": False, "message": "Geometri kolonu adı boş olamaz.", "debug": ""}
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
                return {"ok": False, "message": "SRID pozitif bir sayı olmalı.", "debug": str(req.srid)}

    prepared_fields = []
    seen_fields = set()
    for raw in (req.fields or []):
        col_name = (raw.name or "").strip()
        alias = (raw.alias or "").strip()
        if not col_name:
            return {"ok": False, "message": "Alan adı boş olamaz.", "debug": ""}
        if not _is_valid_ident(col_name):
            return {"ok": False, "message": f"Geçersiz alan adı: {col_name}", "debug": col_name}

        col_key = col_name.lower()
        if col_key in seen_fields:
            return {"ok": False, "message": f"Aynı alan adı tekrarlandı: {col_name}", "debug": col_name}
        if col_key == "id":
            return {"ok": False, "message": "'id' alan adı sistemde ayrılmıştır.", "debug": col_name}
        if geom_type and col_key == geometry_column.lower():
            return {
                "ok": False,
                "message": f"Alan adı geometri kolonu ile çakışıyor: {col_name}",
                "debug": col_name,
            }

        sql_type, type_err = _resolve_field_sql_type(
            raw.data_type, raw.length, raw.precision, raw.scale
        )
        if type_err:
            return {"ok": False, "message": type_err, "debug": f"{col_name}: {raw.data_type}"}

        prepared_fields.append(
            {
                "name": col_name,
                "alias": alias,
                "sql_type": sql_type,
                "nullable": bool(raw.nullable),
                "length": raw.length,
                "precision": raw.precision,
                "scale": raw.scale,
            }
        )
        seen_fields.add(col_key)

    info, err = _validate_postgis_conn(conn_name)
    if err:
        return err

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

        if geom_type:
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

        # id kolonu sistem tarafindan uretilir; istemci tarafinda manuel degistirilmemeli.
        column_defs = [
            sql.SQL("{} BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY").format(
                sql.Identifier("id")
            )
        ]

        for f in prepared_fields:
            null_sql = sql.SQL("NULL" if f["nullable"] else "NOT NULL")
            column_defs.append(
                sql.SQL("{} {} {}").format(
                    sql.Identifier(f["name"]),
                    sql.SQL(f["sql_type"]),
                    null_sql,
                )
            )

        if geom_type:
            geom_decl = f"geometry({geom_type},{srid})" if srid else f"geometry({geom_type})"
            column_defs.append(
                sql.SQL("{} {}").format(
                    sql.Identifier(geometry_column),
                    sql.SQL(geom_decl),
                )
            )

        cur.execute(
            sql.SQL("CREATE TABLE {}.{} ({})").format(
                sql.Identifier(schema_name),
                sql.Identifier(dataset_name),
                sql.SQL(", ").join(column_defs),
            )
        )
        _ensure_id_immutable_trigger(cur, schema_name, dataset_name)

        if dataset_alias:
            cur.execute(
                sql.SQL("COMMENT ON TABLE {}.{} IS %s").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                ),
                (f"alias={dataset_alias}",),
            )

        for f in prepared_fields:
            if not f["alias"]:
                continue
            cur.execute(
                sql.SQL("COMMENT ON COLUMN {}.{}.{} IS %s").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(dataset_name),
                    sql.Identifier(f["name"]),
                ),
                (f"alias={f['alias']}",),
            )

        conn.commit()
        return {
            "ok": True,
            "message": "Veri seti oluşturuldu.",
            "data": {
                "schema": schema_name,
                "dataset": dataset_name,
                "dataset_alias": dataset_alias or None,
                "geometry_type": geom_type,
                "geometry_column": geometry_column if geom_type else None,
                "srid": srid if geom_type else None,
                "field_count": len(prepared_fields),
            },
        }

    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "ok": False,
            "message": "Veri seti oluşturulamadı.",
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

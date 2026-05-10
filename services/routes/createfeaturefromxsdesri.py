from pathlib import Path
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2 import sql

from services.routes.createpostgisschema import (
    _xsd_parse_schema_model,
    _xsd_build_sql_columns,
)
from services.routes.createesrifeature import (
    _connect_db,
    _find_st_geometry_schema,
    _register_with_geodatabase,
    _validate_esri_conn,
)


router = APIRouter(tags=["db-createfeaturefromxsdesri"])


class CreateFeatureFromXsdEsriReq(BaseModel):
    conn_name: str
    schema_name: str
    xsd_path: str
    manual_epsg: int | None = None


def _detect_epsg_from_xsd_text(src: Path) -> int | None:
    try:
        txt = src.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    patterns = [
        r"EPSG\s*[:]\s*(\d{3,7})",
        r"urn:ogc:def:crs:EPSG::(\d{3,7})",
        r",E(\d{3,7})\)",
    ]
    for p in patterns:
        m = re.search(p, txt, flags=re.IGNORECASE)
        if m:
            try:
                val = int(m.group(1))
                if val > 0:
                    return val
            except Exception:
                continue
    return None


def _geom_type_from_pg(pg_type: str) -> str:
    t = (pg_type or "").strip().lower()
    if "multipolygon" in t or "multisurface" in t:
        return "MultiPolygon"
    if "polygon" in t:
        return "Polygon"
    if "multilinestring" in t or "multicurve" in t:
        return "MultiLineString"
    if "linestring" in t or "curve" in t:
        return "LineString"
    if "multipoint" in t:
        return "MultiPoint"
    if "point" in t:
        return "Point"
    return "Geometry"


def _field_data_type_from_pg(pg_type: str) -> tuple[str, int | None]:
    t = (pg_type or "").strip().lower()
    if t in ("text", "varchar", "character varying", "char", "bpchar", "jsonb"):
        return "text", 255
    if t in ("integer", "int", "int4", "smallint", "int2"):
        return "integer", None
    if t in ("bigint", "int8", "numeric", "double precision", "float8", "float4"):
        return "numeric", None
    if t in ("date",):
        return "date", None
    if t in ("timestamp", "timestamp without time zone", "time without time zone"):
        return "timestamp", None
    if t in ("boolean", "bool"):
        return "text", 5
    return "text", 255


@router.post("/create-feature-from-xsd-esri")
def create_feature_from_xsd_esri(req: CreateFeatureFromXsdEsriReq):
    conn_name = (req.conn_name or "").strip()
    schema_name = (req.schema_name or "").strip()
    xsd_path = (req.xsd_path or "").strip()
    manual_epsg = req.manual_epsg

    if not conn_name:
        raise HTTPException(status_code=400, detail="conn_name bos olamaz")
    if not schema_name:
        raise HTTPException(status_code=400, detail="schema_name bos olamaz")
    if not xsd_path:
        raise HTTPException(status_code=400, detail="xsd_path bos olamaz")
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

    src = Path(xsd_path)
    if not src.exists():
        return {"ok": False, "message": "XSD dosyasi bulunamadi.", "debug": xsd_path}
    if not src.is_file():
        return {"ok": False, "message": "Gecersiz XSD dosya yolu.", "debug": xsd_path}
    if src.suffix.lower() != ".xsd":
        return {
            "ok": False,
            "message": "Desteklenmeyen dosya formati. (.xsd olmali)",
            "debug": f"ext={src.suffix.lower()}",
        }

    info, err = _validate_esri_conn(conn_name)
    if err:
        return err

    try:
        dataset_defs, _, parse_notes = _xsd_parse_schema_model(src)
    except Exception as e:
        return {"ok": False, "message": "XSD dosyasi cozumlenemedi.", "debug": str(e)}

    if not dataset_defs:
        return {
            "ok": False,
            "message": "XSD icinde olusturulabilir veri seti bulunamadi.",
            "debug": "; ".join(parse_notes[:10]),
        }

    detected_epsg = _detect_epsg_from_xsd_text(src)
    used_manual_epsg = False
    if manual_epsg is not None:
        srid = int(manual_epsg)
        used_manual_epsg = True
    elif detected_epsg is not None:
        srid = int(detected_epsg)
    else:
        return {
            "ok": False,
            "message": "Koordinat sistemi (EPSG) tespit edilemedi. Lutfen EPSG kodu giriniz.",
            "debug": f"xsd={src.name}",
            "requires_epsg": True,
        }

    jobs = []
    for ds in dataset_defs:
        table_name = (ds.get("table_name") or "").strip()
        if not table_name:
            continue

        columns, has_geom = _xsd_build_sql_columns(ds.get("fields") or [])
        if not has_geom:
            continue

        geom_cols = [c for c in columns if bool(c.get("is_geometry"))]
        geom_col = geom_cols[0] if geom_cols else None
        geom_type = _geom_type_from_pg((geom_col or {}).get("pg_type") or "")

        fields = []
        field_aliases = {}
        required_fields = []
        for c in columns:
            if bool(c.get("is_geometry")):
                continue
            name = (c.get("column_name") or "").strip()
            if not name:
                continue
            if name.lower() in ("objectid", "shape"):
                continue
            data_type, length = _field_data_type_from_pg(c.get("pg_type") or "")
            alias = (c.get("source_name") or "").strip()
            f = {
                "name": name,
                "alias": alias,
                "data_type": data_type,
                "length": length,
                "precision": None,
                "scale": None,
                "nullable": not bool(c.get("is_required")),
            }
            fields.append(f)
            if alias:
                field_aliases[name] = alias
            if bool(c.get("is_required")):
                required_fields.append(name)

        jobs.append(
            {
                "table_name": table_name,
                "geom_type": geom_type,
                "fields": fields,
                "field_aliases": field_aliases,
                "required_fields": required_fields,
            }
        )

    if not jobs:
        return {
            "ok": False,
            "message": "XSD cozumlendi ancak olusturulabilir geometri veri seti bulunamadi.",
            "debug": "Geometri icermeyen tipler atlandi.",
        }

    created_tables = []
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
            return {
                "ok": False,
                "message": "Secilen sema bulunamadi.",
                "debug": f"schema_name={schema_name}",
            }

        st_schema = _find_st_geometry_schema(cur)
        if not st_schema:
            return {
                "ok": False,
                "message": "Secilen veritabaninda ST_Geometry tipi bulunamadi.",
                "debug": "Esri ST_Geometry kurulumunu kontrol edin.",
            }

        existing = []
        for j in jobs:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                LIMIT 1
                """,
                (schema_name, j["table_name"]),
            )
            if cur.fetchone():
                existing.append(j["table_name"])

        if existing:
            return {
                "ok": False,
                "message": "Bazi tablo adlari hedef semada zaten mevcut. Islem baslatilmadi.",
                "debug": ", ".join([f"{schema_name}.{t}" for t in existing[:30]]),
            }

        for j in jobs:
            cur.execute(
                sql.SQL("CREATE TABLE {}.{} ({} {}.st_geometry)").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(j["table_name"]),
                    sql.Identifier("shape"),
                    sql.Identifier(st_schema),
                )
            )
            created_tables.append(j["table_name"])
        conn.commit()
        cur.close()
        conn.close()
        cur = None
        conn = None
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "ok": False,
            "message": "XSD'den Esri veri seti olusturulamadi.",
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

    created_info = []
    for j in jobs:
        ok, reg_debug, _ = _register_with_geodatabase(
            info=info,
            schema_name=schema_name,
            dataset_name=j["table_name"],
            geometry_column="shape",
            geom_type=j["geom_type"],
            srid=srid,
            fields=j["fields"],
            field_aliases=j["field_aliases"],
        )
        if not ok:
            try:
                cleanup_conn = _connect_db(info)
                try:
                    cleanup_cur = cleanup_conn.cursor()
                    for t in created_tables:
                        cleanup_cur.execute(
                            sql.SQL("DROP TABLE IF EXISTS {}.{} CASCADE").format(
                                sql.Identifier(schema_name),
                                sql.Identifier(t),
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

        conn2 = None
        cur2 = None
        try:
            conn2 = _connect_db(info)
            cur2 = conn2.cursor()
            for col_name in j["required_fields"]:
                cur2.execute(
                    sql.SQL("ALTER TABLE {}.{} ALTER COLUMN {} SET NOT NULL").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(j["table_name"]),
                        sql.Identifier(col_name),
                    )
                )
            conn2.commit()
        except Exception:
            if conn2:
                conn2.rollback()
        finally:
            try:
                if cur2:
                    cur2.close()
            except Exception:
                pass
            try:
                if conn2:
                    conn2.close()
            except Exception:
                pass

        created_info.append(
            {
                "table": j["table_name"],
                "geometry_type": j["geom_type"],
                "field_count": len(j["fields"]),
                "required_count": len(j["required_fields"]),
                "srid": srid,
                "used_manual_epsg": used_manual_epsg,
            }
        )

    msg = (
        f"'{src.name}' dosyasindan {len(created_info)} Esri veri seti olusturuldu."
        f"\nKoordinat sistemi: EPSG:{srid}"
    )
    if used_manual_epsg:
        msg += "\nNot: Koordinat sistemi kullanici tarafindan girilen EPSG kodu ile atandi."
    if parse_notes:
        msg += "\nNot: " + "; ".join(parse_notes[:4])
    lines = [
        f"- {schema_name}.{it['table']} ({it['geometry_type']}, alan={it['field_count']}, zorunlu={it['required_count']})"
        for it in created_info[:20]
    ]
    if lines:
        msg += "\n" + "\n".join(lines)

    return {
        "ok": True,
        "message": msg,
        "data": {
            "schema": schema_name,
            "srid": srid,
            "used_manual_epsg": used_manual_epsg,
            "tables": created_info,
        },
    }


from __future__ import print_function

import argparse
import base64
import json
import os
import shutil
import sys
import tempfile


try:
    text_type = unicode  # type: ignore[name-defined]
except NameError:
    text_type = str


def _to_text(value):
    if value is None:
        return text_type("")
    if isinstance(value, text_type):
        return value
    try:
        if sys.version_info[0] < 3 and isinstance(value, str):
            try:
                return value.decode("utf-8")
            except Exception:
                try:
                    return value.decode("cp1254")
                except Exception:
                    return value.decode("latin-1", "ignore")
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return value.decode("latin-1", "ignore")
    except Exception:
        pass
    try:
        return text_type(value)
    except Exception:
        try:
            return text_type(repr(value))
        except Exception:
            return text_type("")


def _exc_text(exc):
    try:
        return _to_text(exc)
    except Exception:
        try:
            return _to_text(repr(exc))
        except Exception:
            return text_type("unknown error")


def _json_out(payload, code=0):
    text = json.dumps(payload, ensure_ascii=False)
    try:
        if sys.version_info[0] < 3:
            sys.stdout.write(text.encode("utf-8"))
            sys.stdout.write("\n")
        else:
            sys.stdout.write(text)
            sys.stdout.write("\n")
    except Exception:
        print(json.dumps(payload, ensure_ascii=True))
    raise SystemExit(code)


def _normalize_version(v):
    parts = [p for p in _to_text(v or "").strip().split(".") if p != ""]
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def _version_from_executable_path():
    exe = (sys.executable or "").replace("\\", "/").lower()
    if "arcgis10.8" in exe or "arcgisx6410.8" in exe:
        return "10.8.x"
    if "arcgis10.7" in exe or "arcgisx6410.7" in exe:
        return "10.7.x"
    return ""


def _check_supported_arcgis_version(arcpy):
    try:
        info = arcpy.GetInstallInfo()
    except Exception:
        return True, ""

    product_name = _to_text(info.get("ProductName") or info.get("Product") or "").strip().lower()
    version = _normalize_version(info.get("Version") or "")

    desktop_markers = ("desktop", "arcmap", "arcgis desktop")
    is_arcmap_family = any(m in product_name for m in desktop_markers)

    if not is_arcmap_family:
        return True, ""

    exe_version = _version_from_executable_path()
    if exe_version == "10.8.x":
        return True, ""

    allowed = {"10.8.0", "10.8.1", "10.8.2"}
    if version not in allowed:
        return (
            False,
            (
                u"Bu islem yalnizca desteklenen ArcMap surumlerinde calistirilabilir. "
                u"Zorunlu surumler: 10.8.0, 10.8.1, 10.8.2. "
                u"Tespit edilen surum: {}"
            ).format(version or "bilinmiyor"),
        )
    return True, ""


def _make_tempdir():
    return tempfile.mkdtemp(prefix="dbm_arcgis_")


def _cleanup_tempdir(path):
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _create_db_connection(arcpy, out_folder, out_name, instance, user, password, database):
    if hasattr(arcpy, "management") and hasattr(arcpy.management, "CreateDatabaseConnection"):
        out_ws = arcpy.management.CreateDatabaseConnection(
            out_folder,
            out_name,
            "POSTGRESQL",
            instance,
            "DATABASE_AUTH",
            user,
            password or "",
            "SAVE_USERNAME",
            database,
        )
        return _to_text(out_ws[0]) if out_ws else _to_text(os.path.join(out_folder, out_name))

    if hasattr(arcpy, "CreateDatabaseConnection_management"):
        out_ws = arcpy.CreateDatabaseConnection_management(
            out_folder,
            out_name,
            "POSTGRESQL",
            instance,
            "DATABASE_AUTH",
            user,
            password or "",
            "SAVE_USERNAME",
            database,
        )
        return _to_text(out_ws[0]) if out_ws else _to_text(os.path.join(out_folder, out_name))

    raise RuntimeError("CreateDatabaseConnection araci bulunamadi.")


def _register_with_geodatabase(arcpy, dataset_path, objectid_field, shape_field, geometry_type, srid):
    objectid_field = (objectid_field or "").strip()
    shape_field = (shape_field or "").strip()

    if shape_field:
        sr = arcpy.SpatialReference(int(srid))
        if hasattr(arcpy, "management") and hasattr(arcpy.management, "RegisterWithGeodatabase"):
            if objectid_field:
                return arcpy.management.RegisterWithGeodatabase(
                    dataset_path,
                    objectid_field,
                    shape_field,
                    geometry_type,
                    sr,
                )
            return arcpy.management.RegisterWithGeodatabase(
                dataset_path,
                None,
                shape_field,
                geometry_type,
                sr,
            )
        if hasattr(arcpy, "RegisterWithGeodatabase_management"):
            if objectid_field:
                return arcpy.RegisterWithGeodatabase_management(
                    dataset_path,
                    objectid_field,
                    shape_field,
                    geometry_type,
                    sr,
                )
            return arcpy.RegisterWithGeodatabase_management(
                dataset_path,
                "#",
                shape_field,
                geometry_type,
                sr,
            )
    else:
        if hasattr(arcpy, "management") and hasattr(arcpy.management, "RegisterWithGeodatabase"):
            if objectid_field:
                return arcpy.management.RegisterWithGeodatabase(
                    dataset_path,
                    objectid_field,
                )
            return arcpy.management.RegisterWithGeodatabase(dataset_path)
        if hasattr(arcpy, "RegisterWithGeodatabase_management"):
            if objectid_field:
                return arcpy.RegisterWithGeodatabase_management(
                    dataset_path,
                    objectid_field,
                )
            return arcpy.RegisterWithGeodatabase_management(dataset_path)

    raise RuntimeError("RegisterWithGeodatabase araci bulunamadi.")


def _alter_alias_name(arcpy, dataset_path, alias_name):
    alias_name = (alias_name or "").strip()
    if not alias_name:
        return

    if hasattr(arcpy, "AlterAliasName"):
        return arcpy.AlterAliasName(dataset_path, alias_name)

    if hasattr(arcpy, "management") and hasattr(arcpy.management, "AlterAliasName"):
        return arcpy.management.AlterAliasName(dataset_path, alias_name)

    raise RuntimeError("AlterAliasName araci bulunamadi.")


def _alter_field_alias(arcpy, dataset_path, field_name, alias_name):
    field_name = (field_name or "").strip()
    alias_name = (alias_name or "").strip()
    if not field_name or not alias_name:
        return

    def _current_alias():
        try:
            fields = arcpy.ListFields(dataset_path, field_name)
            if fields:
                return _to_text(getattr(fields[0], "aliasName", "") or "")
        except Exception:
            return ""
        return ""

    def _run_alter(target_path):
        if hasattr(arcpy, "management") and hasattr(arcpy.management, "AlterField"):
            return arcpy.management.AlterField(
                target_path,
                field_name,
                "#",
                alias_name,
                "#",
                "#",
                "#",
                "FALSE",
            )

        if hasattr(arcpy, "AlterField_management"):
            return arcpy.AlterField_management(
                target_path,
                field_name,
                "#",
                alias_name,
                "#",
                "#",
                "#",
                "FALSE",
            )

        raise RuntimeError("AlterField araci bulunamadi.")

    _run_alter(dataset_path)
    if _current_alias() == alias_name:
        return

    temp_name = "dbm_alias_view"
    desc = arcpy.Describe(dataset_path)
    shape_field = _to_text(getattr(desc, "shapeFieldName", "") or "")

    try:
        if shape_field:
            if hasattr(arcpy, "management") and hasattr(arcpy.management, "MakeFeatureLayer"):
                arcpy.management.MakeFeatureLayer(dataset_path, temp_name)
            else:
                arcpy.MakeFeatureLayer_management(dataset_path, temp_name)
        else:
            if hasattr(arcpy, "management") and hasattr(arcpy.management, "MakeTableView"):
                arcpy.management.MakeTableView(dataset_path, temp_name)
            else:
                arcpy.MakeTableView_management(dataset_path, temp_name)

        _run_alter(temp_name)
    finally:
        try:
            if hasattr(arcpy, "management") and hasattr(arcpy.management, "Delete"):
                arcpy.management.Delete(temp_name)
            else:
                arcpy.Delete_management(temp_name)
        except Exception:
            pass

    if _current_alias() != alias_name:
        raise RuntimeError(
            u"Alan alias'i uygulanamadi: {} -> {}".format(field_name, alias_name)
        )


def _read_field_aliases(arcpy, dataset_path):
    result = {}
    try:
        for fld in arcpy.ListFields(dataset_path):
            name = _to_text(getattr(fld, "name", "") or "")
            alias = _to_text(getattr(fld, "aliasName", "") or "")
            if name:
                result[name] = alias
    except Exception:
        pass
    return result


def _decode_json_arg(raw_text, raw_b64, fallback):
    value = _to_text(raw_b64 or "").strip()
    if value:
        try:
            decoded = base64.b64decode(value)
            return json.loads(decoded.decode("utf-8"))
        except Exception:
            return fallback

    value = _to_text(raw_text or "").strip()
    if value:
        try:
            return json.loads(value)
        except Exception:
            return fallback

    return fallback


def _normalize_field_type(value):
    s = _to_text(value or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    while "  " in s:
        s = s.replace("  ", " ")
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


def _map_addfield_type(field_def):
    data_type = _normalize_field_type(field_def.get("data_type"))

    if data_type in ("text", "varchar", "char"):
        return "TEXT"
    if data_type == "integer":
        return "LONG"
    if data_type in ("numeric", "double precision"):
        return "DOUBLE"
    if data_type in ("date", "timestamp"):
        return "DATE"

    raise RuntimeError(
        u"Bu ArcMap/Esri DB akisinda desteklenmeyen alan tipi: {}".format(
            field_def.get("data_type") or ""
        )
    )


def _add_field(arcpy, dataset_path, field_def):
    field_name = _to_text(field_def.get("name") or "").strip()
    if not field_name:
        raise RuntimeError("Alan adi bos olamaz.")

    field_alias = _to_text(field_def.get("alias") or "").strip()
    field_type = _map_addfield_type(field_def)
    field_precision = field_def.get("precision")
    field_scale = field_def.get("scale")
    field_length = field_def.get("length")

    if field_type != "TEXT":
        field_length = None
    if field_type != "DOUBLE":
        field_precision = None
        field_scale = None

    if hasattr(arcpy, "management") and hasattr(arcpy.management, "AddField"):
        return arcpy.management.AddField(
            dataset_path,
            field_name,
            field_type,
            field_precision,
            field_scale,
            field_length,
            field_alias,
            "NULLABLE",
            "NON_REQUIRED",
        )

    if hasattr(arcpy, "AddField_management"):
        return arcpy.AddField_management(
            dataset_path,
            field_name,
            field_type,
            field_precision if field_precision is not None else "#",
            field_scale if field_scale is not None else "#",
            field_length if field_length is not None else "#",
            field_alias if field_alias else "#",
            "NULLABLE",
            "NON_REQUIRED",
        )

    raise RuntimeError("AddField araci bulunamadi.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=False, default="")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--objectid", required=False, default="")
    parser.add_argument("--skip-register", action="store_true")
    parser.add_argument("--shape-field", default="")
    parser.add_argument("--geometry-type", default="")
    parser.add_argument("--srid", default="")
    parser.add_argument("--dataset-alias", default="")
    parser.add_argument("--field-aliases-json", default="")
    parser.add_argument("--field-aliases-json-b64", default="")
    parser.add_argument("--fields-json", default="")
    parser.add_argument("--fields-json-b64", default="")
    args = parser.parse_args()

    try:
        import arcpy
    except Exception as e:
        _json_out({"ok": False, "message": "arcpy import edilemedi.", "debug": _exc_text(e)}, 2)

    ok, version_msg = _check_supported_arcgis_version(arcpy)
    if not ok:
        _json_out({"ok": False, "message": version_msg, "debug": ""}, 4)

    instance = args.host
    if (args.port or "").strip() and (args.port or "").strip() != "5432":
        instance = "{},{}".format(args.host, args.port)

    tmpdir = _make_tempdir()
    try:
        conn_name = "dbm_register.sde"
        try:
            conn_path = _create_db_connection(
                arcpy,
                tmpdir,
                conn_name,
                instance,
                args.user,
                args.password or "",
                args.database,
            )
            dataset_path = os.path.join(
                conn_path,
                "{}.{}.{}".format(args.database, args.schema, args.dataset),
            )

            if not args.skip_register:
                _register_with_geodatabase(
                    arcpy,
                    dataset_path,
                    args.objectid,
                    (args.shape_field or "").strip(),
                    args.geometry_type,
                    args.srid,
                )

            if (args.dataset_alias or "").strip():
                _alter_alias_name(arcpy, dataset_path, args.dataset_alias)

            field_defs = _decode_json_arg(args.fields_json, args.fields_json_b64, [])

            if isinstance(field_defs, list):
                for field_def in field_defs:
                    if not isinstance(field_def, dict):
                        continue
                    _add_field(arcpy, dataset_path, field_def)

            field_aliases = _decode_json_arg(
                args.field_aliases_json,
                args.field_aliases_json_b64,
                {},
            )

            if isinstance(field_aliases, dict):
                for field_name, alias_name in field_aliases.items():
                    _alter_field_alias(arcpy, dataset_path, field_name, alias_name)

            try:
                if hasattr(arcpy, "management") and hasattr(arcpy.management, "ClearWorkspaceCache"):
                    arcpy.management.ClearWorkspaceCache(conn_path)
                elif hasattr(arcpy, "ClearWorkspaceCache_management"):
                    arcpy.ClearWorkspaceCache_management(conn_path)
            except Exception:
                pass

            fresh_conn_path = _create_db_connection(
                arcpy,
                tmpdir,
                "dbm_verify.sde",
                instance,
                args.user,
                args.password or "",
                args.database,
            )
            fresh_dataset_path = os.path.join(
                fresh_conn_path,
                "{}.{}.{}".format(args.database, args.schema, args.dataset),
            )
            persisted_aliases = _read_field_aliases(arcpy, fresh_dataset_path)
            if isinstance(field_aliases, dict):
                for field_name, alias_name in field_aliases.items():
                    if not (alias_name or "").strip():
                        continue
                    actual_alias = _to_text(persisted_aliases.get(field_name, "") or "")
                    if actual_alias != alias_name:
                        raise RuntimeError(
                            u"Field alias kalici degil: {} -> beklenen='{}', okunan='{}'".format(
                                field_name,
                                alias_name,
                                actual_alias,
                            )
                        )
        except Exception as e:
            _json_out(
                {
                    "ok": False,
                    "message": "Register With Geodatabase islemi basarisiz.",
                    "debug": _exc_text(e),
                },
                3,
            )
    finally:
        _cleanup_tempdir(tmpdir)

    _json_out(
        {
            "ok": True,
            "message": "Register With Geodatabase basarili.",
            "dataset_alias": (args.dataset_alias or "").strip() or None,
            "persisted_field_aliases": persisted_aliases,
        },
        0,
    )


if __name__ == "__main__":
    main()

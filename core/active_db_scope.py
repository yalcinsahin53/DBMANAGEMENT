import re

import flet as ft


def _normalize_db_type(v: str | None) -> str:
    s = (v or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if s == "postgis":
        return "postgis"
    if s in (
        "esri geodatabase",
        "enterprise geodatabase",
        "esri enterprise geodatabase",
        "esri",
    ):
        return "esri"
    return s


def get_active_db_scope(page: ft.Page) -> tuple[str, str, str]:
    return (
        (getattr(page, "active_conn_name", None) or "").strip(),
        (getattr(page, "active_schema_name", None) or "").strip(),
        _normalize_db_type(getattr(page, "active_db_type", None)),
    )


def has_active_db_scope(page: ft.Page, expected_db_type: str | None = None) -> bool:
    conn_name, schema_name, active_db_type = get_active_db_scope(page)
    if not conn_name or not schema_name:
        return False
    if expected_db_type is None:
        return True
    return active_db_type == _normalize_db_type(expected_db_type)


def set_active_db_scope(
    page: ft.Page,
    conn_name: str,
    schema_name: str,
    db_type: str | None = None,
):
    page.active_conn_name = (conn_name or "").strip() or None
    page.active_schema_name = (schema_name or "").strip() or None
    page.active_db_type = _normalize_db_type(db_type)

    refresher = getattr(page, "refresh_active_header", None)
    if callable(refresher):
        refresher()


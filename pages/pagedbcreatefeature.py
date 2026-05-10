import asyncio
import re

import flet as ft

from core.active_db_scope import get_active_db_scope, has_active_db_scope, set_active_db_scope


FIELD_TYPE_OPTIONS = [
    ("text", "Metin (text)"),
    ("varchar", "Metin (varchar)"),
    ("char", "Sabit Metin (char)"),
    ("integer", "Tam Sayi (integer)"),
    ("bigint", "Buyuk Sayi (bigint)"),
    ("numeric", "Ondalik (numeric)"),
    ("double precision", "Ondalik (double precision)"),
    ("boolean", "Mantiksal (boolean)"),
    ("date", "Tarih (date)"),
    ("timestamp", "Tarih-Saat (timestamp)"),
]

GEOMETRY_TYPE_OPTIONS = [
    ("none", "Geometri Yok"),
    ("Point", "Point"),
    ("MultiPoint", "MultiPoint"),
    ("LineString", "LineString"),
    ("MultiLineString", "MultiLineString"),
    ("Polygon", "Polygon"),
    ("MultiPolygon", "MultiPolygon"),
]

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_dbcreatefeature_view(page: ft.Page) -> ft.Control:
    active_conn_name, active_schema_name, _ = get_active_db_scope(page)
    use_active_scope = has_active_db_scope(page, "postgis")

    state = {
        "conn_name": active_conn_name if use_active_scope else None,
        "last_conn": active_conn_name if use_active_scope else None,
        "schema_name": active_schema_name if use_active_scope else None,
        "last_schema": active_schema_name if use_active_scope else None,
        "last_geometry_type": "none",
        "last_field_type": "text",
        "fields": [],
    }

    dd_conn = ft.Dropdown(
        label="PostGIS Baglantisi Secimi",
        hint_text="Kayitli PostGIS baglantilarindan secim yapiniz",
        expand=True,
        visible=not use_active_scope,
    )
    dd_schema = ft.Dropdown(
        label="Sema Secimi",
        hint_text="Once baglanti seciniz",
        expand=True,
        disabled=True if not use_active_scope else False,
        visible=not use_active_scope,
    )
    active_scope_info = ft.Container(
        visible=use_active_scope,
        padding=10,
        border=ft.border.all(1, ft.Colors.BLACK12),
        border_radius=8,
        bgcolor=ft.Colors.BLUE_50,
        content=ft.Text(
            f"Aktif kapsam kullaniliyor | Baglanti: {active_conn_name} | Sema: {active_schema_name}",
            selectable=True,
        ),
    )

    tf_dataset_name = ft.TextField(
        label="Veri Seti (Tablo) Adi",
        expand=True,
    )
    tf_dataset_alias = ft.TextField(
        label="Veri Seti Gorunen Adi (Alias)",
        expand=True,
    )
    dd_geometry_type = ft.Dropdown(
        label="Geometri Tipi",
        value="none",
        width=260,
        options=[ft.dropdown.Option(key=k, text=t) for k, t in GEOMETRY_TYPE_OPTIONS],
    )
    tf_geometry_column = ft.TextField(
        label="Geometri Kolonu",
        value="geom",
        width=220,
        disabled=True,
    )
    tf_srid = ft.TextField(
        label="SRID/EPSG Kodu (ornek: 4326)",
        width=200,
        disabled=True,
    )

    tf_field_name = ft.TextField(label="Alan Adi", width=220)
    tf_field_alias = ft.TextField(label="Gorunen Ad (Alias)", width=260)
    dd_field_type = ft.Dropdown(
        label="Alan Tipi",
        value="text",
        width=240,
        options=[ft.dropdown.Option(key=k, text=t) for k, t in FIELD_TYPE_OPTIONS],
    )
    tf_field_length = ft.TextField(
        label="Karakter Sayisi",
        width=160,
        disabled=True,
    )
    tf_field_precision = ft.TextField(
        label="Precision",
        width=140,
        disabled=True,
    )
    tf_field_scale = ft.TextField(
        label="Scale",
        width=140,
        disabled=True,
    )
    sw_field_nullable = ft.Switch(label="Null", value=True)
    btn_add_field = ft.ElevatedButton("Alan Ekle")
    btn_create = ft.ElevatedButton("Veri Setini Olustur", disabled=True)

    fields_panel = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
    summary_text = ft.Text("Durum: Alan ekleyebilirsiniz.")

    busy = ft.ProgressRing(visible=False)
    busy_text = ft.Text("", visible=False)
    debug_lbl = ft.Text("UYARILAR: hazir", size=12, selectable=True)

    debug_bar = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=10, bottom=10),
        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.BLACK12)),
        bgcolor=ft.Colors.WHITE,
        content=ft.Row(
            controls=[busy, busy_text, ft.Container(expand=True), debug_lbl],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    def _notify(title: str, msg: str):
        if getattr(page, "dialog_service", None):
            page.dialog_service.show(title, msg)
        else:
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(title),
                content=ft.Text(msg, selectable=True),
                actions=[ft.TextButton("Kapat")],
            )
            page.dialog = dlg
            dlg.open = True
            page.update()

    def _open_dialog(dlg: ft.AlertDialog):
        try:
            if hasattr(page, "overlay") and dlg not in page.overlay:
                page.overlay.append(dlg)
        except Exception:
            pass

        if hasattr(page, "open"):
            try:
                page.open(dlg)
                return
            except Exception:
                pass

        try:
            page.dialog = dlg
            dlg.open = True
            page.update()
            return
        except Exception:
            pass

    def _close_dialog(dlg: ft.AlertDialog):
        if hasattr(page, "close"):
            try:
                page.close(dlg)
                return
            except Exception:
                pass

        try:
            dlg.open = False
            if getattr(page, "dialog", None) is dlg:
                page.dialog = None
            page.update()
            return
        except Exception:
            pass
        dlg.open = False
        page.update()

    def _safe_update(control: ft.Control):
        try:
            control.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

    def _set_busy(on: bool, text: str = ""):
        busy.visible = on
        busy_text.visible = on
        busy_text.value = text or ""
        page.update()

    def _set_debug(msg: str):
        debug_lbl.value = msg
        _safe_update(debug_lbl)

    def _is_valid_ident(v: str) -> bool:
        return bool(IDENT_RE.match((v or "").strip()))

    def _field_type_supports_length(v: str) -> bool:
        return (v or "").strip().lower() in ("varchar", "char")

    def _field_type_supports_precision(v: str) -> bool:
        return (v or "").strip().lower() == "numeric"

    def _build_validated_field(
        name: str,
        alias: str,
        data_type: str,
        length_val: str,
        precision_val: str,
        scale_val: str,
        nullable: bool,
        skip_name: str | None = None,
    ) -> tuple[dict | None, str]:
        name = (name or "").strip()
        alias = (alias or "").strip()
        data_type = (data_type or "").strip()
        length_val = (length_val or "").strip()
        precision_val = (precision_val or "").strip()
        scale_val = (scale_val or "").strip()

        if not name:
            return None, "Alan adi bos olamaz."
        if not _is_valid_ident(name):
            return (
                None,
                "Alan adi gecersiz. Harf/rakam/_ kullanin ve ilk karakter harf veya '_' olmali.",
            )

        existing = {f["name"].lower() for f in state.get("fields", [])}
        if skip_name:
            existing.discard(skip_name.lower())
        if name.lower() in existing:
            return None, "Ayni alan adi tekrar eklenemez."

        length = None
        if _field_type_supports_length(data_type):
            if length_val:
                try:
                    length = int(length_val)
                    if length < 1 or length > 10485760:
                        raise ValueError
                except Exception:
                    return None, "Karakter sayisi 1-10485760 arasinda olmali."

        precision = None
        scale = None
        if _field_type_supports_precision(data_type):
            if precision_val:
                try:
                    precision = int(precision_val)
                    if precision < 1 or precision > 1000:
                        raise ValueError
                except Exception:
                    return None, "Precision 1-1000 arasinda olmali."
            if scale_val:
                try:
                    scale = int(scale_val)
                    if scale < 0:
                        raise ValueError
                except Exception:
                    return None, "Scale 0 veya daha buyuk olmali."
            if scale is not None and precision is None:
                return None, "Scale girmek icin once precision giriniz."
            if precision is not None and scale is not None and scale > precision:
                return None, "Scale precision degerinden buyuk olamaz."

        return (
            {
                "name": name,
                "alias": alias,
                "data_type": data_type,
                "length": length,
                "precision": precision,
                "scale": scale,
                "nullable": bool(nullable),
            },
            "",
        )

    def _reset_schema_dropdown():
        dd_schema.options = []
        dd_schema.value = None
        dd_schema.disabled = True
        state["schema_name"] = None
        state["last_schema"] = ""
        _safe_update(dd_schema)
        _update_create_button_state()

    def _sync_geometry_fields():
        gtype = (dd_geometry_type.value or "none").strip().lower()
        has_geom = gtype != "none"
        tf_srid.disabled = not has_geom
        _safe_update(tf_srid)
        page.update()

    def _update_create_button_state():
        conn_ok = bool((state.get("conn_name") or "").strip())
        schema_ok = bool((state.get("schema_name") or "").strip())
        dataset_name = (tf_dataset_name.value or "").strip()
        dataset_ok = bool(dataset_name and _is_valid_ident(dataset_name))

        gtype = (dd_geometry_type.value or "none").strip().lower()
        geom_ok = True
        if gtype != "none":
            geom_col = (tf_geometry_column.value or "").strip()
            if not geom_col or not _is_valid_ident(geom_col):
                geom_ok = False
            else:
                try:
                    srid_val = int((tf_srid.value or "").strip())
                    geom_ok = srid_val > 0
                except Exception:
                    geom_ok = False

        btn_create.disabled = not (conn_ok and schema_ok and dataset_ok and geom_ok)
        _safe_update(btn_create)

    def _render_fields():
        fields = state.get("fields", [])
        if not fields:
            fields_panel.controls = [
                ft.Container(
                    padding=10,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Text("Henuz alan eklenmedi."),
                )
            ]
            summary_text.value = "Durum: Alan ekleyebilirsiniz."
            _safe_update(fields_panel)
            _safe_update(summary_text)
            return

        rows = []
        rows.append(
            ft.Container(
                padding=ft.Padding.only(left=8, right=8, top=6, bottom=6),
                bgcolor=ft.Colors.BLUE_GREY_50,
                border_radius=8,
                content=ft.Row(
                    controls=[
                        ft.Container(
                            width=170,
                            content=ft.Text("Alan Adi", weight=ft.FontWeight.BOLD),
                        ),
                        ft.Container(
                            width=190,
                            content=ft.Text("Alias", weight=ft.FontWeight.BOLD),
                        ),
                        ft.Container(
                            width=170, content=ft.Text("Tip", weight=ft.FontWeight.BOLD)
                        ),
                        ft.Container(
                            width=120,
                            content=ft.Text("Karakter", weight=ft.FontWeight.BOLD),
                        ),
                        ft.Container(
                            width=140,
                            content=ft.Text("P / S", weight=ft.FontWeight.BOLD),
                        ),
                        ft.Container(
                            width=90, content=ft.Text("Null", weight=ft.FontWeight.BOLD)
                        ),
                        ft.Container(
                            width=170,
                            content=ft.Text("Islem", weight=ft.FontWeight.BOLD),
                        ),
                    ]
                ),
            )
        )

        for i, fld in enumerate(fields):
            rows.append(
                ft.Container(
                    padding=ft.Padding.only(left=8, right=8, top=6, bottom=6),
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                width=170, content=ft.Text(fld["name"], selectable=True)
                            ),
                            ft.Container(
                                width=190,
                                content=ft.Text(
                                    fld.get("alias") or "-", selectable=True
                                ),
                            ),
                            ft.Container(
                                width=170,
                                content=ft.Text(fld["data_type"], selectable=True),
                            ),
                            ft.Container(
                                width=120,
                                content=ft.Text(str(fld.get("length") or "-")),
                            ),
                            ft.Container(
                                width=140,
                                content=ft.Text(
                                    f"{fld.get('precision') if fld.get('precision') is not None else '-'} / "
                                    f"{fld.get('scale') if fld.get('scale') is not None else '-'}"
                                ),
                            ),
                            ft.Container(
                                width=90,
                                content=ft.Text(
                                    "Evet" if fld.get("nullable", True) else "Hayir"
                                ),
                            ),
                            ft.Container(
                                width=170,
                                content=ft.Row(
                                    spacing=0,
                                    controls=[
                                        ft.IconButton(
                                            icon=ft.Icons.EDIT_OUTLINED,
                                            tooltip="Guncelle",
                                            on_click=lambda e, idx=i: _open_edit_field_dialog(idx),
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE_OUTLINE,
                                            tooltip="Sil",
                                            on_click=lambda e, idx=i: _confirm_delete_field(idx),
                                        ),
                                    ],
                                ),
                            ),
                        ]
                    ),
                )
            )

        fields_panel.controls = rows
        summary_text.value = f"Durum: {len(fields)} alan hazir."
        _safe_update(fields_panel)
        _safe_update(summary_text)

    def _clear_field_editor():
        tf_field_name.value = ""
        tf_field_alias.value = ""
        dd_field_type.value = "text"
        tf_field_length.value = ""
        tf_field_length.disabled = True
        tf_field_precision.value = ""
        tf_field_precision.disabled = True
        tf_field_scale.value = ""
        tf_field_scale.disabled = True
        sw_field_nullable.value = True
        _safe_update(tf_field_name)
        _safe_update(tf_field_alias)
        _safe_update(dd_field_type)
        _safe_update(tf_field_length)
        _safe_update(tf_field_precision)
        _safe_update(tf_field_scale)
        _safe_update(sw_field_nullable)

    def _on_field_type_change(e):
        dtype = (dd_field_type.value or "").strip().lower()
        supports_length = _field_type_supports_length(dtype)
        supports_precision = _field_type_supports_precision(dtype)

        tf_field_length.disabled = not supports_length
        if tf_field_length.disabled:
            tf_field_length.value = ""
        tf_field_precision.disabled = not supports_precision
        if tf_field_precision.disabled:
            tf_field_precision.value = ""
        tf_field_scale.disabled = not supports_precision
        if tf_field_scale.disabled:
            tf_field_scale.value = ""

        _safe_update(tf_field_length)
        _safe_update(tf_field_precision)
        _safe_update(tf_field_scale)
        page.update()

    def _on_add_field_click(e):
        field_obj, err = _build_validated_field(
            tf_field_name.value or "",
            tf_field_alias.value or "",
            dd_field_type.value or "",
            tf_field_length.value or "",
            tf_field_precision.value or "",
            tf_field_scale.value or "",
            bool(sw_field_nullable.value),
        )
        if err:
            _notify("Uyari", err)
            return

        state["fields"].append(field_obj)
        _clear_field_editor()
        _render_fields()
        _set_debug(f"UYARILAR: alan eklendi | {field_obj['name']}")

    def _confirm_delete_field(idx: int):
        if idx < 0 or idx >= len(state.get("fields", [])):
            return

        field_name = state["fields"][idx]["name"]
        dlg = ft.AlertDialog(modal=True)
        dlg.title = ft.Text("Onay")
        dlg.content = ft.Text(
            f"Silmek Istediginizden Eminmisiniz?\nAlan: {field_name}"
        )

        def _yes(e):
            if 0 <= idx < len(state.get("fields", [])):
                removed = state["fields"].pop(idx)
                _render_fields()
                _set_debug(f"UYARILAR: alan silindi | {removed.get('name','')}")
            _close_dialog(dlg)

        def _no(e):
            _close_dialog(dlg)

        dlg.actions = [
            ft.TextButton("Hayir", on_click=_no),
            ft.ElevatedButton("Evet", on_click=_yes),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(dlg)

    def _open_edit_field_dialog(idx: int):
        if idx < 0 or idx >= len(state.get("fields", [])):
            return

        cur = state["fields"][idx]
        tf_edit_name = ft.TextField(label="Alan Adi", value=cur.get("name") or "", width=220)
        tf_edit_alias = ft.TextField(label="Gorunen Ad (Alias)", value=cur.get("alias") or "", width=260)
        dd_edit_type = ft.Dropdown(
            label="Alan Tipi",
            value=cur.get("data_type") or "text",
            width=240,
            options=[ft.dropdown.Option(key=k, text=t) for k, t in FIELD_TYPE_OPTIONS],
        )
        tf_edit_length = ft.TextField(
            label="Karakter Sayisi",
            width=160,
            value=str(cur.get("length")) if cur.get("length") is not None else "",
        )
        tf_edit_precision = ft.TextField(
            label="Precision",
            width=140,
            value=str(cur.get("precision")) if cur.get("precision") is not None else "",
        )
        tf_edit_scale = ft.TextField(
            label="Scale",
            width=140,
            value=str(cur.get("scale")) if cur.get("scale") is not None else "",
        )
        sw_edit_nullable = ft.Switch(label="Null", value=bool(cur.get("nullable", True)))

        def _sync_edit_type():
            dtype = (dd_edit_type.value or "").strip().lower()
            supports_length = _field_type_supports_length(dtype)
            supports_precision = _field_type_supports_precision(dtype)

            tf_edit_length.disabled = not supports_length
            if tf_edit_length.disabled:
                tf_edit_length.value = ""
            tf_edit_precision.disabled = not supports_precision
            if tf_edit_precision.disabled:
                tf_edit_precision.value = ""
            tf_edit_scale.disabled = not supports_precision
            if tf_edit_scale.disabled:
                tf_edit_scale.value = ""

            _safe_update(tf_edit_length)
            _safe_update(tf_edit_precision)
            _safe_update(tf_edit_scale)

        dd_edit_type.on_change = lambda e: _sync_edit_type()
        _sync_edit_type()

        dlg = ft.AlertDialog(modal=True)
        dlg.title = ft.Text("Alan Guncelle")
        dlg.content = ft.Container(
            width=980,
            content=ft.Column(
                tight=True,
                controls=[
                    ft.Row(
                        spacing=10,
                        controls=[
                            tf_edit_name,
                            tf_edit_alias,
                            dd_edit_type,
                            tf_edit_length,
                            tf_edit_precision,
                            tf_edit_scale,
                            sw_edit_nullable,
                        ],
                        wrap=True,
                    )
                ],
            ),
        )

        def _save(e):
            field_obj, err = _build_validated_field(
                tf_edit_name.value or "",
                tf_edit_alias.value or "",
                dd_edit_type.value or "",
                tf_edit_length.value or "",
                tf_edit_precision.value or "",
                tf_edit_scale.value or "",
                bool(sw_edit_nullable.value),
                skip_name=cur.get("name") or "",
            )
            if err:
                _notify("Uyari", err)
                return

            if 0 <= idx < len(state.get("fields", [])):
                state["fields"][idx] = field_obj
                _render_fields()
                _set_debug(f"UYARILAR: alan guncellendi | {field_obj['name']}")
            _close_dialog(dlg)

        def _cancel(e):
            _close_dialog(dlg)

        dlg.actions = [
            ft.TextButton("Vazgec", on_click=_cancel),
            ft.ElevatedButton("Kaydet", on_click=_save),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(dlg)

    async def _refresh_postgis_connections():
        _set_busy(True, "PostGIS baglantilari yukleniyor...")
        try:
            res = await asyncio.to_thread(page.api.db_list)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", (res or {}).get("message", "Baglantilar okunamadi."))
            dd_conn.options = []
            dd_conn.value = None
            state["conn_name"] = None
            state["last_conn"] = ""
            _reset_schema_dropdown()
            _safe_update(dd_conn)
            return

        items = res.get("data") or []
        postgis = [
            r
            for r in items
            if isinstance(r, dict)
            and (r.get("Conn_Name") or "").strip()
            and str(r.get("DbType") or "").strip().lower() == "postgis"
        ]
        dd_conn.options = [
            ft.dropdown.Option(
                key=r["Conn_Name"],
                text=f'{r["Conn_Name"]} ({r.get("DbType", "-")})',
            )
            for r in postgis
        ]
        dd_conn.value = None
        state["conn_name"] = None
        state["last_conn"] = ""
        _reset_schema_dropdown()
        _safe_update(dd_conn)
        _set_debug(f"UYARILAR: {len(postgis)} PostGIS baglantisi yuklendi.")
        _update_create_button_state()

    async def _load_schemas_for_conn(conn_name: str):
        state["conn_name"] = conn_name or None
        _reset_schema_dropdown()

        if not conn_name:
            _set_debug("UYARILAR: baglanti secimi temizlendi.")
            return

        _set_busy(True, "Sema listesi aliniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.createfeature_list_schemas, conn_name
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Sema listesi alinamadi.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug(f"UYARILAR: sema listesi alinamadi | {conn_name}")
            return

        schemas = [s for s in (res.get("data") or []) if (s or "").strip()]
        dd_schema.options = [ft.dropdown.Option(key=s, text=s) for s in schemas]
        dd_schema.disabled = False
        _safe_update(dd_schema)
        _set_debug(f"UYARILAR: {len(schemas)} sema yuklendi.")
        _update_create_button_state()

    async def on_conn_change(e):
        conn_name = (dd_conn.value or "").strip()
        state["last_conn"] = conn_name
        state["conn_name"] = conn_name or None
        await _load_schemas_for_conn(conn_name)
        _update_create_button_state()

    async def on_schema_change(e):
        schema_name = (dd_schema.value or "").strip()
        state["last_schema"] = schema_name
        state["schema_name"] = schema_name or None
        conn_name = (state.get("conn_name") or "").strip()
        if conn_name and schema_name:
            set_active_db_scope(page, conn_name, schema_name, "postgis")
        _update_create_button_state()
        if schema_name:
            _set_debug(f"UYARILAR: sema secildi | {schema_name}")

    async def _watch_conn_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_conn.value or "").strip()
            if cur == (state.get("last_conn") or ""):
                continue
            state["last_conn"] = cur
            state["conn_name"] = cur or None
            await _load_schemas_for_conn(cur)
            _update_create_button_state()

    async def _watch_schema_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_schema.value or "").strip()
            if cur == (state.get("last_schema") or ""):
                continue
            state["last_schema"] = cur
            state["schema_name"] = cur or None
            _update_create_button_state()

    async def _watch_geometry_type_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_geometry_type.value or "none").strip().lower()
            if cur == (state.get("last_geometry_type") or ""):
                continue
            state["last_geometry_type"] = cur
            _sync_geometry_fields()
            _update_create_button_state()

    async def _watch_field_type_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_field_type.value or "text").strip().lower()
            if cur == (state.get("last_field_type") or ""):
                continue
            state["last_field_type"] = cur
            _on_field_type_change(None)

    async def on_create_click(e):
        conn_name = (state.get("conn_name") or "").strip()
        schema_name = (state.get("schema_name") or "").strip()
        dataset_name = (tf_dataset_name.value or "").strip()
        dataset_alias = (tf_dataset_alias.value or "").strip()
        geometry_type = (dd_geometry_type.value or "none").strip()
        geometry_column = (tf_geometry_column.value or "").strip()

        if not conn_name:
            _notify("Uyari", "Lutfen PostGIS baglantisi seciniz.")
            return
        if not schema_name:
            _notify("Uyari", "Lutfen sema seciniz.")
            return
        if not dataset_name:
            _notify("Uyari", "Lutfen veri seti adi giriniz.")
            return
        if not _is_valid_ident(dataset_name):
            _notify(
                "Uyari",
                "Veri seti adi gecersiz. Harf/rakam/_ kullanin ve ilk karakter harf veya '_' olmali.",
            )
            return

        srid = None
        if geometry_type.lower() != "none":
            if not geometry_column or not _is_valid_ident(geometry_column):
                _notify("Uyari", "Geometri kolonu adi gecersiz.")
                return
            try:
                srid = int((tf_srid.value or "").strip())
                if srid <= 0:
                    raise ValueError
            except Exception:
                _notify("Uyari", "SRID pozitif bir sayi olmali.")
                return
        else:
            geometry_column = "geom"

        payload_fields = []
        for f in state.get("fields", []):
            payload_fields.append(
                {
                    "name": f["name"],
                    "alias": f.get("alias") or "",
                    "data_type": f["data_type"],
                    "length": f.get("length"),
                    "precision": f.get("precision"),
                    "scale": f.get("scale"),
                    "nullable": bool(f.get("nullable", True)),
                }
            )

        _set_busy(True, "Veri seti olusturuluyor...")
        try:
            res = await asyncio.to_thread(
                page.api.createfeature_create_dataset,
                conn_name,
                schema_name,
                dataset_name,
                dataset_alias,
                geometry_type,
                geometry_column,
                srid,
                payload_fields,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Veri seti olusturulamadi.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug("UYARILAR: veri seti olusturma basarisiz.")
            return

        data = res.get("data") or {}
        _notify(
            "Basarili",
            (
                (res.get("message") or "Veri seti olusturuldu.")
                + f"\nSema: {data.get('schema','-')}"
                + f"\nVeri Seti: {data.get('dataset','-')}"
                + f"\nAlias: {data.get('dataset_alias') or '-'}"
                + f"\nAlan Sayisi: {data.get('field_count', 0)}"
                + f"\nGeometri: {data.get('geometry_type') or 'Yok'}"
            ),
        )
        _set_debug(
            f"UYARILAR: veri seti olusturuldu | {data.get('schema','')}.{data.get('dataset','')}"
        )

    dd_conn.on_change = lambda e: page.run_task(on_conn_change, e)
    dd_schema.on_change = lambda e: page.run_task(on_schema_change, e)
    tf_dataset_name.on_change = lambda e: _update_create_button_state()
    tf_dataset_alias.on_change = lambda e: _update_create_button_state()
    dd_geometry_type.on_change = lambda e: (
        state.__setitem__(
            "last_geometry_type", (dd_geometry_type.value or "none").strip().lower()
        ),
        _sync_geometry_fields(),
        _update_create_button_state(),
    )
    tf_geometry_column.on_change = lambda e: _update_create_button_state()
    tf_srid.on_change = lambda e: _update_create_button_state()

    dd_field_type.on_change = _on_field_type_change
    btn_add_field.on_click = _on_add_field_click
    btn_create.on_click = lambda e: page.run_task(on_create_click, e)

    if use_active_scope:
        _update_create_button_state()
        page.run_task(_watch_geometry_type_selection)
        page.run_task(_watch_field_type_selection)
    else:
        page.run_task(_watch_conn_selection)
        page.run_task(_watch_schema_selection)
        page.run_task(_watch_geometry_type_selection)
        page.run_task(_watch_field_type_selection)
        page.run_task(_refresh_postgis_connections)

    _sync_geometry_fields()
    _render_fields()
    _update_create_button_state()

    form = ft.Column(
        width=1100,
        spacing=16,
        controls=[
            active_scope_info,
            dd_conn,
            dd_schema,
            tf_dataset_name,
            tf_dataset_alias,
            ft.Row(
                spacing=10,
                controls=[dd_geometry_type, tf_geometry_column, tf_srid],
                wrap=True,
            ),
            ft.Divider(thickness=1),
            ft.Text("Alan (Field) Ayarlari", weight=ft.FontWeight.BOLD),
            ft.Row(
                spacing=10,
                controls=[
                    tf_field_name,
                    tf_field_alias,
                    dd_field_type,
                    tf_field_length,
                    tf_field_precision,
                    tf_field_scale,
                    sw_field_nullable,
                    btn_add_field,
                ],
                wrap=True,
            ),
            ft.Container(
                height=280,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=8,
                padding=10,
                content=fields_panel,
            ),
            summary_text,
            ft.Row(controls=[btn_create]),
        ],
    )

    return ft.Container(
        expand=True,
        bgcolor=ft.Colors.WHITE,
        content=ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Container(
                    expand=True,
                    content=ft.ListView(
                        expand=True,
                        padding=ft.Padding.only(left=36, right=36, top=32, bottom=16),
                        controls=[
                            ft.Container(
                                alignment=ft.Alignment.TOP_CENTER, content=form
                            )
                        ],
                    ),
                ),
                debug_bar,
            ],
        ),
    )

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

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_dbtype(v: str) -> str:
    s = (v or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_esri_dbtype(v: str) -> bool:
    return _normalize_dbtype(v) in (
        "esri geodatabase",
        "enterprise geodatabase",
        "esri enterprise geodatabase",
        "esri",
    )


def build_dbcreateandeditfieldesri_view(page: ft.Page) -> ft.Control:
    active_conn_name, active_schema_name, _ = get_active_db_scope(page)
    use_active_scope = has_active_db_scope(page, "esri")

    state = {
        "conn_name": active_conn_name if use_active_scope else None,
        "last_conn": active_conn_name if use_active_scope else "",
        "schema_name": active_schema_name if use_active_scope else None,
        "last_schema": active_schema_name if use_active_scope else "",
        "dataset_name": None,
        "last_dataset": "",
        "last_field_type": "text",
        "fields": [],
    }

    dd_conn = ft.Dropdown(
        label="Esri DB Baglantisi Secimi",
        hint_text="Kayitli Esri Geodatabase baglantilarindan secim yapiniz",
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
    dd_dataset = ft.Dropdown(
        label="Veri Seti (Tablo) Secimi",
        hint_text="Once sema seciniz",
        expand=True,
        disabled=True,
    )

    tf_field_name = ft.TextField(label="Alan Adi", width=210, disabled=True)
    tf_field_alias = ft.TextField(label="Gorunen Ad (Alias)", width=250, disabled=True)
    dd_field_type = ft.Dropdown(
        label="Alan Tipi",
        value="text",
        width=220,
        disabled=True,
        options=[ft.dropdown.Option(key=k, text=t) for k, t in FIELD_TYPE_OPTIONS],
    )
    tf_field_length = ft.TextField(
        label="Karakter Sayisi",
        hint_text="char/varchar icin 1-10485760",
        width=170,
        disabled=True,
    )
    tf_field_precision = ft.TextField(
        label="Precision",
        hint_text="numeric icin 1-1000",
        width=140,
        disabled=True,
    )
    tf_field_scale = ft.TextField(
        label="Scale",
        hint_text="numeric icin 0+",
        width=130,
        disabled=True,
    )
    sw_field_nullable = ft.Switch(label="Null", value=True, disabled=True)
    btn_add_field = ft.ElevatedButton("Yeni Alan Ekle", disabled=True)

    fields_panel = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
    summary_text = ft.Text("Durum: Once baglanti, sema ve veri seti seciniz.")

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

    def _safe_update(control: ft.Control):
        try:
            control.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

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

    def _selected_scope() -> tuple[str, str, str]:
        return (
            (state.get("conn_name") or "").strip(),
            (state.get("schema_name") or "").strip(),
            (state.get("dataset_name") or "").strip(),
        )

    def _sync_field_type_editor_state(clear_values: bool = False):
        dataset_ok = bool((state.get("dataset_name") or "").strip())
        dtype = (dd_field_type.value or "text").strip().lower()

        supports_length = dataset_ok and _field_type_supports_length(dtype)
        supports_precision = dataset_ok and _field_type_supports_precision(dtype)

        tf_field_length.disabled = not supports_length
        if tf_field_length.disabled and clear_values:
            tf_field_length.value = ""

        tf_field_precision.disabled = not supports_precision
        if tf_field_precision.disabled and clear_values:
            tf_field_precision.value = ""

        tf_field_scale.disabled = not supports_precision
        if tf_field_scale.disabled and clear_values:
            tf_field_scale.value = ""

        _safe_update(tf_field_length)
        _safe_update(tf_field_precision)
        _safe_update(tf_field_scale)

    def _update_editor_enablement(clear_values: bool = False):
        dataset_ok = bool((state.get("dataset_name") or "").strip())

        tf_field_name.disabled = not dataset_ok
        tf_field_alias.disabled = not dataset_ok
        dd_field_type.disabled = not dataset_ok
        sw_field_nullable.disabled = not dataset_ok
        btn_add_field.disabled = not dataset_ok

        if not dataset_ok and clear_values:
            tf_field_name.value = ""
            tf_field_alias.value = ""
            dd_field_type.value = "text"
            tf_field_length.value = ""
            tf_field_precision.value = ""
            tf_field_scale.value = ""
            sw_field_nullable.value = True

        _sync_field_type_editor_state(clear_values=clear_values)

        _safe_update(tf_field_name)
        _safe_update(tf_field_alias)
        _safe_update(dd_field_type)
        _safe_update(sw_field_nullable)
        _safe_update(btn_add_field)

    def _reset_dataset_dropdown():
        dd_dataset.options = []
        dd_dataset.value = None
        dd_dataset.disabled = True

        state["dataset_name"] = None
        state["last_dataset"] = ""
        state["fields"] = []

        _safe_update(dd_dataset)
        _render_fields()
        _update_editor_enablement(clear_values=True)

    def _reset_schema_dropdown():
        dd_schema.options = []
        dd_schema.value = None
        dd_schema.disabled = True
        state["schema_name"] = None
        state["last_schema"] = ""

        _safe_update(dd_schema)
        _reset_dataset_dropdown()

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
        data_type = (data_type or "").strip().lower()
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

        existing = {
            (f.get("name") or "").lower()
            for f in state.get("fields", [])
            if isinstance(f, dict)
        }
        if skip_name:
            existing.discard(skip_name.lower())
        if name.lower() in existing:
            return None, "Ayni alan adi zaten mevcut."

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
                return None, "Scale girildiyse precision da girilmelidir."
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

    def _fmt_ps(fld: dict) -> str:
        p = fld.get("precision")
        s = fld.get("scale")
        if p is None and s is None:
            return "- / -"
        return f"{p if p is not None else '-'} / {s if s is not None else '-'}"

    def _render_fields():
        fields = [f for f in (state.get("fields") or []) if isinstance(f, dict)]
        dataset_name = (state.get("dataset_name") or "").strip()

        if not dataset_name:
            fields_panel.controls = [
                ft.Container(
                    padding=10,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Text("Once baglanti, sema ve veri seti seciniz."),
                )
            ]
            summary_text.value = "Durum: Veri seti secimi bekleniyor."
            _safe_update(fields_panel)
            _safe_update(summary_text)
            return

        if not fields:
            fields_panel.controls = [
                ft.Container(
                    padding=10,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Text("Secilen veri setinde alan bulunamadi."),
                )
            ]
            summary_text.value = "Durum: Alan yok, yeni alan ekleyebilirsiniz."
            _safe_update(fields_panel)
            _safe_update(summary_text)
            return

        rows = [
            ft.Container(
                padding=ft.Padding.only(left=8, right=8, top=6, bottom=6),
                bgcolor=ft.Colors.BLUE_GREY_50,
                border_radius=8,
                content=ft.Row(
                    controls=[
                        ft.Container(width=140, content=ft.Text("Alan Adi", weight=ft.FontWeight.BOLD)),
                        ft.Container(width=170, content=ft.Text("Alias", weight=ft.FontWeight.BOLD)),
                        ft.Container(width=140, content=ft.Text("Tip", weight=ft.FontWeight.BOLD)),
                        ft.Container(width=110, content=ft.Text("Karakter", weight=ft.FontWeight.BOLD)),
                        ft.Container(width=120, content=ft.Text("P / S", weight=ft.FontWeight.BOLD)),
                        ft.Container(width=70, content=ft.Text("Null", weight=ft.FontWeight.BOLD)),
                        ft.Container(width=120, content=ft.Text("Durum", weight=ft.FontWeight.BOLD)),
                        ft.Container(width=150, content=ft.Text("Islem", weight=ft.FontWeight.BOLD)),
                    ]
                ),
            )
        ]

        for fld in fields:
            field_name = (fld.get("name") or "").strip()
            is_system = bool(fld.get("is_system"))
            is_geom = bool(fld.get("is_geometry"))
            lock_reason = ""
            if is_system:
                lock_reason = "Sistem"
            elif is_geom:
                lock_reason = "Geometri"
            else:
                lock_reason = "Normal"

            rows.append(
                ft.Container(
                    padding=ft.Padding.only(left=8, right=8, top=6, bottom=6),
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Row(
                        controls=[
                            ft.Container(width=140, content=ft.Text(field_name, selectable=True)),
                            ft.Container(width=170, content=ft.Text(fld.get("alias") or "-", selectable=True)),
                            ft.Container(width=140, content=ft.Text(fld.get("data_type") or "-", selectable=True)),
                            ft.Container(width=110, content=ft.Text(str(fld.get("length") if fld.get("length") is not None else "-"))),
                            ft.Container(width=120, content=ft.Text(_fmt_ps(fld))),
                            ft.Container(width=70, content=ft.Text("Evet" if bool(fld.get("nullable", True)) else "Hayir")),
                            ft.Container(width=120, content=ft.Text(lock_reason)),
                            ft.Container(
                                width=150,
                                content=ft.Row(
                                    spacing=0,
                                    controls=[
                                        ft.IconButton(
                                            icon=ft.Icons.EDIT_OUTLINED,
                                            tooltip="Guncelle",
                                            disabled=is_system or is_geom,
                                            on_click=lambda e, fn=field_name: _open_edit_field_dialog(fn),
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE_OUTLINE,
                                            tooltip="Sil",
                                            disabled=is_system,
                                            on_click=lambda e, fn=field_name: _confirm_delete_field(fn),
                                        ),
                                    ],
                                ),
                            ),
                        ]
                    ),
                )
            )

        fields_panel.controls = rows
        summary_text.value = f"Durum: {len(fields)} alan listelendi."
        _safe_update(fields_panel)
        _safe_update(summary_text)

    def _clear_field_editor():
        tf_field_name.value = ""
        tf_field_alias.value = ""
        dd_field_type.value = "text"
        tf_field_length.value = ""
        tf_field_precision.value = ""
        tf_field_scale.value = ""
        sw_field_nullable.value = True

        _safe_update(tf_field_name)
        _safe_update(tf_field_alias)
        _safe_update(dd_field_type)
        _safe_update(tf_field_length)
        _safe_update(tf_field_precision)
        _safe_update(tf_field_scale)
        _safe_update(sw_field_nullable)

        _sync_field_type_editor_state(clear_values=True)

    async def _refresh_esri_connections():
        _set_busy(True, "Esri Geodatabase baglantilari yukleniyor...")
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
            _set_debug("UYARILAR: baglanti listesi alinamadi.")
            return

        items = res.get("data") or []
        esri = [
            r
            for r in items
            if isinstance(r, dict)
            and (r.get("Conn_Name") or "").strip()
            and _is_esri_dbtype(str(r.get("DbType") or ""))
        ]
        dd_conn.options = [
            ft.dropdown.Option(
                key=r["Conn_Name"],
                text=f'{r["Conn_Name"]} ({r.get("DbType", "-")})',
            )
            for r in esri
        ]
        dd_conn.value = None
        state["conn_name"] = None
        state["last_conn"] = ""

        _reset_schema_dropdown()
        _safe_update(dd_conn)
        _set_debug(f"UYARILAR: {len(esri)} Esri Geodatabase baglantisi yuklendi.")

    async def _load_schemas_for_conn(conn_name: str):
        state["conn_name"] = conn_name or None
        _reset_schema_dropdown()

        if not conn_name:
            _set_debug("UYARILAR: baglanti secimi temizlendi.")
            return

        _set_busy(True, "Sema listesi aliniyor...")
        try:
            res = await asyncio.to_thread(page.api.createandeditfieldesri_list_schemas, conn_name)
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
        dd_schema.disabled = not bool(schemas)
        _safe_update(dd_schema)
        _set_debug(f"UYARILAR: {len(schemas)} sema yuklendi.")

    async def _load_datasets_for_schema(schema_name: str):
        state["schema_name"] = schema_name or None
        _reset_dataset_dropdown()

        conn_name = (state.get("conn_name") or "").strip()
        if not conn_name or not schema_name:
            if not schema_name:
                _set_debug("UYARILAR: sema secimi temizlendi.")
            return

        _set_busy(True, "Veri setleri aliniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.createandeditfieldesri_list_datasets,
                conn_name,
                schema_name,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Veri setleri alinamadi.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug(f"UYARILAR: veri seti listesi alinamadi | {schema_name}")
            return

        datasets = [s for s in (res.get("data") or []) if (s or "").strip()]
        dd_dataset.options = [ft.dropdown.Option(key=s, text=s) for s in datasets]
        dd_dataset.disabled = not bool(datasets)
        _safe_update(dd_dataset)
        _set_debug(f"UYARILAR: {len(datasets)} veri seti yuklendi.")

    async def _load_fields_for_dataset(dataset_name: str):
        state["dataset_name"] = dataset_name or None
        state["fields"] = []
        _render_fields()
        _update_editor_enablement(clear_values=True)

        conn_name, schema_name, ds_name = _selected_scope()
        if not conn_name or not schema_name or not ds_name:
            if not ds_name:
                _set_debug("UYARILAR: veri seti secimi temizlendi.")
            return

        _set_busy(True, "Alanlar aliniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.createandeditfieldesri_list_fields,
                conn_name,
                schema_name,
                ds_name,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Alanlar alinamadi.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug(f"UYARILAR: alanlar alinamadi | {schema_name}.{ds_name}")
            return

        fields = [f for f in (res.get("data") or []) if isinstance(f, dict)]
        state["fields"] = fields
        _render_fields()
        _update_editor_enablement(clear_values=False)
        _set_debug(f"UYARILAR: {len(fields)} alan yuklendi | {schema_name}.{ds_name}")

    def _on_field_type_change(e):
        state["last_field_type"] = (dd_field_type.value or "text").strip().lower()
        _sync_field_type_editor_state(clear_values=True)

    async def on_conn_change(e):
        cur = (dd_conn.value or "").strip()
        state["last_conn"] = cur
        await _load_schemas_for_conn(cur)

    async def on_schema_change(e):
        cur = (dd_schema.value or "").strip()
        state["last_schema"] = cur
        conn_name = (state.get("conn_name") or "").strip()
        if conn_name and cur:
            set_active_db_scope(page, conn_name, cur, "esri")
        await _load_datasets_for_schema(cur)

    async def on_dataset_change(e):
        cur = (dd_dataset.value or "").strip()
        state["last_dataset"] = cur
        await _load_fields_for_dataset(cur)

    async def _on_add_field_click(e):
        conn_name, schema_name, dataset_name = _selected_scope()
        if not conn_name or not schema_name or not dataset_name:
            _notify("Uyari", "Once baglanti, sema ve veri seti seciniz.")
            return

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

        _set_busy(True, "Yeni alan ekleniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.createandeditfieldesri_add_field,
                conn_name,
                schema_name,
                dataset_name,
                field_obj,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Alan eklenemedi.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug(f"UYARILAR: alan ekleme basarisiz | {field_obj.get('name','')}")
            return

        _clear_field_editor()
        await _load_fields_for_dataset(dataset_name)
        _set_debug(f"UYARILAR: alan eklendi | {field_obj.get('name','')}")
        _notify("Basarili", res.get("message") or "Alan eklendi.")

    def _confirm_delete_field(field_name: str):
        if not field_name:
            return

        dlg = ft.AlertDialog(modal=True)
        dlg.title = ft.Text("Onay")
        dlg.content = ft.Text(
            f"Silmek Istediginizden Eminmisiniz?\nAlan: {field_name}"
        )

        async def _delete_now():
            conn_name, schema_name, dataset_name = _selected_scope()
            if not conn_name or not schema_name or not dataset_name:
                _notify("Uyari", "Baglanti/scope bilgisi eksik.")
                return

            _set_busy(True, "Alan siliniyor...")
            try:
                res = await asyncio.to_thread(
                    page.api.createandeditfieldesri_delete_field,
                    conn_name,
                    schema_name,
                    dataset_name,
                    field_name,
                )
            finally:
                _set_busy(False)

            if not isinstance(res, dict) or not res.get("ok"):
                msg = (res or {}).get("message", "Alan silinemedi.")
                dbg = (res or {}).get("debug", "")
                _notify("Hata", f"{msg}\n\n{dbg}".strip())
                _set_debug(f"UYARILAR: alan silme basarisiz | {field_name}")
                return

            await _load_fields_for_dataset(dataset_name)
            _set_debug(f"UYARILAR: alan silindi | {field_name}")
            _notify("Basarili", res.get("message") or "Alan silindi.")

        def _yes(e):
            _close_dialog(dlg)
            page.run_task(_delete_now)

        def _no(e):
            _close_dialog(dlg)

        dlg.actions = [
            ft.TextButton("Hayir", on_click=_no),
            ft.ElevatedButton("Evet", on_click=_yes),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(dlg)

    def _open_edit_field_dialog(field_name: str):
        current = None
        for fld in state.get("fields", []):
            if (fld.get("name") or "").strip().lower() == (field_name or "").strip().lower():
                current = fld
                break

        if not isinstance(current, dict):
            _notify("Uyari", "Guncellenecek alan bulunamadi.")
            return

        tf_edit_name = ft.TextField(label="Alan Adi", value=current.get("name") or "", width=210)
        tf_edit_alias = ft.TextField(label="Gorunen Ad (Alias)", value=current.get("alias") or "", width=250)
        dd_edit_type = ft.Dropdown(
            label="Alan Tipi",
            value=(current.get("data_type") or "text").lower(),
            width=220,
            options=[ft.dropdown.Option(key=k, text=t) for k, t in FIELD_TYPE_OPTIONS],
        )
        tf_edit_length = ft.TextField(
            label="Karakter Sayisi",
            hint_text="char/varchar icin 1-10485760",
            width=170,
            value=str(current.get("length")) if current.get("length") is not None else "",
        )
        tf_edit_precision = ft.TextField(
            label="Precision",
            hint_text="numeric icin 1-1000",
            width=140,
            value=str(current.get("precision")) if current.get("precision") is not None else "",
        )
        tf_edit_scale = ft.TextField(
            label="Scale",
            hint_text="numeric icin 0+",
            width=130,
            value=str(current.get("scale")) if current.get("scale") is not None else "",
        )
        sw_edit_nullable = ft.Switch(label="Null", value=bool(current.get("nullable", True)))

        def _sync_edit_type(clear_values: bool = False):
            dtype = (dd_edit_type.value or "text").strip().lower()
            supports_length = _field_type_supports_length(dtype)
            supports_precision = _field_type_supports_precision(dtype)

            tf_edit_length.disabled = not supports_length
            if tf_edit_length.disabled and clear_values:
                tf_edit_length.value = ""

            tf_edit_precision.disabled = not supports_precision
            if tf_edit_precision.disabled and clear_values:
                tf_edit_precision.value = ""

            tf_edit_scale.disabled = not supports_precision
            if tf_edit_scale.disabled and clear_values:
                tf_edit_scale.value = ""

            _safe_update(tf_edit_length)
            _safe_update(tf_edit_precision)
            _safe_update(tf_edit_scale)

        dd_edit_type.on_change = lambda e: _sync_edit_type(clear_values=True)
        _sync_edit_type(clear_values=False)

        dlg = ft.AlertDialog(modal=True)
        dlg.title = ft.Text("Alan Guncelle")
        dlg.content = ft.Container(
            width=980,
            content=ft.Column(
                tight=True,
                controls=[
                    ft.Row(
                        spacing=10,
                        wrap=True,
                        controls=[
                            tf_edit_name,
                            tf_edit_alias,
                            dd_edit_type,
                            tf_edit_length,
                            tf_edit_precision,
                            tf_edit_scale,
                            sw_edit_nullable,
                        ],
                    )
                ],
            ),
        )

        async def _save_async():
            conn_name, schema_name, dataset_name = _selected_scope()
            if not conn_name or not schema_name or not dataset_name:
                _notify("Uyari", "Baglanti/scope bilgisi eksik.")
                return

            field_obj, err = _build_validated_field(
                tf_edit_name.value or "",
                tf_edit_alias.value or "",
                dd_edit_type.value or "",
                tf_edit_length.value or "",
                tf_edit_precision.value or "",
                tf_edit_scale.value or "",
                bool(sw_edit_nullable.value),
                skip_name=current.get("name") or "",
            )
            if err:
                _notify("Uyari", err)
                return

            _set_busy(True, "Alan guncelleniyor...")
            try:
                res = await asyncio.to_thread(
                    page.api.createandeditfieldesri_update_field,
                    conn_name,
                    schema_name,
                    dataset_name,
                    current.get("name") or "",
                    field_obj,
                )
            finally:
                _set_busy(False)

            if not isinstance(res, dict) or not res.get("ok"):
                msg = (res or {}).get("message", "Alan guncellenemedi.")
                dbg = (res or {}).get("debug", "")
                _notify("Hata", f"{msg}\n\n{dbg}".strip())
                _set_debug(
                    f"UYARILAR: alan guncelleme basarisiz | {current.get('name','')}"
                )
                return

            _close_dialog(dlg)
            await _load_fields_for_dataset(dataset_name)
            _set_debug(
                f"UYARILAR: alan guncellendi | {current.get('name','')} -> {field_obj.get('name','')}"
            )
            _notify("Basarili", res.get("message") or "Alan guncellendi.")

        def _save(e):
            page.run_task(_save_async)

        def _cancel(e):
            _close_dialog(dlg)

        dlg.actions = [
            ft.TextButton("Vazgec", on_click=_cancel),
            ft.ElevatedButton("Kaydet", on_click=_save),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_dialog(dlg)

    async def _watch_conn_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_conn.value or "").strip()
            if cur == (state.get("last_conn") or ""):
                continue
            state["last_conn"] = cur
            await _load_schemas_for_conn(cur)

    async def _watch_schema_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_schema.value or "").strip()
            if cur == (state.get("last_schema") or ""):
                continue
            state["last_schema"] = cur
            await _load_datasets_for_schema(cur)

    async def _watch_dataset_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_dataset.value or "").strip()
            if cur == (state.get("last_dataset") or ""):
                continue
            state["last_dataset"] = cur
            await _load_fields_for_dataset(cur)

    async def _watch_field_type_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_field_type.value or "text").strip().lower()
            if cur == (state.get("last_field_type") or ""):
                continue
            state["last_field_type"] = cur
            _sync_field_type_editor_state(clear_values=True)

    dd_conn.on_change = lambda e: page.run_task(on_conn_change, e)
    dd_schema.on_change = lambda e: page.run_task(on_schema_change, e)
    dd_dataset.on_change = lambda e: page.run_task(on_dataset_change, e)

    dd_field_type.on_change = _on_field_type_change
    btn_add_field.on_click = lambda e: page.run_task(_on_add_field_click, e)

    if use_active_scope:
        page.run_task(_watch_dataset_selection)
        page.run_task(_watch_field_type_selection)
        page.run_task(_load_datasets_for_schema, active_schema_name)
    else:
        page.run_task(_watch_conn_selection)
        page.run_task(_watch_schema_selection)
        page.run_task(_watch_dataset_selection)
        page.run_task(_watch_field_type_selection)
        page.run_task(_refresh_esri_connections)

    _render_fields()
    _update_editor_enablement(clear_values=True)

    form = ft.Column(
        width=1120,
        spacing=16,
        controls=[
            active_scope_info,
            dd_conn,
            dd_schema,
            dd_dataset,
            ft.Divider(thickness=1),
            ft.Text("Yeni Alan Ekle", weight=ft.FontWeight.BOLD),
            ft.Row(
                spacing=10,
                wrap=True,
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
            ),
            ft.Text("Secilen Veri Seti Alanlari", weight=ft.FontWeight.BOLD),
            ft.Container(
                height=380,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=8,
                padding=10,
                content=fields_panel,
            ),
            summary_text,
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
                                alignment=ft.Alignment.TOP_CENTER,
                                content=form,
                            )
                        ],
                    ),
                ),
                debug_bar,
            ],
        ),
    )

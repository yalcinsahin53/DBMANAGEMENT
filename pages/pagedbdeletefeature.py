import asyncio

import flet as ft

from core.active_db_scope import get_active_db_scope, has_active_db_scope, set_active_db_scope


def build_dbdeletefeature_view(page: ft.Page) -> ft.Control:
    active_conn_name, active_schema_name, _ = get_active_db_scope(page)
    use_active_scope = has_active_db_scope(page, "postgis")

    state = {
        "conn_name": active_conn_name if use_active_scope else None,
        "last_conn": active_conn_name if use_active_scope else "",
        "schema_name": active_schema_name if use_active_scope else None,
        "last_schema": active_schema_name if use_active_scope else "",
        "datasets": [],
        "selected": set(),
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

    btn_list = ft.ElevatedButton("Veri Seti Listele", disabled=True)
    btn_delete = ft.ElevatedButton("Secilen Veri Setlerini Sil", disabled=True)

    summary_text = ft.Text("Durum: Once baglanti ve sema seciniz.")
    datasets_panel = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

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
            return
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

        page.dialog = dlg
        dlg.open = True
        page.update()

    def _close_dialog(dlg: ft.AlertDialog):
        if hasattr(page, "close"):
            try:
                page.close(dlg)
                return
            except Exception:
                pass
        dlg.open = False
        if getattr(page, "dialog", None) is dlg:
            page.dialog = None
        page.update()

    def _set_busy(on: bool, text: str = ""):
        busy.visible = on
        busy_text.visible = on
        busy_text.value = text or ""
        page.update()

    def _set_debug(msg: str):
        debug_lbl.value = msg
        _safe_update(debug_lbl)

    def _update_buttons_state():
        conn_ok = bool((state.get("conn_name") or "").strip())
        schema_ok = bool((state.get("schema_name") or "").strip())
        btn_list.disabled = not (conn_ok and schema_ok)
        btn_delete.disabled = len(state.get("selected") or set()) == 0
        _safe_update(btn_list)
        _safe_update(btn_delete)

    def _reset_dataset_list(message: str = "Durum: Once baglanti ve sema seciniz."):
        state["datasets"] = []
        state["selected"] = set()
        datasets_panel.controls = [
            ft.Container(
                padding=10,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=8,
                content=ft.Text("Liste bos."),
            )
        ]
        summary_text.value = message
        _safe_update(datasets_panel)
        _safe_update(summary_text)
        _update_buttons_state()

    def _render_dataset_list():
        datasets = [str(x) for x in (state.get("datasets") or []) if str(x).strip()]

        if not datasets:
            datasets_panel.controls = [
                ft.Container(
                    padding=10,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Text("Secilen semada veri seti bulunamadi."),
                )
            ]
            summary_text.value = "Durum: Veri seti bulunamadi."
            _safe_update(datasets_panel)
            _safe_update(summary_text)
            _update_buttons_state()
            return

        rows = []

        def _on_select_all(e):
            checked = bool(getattr(e.control, "value", False))
            if checked:
                state["selected"] = set(datasets)
            else:
                state["selected"] = set()
            _render_dataset_list()

        all_selected = len(state.get("selected") or set()) == len(datasets)
        rows.append(
            ft.Container(
                padding=ft.Padding.only(left=6, right=6, top=2, bottom=2),
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=8,
                bgcolor=ft.Colors.BLUE_GREY_50,
                content=ft.Row(
                    controls=[
                        ft.Checkbox(label="Tumunu Sec", value=all_selected, on_change=_on_select_all),
                        ft.Text(f"Toplam: {len(datasets)}"),
                    ]
                ),
            )
        )

        for ds in datasets:
            checked = ds in state.get("selected", set())

            def _on_item_change(e, name=ds):
                if bool(getattr(e.control, "value", False)):
                    state["selected"].add(name)
                else:
                    state["selected"].discard(name)
                _update_buttons_state()
                summary_text.value = (
                    f"Durum: {len(state['selected'])} veri seti secildi."
                )
                _safe_update(summary_text)

            rows.append(
                ft.Container(
                    padding=ft.Padding.only(left=6, right=6, top=2, bottom=2),
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Checkbox(label=ds, value=checked, on_change=_on_item_change),
                )
            )

        datasets_panel.controls = rows
        summary_text.value = f"Durum: {len(datasets)} veri seti listelendi. {len(state['selected'])} secili."
        _safe_update(datasets_panel)
        _safe_update(summary_text)
        _update_buttons_state()

    def _reset_schema_dropdown():
        dd_schema.options = []
        dd_schema.value = None
        dd_schema.disabled = True
        state["schema_name"] = None
        state["last_schema"] = ""
        _safe_update(dd_schema)
        _reset_dataset_list("Durum: Once baglanti seciniz.")

    async def _refresh_postgis_connections():
        _set_busy(True, "PostGIS baglantilari yukleniyor...")
        try:
            res = await asyncio.to_thread(page.api.db_list)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            dd_conn.options = []
            dd_conn.value = None
            state["conn_name"] = None
            state["last_conn"] = ""
            _safe_update(dd_conn)
            _reset_schema_dropdown()
            _notify("Hata", (res or {}).get("message", "Baglantilar okunamadi."))
            _set_debug("UYARILAR: baglanti listesi alinamadi.")
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
        _safe_update(dd_conn)
        _reset_schema_dropdown()
        _set_debug(f"UYARILAR: {len(postgis)} PostGIS baglantisi yuklendi.")
        _update_buttons_state()

    async def _load_schemas_for_conn(conn_name: str):
        state["conn_name"] = conn_name or None
        _reset_schema_dropdown()

        if not conn_name:
            _set_debug("UYARILAR: baglanti secimi temizlendi.")
            _update_buttons_state()
            return

        _set_busy(True, "Sema listesi aliniyor...")
        try:
            res = await asyncio.to_thread(page.api.dbdeletefeature_list_schemas, conn_name)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Sema listesi alinamadi.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug(f"UYARILAR: sema listesi alinamadi | {conn_name}")
            _update_buttons_state()
            return

        schemas = [s for s in (res.get("data") or []) if (s or "").strip()]
        dd_schema.options = [ft.dropdown.Option(key=s, text=s) for s in schemas]
        dd_schema.disabled = not bool(schemas)
        _safe_update(dd_schema)
        _set_debug(f"UYARILAR: {len(schemas)} sema yuklendi.")
        _update_buttons_state()

    async def on_conn_change(e):
        cur = (dd_conn.value or "").strip()
        state["last_conn"] = cur
        await _load_schemas_for_conn(cur)

    async def on_schema_change(e):
        cur = (dd_schema.value or "").strip()
        state["schema_name"] = cur or None
        state["last_schema"] = cur
        conn_name = (state.get("conn_name") or "").strip()
        if conn_name and cur:
            set_active_db_scope(page, conn_name, cur, "postgis")
        _reset_dataset_list("Durum: Veri setlerini listelemek icin butona basin.")
        _update_buttons_state()

    async def on_list_click(e):
        conn_name = (state.get("conn_name") or "").strip()
        schema_name = (state.get("schema_name") or "").strip()

        if not conn_name:
            _notify("Uyari", "Lutfen PostGIS baglantisi seciniz.")
            return
        if not schema_name:
            _notify("Uyari", "Lutfen sema seciniz.")
            return

        _set_busy(True, "Veri setleri listeleniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.dbdeletefeature_list_datasets,
                conn_name,
                schema_name,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Veri setleri listelenemedi.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug(f"UYARILAR: veri setleri listelenemedi | {schema_name}")
            return

        datasets = [d for d in (res.get("data") or []) if (d or "").strip()]
        state["datasets"] = datasets
        state["selected"] = set()
        _render_dataset_list()
        _set_debug(f"UYARILAR: {len(datasets)} veri seti listelendi | {schema_name}")

    def _confirm_delete_dialog():
        selected = sorted(list(state.get("selected") or set()), key=lambda s: s.lower())
        if not selected:
            _notify("Uyari", "Lutfen silmek icin en az bir veri seti seciniz.")
            return

        preview = "\n".join([f"- {x}" for x in selected[:20]])
        if len(selected) > 20:
            preview += f"\n... (+{len(selected)-20} adet daha)"

        dlg = ft.AlertDialog(modal=True)
        dlg.title = ft.Text("Onay")
        dlg.content = ft.Text(
            (
                "Secilen veri setleri silinecek. Emin misiniz?\n\n"
                f"Toplam secim: {len(selected)}\n"
                f"{preview}"
            ),
            selectable=True,
        )

        async def _delete_now():
            conn_name = (state.get("conn_name") or "").strip()
            schema_name = (state.get("schema_name") or "").strip()
            if not conn_name or not schema_name:
                _notify("Uyari", "Baglanti/scope bilgisi eksik.")
                return

            _set_busy(True, "Secilen veri setleri siliniyor...")
            try:
                res = await asyncio.to_thread(
                    page.api.dbdeletefeature_delete_datasets,
                    conn_name,
                    schema_name,
                    selected,
                )
            finally:
                _set_busy(False)

            if not isinstance(res, dict) or not res.get("ok"):
                msg = (res or {}).get("message", "Silme islemi basarisiz.")
                dbg = (res or {}).get("debug", "")
                _notify("Hata", f"{msg}\n\n{dbg}".strip())
                _set_debug("UYARILAR: veri seti silme basarisiz.")
                return

            data = res.get("data") or {}
            deleted = data.get("deleted") or []
            missing = data.get("missing") or []
            detail = f"Silinen: {len(deleted)}"
            if missing:
                detail += f"\nBulunamayan: {len(missing)}"
            _notify("Basarili", f"{res.get('message') or 'Islem tamamlandi.'}\n\n{detail}")
            _set_debug(f"UYARILAR: silme tamamlandi | deleted={len(deleted)} | missing={len(missing)}")

            # Listeyi yenile
            await on_list_click(None)

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
            state["schema_name"] = cur or None
            _reset_dataset_list("Durum: Veri setlerini listelemek icin butona basin.")
            _update_buttons_state()

    dd_conn.on_change = lambda e: page.run_task(on_conn_change, e)
    dd_schema.on_change = lambda e: page.run_task(on_schema_change, e)
    btn_list.on_click = lambda e: page.run_task(on_list_click, e)
    btn_delete.on_click = lambda e: _confirm_delete_dialog()

    if use_active_scope:
        _update_buttons_state()
    else:
        page.run_task(_watch_conn_selection)
        page.run_task(_watch_schema_selection)
        page.run_task(_refresh_postgis_connections)

    _reset_dataset_list("Durum: Once baglanti ve sema seciniz.")

    form = ft.Column(
        width=1020,
        spacing=14,
        controls=[
            active_scope_info,
            dd_conn,
            dd_schema,
            ft.Row(
                controls=[btn_list, btn_delete],
                alignment=ft.MainAxisAlignment.START,
            ),
            summary_text,
            ft.Container(
                height=560,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=8,
                padding=10,
                content=datasets_panel,
            ),
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
                        controls=[ft.Container(alignment=ft.Alignment.TOP_CENTER, content=form)],
                    ),
                ),
                debug_bar,
            ],
        ),
    )

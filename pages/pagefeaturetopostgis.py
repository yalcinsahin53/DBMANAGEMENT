import asyncio
import flet as ft

from core.active_db_scope import get_active_db_scope, has_active_db_scope, set_active_db_scope


def build_featuretopostgis_view(page: ft.Page) -> ft.Control:
    active_conn_name, active_schema_name, _ = get_active_db_scope(page)
    use_active_scope = has_active_db_scope(page, "postgis")

    state = {
        "conn_name": active_conn_name if use_active_scope else None,
        "last_conn": active_conn_name if use_active_scope else None,
        "schema_name": active_schema_name if use_active_scope else None,
        "last_schema": active_schema_name if use_active_scope else None,
        "file_path": None,
    }

    dd_conn = ft.Dropdown(
        label="PostGIS Bağlantısı Seçimi",
        hint_text="Kayıtlı PostGIS bağlantılarından seçim yapınız",
        expand=True,
        visible=not use_active_scope,
    )

    dd_schema = ft.Dropdown(
        label="PostGIS Şema Seçimi",
        hint_text="Önce bağlantı seçiniz",
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

    tf_file = ft.TextField(
        label="Seçilen Vektör Dosyası",
        hint_text="gml, shp veya xml dosyası seçiniz",
        read_only=True,
        expand=True,
    )

    btn_pick = ft.ElevatedButton("Vektör Dosyası Seç (.gml / .shp / .xml)")
    btn_import = ft.ElevatedButton("PostGIS'e Aktar", disabled=True)

    busy = ft.ProgressRing(visible=False)
    busy_text = ft.Text("", visible=False)
    debug_lbl = ft.Text("UYARILAR: hazır", size=12, selectable=True)

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

    def _safe_update(control: ft.Control):
        try:
            control.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

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
        try:
            page.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

    def _update_import_button_state():
        conn_name = (dd_conn.value or state.get("conn_name") or "").strip()
        schema_name = (dd_schema.value or state.get("schema_name") or "").strip()
        file_path = (tf_file.value or state.get("file_path") or "").strip()

        state["conn_name"] = conn_name or None
        state["schema_name"] = schema_name or None
        state["file_path"] = file_path or None

        conn_ok = bool(conn_name)
        schema_ok = bool(schema_name)
        file_ok = bool(file_path)
        btn_import.disabled = not (conn_ok and schema_ok and file_ok)
        _safe_update(btn_import)

    def _reset_schema_dropdown():
        dd_schema.options = []
        dd_schema.value = None
        dd_schema.disabled = True
        state["schema_name"] = None
        _safe_update(dd_schema)
        _update_import_button_state()

    def api_db_list():
        return page.api.db_list()

    def api_list_schemas(conn_name: str):
        return page.api.postgis_list_schemas(conn_name)

    def api_import(conn_name: str, schema_name: str, file_path: str, manual_epsg: int | None = None):
        return page.api.postgis_import_vector(conn_name, schema_name, file_path, manual_epsg)

    async def refresh_postgis_connections():
        _set_busy(True, "PostGIS bağlantıları yükleniyor...")
        try:
            res = await asyncio.to_thread(api_db_list)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", (res or {}).get("message", "Bağlantılar okunamadı."))
            dd_conn.options = []
            dd_conn.value = None
            _reset_schema_dropdown()
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
        _reset_schema_dropdown()

        debug_lbl.value = f"UYARILAR: {len(postgis)} PostGIS bağlantısı yüklendi."
        try:
            page.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

    async def _load_schemas_for_conn(conn_name: str):
        state["conn_name"] = conn_name or None
        _reset_schema_dropdown()

        if not conn_name:
            debug_lbl.value = "UYARILAR: bağlantı seçimi temizlendi."
            _safe_update(debug_lbl)
            return

        _set_busy(True, "Şema listesi alınıyor...")
        try:
            res = await asyncio.to_thread(api_list_schemas, conn_name)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Şema listesi alınamadı.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            debug_lbl.value = f"UYARILAR: şema listesi alınamadı | {conn_name}"
            _safe_update(debug_lbl)
            return

        schemas = [s for s in (res.get("data") or []) if (s or "").strip()]
        dd_schema.options = [ft.dropdown.Option(key=s, text=s) for s in schemas]
        dd_schema.disabled = False
        _safe_update(dd_schema)

        debug_lbl.value = f"UYARILAR: {len(schemas)} şema yüklendi | {conn_name}"
        _safe_update(debug_lbl)

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
            _update_import_button_state()
            debug_lbl.value = f"UYARILAR: şema seçildi | {cur}" if cur else "UYARILAR: şema seçimi temizlendi."
            _safe_update(debug_lbl)

    async def on_conn_change(e):
        conn_name = (dd_conn.value or "").strip()
        state["last_conn"] = conn_name
        await _load_schemas_for_conn(conn_name)

    def on_schema_change(e):
        schema_name = (dd_schema.value or "").strip()
        state["last_schema"] = schema_name
        state["schema_name"] = schema_name or None
        conn_name = (state.get("conn_name") or "").strip()
        if conn_name and schema_name:
            set_active_db_scope(page, conn_name, schema_name, "postgis")
        _update_import_button_state()

    async def on_pick_click(e):
        try:
            picked = await ft.FilePicker().pick_files(
                dialog_title="Vektör dosyası seçiniz (.gml / .shp / .xml)",
                allow_multiple=False,
                allowed_extensions=["gml", "xml", "shp"],
            )
        except Exception as ex:
            _notify("Hata", f"Dosya seçim penceresi açılamadı.\n{ex}")
            return

        files = picked or []
        if not files:
            _notify("Bilgi", "Dosya seçimi iptal edildi.")
            return

        file_path = (files[0].path or "").strip()
        if not file_path:
            _notify("Hata", "Seçilen dosya yolu okunamadı.")
            return

        state["file_path"] = file_path
        tf_file.value = file_path
        _safe_update(tf_file)
        _update_import_button_state()

        debug_lbl.value = f"UYARILAR: dosya seçildi | {file_path}"
        _safe_update(debug_lbl)

    async def on_import_click(e):
        conn_name = (state.get("conn_name") or "").strip()
        schema_name = (state.get("schema_name") or "").strip()
        file_path = (state.get("file_path") or "").strip()

        if not conn_name:
            _notify("Uyarı", "Lütfen PostGIS bağlantısı seçiniz.")
            return
        if not schema_name:
            _notify("Uyarı", "Lütfen PostGIS şema seçiniz.")
            return
        if not file_path:
            _notify("Uyarı", "Lütfen bir vektör dosyası seçiniz.")
            return

        async def _run_import(manual_epsg: int | None = None):
            _set_busy(True, "Vektör veri PostGIS'e aktarılıyor...")
            try:
                return await asyncio.to_thread(
                    api_import, conn_name, schema_name, file_path, manual_epsg
                )
            finally:
                _set_busy(False)

        async def _prompt_epsg_and_retry(base_message: str, base_debug: str):
            tf_epsg = ft.TextField(
                label="EPSG Kodu",
                hint_text="Ornek: 4326",
                width=220,
                autofocus=True,
            )
            hint_text = base_message or "Koordinat sistemi tanimli degil."
            if base_debug:
                hint_text += f"\n\n{base_debug}"

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("EPSG Gerekli"),
                content=ft.Column(
                    tight=True,
                    controls=[
                        ft.Text(hint_text, selectable=True),
                        tf_epsg,
                    ],
                ),
            )

            async def _submit_with_epsg(_):
                raw = (tf_epsg.value or "").strip()
                try:
                    epsg = int(raw)
                    if epsg <= 0:
                        raise ValueError
                except Exception:
                    _notify("Uyari", "Gecerli bir EPSG kodu giriniz.")
                    return

                _close_dialog(dlg)
                retry_res = await _run_import(epsg)
                if not isinstance(retry_res, dict) or not retry_res.get("ok"):
                    msg = (retry_res or {}).get("message", "Aktarim basarisiz.")
                    dbg = (retry_res or {}).get("debug", "")
                    _notify("Hata", f"{msg}\n\n{dbg}".strip())
                    debug_lbl.value = "UYARILAR: aktarim basarisiz."
                    _safe_update(debug_lbl)
                    return

                _notify("Basarili", retry_res.get("message") or "Aktarim tamamlandi.")
                debug_lbl.value = "UYARILAR: aktarim basarili."
                _safe_update(debug_lbl)

            def _cancel(_):
                _close_dialog(dlg)
                _notify("Bilgi", "Aktarim islemi iptal edildi.")
                debug_lbl.value = "UYARILAR: aktarim iptal edildi."
                _safe_update(debug_lbl)

            dlg.actions = [
                ft.TextButton("Iptal", on_click=_cancel),
                ft.ElevatedButton("Devam Et", on_click=lambda ev: page.run_task(_submit_with_epsg, ev)),
            ]
            dlg.actions_alignment = ft.MainAxisAlignment.END
            _open_dialog(dlg)

        res = await _run_import()

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Aktarım başarısız.")
            dbg = (res or {}).get("debug", "")
            if bool((res or {}).get("requires_epsg")):
                await _prompt_epsg_and_retry(msg, dbg)
                return
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            debug_lbl.value = "UYARILAR: aktarım başarısız."
            _safe_update(debug_lbl)
            return

        _notify("Başarılı", res.get("message") or "Aktarım tamamlandı.")
        debug_lbl.value = "UYARILAR: aktarım başarılı."
        _safe_update(debug_lbl)

    dd_conn.on_change = lambda e: page.run_task(on_conn_change, e)
    dd_schema.on_change = on_schema_change
    btn_pick.on_click = lambda e: page.run_task(on_pick_click, e)
    btn_import.on_click = lambda e: page.run_task(on_import_click, e)

    if use_active_scope:
        _update_import_button_state()
    else:
        page.run_task(refresh_postgis_connections)
        page.run_task(_watch_conn_selection)
        page.run_task(_watch_schema_selection)

    form = ft.Column(
        width=900,
        spacing=16,
        controls=[
            active_scope_info,
            dd_conn,
            dd_schema,
            ft.Row(spacing=12, controls=[tf_file, btn_pick]),
            ft.Row(controls=[btn_import]),
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
                        padding=ft.Padding.only(left=48, right=48, top=64, bottom=24),
                        controls=[
                            ft.Container(alignment=ft.Alignment.TOP_CENTER, content=form)
                        ],
                    ),
                ),
                debug_bar,
            ],
        ),
    )

import asyncio
import flet as ft

from core.active_db_scope import get_active_db_scope, has_active_db_scope, set_active_db_scope


def build_dbcreatefeaturefromxsd_view(page: ft.Page) -> ft.Control:
    active_conn_name, active_schema_name, _ = get_active_db_scope(page)
    use_active_scope = has_active_db_scope(page, "postgis")

    state = {
        "conn_name": active_conn_name if use_active_scope else None,
        "last_conn": active_conn_name if use_active_scope else None,
        "schema_name": active_schema_name if use_active_scope else None,
        "last_schema": active_schema_name if use_active_scope else None,
        "xsd_path": None,
    }

    dd_conn = ft.Dropdown(
        label="PostGIS Bağlantısı Seçimi",
        hint_text="Kayıtlı PostGIS bağlantılarından seçim yapınız",
        expand=True,
        visible=not use_active_scope,
    )
    dd_schema = ft.Dropdown(
        label="Şema Seçimi",
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

    tf_xsd = ft.TextField(
        label="Seçilen XSD Dosyası",
        hint_text=".xsd dosyası seçiniz",
        read_only=True,
        expand=True,
    )

    btn_pick = ft.ElevatedButton("XSD Dosyası Seç (.xsd)")
    btn_create = ft.ElevatedButton("Veri Setlerini Oluştur", disabled=True)

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

    def _set_busy(on: bool, text: str = ""):
        busy.visible = on
        busy_text.visible = on
        busy_text.value = text or ""
        try:
            page.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

    def _update_create_button_state():
        conn_name = (dd_conn.value or state.get("conn_name") or "").strip()
        schema_name = (dd_schema.value or state.get("schema_name") or "").strip()
        xsd_path = (tf_xsd.value or state.get("xsd_path") or "").strip()

        state["conn_name"] = conn_name or None
        state["schema_name"] = schema_name or None
        state["xsd_path"] = xsd_path or None

        btn_create.disabled = not (
            bool(conn_name) and bool(schema_name) and bool(xsd_path)
        )
        _safe_update(btn_create)

    def _reset_schema_dropdown():
        dd_schema.options = []
        dd_schema.value = None
        dd_schema.disabled = True
        state["schema_name"] = None
        _safe_update(dd_schema)
        _update_create_button_state()

    def api_db_list():
        return page.api.db_list()

    def api_list_schemas(conn_name: str):
        return page.api.postgis_list_schemas(conn_name)

    def api_create(conn_name: str, schema_name: str, xsd_path: str):
        return page.api.postgis_create_features_from_xsd(
            conn_name, schema_name, xsd_path
        )

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
        page.update()

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

    async def on_conn_change(e):
        conn_name = (dd_conn.value or "").strip()
        state["last_conn"] = conn_name
        state["conn_name"] = conn_name or None
        await _load_schemas_for_conn(conn_name)

    def on_schema_change(e):
        schema_name = (dd_schema.value or "").strip()
        state["last_schema"] = schema_name
        state["schema_name"] = schema_name or None
        conn_name = (state.get("conn_name") or "").strip()
        if conn_name and schema_name:
            set_active_db_scope(page, conn_name, schema_name, "postgis")
        _update_create_button_state()
        debug_lbl.value = (
            f"UYARILAR: şema seçildi | {schema_name}"
            if schema_name
            else "UYARILAR: şema seçimi temizlendi."
        )
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
            _update_create_button_state()
            debug_lbl.value = (
                f"UYARILAR: şema seçildi | {cur}"
                if cur
                else "UYARILAR: şema seçimi temizlendi."
            )
            _safe_update(debug_lbl)

    async def on_pick_click(e):
        try:
            picked = await ft.FilePicker().pick_files(
                dialog_title="XSD dosyası seçiniz (.xsd)",
                allow_multiple=False,
                allowed_extensions=["xsd"],
            )
        except Exception as ex:
            _notify("Hata", f"Dosya seçim penceresi açılamadı.\n{ex}")
            return

        files = picked or []
        if not files:
            _notify("Bilgi", "Dosya seçimi iptal edildi.")
            return

        xsd_path = (files[0].path or "").strip()
        if not xsd_path:
            _notify("Hata", "Seçilen dosya yolu okunamadı.")
            return

        state["xsd_path"] = xsd_path
        tf_xsd.value = xsd_path
        _safe_update(tf_xsd)
        _update_create_button_state()
        debug_lbl.value = f"UYARILAR: xsd seçildi | {xsd_path}"
        _safe_update(debug_lbl)

    async def on_create_click(e):
        conn_name = (state.get("conn_name") or "").strip()
        schema_name = (state.get("schema_name") or "").strip()
        xsd_path = (state.get("xsd_path") or "").strip()

        if not conn_name:
            _notify("Uyarı", "Lütfen PostGIS bağlantısı seçiniz.")
            return
        if not schema_name:
            _notify("Uyarı", "Lütfen PostGIS şema seçiniz.")
            return
        if not xsd_path:
            _notify("Uyarı", "Lütfen bir XSD dosyası seçiniz.")
            return

        _set_busy(True, "XSD'den veri setleri oluşturuluyor...")
        try:
            res = await asyncio.to_thread(api_create, conn_name, schema_name, xsd_path)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "İşlem başarısız.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            debug_lbl.value = "UYARILAR: oluşturma başarısız."
            _safe_update(debug_lbl)
            return

        _notify(
            "Başarılı", res.get("message") or "XSD'den veri seti oluşturma tamamlandı."
        )
        debug_lbl.value = "UYARILAR: oluşturma başarılı."
        _safe_update(debug_lbl)

    dd_conn.on_change = lambda e: page.run_task(on_conn_change, e)
    dd_schema.on_change = on_schema_change
    btn_pick.on_click = lambda e: page.run_task(on_pick_click, e)
    btn_create.on_click = lambda e: page.run_task(on_create_click, e)

    if use_active_scope:
        _update_create_button_state()
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
            ft.Row(spacing=12, controls=[tf_xsd, btn_pick]),
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
                        padding=ft.Padding.only(left=48, right=48, top=64, bottom=24),
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

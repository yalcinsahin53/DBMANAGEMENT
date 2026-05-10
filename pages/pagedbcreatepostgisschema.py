# pages/pagedbcreatepostgisschema.py
import asyncio
import flet as ft

SCHEMA_PRESETS = [
    "UIP",
    "NIP",
    "MUIP",
    "MNIP",
    "CDP",
    "MCDP25000",
    "MCDP100000",
    "OSBUIP",
    "OSBNIP",
    "Diger",  # manuel giriş açılacak
]


def build_dbcreatepostgisschema_view(page: ft.Page) -> ft.Control:
    state = {
        "conn_name": None,
        "last_conn": None,
        "schema_choice": None,
        "last_schema": None,
    }

    # ---------- UI ----------
    dd_conn = ft.Dropdown(
        label="PostGIS Bağlantısı Seçimi",
        hint_text="Kayıtlı PostGIS bağlantılarından seçim yapınız!",
        expand=True,
        options=[],
    )

    dd_schema = ft.Dropdown(
        label="Şema Seçimi",
        hint_text="Hazır şema seçebilir veya 'Diger' ile manuel girebilirsiniz.",
        expand=True,
        options=[ft.dropdown.Option(key=s, text=s) for s in SCHEMA_PRESETS],
        disabled=True,
    )

    tf_custom_schema = ft.TextField(
        label="Diğer Şema Adı",
        hint_text="Sadece 'Diger' seçilince aktif olur",
        expand=True,
        disabled=True,
    )

    btn_create = ft.ElevatedButton("Şema Oluştur", disabled=True)

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

    # ---------- helpers ----------
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

    def _set_busy(on: bool, text: str = ""):
        busy.visible = on
        busy_text.visible = on
        busy_text.value = text or ""
        page.update()

    def _update_create_button_state():
        conn_ok = bool((state.get("conn_name") or "").strip())
        schema_ok = False

        choice = (dd_schema.value or "").strip()
        if choice and choice != "Diger":
            schema_ok = True
        elif choice == "Diger":
            schema_ok = bool((tf_custom_schema.value or "").strip())

        btn_create.disabled = not (conn_ok and schema_ok)
        btn_create.update()

    # ---------- API wrappers ----------
    def api_db_list():
        return page.api.db_list()

    def api_create_schema(conn_name: str, schema_name: str):
        return page.api.postgis_create_schema(conn_name, schema_name)

    # ---------- load connections ----------
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
            dd_schema.disabled = True
            btn_create.disabled = True
            page.update()
            return

        items = res.get("data") or []
        # db_list() beklenen: [{"No":..,"Conn_Name":"..","DbType":".."}, ...]
        postgis = [
            r
            for r in items
            if isinstance(r, dict)
            and (r.get("Conn_Name") or "").strip()
            and (str(r.get("DbType") or "").strip().lower() == "postgis")
        ]

        dd_conn.options = [
            ft.dropdown.Option(
                key=r["Conn_Name"],
                text=f'{r["Conn_Name"]} ({r.get("DbType", "-")})',
            )
            for r in postgis
        ]
        dd_conn.value = None

        dd_schema.value = None
        dd_schema.disabled = True
        tf_custom_schema.value = ""
        tf_custom_schema.disabled = True
        btn_create.disabled = True

        debug_lbl.value = f"UYARILAR: {len(postgis)} PostGIS bağlantısı yüklendi."
        page.update()

        page.run_task(_watch_conn_selection)

    async def _watch_conn_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_conn.value or "").strip()
            if not cur:
                continue
            if cur == state.get("last_conn"):
                continue

            state["last_conn"] = cur
            state["conn_name"] = cur

            dd_schema.disabled = False
            dd_schema.update()

            debug_lbl.value = f"UYARILAR: conn seçildi | {cur}"
            page.update()

            _update_create_button_state()

    async def _watch_schema_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_schema.value or "").strip()
            if not cur:
                continue
            if cur == state.get("last_schema"):
                continue

            state["last_schema"] = cur
            state["schema_choice"] = cur

            if cur == "Diger":
                tf_custom_schema.disabled = False
            else:
                tf_custom_schema.disabled = True
                tf_custom_schema.value = ""

            tf_custom_schema.update()
            debug_lbl.value = f"UYARILAR: schema seçildi | {cur}"
            page.update()

            _update_create_button_state()

    # ---------- create action ----------
    async def on_create_click(e):
        conn_name = (state.get("conn_name") or "").strip()
        if not conn_name:
            _notify("Hata", "Lütfen PostGIS bağlantısı seçin.")
            return

        choice = (dd_schema.value or "").strip()
        if not choice:
            _notify("Hata", "Lütfen şema seçin.")
            return

        if choice == "Diger":
            schema_name = (tf_custom_schema.value or "").strip()
            if not schema_name:
                _notify("Hata", "Lütfen şema adını girin.")
                return
        else:
            schema_name = choice

        _set_busy(True, "Şema oluşturuluyor...")
        try:
            res = await asyncio.to_thread(api_create_schema, conn_name, schema_name)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Şema oluşturulamadı.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            return

        _notify("Başarılı", res.get("message") or f"Şema oluşturuldu: {schema_name}")

    # ---------- wire ----------
    dd_schema.on_change = lambda e: _update_create_button_state()
    tf_custom_schema.on_change = lambda e: _update_create_button_state()
    btn_create.on_click = lambda e: page.run_task(on_create_click, e)

    page.run_task(_watch_schema_selection)
    page.run_task(refresh_postgis_connections)

    form = ft.Column(
        width=900,
        spacing=16,
        controls=[
            dd_conn,
            dd_schema,
            tf_custom_schema,
            ft.Row(controls=[btn_create]),
        ],
    )

    root = ft.Container(
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
    return root

import asyncio
import flet as ft

from core.active_db_scope import set_active_db_scope
from services.api_runner import LocalAPIRunner
from services.api_client import LocalAPIClient

from pages.pagedbcheckandsave import build_dbcheckandsave_view
from pages.dashboard import build_dashboard_view
from pages.pagedbshowandedit import build_dbshowandedit_view
from pages.pagewfscheckandsave import build_wfscheckandsave_view
from pages.pagewfsshowandedit import build_wfsshowandedit_view
from pages.pagewfsdownload import build_wfsdownload_view
from pages.pagedbcreatepostgisschema import build_dbcreatepostgisschema_view
from pages.pagecheckdublicateanddelete import build_checkdublicateanddelete_view
from pages.pagefeaturetopostgis import build_featuretopostgis_view
from pages.pagefeaturetoesridb import build_featuretoesridb_view
from pages.pagedbcreatefeaturefromxsd import build_dbcreatefeaturefromxsd_view
from pages.pagedbcreatefeaturefromxsdesri import build_dbcreatefeaturefromxsdesri_view
from pages.pagedbmatchfeatureandload import build_dbmatchfeatureandload_view
from pages.pagedbmatchfeatureandloadesri import build_dbmatchfeatureandloadesri_view
from pages.pagedbcreatefeature import build_dbcreatefeature_view
from pages.pagedbcreatefeatureesri import build_dbcreatefeatureesri_view
from pages.pagedbcreateandeditfield import build_dbcreateandeditfield_view
from pages.pagedbcreateandeditfieldesri import build_dbcreateandeditfieldesri_view
from pages.pagedbcheckdublicateanddelete import build_dbcheckdublicateanddelete_view
from pages.pagedbcheckdublicateanddeleteesri import (
    build_dbcheckdublicateanddeleteesri_view,
)
from pages.pagedbdeletefeature import build_dbdeletefeature_view
from pages.pagedbdeletefeatureesri import build_dbdeletefeatureesri_view


class DialogService:
    def __init__(self, page: ft.Page):
        self.page = page
        self._title = ft.Text("")
        self._message = ft.Text("", selectable=True)

        self._dlg = ft.AlertDialog(
            modal=True,
            title=self._title,
            content=self._message,
            actions=[ft.TextButton("Kapat")],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._dlg.actions[0].on_click = self.close

        if hasattr(self.page, "overlay"):
            try:
                if self._dlg not in self.page.overlay:
                    self.page.overlay.append(self._dlg)
            except Exception:
                pass

        try:
            self.page.dialog = self._dlg
        except Exception:
            pass

    def show(self, title: str, message: str):
        self._title.value = title
        self._message.value = message

        if hasattr(self.page, "open"):
            self.page.open(self._dlg)
            return

        if hasattr(self.page, "show_dialog"):
            self._dlg.open = True
            self.page.show_dialog(self._dlg)
            return

        self._dlg.open = True
        self.page.update()

    def close(self, e=None):
        if hasattr(self.page, "close"):
            try:
                self.page.close(self._dlg)
                return
            except Exception:
                pass

        if hasattr(self.page, "pop_dialog"):
            try:
                self.page.pop_dialog()
                return
            except Exception:
                pass

        self._dlg.open = False
        self.page.update()

    def toast(self, message: str):
        sb = ft.SnackBar(content=ft.Text(message))

        if hasattr(self.page, "open"):
            self.page.open(sb)
            return

        if hasattr(self.page, "show_snack_bar"):
            sb.open = True
            self.page.show_snack_bar(sb)
            return

        self.page.snack_bar = sb
        try:
            self.page.snack_bar.open = True
        except Exception:
            pass
        self.page.update()


def _bootstrap_local_api(page: ft.Page, dialog: DialogService) -> None:
    """
    Uygulama açılışında tek kez Local API ayağa kaldırma.
    Sonuç:
      page.api_runner
      page.api
    """
    runner = LocalAPIRunner()
    port = runner.start()

    client = LocalAPIClient(port)

    # objeleri page'e as
    page.api_runner = runner
    page.api = client

    # sağlık kontrolü
    if not client.wait_ready(timeout_sec=4.0):
        detail = ""
        if getattr(runner, "last_error", None):
            detail = "\n\nDetay:\n" + runner.last_error

        dialog.show(
            "Hata",
            "Local API başlatılamadı. Uygulama fonksiyonları çalışmayabilir."
            f"\nPort: {port}" + detail,
        )


def main(page: ft.Page):
    # Ana tema renkleri (mavi-yesil-beyaz)
    PRIMARY_BLUE = "#0B5ED7"
    DEEP_BLUE = "#0A3D91"
    PRIMARY_GREEN = "#12B886"
    MINT_BG = "#E9F9F3"
    SURFACE = "#FFFFFF"
    BACKGROUND = "#F4FAFF"
    BORDER_SOFT = "#D3E6F5"
    TEXT_DARK = "#11324D"

    page.title = "Database Management"
    page.bgcolor = BACKGROUND
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=PRIMARY_BLUE)

    # pencere
    page.window.width = 1280
    page.window.height = 850
    page.window.min_width = 980
    page.window.min_height = 850
    page.window.resizable = True

    # ✅ FilePicker'ı TEK KERE oluştur (overlay'e EKLEME!)
    # main.py  → main(page)

    # dialog servis
    page.dialog_service = DialogService(page)

    # aktif baglanti/sema durumu (uygulama genelinde kullanilabilir)
    page.active_conn_name = None
    page.active_schema_name = None
    page.active_db_type = None

    # Local API bootstrap (TEK NOKTA)
    _bootstrap_local_api(page, page.dialog_service)

    # content host
    content_host = ft.Container(
        expand=True,
        padding=18,
        bgcolor=SURFACE,
    )
    current_page_text = ft.Text(
        "Anasayfa",
        size=14,
        weight=ft.FontWeight.BOLD,
        color=TEXT_DARK,
        selectable=True,
    )
    current_page_bar = ft.Container(
        padding=ft.Padding.only(left=20, right=20, top=11, bottom=11),
        bgcolor=MINT_BG,
        border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_SOFT)),
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.LABEL, size=16, color=PRIMARY_GREEN),
                current_page_text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    # --- KAPANIŞ CALLBACK ---
    def on_window_event(e: ft.WindowEvent):
        # pencere kapatılıyorsa
        if e.type == "close":
            if getattr(page, "api_runner", None):
                try:
                    page.api_runner.stop()
                except Exception:
                    pass

    page.window.on_event = on_window_event

    def _safe_update(control: ft.Control):
        try:
            control.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

    active_db_text = ft.Text("", size=12, weight=ft.FontWeight.BOLD, color=DEEP_BLUE)
    active_schema_text = ft.Text(
        "", size=12, weight=ft.FontWeight.BOLD, color=DEEP_BLUE
    )
    active_warn_text = ft.Text(
        "Veritabani ve Sema Secimi Yapiniz!",
        size=12,
        color=ft.Colors.RED_800,
        weight=ft.FontWeight.BOLD,
        visible=True,
    )

    def _update_active_header():
        conn_name = (getattr(page, "active_conn_name", None) or "").strip()
        schema_name = (getattr(page, "active_schema_name", None) or "").strip()
        db_type = (getattr(page, "active_db_type", None) or "").strip()

        if conn_name and schema_name:
            db_suffix = f" ({db_type})" if db_type else ""
            active_db_text.value = f"Aktif Veri Tabani: {conn_name}{db_suffix}"
            active_schema_text.value = f"Aktif Sema: {schema_name}"
            active_db_text.visible = True
            active_schema_text.visible = True
            active_warn_text.visible = False
        else:
            active_db_text.value = ""
            active_schema_text.value = ""
            active_db_text.visible = False
            active_schema_text.visible = False
            active_warn_text.visible = True

        _safe_update(active_db_text)
        _safe_update(active_schema_text)
        _safe_update(active_warn_text)

    page.refresh_active_header = _update_active_header

    def _do_clear_active_db_scope():
        page.active_conn_name = None
        page.active_schema_name = None
        page.active_db_type = None
        _update_active_header()

    def clear_active_db_scope(e=None):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Uyari"),
            content=ft.Text("Temizlemek istediginizden emin misiniz?"),
        )

        def _on_yes(ev):
            _do_clear_active_db_scope()
            _close_dialog(dlg)

        def _on_no(ev):
            _close_dialog(dlg)

        dlg.actions = [
            ft.TextButton("Hayir", on_click=_on_no),
            ft.ElevatedButton("Evet", on_click=_on_yes),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END
        _open_or_show_dialog(dlg)

    def _open_or_show_dialog(dlg: ft.AlertDialog):
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

    def open_change_active_dialog(e=None):
        dialog_state = {"last_conn": "", "alive": True, "conn_types": {}}

        dd_conn = ft.Dropdown(
            label="Veritabani Baglantisi",
            hint_text="Kayitli PostGIS baglantilarindan seciniz",
            expand=True,
        )
        dd_schema = ft.Dropdown(
            label="Sema Secimi",
            hint_text="Once baglanti seciniz",
            expand=True,
            disabled=True,
        )
        info_text = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_700)

        def _set_info(msg: str):
            info_text.value = msg or ""
            _safe_update(info_text)

        async def _load_schemas_for_conn(conn_name: str):
            dd_schema.options = []
            dd_schema.value = None
            dd_schema.disabled = True
            _safe_update(dd_schema)

            if not conn_name:
                _set_info("Baglanti secimi temizlendi.")
                return

            _set_info("Sema listesi aliniyor...")
            active_type = dialog_state["conn_types"].get(conn_name, "")
            if active_type == "esri":
                res = await asyncio.to_thread(page.api.esri_db_list_schemas, conn_name)
            else:
                res = await asyncio.to_thread(
                    page.api.createfeature_list_schemas, conn_name
                )
            if not isinstance(res, dict) or not res.get("ok"):
                msg = (res or {}).get("message", "Sema listesi alinamadi.")
                dbg = (res or {}).get("debug", "")
                page.dialog_service.show("Hata", f"{msg}\n\n{dbg}".strip())
                _set_info("Sema listesi alinamadi.")
                return

            schemas = [s for s in (res.get("data") or []) if (s or "").strip()]
            dd_schema.options = [ft.dropdown.Option(key=s, text=s) for s in schemas]
            dd_schema.disabled = not bool(schemas)

            current_schema = (getattr(page, "active_schema_name", None) or "").strip()
            if current_schema and current_schema in schemas:
                dd_schema.value = current_schema

            _safe_update(dd_schema)
            _set_info(f"{len(schemas)} sema yuklendi.")

        async def _load_connections_and_defaults():
            _set_info("Baglantilar yukleniyor...")
            res = await asyncio.to_thread(page.api.db_list)
            if not isinstance(res, dict) or not res.get("ok"):
                page.dialog_service.show(
                    "Hata", (res or {}).get("message", "Baglantilar okunamadi.")
                )
                _set_info("Baglantilar okunamadi.")
                return

            items = res.get("data") or []
            schema_capable = [
                r
                for r in items
                if isinstance(r, dict)
                and (r.get("Conn_Name") or "").strip()
                and (
                    str(r.get("DbType") or "").strip().lower() == "postgis"
                    or "esri" in str(r.get("DbType") or "").strip().lower()
                    or "enterprise geodatabase"
                    in str(r.get("DbType") or "").strip().lower()
                )
            ]
            dialog_state["conn_types"] = {}
            for row in schema_capable:
                raw_type = str(row.get("DbType") or "").strip().lower()
                if raw_type == "postgis":
                    dialog_state["conn_types"][row["Conn_Name"]] = "postgis"
                else:
                    dialog_state["conn_types"][row["Conn_Name"]] = "esri"

            dd_conn.options = [
                ft.dropdown.Option(
                    key=r["Conn_Name"],
                    text=f'{r["Conn_Name"]} ({r.get("DbType", "-")})',
                )
                for r in schema_capable
            ]

            current_conn = (getattr(page, "active_conn_name", None) or "").strip()
            if current_conn and any(
                current_conn == r.get("Conn_Name") for r in schema_capable
            ):
                dd_conn.value = current_conn
                await _load_schemas_for_conn(current_conn)
            else:
                dd_conn.value = None
                dd_schema.options = []
                dd_schema.value = None
                dd_schema.disabled = True
                _safe_update(dd_schema)
                _set_info(f"{len(schema_capable)} baglanti yuklendi.")

            _safe_update(dd_conn)
            dialog_state["last_conn"] = (dd_conn.value or "").strip()

        dlg = ft.AlertDialog(modal=True)
        dlg.title = ft.Text("Aktif Veritabani ve Sema Secimi")
        dlg.content = ft.Container(
            width=620,
            content=ft.Column(
                tight=True,
                controls=[
                    dd_conn,
                    dd_schema,
                    info_text,
                ],
            ),
        )

        def _on_conn_change(e):
            try:
                conn_name = (getattr(e, "control", None).value or "").strip()
            except Exception:
                conn_name = (dd_conn.value or "").strip()
            dd_conn.value = conn_name or None
            dialog_state["last_conn"] = conn_name
            _safe_update(dd_conn)
            page.run_task(_load_schemas_for_conn, conn_name)

        async def _watch_conn_selection():
            while dialog_state.get("alive"):
                await asyncio.sleep(0.2)
                cur = (dd_conn.value or "").strip()
                if cur == (dialog_state.get("last_conn") or ""):
                    continue
                dialog_state["last_conn"] = cur
                await _load_schemas_for_conn(cur)

        def _close_this_dialog():
            dialog_state["alive"] = False
            _close_dialog(dlg)

        def _on_save(e):
            conn_name = (dd_conn.value or "").strip()
            schema_name = (dd_schema.value or "").strip()
            conn_type = dialog_state["conn_types"].get(conn_name, "postgis")
            if not conn_name:
                page.dialog_service.show(
                    "Uyari", "Lutfen veritabani baglantisi seciniz."
                )
                return
            if not schema_name:
                page.dialog_service.show("Uyari", "Lutfen sema seciniz.")
                return

            set_active_db_scope(page, conn_name, schema_name, conn_type)
            _close_this_dialog()

        def _on_cancel(e):
            _close_this_dialog()

        dd_conn.on_change = _on_conn_change
        dlg.actions = [
            ft.TextButton("Vazgec", on_click=_on_cancel),
            ft.ElevatedButton("Kaydet", on_click=_on_save),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.END

        _open_or_show_dialog(dlg)
        page.run_task(_watch_conn_selection)
        page.run_task(_load_connections_and_defaults)

    def show_view(control: ft.Control, page_label: str | None = None):
        content_host.content = control
        if page_label is not None:
            current_page_text.value = page_label
        page.update()

    def _ensure_postgis_navigation_allowed() -> bool:
        conn_name = (getattr(page, "active_conn_name", None) or "").strip()
        db_type = (getattr(page, "active_db_type", None) or "").strip().lower()
        if conn_name and db_type and db_type != "postgis":
            page.dialog_service.show(
                "Uyari",
                "Aktif Veritabani Baglantisi PostGIS olmadigi icin bu islemi gerceklestiremezsiniz. "
                "Aktif Veritabani Baglantinizi bir PostGIS veritabani olarak guncellemeniz gerekiyor",
            )
            return False
        return True

    def _ensure_esri_navigation_allowed() -> bool:
        conn_name = (getattr(page, "active_conn_name", None) or "").strip()
        db_type = (getattr(page, "active_db_type", None) or "").strip().lower()
        if conn_name and db_type and db_type != "esri":
            page.dialog_service.show(
                "Uyari",
                "Aktif Veritabani Baglantisi Esri Geodatabase olmadigi icin bu islemi gerceklestiremezsiniz. "
                "Aktif Veritabani Baglantinizi bir Esri Geodatabase veritabani olarak guncellemeniz gerekiyor",
            )
            return False
        return True

    # başlangıç view
    show_view(build_dashboard_view(page), "Anasayfa")

    async def handle_show_drawer(e):
        await page.show_drawer()

    async def close_drawer():
        await page.close_drawer()

    async def navigate_to_pagedbcheckandsave(e):
        show_view(build_dbcheckandsave_view(page), "VT Bağlantı Bilgileri Kaydetme")
        await close_drawer()

    async def navigate_to_pagedbshowandedit(e):
        show_view(build_dbshowandedit_view(page), "VT Bağlantıları Görüntüleme")
        await close_drawer()

    async def navigate_to_pagewfscheckandsave(e):
        show_view(build_wfscheckandsave_view(page), "WFS Bağlantı Bilgileri Kaydetme")
        await close_drawer()

    async def navigate_to_pagewfsshowandedit(e):
        show_view(build_wfsshowandedit_view(page), "WFS Bağlantıları Görüntüleme")
        await close_drawer()

    async def navigate_to_pagewfsdownload(e):
        show_view(build_wfsdownload_view(page), "WFS Veri İndirme")
        await close_drawer()

    async def navigate_to_dbcreatepostgis(e):
        if not _ensure_postgis_navigation_allowed():
            return
        show_view(build_dbcreatepostgisschema_view(page), "VT Şema Oluşturma (PostGIS)")
        await close_drawer()

    async def navigate_to_dbcreatefeaturefromxsd(e):
        if not _ensure_postgis_navigation_allowed():
            return
        show_view(
            build_dbcreatefeaturefromxsd_view(page),
            "VT XSD İle Veri Seti Oluşturma (PostGIS)",
        )
        await close_drawer()

    async def navigate_to_dbcreatefeaturefromxsdesri(e):
        if not _ensure_esri_navigation_allowed():
            return
        show_view(
            build_dbcreatefeaturefromxsdesri_view(page),
            "VT XSD İle Veri Seti Oluşturma (Esri DB)",
        )
        await close_drawer()

    async def navigate_to_dbmatchfeatureandload(e):
        if not _ensure_postgis_navigation_allowed():
            return
        show_view(
            build_dbmatchfeatureandload_view(page),
            "VT Veri Seti Eşleme ve Veri Yükleme (PostGIS)",
        )
        await close_drawer()

    async def navigate_to_dbmatchfeatureandloadesri(e):
        if not _ensure_esri_navigation_allowed():
            return
        show_view(
            build_dbmatchfeatureandloadesri_view(page),
            "VT Veri Seti Eşleme ve Veri Yükleme (Esri DB)",
        )
        await close_drawer()

    async def navigate_to_dbcreatefeature(e):
        if not _ensure_postgis_navigation_allowed():
            return
        show_view(build_dbcreatefeature_view(page), "VT Veri Seti Oluşturma (PostGIS)")
        await close_drawer()

    async def navigate_to_dbcreatefeatureesri(e):
        if not _ensure_esri_navigation_allowed():
            return
        show_view(
            build_dbcreatefeatureesri_view(page), "VT Veri Seti Oluşturma (Esri DB)"
        )
        await close_drawer()

    async def navigate_to_dbdeletefeature(e):
        if not _ensure_postgis_navigation_allowed():
            return
        show_view(build_dbdeletefeature_view(page), "VT Veri Seti Silme (PostGIS)")
        await close_drawer()

    async def navigate_to_dbdeletefeatureesri(e):
        if not _ensure_esri_navigation_allowed():
            return
        show_view(build_dbdeletefeatureesri_view(page), "VT Veri Seti Silme (Esri DB)")
        await close_drawer()

    async def navigate_to_checkdublicateanddelete(e):
        show_view(
            build_checkdublicateanddelete_view(page), "Tekrarlı Veri Kontrol ve Silme"
        )
        await close_drawer()

    async def navigate_to_dbcheckdublicateanddelete(e):
        if not _ensure_postgis_navigation_allowed():
            return
        show_view(
            build_dbcheckdublicateanddelete_view(page),
            "VT Tekrarlı Veri Kontrol ve Silme (PostGIS)",
        )
        await close_drawer()

    async def navigate_to_dbcheckdublicateanddeleteesri(e):
        if not _ensure_esri_navigation_allowed():
            return
        show_view(
            build_dbcheckdublicateanddeleteesri_view(page),
            "VT Tekrarlı Veri Kontrol ve Silme (Esri DB)",
        )
        await close_drawer()

    async def navigate_to_featuretopostgis(e):
        if not _ensure_postgis_navigation_allowed():
            return

        show_view(build_featuretopostgis_view(page), "Veri Seti Aktarımı (PostGIS)")
        await close_drawer()

    async def navigate_to_featuretoesridb(e):
        if not _ensure_esri_navigation_allowed():
            return

        show_view(build_featuretoesridb_view(page), "Veri Seti Aktarımı (Esri DB)")
        await close_drawer()

    async def navigate_to_dbcreateandeditfield(e):
        if not _ensure_postgis_navigation_allowed():
            return

        show_view(
            build_dbcreateandeditfield_view(page),
            "VT Veri Seti Alan Ekleme/Güncelleme (PostGIS)",
        )
        await close_drawer()

    async def navigate_to_dbcreateandeditfieldesri(e):
        if not _ensure_esri_navigation_allowed():
            return

        show_view(
            build_dbcreateandeditfieldesri_view(page),
            "VT Veri Seti Alan Ekleme/Güncelleme (Esri DB)",
        )
        await close_drawer()

    # drawer options
    listtile_dbsave = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Bağlantı Bilgileri Kaydetme"),
        on_click=lambda e: page.run_task(navigate_to_pagedbcheckandsave, e),
    )
    listtile_dbshow = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Bağlantıları Görüntüleme"),
        on_click=lambda e: page.run_task(navigate_to_pagedbshowandedit, e),
    )
    listtile_dbcreatepostgisschema = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Şema Oluşturma (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_dbcreatepostgis, e),
    )
    listtile_dbcreatefeaturefromxsd = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT XSD İle Veri Seti Oluşturma (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_dbcreatefeaturefromxsd, e),
    )
    listtile_dbcreatefeaturefromxsdesri = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT XSD İle Veri Seti Oluşturma (Esri DB)"),
        on_click=lambda e: page.run_task(navigate_to_dbcreatefeaturefromxsdesri, e),
    )
    listtile_dbmatchfeatureandload = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Eşleme ve Veri Yükleme (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_dbmatchfeatureandload, e),
    )
    listtile_dbmatchfeatureandloadesri = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Eşleme ve Veri Yükleme (Esri DB)"),
        on_click=lambda e: page.run_task(navigate_to_dbmatchfeatureandloadesri, e),
    )
    listtile_dbcreatefeature = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Oluşturma (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_dbcreatefeature, e),
    )
    listtile_dbcreatefeatureesri = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Oluşturma (Esri DB)"),
        on_click=lambda e: page.run_task(navigate_to_dbcreatefeatureesri, e),
    )
    listtile_dbdeletefeature = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Silme (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_dbdeletefeature, e),
    )
    listtile_dbdeletefeatureesri = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Silme (Esri DB)"),
        on_click=lambda e: page.run_task(navigate_to_dbdeletefeatureesri, e),
    )
    listtile_dbcreateandeditfield = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Alan Ekleme/Güncelleme (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_dbcreateandeditfield, e),
    )
    listtile_dbcreateandeditfieldesri = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Veri Seti Alan Ekleme/Güncelleme (Esri DB)"),
        on_click=lambda e: page.run_task(navigate_to_dbcreateandeditfieldesri, e),
    )
    listtile_checkdublicateanddelete = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("Tekrarlı Veri Kontrol ve Silme"),
        on_click=lambda e: page.run_task(navigate_to_checkdublicateanddelete, e),
    )
    listtile_dbcheckdublicateanddelete = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Tekrarlı Veri Kontrol ve Silme (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_dbcheckdublicateanddelete, e),
    )
    listtile_dbcheckdublicateanddeleteesri = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("VT Tekrarlı Veri Kontrol ve Silme (Esri DB)"),
        on_click=lambda e: page.run_task(navigate_to_dbcheckdublicateanddeleteesri, e),
    )
    listtile_featuretopostgis = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("Veri Seti Aktarımı (PostGIS)"),
        on_click=lambda e: page.run_task(navigate_to_featuretopostgis, e),
    )
    listtile_featuretoesridb = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("Veri Seti Aktarımı (Esri DB)"),
        on_click=lambda e: page.run_task(navigate_to_featuretoesridb, e),
    )
    listtile_wfssave = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("WFS Bağlantı Bilgileri Kaydetme"),
        on_click=lambda e: page.run_task(navigate_to_pagewfscheckandsave, e),
    )
    listtile_wfsshow = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("WFS Bağlantıları Görüntüleme"),
        on_click=lambda e: page.run_task(navigate_to_pagewfsshowandedit, e),
    )
    listtile_wfsdownload = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("WFS Veri İndirme"),
        on_click=lambda e: page.run_task(navigate_to_pagewfsdownload, e),
    )
    listtile_checkdublicateanddelete = ft.ListTile(
        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        title=ft.Text("Tekrarlı Veri Kontrol ve Silme"),
        on_click=lambda e: page.run_task(navigate_to_checkdublicateanddelete, e),
    )

    page.drawer = ft.NavigationDrawer(
        bgcolor=SURFACE,
        controls=[
            ft.Container(
                padding=ft.Padding.only(left=16, right=16, top=16, bottom=12),
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_SOFT)),
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=34,
                            height=34,
                            border_radius=10,
                            alignment=ft.Alignment.CENTER,
                            bgcolor=PRIMARY_BLUE,
                            content=ft.Icon(
                                ft.Icons.APPS, color=ft.Colors.WHITE, size=18
                            ),
                        ),
                        ft.Column(
                            spacing=0,
                            controls=[
                                ft.Text(
                                    "Menü",
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXT_DARK,
                                ),
                            ],
                        ),
                    ],
                ),
            ),
            ft.NavigationDrawerDestination(
                label="Anasayfa",
                icon=ft.Icons.DOOR_BACK_DOOR_OUTLINED,
                selected_icon=ft.Icon(ft.Icons.DOOR_BACK_DOOR),
            ),
            ft.Divider(thickness=2),
            ft.ExpansionTile(
                title=ft.Text("Veritabanı İşlemleri", weight=ft.FontWeight.BOLD),
                leading=ft.Icon(ft.Icons.MAIL_OUTLINED),
                controls=[
                    listtile_dbsave,
                    listtile_dbshow,
                    ft.ExpansionTile(
                        title=ft.Text("Esri İşlemleri"),
                        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                        controls=[
                            ft.Container(
                                padding=ft.Padding.only(left=24),
                                content=ft.Column(
                                    spacing=0,
                                    controls=[
                                        listtile_dbcreatefeaturefromxsdesri,
                                        listtile_dbcreatefeatureesri,
                                        listtile_dbdeletefeatureesri,
                                        listtile_dbcreateandeditfieldesri,
                                        listtile_dbcheckdublicateanddeleteesri,
                                        listtile_dbmatchfeatureandloadesri,
                                        listtile_featuretoesridb,
                                    ],
                                ),
                            )
                        ],
                    ),
                    ft.ExpansionTile(
                        title=ft.Text("Postgis İşlemleri"),
                        leading=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                        controls=[
                            ft.Container(
                                padding=ft.Padding.only(left=24),
                                content=ft.Column(
                                    spacing=0,
                                    controls=[
                                        listtile_dbcreatepostgisschema,
                                        listtile_dbcreatefeaturefromxsd,
                                        listtile_dbcreatefeature,
                                        listtile_dbdeletefeature,
                                        listtile_dbcreateandeditfield,
                                        listtile_dbcheckdublicateanddelete,
                                        listtile_dbmatchfeatureandload,
                                        listtile_featuretopostgis,
                                    ],
                                ),
                            )
                        ],
                    ),
                ],
            ),
            ft.ExpansionTile(
                title=ft.Text("Veri İşlemleri", weight=ft.FontWeight.BOLD),
                leading=ft.Icon(ft.Icons.MAIL_OUTLINED),
                controls=[
                    ft.Container(
                        padding=ft.Padding.only(left=24),
                        content=ft.Column(
                            spacing=0,
                            controls=[
                                listtile_checkdublicateanddelete,
                            ],
                        ),
                    )
                ],
            ),
            ft.ExpansionTile(
                title=ft.Text("WFS İşlemleri", weight=ft.FontWeight.BOLD),
                leading=ft.Icon(ft.Icons.MAIL_OUTLINED),
                controls=[
                    ft.Container(
                        padding=ft.Padding.only(left=24),
                        content=ft.Column(
                            spacing=0,
                            controls=[
                                listtile_wfssave,
                                listtile_wfsshow,
                                listtile_wfsdownload,
                            ],
                        ),
                    )
                ],
            ),
        ],
    )

    page.add(
        ft.AppBar(
            leading=ft.IconButton(ft.Icons.APPS, on_click=handle_show_drawer),
            title=ft.Row(
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Container(
                            padding=ft.Padding.only(left=14, right=14, top=8, bottom=8),
                            border_radius=14,
                            bgcolor="#D9FFFFFF",
                            border=ft.border.all(1, BORDER_SOFT),
                            content=ft.Row(
                                tight=True,
                                spacing=12,
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Column(
                                        spacing=0,
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            active_db_text,
                                            active_schema_text,
                                            active_warn_text,
                                        ],
                                    ),
                                    ft.ElevatedButton(
                                        "Degistir",
                                        icon=ft.Icons.SYNC_ALT,
                                        style=ft.ButtonStyle(
                                            bgcolor=PRIMARY_BLUE,
                                            color=ft.Colors.WHITE,
                                        ),
                                        on_click=open_change_active_dialog,
                                    ),
                                    ft.OutlinedButton(
                                        "Temizle",
                                        icon=ft.Icons.CLEAR_ALL,
                                        style=ft.ButtonStyle(
                                            color=PRIMARY_GREEN,
                                            side=ft.BorderSide(1, PRIMARY_GREEN),
                                        ),
                                        on_click=clear_active_db_scope,
                                    ),
                                ],
                            ),
                        ),
                    ),
                ],
            ),
            actions=[ft.IconButton(ft.Icons.SWITCH_RIGHT, icon_color=ft.Colors.WHITE)],
            bgcolor=PRIMARY_BLUE,
            center_title=False,
        )
    )
    _update_active_header()
    page.add(current_page_bar)
    page.add(content_host)


if __name__ == "__main__":
    ft.run(main)

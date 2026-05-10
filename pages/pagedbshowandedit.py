import flet as ft


def build_dbshowandedit_view(page: ft.Page) -> ft.Control:
    selected_no = {"value": None}
    tile_by_no = {}  # No -> ListTile referansı
    edit_mode = {"value": False}

    # --- Sağ panel alanları ---
    tf_conn_name = ft.TextField(label="Conn Name", expand=True, disabled=True)
    tf_database  = ft.TextField(label="Database",  expand=True, disabled=True)
    tf_host      = ft.TextField(label="Host",      expand=True, disabled=True)
    tf_port      = ft.TextField(label="Port",      expand=True, disabled=True)
    tf_user      = ft.TextField(label="User",      expand=True, disabled=True)
    tf_password  = ft.TextField(label="Password",  expand=True, disabled=True, password=True, can_reveal_password=True)
    tf_dbtype    = ft.TextField(label="Db Type",   expand=True, disabled=True)

    btn_update = ft.ElevatedButton("Güncelle", disabled=True)
    btn_check  = ft.ElevatedButton("Bağlantıyı Test Et", disabled=True)
    btn_save   = ft.ElevatedButton("Güncellemeleri Kaydet", disabled=True)

    # --- Sol liste ---
    lv = ft.ListView(expand=True, spacing=4, padding=0)

    def _set_fields_enabled(enabled: bool):
        tf_conn_name.disabled = not enabled
        tf_database.disabled  = not enabled
        tf_host.disabled      = not enabled
        tf_port.disabled      = not enabled
        tf_user.disabled      = not enabled
        tf_password.disabled  = not enabled
        tf_dbtype.disabled    = not enabled

    def _clear_fields():
        tf_conn_name.value = ""
        tf_database.value  = ""
        tf_host.value      = ""
        tf_port.value      = ""
        tf_user.value      = ""
        tf_password.value  = ""
        tf_dbtype.value    = ""
        _set_fields_enabled(False)

    def _notify(title: str, msg: str):
        # main.py içinde page.dialog_service var
        if hasattr(page, "dialog_service") and page.dialog_service:
            page.dialog_service.show(title, msg)
        else:
            dlg = ft.AlertDialog(
                title=ft.Text(title),
                content=ft.Text(msg),
                modal=True,
                actions=[ft.TextButton("Kapat")],
            )
            page.dialog = dlg
            dlg.open = True
            page.update()

    def _require_api() -> bool:
        if not hasattr(page, "api") or page.api is None:
            _notify("Hata", "Local API client (page.api) bulunamadı. main.py içinde page.api oluşturulmalı.")
            return False
        return True

    def _apply_selection_visuals():
        for no, tile in tile_by_no.items():
            tile.selected = (no == selected_no["value"])
        page.update()

    def refresh_list():
        if not _require_api():
            return

        lv.controls.clear()
        tile_by_no.clear()

        try:
            res = page.api.db_list()
        except Exception as ex:
            _notify("Hata", f"Liste API çağrısı başarısız:\n{ex}")
            page.update()
            return

        if not res.get("ok"):
            _notify("Hata", f"Liste okunamadı:\n{res.get('message','')}")
            page.update()
            return

        data = res.get("data") or []
        if not data:
            lv.controls.append(
                ft.Container(padding=12, content=ft.Text("Kayıt bulunamadı.", italic=True))
            )
            page.update()
            return

        for r in data:
            no = r.get("No")
            text = f"{r.get('Conn_Name','')} ({r.get('DbType','')})"

            tile = ft.ListTile(
                title=ft.Text(text),
                leading=ft.Icon(ft.Icons.LINK),
                selected=False,
                selected_tile_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                selected_color=ft.Colors.PRIMARY,
                on_click=lambda e, i=no: select_connection(i),
            )

            tile_by_no[no] = tile
            lv.controls.append(tile)

        # Eğer daha önce bir seçim vardıysa yeniden uygula
        _apply_selection_visuals()

    def select_connection(no: int):
        if not _require_api():
            return

        selected_no["value"] = no
        _apply_selection_visuals()

        if edit_mode["value"]:
            _notify("Uyarı", "Güncellemeleri önce kaydedin.")
            return

        try:
            res = page.api.db_get(no)
        except Exception as ex:
            _notify("Hata", f"Detay API çağrısı başarısız:\n{ex}")
            return

        if not res.get("ok"):
            _notify("Hata", res.get("message", "Kayıt okunamadı."))
            return

        row = res.get("data") or {}
        selected_no["value"] = row.get("No")

        tf_conn_name.value = row.get("Conn_Name", "")
        tf_database.value  = row.get("Database", "")
        tf_host.value      = row.get("Host", "")
        tf_port.value      = str(row.get("Port", "") if row.get("Port", "") is not None else "")
        tf_user.value      = row.get("UserName", "")
        tf_password.value  = row.get("Password", "")
        tf_dbtype.value    = row.get("DbType", "")

        btn_update.disabled = False
        btn_check.disabled  = False
        btn_save.disabled   = True
        _set_fields_enabled(False)
        page.update()

    def on_update_click(e):
        if not selected_no["value"]:
            return
        edit_mode["value"] = True
        _set_fields_enabled(True)
        btn_update.disabled = True
        btn_save.disabled = False
        page.update()

    def on_check_click(e):
        if not _require_api():
            return
        if not selected_no["value"]:
            return

        if edit_mode["value"]:
            _notify("Uyarı", "Düzenleme modundayken test yapmadan önce güncellemeleri kaydedin veya iptal edin.")
            return

        try:
            # db_check: API üzerinden psycopg2 connect test
            res = page.api.db_check(
                host=(tf_host.value or "").strip(),
                port=(tf_port.value or "").strip(),
                user=(tf_user.value or "").strip(),
                password=tf_password.value or "",
                database=(tf_database.value or "").strip(),
            )
        except Exception as ex:
            _notify("Hata", f"Test API çağrısı başarısız:\n{ex}")
            return

        _notify(res.get("title", "Bilgi"), res.get("message", ""))

    def on_save_click(e):
        if not _require_api():
            return
        if not selected_no["value"]:
            return

        try:
            res = page.api.db_update(
                no=selected_no["value"],
                conn_name=(tf_conn_name.value or "").strip(),
                database=(tf_database.value or "").strip(),
                host=(tf_host.value or "").strip(),
                port=(tf_port.value or "").strip(),
                user=(tf_user.value or "").strip(),
                password=tf_password.value or "",
                db_type=(tf_dbtype.value or "").strip(),
            )
        except Exception as ex:
            _notify("Hata", f"Güncelleme API çağrısı başarısız:\n{ex}")
            return

        if not res.get("ok"):
            _notify("Hata", res.get("message", "Güncelleme başarısız."))
            return

        _notify("Başarılı", res.get("message", "Güncelleme kaydedildi."))
        if hasattr(page, "dialog_service") and page.dialog_service:
            page.dialog_service.toast("Kayıt güncellendi.")

        edit_mode["value"] = False
        _set_fields_enabled(False)
        btn_update.disabled = False
        btn_save.disabled = True

        # Listeyi yenile (Conn_Name/DbType değişmiş olabilir)
        refresh_list()

    btn_update.on_click = on_update_click
    btn_check.on_click = on_check_click
    btn_save.on_click = on_save_click

    left_panel = ft.Container(
        width=480,
        padding=ft.Padding(12, 12, 12, 12),
        content=ft.Column(
            expand=True,
            spacing=12,
            controls=[
                ft.Text("Görüntülemek/Güncellemek İçin Bağlantı Seçin", size=16, weight=ft.FontWeight.BOLD),
                ft.Container(
                    expand=True,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    padding=8,
                    content=lv,
                ),
            ],
        ),
    )

    right_panel = ft.Container(
        expand=True,
        padding=ft.Padding(12, 12, 12, 12),
        content=ft.Column(
            spacing=12,
            controls=[
                tf_conn_name,
                tf_database,
                tf_host,
                tf_port,
                tf_user,
                tf_password,
                tf_dbtype,
                ft.Divider(),
                ft.ResponsiveRow(
                    columns=12,
                    spacing=12,
                    run_spacing=12,
                    controls=[
                        ft.Container(col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 4}, content=btn_update),
                        ft.Container(col={"xs": 12, "sm": 6, "md": 4, "lg": 4, "xl": 4}, content=btn_check),
                        ft.Container(col={"xs": 12, "sm": 12, "md": 4, "lg": 4, "xl": 4}, content=btn_save),
                    ],
                )
            ],
        ),
    )

    root = ft.Container(
        expand=True,
        bgcolor=ft.Colors.WHITE,
        padding=ft.Padding(16, 16, 16, 16),
        content=ft.Row(
            expand=True,
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[left_panel, right_panel],
        ),
    )

    # İlk açılış
    _clear_fields()
    refresh_list()

    return root

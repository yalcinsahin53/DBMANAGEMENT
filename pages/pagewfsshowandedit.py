import flet as ft
from functions.wfs.functionwfsshowandedit import (
    list_wfs_connections,
    get_wfs_connection,
    update_wfs_connection,
    wfs_test_connection,
)

def build_wfsshowandedit_view(page: ft.Page) -> ft.Control:
    selected_no = {"value": None}
    tile_by_no = {}
    edit_mode = {"value": False}

    # Sağ panel alanları
    tf_conn_name = ft.TextField(label="Bağlantı Adı", disabled=True, expand=True)
    tf_url       = ft.TextField(label="URL", disabled=True, expand=True)
    tf_username  = ft.TextField(label="Kullanıcı Adı", disabled=True, expand=True)
    tf_password  = ft.TextField(label="Şifre", disabled=True, password=True, can_reveal_password=True, expand=True)

    btn_update = ft.ElevatedButton("Güncelle", disabled=True)
    btn_check  = ft.ElevatedButton("Bağlantıyı Test Et", disabled=True)
    btn_save   = ft.ElevatedButton("Güncellemeleri Kaydet", disabled=True)

    lv = ft.ListView(expand=True, spacing=4, padding=0)

    def _notify(title: str, msg: str):
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

    def _set_fields_enabled(enabled: bool):
        tf_conn_name.disabled = not enabled
        tf_url.disabled = not enabled
        tf_username.disabled = not enabled
        tf_password.disabled = not enabled

    def _clear_fields():
        tf_conn_name.value = ""
        tf_url.value = ""
        tf_username.value = ""
        tf_password.value = ""
        _set_fields_enabled(False)

    def _apply_selection_visuals():
        for no, tile in tile_by_no.items():
            tile.selected = (no == selected_no["value"])
        page.update()

    def refresh_list():
        lv.controls.clear()
        tile_by_no.clear()

        res = list_wfs_connections()
        if not res["ok"]:
            _notify("Hata", f"Liste okunamadı:\n{res['message']}")
            page.update()
            return

        data = res["data"]
        if not data:
            lv.controls.append(ft.Container(padding=12, content=ft.Text("Kayıt bulunamadı.", italic=True)))
            page.update()
            return

        for r in data:
            no = r["No"]
            name = r.get("Conn_Name", "")
            url = r.get("UrlAdress", "")
            text = f"{name}"

            tile = ft.ListTile(
                title=ft.Text(text),
                subtitle=ft.Text(url, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                leading=ft.Icon(ft.Icons.CLOUD_OUTLINED),
                selected=False,
                selected_tile_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                selected_color=ft.Colors.PRIMARY,
                on_click=lambda e, i=no: select_connection(i),
            )
            tile_by_no[no] = tile
            lv.controls.append(tile)

        _apply_selection_visuals()

    def select_connection(no: int):
        if edit_mode["value"]:
            _notify("Uyarı", "Güncellemeleri önce kaydedin.")
            return

        selected_no["value"] = no
        _apply_selection_visuals()

        res = get_wfs_connection(no)
        if not res["ok"]:
            _notify("Hata", res["message"])
            return

        row = res["data"]
        tf_conn_name.value = row.get("Conn_Name", "")
        tf_url.value       = row.get("UrlAdress", "")
        tf_username.value  = row.get("UserName", "")
        tf_password.value  = row.get("Password", "")

        _set_fields_enabled(False)
        btn_update.disabled = False
        btn_check.disabled  = False
        btn_save.disabled   = True
        page.update()

    def on_update_click(e):
        if not selected_no["value"]:
            return
        edit_mode["value"] = True
        _set_fields_enabled(True)
        btn_update.disabled = True
        btn_check.disabled  = True   # edit modunda test istenmiyorsa kilitle
        btn_save.disabled   = False
        page.update()

    def on_check_click(e):
        if not selected_no["value"]:
            return
        if edit_mode["value"]:
            _notify("Uyarı", "Düzenleme modundayken test yapmadan önce kaydedin veya iptal edin.")
            return

        # Basit “işleniyor” hissi
        btn_check.disabled = True
        page.update()

        res = wfs_test_connection(
            urladress=(tf_url.value or "").strip(),
            username=(tf_username.value or "").strip(),
            password=tf_password.value or "",
            timeout=10,
        )

        _notify(res.get("title", "Bilgi"), res.get("message", ""))
        btn_check.disabled = False
        page.update()

    def on_save_click(e):
        if not selected_no["value"]:
            return

        res = update_wfs_connection(
            no=selected_no["value"],
            conn_name=(tf_conn_name.value or "").strip(),
            urladress=(tf_url.value or "").strip(),
            username=(tf_username.value or "").strip(),
            password=tf_password.value or "",
        )

        if not res["ok"]:
            _notify("Hata", res["message"])
            return

        _notify("Başarılı", res["message"])
        if hasattr(page, "dialog_service") and page.dialog_service:
            page.dialog_service.toast("Kayıt güncellendi.")

        edit_mode["value"] = False
        _set_fields_enabled(False)
        btn_update.disabled = False
        btn_check.disabled  = False
        btn_save.disabled   = True

        refresh_list()

    btn_update.on_click = on_update_click
    btn_check.on_click  = on_check_click
    btn_save.on_click   = on_save_click

    left_panel = ft.Container(
        width=480,  # sol panel dar
        padding=ft.Padding(12, 12, 12, 12),
        content=ft.Column(
            expand=True,
            spacing=12,
            controls=[
                ft.Text("WFS Bağlantıları", size=16, weight=ft.FontWeight.BOLD),
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

    # Sağ panel form ve butonlar responsive
    buttons = ft.ResponsiveRow(
        columns=12,
        spacing=12,
        run_spacing=12,
        controls=[
            ft.Container(col={"xs": 12, "sm": 6, "md": 4}, content=btn_update),
            ft.Container(col={"xs": 12, "sm": 6, "md": 4}, content=btn_check),
            ft.Container(col={"xs": 12, "sm": 12, "md": 4}, content=btn_save),
        ],
    )

    right_panel = ft.Container(
        expand=True,
        padding=ft.Padding(12, 12, 12, 12),
        content=ft.Column(
            spacing=12,
            controls=[
                tf_conn_name,
                tf_url,
                tf_username,
                tf_password,
                ft.Divider(),
                buttons,
            ],
        ),
    )

    root = ft.Container(
        expand=True,
        bgcolor=ft.Colors.WHITE,
        padding=ft.Padding(16, 16, 16, 16),
        content=ft.Row(
            expand=True,
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[left_panel, right_panel],
        ),
    )

    _clear_fields()
    refresh_list()
    return root

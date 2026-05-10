import flet as ft


def build_wfscheckandsave_view(page: ft.Page) -> ft.Control:
    tf_conn_name = ft.TextField(label="Bağlantı Adı Giriniz!", width=520)
    tf_url = ft.TextField(label="Bağlantı Adresi Giriniz!", width=520)
    tf_username = ft.TextField(label="Kullanıcı Adı", width=520)
    tf_password = ft.TextField(label="Şifre", width=520, password=True, can_reveal_password=True)

    btn_check = ft.ElevatedButton("Bağlantıyı Kontrol Et")
    btn_save = ft.ElevatedButton("Bağlantıyı Kaydet", disabled=True)

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

    def _require_api() -> bool:
        if not hasattr(page, "api") or page.api is None:
            _notify("Hata", "Local API client (page.api) bulunamadı. main.py içinde page.api oluşturulmalı.")
            return False
        return True

    def on_check_click(e):
        if not _require_api():
            return

        try:
            res = page.api.wfs_check(
                urladress=(tf_url.value or "").strip(),
                username=(tf_username.value or "").strip(),
                password=tf_password.value or "",
                timeout=10,
            )
        except Exception as ex:
            _notify("Hata", f"WFS test API çağrısı başarısız:\n{ex}")
            btn_save.disabled = True
            page.update()
            return

        _notify(res.get("title", "Bilgi"), res.get("message", ""))
        btn_save.disabled = not bool(res.get("is_save_enabled", False))
        page.update()

    def on_save_click(e):
        if not _require_api():
            return

        try:
            res = page.api.wfs_save(
                conn_name=(tf_conn_name.value or "").strip(),
                urladress=(tf_url.value or "").strip(),
                username=(tf_username.value or "").strip(),
                password=tf_password.value or "",
            )
        except Exception as ex:
            _notify("Hata", f"WFS kayıt API çağrısı başarısız:\n{ex}")
            return

        _notify(res.get("title", "Bilgi"), res.get("message", ""))

        if res.get("ok"):
            btn_save.disabled = True
            if hasattr(page, "dialog_service") and page.dialog_service:
                page.dialog_service.toast("Kayıt tamamlandı.")
        page.update()

    btn_check.on_click = on_check_click
    btn_save.on_click = on_save_click

    form = ft.Column(
        spacing=24,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[tf_conn_name, tf_url, tf_username, tf_password],
    )

    buttons = ft.ResponsiveRow(
        columns=12,
        spacing=12,
        run_spacing=12,
        controls=[
            ft.Container(col={"xs": 12, "md": 6}, content=btn_check),
            ft.Container(col={"xs": 12, "md": 6}, content=btn_save),
        ],
    )

    return ft.Container(
        expand=True,
        bgcolor=ft.Colors.WHITE,
        content=ft.ListView(
            expand=True,
            padding=ft.Padding.only(left=48, right=48, top=64, bottom=24),
            controls=[
                ft.Container(
                    alignment=ft.Alignment.TOP_CENTER,
                    content=ft.Column(
                        width=560,
                        spacing=18,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[form, ft.Container(height=6), buttons],
                    ),
                )
            ],
        ),
    )

import flet as ft


def build_dbcheckandsave_view(page: ft.Page) -> ft.Control:
    # --- Alanlar ---
    db_type = ft.Dropdown(
        width=400,
        label="Veritabanı Türü Seçiniz!",
        options=[
            ft.dropdown.Option("PostGIS"),
            ft.dropdown.Option("Esri Geodatabase"),
        ],
    )

    conn_name = ft.TextField(label="Bağlantı Adı Giriniz!", width=400)
    host = ft.TextField(label="Host", value="localhost", width=400)
    port = ft.TextField(label="Port", value="5432", width=400)
    user = ft.TextField(label="Kullanıcı Adı", width=400)
    password = ft.TextField(label="Şifre", password=True, can_reveal_password=True, width=400)
    database = ft.TextField(label="Veritabanı Adı", width=400)

    # Butonlar
    check_btn = ft.ElevatedButton("Bağlantıyı Kontrol Et", width=200)
    save_btn = ft.ElevatedButton("Bağlantıyı Kaydet", width=200, disabled=True)

    # --- yardımcılar ---
    def _notify(title: str, message: str):
        if hasattr(page, "dialog_service") and page.dialog_service:
            page.dialog_service.show(title, message)
        else:
            dlg = ft.AlertDialog(
                title=ft.Text(title),
                content=ft.Text(message),
                modal=True,
                actions=[ft.TextButton("Kapat")],
            )
            page.dialog = dlg
            dlg.open = True
            page.update()

    def _toast(message: str):
        if hasattr(page, "dialog_service") and page.dialog_service:
            page.dialog_service.toast(message)

    def _require_api() -> bool:
        if not hasattr(page, "api") or page.api is None:
            _notify("Hata", "Local API client (page.api) bulunamadı. main.py içinde page.api oluşturulmalı.")
            return False
        return True

    def _validate_required() -> tuple[bool, str]:
        if not (db_type.value or "").strip():
            return False, "Veritabanı türü seçiniz."
        if not (conn_name.value or "").strip():
            return False, "Bağlantı adı giriniz."
        if not (host.value or "").strip():
            return False, "Host giriniz."
        if not (port.value or "").strip():
            return False, "Port giriniz."
        if not (user.value or "").strip():
            return False, "Kullanıcı adı giriniz."
        if not (password.value or "").strip():
            return False, "Şifre giriniz."
        if not (database.value or "").strip():
            return False, "Veritabanı adı giriniz."
        return True, ""

    # --- events ---
    def on_check_click(e):
        if not _require_api():
            return

        ok, msg = _validate_required()
        if not ok:
            _notify("Uyarı", msg)
            save_btn.disabled = True
            page.update()
            return

        try:
            res = page.api.db_check(
                host=(host.value or "").strip(),
                port=(port.value or "").strip(),
                user=(user.value or "").strip(),
                password=password.value or "",
                database=(database.value or "").strip(),
            )
        except Exception as ex:
            _notify("Hata", f"Bağlantı testi API çağrısı başarısız:\n{ex}")
            save_btn.disabled = True
            page.update()
            return

        _notify(res.get("title", "Bilgi"), res.get("message", ""))

        # db_check sonucu: is_save_enabled = True ise kaydet aktif
        save_btn.disabled = not bool(res.get("is_save_enabled", False))
        page.update()

    def on_save_click(e):
        if not _require_api():
            return

        ok, msg = _validate_required()
        if not ok:
            _notify("Uyarı", msg)
            return

        try:
            res = page.api.db_save(
                conn_name=(conn_name.value or "").strip(),
                host=(host.value or "").strip(),
                port=(port.value or "").strip(),
                user=(user.value or "").strip(),
                password=password.value or "",
                database=(database.value or "").strip(),
                db_type=(db_type.value or "").strip(),
            )
        except Exception as ex:
            _notify("Hata", f"Kayıt API çağrısı başarısız:\n{ex}")
            return

        _notify(res.get("title", "Bilgi"), res.get("message", ""))

        if res.get("ok"):
            _toast("Kayıt tamamlandı.")
            # Kaydetten sonra tekrar kaydetme kapalı (yeniden test etsin)
            save_btn.disabled = True
            page.update()

    check_btn.on_click = on_check_click
    save_btn.on_click = on_save_click

    form = ft.Column(
        spacing=24,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            db_type,
            conn_name,
            host,
            port,
            user,
            password,
            database,
        ],
    )

    buttons = ft.Row(
        spacing=24,
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[check_btn, save_btn],
    )

    return ft.Container(
        expand=True,
        bgcolor=ft.Colors.WHITE,
        content=ft.ListView(
            expand=True,
            spacing=0,
            padding=ft.Padding.only(left=48, right=48, top=16, bottom=8),
            controls=[
                ft.Container(
                    alignment=ft.Alignment.TOP_CENTER,
                    content=ft.Column(
                        width=520,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=16,
                        controls=[
                            form,
                            ft.Container(height=8),
                            buttons,
                            ft.Container(height=24),
                        ],
                    ),
                ),
            ],
        ),
    )

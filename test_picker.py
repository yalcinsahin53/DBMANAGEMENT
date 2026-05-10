import flet as ft

async def main(page: ft.Page):
    async def pick_dir(e):
        p = await ft.FilePicker().get_directory_path()
        page.add(ft.Text(f"dir={p}"))

    page.add(ft.Button("Open directory", on_click=pick_dir))

ft.run(main)

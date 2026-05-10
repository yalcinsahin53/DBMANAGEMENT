import asyncio
from collections import defaultdict
import flet as ft

from core.gml_duplicate_service import (
    VectorDocument,
    analyze_duplicates,
    delete_record,
    load_vector,
)


def build_checkdublicateanddelete_view(page: ft.Page) -> ft.Control:
    state = {
        "doc": None,
        "file_path": "",
        "rows": [],
        "last_dataset": None,
        "last_field": None,
    }

    tf_file = ft.TextField(
        label="Secilen Vektor Dosyasi",
        hint_text="Once bir .gml veya .shp dosyasi seciniz",
        read_only=True,
        expand=True,
        disabled=True,
    )
    btn_pick = ft.ElevatedButton("Vektor Dosyasi Sec (.gml / .shp)")

    dd_dataset = ft.Dropdown(
        label="Veri Seti Secimi",
        hint_text="GML seciminde aktif olur",
        options=[],
        expand=True,
        disabled=True,
    )

    dd_field = ft.Dropdown(
        label="Tekrar Kontrol Alani",
        hint_text="Dosya icindeki alan adlarindan birini seciniz",
        options=[],
        expand=True,
        disabled=True,
    )

    btn_analyze = ft.ElevatedButton("Analiz Et", disabled=True)

    summary_text = ft.Text("Sonuc: Henuz analiz yapilmadi.")
    result_list = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.AUTO)

    busy = ft.ProgressRing(visible=False)
    busy_text = ft.Text("", visible=False)
    debug_lbl = ft.Text("UYARILAR: hazir", size=12, selectable=True)

    def _notify(title: str, msg: str):
        if hasattr(page, "dialog_service") and page.dialog_service:
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

    def _set_busy(on: bool, text: str = ""):
        busy.visible = on
        busy_text.visible = on
        busy_text.value = text or ""
        page.update()

    def _doc_kind() -> str:
        doc = state.get("doc")
        return (getattr(doc, "kind", "") or "").strip().lower()

    def _is_gml() -> bool:
        return _doc_kind() == "gml"

    def _gml_dataset_names(doc: VectorDocument) -> list[str]:
        names = {
            str(rec.feature_type or "").strip()
            for rec in (doc.features or [])
            if str(rec.feature_type or "").strip()
        }
        return sorted(names, key=lambda x: x.lower())

    def _gml_fields_for_dataset(doc: VectorDocument, dataset_name: str) -> list[str]:
        target = (dataset_name or "").strip()
        if not target:
            return []
        field_set: set[str] = set()
        for rec in (doc.features or []):
            if (str(rec.feature_type or "").strip()) != target:
                continue
            field_set.update((rec.values or {}).keys())
        return sorted(field_set, key=lambda s: s.lower())

    def _set_controls_enabled():
        has_doc = state.get("doc") is not None
        gml_mode = _is_gml()
        has_dataset = bool((dd_dataset.value or "").strip())
        has_field = bool((dd_field.value or "").strip())

        # GML icin dataset secimi zorunlu; SHP icin dropdown pasif kalir.
        dd_dataset.disabled = not (has_doc and gml_mode and len(dd_dataset.options) > 0)
        dd_field.disabled = not has_doc or (gml_mode and not has_dataset)
        btn_analyze.disabled = not (has_doc and (not gml_mode or has_dataset) and has_field)

        dd_dataset.update()
        dd_field.update()
        btn_analyze.update()

    def _clear_results(message: str = "Sonuc: Henuz analiz yapilmadi."):
        state["rows"] = []
        summary_text.value = message
        result_list.controls = []
        summary_text.update()
        result_list.update()

    def _group_rows_by_value(rows: list[dict]) -> list[tuple[str, list[dict]]]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            key = str(row.get("value") or "").strip()
            groups[key].append(row)

        grouped = []
        for value, items in groups.items():
            items.sort(key=lambda r: int(r.get("record_id") or 0))
            grouped.append((value, items))

        grouped.sort(key=lambda t: t[0].lower())
        return grouped

    def _build_group_tile(group_index: int, value: str, items: list[dict]) -> ft.Control:
        value_text = value if value else "(Bos Deger)"
        detail_rows: list[ft.Control] = []
        button_rows: list[ft.Control] = []
        field_order = sorted(
            {str(k) for row in items for k in (row.get("all_values") or {}).keys()},
            key=lambda x: x.lower(),
        )
        columns = ["KayitID", "Tip"] + field_order

        col_width: dict[str, int] = {}
        for col in columns:
            max_len = len(col)
            for row in items:
                if col == "KayitID":
                    val = str(int(row.get("record_id") or 0))
                elif col == "Tip":
                    val = str(row.get("feature_type") or "")
                else:
                    val = str((row.get("all_values") or {}).get(col) or "")
                if len(val) > max_len:
                    max_len = len(val)
            col_width[col] = max(120, max_len * 8 + 28)

        def _cell(text: str, width: int, header: bool = False) -> ft.Control:
            return ft.Container(
                width=width,
                padding=ft.Padding.only(left=8, right=8, top=6, bottom=6),
                border=ft.Border.only(right=ft.BorderSide(1, ft.Colors.BLACK12)),
                bgcolor=ft.Colors.BLUE_50 if header else None,
                content=ft.Text(
                    text,
                    selectable=True,
                    weight=ft.FontWeight.BOLD if header else ft.FontWeight.NORMAL,
                ),
            )

        header_cells = [_cell(col, col_width[col], header=True) for col in columns]
        detail_rows.append(
            ft.Container(
                border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
                content=ft.Row(wrap=False, spacing=0, controls=header_cells),
            )
        )

        button_rows.append(
            ft.Container(
                width=130,
                padding=ft.Padding.only(left=6, right=6, top=6, bottom=6),
                border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
                bgcolor=ft.Colors.BLUE_50,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("Islem", weight=ft.FontWeight.BOLD),
            )
        )

        for row in items:
            rid = int(row.get("record_id") or 0)
            feature_type = str(row.get("feature_type") or "")
            all_values = row.get("all_values") or {}

            row_cells: list[ft.Control] = []
            row_cells.append(_cell(str(rid), col_width["KayitID"]))
            row_cells.append(_cell(feature_type, col_width["Tip"]))
            for field in field_order:
                row_cells.append(_cell(str(all_values.get(field) or ""), col_width[field]))

            detail_rows.append(
                ft.Container(
                    border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
                    content=ft.Row(wrap=False, spacing=0, controls=row_cells),
                )
            )

            button_rows.append(
                ft.Container(
                    width=130,
                    padding=ft.Padding.only(left=6, right=6, top=6, bottom=6),
                    border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
                    alignment=ft.Alignment.CENTER,
                    content=ft.ElevatedButton(
                        "Veri Sil",
                        icon=ft.Icons.DELETE_OUTLINE,
                        height=20,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.RED_50,
                            color=ft.Colors.RED_900,
                            padding=ft.Padding.only(left=8, right=8, top=4, bottom=4),
                            text_style=ft.TextStyle(size=12),
                            icon_size=14,
                        ),
                        on_click=lambda e, record_id=rid: page.run_task(on_delete_click, record_id),
                    ),
                )
            )

        return ft.ExpansionTile(
            title=ft.Text(f"{group_index}. {value_text}", selectable=True),
            subtitle=ft.Text(f"Tekrarli kayit sayisi: {len(items)}"),
            expanded=False,
            maintain_state=True,
            controls=[
                ft.Container(
                    padding=ft.Padding.only(left=4, right=4, top=4, bottom=10),
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                expand=True,
                                content=ft.Row(
                                    scroll=ft.ScrollMode.AUTO,
                                    controls=[ft.Column(spacing=0, controls=detail_rows)],
                                ),
                            ),
                            ft.Container(
                                width=130,
                                content=ft.Column(
                                    spacing=0,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    controls=button_rows,
                                ),
                            ),
                        ],
                    ),
                )
            ],
        )

    def _render_results(rows: list[dict], field_name: str):
        if not rows:
            summary_text.value = f"Sonuc: '{field_name}' alaninda tekrarli kayit bulunamadi."
            result_list.controls = [
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Text("Tekrarli kayit bulunamadi."),
                )
            ]
            summary_text.update()
            result_list.update()
            return

        grouped = _group_rows_by_value(rows)
        summary_text.value = (
            f"Sonuc: {len(grouped)} tekrarli deger grubu, "
            f"{len(rows)} tekrarli kayit bulundu."
        )
        controls = []
        for i, (value, items) in enumerate(grouped, start=1):
            controls.append(
                ft.Container(
                    padding=ft.Padding.only(left=8, right=8, top=2, bottom=2),
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=_build_group_tile(i, value, items),
                )
            )

        result_list.controls = controls
        summary_text.update()
        result_list.update()

    def _refresh_dataset_and_field_dropdowns(preferred_dataset: str = "", preferred_field: str = ""):
        doc = state.get("doc")
        if doc is None:
            dd_dataset.options = []
            dd_dataset.value = None
            dd_field.options = []
            dd_field.value = None
            dd_dataset.update()
            dd_field.update()
            _set_controls_enabled()
            return

        if (doc.kind or "").lower() == "gml":
            datasets = _gml_dataset_names(doc)
            dd_dataset.options = [ft.dropdown.Option(key=d, text=d) for d in datasets]

            selected_dataset = preferred_dataset if preferred_dataset in datasets else ""
            if not selected_dataset and len(datasets) == 1:
                selected_dataset = datasets[0]
            dd_dataset.value = selected_dataset or None

            fields = _gml_fields_for_dataset(doc, dd_dataset.value or "")
            dd_field.options = [ft.dropdown.Option(key=f, text=f) for f in fields]
            if preferred_field and preferred_field in fields:
                dd_field.value = preferred_field
            else:
                dd_field.value = None

        else:
            dd_dataset.options = []
            dd_dataset.value = None

            fields = list(getattr(doc, "fields", []) or [])
            dd_field.options = [ft.dropdown.Option(key=f, text=f) for f in fields]
            if preferred_field and preferred_field in fields:
                dd_field.value = preferred_field
            else:
                dd_field.value = None

        dd_dataset.update()
        dd_field.update()
        _set_controls_enabled()

    async def _run_analyze():
        file_path = (state.get("file_path") or "").strip()
        if not file_path:
            _notify("Uyari", "Once bir vektor dosyasi seciniz.")
            return False

        selected_dataset = (dd_dataset.value or "").strip()
        field_name = (dd_field.value or "").strip()

        if _is_gml() and not selected_dataset:
            _notify("Uyari", "GML icin once veri seti seciniz.")
            return False

        if not field_name:
            _notify("Uyari", "Lutfen bir alan seciniz.")
            return False

        _set_busy(True, "Tekrarli kayitlar analiz ediliyor...")
        try:
            reload_res = await asyncio.to_thread(load_vector, file_path)
            if not reload_res.get("ok"):
                _notify(
                    "Hata",
                    f"{reload_res.get('message','Dosya okunamadi.')}\n\n{reload_res.get('debug','')}",
                )
                return False

            state["doc"] = reload_res["data"]

            # Reload sonrasi dataset/alan listelerini secime gore tekrar kur.
            _refresh_dataset_and_field_dropdowns(
                preferred_dataset=selected_dataset,
                preferred_field=field_name,
            )

            selected_dataset = (dd_dataset.value or "").strip()
            field_name = (dd_field.value or "").strip()
            if _is_gml() and not selected_dataset:
                _notify("Uyari", "Secilen veri seti tekrar yukleme sonrasi bulunamadi.")
                return False
            if not field_name:
                _notify("Uyari", "Secilen alan tekrar yukleme sonrasi bulunamadi.")
                return False

            doc = state["doc"]
            run_doc = doc
            if (doc.kind or "").lower() == "gml":
                filtered_features = [
                    rec
                    for rec in (doc.features or [])
                    if (str(rec.feature_type or "").strip()) == selected_dataset
                ]
                run_doc = VectorDocument(
                    path=doc.path,
                    kind=doc.kind,
                    features=filtered_features,
                    fields=_gml_fields_for_dataset(doc, selected_dataset),
                    tree=doc.tree,
                    namespaces=doc.namespaces,
                )

            res = await asyncio.to_thread(analyze_duplicates, run_doc, field_name)
        finally:
            _set_busy(False)

        if not res.get("ok"):
            _notify(
                "Hata",
                f"{res.get('message','Analiz basarisiz.')}\n\n{res.get('debug','')}",
            )
            return False

        rows = (res.get("data") or {}).get("rows") or []
        state["rows"] = rows
        _render_results(rows, field_name)

        extra = f" | dataset={selected_dataset}" if selected_dataset else ""
        debug_lbl.value = f"UYARILAR: analiz tamamlandi | field={field_name}{extra} | duplicate={len(rows)}"
        debug_lbl.update()
        return True

    async def on_pick_click(e):
        try:
            picked = await ft.FilePicker().pick_files(
                dialog_title="Vektor dosyasi seciniz (.gml / .shp)",
                allow_multiple=False,
                allowed_extensions=["gml", "xml", "shp"],
            )
        except Exception as ex:
            _notify("Hata", f"Dosya secimi acilamadi.\n{ex}")
            return

        files = picked or []
        if not files:
            _notify("Bilgi", "Dosya secimi iptal edildi.")
            return

        file_path = (files[0].path or "").strip()
        if not file_path:
            _notify("Hata", "Secilen dosya yolu alinamadi.")
            return

        _set_busy(True, "Vektor dosyasi okunuyor...")
        try:
            res = await asyncio.to_thread(load_vector, file_path)
        finally:
            _set_busy(False)

        if not res.get("ok"):
            _notify(
                "Hata",
                f"{res.get('message','Dosya okunamadi.')}\n\n{res.get('debug','')}",
            )
            return

        state["doc"] = res["data"]
        state["file_path"] = file_path

        tf_file.value = file_path
        tf_file.update()

        _refresh_dataset_and_field_dropdowns()
        _clear_results("Sonuc: Secimlerinizi yapip analiz baslatabilirsiniz.")

        kind = _doc_kind().upper() or "?"
        debug_lbl.value = f"UYARILAR: dosya yuklendi | kind={kind} | {len(state['doc'].features)} kayit"
        debug_lbl.update()

    async def on_dataset_change(e):
        doc = state.get("doc")
        if doc is None:
            return

        if (doc.kind or "").lower() != "gml":
            _set_controls_enabled()
            return

        selected_dataset = (dd_dataset.value or "").strip()
        state["last_dataset"] = selected_dataset

        fields = _gml_fields_for_dataset(doc, selected_dataset)
        dd_field.options = [ft.dropdown.Option(key=f, text=f) for f in fields]
        dd_field.value = None
        dd_field.update()

        _clear_results("Sonuc: Alan secip analiz baslatabilirsiniz.")
        _set_controls_enabled()

    async def on_analyze_click(e):
        await _run_analyze()

    async def on_delete_click(record_id: int):
        doc = state.get("doc")
        if doc is None:
            _notify("Uyari", "Once dosya seciniz.")
            return

        field_name = (dd_field.value or "").strip()
        if not field_name:
            _notify("Uyari", "Once analiz alanini seciniz.")
            return

        selected_dataset = (dd_dataset.value or "").strip()

        _set_busy(True, "Kayit siliniyor...")
        try:
            res = await asyncio.to_thread(delete_record, doc, int(record_id))
            if not res.get("ok"):
                _notify(
                    "Hata",
                    f"{res.get('message','Kayit silinemedi.')}\n\n{res.get('debug','')}",
                )
                return

            reload_res = await asyncio.to_thread(load_vector, state["file_path"])
            if not reload_res.get("ok"):
                _notify(
                    "Hata",
                    (
                        "Kayit silindi ancak dosya yeniden okunamadi.\n\n"
                        f"{reload_res.get('message','')}\n{reload_res.get('debug','')}"
                    ).strip(),
                )
                state["doc"] = None
                dd_dataset.options = []
                dd_dataset.value = None
                dd_field.options = []
                dd_field.value = None
                _clear_results("Sonuc: Dosya tekrar yuklenmeli.")
                _set_controls_enabled()
                return

            state["doc"] = reload_res["data"]
            _refresh_dataset_and_field_dropdowns(
                preferred_dataset=selected_dataset,
                preferred_field=field_name,
            )

            if dd_field.value:
                await _run_analyze()
            else:
                _clear_results("Sonuc: Secilen alan/veri seti bulunamadi, secimi yenileyin.")

            if hasattr(page, "dialog_service") and page.dialog_service:
                page.dialog_service.toast("Secilen kayit silindi.")

            debug_lbl.value = f"UYARILAR: kayit silindi | record_id={record_id}"
            debug_lbl.update()

        finally:
            _set_busy(False)

    async def _watch_dataset_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_dataset.value or "").strip()
            if cur == state.get("last_dataset"):
                continue
            state["last_dataset"] = cur
            await on_dataset_change(None)

    async def _watch_field_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_field.value or "").strip()
            if cur == state.get("last_field"):
                continue
            state["last_field"] = cur
            _set_controls_enabled()

    def on_field_change(e):
        try:
            if e and getattr(e, "control", None) is not None:
                dd_field.value = (e.control.value or "").strip() or None
        except Exception:
            pass
        _set_controls_enabled()

    btn_pick.on_click = lambda e: page.run_task(on_pick_click, e)
    btn_analyze.on_click = lambda e: page.run_task(on_analyze_click, e)
    dd_dataset.on_change = lambda e: page.run_task(on_dataset_change, e)
    dd_field.on_change = on_field_change

    page.run_task(_watch_dataset_selection)
    page.run_task(_watch_field_selection)

    header_form = ft.Column(
        width=980,
        spacing=12,
        controls=[
            ft.Row(
                controls=[tf_file, btn_pick],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            dd_dataset,
            ft.Row(
                controls=[dd_field, btn_analyze],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            summary_text,
        ],
    )

    debug_bar = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=10, bottom=10),
        border=ft.Border.only(top=ft.BorderSide(1, ft.Colors.BLACK12)),
        bgcolor=ft.Colors.WHITE,
        content=ft.Row(
            controls=[busy, busy_text, ft.Container(expand=True), debug_lbl],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
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
                        padding=ft.Padding.only(left=48, right=48, top=40, bottom=20),
                        controls=[
                            ft.Container(
                                alignment=ft.Alignment.TOP_CENTER,
                                content=ft.Column(
                                    width=1000,
                                    spacing=14,
                                    controls=[
                                        header_form,
                                        ft.Container(
                                            height=1,
                                            bgcolor=ft.Colors.BLACK12,
                                            margin=ft.margin.only(top=4, bottom=2),
                                        ),
                                        ft.Container(
                                            height=640,
                                            content=result_list,
                                            padding=ft.Padding.only(top=8, bottom=12),
                                        ),
                                    ],
                                ),
                            )
                        ],
                    ),
                ),
                debug_bar,
            ],
        ),
    )

import asyncio
from collections import defaultdict
import re

import flet as ft

from core.active_db_scope import get_active_db_scope, has_active_db_scope, set_active_db_scope


def _normalize_dbtype(v: str) -> str:
    s = (v or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_esri_dbtype(v: str) -> bool:
    return _normalize_dbtype(v) in (
        "esri geodatabase",
        "enterprise geodatabase",
        "esri enterprise geodatabase",
        "esri",
    )


def build_dbcheckdublicateanddeleteesri_view(page: ft.Page) -> ft.Control:
    active_conn_name, active_schema_name, _ = get_active_db_scope(page)
    use_active_scope = has_active_db_scope(page, "esri")

    state = {
        "conn_name": active_conn_name if use_active_scope else None,
        "last_conn": active_conn_name if use_active_scope else "",
        "schema_name": active_schema_name if use_active_scope else None,
        "last_schema": active_schema_name if use_active_scope else "",
        "dataset_name": None,
        "last_dataset": "",
        "last_field": "",
        "rows": [],
    }

    dd_conn = ft.Dropdown(
        label="Esri DB Baglantisi Secimi",
        hint_text="Kayitli Esri Geodatabase baglantilarindan secim yapiniz",
        options=[],
        expand=True,
        visible=not use_active_scope,
    )
    dd_schema = ft.Dropdown(
        label="Sema Secimi",
        hint_text="Once baglanti seciniz",
        options=[],
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
    dd_dataset = ft.Dropdown(
        label="Veri Seti (Tablo) Secimi",
        hint_text="Once sema seciniz",
        options=[],
        expand=True,
        disabled=True,
    )
    dd_field = ft.Dropdown(
        label="Tekrar Kontrol Alani",
        hint_text="Once veri seti seciniz",
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

    def _safe_update(control: ft.Control):
        try:
            control.update()
        except RuntimeError as ex:
            if "must be added to the page first" not in str(ex).lower():
                raise

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

    def _set_debug(msg: str):
        debug_lbl.value = msg
        _safe_update(debug_lbl)

    def _selected_scope() -> tuple[str, str, str, str]:
        return (
            (state.get("conn_name") or "").strip(),
            (state.get("schema_name") or "").strip(),
            (state.get("dataset_name") or "").strip(),
            (dd_field.value or "").strip(),
        )

    def _set_controls_enabled():
        conn_ok = bool((state.get("conn_name") or "").strip())
        schema_ok = bool((state.get("schema_name") or "").strip())
        dataset_ok = bool((state.get("dataset_name") or "").strip())
        field_ok = bool((dd_field.value or "").strip())

        dd_schema.disabled = not conn_ok or len(dd_schema.options) == 0
        dd_dataset.disabled = not schema_ok or len(dd_dataset.options) == 0
        dd_field.disabled = not dataset_ok or len(dd_field.options) == 0
        btn_analyze.disabled = not (conn_ok and schema_ok and dataset_ok and field_ok)

        _safe_update(dd_schema)
        _safe_update(dd_dataset)
        _safe_update(dd_field)
        _safe_update(btn_analyze)

    def _clear_results(message: str = "Sonuc: Henuz analiz yapilmadi."):
        state["rows"] = []
        summary_text.value = message
        result_list.controls = []
        _safe_update(summary_text)
        _safe_update(result_list)

    def _group_rows_by_value(rows: list[dict]) -> list[tuple[str, list[dict]]]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            key = str(row.get("value") or "").strip()
            groups[key].append(row)

        grouped = []
        for value, items in groups.items():
            items.sort(key=lambda r: str(r.get("record_id") or ""))
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
                    val = str(row.get("record_id") or "")
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
                border=ft.border.only(right=ft.BorderSide(1, ft.Colors.BLACK12)),
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
                border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
                content=ft.Row(wrap=False, spacing=0, controls=header_cells),
            )
        )

        button_rows.append(
            ft.Container(
                width=130,
                padding=ft.Padding.only(left=6, right=6, top=6, bottom=6),
                border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
                bgcolor=ft.Colors.BLUE_50,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("Islem", weight=ft.FontWeight.BOLD),
            )
        )

        for row in items:
            rid = str(row.get("record_id") or "")
            feature_type = str(row.get("feature_type") or "")
            all_values = row.get("all_values") or {}
            row_ref = str(row.get("row_ref") or "")

            row_cells: list[ft.Control] = []
            row_cells.append(_cell(rid, col_width["KayitID"]))
            row_cells.append(_cell(feature_type, col_width["Tip"]))
            for field in field_order:
                row_cells.append(_cell(str(all_values.get(field) or ""), col_width[field]))

            detail_rows.append(
                ft.Container(
                    border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
                    content=ft.Row(wrap=False, spacing=0, controls=row_cells),
                )
            )

            button_rows.append(
                ft.Container(
                    width=130,
                    padding=ft.Padding.only(left=6, right=6, top=6, bottom=6),
                    border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.BLACK12)),
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
                        on_click=lambda e, rr=row_ref: page.run_task(on_delete_click, rr),
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
            _safe_update(summary_text)
            _safe_update(result_list)
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
        _safe_update(summary_text)
        _safe_update(result_list)

    def _reset_schema_dropdown():
        dd_schema.options = []
        dd_schema.value = None
        state["schema_name"] = None
        state["last_schema"] = ""
        _safe_update(dd_schema)
        _reset_dataset_dropdown()

    def _reset_dataset_dropdown():
        dd_dataset.options = []
        dd_dataset.value = None
        state["dataset_name"] = None
        state["last_dataset"] = ""
        _safe_update(dd_dataset)
        _reset_field_dropdown()

    def _reset_field_dropdown():
        dd_field.options = []
        dd_field.value = None
        state["last_field"] = ""
        _safe_update(dd_field)
        _set_controls_enabled()
        _clear_results("Sonuc: Henuz analiz yapilmadi.")

    async def _refresh_esri_connections():
        _set_busy(True, "Esri Geodatabase baglantilari yukleniyor...")
        try:
            res = await asyncio.to_thread(page.api.db_list)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            dd_conn.options = []
            dd_conn.value = None
            state["conn_name"] = None
            state["last_conn"] = ""
            _reset_schema_dropdown()
            _safe_update(dd_conn)
            _set_debug("UYARILAR: baglanti listesi alinamadi.")
            _notify("Hata", (res or {}).get("message", "Baglantilar okunamadi."))
            return

        items = res.get("data") or []
        esri = [
            r
            for r in items
            if isinstance(r, dict)
            and (r.get("Conn_Name") or "").strip()
            and _is_esri_dbtype(str(r.get("DbType") or ""))
        ]

        dd_conn.options = [
            ft.dropdown.Option(
                key=r["Conn_Name"],
                text=f'{r["Conn_Name"]} ({r.get("DbType", "-")})',
            )
            for r in esri
        ]
        dd_conn.value = None
        state["conn_name"] = None
        state["last_conn"] = ""

        _safe_update(dd_conn)
        _reset_schema_dropdown()
        _set_debug(f"UYARILAR: {len(esri)} Esri Geodatabase baglantisi yuklendi.")
        _set_controls_enabled()

    async def _load_schemas_for_conn(conn_name: str):
        state["conn_name"] = conn_name or None
        _reset_schema_dropdown()

        if not conn_name:
            _set_debug("UYARILAR: baglanti secimi temizlendi.")
            _set_controls_enabled()
            return

        _set_busy(True, "Sema listesi aliniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.dbcheckdublicateanddeleteesri_list_schemas,
                conn_name,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", f"{(res or {}).get('message', 'Sema listesi alinamadi.')}\n\n{(res or {}).get('debug', '')}".strip())
            _set_debug(f"UYARILAR: sema listesi alinamadi | {conn_name}")
            _set_controls_enabled()
            return

        schemas = [s for s in (res.get("data") or []) if (s or "").strip()]
        dd_schema.options = [ft.dropdown.Option(key=s, text=s) for s in schemas]
        _safe_update(dd_schema)
        _set_debug(f"UYARILAR: {len(schemas)} sema yuklendi.")
        _set_controls_enabled()

    async def _load_datasets_for_schema(schema_name: str):
        state["schema_name"] = schema_name or None
        conn_name = (state.get("conn_name") or "").strip()
        if conn_name and schema_name:
            set_active_db_scope(page, conn_name, schema_name, "esri")
        _reset_dataset_dropdown()

        conn_name = (state.get("conn_name") or "").strip()
        if not conn_name or not schema_name:
            if not schema_name:
                _set_debug("UYARILAR: sema secimi temizlendi.")
            _set_controls_enabled()
            return

        _set_busy(True, "Veri setleri aliniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.dbcheckdublicateanddeleteesri_list_datasets,
                conn_name,
                schema_name,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", f"{(res or {}).get('message', 'Veri setleri alinamadi.')}\n\n{(res or {}).get('debug', '')}".strip())
            _set_debug(f"UYARILAR: veri setleri alinamadi | {schema_name}")
            _set_controls_enabled()
            return

        datasets = [d for d in (res.get("data") or []) if (d or "").strip()]
        dd_dataset.options = [ft.dropdown.Option(key=d, text=d) for d in datasets]
        _safe_update(dd_dataset)
        _set_debug(f"UYARILAR: {len(datasets)} veri seti yuklendi.")
        _set_controls_enabled()

    async def _load_fields_for_dataset(dataset_name: str):
        state["dataset_name"] = dataset_name or None
        _reset_field_dropdown()

        conn_name, schema_name, ds_name, _ = _selected_scope()
        if not conn_name or not schema_name or not ds_name:
            if not ds_name:
                _set_debug("UYARILAR: veri seti secimi temizlendi.")
            _set_controls_enabled()
            return

        _set_busy(True, "Alanlar aliniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.dbcheckdublicateanddeleteesri_list_fields,
                conn_name,
                schema_name,
                ds_name,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", f"{(res or {}).get('message', 'Alanlar alinamadi.')}\n\n{(res or {}).get('debug', '')}".strip())
            _set_debug(f"UYARILAR: alanlar alinamadi | {schema_name}.{ds_name}")
            _set_controls_enabled()
            return

        fields = [f for f in (res.get("data") or []) if (f or "").strip()]
        dd_field.options = [ft.dropdown.Option(key=f, text=f) for f in fields]
        _safe_update(dd_field)

        _set_debug(f"UYARILAR: {len(fields)} alan yuklendi | {schema_name}.{ds_name}")
        _set_controls_enabled()

    async def on_analyze_click(e):
        conn_name, schema_name, dataset_name, field_name = _selected_scope()

        if not conn_name:
            _notify("Uyari", "Lutfen Esri DB baglantisi seciniz.")
            return
        if not schema_name:
            _notify("Uyari", "Lutfen sema seciniz.")
            return
        if not dataset_name:
            _notify("Uyari", "Lutfen veri seti seciniz.")
            return
        if not field_name:
            _notify("Uyari", "Lutfen tekrar kontrol alani seciniz.")
            return

        _set_busy(True, "Tekrarli kayitlar analiz ediliyor...")
        try:
            res = await asyncio.to_thread(
                page.api.dbcheckdublicateanddeleteesri_analyze,
                conn_name,
                schema_name,
                dataset_name,
                field_name,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", f"{(res or {}).get('message', 'Analiz basarisiz.')}\n\n{(res or {}).get('debug', '')}".strip())
            _set_debug(f"UYARILAR: analiz basarisiz | {schema_name}.{dataset_name}.{field_name}")
            return

        data = res.get("data") or {}
        rows = data.get("rows") or []
        state["rows"] = rows
        _render_results(rows, field_name)
        _set_debug(
            f"UYARILAR: analiz tamamlandi | {schema_name}.{dataset_name} | field={field_name} | duplicate={len(rows)}"
        )

    async def on_delete_click(row_ref: str):
        conn_name, schema_name, dataset_name, field_name = _selected_scope()
        if not conn_name or not schema_name or not dataset_name:
            _notify("Uyari", "Baglanti/scope bilgisi eksik.")
            return
        if not row_ref:
            _notify("Uyari", "Silinecek kayit referansi bos.")
            return

        _set_busy(True, "Kayit siliniyor...")
        try:
            res = await asyncio.to_thread(
                page.api.dbcheckdublicateanddeleteesri_delete,
                conn_name,
                schema_name,
                dataset_name,
                row_ref,
            )
            if not isinstance(res, dict) or not res.get("ok"):
                _notify("Hata", f"{(res or {}).get('message', 'Kayit silinemedi.')}\n\n{(res or {}).get('debug', '')}".strip())
                _set_debug(f"UYARILAR: kayit silme basarisiz | {row_ref}")
                return

            if field_name:
                analyze_res = await asyncio.to_thread(
                    page.api.dbcheckdublicateanddeleteesri_analyze,
                    conn_name,
                    schema_name,
                    dataset_name,
                    field_name,
                )
                if isinstance(analyze_res, dict) and analyze_res.get("ok"):
                    rows = (analyze_res.get("data") or {}).get("rows") or []
                    state["rows"] = rows
                    _render_results(rows, field_name)

            if hasattr(page, "dialog_service") and page.dialog_service:
                page.dialog_service.toast("Secilen kayit silindi.")

            _set_debug(f"UYARILAR: kayit silindi | {row_ref}")
        finally:
            _set_busy(False)

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
            await _load_datasets_for_schema(cur)

    async def _watch_dataset_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_dataset.value or "").strip()
            if cur == (state.get("last_dataset") or ""):
                continue
            state["last_dataset"] = cur
            await _load_fields_for_dataset(cur)

    async def _watch_field_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_field.value or "").strip()
            if cur == (state.get("last_field") or ""):
                continue
            state["last_field"] = cur
            _set_controls_enabled()

    dd_conn.on_change = lambda e: page.run_task(_load_schemas_for_conn, (dd_conn.value or "").strip())
    dd_schema.on_change = lambda e: page.run_task(_load_datasets_for_schema, (dd_schema.value or "").strip())
    dd_dataset.on_change = lambda e: page.run_task(_load_fields_for_dataset, (dd_dataset.value or "").strip())
    dd_field.on_change = lambda e: _set_controls_enabled()
    btn_analyze.on_click = lambda e: page.run_task(on_analyze_click, e)

    if use_active_scope:
        page.run_task(_watch_dataset_selection)
        page.run_task(_watch_field_selection)
        page.run_task(_load_datasets_for_schema, active_schema_name)
    else:
        page.run_task(_watch_conn_selection)
        page.run_task(_watch_schema_selection)
        page.run_task(_watch_dataset_selection)
        page.run_task(_watch_field_selection)
        page.run_task(_refresh_esri_connections)

    _set_controls_enabled()

    header_form = ft.Column(
        width=1040,
        spacing=12,
        controls=[
            active_scope_info,
            dd_conn,
            dd_schema,
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
        border=ft.border.only(top=ft.BorderSide(1, ft.Colors.BLACK12)),
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
                                    width=1060,
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

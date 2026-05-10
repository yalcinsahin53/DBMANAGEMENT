import asyncio
from difflib import get_close_matches

import flet as ft

from core.active_db_scope import get_active_db_scope, has_active_db_scope, set_active_db_scope


def build_dbmatchfeatureandload_view(page: ft.Page) -> ft.Control:
    active_conn_name, active_schema_name, _ = get_active_db_scope(page)
    use_active_scope = has_active_db_scope(page, "postgis")

    state = {
        "conn_name": active_conn_name if use_active_scope else None,
        "last_conn": active_conn_name if use_active_scope else None,
        "schema_name": active_schema_name if use_active_scope else None,
        "last_schema": active_schema_name if use_active_scope else None,
        "file_path": None,
        "tables": [],
        "layers": [],
        "layer_fields": {},
        "layer_table": {},
        "table_columns": {},
        "field_mapping": {},
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

    tf_file = ft.TextField(
        label="Seçilen Vektör Dosyası",
        hint_text="gml, shp, xml veya OGR destekli vektör dosyası seçiniz",
        read_only=True,
        expand=True,
    )

    btn_pick = ft.ElevatedButton("Veri Seti Seç")
    btn_load_structure = ft.ElevatedButton("Katmanları Oku", disabled=True)
    btn_transfer = ft.ElevatedButton("Eşleştir ve Yükle", disabled=True)

    summary_text = ft.Text("Durum: Dosya seçip katmanları okuyunuz.")
    layer_panel = ft.Column(spacing=10, expand=True, scroll=ft.ScrollMode.AUTO)

    busy = ft.ProgressRing(visible=False)
    busy_text = ft.Text("", visible=False)
    debug_lbl = ft.Text("UYARILAR: hazır", size=12, selectable=True)

    debug_bar = ft.Container(
        padding=ft.Padding.only(left=16, right=16, top=10, bottom=10),
        border=ft.border.only(top=ft.BorderSide(1, ft.Colors.BLACK12)),
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

    def _set_busy(on: bool, text: str = ""):
        busy.visible = on
        busy_text.visible = on
        busy_text.value = text or ""
        page.update()

    def _safe_update(control: ft.Control):
        try:
            control.update()
        except RuntimeError as ex:
            # View henuz page'e eklenmeden update denemelerini yoksay.
            if "must be added to the page first" not in str(ex).lower():
                raise

    def _normalize_dbtype(v: str) -> str:
        return (v or "").strip().lower().replace("_", " ").replace("-", " ")

    def _is_postgis(v: str) -> bool:
        return _normalize_dbtype(v).strip() == "postgis"

    def _set_debug(msg: str):
        debug_lbl.value = msg
        _safe_update(debug_lbl)

    def _clear_layer_state():
        state["layers"] = []
        state["layer_fields"] = {}
        state["layer_table"] = {}
        state["table_columns"] = {}
        state["field_mapping"] = {}

    def _reset_schema_dropdown():
        dd_schema.options = []
        dd_schema.value = None
        dd_schema.disabled = True
        state["schema_name"] = None
        state["last_schema"] = ""
        state["tables"] = []
        _clear_layer_state()
        _render_layers()
        _safe_update(dd_schema)
        _update_action_state()

    def _get_selected_table_count() -> int:
        count = 0
        for layer in state.get("layers", []):
            if (state["layer_table"].get(layer) or "").strip():
                count += 1
        return count

    def _update_action_state():
        conn_ok = bool((state.get("conn_name") or "").strip())
        schema_ok = bool((state.get("schema_name") or "").strip())
        file_ok = bool((state.get("file_path") or "").strip())
        layer_ok = len(state.get("layers", [])) > 0
        target_ok = _get_selected_table_count() > 0

        btn_load_structure.disabled = not (conn_ok and schema_ok and file_ok)
        btn_transfer.disabled = not (conn_ok and schema_ok and file_ok and layer_ok and target_ok)

        _safe_update(btn_load_structure)
        _safe_update(btn_transfer)

    def _render_layers():
        controls = []
        layers = state.get("layers", [])
        tables = state.get("tables", [])

        if not layers:
            controls = [
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.Text("Henüz okunmuş katman bulunmuyor."),
                )
            ]
            layer_panel.controls = controls
            _safe_update(layer_panel)
            _update_action_state()
            return

        for layer_name in layers:
            source_fields = state["layer_fields"].get(layer_name, [])
            selected_table = (state["layer_table"].get(layer_name) or "").strip()

            dd_table = ft.Dropdown(
                label="Hedef Tablo",
                hint_text="Bu katman için tablo seçiniz",
                width=360,
                options=[ft.dropdown.Option(key=t, text=t) for t in tables],
                value=selected_table if selected_table in tables else None,
            )

            def _table_change_handler(e, ln=layer_name, dd=dd_table):
                page.run_task(_on_layer_table_change, ln, (dd.value or "").strip())

            dd_table.on_change = _table_change_handler

            mapping_rows = []
            target_cols = []
            if selected_table:
                cols = state["table_columns"].get(selected_table) or []
                target_cols = [c["name"] for c in cols if not c.get("is_geometry")]

            if not source_fields:
                mapping_rows.append(ft.Text("Bu katmanda eşleştirilebilir alan bulunamadı."))
            elif selected_table and not target_cols:
                mapping_rows.append(ft.Text("Seçilen tabloda eşleştirilebilir kolon bulunamadı."))
            elif selected_table:
                for src_field in source_fields:
                    layer_map = state["field_mapping"].setdefault(layer_name, {})
                    cur_value = (layer_map.get(src_field) or "").strip()
                    if cur_value and cur_value not in target_cols:
                        cur_value = ""

                    dd_target = ft.Dropdown(
                        width=320,
                        options=[ft.dropdown.Option(key="", text="(Atla)")]
                        + [ft.dropdown.Option(key=c, text=c) for c in target_cols],
                        value=cur_value,
                    )

                    def _mapping_change_handler(
                        e, ln=layer_name, sf=src_field, dd=dd_target
                    ):
                        _on_field_mapping_change(ln, sf, (dd.value or "").strip())

                    dd_target.on_change = _mapping_change_handler

                    mapping_rows.append(
                        ft.Row(
                            spacing=10,
                            controls=[
                                ft.Container(
                                    width=300,
                                    content=ft.Text(src_field, selectable=True),
                                ),
                                dd_target,
                            ],
                        )
                    )
            else:
                mapping_rows.append(ft.Text("Önce hedef tablo seçiniz."))

            controls.append(
                ft.Container(
                    padding=ft.Padding.only(left=10, right=10, top=8, bottom=8),
                    border=ft.border.all(1, ft.Colors.BLACK12),
                    border_radius=8,
                    content=ft.ExpansionTile(
                        title=ft.Text(layer_name, selectable=True),
                        subtitle=ft.Text(
                            f"Kaynak alan: {len(source_fields)} | Hedef tablo: {selected_table or '-'}"
                        ),
                        maintain_state=True,
                        controls=[
                            ft.Container(
                                padding=ft.Padding.only(left=8, right=8, bottom=8),
                                content=ft.Column(
                                    spacing=8,
                                    controls=[
                                        dd_table,
                                        ft.Row(
                                            spacing=10,
                                            controls=[
                                                ft.Container(
                                                    width=300,
                                                    content=ft.Text(
                                                        "Kaynak Alan",
                                                        weight=ft.FontWeight.BOLD,
                                                    ),
                                                ),
                                                ft.Text(
                                                    "Hedef Kolon",
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                            ],
                                        ),
                                        *mapping_rows,
                                    ],
                                ),
                            )
                        ],
                    ),
                )
            )

        layer_panel.controls = controls
        _safe_update(layer_panel)
        summary_text.value = (
            f"Durum: {len(layers)} katman okundu, {_get_selected_table_count()} katmanda hedef tablo seçildi."
        )
        _safe_update(summary_text)
        _update_action_state()

    def _auto_map_fields_for_layer(layer_name: str):
        table_name = (state["layer_table"].get(layer_name) or "").strip()
        if not table_name:
            return

        cols = state["table_columns"].get(table_name) or []
        target_cols = [c["name"] for c in cols if not c.get("is_geometry")]
        if not target_cols:
            return

        layer_map = state["field_mapping"].setdefault(layer_name, {})
        source_fields = state["layer_fields"].get(layer_name) or []

        used_targets = {v for v in layer_map.values() if v}
        for src in source_fields:
            cur = (layer_map.get(src) or "").strip()
            if cur in target_cols:
                continue
            match = get_close_matches(src, target_cols, n=1, cutoff=0.45)
            picked = match[0] if match and match[0] not in used_targets else ""
            layer_map[src] = picked
            if picked:
                used_targets.add(picked)

    def _on_field_mapping_change(layer_name: str, source_field: str, target_col: str):
        layer_map = state["field_mapping"].setdefault(layer_name, {})
        if target_col:
            # Aynı katmanda aynı hedef kolona çift eşlemeyi engelle.
            for k, v in list(layer_map.items()):
                if k != source_field and v == target_col:
                    layer_map[k] = ""
        layer_map[source_field] = target_col
        _render_layers()

    async def _ensure_table_columns(table_name: str):
        table_name = (table_name or "").strip()
        if not table_name:
            return
        if table_name in state["table_columns"]:
            return

        conn_name = (state.get("conn_name") or "").strip()
        schema_name = (state.get("schema_name") or "").strip()
        if not conn_name or not schema_name:
            return

        res = await asyncio.to_thread(
            page.api.postgis_dbmatch_table_columns, conn_name, schema_name, table_name
        )
        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", f"Kolon listesi alınamadı.\n{(res or {}).get('message','')}")
            return
        state["table_columns"][table_name] = res.get("data") or []

    async def _on_layer_table_change(layer_name: str, table_name: str):
        state["layer_table"][layer_name] = table_name or ""
        if table_name:
            await _ensure_table_columns(table_name)
            _auto_map_fields_for_layer(layer_name)
        else:
            state["field_mapping"][layer_name] = {}
        _render_layers()
        _set_debug(f"UYARILAR: {layer_name} katmanı için tablo seçimi güncellendi.")

    async def _refresh_postgis_connections():
        _set_busy(True, "PostGIS bağlantıları yükleniyor...")
        try:
            res = await asyncio.to_thread(page.api.db_list)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", (res or {}).get("message", "Bağlantılar okunamadı."))
            dd_conn.options = []
            dd_conn.value = None
            state["conn_name"] = None
            state["last_conn"] = ""
            _reset_schema_dropdown()
            return

        items = res.get("data") or []
        postgis = [
            r
            for r in items
            if isinstance(r, dict)
            and (r.get("Conn_Name") or "").strip()
            and _is_postgis(str(r.get("DbType") or ""))
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
        state["last_conn"] = ""
        _reset_schema_dropdown()
        page.update()
        _set_debug(f"UYARILAR: {len(postgis)} PostGIS bağlantısı yüklendi.")

    async def _load_schemas_for_conn(conn_name: str):
        state["conn_name"] = conn_name or None
        _reset_schema_dropdown()

        if not conn_name:
            _set_debug("UYARILAR: bağlantı seçimi temizlendi.")
            return

        _set_busy(True, "Şema listesi alınıyor...")
        try:
            res = await asyncio.to_thread(page.api.postgis_list_schemas, conn_name)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (res or {}).get("message", "Şema listesi alınamadı.")
            dbg = (res or {}).get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            _set_debug(f"UYARILAR: şema listesi alınamadı | {conn_name}")
            return

        schemas = [s for s in (res.get("data") or []) if (s or "").strip()]
        dd_schema.options = [ft.dropdown.Option(key=s, text=s) for s in schemas]
        dd_schema.disabled = False
        _safe_update(dd_schema)
        _set_debug(f"UYARILAR: {len(schemas)} şema yüklendi.")
        _update_action_state()

    async def _load_tables(conn_name: str, schema_name: str):
        state["tables"] = []
        _clear_layer_state()
        _render_layers()

        if not conn_name or not schema_name:
            return

        _set_busy(True, "Tablo listesi alınıyor...")
        try:
            res = await asyncio.to_thread(
                page.api.postgis_dbmatch_schema_tables, conn_name, schema_name
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify("Hata", f"Tablolar alınamadı.\n{(res or {}).get('message','')}")
            return

        tables = [t for t in (res.get("data") or []) if (t or "").strip()]
        state["tables"] = tables
        _render_layers()
        _set_debug(f"UYARILAR: {len(tables)} tablo yüklendi.")
        _update_action_state()

    async def on_conn_change(e):
        conn_name = (dd_conn.value or "").strip()
        state["last_conn"] = conn_name
        state["conn_name"] = conn_name or None
        await _load_schemas_for_conn(conn_name)
        _update_action_state()

    async def on_schema_change(e):
        schema_name = (dd_schema.value or "").strip()
        state["last_schema"] = schema_name
        state["schema_name"] = schema_name or None
        conn_name = (state.get("conn_name") or "").strip()
        if conn_name and schema_name:
            set_active_db_scope(page, conn_name, schema_name, "postgis")
        await _load_tables((state.get("conn_name") or "").strip(), schema_name)
        _update_action_state()

    async def _watch_conn_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_conn.value or "").strip()
            if cur == (state.get("last_conn") or ""):
                continue
            state["last_conn"] = cur
            state["conn_name"] = cur or None
            await _load_schemas_for_conn(cur)
            _update_action_state()

    async def _watch_schema_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_schema.value or "").strip()
            if cur == (state.get("last_schema") or ""):
                continue
            state["last_schema"] = cur
            state["schema_name"] = cur or None
            await _load_tables((state.get("conn_name") or "").strip(), cur)
            _update_action_state()

    async def on_pick_click(e):
        try:
            picked = await ft.FilePicker().pick_files(
                dialog_title="Veri seti seçiniz (gml/shp/xml ve benzeri)",
                allow_multiple=False,
                allowed_extensions=[
                    "gml",
                    "xml",
                    "shp",
                    "geojson",
                    "json",
                    "kml",
                    "gpkg",
                ],
            )
        except Exception as ex:
            _notify("Hata", f"Dosya seçimi açılamadı.\n{ex}")
            return

        files = picked or []
        if not files:
            _notify("Bilgi", "Dosya seçimi iptal edildi.")
            return

        path = (files[0].path or "").strip()
        if not path:
            _notify("Hata", "Seçilen dosya yolu okunamadı.")
            return

        state["file_path"] = path
        tf_file.value = path
        _safe_update(tf_file)
        _clear_layer_state()
        _render_layers()
        _set_debug(f"UYARILAR: dosya seçildi | {path}")
        _update_action_state()

    async def on_load_structure_click(e):
        conn_name = (state.get("conn_name") or "").strip()
        schema_name = (state.get("schema_name") or "").strip()
        file_path = (state.get("file_path") or "").strip()
        if not conn_name or not schema_name or not file_path:
            _notify("Uyarı", "Önce bağlantı, şema ve dosya seçimi tamamlanmalı.")
            return

        _set_busy(True, "Katman yapısı okunuyor...")
        try:
            res = await asyncio.to_thread(page.api.postgis_dbmatch_vector_structure, file_path)
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify(
                "Hata",
                f"{(res or {}).get('message','Katman yapısı okunamadı.')}\n\n{(res or {}).get('debug','')}",
            )
            return

        layers_data = ((res.get("data") or {}).get("layers") or [])
        if not layers_data:
            _notify("Bilgi", "Dosyada eşleştirilebilir katman bulunamadı.")
            return

        state["layers"] = []
        state["layer_fields"] = {}
        state["layer_table"] = {}
        state["field_mapping"] = {}

        table_names = state.get("tables") or []
        for layer_obj in layers_data:
            lname = (layer_obj or {}).get("name")
            if not lname or not str(lname).strip():
                continue
            layer_name = str(lname).strip()
            source_fields = [
                f for f in ((layer_obj or {}).get("fields") or []) if (f or "").strip()
            ]

            state["layers"].append(layer_name)
            state["layer_fields"][layer_name] = source_fields
            state["field_mapping"][layer_name] = {}

            guessed_table = ""
            if table_names:
                match = get_close_matches(layer_name, table_names, n=1, cutoff=0.3)
                guessed_table = match[0] if match else ""
            state["layer_table"][layer_name] = guessed_table

        # Seçili tabloların kolonlarını önceden yükle ve otomatik alan eşleşmesi yap.
        selected_tables = sorted(
            {t for t in state["layer_table"].values() if (t or "").strip()}
        )
        for tname in selected_tables:
            await _ensure_table_columns(tname)
        for lname in state["layers"]:
            _auto_map_fields_for_layer(lname)

        _render_layers()
        dbg = (res.get("debug") or "").strip()
        _set_debug(
            f"UYARILAR: {len(state['layers'])} katman okundu."
            + (f" | {dbg}" if dbg else "")
        )

    def _build_transfer_payload() -> list[dict]:
        payload = []
        for layer_name in state.get("layers", []):
            table_name = (state["layer_table"].get(layer_name) or "").strip()
            if not table_name:
                continue

            fmap = {}
            for src_field, tgt_col in (state["field_mapping"].get(layer_name) or {}).items():
                src = (src_field or "").strip()
                tgt = (tgt_col or "").strip()
                if src and tgt:
                    fmap[src] = tgt

            payload.append(
                {
                    "source_layer": layer_name,
                    "target_table": table_name,
                    "field_mapping": fmap,
                }
            )
        return payload

    async def on_transfer_click(e):
        conn_name = (state.get("conn_name") or "").strip()
        schema_name = (state.get("schema_name") or "").strip()
        file_path = (state.get("file_path") or "").strip()
        layer_payload = _build_transfer_payload()

        if not conn_name or not schema_name or not file_path:
            _notify("Uyarı", "Önce bağlantı, şema ve dosya seçimi tamamlanmalı.")
            return
        if not layer_payload:
            _notify("Uyarı", "Aktarım için en az bir katman-hedef tablo eşleştirmesi yapınız.")
            return

        _set_busy(True, "Eşleme ile aktarım çalışıyor...")
        try:
            res = await asyncio.to_thread(
                page.api.postgis_dbmatch_load,
                conn_name,
                schema_name,
                file_path,
                layer_payload,
            )
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            _notify(
                "Hata",
                f"{(res or {}).get('message','Aktarım başarısız.')}\n\n{(res or {}).get('debug','')}",
            )
            _set_debug("UYARILAR: aktarım başarısız.")
            return

        data = res.get("data") or {}
        success_count = int(data.get("success_count") or 0)
        failed_count = int(data.get("failed_count") or 0)
        result_rows = data.get("results") or []

        summary_lines = [res.get("message") or "Aktarım tamamlandı."]
        for r in result_rows:
            layer_txt = (r.get("layer") or "-").strip() or "-"
            table_txt = (r.get("table") or "-").strip() or "-"
            if r.get("ok"):
                summary_lines.append(
                    f"- OK | {layer_txt} -> {table_txt} | eklenen: {r.get('inserted', 0)}"
                )
            else:
                summary_lines.append(
                    f"- HATA | {layer_txt} -> {table_txt} | {r.get('message','')}"
                )

        _notify("Sonuç", "\n".join(summary_lines[:40]))
        _set_debug(
            f"UYARILAR: aktarım tamamlandı | başarılı={success_count}, hatalı={failed_count}"
        )

    dd_conn.on_change = lambda e: page.run_task(on_conn_change, e)
    dd_schema.on_change = lambda e: page.run_task(on_schema_change, e)
    btn_pick.on_click = lambda e: page.run_task(on_pick_click, e)
    btn_load_structure.on_click = lambda e: page.run_task(on_load_structure_click, e)
    btn_transfer.on_click = lambda e: page.run_task(on_transfer_click, e)

    if use_active_scope:
        page.run_task(_load_tables, active_conn_name, active_schema_name)
    else:
        page.run_task(_watch_conn_selection)
        page.run_task(_watch_schema_selection)
        page.run_task(_refresh_postgis_connections)

    form = ft.Column(
        width=1000,
        spacing=16,
        controls=[
            active_scope_info,
            dd_conn,
            dd_schema,
            ft.Row(spacing=10, controls=[tf_file, btn_pick]),
            ft.Row(spacing=10, controls=[btn_load_structure, btn_transfer]),
            summary_text,
            ft.Container(
                height=430,
                border=ft.border.all(1, ft.Colors.BLACK12),
                border_radius=8,
                padding=10,
                content=layer_panel,
            ),
        ],
    )

    _render_layers()
    _update_action_state()

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
                        padding=ft.Padding.only(left=36, right=36, top=32, bottom=16),
                        controls=[ft.Container(alignment=ft.Alignment.TOP_CENTER, content=form)],
                    ),
                ),
                debug_bar,
            ],
        ),
    )

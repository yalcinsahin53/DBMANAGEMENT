import asyncio
import io
import os
import zipfile
import flet as ft


def build_wfsdownload_view(page: ft.Page) -> ft.Control:

    state = {
        "conn": None,
        "typename": None,
        "last_conn": None,
        "last_typename": None,
        "vector_format": "gml",
        # dinamik filtre panelleri
        "filters": [],  # list[dict]
        # typename'a göre cache'lenen alan seçenekleri (Dropdown options)
        "field_opts": [],  # list[ft.dropdown.Option]
    }

    # ---------------- UI (üst seçimler) ----------------
    dd_conn = ft.Dropdown(
        label="Bağlantı Seçimi",
        hint_text="Kayıtlı bağlantılardan seçim yapınız!",
        expand=True,
    )

    dd_typename = ft.Dropdown(
        label="Veri Seti Seçimi (typeName)",
        width=260,
        disabled=True,
    )

    dd_vector_format = ft.Dropdown(
        label="Vektör Formatı",
        width=180,
        value="gml",
        options=[
            ft.dropdown.Option(key="gml", text=".gml"),
            ft.dropdown.Option(key="shp", text=".shp"),
        ],
    )

    btn_download = ft.ElevatedButton("Veri Seti İndir", disabled=True)
    btn_download_schema = ft.ElevatedButton("Veri Seti Şeması İndir", disabled=True)

    btn_download_filtered = ft.ElevatedButton("Filtreli Veri Seti İndir", disabled=True)

    btn_add_filter = ft.ElevatedButton(content=ft.Text("Filtre Ekle"), disabled=True)

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

    # Filtre panelleri: scroll'lu alan
    filters_scroll = ft.ListView(
        spacing=10,
        expand=True,  # container içinde expand
        auto_scroll=False,  # istersen True yapabilirsin
    )

    filters_container = ft.Container(
        visible=False,  # ✅ EKLE
        padding=10,
        border=ft.border.all(1, ft.Colors.BLACK12),
        border_radius=10,
        expand=True,
        content=filters_scroll,
    )

    # ---------------- helpers ----------------
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

    def _normalize_vector_format(raw: str | None) -> str:
        v = (raw or "").strip().lower()
        if v.startswith("."):
            v = v[1:]
        if v == "shp":
            return "shp"
        return "gml"

    def _get_selected_vector_format() -> str:
        # Dropdown değeri farklı Flet sürümlerinde key/text gelebildiği için normalize ediyoruz.
        control_val = getattr(dd_vector_format, "value", None)
        fmt = _normalize_vector_format(control_val)
        state["vector_format"] = fmt
        return fmt

    def _set_busy(on: bool, text: str = ""):
        busy.visible = on
        busy_text.visible = on
        busy_text.value = text or ""
        page.update()

    def _unique_values(vals):
        seen = set()
        out = []
        for v in vals or []:
            s = "" if v is None else str(v).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        out.sort()
        return out

    def _escape_cql_literal(v: str) -> str:
        return (v or "").replace("'", "''")

    def _panel_to_cql(panel: dict) -> str | None:
        field = (panel.get("field") or "").strip()
        values = list(panel.get("selected_values") or [])
        if not field or not values:
            return None

        # tek değer
        if len(values) == 1:
            v = _escape_cql_literal(values[0])
            return f"{field} = '{v}'"

        # çoklu değer
        safe_vals = [f"'{_escape_cql_literal(x)}'" for x in values]
        return f"{field} IN ({', '.join(safe_vals)})"

    def _build_cql_from_all_filters() -> str | None:
        """
        Aynı alan birden fazla panelde seçilmişse değerleri birleştir (OR/IN),
        farklı alanlar arasında AND uygula.
        """
        by_field: dict[str, set[str]] = {}
        field_order: list[str] = []

        for p in state.get("filters", []):
            field = (p.get("field") or "").strip()
            if not field:
                continue
            vals = {
                str(v).strip()
                for v in (p.get("selected_values") or [])
                if str(v).strip()
            }
            if not vals:
                continue
            if field not in by_field:
                by_field[field] = set()
                field_order.append(field)
            by_field[field].update(vals)

        parts: list[str] = []
        for field in field_order:
            vals = sorted(by_field.get(field) or [])
            if not vals:
                continue
            if len(vals) == 1:
                v = _escape_cql_literal(vals[0])
                parts.append(f"({field} = '{v}')")
            else:
                safe_vals = [f"'{_escape_cql_literal(x)}'" for x in vals]
                parts.append(f"({field} IN ({', '.join(safe_vals)}))")

        if not parts:
            return None
        return " AND ".join(parts)

    def _update_filtered_button_state():
        if not (state.get("conn") and state.get("typename")):
            btn_download_filtered.disabled = True
            btn_download_filtered.update()
            return

        has_any_valid_filter = False
        for p in state.get("filters", []):
            if (p.get("field") or "").strip() and p.get("selected_values"):
                has_any_valid_filter = True
                break

        btn_download_filtered.disabled = not has_any_valid_filter
        btn_download_filtered.update()

    def _reset_filters():
        state["filters"].clear()
        filters_scroll.controls.clear()
        _sync_filters_container_visibility()  # ✅ EKLE
        page.update()
        _update_filtered_button_state()

    # ---------------- API wrappers ----------------
    def api_list_connections():
        return page.api.wfs_list()

    def api_typenames(conn_name: str):
        return page.api.wfs_typenames_meta(conn_name)

    def api_fields(conn_name: str, typename: str):
        return page.api.wfs_fields_meta(conn_name, typename)

    def api_count(conn_name: str, typename: str):
        return page.api.wfs_count(conn_name, typename)

    def api_field_values(conn_name: str, typename: str, field: str):
        return page.api.wfs_field_values(conn_name, typename, field)

    # ---------------- dynamic filter panel factory ----------------
    def _make_filter_panel(index: int) -> dict:
        """
        1 filtre paneli üretir:
          - ExpansionTile (akordion)
          - dd_field, btn_list_values
          - checkbox listesi
        """
        panel_state = {
            "index": index,
            "field": None,
            "values": [],
            "selected_values": set(),
            "last_field": None,
        }

        dd_field = ft.Dropdown(
            label="Alan Adı Seçimi",
            expand=True,
            disabled=False,  # panel açıkken alan seçilebilir
        )

        async def _watch_field_selection():
            while True:
                await asyncio.sleep(0.2)

                # panel ekrandan kaldırıldıysa dur
                if panel_state not in state["filters"]:
                    return

                cur = (dd_field.value or "").strip()
                last = (panel_state.get("last_field") or "").strip()

                if not cur or cur == last:
                    continue

                # seçimi kaydet
                panel_state["last_field"] = cur
                panel_state["field"] = cur

                # önceki değerleri sıfırla
                panel_state["values"] = []
                panel_state["selected_values"].clear()
                values_list.controls.clear()

                # ✅ Listede Göster aktif et
                btn_list_values.disabled = False
                btn_list_values.update()

                # başlığı güncelle
                _refresh_panel_title()

                # filtreli indir butonunu güncelle
                _update_filtered_button_state()

        btn_list_values = ft.ElevatedButton("Listede Göster", disabled=True)

        values_list = ft.ListView(expand=True, spacing=2)

        # ✅ watcher'ı 1 kere başlat
        page.run_task(_watch_field_selection)

        def _select_all(_e=None):
            panel_state["selected_values"] = set(map(str, panel_state["values"]))
            for c in values_list.controls:
                if isinstance(c, ft.Checkbox):
                    c.value = True
            page.update()
            _update_filtered_button_state()
            _refresh_panel_title()

        def _clear_all(_e=None):
            panel_state["selected_values"].clear()
            for c in values_list.controls:
                if isinstance(c, ft.Checkbox):
                    c.value = False
            page.update()
            _update_filtered_button_state()
            _refresh_panel_title()

        def _close_values(_e=None):
            # sadece panel içeriğini daraltmak için listview’u gizlemiyoruz; kullanıcı akordiona basıp kapatabilir
            pass

        values_panel = ft.Container(
            visible=True,
            padding=10,
            border=ft.border.all(1, ft.Colors.BLACK12),
            border_radius=8,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("Değer Seçimi", weight=ft.FontWeight.BOLD),
                            ft.Container(expand=True),
                            ft.TextButton("Tümünü Seç", on_click=_select_all),
                            ft.TextButton("Tümünü Temizle", on_click=_clear_all),
                        ]
                    ),
                    ft.Container(height=280, content=values_list),
                ],
            ),
        )

        # Panel başlığını seçim sayısına göre dinamik güncelle
        title_text = ft.Text(f"Filtre {index + 1}", weight=ft.FontWeight.BOLD)

        def _refresh_panel_title():
            f = (panel_state.get("field") or "").strip()
            n = len(panel_state.get("selected_values") or [])
            if f and n:
                title_text.value = f"Filtre {index + 1}: {f} ({n} seçim)"
            elif f:
                title_text.value = f"Filtre {index + 1}: {f}"
            else:
                title_text.value = f"Filtre {index + 1}"
            title_text.update()

        def _on_field_changed(e: ft.ControlEvent):
            # seçilen alan
            val = (e.control.value or "").strip()

            # state güncelle
            panel_state["field"] = val
            panel_state["last_field"] = val

            # önceki seçimleri sıfırla
            panel_state["values"] = []
            panel_state["selected_values"].clear()
            values_list.controls.clear()

            # ✅ butonu anında aç/kapat
            btn_list_values.disabled = val == ""
            btn_list_values.update()

            # başlık ve genel filtre butonu state
            _refresh_panel_title()
            _update_filtered_button_state()

            # debug istersen:
            # debug_lbl.value = f"DEBUG(panel {index+1}): field={val!r} btn_list_values.disabled={btn_list_values.disabled}"
            # page.update()

        async def _on_list_values_click(e):
            if not (
                state["conn"]
                and state["typename"]
                and (panel_state["field"] or "").strip()
            ):
                return

            _set_busy(True, "Alan değerleri alınıyor...")
            res = await asyncio.to_thread(
                api_field_values, state["conn"], state["typename"], panel_state["field"]
            )
            _set_busy(False)

            if not isinstance(res, dict) or not res.get("ok"):
                _notify(
                    "Hata",
                    f"{(res or {}).get('message','Değerler alınamadı.')}\n\n{(res or {}).get('debug','')}",
                )
                return

            raw_vals = res.get("data") or []
            vals = _unique_values(raw_vals)

            if not vals:
                _notify(
                    "Bilgi", "Seçilen alan için listelenecek unique değer bulunamadı."
                )
                values_list.controls.clear()
                page.update()
                return

            panel_state["values"] = vals
            panel_state["selected_values"].clear()
            values_list.controls.clear()

            def make_cb(v: str):
                def _on_change(ev):
                    if ev.control.value:
                        panel_state["selected_values"].add(v)
                    else:
                        panel_state["selected_values"].discard(v)
                    _update_filtered_button_state()
                    _refresh_panel_title()

                return ft.Checkbox(label=v, value=False, on_change=_on_change)

            if len(vals) > 10000:
                _notify(
                    "Bilgi",
                    f"{len(vals)} unique değer listelenecek; arayüz yavaşlayabilir.",
                )

            for v in vals:
                values_list.controls.append(make_cb(v))

            page.update()
            _update_filtered_button_state()
            _refresh_panel_title()

        dd_field.on_change = _on_field_changed
        btn_list_values.on_click = lambda e: page.run_task(_on_list_values_click, e)

        # Paneli kaldır (silme) butonu: sadece ilave paneller için görünür
        btn_remove = ft.IconButton(
            icon=ft.Icons.CLOSE,
            tooltip="Filtreyi kaldır",
            on_click=lambda e: _remove_filter_panel(panel_state),
        )

        header_row = ft.Row(
            controls=[
                title_text,
                ft.Container(expand=True),
                btn_remove,
            ]
        )

        panel_body = ft.Container(
            padding=10,
            visible=True,  # ✅ default açık
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row(spacing=12, controls=[dd_field, btn_list_values]),
                    values_panel,
                ],
            ),
        )

        tile = ft.ExpansionTile(
            title=header_row,
            controls=[panel_body],
        )

        # ✅ bazı sürümlerde expanded property varsa onu da set etmeyi dene
        try:
            tile.expanded = True
        except Exception:
            pass

        panel_state["dd_field"] = dd_field
        panel_state["btn_list_values"] = btn_list_values
        panel_state["values_list"] = values_list
        panel_state["tile"] = tile
        panel_state["panel_body"] = panel_body
        panel_state["_refresh_title"] = _refresh_panel_title

        return panel_state

    def _remove_filter_panel(panel_state: dict):
        # state listesinden çıkar
        try:
            state["filters"].remove(panel_state)
        except ValueError:
            pass

        # UI’dan çıkar
        try:
            filters_scroll.controls.remove(panel_state["tile"])
        except Exception:
            pass

        # indeksleri ve başlıkları yeniden düzenle
        for i, p in enumerate(state["filters"]):
            p["index"] = i
            # başlıklar yeniden
            if p.get("_refresh_title"):
                p["_refresh_title"]()

        # hiç filtre kalmadıysa panel alanını kapat (istersen)
        if len(state["filters"]) == 0:
            filters_container.visible = False

        _sync_filters_container_visibility()
        page.update()
        _update_filtered_button_state()

    async def _load_field_options_cache():
        """
        typename seçilince alan listesi alınır ve state["field_opts"] içine cache'lenir.
        Mevcut filtreleri RESETLEMEZ.
        """
        if not (state.get("conn") and state.get("typename")):
            state["field_opts"] = []
            return

        _set_busy(True, "Alan adları alınıyor...")
        try:
            res = await asyncio.to_thread(api_fields, state["conn"], state["typename"])
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (
                res.get("message") if isinstance(res, dict) else ""
            ) or "Alanlar alınamadı."
            dbg = (res.get("debug") if isinstance(res, dict) else "") or ""
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            state["field_opts"] = []
            return

        items = res.get("data") or []
        state["field_opts"] = [
            ft.dropdown.Option(
                key=i["name"], text=f'{i["name"]} ({i.get("type","unknown")})'
            )
            for i in items
            if isinstance(i, dict) and i.get("name")
        ]

    def _apply_field_opts_to_panel(p: dict, *, reset_selection: bool):
        """
        Cache'lenen state["field_opts"] seçeneklerini panele uygular.
        reset_selection=True ise panel seçimini temizler; False ise dokunmaz.
        """
        dd = p["dd_field"]
        dd.options = state.get("field_opts") or []
        if reset_selection:
            dd.value = None
            p["field"] = None
            p["last_field"] = None
            p["values"] = []
            p["selected_values"].clear()
            p["values_list"].controls.clear()
            p["btn_list_values"].disabled = True
            if p.get("_refresh_title"):
                p["_refresh_title"]()

    # ---------------- loading chain ----------------
    async def refresh_connections():
        _set_busy(True, "WFS bağlantıları yükleniyor...")
        try:
            res = await asyncio.to_thread(api_list_connections)
        except Exception as ex:
            _set_busy(False)
            _notify("Hata", f"WFS liste exception:\n{ex}")
            return
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = ""
            dbg = ""
            if isinstance(res, dict):
                msg = (res.get("message") or "").strip()
                dbg = (res.get("debug") or "").strip()
            if not msg and not dbg:
                msg = "WFS liste çağrısı başarısız (message/debug boş)."
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            dd_conn.options = []
            dd_conn.value = None
            _reset_after_conn()
            return

        items = res.get("data") or []
        dd_conn.options = [
            ft.dropdown.Option(key=r["Conn_Name"], text=r["Conn_Name"])
            for r in items
            if isinstance(r, dict) and r.get("Conn_Name")
        ]
        dd_conn.value = None
        _reset_after_conn()
        page.update()

        page.run_task(_watch_conn_selection)

    def _reset_after_conn():
        state["typename"] = None
        dd_typename.value = None
        dd_typename.options = []
        dd_typename.disabled = True

        btn_download.disabled = True
        btn_download_schema.disabled = True
        btn_download_filtered.disabled = True
        btn_add_filter.disabled = True
        btn_add_filter.disabled = True

        _reset_filters()
        page.update()

    def _reset_after_typename():
        btn_download.disabled = False
        btn_download_schema.disabled = False
        btn_add_filter.disabled = False
        btn_add_filter.disabled = False
        btn_download_schema.update()
        page.update()
        _update_filtered_button_state()

    async def _load_typenames_for_conn(conn_name: str):
        state["conn"] = conn_name
        _reset_after_conn()

        _set_busy(True, "typeName listesi alınıyor...")
        try:
            res = await asyncio.to_thread(api_typenames, conn_name)
        except Exception as ex:
            _notify("Hata", f"typeName exception:\n{ex}")
            return
        finally:
            _set_busy(False)

        if not isinstance(res, dict) or not res.get("ok"):
            msg = (
                res.get("message") if isinstance(res, dict) else ""
            ) or "typeName alınamadı."
            dbg = (res.get("debug") if isinstance(res, dict) else "") or ""
            _notify("WFS Hata", f"{msg}\n\n{dbg}".strip())
            return

        items = res.get("data") or []  # [{"name":"cities","geom":"Point"}...]
        dd_typename.options = [
            ft.dropdown.Option(
                key=i["name"], text=f'{i["name"]} ({i.get("geom","Unknown")})'
            )
            for i in items
            if isinstance(i, dict) and i.get("name")
        ]
        dd_typename.disabled = False
        page.update()

        page.run_task(_watch_typename_selection)

    async def _load_after_typename_selected(typename: str):
        state["typename"] = typename
        _reset_after_typename()

        # ilk filtre paneli varsa/ekliyse alanları doldur

        # alan option cache yükle
        await _load_field_options_cache()

        # varsa panellere uygula (typename değişti, eski seçimler geçersiz -> reset)
        for p in state["filters"]:
            _apply_field_opts_to_panel(p, reset_selection=True)

        page.update()
        _update_filtered_button_state()

        # count uyarısı
        res_count = await asyncio.to_thread(api_count, state["conn"], typename)
        c = (res_count.get("data") or {}).get("count")
        if isinstance(c, int) and c > 1000:
            _notify("Uyarı", f"Toplam Veri Adedi {c}. Filtre eklemek isteyebilirsiniz.")

    async def _watch_conn_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_conn.value or "").strip()
            if not cur:
                continue
            if cur == state.get("last_conn"):
                continue
            state["last_conn"] = cur
            debug_lbl.value = f"UYARILAR: conn seçildi (poll) | {cur}"
            page.update()
            await _load_typenames_for_conn(cur)

    async def _watch_typename_selection():
        while True:
            await asyncio.sleep(0.2)
            cur = (dd_typename.value or "").strip()
            if not cur:
                continue
            if cur == state.get("last_typename"):
                continue
            state["last_typename"] = cur
            debug_lbl.value = f"UYARILAR: typename seçildi (poll) | {cur}"
            page.update()
            await _load_after_typename_selected(cur)

    def on_add_filter_click(e):
        """
        Her tıklamada yeni panel ekle.
        """
        if not (state["conn"] and state["typename"]):
            _notify(
                "Uyarı", "İlave filtre eklemek için önce bağlantı ve typeName seçin."
            )
            return

        idx = len(state["filters"])
        p = _make_filter_panel(idx)
        state["filters"].append(p)
        filters_scroll.controls.append(p["tile"])

        _sync_filters_container_visibility()

        _sync_filters_container_visibility()  # ✅ EKLE
        page.update()

        # sadece yeni panele cache'deki alanları uygula (mevcut filtreleri bozma!)
        _apply_field_opts_to_panel(p, reset_selection=True)

        page.update()
        _update_filtered_button_state()

    # ---------------- download ----------------
    async def pick_dir_and_continue(after_pick_cb):
        export_dir = await ft.FilePicker().get_directory_path(
            dialog_title="Kayıt klasörü seçiniz"
        )
        export_dir = (export_dir or "").strip()
        if not export_dir:
            _notify("Bilgi", "Klasör seçimi iptal edildi.")
            return
        await after_pick_cb(export_dir)

    async def _continue_download(
        export_dir: str, use_filter: bool, cql_filter: str | None = None
    ):
        fmt = _get_selected_vector_format()
        fmt_label = "SHP" if fmt == "shp" else "GML"

        _set_busy(True, f"{fmt_label} indiriliyor...")
        try:
            res = await asyncio.to_thread(
                page.api.wfs_download_vector_bytes,
                state["conn"],
                state["typename"],
                fmt,
                180,
                cql_filter if use_filter else None,
            )
        finally:
            _set_busy(False)

        # debug: çok büyük bytes basma
        blen = len(res.get("bytes") or b"") if isinstance(res, dict) else 0
        debug_lbl.value = (
            f"UYARI: download ok={res.get('ok')} fmt={fmt} "
            f"filename={res.get('filename')} bytes_len={blen} cql={cql_filter!r}"
        )
        page.update()

        if not res.get("ok"):
            msg = res.get("message", f"{fmt_label} indirilemedi.")
            dbg = res.get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            return

        filename = res.get("filename") or (
            "wfs_export.zip" if fmt == "shp" else "wfs_export.gml"
        )
        content = res.get("bytes") or b""
        if not content:
            _notify("Hata", "İndirilen içerik boş.")
            return

        os.makedirs(export_dir, exist_ok=True)

        if fmt == "shp":
            try:
                zip_stream = io.BytesIO(content)
                if not zipfile.is_zipfile(zip_stream):
                    path = os.path.join(export_dir, filename)
                    with open(path, "wb") as f:
                        f.write(content)
                    _notify(
                        "Başarılı",
                        f"SHP içeriği zip formatında dönmedi, ham dosya kaydedildi:\n{path}",
                    )
                    return

                folder_name = os.path.splitext(filename)[0] or "wfs_shp"
                extract_dir = os.path.join(export_dir, folder_name)
                base_extract_dir = extract_dir
                idx = 1
                while os.path.exists(extract_dir):
                    extract_dir = f"{base_extract_dir}_{idx}"
                    idx += 1

                os.makedirs(extract_dir, exist_ok=True)
                zip_stream.seek(0)
                with zipfile.ZipFile(zip_stream) as zf:
                    zf.extractall(extract_dir)

                shp_files = []
                for root_dir, _, files in os.walk(extract_dir):
                    for name in files:
                        if name.lower().endswith(".shp"):
                            shp_files.append(os.path.join(root_dir, name))

                if shp_files:
                    _notify(
                        "Başarılı",
                        "SHP veri seti kaydedildi.\n"
                        f"Klasör: {extract_dir}\n"
                        f"Ana SHP: {shp_files[0]}",
                    )
                else:
                    _notify(
                        "Başarılı",
                        f"ZIP açıldı fakat .shp dosyası bulunamadı.\nKlasör: {extract_dir}",
                    )
                return
            except Exception as ex:
                _notify("Hata", f"SHP ZIP açılırken hata oluştu.\n\n{ex}")
                return

        path = os.path.join(export_dir, filename)
        try:
            with open(path, "wb") as f:
                f.write(content)
        except Exception as ex:
            _notify("Hata", f"Dosya yazılamadı:\n{path}\n\n{ex}")
            return

        _notify("Başarılı", f"GML kaydedildi:\n{path}")

    async def _continue_download_xsd(export_dir: str):
        _set_busy(True, "XSD indiriliyor...")
        try:
            res = await asyncio.to_thread(
                page.api.wfs_download_xsd_bytes,
                state["conn"],
                state["typename"],
                60,
            )
        finally:
            _set_busy(False)

        blen = len(res.get("bytes") or b"") if isinstance(res, dict) else 0
        debug_lbl.value = f"UYARI: xsd ok={res.get('ok')} filename={res.get('filename')} bytes_len={blen}"
        page.update()

        if not res.get("ok"):
            msg = res.get("message", "XSD indirilemedi.")
            dbg = res.get("debug", "")
            _notify("Hata", f"{msg}\n\n{dbg}".strip())
            return

        filename = res.get("filename") or "schema.xsd"
        content = res.get("bytes") or b""
        if not content:
            _notify("Hata", "İndirilen XSD içeriği boş.")
            return

        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, filename)

        try:
            with open(path, "wb") as f:
                f.write(content)
        except Exception as ex:
            _notify("Hata", f"Dosya yazılamadı:\n{path}\n\n{ex}")
            return

        _notify("Başarılı", f"XSD kaydedildi:\n{path}")

    async def on_download_click(e):
        if not (state["conn"] and state["typename"]):
            _notify("Uyarı", "Önce bir WFS bağlantısı ve typeName seçin.")
            return
        await pick_dir_and_continue(
            lambda export_dir: _continue_download(export_dir, use_filter=False)
        )

    async def on_download_xsd_click(e):
        if not (state.get("conn") and state.get("typename")):
            _notify("Uyarı", "Önce bir WFS bağlantısı ve typeName seçin.")
            return

        await pick_dir_and_continue(
            lambda export_dir: _continue_download_xsd(export_dir)
        )

    async def on_download_filtered_click(e):
        if not (state.get("conn") and state.get("typename")):
            _notify("Uyarı", "Önce bir WFS bağlantısı ve typeName seçin.")
            return

        cql_filter = _build_cql_from_all_filters()
        if not cql_filter:
            _notify(
                "Uyarı",
                "Filtreli indirme için en az 1 filtrede alan ve değer seçmelisiniz.",
            )
            return

        await pick_dir_and_continue(
            lambda export_dir: _continue_download(
                export_dir, use_filter=True, cql_filter=cql_filter
            )
        )

    def on_vector_format_change(e: ft.ControlEvent):
        val = _normalize_vector_format(e.control.value)
        state["vector_format"] = val
        debug_lbl.value = f"UYARILAR: indirilecek format -> {val}"
        page.update()

    def _escape_cql_literal(v: str) -> str:
        return (v or "").replace("'", "''")

    def _panel_to_cql(panel: dict) -> str | None:
        field = (panel.get("field") or "").strip()
        values = list(panel.get("selected_values") or [])
        if not field or not values:
            return None

        # tek değer
        if len(values) == 1:
            v = _escape_cql_literal(values[0])
            return f"{field} = '{v}'"

        # çoklu değer
        safe_vals = [f"'{_escape_cql_literal(x)}'" for x in values]
        return f"{field} IN ({', '.join(safe_vals)})"

    def _build_cql_from_all_filters() -> str | None:
        """
        Aynı alan birden fazla panelde seçilmişse değerleri birleştir (OR/IN),
        farklı alanlar arasında AND uygula.
        """
        by_field: dict[str, set[str]] = {}
        field_order: list[str] = []

        for p in state.get("filters", []):
            field = (p.get("field") or "").strip()
            if not field:
                continue
            vals = {
                str(v).strip()
                for v in (p.get("selected_values") or [])
                if str(v).strip()
            }
            if not vals:
                continue
            if field not in by_field:
                by_field[field] = set()
                field_order.append(field)
            by_field[field].update(vals)

        parts: list[str] = []
        for field in field_order:
            vals = sorted(by_field.get(field) or [])
            if not vals:
                continue
            if len(vals) == 1:
                v = _escape_cql_literal(vals[0])
                parts.append(f"({field} = '{v}')")
            else:
                safe_vals = [f"'{_escape_cql_literal(x)}'" for x in vals]
                parts.append(f"({field} IN ({', '.join(safe_vals)}))")

        if not parts:
            return None
        return " AND ".join(parts)

    def _sync_filters_container_visibility():
        filters_container.visible = len(state["filters"]) > 0

    # ---------------- wire ----------------
    btn_add_filter.on_click = on_add_filter_click

    btn_download.on_click = lambda e: page.run_task(on_download_click, e)
    btn_download_schema.on_click = lambda e: page.run_task(on_download_xsd_click, e)
    btn_download_filtered.on_click = lambda e: page.run_task(
        on_download_filtered_click, e
    )
    dd_vector_format.on_change = on_vector_format_change

    # ---------------- layout ----------------
    form = ft.Column(
        width=1100,
        spacing=16,
        controls=[
            dd_conn,
            ft.Row(
                spacing=12,
                controls=[
                    dd_typename,
                    dd_vector_format,
                    btn_download,
                    btn_download_schema,
                    btn_download_filtered,
                    btn_add_filter,
                ],
            ),
            # ✅ Filtre alanı artık scroll'lu container
            filters_container,
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
                # ✅ Sayfanın en altına sabit debug bar
                debug_bar,
            ],
        ),
    )

    page.run_task(refresh_connections)
    return root

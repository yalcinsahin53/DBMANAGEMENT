# create_schema_esri.py
from kivymd.uix.screen import MDScreen
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.button import MDButton, MDButtonText
import openpyxl
import requests, json, hashlib, xml.etree.ElementTree as ET
from threading import Thread

import psycopg2
import os
import math
from kivy.metrics import dp

from kivymd.uix.filemanager import MDFileManager
import tempfile, shutil, re, datetime
import xml.etree.ElementTree as ET
from kivymd.uix.list import MDListItem, MDListItemHeadlineText, MDListItemTrailingCheckbox
from kivymd.uix.list import MDListItemTrailingIcon
from kivy.uix.scrollview import ScrollView
from kivymd.uix.divider import MDDivider
from kivy.factory import Factory

from kivy.uix.widget import Widget
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogSupportingText,
    MDDialogButtonContainer,
)

# GeoPandas opsiyonel — yoksa reprojeksiyon atlanır
try:
    import geopandas as gpd
    HAS_GPD = True
except Exception:
    gpd = None
    HAS_GPD = False

class WFSDownloadScreen(MDScreen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # ... senin mevcut alanların ...
        self.file_manager = None
        self.export_dir = None
        self.conn_menu = None
        self.type_menu = None          # ← typenames menüsü
        self.conn_info_map = {}  # Bağlantı bilgilerini burada saklıyoruz
        self.typenames = []            # ← çekilen typeName listesi
        self.field_menu = None          # ← alan adları menüsü
        self.fieldnames = []            # ← çekilen alan adları
        self.selected_conn = None       # ← seçili bağlantı adı (kolay erişim)
        self.selected_typename = None   # ← seçili typeName
        self.field_value_options = []      # Unique değerler listesi (string’ler)
        self.selected_field_values = set() # Kullanıcı seçimleri
        self.multi_select = True           # Çoklu seçim açık/kapalı kontrolü
        self.values_dialog = None          # Liste diyalogu instance
        self.register_event_type('on_load_values_done')

    def on_load_values_done(self, *args):
        pass

    def on_pre_enter(self):
        self.load_wfsconnection_names()
        
    def load_wfsconnection_names(self):
        path = "documents/app_informations.xlsx"
        self.conn_names = []
        self.conn_info_map = {}

        if os.path.exists(path):
            wb = openpyxl.load_workbook(path)
            if "wfs_connections" in wb.sheetnames:
                ws = wb["wfs_connections"]
                headers = [cell.value for cell in ws[1]]
                

            for row in ws.iter_rows(min_row=2, values_only=True):
                row_data = dict(zip(headers, row))

                # Excel başlıklarını birebir kullan
                conn_name = (row_data.get("Conn_Name") or "").strip()
                urladress = (row_data.get("UrlAdress") or "").strip()
                username  = (row_data.get("UserName") or "").strip()
                password  = (row_data.get("Password") or "").strip()

                # Boş isimli kaydı atla
                if not conn_name:
                    continue

                self.conn_names.append(conn_name)
                # conn_info_map içinde KEY'ler bizim belirlediğimiz (küçük harf) olsun,
                # AMA değerleri Excel'den okuduğumuz değişkenlerden verelim.
                self.conn_info_map[conn_name] = {
                    "conn_name": conn_name,
                    "urladress": urladress,
                    "username": username,
                    "password": password,
                }

        menu_items = [
            {"text": name, "on_release": lambda x=name: self.set_wfsconnection_name(x)}
            for name in self.conn_names
        ]
        self.conn_menu = MDDropdownMenu(
            caller=self.ids.wfsconn_dropdown,
            items=menu_items,
            width_mult=3,
            position="bottom",
        )

    def open_wfsconn_menu(self):
        if hasattr(self, 'conn_menu'):
            self.conn_menu.open()

    def set_wfsconnection_name(self, name):
        self.ids.wfsconn_dropdown.text = name
        self.selected_conn = name
        if getattr(self, "conn_menu", None):
            self.conn_menu.dismiss()

        # typeName ve field seçimini temizle
        self.ids.wfstypenamelist_dropdown.text = ""
        self.typenames = []
        if getattr(self, "type_menu", None):
            self.type_menu.dismiss()
            self.type_menu = None

        self.ids.wfsfieldnamelist_dropdown.text = ""
        self.fieldnames = []
        if getattr(self, "field_menu", None):
            self.field_menu.dismiss()
            self.field_menu = None

        # typeName’leri yükle
        self.fetch_wfs_typenames(name)


    def fetch_wfs_typenames(self, conn_name: str):
        info = self.conn_info_map.get(conn_name, {})
        url = (info.get("urladress") or "").strip()
        username = info.get("username", "")
        password = info.get("password", "")

        if not url:
            self.dialog("Uyarı", "Seçilen bağlantıda 'UrlAdress' bilgisi bulunamadı.\n"
                        "Lütfen Excel'de 'UrlAdress' sütununu ekleyip doldurun.")
            return

        # WFS GetCapabilities isteği
        params = {"service": "WFS", "request": "GetCapabilities"}
        kwargs = {"params": params, "timeout": 15}
        if username and password:
            kwargs["auth"] = (username, password)

        try:
            resp = requests.get(url, **kwargs)
            if resp.status_code != 200:
                self.dialog("Hata", f"GetCapabilities başarısız (HTTP {resp.status_code}).")
                return

            # XML parse — WFS 1.0/1.1/2.0 için olası ad alanları
            ns = {
                "wfs": "http://www.opengis.net/wfs",
                "wfs2": "http://www.opengis.net/wfs/2.0",
                "ows": "http://www.opengis.net/ows",
                "xlink": "http://www.w3.org/1999/xlink",
            }

            root = ET.fromstring(resp.content)

            # 1) WFS 1.0/1.1 tipik yol: FeatureTypeList/FeatureType/Name
            names = [n.text for n in root.findall(".//{http://www.opengis.net/wfs}FeatureType/{http://www.opengis.net/wfs}Name")]
            # 2) WFS 2.0 olasılığı: {wfs2}FeatureTypeList/{wfs2}FeatureType/{wfs2}Name
            if not names:
                names = [n.text for n in root.findall(".//{http://www.opengis.net/wfs/2.0}FeatureType/{http://www.opengis.net/wfs/2.0}Name")]

            # Temizle ve sırala
            self.typenames = sorted([n.strip() for n in names if n and n.strip()])

            if not self.typenames:
                self.dialog("Bilgi", "Bu servisten herhangi bir typeName okunamadı.")
                return

            # Dropdown menüyü hazırla
            menu_items = [
                {"text": t, "on_release": (lambda x=t: self.set_wfstypename(x))}
                for t in self.typenames
            ]

            # Mevcut menü varsa kapat
            if getattr(self, "type_menu", None):
                self.type_menu.dismiss()

            self.type_menu = MDDropdownMenu(
                caller=self.ids.wfstypenamelist_dropdown,
                items=menu_items,
                width_mult=4,
                position="bottom",
            )

            # İsteğe bağlı: otomatik açmak istersen uncomment et
            # self.open_wfstypenamelist_menu()

        except Exception as e:
            self.dialog("Hata", f"Capabilities okunamadı.\nHata: {e}")

    def open_wfstypenamelist_menu(self):
        if getattr(self, "type_menu", None):
            self.type_menu.open()
        else:
            self.dialog("Uyarı", "Önce bir WFS bağlantısı seçin ve typeName’ler yüklensin.")

        self.ids.btn_download_wfs_data.disabled = True
        self.ids.btn_add_fieldquery.disabled = True


    def set_wfstypename(self, typename: str):
        self.ids.wfstypenamelist_dropdown.text = typename
        self.selected_typename = typename

        if getattr(self, "type_menu", None):
            self.type_menu.dismiss()

        # önceki alan adlarını temizle
        self.ids.wfsfieldnamelist_dropdown.text = ""
        self.fieldnames = []
        if getattr(self, "field_menu", None):
            self.field_menu.dismiss()
            self.field_menu = None

        # alan adlarını yükle
        self.fetch_wfs_fieldnames()

        # 🔹 butonu aktif hale getir
        if "btn_download_wfs_data" in self.ids:
            self.ids.btn_download_wfs_data.disabled = False

        # --- YENİ: Kayıt sayısını kontrol et ve gerekiyorsa uyar ---
        self._check_feature_count_and_maybe_prompt()

    def _check_feature_count_and_maybe_prompt(self):
        if not getattr(self, "selected_conn", None) or not getattr(self, "selected_typename", None):
            return

        info = self.conn_info_map.get(self.selected_conn, {})
        url = (info.get("urladress") or "").strip()
        username = info.get("username", "")
        password = info.get("password", "")

        try:
            count = self._wfs_count_features(url, self.selected_typename, username, password)
        except Exception:
            count = None  # sayım başarısızsa sessizce geç

        if isinstance(count, int) and count > 5:
            # iki seçenekli uyarı
            def on_yes(*_):
                # Filtre ekleme butonunu aktif et
                if "btn_add_fieldquery" in self.ids:
                    self.ids.btn_add_fieldquery.disabled = False
                self.dismiss_dialog()

            def on_no(*_):
                # hiç bir şey yapmadan devam
                self.dismiss_dialog()

            self.dialog_instance = MDDialog(
                MDDialogHeadlineText(text="Uyarı"),
                MDDialogSupportingText(text="Toplam Veri Adedi 5000'den fazladır. Filtre eklemek istermisiniz?"),
                MDDialogButtonContainer(
                    Widget(),
                    MDButton(MDButtonText(text="Hayır"), style="text", on_release=on_no),
                    MDButton(MDButtonText(text="Evet"), style="text", on_release=on_yes),
                    spacing="8dp",
                ),
            )
            self.dialog_instance.open()


    def _wfs_count_features(self, base_url: str, typename: str, username: str = "", password: str = "") -> int | None:
        """
        WFS GetFeature resultType=hits ile toplam kayıt sayısını döner.
        Başarısızsa None döner. WFS 2.0.0 ve 1.1.0 varyantlarını dener.
        """
        auth = (username, password) if (username and password) else None
        attempts = [
            # WFS 2.0.0 (typenames)
            {"service": "WFS", "request": "GetFeature", "version": "2.0.0", "typenames": typename, "resultType": "hits"},
            # WFS 1.1.0 (typename)
            {"service": "WFS", "request": "GetFeature", "version": "1.1.0", "typename": typename, "resultType": "hits"},
            # Version belirtilmeden
            {"service": "WFS", "request": "GetFeature", "typename": typename, "resultType": "hits"},
        ]

        for p in attempts:
            try:
                r = requests.get(base_url, params=p, timeout=20, auth=auth)
                if r.status_code != 200 or not r.content:
                    continue

                root = ET.fromstring(r.content)

                # Olası attribute’lar: numberMatched (WFS 2.0), numberOfFeatures / totalFeatures (bazı 1.1.0/GeoServer)
                for attr in ("numberMatched", "numberOfFeatures", "totalFeatures"):
                    val = root.attrib.get(attr)
                    if val and val.isdigit():
                        return int(val)

                # Bazı sunucular 'unknown' döner; bu durumda None
            except Exception:
                continue

        return None


    def fetch_wfs_fieldnames(self):
        if not self.selected_conn:
            self.dialog("Uyarı", "Önce bir WFS bağlantısı seçin.")
            return
        if not self.selected_typename:
            self.dialog("Uyarı", "Önce bir veri seti (typeName) seçin.")
            return

        info = self.conn_info_map.get(self.selected_conn, {})
        url = (info.get("urladress") or "").strip()
        username = info.get("username", "")
        password = info.get("password", "")

        if not url:
            self.dialog("Uyarı", "Seçilen bağlantının URL bilgisi boş.")
            return

        # --- YENİ: Çoklu denemeli DescribeFeatureType ---
        resp, err = self._describe_feature_type(url, self.selected_typename, username, password)
        if not resp:
            self.dialog("Hata", f"DescribeFeatureType başarısız.\n{err or ''}")
            return

        # --- XSD parse (değişmedi) ---
        XSD = "{http://www.w3.org/2001/XMLSchema}"
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            self.dialog("Hata", f"XSD parse edilemedi.\nHata: {e}")
            return

        elements = []
        for seq in root.findall(f".//{XSD}sequence"):
            for el in seq.findall(f"{XSD}element"):
                name = el.get("name")
                if name:
                    elements.append((name, el.get("type", "")))
        if not elements:
            for el in root.findall(f".//{XSD}element"):
                name = el.get("name")
                if name:
                    elements.append((name, el.get("type", "")))

        names = [n for n, t in elements if n]
        uniq, seen = [], set()
        for n in names:
            if n not in seen:
                uniq.append(n); seen.add(n)

        self.fieldnames = uniq
        if not self.fieldnames:
            self.dialog("Bilgi", "DescribeFeatureType içinde alan ismi bulunamadı.")
            return

        menu_items = [{"text": f, "on_release": (lambda x=f: self.set_wfsfieldname(x))} for f in self.fieldnames]
        if getattr(self, "field_menu", None):
            self.field_menu.dismiss()
        self.field_menu = MDDropdownMenu(
            caller=self.ids.wfsfieldnamelist_dropdown,
            items=menu_items,
            width_mult=4,
            position="bottom",
        )

    def open_fieldnamelist_menu(self):
        if getattr(self, "field_menu", None):
            self.field_menu.open()
        else:
            self.dialog("Uyarı", "Önce bir typeName seçin; alan adları yüklensin.")


    def set_wfsfieldname(self, fieldname: str):
        self.ids.wfsfieldnamelist_dropdown.text = fieldname
        if getattr(self, "field_menu", None):
            self.field_menu.dismiss()

        self.ids.btn_listfield_values.disabled = False



    def _describe_feature_type(self, url, typename, username="", password=""):
        """
        WFS DescribeFeatureType için yaygın parametre varyantlarını dener.
        Başarılı ilk 200 yanıtı döndürür; olmazsa (None, son_hata_mesajı) döner.
        """
        auth = (username, password) if (username and password) else None
        attempts = [
            # En sade (birçok sunucu kabul eder)
            {"service": "WFS", "request": "DescribeFeatureType", "typename": typename},
            {"SERVICE": "WFS", "REQUEST": "DescribeFeatureType", "TYPENAME": typename},

            # WFS 1.1.0 ile
            {"service": "WFS", "request": "DescribeFeatureType", "version": "1.1.0", "typename": typename},
            {"SERVICE": "WFS", "REQUEST": "DescribeFeatureType", "VERSION": "1.1.0", "TYPENAME": typename},

            # WFS 1.0.0 da deneyelim
            {"service": "WFS", "request": "DescribeFeatureType", "version": "1.0.0", "typename": typename},
            {"SERVICE": "WFS", "REQUEST": "DescribeFeatureType", "VERSION": "1.0.0", "TYPENAME": typename},

            # WFS 2.0.0'da parametre plural olabilir: typenames / TYPENAMES
            {"service": "WFS", "request": "DescribeFeatureType", "version": "2.0.0", "typenames": typename},
            {"SERVICE": "WFS", "REQUEST": "DescribeFeatureType", "VERSION": "2.0.0", "TYPENAMES": typename},
        ]

        last_err = None
        for p in attempts:
            try:
                resp = requests.get(url, params=p, timeout=20, auth=auth)
                if resp.status_code == 200 and resp.content:
                    return resp, None
                else:
                    last_err = f"HTTP {resp.status_code} - params={p}"
            except Exception as e:
                last_err = f"Exception {e} - params={p}"

        return None, last_err


    def on_add_fieldquery(self):
        self.ids.wfsfieldnamelist_dropdown.disabled = not self.ids.wfsfieldnamelist_dropdown.disabled
        
    # -------------------------------------------
    # DİZİN SEÇİCİ (klasör seçtirme)
    # -------------------------------------------
    def pick_export_folder(self):
        if self.file_manager is None:
            self.file_manager = MDFileManager(
                select_path=self._on_folder_picked,
                exit_manager=self._close_file_manager,
                preview=False,
            )

        # Kökü mevcut çalışma dizini yap
        self.file_manager.show(os.getcwd())

    def _close_file_manager(self, *args):
        if self.file_manager:
            self.file_manager.close()

    def _on_folder_picked(self, path: str):
        # Kullanıcının seçtiği klasör
        self.export_dir = path
        self._close_file_manager()
        # Seçimden sonra indirme işlemini başlat
        self.download_selected_wfs_as_gml()


    # -------------------------------------------
    # İNDİRME ve KAYDETME
    # -------------------------------------------
    def download_selected_wfs_as_gml(self):
        # Seçimler kontrol
        if not getattr(self, "selected_conn", None):
            self.dialog("Uyarı", "Önce bir WFS bağlantısı seçin.")
            return
        if not getattr(self, "selected_typename", None):
            self.dialog("Uyarı", "Önce bir veri seti (typeName) seçin.")
            return
        if not self.export_dir:
            self.dialog("Uyarı", "Lütfen önce kaydedilecek klasörü seçin.")
            return

        info = self.conn_info_map.get(self.selected_conn, {})
        url = (info.get("urladress") or "").strip()
        username = info.get("username", "")
        password = info.get("password", "")

        if not url:
            self.dialog("Hata", "Seçilen bağlantının URL bilgisi boş.")
            return

        try:
            content, used_params = self._getfeature_gml(url, self.selected_typename, username, password)
            # Dosya adı
            safe_typename = re.sub(r"[^A-Za-z0-9_\-\.]+", "_", self.selected_typename)
            ts = datetime.datetime.now().strftime("%Y%m%d")
            fname = f"{safe_typename}_{ts}.gml"
            fpath = os.path.join(self.export_dir, fname)

            with open(fpath, "wb") as f:
                f.write(content)

            self.dialog(
                "Başarılı",
                f"GML dosyası kaydedildi:\n{fpath}\n\n"
                f"Kullanılan parametreler:\n{used_params}"
            )
        except Exception as e:
            self.dialog("Hata", f"GML indirilemedi.\nHata: {e}")




    def on_listfield_values(self):
        """
        'Alan Değerlerini Listele' butonu. Seçili field'ın TÜM değerlerini (tekrarlı) indirir.
        """
        fieldname = (self.ids.wfsfieldnamelist_dropdown.text or "").strip()
        if not fieldname:
            self.dialog("Uyarı", "Önce bir alan (field) seçiniz.")
            return
        if not getattr(self, "selected_conn", None) or not getattr(self, "selected_typename", None):
            self.dialog("Uyarı", "Önce bir WFS bağlantısı ve veri seti (typeName) seçiniz.")
            return

        info = self.conn_info_map.get(self.selected_conn, {})
        url = (info.get("urladress") or "").strip()
        username = info.get("username", "")
        password = info.get("password", "")

        try:
            values = self._wfs_fetch_field_values_all(
                url, self.selected_typename, fieldname, username, password
            )
            # tekrarlı değerleri olduğu gibi listeye basacağız
            self.field_value_options = ["" if v is None else str(v) for v in values]
            self.selected_field_values = set()
            self.populate_field_values(self.field_value_options)   # mevcut liste panelini doldur
        except Exception as e:
            self.dialog("Hata", f"Alan değerleri alınamadı.\nHata: {e}")

        if len(self.field_value_options) > 10000:
            self.dialog("Bilgi", f"{len(self.field_value_options)} değer listelenecek; arayüz yavaşlayabilir.")

            
    def _wfs_fetch_field_values_all(self, base_url: str, typename: str, fieldname: str,
                                    username: str = "", password: str = "") -> list:
        """
        Seçili field'ın TÜM değerlerini döndürür (tekrarlı dahil).
        - Yalnızca ilgili sütunu çekmek için propertyName/PROPERTYNAME kullanır.
        - Önce WFS 2.0.0 (typenames + startIndex/count) sayfalama dener,
        olmazsa WFS 1.1.0 (typename + maxFeatures) ile tek çekim yapar.
        - JSON/GeoJSON döndürmeyi dener. Başarısızsa exception fırlatır.
        - Aşırı büyük veri için güvenlik sınırı koyar (UI kilitlenmesin).
        """
        auth = (username, password) if (username and password) else None
        json_outs = ["application/json", "application/geo+json", "json", "GeoJSON"]

        # Koruma sınırları (gerekirse büyüt)
        PAGE_SIZE = 1000
        MAX_PAGES = 200            # 200 * 1000 = 200k kayıt
        HARD_CAP = PAGE_SIZE * MAX_PAGES

        # 1) WFS 2.0.0 (typenames + startIndex/count)
        for out in json_outs:
            try:
                all_vals = []
                for page in range(MAX_PAGES):
                    params = {
                        "service": "WFS",
                        "request": "GetFeature",
                        "version": "2.0.0",
                        "typenames": typename,
                        "propertyName": fieldname,
                        "count": PAGE_SIZE,
                        "startIndex": page * PAGE_SIZE,
                        "outputFormat": out,
                    }
                    r = requests.get(base_url, params=params, timeout=40, auth=auth)
                    if r.status_code != 200 or not r.content:
                        break
                    data = r.json()
                    feats = data.get("features", [])
                    if not feats:
                        break

                    for f in feats:
                        props = f.get("properties", {})
                        val = props.get(fieldname)
                        # liste/dict gelirse stringify edelim
                        if isinstance(val, (list, dict)):
                            val = json.dumps(val, ensure_ascii=False)
                        all_vals.append(val)

                    if len(all_vals) >= HARD_CAP:
                        break

                if all_vals:
                    # eğer limit sebebiyle kesildiyse kullanıcıya ufak bilgi
                    if len(all_vals) >= HARD_CAP:
                        self.dialog("Bilgi", f"Toplam değer sayısı {HARD_CAP}+ (kırpıldı). Daha dar filtre önerilir.")
                    return all_vals
            except Exception:
                pass  # başka çıktıları/versiyonları dene

        # 2) WFS 1.1.0 (typename + maxFeatures) — genelde tek çekim (bazı sunucularda sayfalama yok)
        for out in json_outs:
            try:
                params = {
                    "service": "WFS",
                    "request": "GetFeature",
                    "version": "1.1.0",
                    "typename": typename,
                    "PROPERTYNAME": fieldname,
                    "maxFeatures": HARD_CAP,
                    "outputFormat": out,
                }
                r = requests.get(base_url, params=params, timeout=60, auth=auth)
                if r.status_code != 200 or not r.content:
                    continue
                data = r.json()
                feats = data.get("features", [])
                all_vals = []
                for f in feats:
                    props = f.get("properties", {})
                    val = props.get(fieldname)
                    if isinstance(val, (list, dict)):
                        val = json.dumps(val, ensure_ascii=False)
                    all_vals.append(val)
                if all_vals:
                    return all_vals
            except Exception:
                pass

        raise Exception("Sunucu JSON/GeoJSON döndürmedi veya değerler okunamadı.")

    def _getfeature_gml(self, base_url: str, typename: str, username: str = "", password: str = ""):
        """
        GML döndürmek için yaygın WFS 2.0.0 ve 1.1.0 kombinasyonlarını dener.
        Başarılı olursa (content_bytes, params_repr) döner; aksi halde Exception atar.
        """
        auth = (username, password) if (username and password) else None

        # Çoğu sunucuda GML3/3.2 çalışır; bazıları GML2 ister.
        output_candidates = [
            "application/gml+xml; version=3.2",
            "text/xml; subtype=gml/3.2",
            "GML3",
            "GML2",
        ]
        attempts = []

        # WFS 2.0.0
        for of in output_candidates:
            attempts.append({
                "service": "WFS", "request": "GetFeature",
                "version": "2.0.0",
                "typenames": typename,       # 2.0.0'da plural
                "outputFormat": of,
                "count": 100000              # makul büyük bir sayı
            })
        # WFS 1.1.0
        for of in output_candidates:
            attempts.append({
                "service": "WFS", "request": "GetFeature",
                "version": "1.1.0",
                "typename": typename,        # 1.1.0'da singular
                "outputFormat": of,
                "maxFeatures": 100000
            })
        # Bazı sunucular version vermeden kabul eder
        for of in output_candidates:
            attempts.append({
                "service": "WFS", "request": "GetFeature",
                "typename": typename,
                "outputFormat": of
            })

        last_status = None
        last_text = None

        for p in attempts:
            try:
                resp = requests.get(base_url, params=p, timeout=60, auth=auth, stream=True)
                last_status = resp.status_code
                if resp.status_code == 200:
                    # İçerik türü GML/XML olmalı
                    # Bazı sunucular zip döndürebilir; burada doğrudan baytları yazıyoruz.
                    content = resp.content
                    # Çok kısa/boş içerik şüpheli olabilir; fakat yine de kaydedeceğiz.
                    used = "&".join(f"{k}={v}" for k, v in p.items())
                    return content, used
                else:
                    # hatayı biraz sakla, denemeye devam
                    last_text = resp.text[:400]
            except Exception as e:
                last_text = str(e)

        raise Exception(f"GetFeature başarısız. Son durum: HTTP {last_status}. Ayrıntı: {last_text}")

    def set_multi_select(self, active: bool):
        self.multi_select = bool(active)
        # tekli moda geçtiyse mevcut seçimleri en fazla 1 öğede tut

    def is_value_selected(self, value: str) -> bool:
        return value in self.selected_field_values

    def on_select_all_field_values(self):
        self.selected_field_values = set([w.value for w in self.ids.field_values_list.children if hasattr(w, "value")])
        for child in self.ids.field_values_list.children:
            if "chk" in child.ids: child.ids.chk.active = True

    def on_clear_all_field_values(self):
        self.selected_field_values.clear()
        for child in self.ids.field_values_list.children:
            if "chk" in child.ids: child.ids.chk.active = False

    def _wfs_fetch_field_values_all(self, base_url: str, typename: str, fieldname: str,
                                    username: str = "", password: str = "") -> list:
        """Önce JSON/GeoJSON dener; olmazsa GML parse ederek TÜM değerleri döndürür."""
        try:
            return self._wfs_fetch_field_values_all_json(base_url, typename, fieldname, username, password)
        except Exception:
            # JSON olmazsa GML’e düş
            return self._wfs_fetch_field_values_all_gml(base_url, typename, fieldname, username, password)

    def _wfs_get_total_hits(self, base_url, typename, auth):
        # WFS 2.0.0 hits
        p = {"service":"WFS","request":"GetFeature","version":"2.0.0",
            "typenames": typename, "resultType":"hits"}
        r = requests.get(base_url, params=p, timeout=25, auth=auth)
        if r.status_code == 200 and r.content:
            try:
                root = ET.fromstring(r.content)
                for attr in ("numberMatched","numberOfFeatures","totalFeatures"):
                    v = root.attrib.get(attr)
                    if v and v.isdigit():
                        return int(v)
            except Exception:
                pass
        return None

    def _wfs_fetch_field_values_all_json(self, base_url, typename, fieldname, username="", password=""):
        auth = (username, password) if (username and password) else None
        outs = ["application/json","application/geo+json","json","GeoJSON"]
        PAGE_SIZE = 1000
        HARD_CAP  = 200_000

        total = self._wfs_get_total_hits(base_url, typename, auth)
        # hits yoksa yine deneyeceğiz ama limitle
        max_to_fetch = min(total if isinstance(total,int) else HARD_CAP, HARD_CAP)

        for out in outs:
            # önce propertyName ile dene; olmazsa (0 feature gelirse) propertyName'siz dene
            for use_prop in (True, False):
                values = []
                last_hash = None
                start = 0
                while start < max_to_fetch:
                    params = {"service":"WFS","request":"GetFeature","version":"2.0.0",
                            "typenames": typename, "count": PAGE_SIZE, "startIndex": start,
                            "outputFormat": out}
                    if use_prop:
                        # ArcGIS bazı katmanlarda propertyName'ı desteklemiyor
                        params["propertyName"] = fieldname

                    r = requests.get(base_url, params=params, timeout=35, auth=auth)
                    if r.status_code != 200 or not r.content:
                        break

                    # Aynı sayfa tekrar mı geldi? (startIndex yok sayılıyor olabilir)
                    cur_hash = hashlib.md5(r.content).hexdigest()
                    if last_hash and cur_hash == last_hash:
                        # startIndex etkisiz → döngüyü kır
                        break
                    last_hash = cur_hash

                    try:
                        data = r.json()
                    except Exception:
                        # JSON değilse bu outputFormat’ı bırak
                        values = []
                        break

                    feats = data.get("features") or []
                    if not feats:
                        # propertyName yüzünden boş geldi → bir sonraki denemeye geç
                        values = []
                        break

                    for f in feats:
                        v = (f.get("properties") or {}).get(fieldname)
                        if isinstance(v,(list,dict)):
                            v = json.dumps(v,ensure_ascii=False)
                        values.append(v)

                    got = len(feats)
                    if got < PAGE_SIZE:
                        # son sayfa
                        break
                    start += PAGE_SIZE

                if values:
                    return values

        raise Exception("Sunucu JSON/GeoJSON döndürmedi veya değerler okunamadı.")

    def _wfs_fetch_field_values_all_gml(self, base_url, typename, fieldname, username="", password=""):
        auth = (username, password) if (username and password) else None

        def local_name(tag):
            if not tag: return ""
            if tag.startswith("{"): return tag.split("}",1)[1]
            if ":" in tag: return tag.split(":",1)[1]
            return tag

        def parse_values(xml_bytes):
            root = ET.fromstring(xml_bytes)
            out=[]
            for el in root.iter():
                if local_name(el.tag)==fieldname:
                    out.append(el.text)
            return out

        PAGE_SIZE=1000
        total = self._wfs_get_total_hits(base_url, typename, auth)
        max_to_fetch = min(total if isinstance(total,int) else 200_000, 200_000)

        last_hash=None
        start=0
        while start < max_to_fetch:
            params={"service":"WFS","request":"GetFeature","version":"2.0.0",
                    "typenames": typename, "count": PAGE_SIZE,"startIndex": start,
                    "outputFormat":"application/gml+xml; version=3.2"}
            r = requests.get(base_url, params=params, timeout=45, auth=auth)
            if r.status_code!=200 or not r.content:
                break
            cur_hash = hashlib.md5(r.content).hexdigest()
            if last_hash and cur_hash==last_hash:
                # startIndex yok sayılıyor → aynı sayfa geliyor
                break
            last_hash = cur_hash

            vals = parse_values(r.content)
            if not vals:
                break
            # topluyoruz (tekrarlarıyla)
            if start==0:
                all_vals = []
            all_vals.extend(vals)

            if len(vals) < PAGE_SIZE:
                break
            start += PAGE_SIZE

        return all_vals if 'all_vals' in locals() and all_vals else []


    def show_field_values_panel(self):
        p = self.ids.field_values_panel
        p.opacity = 1
        p.height = min(dp(480), self.height * 0.6)

    def hide_field_values_panel(self):
        p = self.ids.field_values_panel
        p.opacity = 0
        p.height = 0

    def populate_field_values(self, values):
        # tekrarlı dahil tüm değerler
        data = [{"text": "" if v is None else str(v), "active": False} for v in values]
        self.ids.values_rv.data = data
        self.show_field_values_panel()

    def on_checkbox_toggle(self, value, active):
        if not hasattr(self, "selected_field_values"):
            self.selected_field_values = set()
        if active:
            self.selected_field_values.add(value)
        else:
            self.selected_field_values.discard(value)




    def dialog(self, title, text):
        dialog= MDDialog(

            # -----------------------Headline text-------------------------
            MDDialogHeadlineText(
                text=title,
            ),
            # -----------------------Supporting text-----------------------
            MDDialogSupportingText(
                text= text,
            ),
            # ---------------------Button container------------------------
            MDDialogButtonContainer(
                Widget(),
                MDButton(
                    MDButtonText(text="Kapat"),
                    style="text",
                    on_release=lambda *args: dialog.dismiss(),  # Kapat'a basınca dialog kapanır
                ),
                spacing="8dp",
            ),
            # -------------------------------------------------------------
            # -------------------------------------------------------------
        )
        dialog.open()
        

    def dismiss_dialog(self):
        if self.dialog_instance:
            self.dialog_instance.dismiss()
            self.dialog_instance = None

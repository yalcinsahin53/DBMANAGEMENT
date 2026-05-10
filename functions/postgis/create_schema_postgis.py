# create_schema_esri.py
from kivymd.uix.screen import MDScreen
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.button import MDButton, MDButtonText
import openpyxl
import psycopg2
import os
from kivy.uix.widget import Widget
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogSupportingText,
    MDDialogButtonContainer,
)

class CreateSchemaPostgisScreen(MDScreen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.conn_menu = None
        self.schema_menu = None
        self.conn_info_map = {}  # Bağlantı bilgilerini burada saklıyoruz


    def on_pre_enter(self):
        self.load_connection_names()
        
    def load_connection_names(self):
        path = "documents/app_informations.xlsx"
        self.conn_names = []
        self.conn_info_map = {}

        if os.path.exists(path):
            wb = openpyxl.load_workbook(path)
            if "vt_connections" in wb.sheetnames:
                ws = wb["vt_connections"]
                headers = [cell.value for cell in ws[1]]
                
                for row in ws.iter_rows(min_row=2, values_only=True):
                    row_data = dict(zip(headers, row))
                    conn_name = row_data.get("Conn_Name")
                    db_type = row_data.get("DbType")

                    # Yalnızca DbType "Esri Geodatabase" olanları ekle
                    if conn_name and db_type == "Postgis":
                        self.conn_names.append(conn_name)
                        self.conn_info_map[conn_name] = {
                            "database": row_data.get("Database"),
                            "host": row_data.get("Host"),
                            "port": row_data.get("Port"),
                            "user": row_data.get("UserName"),
                            "password": row_data.get("Password"),
                        }

        menu_items = [
            {"text": name, "on_release": lambda x=name: self.set_connection_name(x)}
            for name in self.conn_names
        ]
        self.conn_menu = MDDropdownMenu(
            caller=self.ids.conn_dropdown,
            items=menu_items,
            width_mult=3,
            position="bottom",
        )

    def open_conn_menu(self):
        if hasattr(self, 'conn_menu'):
            self.conn_menu.open()

    def set_connection_name(self, name):
        self.ids.conn_dropdown.text = name
        self.conn_menu.dismiss()

    def open_schema_menu(self):
        items = [
            {"text": "UIP", "on_release": lambda x="UIP": self.set_schema_option(x)},
            {"text": "NIP", "on_release": lambda x="NIP": self.set_schema_option(x)},
            {"text": "MUIP", "on_release": lambda x="MUIP": self.set_schema_option(x)},
            {"text": "MNIP", "on_release": lambda x="MNIP": self.set_schema_option(x)},
            {"text": "CDP", "on_release": lambda x="CDP": self.set_schema_option(x)},
            {"text": "MCDP25000", "on_release": lambda x="MCDP25000": self.set_schema_option(x)},
            {"text": "MCDP100000", "on_release": lambda x="MCDP100000": self.set_schema_option(x)},
            {"text": "OCBUIP", "on_release": lambda x="OSBUIP": self.set_schema_option(x)},
            {"text": "OCBNIP", "on_release": lambda x="OSBNIP": self.set_schema_option(x)},
            {"text": "Diger", "on_release": lambda x="Diger":self.set_schema_option(x)}
            
        ]
        self.schema_menu = MDDropdownMenu(
            caller=self.ids.schema_dropdown,
            items=items,
            width_mult=3,
            position="bottom",
        )
        self.schema_menu.open()

    def set_schema_option(self, value):
        # Şema ismini inputa yaz (seçilen metni göster)
        self.ids.schema_dropdown.text = value

        # Eğer 'Diğer' seçilmişse özel giriş alanı aktif olsun
        self.ids.custom_schema_name.disabled = (value != "Diger")

        # Şema seçimi yapıldıktan sonra buton aktif hale gelsin
        self.ids.create_schema_btn.disabled = False

        if self.schema_menu:
            self.schema_menu.dismiss()

    def createschemapostgis(self):
        conn_name = self.ids.conn_dropdown.text
        if not conn_name:
            self.dialog("Hata", "Lütfen bağlantı seçin.")
            return

        conn_info = self.conn_info_map.get(conn_name)
        if not conn_info:
            self.dialog("Hata", "Seçilen bağlantının bilgileri bulunamadı.")
            return

        selected_schema = self.ids.schema_dropdown.text
        if selected_schema == "Diger":
            schema_name = self.ids.custom_schema_name.text.strip()
            if not schema_name:
                self.dialog("Hata", "Lütfen özel şema adını girin.")
                return
        else:
            schema_name = selected_schema

        try:
            conn = psycopg2.connect(
                host=conn_info["host"],
                port=conn_info["port"],
                user=conn_info["user"],
                password=conn_info["password"],
                database=conn_info["database"]
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS \"{schema_name}\"")
            conn.commit()
            cursor.close()
            conn.close()
            self.dialog("Başarılı", f"'{schema_name}' adında şema oluşturuldu.")
        except Exception as e:
            self.dialog("Hata", f"Şema oluşturulamadı: {str(e)}")

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
        
    def dismiss_dialog(self, instance):
        if self.dialog_instance:
            self.dialog_instance.dismiss()
            self.dialog_instance = None

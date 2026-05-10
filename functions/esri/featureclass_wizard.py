# featureclass_wizard.py

from kivymd.uix.screen import MDScreen
from kivy.properties import ListProperty, StringProperty, NumericProperty
from kivy.uix.screenmanager import SlideTransition
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.textfield import MDTextField
from kivymd.uix.recycleview import MDRecycleView
from kivy.factory import Factory
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.metrics import dp
from kivymd.uix.label import MDLabel
from kivymd.uix.anchorlayout import MDAnchorLayout


class FeatureclassWizardScreen(MDScreen):
    step = NumericProperty(1)

    # 1) Seçilen bağlantı & şema
    sel_connection = StringProperty("")
    sel_schema     = StringProperty("")

    # 2) Feature Class özellikleri
    fc_name    = StringProperty("")
    fc_alias   = StringProperty("")
    geom_types = ListProperty([
        "POINT", "LINESTRING", "POLYGON",
        "MULTIPOLYGON", "MULTILINESTRING"
    ])
    sel_geom = StringProperty("POINT")

    coord_systems = ListProperty([
        "EPSG:4326", "EPSG:3857", "EPSG:32633"
    ])
    sel_crs = StringProperty("EPSG:4326")  # default CRS

    # 3) Alanlar
    fields = ListProperty([])  # her alan: {'name','alias','type','length'}

    # Dialog referansı
    dlg = None
    field_dialog = None          # <<< burada ekleyin


    def next_step(self):
        if self.step < 2:
            self.step += 1
            self.ids.sm.transition = SlideTransition(direction="left")
            self.ids.sm.current = f"page{self.step}"

    def prev_step(self):
        if self.step > 1:
            self.step -= 1
            self.ids.sm.transition = SlideTransition(direction="right")
            self.ids.sm.current = f"page{self.step}"



    def open_field_dialog(self, title):
        # Sadece bir kez oluştur
        content = MDBoxLayout(
            orientation="vertical",
            spacing=dp(16),
            padding=dp(24),
            adaptive_height=True,
            size_hint_x=1.0,            # <-- tam genişlik alması için
            pos_hint={"center_x": 0.5},
        )
        content.add_widget(
            MDLabel(
                text=title,
                halign="center",
                size_hint_y=None,
                height=dp(30),
            )
        )
        
        fieldlabel_name= MDLabel(
            text="Alan Adı Girin",
            size_hint_x=0.9, pos_hint={"center_x": 0.5}
            )
        content.add_widget(fieldlabel_name)

        field_name= MDTextField(
            id="field_name",              # ← bu id'yi kullanarak içeriğe erişeceğiz
            size_hint_x=0.9, pos_hint={"center_x": 0.5},
        )
        content.add_widget(field_name)
        content.add_widget(Widget(size_hint_y=None, height=dp(5)))

        fieldlabel_alias= MDLabel(
            text="Alan Etiketi  Girin",
            size_hint_x=0.9, pos_hint={"center_x": 0.5}
            )
        content.add_widget(fieldlabel_alias)

        field_alias= MDTextField(
            id="field_alias",             # ← bu id'yi kullanarak içeriğe erişeceğiz
            size_hint_x=0.9, pos_hint={"center_x": 0.5}
            
        )
        content.add_widget(field_alias)
        content.add_widget(Widget(size_hint_y=None, height=dp(5)))

        
        fieldlabel_alias= MDLabel(
            text="Alan Tipi  Girin",
            size_hint_x=0.9, pos_hint={"center_x": 0.5}
            )
        content.add_widget(fieldlabel_alias)

        field_type = MDTextField(
            id="field_type",              # ← bu id'yi kullanarak içeriğe erişeceğiz
            size_hint_x=0.9, pos_hint={"center_x": 0.5}
        )
        content.add_widget(field_type)
        content.add_widget(Widget(size_hint_y=None, height=dp(5)))

        fieldlabel_lenght= MDLabel(
            text="Alan Uzunluğu  Girin",
            size_hint_x=0.9, pos_hint={"center_x": 0.5}
            )
        content.add_widget(fieldlabel_lenght)

        field_length = MDTextField(
            id="field_length",            # ← bu id'yi kullanarak içeriğe erişeceğiz
            size_hint_x=0.9, pos_hint={"center_x": 0.5},
            input_filter="int"
        )
        content.add_widget(field_length)

        if not self.field_dialog:
           
            
            dlg = MDDialog(
            content,
            # -----------------------Headline text-------------------------
            MDDialogHeadlineText(
                text=title,
            ),

            # ---------------------Button container------------------------
            MDDialogButtonContainer(
                
                MDButton(
                    MDButtonText(text="İptal",height="128dp", width="128dp"),
                    style="text",
                    height= "64dp",
                    width= "64dp",
                    on_release=lambda *a: dlg.dismiss(),  # Kapat'a basınca dialog kapanır
                ),
                MDButton(
                    MDButtonText(text="Ekle"),
                    style="text",
                    height= "64dp",
                    width= "64dp",
                    on_release=lambda *a: self.add_field_from_dialog(content, dlg),  # Ekle'ye basınca alan eklenir
                ), 
            ),

            # -----------------------Headline text-------------------------

            adaptive_height=True,     # <- **bu** satıra dikkat!
            auto_dismiss=False,
            size_hint=(0.9, None),
            pos_hint={"center_x": 0.5, "center_y": 0.5},


            # -------------------------------------------------------------
            )

            self.field_dialog = dlg

        self.field_dialog.open()

    def dismiss_dialog(self, instance):
        if self.dialog_instance:
            self.dialog_instance.dismiss()
            self.dialog_instance = None




    def add_field_from_dialog(self, content, dlg):
        # Popup içindeki TextField'lerden verileri oku
        name  = content.ids.field_name.text.strip()
        alias = content.ids.field_alias.text.strip()
        ftype = content.ids.field_type.text.strip()
        length= content.ids.field_length.text.strip()

        if name and ftype:
            self.fields.append({
                "name": name, "alias": alias, "type": ftype, "length": length
            })
            # RecycleView güncellemesi (rv id'si sizin KV'de neyse ona göre)
            self.ids.rv.data = [
                {"text": f"{f['name']} ({f['type']})"} for f in self.fields
            ]

        # Alanları temizleyip popup'u kapat
        for wid in (content.ids.field_name,
                    content.ids.field_alias,
                    content.ids.field_type,
                    content.ids.field_length):
            wid.text = ""
        dlg.dismiss()

    def on_submit_popup(self, name, age):
        # Burada gönderme, validation, veritabanı kaydı vs. yapabilirsiniz
        print(f"Gönderilen: {name}, {age}")
        self.dialog.dismiss()

    def finish_and_create(self):
        # ESRI st_geometry çağrılarınızı burada yapın...

        # Boş bir MDDialog örneği
        dialog = MDDialog(
            size_hint=(0.8, None),
            auto_dismiss=False,
        )
        # Başlık
        dialog.add_widget(
            MDDialogHeadlineText(text="Tamamlandı", halign="center")
        )
        # Açıklayıcı metin
        dialog.add_widget(
            MDDialogSupportingText(
                text="Feature Class başarıyla oluşturuldu.", 
                halign="center"
            )
        )
        # Butonlar
        buttons = MDDialogButtonContainer(spacing="8dp")
        buttons.add_widget(
            MDButton(text="Kapat", on_release=lambda inst: dialog.dismiss())
        )
        dialog.add_widget(buttons)

        dialog.open()

    def _close_dialog(self, *args):
        """Dialog'u kapat ve ana menüye dön."""
        if self.dialog:
            self.dialog.dismiss()
            self.manager.current = "featureclassmenu"
            self.dialog = None

<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:gml="http://www.opengis.net/gml" xmlns:plan="www.csb.gov.tr" elementFormDefault="qualified" targetNamespace="www.csb.gov.tr" version="1.0" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:import schemaLocation="http://schemas.opengis.net/gml/2.1.2/feature.xsd" namespace="http://www.opengis.net/gml" />
	<xs:element name="CsbFeatureType" type="plan:CsbFeatureType"/>
	<xs:complexType name="CsbFeatureType">
		<xs:complexContent>
			<xs:extension base="gml:AbstractFeatureType">
				<xs:sequence>
					<xs:element name="symbolizer" type="xs:string" minOccurs="0" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="AbstractYapilasma" type="plan:AbstractYapilasma"/>
	<xs:complexType name="AbstractYapilasma" abstract="true">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="OnBahceMesafesi" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YanBahceMesafesi" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YapiDuzeni" type="plan:YapiDuzenTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="Konut" type="plan:Konut"/>
	<xs:complexType name="Konut">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KonutTip" type="plan:KonutTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="TurizmAlani" type="plan:TurizmAlani"/>
	<xs:complexType name="TurizmAlani">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TurizmTip" type="plan:TurizmTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="EgitimTesisAlani" type="plan:EgitimTesisAlani"/>
	<xs:complexType name="EgitimTesisAlani">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
				<xs:element name="EgitimTesisTip" type="plan:EgitimTesisTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>					
					<xs:element name="MulkiyetTip" type="plan:MulkiyetTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="SaglikTesisAlani" type="plan:SaglikTesisAlani"/>
	<xs:complexType name="SaglikTesisAlani">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="SaglikTip" type="plan:SaglikTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="TurizmTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="PansiyonAlani"/>
			<xs:enumeration value="ApartOtelAlani"/>
			<xs:enumeration value="OtelAlani"/>
			<xs:enumeration value="MotelAlani"/>
			<xs:enumeration value="HostelAlani"/>
			<xs:enumeration value="TatilKoyuAlani"/>
			<xs:enumeration value="SaglikOdakliTatilKoyu"/>
			<xs:enumeration value="TermalTurizmAlani"/>
			<xs:enumeration value="KampingAlani"/>
			<xs:enumeration value="GunubirlikTesisAlani"/>
			<xs:enumeration value="GolfAlani"/>
			<xs:enumeration value="KisSporlariKayakTesisAlani"/>
			<xs:enumeration value="EkoTurizmKirsalTurizmTesisAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="TmKtkgbAlan" type="plan:TmKtkgbAlan"/>
	<xs:complexType name="TmKtkgbAlan">
		<xs:annotation>
			<xs:documentation>Turizm Merkezi Kültür ve Turizm Koruma ve Gelişim Altbölgesi</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="PlanDegisiklikSiniri" type="plan:PlanDegisiklikSiniri"/>
	<xs:complexType name="PlanDegisiklikSiniri">
		<xs:annotation>
			<xs:documentation>Plan Değişikliği Onama Sınırı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:AbstractPlanOnama">
				<xs:sequence>
					<xs:element name="DegismeSebepTip" type="plan:DegismeSebepTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="PlanSiniri" type="plan:PlanSiniri"/>
	<xs:complexType name="PlanSiniri">
		<xs:annotation>
			<xs:documentation>Plan Onama Sınırı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:AbstractPlanOnama">
				<xs:sequence>
					<xs:element name="Nitelik" type="plan:NitelikTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="KiyiKenarCizgisi" type="plan:KiyiKenarCizgisi"/>
	<xs:complexType name="KiyiKenarCizgisi">
		<xs:annotation>
			<xs:documentation>Kıyı Kenar Çizgisi</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="OnamaTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="Yolorta" type="plan:Yolorta"/>
	<xs:complexType name="Yolorta">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YolGenisligi" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YolTip" type="plan:YolTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="Demiryolu" type="plan:Demiryolu"/>
	<xs:complexType name="Demiryolu">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="DemirTip" type="plan:DemirTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GuzergahAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="YayaYolu" type="plan:YayaYolu"/>
	<xs:complexType name="YayaYolu">
		<xs:annotation>
			<xs:documentation>Yaya Yolu ve Bölgesi</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Genislik" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="SuKaptaj" type="plan:SuKaptaj"/>
	<xs:complexType name="SuKaptaj">
		<xs:annotation>
			<xs:documentation>Su Kaynakları Toplama Yeri (Kaptaj Alanı)</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="EnerjiDagitimDepolama" type="plan:EnerjiDagitimDepolama"/>
	<xs:complexType name="EnerjiDagitimDepolama">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="EnerjiTesisTip" type="plan:EnerjiTesisTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="DigerYolNesneTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Refuj"/>
			<xs:enumeration value="Kaldirim"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="IbadetAlani" type="plan:IbadetAlani"/>
	<xs:complexType name="IbadetAlani">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IbadetTip" type="plan:IbadetTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="SosyalKulturelAlan" type="plan:SosyalKulturelAlan"/>
	<xs:complexType name="SosyalKulturelAlan">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="MulkiyetTip" type="plan:MulkiyetTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="SosyalKulturelTip" type="plan:SosyalKulturelTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="AbstractKatliYapi" type="plan:AbstractKatliYapi"/>
	<xs:complexType name="AbstractKatliYapi" abstract="true">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="EmsalKaks" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="EmsalKaksTip" type="plan:DegerTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KatAdedi" type="xs:int" minOccurs="1" maxOccurs="1"/>
					<xs:element name="MudahaleYontemi" type="xs:string" minOccurs="0" maxOccurs="1"/>
					<xs:element name="Taks" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TaksTip" type="plan:DegerTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YapiYuksekligi" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YapiYuksekligiTip" type="plan:DegerTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="SembolPoz" type="xs:string" minOccurs="0" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="YapiYaklasC" type="plan:YapiYaklasC"/>
	<xs:complexType name="YapiYaklasC">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Mesafe" type="xs:double" minOccurs="0" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="AcikYesilAlan" type="plan:AcikYesilAlan"/>
	<xs:complexType name="AcikYesilAlan">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="AcikYesilTip" type="plan:AcikYesilTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="DogalKarakter" type="plan:DogalKarakter"/>
	<xs:complexType name="DogalKarakter">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="DogalKarakterTip" type="plan:DogalKarakterTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="Tip" type="xs:string" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="JeotermalKaynak" type="plan:JeotermalKaynak"/>
	<xs:complexType name="JeotermalKaynak">
		<xs:annotation>
			<xs:documentation>Jeotermal Kaynak </xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:PointPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="IcmeKullanmaSuyuKoruma" type="plan:IcmeKullanmaSuyuKoruma"/>
	<xs:complexType name="IcmeKullanmaSuyuKoruma">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="HavzaAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KorumaDerecesi" type="plan:KorumaDerecesi" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="KorumaDerecesi">
		<xs:restriction base="xs:string">
			<xs:enumeration value="MutlakKorumaAlani"/>
			<xs:enumeration value="KisaMesafeliKorumaAlani"/>
			<xs:enumeration value="OrtaMesafeliKorumaAani"/>
			<xs:enumeration value="UzunMesafeliKorumaAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="AbstractIdariSinir" type="plan:AbstractIdariSinir"/>
	<xs:complexType name="AbstractIdariSinir" abstract="true">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlKod" type="xs:int" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="UlkeSiniri" type="plan:UlkeSiniri"/>
	<xs:complexType name="UlkeSiniri">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="UlkeKod" type="xs:int" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="IlSiniri" type="plan:IlSiniri"/>
	<xs:complexType name="IlSiniri">
		<xs:complexContent>
			<xs:extension base="plan:AbstractIdariSinir">
				<xs:sequence>
					<xs:element name="NutKodD1" type="xs:int" minOccurs="1" maxOccurs="1"/>
					<xs:element name="NutKodD2" type="xs:int" minOccurs="1" maxOccurs="1"/>
					<xs:element name="NutKodD3" type="xs:int" minOccurs="1" maxOccurs="1"/>
					<xs:element name="UlkeKod" type="xs:int" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="IlceSiniri" type="plan:IlceSiniri"/>
	<xs:complexType name="IlceSiniri">
		<xs:complexContent>
			<xs:extension base="plan:AbstractIdariSinir">
				<xs:sequence>
					<xs:element name="IlceKod" type="xs:int" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="BelediyeSiniri" type="plan:BelediyeSiniri"/>
	<xs:complexType name="BelediyeSiniri">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlceKod" type="xs:int" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlKod" type="xs:int" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="SulakAlan" type="plan:SulakAlan"/>
	<xs:complexType name="SulakAlan">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
					<xs:element name="SulakTip" type="plan:SulakTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="SulakTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="SulakAlanBolgesi"/>
			<xs:enumeration value="SulakAlanTamponBolgesi"/>
			<xs:enumeration value="SulakAlanEkolojikEtkilenmeBolgesi"/>
			<xs:enumeration value="SulakAlanMutlakKorumaBolgesi"/>
			<xs:enumeration value="SulakAlanOzelHukumBolgesi"/>
			<xs:enumeration value="SulakAlanSiniri"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="IcmesuAnaHat" type="plan:IcmesuAnaHat"/>
	<xs:complexType name="IcmesuAnaHat">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="SogutmaSuyuAlmaHatti" type="plan:SogutmaSuyuAlmaHatti"/>
	<xs:complexType name="SogutmaSuyuAlmaHatti">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="MucavirAlanSiniri" type="plan:MucavirAlanSiniri"/>
	<xs:complexType name="MucavirAlanSiniri">
		<xs:complexContent>
			<xs:extension base="plan:BelediyeSiniri">
				<xs:sequence/>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="KoySiniri" type="plan:KoySiniri"/>
	<xs:complexType name="KoySiniri">
		<xs:complexContent>
			<xs:extension base="plan:AbstractIdariSinir">
				<xs:sequence/>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="MahalleSiniri" type="plan:MahalleSiniri"/>
	<xs:complexType name="MahalleSiniri">
		<xs:complexContent>
			<xs:extension base="plan:AbstractIdariSinir">
				<xs:sequence/>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="BuyuksehirSiniri" type="plan:BuyuksehirSiniri"/>
	<xs:complexType name="BuyuksehirSiniri">
		<xs:complexContent>
			<xs:extension base="plan:AbstractIdariSinir">
				<xs:sequence/>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="AbstractPlanOnama" type="plan:AbstractPlanOnama"/>
	<xs:complexType name="AbstractPlanOnama" abstract="true">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="Pin" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="PlanAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="EtaplamaSiniri" type="plan:EtaplamaSiniri"/>
	<xs:complexType name="EtaplamaSiniri">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="EtapAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="ImarHakkiAktarimSiniri" type="plan:ImarHakkiAktarimSiniri"/>
	<xs:complexType name="ImarHakkiAktarimSiniri">
		<xs:annotation>
			<xs:documentation>İmar Hakkı Aktarım Alanı Sınırı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="KentselTasarimProjeSiniri" type="plan:KentselTasarimProjeSiniri"/>
	<xs:complexType name="KentselTasarimProjeSiniri">
		<xs:annotation>
			<xs:documentation>Kentsel Tasarım Projesi Sınırı </xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="KopruGecit" type="plan:KopruGecit"/>
	<xs:complexType name="KopruGecit">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GecitTip" type="plan:GecitTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="Genislik" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="TopluTasimaHatti" type="plan:TopluTasimaHatti"/>
	<xs:complexType name="TopluTasimaHatti">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TopluHatTip" type="plan:TopluHatTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="DenizUlasimBaglanti" type="plan:DenizUlasimBaglanti"/>
	<xs:complexType name="DenizUlasimBaglanti">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GuzergahAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="TopluHatTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="RayliTopluTasimaYerUstu"/>
			<xs:enumeration value="HavaiHat"/>
			<xs:enumeration value="RayliTopluTasimaYerAlti"/>
			<xs:enumeration value="Havaray"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="KarayoluTesisleri" type="plan:KarayoluTesisleri"/>
	<xs:complexType name="KarayoluTesisleri">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KaraTesisTip" type="plan:KaraTesisTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="GecitTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Kopru"/>
			<xs:enumeration value="YayaUstGecit"/>
			<xs:enumeration value="YayaAltGecit"/>
			<xs:enumeration value="Tunel"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="OckBolge" type="plan:OckBolge"/>
	<xs:complexType name="OckBolge">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="AdaKenari" type="plan:AdaKenari"/>
	<xs:complexType name="AdaKenari">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="AdaKenariCizgiTip" type="plan:AdaKenariCizgiTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="CizgiKalinligi" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="OzelEkosistem" type="plan:OzelEkosistem"/>
	<xs:complexType name="OzelEkosistem">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="EkosistemTip" type="plan:EkosistemTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TurAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="EkosistemTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="FloraFauna"/>
			<xs:enumeration value="EkolojikKoruma"/>
			<xs:enumeration value="EndemikBiyotop"/>
			<xs:enumeration value="AkdenizFoku"/>
			<xs:enumeration value="DenizKaplumbagasi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="KiyiYapilari" type="plan:KiyiYapilari"/>
	<xs:complexType name="KiyiYapilari">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KiyiYapiTip" type="plan:KiyiYapiTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="OckHassasAlan" type="plan:OckHassasAlan"/>
	<xs:complexType name="OckHassasAlan">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="HassaslikDerecesi" type="plan:HassaslikDerecesi" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="MilliPark" type="plan:MilliPark"/>
	<xs:complexType name="MilliPark">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
					<xs:element name="MilliParkTip" type="plan:MilliParkTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="MilliParkTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="TabiatParkiAlani"/>
			<xs:enumeration value="TabiatiKorumaAlani"/>
			<xs:enumeration value="MilliPark"/>
			<xs:enumeration value="YabanHayatiKorumaGelistirmeAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="YoreselMimariKoruma" type="plan:YoreselMimariKoruma"/>
	<xs:complexType name="YoreselMimariKoruma">
		<xs:annotation>
			<xs:documentation>Yöresel Mimari Özellikleri Korunacak Alan</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
  <xs:element name="YapayAda" type="plan:YapayAda"/>
  <xs:complexType name="YapayAda">
	  <xs:annotation>
		  <xs:documentation>Yapay Ada</xs:documentation>
	  </xs:annotation>
	  <xs:complexContent>
		  <xs:extension base="plan:CsbFeatureType">
			  <xs:sequence>
				  <xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
				  <xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
			  </xs:sequence>
		  </xs:extension>
	  </xs:complexContent>
  </xs:complexType>
	<xs:simpleType name="IcmesuTur">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Depolama"/>
			<xs:enumeration value="Aritma"/>
			<xs:enumeration value="TerfiMerkezi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="IcmesuTesis" type="plan:IcmesuTesis"/>
	<xs:complexType name="IcmesuTesis">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IcmesuTur" type="plan:IcmesuTur" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="DogalKarakterTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Agaclik"/>
			<xs:enumeration value="KayalikTaslik"/>
			<xs:enumeration value="Calilik"/>
			<xs:enumeration value="Kumul"/>
			<xs:enumeration value="MakilikFundalik"/>
			<xs:enumeration value="SazlikBataklik"/>
			<xs:enumeration value="Diger"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="PlanNotu" type="plan:PlanNotu"/>
	<xs:complexType name="PlanNotu">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Aciklama" type="xs:string" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="Orman" type="plan:Orman"/>
	<xs:complexType name="Orman">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="ManiaPlani" type="plan:ManiaPlani"/>
	<xs:complexType name="ManiaPlani">
		<xs:annotation>
			<xs:documentation>Mania Planı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiLineStringPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="Yukseklik" type="xs:double" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="FonksiyonluCalisma" type="plan:FonksiyonluCalisma"/>
	<xs:complexType name="FonksiyonluCalisma">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="FonksiyonAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="FonksiyonluCalismaTip" type="plan:FonksiyonluCalismaTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="SulamaHatti" type="plan:SulamaHatti"/>
	<xs:complexType name="SulamaHatti">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="TunelEtkiAlani" type="plan:TunelEtkiAlani"/>
	<xs:complexType name="TunelEtkiAlani">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="FonksiyonluCalismaTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="TopluIsyeri"/>
			<xs:enumeration value="BelediyeHizmetAlani"/>
			<xs:enumeration value="ResmiKurumAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="NitelikTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Plan"/>
			<xs:enumeration value="Revizyon"/>
			<xs:enumeration value="Ilave"/>
			<xs:enumeration value="IlaveRevizyon"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="DegismeSebepTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Resen"/>
			<xs:enumeration value="Talep"/>
			<xs:enumeration value="Mahkeme"/>
			<xs:enumeration value="Itiraz"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="AskeriYasakBolge" type="plan:AskeriYasakBolge"/>
	<xs:complexType name="AskeriYasakBolge">
		<xs:annotation>
			<xs:documentation>Askeri Yasak ve Güvenlik Bölgesi</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="BogaziciSinirlari" type="plan:BogaziciSinirlari"/>
	<xs:complexType name="BogaziciSinirlari">
		<xs:annotation>
			<xs:documentation>Boğaziçi Etkilenme Bölgesi Sınırı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="BogaziciBolgeTip" type="plan:BogaziciBolgeTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="BogaziciBolgeTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="BogaziciEtkilenmeBolgeSiniri"/>
			<xs:enumeration value="BogaziciGeriGorunumBolgeSiniri"/>
			<xs:enumeration value="BogaziciOnGorunumBolgeSiniri"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="SahilSeridi" type="plan:SahilSeridi"/>
	<xs:complexType name="SahilSeridi">
		<xs:annotation>
			<xs:documentation>Sahil Şeridi</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="DigerOzelSinir" type="plan:DigerOzelSinir"/>
	<xs:complexType name="DigerOzelSinir">
		<xs:annotation>
			<xs:documentation>Diğer Özel Kanunlarla Belirlenen Alan ve Sınırları</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="DonusumKonutAlanlari" type="plan:DonusumKonutAlanlari"/>
	<xs:complexType name="DonusumKonutAlanlari">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="DonusumTip" type="plan:DonusumTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="DonusumTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="TopluKonutAlanlari"/>
			<xs:enumeration value="GecekonduOnlemeBolgesi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="DegerTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Serbest"/>
			<xs:enumeration value="GecerliDegil"/>
			<xs:enumeration value="Deger"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="AdaKenariCizgiTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Onerilen"/>
			<xs:enumeration value="Korunan"/>
			<xs:enumeration value="Duzeltilen"/>
			<xs:enumeration value="IfrazHatti"/>
			<xs:enumeration value="KademeHatti"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="DigerYolNesneleri" type="plan:DigerYolNesneleri"/>
	<xs:complexType name="DigerYolNesneleri">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="DigerYolNesneTip" type="plan:DigerYolNesneTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="YolTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Otoyol"/>
			<xs:enumeration value="BolunmusTasit"/>
			<xs:enumeration value="TasitYol"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="BisikletYolu" type="plan:BisikletYolu"/>
	<xs:complexType name="BisikletYolu">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Genislik" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="DemirTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Demiryolu"/>
			<xs:enumeration value="HizliTrenHat"/>
			<xs:enumeration value="TriyajAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="HavayoluTesisleri" type="plan:HavayoluTesisleri"/>
	<xs:complexType name="HavayoluTesisleri">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="HavaTip" type="plan:HavaTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="KaraTesisTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="GenelOtopark"/>
			<xs:enumeration value="TirKamyonMakinaParkGarajAlani"/>
			<xs:enumeration value="BisikletParki"/>
			<xs:enumeration value="KatliOtoparkAlani"/>
			<xs:enumeration value="ElektrikliAracSarjIstasyonAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="HavaTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="HavalimaniHavaalani"/>
			<xs:enumeration value="HelikopterInisAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="TopluTasimTurleriArasiDegisimAktarmaAlani" type="plan:TopluTasimTurleriArasiDegisimAktarmaAlani"/>
	<xs:complexType name="TopluTasimTurleriArasiDegisimAktarmaAlani">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="Durak" type="plan:Durak"/>
	<xs:complexType name="Durak">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="DurakTip" type="plan:DurakTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:PolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="DurakTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="AnaIstasyonGar"/>
			<xs:enumeration value="AraIstasyon"/>
			<xs:enumeration value="TerminalOtogar"/>
			<xs:enumeration value="RayliTopluTasimaIstasyonu"/>
			<xs:enumeration value="HavaiHatIstasyonu"/>
			<xs:enumeration value="HavarayIstasyonu"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="KiyiYapiTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="TersaneAlani"/>
			<xs:enumeration value="KonteynerLimani"/>
			<xs:enumeration value="KruvaziyerLimani"/>
			<xs:enumeration value="RoRoLimani"/>
			<xs:enumeration value="YatLimani"/>
			<xs:enumeration value="BalikciBarinagi"/>
			<xs:enumeration value="TekneImalCekekYeri"/>
			<xs:enumeration value="GemiSokumYeri"/>
			<xs:enumeration value="Iskele"/>
			<xs:enumeration value="Rihtim"/>
			<xs:enumeration value="Barinak"/>
			<xs:enumeration value="DolfenPlatform"/>
			<xs:enumeration value="TekneImalBakimYeri"/>
			<xs:enumeration value="DenizInisRampasi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="KiyiKorumaYapilari" type="plan:KiyiKorumaYapilari"/>
	<xs:complexType name="KiyiKorumaYapilari">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KiyiKorumaTip" type="plan:KiyiKorumaTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="KiyiKorumaTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Dalgakiran"/>
			<xs:enumeration value="Kopru"/>
			<xs:enumeration value="Menfez"/>
			<xs:enumeration value="IstinatDuvari"/>
			<xs:enumeration value="Mendirek"/>
			<xs:enumeration value="Mahmuz"/>
			<xs:enumeration value="KiyiKoruma"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="YapiDuzenTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Ayrik"/>
			<xs:enumeration value="Bitisik"/>
			<xs:enumeration value="Blok"/>
			<xs:enumeration value="Serbest"/>
			<xs:enumeration value="Ikiz"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="KonutTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="YerlesikKonut"/>
			<xs:enumeration value="GelismeKonut"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="YapiYaklasmaSiniri" type="plan:YapiYaklasmaSiniri"/>
	<xs:complexType name="YapiYaklasmaSiniri">
		<xs:annotation>
			<xs:documentation>Yapı Yaklaşma Sınırı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="KentselCalisma" type="plan:KentselCalisma"/>
	<xs:complexType name="KentselCalisma">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="CalismaTip" type="plan:CalismaTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="CalismaTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="TicaretAlani"/>
			<xs:enumeration value="TicaretKonutAlani"/>
			<xs:enumeration value="TicaretTurizmAlani"/>
			<xs:enumeration value="ToptanTicaretAlani"/>
			<xs:enumeration value="IdariHizmetAlani"/>
			<xs:enumeration value="AkaryakitServisIstasyonu"/>
			<xs:enumeration value="SanayiAlani"/>
			<xs:enumeration value="EndustriyelGelismeBolgesi"/>
			<xs:enumeration value="KucukSanayiAlani"/>
			<xs:enumeration value="DepolamaAlani"/>
			<xs:enumeration value="LojistikTesisAlani"/>
			<xs:enumeration value="PazarAlani"/>
			<xs:enumeration value="TarimHayvancilikTesisAlani"/>
			<xs:enumeration value="AskeriAlan"/>
			<xs:enumeration value="BetonSantrali"/>
			<xs:enumeration value="1KademeTicaretAlani"/>
			<xs:enumeration value="2KademeTicaretAlani"/>
			<xs:enumeration value="3KademeTicaretAlani"/>
			<xs:enumeration value="SuUrunleriUretimYetistirmeTesisi"/>
			<xs:enumeration value="TicaretTurizmKonutAlani"/>
			<xs:enumeration value="ImalathaneTesisAlani"/>
			<xs:enumeration value="OSBHizmetDestekAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="EgitimTesisTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="AnaokuluAlani"/>
			<xs:enumeration value="IlkokulAlani"/>
			<xs:enumeration value="OrtaokulAlani"/>
			<xs:enumeration value="LiseAlani"/>
			<xs:enumeration value="OzelEgitimAlani"/>
			<xs:enumeration value="MeslekiTeknikOgretimTesisAlani"/>
			<xs:enumeration value="YuksekOgretimAlani"/>
			<xs:enumeration value="HalkEgitimMerkezi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="SaglikTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="SaglikTesisAlani"/>
			<xs:enumeration value="OzelSaglikTesisiAlani"/>
			<xs:enumeration value="Hastane"/>
			<xs:enumeration value="AileSagligiMerkezi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="TescilliAlan" type="plan:TescilliAlan"/>
	<xs:complexType name="TescilliAlan">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="EnvanterNo" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="PlanFonksiyonu" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TescilTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TescilTip" type="plan:TescilTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="IbadetTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Cami"/>
			<xs:enumeration value="Mescit"/>
			<xs:enumeration value="Kilise"/>
			<xs:enumeration value="Sapel"/>
			<xs:enumeration value="SinagogHavra"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="SosyalKulturelTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="SosyalTesisAlani"/>
			<xs:enumeration value="KulturelTesisAlani"/>
			<xs:enumeration value="SefkatEvleriAlani"/>
			<xs:enumeration value="AcikSporTesisiAlani"/>
			<xs:enumeration value="KapaliSporTesisiAlani"/>
			<xs:enumeration value="KresGunduzBakimevi"/>
			<xs:enumeration value="YurtAlani"/>
			<xs:enumeration value="KongreSergiMerkeziAlani"/>
			<xs:enumeration value="YasliBakimeviAlani"/>
			<xs:enumeration value="SemtSporAlani"/>
			<xs:enumeration value="OzelSosyalTesisAlani"/>
			<xs:enumeration value="OzelKulturelTesisAlani"/>
			<xs:enumeration value="OzelAcikSporTesisiAlani"/>
			<xs:enumeration value="OzelKapaliSporTesisiAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="AcikYesilTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Park"/>
			<xs:enumeration value="CocukBahcesiOyunAlani"/>
			<xs:enumeration value="PasifYesilAlan"/>
			<xs:enumeration value="RekreasyonAlani"/>
			<xs:enumeration value="FuarPanayirFestivalAlani"/>
			<xs:enumeration value="MesireYeri"/>
			<xs:enumeration value="HayvanatBahcesi"/>
			<xs:enumeration value="Hipodrom"/>
			<xs:enumeration value="Meydan"/>
			<xs:enumeration value="BakiSeyirTerasi"/>
			<xs:enumeration value="KentOrmani"/>
			<xs:enumeration value="ArboretumBotanikParki"/>
			<xs:enumeration value="AgaclandirilacakAlan"/>
			<xs:enumeration value="MezarlikAlani"/>
			<xs:enumeration value="KorunacakBahce"/>
			<xs:enumeration value="RekreatifAlan"/>
			<xs:enumeration value="MilletBahcesi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="SitAlanlari" type="plan:SitAlanlari"/>
	<xs:complexType name="SitAlanlari">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
					<xs:element name="SitTip" type="plan:SitTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="SitTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="1DereceArkeolojikSit"/>
			<xs:enumeration value="2DereceArkeolojikSit"/>
			<xs:enumeration value="3DereceArkeolojikSit"/>
			<xs:enumeration value="KesinKorunacakHassasAlan"/>
			<xs:enumeration value="NitelikliDogalKorumaAlani"/>
			<xs:enumeration value="SurdurulebilirKorumaKontrolluKullanimAlani"/>
			<xs:enumeration value="KentselSit"/>
			<xs:enumeration value="TarihiSit"/>
			<xs:enumeration value="SitEtkilesimAlani"/>
			<xs:enumeration value="1DereceDogalSit"/>
			<xs:enumeration value="2DereceDogalSit"/>
			<xs:enumeration value="3DereceDogalSit"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="HassaslikDerecesi">
		<xs:restriction base="xs:string">
			<xs:enumeration value="OckBolgesiHassasAlanA"/>
			<xs:enumeration value="OckBolgesiHassasAlanB"/>
			<xs:enumeration value="OckBolgesiHassasAlanC"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="SozlesmeKoruma" type="plan:SozlesmeKoruma"/>
	<xs:complexType name="SozlesmeKoruma">
		<xs:annotation>
			<xs:documentation>Uluslarası Sözleşmelerle Belirlenen Koruma Alan Sınırı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="AlanAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
					<xs:element name="SozlesmeAdi" type="xs:string" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="KentselImge" type="plan:KentselImge"/>
	<xs:complexType name="KentselImge">
		<xs:annotation>
			<xs:documentation>Kentsel Görüntü Ögeleri / İmgeleri (Vista/Silüet-Odak Noktalari vb)</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:PointPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="TescilTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="TescilliAnitYapi"/>
			<xs:enumeration value="TescilliBina"/>
			<xs:enumeration value="TescilliParsel"/>
			<xs:enumeration value="TescilliTabiatVarligi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="Tarim" type="plan:Tarim"/>
	<xs:complexType name="Tarim">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="EmsalKaks" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="EmsalKaksTip" type="plan:DegerTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="MinimumIfraz" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TarimTip" type="plan:TarimTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YapiYuksekligi" type="xs:double" minOccurs="1" maxOccurs="1"/>
					<xs:element name="YapiYuksekligiTip" type="plan:DegerTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="TarimTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Zeytinlik"/>
			<xs:enumeration value="OrtuAltiTarim"/>
			<xs:enumeration value="OrganikTarim"/>
			<xs:enumeration value="TarımsalNitelikliAlan"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="Mera" type="plan:Mera"/>
	<xs:complexType name="Mera">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="MeraSinif" type="plan:MeraSinif" minOccurs="1" maxOccurs="1"/>
					<xs:element name="MeraTip" type="plan:MeraTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
  <xs:element name="OzelProjeAlanSiniri" type="plan:OzelProjeAlanSiniri"/>
  <xs:complexType name="OzelProjeAlanSiniri">
	  <xs:complexContent>
		  <xs:extension base="plan:CsbFeatureType">
			  <xs:sequence>
				  <xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
			  </xs:sequence>
		  </xs:extension>
	  </xs:complexContent>
  </xs:complexType>
  <xs:element name="YeraltiSuKaynakKoruma" type="plan:YeraltiSuKaynakKoruma"/>
  <xs:complexType name="YeraltiSuKaynakKoruma">
	  <xs:complexContent>
		  <xs:extension base="plan:CsbFeatureType">
			  <xs:sequence>
				  <xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
			  </xs:sequence>
		  </xs:extension>
	  </xs:complexContent>
  </xs:complexType>
	<xs:simpleType name="MeraSinif">
		<xs:restriction base="xs:string">
			<xs:enumeration value="CokIyi"/>
			<xs:enumeration value="Iyi"/>
			<xs:enumeration value="Orta"/>
			<xs:enumeration value="Kotu"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="HavaalaniHavaKoridoru" type="plan:HavaalaniHavaKoridoru"/>
	<xs:complexType name="HavaalaniHavaKoridoru">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="MeraTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Mera"/>
			<xs:enumeration value="Yaylak"/>
			<xs:enumeration value="Kislak"/>
			<xs:enumeration value="Cayir"/>
			<xs:enumeration value="Otlak"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="KumsalPlaj" type="plan:KumsalPlaj"/>
	<xs:complexType name="KumsalPlaj">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="KorumaKusaklari" type="plan:KorumaKusaklari"/>
	<xs:complexType name="KorumaKusaklari">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KusakTip" type="plan:KusakTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="KusakTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="NukleerEnerjiKorumaKusagi"/>
			<xs:enumeration value="HavaalaniKorumaKusagi"/>
			<xs:enumeration value="KarayoluKorumaKusagi"/>
			<xs:enumeration value="BoruHattiKorumaKusagi"/>
			<xs:enumeration value="SuKanaliKorumaKusagi"/>
			<xs:enumeration value="IcmesuyuKorumaKusagi"/>
			<xs:enumeration value="YeraltiSuKorumaKusagi"/>
			<xs:enumeration value="DemiryoluKorumaKusagi"/>
			<xs:enumeration value="JeotermalKorumaKusagi"/>
			<xs:enumeration value="YaniciPatlayiciMaddeKorumaKusagi"/>
			<xs:enumeration value="SaglikKorumaBandi"/>
			<xs:enumeration value="EnerjiNakilHattiKorumaKusagi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="AfetTehlikeliAlanlar" type="plan:AfetTehlikeliAlanlar"/>
	<xs:complexType name="AfetTehlikeliAlanlar">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="AfetTip" type="plan:AfetTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="AfetTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="YapiYasakliAlan"/>
			<xs:enumeration value="HeyelanAlani"/>
			<xs:enumeration value="TaskinaMaruzAlan"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="OnlemliAlan" type="plan:OnlemliAlan"/>
	<xs:complexType name="OnlemliAlan">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="OnlemliTip" type="plan:OnlemliTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="OnlemliTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="OnlemliAlan"/>
			<xs:enumeration value="1DereceOnlemliAlan"/>
			<xs:enumeration value="2DereceOnlemliAlan"/>
			<xs:enumeration value="3DereceOnlemliAlan"/>
			<xs:enumeration value="4DereceOnlemliAlan"/>
			<xs:enumeration value="5DereceOnlemliAlan"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="EnerjiUretim" type="plan:EnerjiUretim"/>
	<xs:complexType name="EnerjiUretim">
		<xs:annotation>
			<xs:documentation>Enerji Üretim Alanı</xs:documentation>
		</xs:annotation>
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="EnerjiTip" type="plan:EnerjiTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KuruluGuc" type="xs:long" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="EnerjiTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="NukleerEnerjiSantralAlani"/>
			<xs:enumeration value="TermikSantralAlani"/>
			<xs:enumeration value="YenilenebilirEnerjiKaynaginaDayaliUretimTesisAlani"/>
			<xs:enumeration value="EnerjiUretimAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="EnerjiTesisTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="RegulatorAlani"/>
			<xs:enumeration value="TurbinAlani"/>
			<xs:enumeration value="DogalgazDagitimTesisAlani"/>
			<xs:enumeration value="YaniciParlayiciPatlayiciMaddeUretimDepoAlani"/>
			<xs:enumeration value="AkaryakitUrunDepolamaAlani"/>
			<xs:enumeration value="TrafoAlani"/>
			<xs:enumeration value="ElektronikHaberlesmeAltyapiAlani"/>
			<xs:enumeration value="RafineriPetroKimyaTesisiAlani"/>
			<xs:enumeration value="EnerjiDepolamaAlani"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="IletimHatti" type="plan:IletimHatti"/>
	<xs:complexType name="IletimHatti">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="EnerjiHatTip" type="plan:EnerjiHatTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="EnerjiNakilHatti" type="plan:EnerjiNakilHatti"/>
	<xs:complexType name="EnerjiNakilHatti">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="Gerilim" type="plan:GerilimKw" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="EnerjiHatTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="BoruHatti"/>
			<xs:enumeration value="DogalgazBoruHatti"/>
			<xs:enumeration value="AkaryakitBoruHatti"/>
			<xs:enumeration value="IletimTuneli"/>
			<xs:enumeration value="CebriBoruHatti"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="GerilimKw">
		<xs:restriction base="xs:string">
			<xs:enumeration value="34.5"/>
			<xs:enumeration value="154"/>
			<xs:enumeration value="380"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="AtiksuTesis" type="plan:AtiksuTesis"/>
	<xs:complexType name="AtiksuTesis">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="AtiksuTur" type="plan:AtiksuTur" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="AtiksuTur">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Aritma"/>
			<xs:enumeration value="TerfiMerkezi"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="KatiAtikTesis" type="plan:KatiAtikTesis"/>
	<xs:complexType name="KatiAtikTesis">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="KatiAtikTur" type="plan:KatiAtikTur" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="TehlikeliTesis" type="plan:TehlikeliTesis"/>
	<xs:complexType name="TehlikeliTesis">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="TehlikeTur" type="plan:TehlikeTur" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="TeknikAltyapi" type="plan:TeknikAltyapi"/>
	<xs:complexType name="TeknikAltyapi">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="AltyapiTur" type="plan:AltyapiTur" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="AtikGeriKazTesAlani" type="plan:AtikGeriKazTesAlani"/>
	<xs:complexType name="AtikGeriKazTesAlani">
		<xs:complexContent>
			<xs:extension base="plan:AbstractKatliYapi">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="SuYuzeyi" type="plan:SuYuzeyi"/>
	<xs:complexType name="SuYuzeyi">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="Adi" type="xs:string" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="SuYuzeyiTip" type="plan:SuYuzeyiTip" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:element name="AtiksuSistemi" type="plan:AtiksuSistemi"/>
	<xs:complexType name="AtiksuSistemi">
		<xs:complexContent>
			<xs:extension base="plan:CsbFeatureType">
				<xs:sequence>
					<xs:element name="AtiksuSistemTip" type="plan:AtiksuSistemTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="GeometryProperty" type="gml:LineStringPropertyType" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="KatiAtikTur">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Bosaltma"/>
			<xs:enumeration value="Bertaraf"/>
			<xs:enumeration value="Isleme"/>
			<xs:enumeration value="Transfer"/>
			<xs:enumeration value="Depolama"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="AltyapiTur">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Enerji"/>
			<xs:enumeration value="Icmesuyu"/>
			<xs:enumeration value="Atiksu"/>
			<xs:enumeration value="KatiAtik"/>
			<xs:enumeration value="Kanalizasyon"/>
			<xs:enumeration value="Ulastirma"/>
			<xs:enumeration value="Haberlesme"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="AtiksuSistemTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="AtiksuAnaKollektoru"/>
			<xs:enumeration value="AtiksuDerinDenizDesarjHatti"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="TehlikeTur">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Bertaraf"/>
			<xs:enumeration value="Depolama"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="SuYuzeyiTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Gol"/>
			<xs:enumeration value="Golet"/>
			<xs:enumeration value="NehirDere"/>
			<xs:enumeration value="Deniz"/>
			<xs:enumeration value="Baraj"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:simpleType name="MulkiyetTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="Ozel"/>
			<xs:enumeration value="Kamu"/>
		</xs:restriction>
	</xs:simpleType>
	<xs:element name="IlanEdilenClsmaAlan" type="plan:IlanEdilenClsmaAlan"/>
	<xs:complexType name="IlanEdilenClsmaAlan">
		<xs:complexContent>
			<xs:extension base="plan:AbstractYapilasma">
				<xs:sequence>
					<xs:element name="GeometryProperty" type="gml:MultiPolygonPropertyType" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanEdilenCalismaTip" type="plan:IlanEdilenCalismaTip" minOccurs="1" maxOccurs="1"/>
					<xs:element name="IlanTarihi" type="xs:dateTime" minOccurs="1" maxOccurs="1"/>
				</xs:sequence>
			</xs:extension>
		</xs:complexContent>
	</xs:complexType>
	<xs:simpleType name="IlanEdilenCalismaTip">
		<xs:restriction base="xs:string">
			<xs:enumeration value="TeknolojiGelistirmeBolgesi"/>
			<xs:enumeration value="SerbestBolge"/>
			<xs:enumeration value="Osb"/>
			<xs:enumeration value="EndustriBolgesi"/>
		</xs:restriction>
	</xs:simpleType>
		<xs:element name="FeatureCollection" type="plan:FeatureCollection"/>
	  <xs:complexType name="FeatureCollection">
		<xs:choice maxOccurs="unbounded">
		  <xs:element minOccurs="0" maxOccurs="1" name="featureMember" type="plan:features"/>
		</xs:choice>
	  </xs:complexType>
	  <xs:element name="features" type="plan:features"/>
	  <xs:complexType name="features">
		<xs:choice maxOccurs="unbounded">
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="AcikYesilAlan" type="plan:AcikYesilAlan"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="AfetTehlikeliAlanlar" type="plan:AfetTehlikeliAlanlar"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="AdaKenari" type="plan:AdaKenari"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="AtiksuSistemi" type="plan:AtiksuSistemi"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="AtiksuTesis" type="plan:AtiksuTesis"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="AskeriYasakBolge" type="plan:AskeriYasakBolge"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="BelediyeSiniri" type="plan:BelediyeSiniri"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="BisikletYolu" type="plan:BisikletYolu"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="BogaziciSinirlari" type="plan:BogaziciSinirlari"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="BuyuksehirSiniri" type="plan:BuyuksehirSiniri"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="Demiryolu" type="plan:Demiryolu"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="DenizUlasimBaglanti" type="plan:DenizUlasimBaglanti"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="DigerOzelSinir" type="plan:DigerOzelSinir"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="DigerYolNesneleri" type="plan:DigerYolNesneleri"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="DogalKarakter" type="plan:DogalKarakter"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="DonusumKonutAlanlari" type="plan:DonusumKonutAlanlari"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="Durak" type="plan:Durak"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="EgitimTesisAlani" type="plan:EgitimTesisAlani"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="EnerjiDagitimDepolama" type="plan:EnerjiDagitimDepolama"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="EnerjiNakilHatti" type="plan:EnerjiNakilHatti"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="EnerjiUretim" type="plan:EnerjiUretim"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="EtaplamaSiniri" type="plan:EtaplamaSiniri"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="FonksiyonluCalisma" type="plan:FonksiyonluCalisma"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="HavaalaniHavaKoridoru" type="plan:HavaalaniHavaKoridoru"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="HavayoluTesisleri" type="plan:HavayoluTesisleri"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="IbadetAlani" type="plan:IbadetAlani"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="IcmeKullanmaSuyuKoruma" type="plan:IcmeKullanmaSuyuKoruma"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="IcmesuAnaHat" type="plan:IcmesuAnaHat"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="IcmesuTesis" type="plan:IcmesuTesis"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="IlSiniri" type="plan:IlSiniri"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="IlanEdilenClsmaAlan" type="plan:IlanEdilenClsmaAlan"/>
		  <xs:element minOccurs="0" maxOccurs="unbounded" name="IlceSiniri" type="plan:IlceSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="IletimHatti" type="plan:IletimHatti"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="ImarHakkiAktarimSiniri" type="plan:ImarHakkiAktarimSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="JeotermalKaynak" type="plan:JeotermalKaynak"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KarayoluTesisleri" type="plan:KarayoluTesisleri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KatiAtikTesis" type="plan:KatiAtikTesis"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KentselCalisma" type="plan:KentselCalisma"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KentselImge" type="plan:KentselImge"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KentselTasarimProjeSiniri" type="plan:KentselTasarimProjeSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KiyiKenarCizgisi" type="plan:KiyiKenarCizgisi"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KiyiKorumaYapilari" type="plan:KiyiKorumaYapilari"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KiyiYapilari" type="plan:KiyiYapilari"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="Konut" type="plan:Konut"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KopruGecit" type="plan:KopruGecit"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KorumaKusaklari" type="plan:KorumaKusaklari"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KoySiniri" type="plan:KoySiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="KumsalPlaj" type="plan:KumsalPlaj"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="MahalleSiniri" type="plan:MahalleSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="ManiaPlani" type="plan:ManiaPlani"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="Mera" type="plan:Mera"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="MilliPark" type="plan:MilliPark"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="MucavirAlanSiniri" type="plan:MucavirAlanSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="OckBolge" type="plan:OckBolge"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="OckHassasAlan" type="plan:OckHassasAlan"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="OnlemliAlan" type="plan:OnlemliAlan"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="Orman" type="plan:Orman"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="OzelEkosistem" type="plan:OzelEkosistem"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="PlanDegisiklikSiniri" type="plan:PlanDegisiklikSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="PlanNotu" type="plan:PlanNotu"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="PlanSiniri" type="plan:PlanSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SaglikTesisAlani" type="plan:SaglikTesisAlani"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SahilSeridi" type="plan:SahilSeridi"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SitAlanlari" type="plan:SitAlanlari"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SogutmaSuyuAlmaHatti" type="plan:SogutmaSuyuAlmaHatti"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SosyalKulturelAlan" type="plan:SosyalKulturelAlan"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SozlesmeKoruma" type="plan:SozlesmeKoruma"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SuKaptaj" type="plan:SuKaptaj"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SuYuzeyi" type="plan:SuYuzeyi"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SulakAlan" type="plan:SulakAlan"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="Tarim" type="plan:Tarim"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TehlikeliTesis" type="plan:TehlikeliTesis"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TeknikAltyapi" type="plan:TeknikAltyapi"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="AtikGeriKazTesAlani" type="plan:AtikGeriKazTesAlani"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TescilliAlan" type="plan:TescilliAlan"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TmKtkgbAlan" type="plan:TmKtkgbAlan"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TopluTasimTurleriArasiDegisimAktarmaAlani" type="plan:TopluTasimTurleriArasiDegisimAktarmaAlani"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TopluTasimaHatti" type="plan:TopluTasimaHatti"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TurizmAlani" type="plan:TurizmAlani"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="UlkeSiniri" type="plan:UlkeSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="YapiYaklasmaSiniri" type="plan:YapiYaklasmaSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="YapiYaklasC" type="plan:YapiYaklasC"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="YayaYolu" type="plan:YayaYolu"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="Yolorta" type="plan:Yolorta"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="YoreselMimariKoruma" type="plan:YoreselMimariKoruma"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="YapayAda" type="plan:YapayAda"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="OzelProjeAlanSiniri" type="plan:OzelProjeAlanSiniri"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="YeraltiSuKaynakKoruma" type="plan:YeraltiSuKaynakKoruma"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="SulamaHatti" type="plan:SulamaHatti"/>
		   <xs:element minOccurs="0" maxOccurs="unbounded" name="TunelEtkiAlani" type="plan:TunelEtkiAlani"/>
		</xs:choice>
	  </xs:complexType>
</xs:schema>

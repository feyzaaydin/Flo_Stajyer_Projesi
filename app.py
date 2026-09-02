import streamlit as st
import sqlite3
import pandas as pd
import PyPDF2
from google import genai
import plotly.express as px
import io
import time
import datetime
import re

from okullar import universiteler_listesi
from bolumler import bolumler_listesi
from database import FLO_DEPARTMANLARI
from veritabani_islemleri import semayi_kontrol_et_ve_onar, basvuru_kaydet

semayi_kontrol_et_ve_onar()

st.set_page_config(page_title="FLO Kariyer - Stajyer Başvurusu", layout="wide")

st.sidebar.image("flo.jpg", width="stretch")
st.sidebar.header("⚙️ Sistem")

# API anahtarını önce güvenli sistem ayarlarından (.streamlit/secrets.toml) okumayı dene.
# Orada tanımlıysa kullanıcı her seferinde elle girmek zorunda kalmaz.
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ API anahtarı sistemde kayıtlı, tekrar girmenize gerek yok.")
except Exception:
    api_key = st.sidebar.text_input("Gemini API Anahtarı Girin", type="password")
    st.sidebar.info("Yapay zeka analizinin çalışması için Google AI Studio'dan alınmış bir API anahtarı gereklidir.")

st.title("👟 FLO Stajyer Başvuru Sistemi")
st.write("Aşağıdaki formu doldurun ve CV'nizi yükleyin.")

yetkinlik_havuzu = [
    # Yazılım & Teknoloji
    "Python", "SQL", "Yazılım Geliştirme", "React", "Node.js", "API",
    "Makine Öğrenmesi", "Veri Analizi", "Veri Bilimi", "Bulut Teknolojileri (Cloud)",
    "Siber Güvenlik", "Mobil Uygulama Geliştirme", "Otomasyon", "Test Mühendisliği",

    # Ofis & Analitik
    "Excel", "Analitik Düşünme", "Problem Çözme", "Araştırma", "Raporlama",
    "Proje Yönetimi", "Süreç İyileştirme", "Bütçe Yönetimi", "Finansal Analiz",

    # Pazarlama & Dijital
    "Pazarlama", "Dijital Pazarlama", "Sosyal Medya", "SEO", "SEM",
    "İçerik Üretimi", "Marka Yönetimi", "Reklamcılık", "E-Posta Pazarlaması",
    "Influencer İş Birlikleri", "Fotoğrafçılık", "Video Düzenleme",

    # Tasarım
    "Tasarım", "UI/UX Tasarım", "Grafik Tasarım", "Adobe Photoshop",
    "Adobe Illustrator", "Figma", "Kullanıcı Deneyimi Araştırması",

    # E-Ticaret & Lojistik
    "E-Ticaret Yönetimi", "Lojistik", "Tedarik Zinciri Yönetimi", "Stok Yönetimi",
    "Depo Yönetimi", "Sevkiyat Planlama", "Satın Alma",

    # İnsan Kaynakları & Yönetim
    "İletişim", "Liderlik", "İşe Alım", "Takım Çalışması", "Performans Yönetimi",
    "Eğitim ve Gelişim", "Organizasyon Becerisi", "Zaman Yönetimi", "Sunum Becerisi",
    "Müzakere", "Müşteri İlişkileri Yönetimi",

    # Diğer
    "Yabancı Dil (İngilizce)", "Hukuk ve Uyum", "Sürdürülebilirlik"
]

def gecerli_eposta_mi(eposta):
    eposta = eposta.strip()
    # Kullanıcı adı: harf/rakam/._%+- ; alan adı: harf/rakam/.- ; uzantı: en az 2 harf
    desen = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(desen, eposta):
        return False
    if '..' in eposta:                      # üst üste nokta (ör. ad..soyad@x.com)
        return False
    if eposta.startswith('.') or eposta.startswith('@'):  # baştan nokta/@ ile başlama
        return False
    kullanici_adi, alan_adi = eposta.split('@', 1)
    if alan_adi.startswith('.') or alan_adi.startswith('-'):  # alan adı . veya - ile başlamasın
        return False
    return True

def gecerli_telefon_mu(telefon):
    telefon = telefon.strip()
    if not telefon:
        return True  # isteğe bağlı alan, boş bırakılabilir
    sadece_rakamlar = re.sub(r'\D', '', telefon)  # boşluk, tire, parantez vb. temizle
    # Kabul edilen formatlar: 5XXXXXXXXX / 05XXXXXXXXX / 905XXXXXXXXX (+90 dahil)
    return bool(re.match(r'^(90)?0?5\d{9}$', sadece_rakamlar))

def pdf_metin_cikar(pdf_dosyasi):
    pdf_okuyucu = PyPDF2.PdfReader(pdf_dosyasi)
    metin = ""
    for sayfa in pdf_okuyucu.pages:
        metin += sayfa.extract_text()
    return metin

def cv_analiz_et(cv_metni, yetkinlikler, key):
    client = genai.Client(api_key=key)
    prompt = f"""Sen uzman bir IT ve İK işe alım uzmanısın. Adayın CV'sini derinlemesine analiz et.
    Sadece şu havuzdaki kelimeleri kullanarak eşleşenleri bul: {', '.join(yetkinlikler)}. 
    Sadece eşleşen kelimeleri virgülle ayırarak yaz, hiçbir ek açıklama yapma."""
    
    for deneme in range(3):
        try:
            response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
            return [yetenek.strip() for yetenek in response.text.split(",") if yetenek.strip()]
        except Exception:
            if deneme < 2:
                time.sleep(3)
                continue
            else:
                return [] # Hata durumunda sistemi çökertmez, boş geçer

def metin_analiz_et(hedef_metni, yetkinlikler, key):
    client = genai.Client(api_key=key)
    prompt = f"""Sen uzman bir IK işe alım uzmanısın. Adayın kendi cümleleriyle yazdığı hedeflerini,
    ilgi alanlarını ve ne yapmak istediğini analiz et.
    Sadece şu havuzdaki kelimeleri kullanarak, adayın anlattıklarıyla eşleşen yetkinlikleri bul: {', '.join(yetkinlikler)}.
    Adayın yazdığı metin:
    \"\"\"{hedef_metni}\"\"\"
    Sadece eşleşen kelimeleri virgülle ayırarak yaz, hiçbir ek açıklama yapma."""

    for deneme in range(3):
        try:
            response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
            return [yetenek.strip() for yetenek in response.text.split(",") if yetenek.strip()]
        except Exception:
            if deneme < 2:
                time.sleep(3)
                continue
            else:
                return [] # Hata durumunda sistemi çökertmez, boş geçer

def yeni_proje_onerisi_olustur(final_yetkinlikler, ad_soyad, bolum, key):
    conn = sqlite3.connect('flo_stajyer.db')
    mevcut_projeler_df = pd.read_sql_query(
        "SELECT proje_adi, departman, aranan_yetkinlikler, aciklama FROM projeler", conn
    )
    conn.close()

    ornekler = "\n".join(
        f"- {row['proje_adi']} ({row['departman']}): {row['aciklama']} [Gerekli yetkinlikler: {row['aranan_yetkinlikler']}]"
        for _, row in mevcut_projeler_df.iterrows()
    )

    departman_listesi_metni = "\n".join(f"- {d}" for d in FLO_DEPARTMANLARI)

    prompt = f"""Sen FLO ayakkabı ve spor perakende şirketinde stajyer projelerini planlayan deneyimli bir İK/proje yöneticisisin.
    Aşağıda FLO'nun mevcut stajyer proje havuzundan örnekler var, bunları sadece FLO'nun iş yapısını ve üslubunu anlamak için referans al:
    {ornekler}

    Şimdi yeni bir aday geldi: {ad_soyad} ({bolum} bölümü okuyor), yetkinlikleri: {', '.join(final_yetkinlikler)}.
    Mevcut projelerin hiçbiri bu adayın yetkinlikleriyle güçlü bir şekilde eşleşmiyor.

    Bu adayın yetkinliklerine özel, gerçekçi ve FLO bünyesinde uygulanabilir YENİ bir stajyer proje fikri öner.

    ÖNEMLİ KURAL: DEPARTMAN alanına SADECE aşağıdaki FLO departman listesinden birini,
    yazdığı gibi BİREBİR aynı şekilde yaz. Listede olmayan, kısaltılmış ya da uydurma bir
    departman adı YAZMA:
    {departman_listesi_metni}

    Cevabını TAM OLARAK şu formatta ver, başka hiçbir açıklama ekleme:
    PROJE_ADI: <proje adı>
    DEPARTMAN: <yukarıdaki listeden birebir bir departman adı>
    ACIKLAMA: <1-2 cümlelik proje açıklaması>
    GEREKCE: <adayın yetkinlikleriyle neden uyumlu olduğuna dair 1 cümle>"""

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        sonuc = {}
        for satir in response.text.strip().split("\n"):
            if ":" in satir:
                anahtar, deger = satir.split(":", 1)
                sonuc[anahtar.strip().upper()] = deger.strip()

        if "PROJE_ADI" not in sonuc:
            return None

        # Güvenlik kontrolü: AI listede olmayan/uydurma bir departman yazmışsa
        # bunu FLO'nun gerçek departmanlarından biriyle değiştirmiyoruz, sadece
        # olduğunu belirtip en yakın bilinen değeri "Belirtilmedi" yapıyoruz.
        if sonuc.get("DEPARTMAN") not in FLO_DEPARTMANLARI:
            sonuc["DEPARTMAN"] = "Belirtilmedi (İK ile görüşülmeli)"

        return sonuc
    except Exception:
        return None

def cv_tutarliligini_kontrol_et(cv_metni, form_ad_soyad, form_bolum, form_universite, form_sinif, key):
    prompt = f"""Sen bir CV doğrulama uzmanısın. Aday başvuru formuna şu bilgileri girdi:
    Ad Soyad: {form_ad_soyad}
    Üniversite: {form_universite}
    Bölüm: {form_bolum}
    Sınıf/Eğitim Seviyesi: {form_sinif}

    Aşağıdaki CV metnini incele ve CV'de yer alan ad soyad, üniversite, bölüm ve sınıf/mezuniyet
    bilgisinin, formda girilen bilgilerle tutarlı olup olmadığını değerlendir. CV'de bu bilgilerden
    biri hiç geçmiyorsa bunu bir uyumsuzluk sayma, sadece gerçekten çelişen bir bilgi varsa belirt.

    CV Metni:
    \"\"\"{cv_metni[:4000]}\"\"\"

    Cevabını TAM OLARAK şu formatta ver, başka hiçbir şey yazma:
    TUTARLI: EVET veya HAYIR
    ACIKLAMA: <TUTARLI HAYIR ise hangi bilginin (ad soyad/üniversite/bölüm/sınıf) uyuşmadığını 1-2 cümleyle açıkla, EVET ise boş bırak>"""

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
        sonuc = {}
        for satir in response.text.strip().split("\n"):
            if ":" in satir:
                anahtar, deger = satir.split(":", 1)
                sonuc[anahtar.strip().upper()] = deger.strip()
        return sonuc
    except Exception:
        return None

def projeleri_eslestir(aday_yetkinlikler_listesi):
    conn = sqlite3.connect('flo_stajyer.db')
    df = pd.read_sql_query("SELECT * FROM projeler", conn)
    conn.close()
    
    uyum_puanlari = []
    
    for index, row in df.iterrows():
        aranan_metin = row["aranan_yetkinlikler"]
        aranan_listesi = [y.strip() for y in str(aranan_metin).split(",") if y.strip()]
        aranan_sayisi = len(aranan_listesi)
        
        if aranan_sayisi == 0:
            uyum_puanlari.append(0)
            continue
            
        ortak_yetkinlikler = set(aranan_listesi).intersection(set(aday_yetkinlikler_listesi))
        uyum_yuzdesi = (len(ortak_yetkinlikler) / aranan_sayisi) * 100
        
        uyum_puanlari.append(round(uyum_yuzdesi, 2))
        
    df["Uyum Puanı (%)"] = uyum_puanlari
    df_sonuc = df.sort_values(by="Uyum Puanı (%)", ascending=False).reset_index(drop=True)
    return df_sonuc

with st.form("kurumsal_basvuru_formu"):
    st.subheader("👤 Kişisel ve Eğitim Bilgileriniz")
    
    col1, col2 = st.columns(2)
    with col1:
        ad_soyad = st.text_input("Adınız ve Soyadınız*")
        eposta = st.text_input("E-posta Adresiniz*", placeholder="ornek@eposta.com")
        universite = st.selectbox("Üniversiteniz* (Yazarak arayabilirsiniz)", universiteler_listesi)
        universite_diger = st.text_input("Üniversitenizi 'Diğer' seçtiyseniz buraya yazın:")
        bolum = st.selectbox("Okuduğunuz Bölüm* (Yazarak arayabilirsiniz)", bolumler_listesi)
        bolum_diger = st.text_input("Bölümünüzü 'Diğer' seçtiyseniz buraya yazın:")   
        
    with col2:
        telefon = st.text_input("Telefon Numaranız", placeholder="05xx xxx xx xx (isteğe bağlı)")
        egitim_seviyesi = st.selectbox("Eğitim Durumunuz", ["Lise", "Üniversite (Ön Lisans)", "Üniversite (Lisans)", "Yüksek Lisans", "Doktora"])
        sinif = st.selectbox("Kaçıncı Sınıftasınız?", [
            "Hazırlık", "1. Sınıf", "2. Sınıf", "3. Sınıf", "4. Sınıf", "5. Sınıf",
            "Yüksek Lisans", "Doktora"
        ])
        staj_gunu = st.number_input("Staj Süreniz (Gün)*", min_value=10, max_value=120, value=30, step=5)
        
    st.divider()
    
    st.subheader("🌟 Yetkinlikler ve Özgeçmiş (CV)")
    secilen_yetkinlikler = st.multiselect("Yetkinliklerinizi Seçin", yetkinlik_havuzu)
    yuklenen_cv = st.file_uploader("Özgeçmişinizi Yükleyin (PDF) - İsteğe Bağlı", type=["pdf"])

    st.divider()

    st.subheader("💭 Hedefleriniz")
    hedef_metni = st.text_area(
        "FLO'da hangi tür projelerde çalışmak istersiniz, neyi öğrenmek/geliştirmek hedefliyorsunuz? "
        "Kısaca kendi cümlelerinizle anlatın (isteğe bağlı)",
        placeholder="Örn: Veri analitiği ve pazarlama tarafında kendimi geliştirmek istiyorum, "
                    "Excel kullanmayı seviyorum, ekip içinde iletişimi güçlü biriyim...",
        height=120
    )

    submit_button = st.form_submit_button("Başvuruyu Tamamla ve Proje Bul")

if submit_button:
    nihai_bolum = bolum_diger if bolum == "Diğer (Listede Yok)" and bolum_diger else bolum
    nihai_universite = universite_diger if universite == "Diğer (Listede Yok)" and universite_diger else universite

    if not ad_soyad or not nihai_bolum or not eposta:
        st.error("Lütfen Ad Soyad, Bölüm ve E-posta alanlarını zorunlu olarak doldurun.")
    elif not gecerli_eposta_mi(eposta):
        st.error("Lütfen geçerli bir e-posta adresi girin (örn: ad@ornek.com).")
    elif not gecerli_telefon_mu(telefon):
        st.error("Lütfen geçerli bir telefon numarası girin (örn: 0555 111 22 33) ya da alanı boş bırakın.")
    elif not secilen_yetkinlikler and not yuklenen_cv and not hedef_metni.strip():
        st.error("Lütfen en azından havuzdan bir yetkinlik seçin, CV'nizi yükleyin ya da hedeflerinizi kısaca yazın.")
    else:
        final_yetkinlikler = list(secilen_yetkinlikler)

        if (yuklenen_cv or hedef_metni.strip()) and not api_key:
            st.error("CV veya hedef metni analizi için sol menüden API Anahtarını girmelisiniz!")
            st.stop()

        cv_tutarlilik_notu = ""

        if yuklenen_cv:
            with st.spinner('Yapay zeka CV\'nizi okuyor, bu birkaç saniye sürebilir...'):
                cv_metni = pdf_metin_cikar(yuklenen_cv)
                ai_yetkinlikler = cv_analiz_et(cv_metni, yetkinlik_havuzu, api_key)
                
                if ai_yetkinlikler:
                    final_yetkinlikler = list(set(final_yetkinlikler + ai_yetkinlikler))
                    st.toast('Yapay zeka CV analizinizi tamamladı!', icon='🤖')

            with st.spinner('CV bilgileriniz form ile karşılaştırılıyor...'):
                tutarlilik = cv_tutarliligini_kontrol_et(
                    cv_metni, ad_soyad, nihai_bolum, nihai_universite, sinif, api_key
                )
                if tutarlilik and tutarlilik.get("TUTARLI", "").strip().upper().startswith("HAY"):
                    cv_tutarlilik_notu = tutarlilik.get("ACIKLAMA", "").strip()

        if hedef_metni.strip():
            with st.spinner('Yapay zeka hedeflerinizi analiz ediyor...'):
                metin_yetkinlikler = metin_analiz_et(hedef_metni, yetkinlik_havuzu, api_key)

                if metin_yetkinlikler:
                    final_yetkinlikler = list(set(final_yetkinlikler + metin_yetkinlikler))
                    st.toast('Hedefleriniz analiz edildi!', icon='🎯')
        
        if final_yetkinlikler:
            st.snow() 
            sonuclar_df = projeleri_eslestir(final_yetkinlikler)
            
            if sonuclar_df.empty:
                st.warning("Seçtiğiniz yetkinliklere uygun bir proje bulunamadı.")
            else:
                st.success(f"**{ad_soyad}** ({nihai_bolum}) için en uygun projeler:")

                if cv_tutarlilik_notu:
                    st.warning(f"⚠️ CV tutarlılık kontrolü: {cv_tutarlilik_notu}")

                st.dataframe(sonuclar_df, width="stretch")

                en_iyi_satir = sonuclar_df.iloc[0]
                basvuru_kaydet(
                    ad_soyad, egitim_seviyesi, sinif, nihai_bolum, final_yetkinlikler, staj_gunu,
                    en_iyi_satir['departman'], en_iyi_satir['proje_adi'], en_iyi_satir['Uyum Puanı (%)'],
                    eposta=eposta, telefon=telefon, cv_tutarlilik_notu=cv_tutarlilik_notu
                )
                st.toast(f"{ad_soyad} için başvuru geçmişe kaydedildi!", icon='📝')

                DUSUK_ESLESME_ESIGI = 40  # yüzde
                if en_iyi_satir['Uyum Puanı (%)'] < DUSUK_ESLESME_ESIGI and api_key:
                    with st.spinner('Yapay zeka size özel bir proje fikri düşünüyor...'):
                        yeni_proje = yeni_proje_onerisi_olustur(final_yetkinlikler, ad_soyad, nihai_bolum, api_key)
                    if yeni_proje:
                        st.info(
                            f"🤖 **Yapay Zeka Önerisi:** Mevcut projeler arasında güçlü bir eşleşme bulunamadı, "
                            f"işte size özel bir fikir:\n\n"
                            f"**{yeni_proje.get('PROJE_ADI', '')}** — *{yeni_proje.get('DEPARTMAN', '')}*\n\n"
                            f"{yeni_proje.get('ACIKLAMA', '')}\n\n"
                            f"*Neden uygun:* {yeni_proje.get('GEREKCE', '')}"
                        )

                col1, col2 = st.columns(2)
                with col1:
                    # names='Departman' yerine names='departman' yazıyoruz
                    fig_pie = px.pie(sonuclar_df, 
                                     values='Uyum Puanı (%)', 
                                     names='departman', 
                                     title="Uygun Departman Dağılımı",
                                     color_discrete_sequence=['#F25C05', '#1E1E1E', '#FF8A4C', '#D3D3D3'])
                    st.plotly_chart(fig_pie, width="stretch", key="pie")
                    
                with col2:
                    # x='Proje Adı' yerine x='proje_adi' yazıyoruz
                    fig_bar = px.bar(sonuclar_df, x='proje_adi', y='Uyum Puanı (%)', 
                                     title="Proje Uyum Oranları",
                                     color_discrete_sequence=['#F25C05'])
                    st.plotly_chart(fig_bar, width="stretch", key="bar")
                    
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    sonuclar_df.to_excel(writer, index=False, sheet_name='Rapor')
                    
                dosya_adi = ad_soyad.replace(" ", "_")
                st.download_button(label="📥 Bu Raporu İndir (.xlsx)", 
                                   data=buffer.getvalue(), 
                                   file_name=f"{dosya_adi}_rapor.xlsx", 
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
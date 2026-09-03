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
from liseler import liseler_listesi
from database import FLO_DEPARTMANLARI
from veritabani_islemleri import semayi_kontrol_et_ve_onar, basvuru_kaydet
from eposta_gonder import haftalik_program_olustur, staj_programi_eposta_gonder

semayi_kontrol_et_ve_onar()

st.sidebar.image("flo.jpg", width="stretch")
st.sidebar.header("⚙️ Sistem.")

# API anahtarını önce güvenli sistem ayarlarından (.streamlit/secrets.toml) okumayı dene.
# Orada tanımlıysa kullanıcı her seferinde elle girmek zorunda kalmaz.
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ API anahtarı sistemde kayıtlı, tekrar girmenize gerek yok.")
except Exception:
    api_key = st.sidebar.text_input("Gemini API Anahtarı Girin", type="password")
    st.sidebar.info("Yapay zeka analizinin çalışması için Google AI Studio'dan alınmış bir API anahtarı gereklidir.")

# SMTP (e-posta) ayarları: stajyere çalışma programını göndermek için kullanılır.
# .streamlit/secrets.toml içinde tanımlı değilse e-posta adımı sessizce atlanır.
try:
    smtp_ayarlari = {
        "host": st.secrets["SMTP_HOST"],
        "port": st.secrets["SMTP_PORT"],
        "user": st.secrets["SMTP_USER"],
        "password": st.secrets["SMTP_PASSWORD"],
        "from": st.secrets.get("SMTP_FROM", st.secrets["SMTP_USER"]),
    }
    st.sidebar.success("✅ E-posta gönderimi aktif.")
except Exception:
    smtp_ayarlari = None
    st.sidebar.info("E-posta gönderimi kapalı: SMTP ayarları (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD) tanımlı değil.")

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

def _sadelestir(metin):
    """Karşılaştırma için metni sadeleştirir: küçük harf + Türkçe karakter sadeleştirme."""
    metin = (metin or "").lower()
    cevrim = str.maketrans("çğıöşü", "cgiosu")
    return metin.translate(cevrim)


def yerel_tutarlilik_kontrolu(cv_metni, form_ad_soyad, form_universite, form_bolum):
    """Yapay zekadan bağımsız, basit bir kontrol: formdaki ad soyad / üniversite / bölüm
    bilgileri CV metninde hiç geçmiyorsa uyumsuzluk olarak işaretlenir. AI çalışmasa bile
    en azından bariz uyuşmazlıklar yakalanır."""
    cv = _sadelestir(cv_metni)
    if not cv.strip():
        return ""

    uyusmayanlar = []

    # Ad soyad: en az bir isim parçası (2+ harf) CV'de geçmeli
    ad_parcalari = [p for p in _sadelestir(form_ad_soyad).split() if len(p) >= 2]
    if ad_parcalari and not any(p in cv for p in ad_parcalari):
        uyusmayanlar.append("ad soyad")

    for etiket, deger in (("üniversite", form_universite), ("bölüm", form_bolum)):
        deger_sade = _sadelestir(deger).strip()
        if deger_sade and deger_sade not in ("-", "diger (listede yok)"):
            anlamli_kelimeler = [k for k in deger_sade.split() if len(k) >= 4]
            if anlamli_kelimeler and not any(k in cv for k in anlamli_kelimeler):
                uyusmayanlar.append(etiket)

    if uyusmayanlar:
        return f"CV metninde şu form bilgileri bulunamadı: {', '.join(uyusmayanlar)}."
    return ""


def cv_analiz_ve_dogrulama_yap(
    cv_metni,
    yetkinlikler,
    form_ad_soyad,
    form_bolum,
    form_universite,
    form_sinif,
    key
):
    client = genai.Client(api_key=key)

    prompt = f"""
Sen SIFIR TOLERANSLI bir CV doğrulama uzmanısın.

GÖREV 1 - YETKİNLİK ANALİZİ:
Sadece şu havuzdan eşleşen yetkinlikleri bul:
{', '.join(yetkinlikler)}

GÖREV 2 - BİLGİ TUTARLILIK KONTROLÜ:

Adayın başvuru formuna girdiği bilgiler:

Ad Soyad: {form_ad_soyad}
Üniversite: {form_universite}
Bölüm: {form_bolum}

CV'deki bilgilerle formdaki bilgileri karşılaştır.

Eğer:
- Ad soyad açıkça farklıysa,
- Üniversite açıkça farklıysa,
- Bölüm açıkça farklıysa,

TUTARLI: HAYIR yaz.

Eğer bilgiler birbiriyle uyumluysa:

TUTARLI: EVET yaz.

Kesinlikle tahmin yapma.

CV Metni:
\"\"\"
{cv_metni[:4000]}
\"\"\"

Cevabını TAM OLARAK şu formatta ver:

YETKINLIKLER: <eşleşen yetkinlikleri virgülle yaz>
TUTARLI: EVET veya HAYIR
ACIKLAMA: <HAYIR ise hangi bilginin uyuşmadığını yaz, EVET ise boş bırak>
"""

    for deneme in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )

            sonuc = {}

            for satir in response.text.strip().split("\n"):
                if ":" in satir:
                    anahtar, deger = satir.split(":", 1)
                    # Yapay zekanın olası Türkçe düzeltmelerini yakalamak için Ç'yi C'ye çeviriyoruz
                    duzeltilmis_anahtar = anahtar.strip().upper().replace("Ç", "C").replace("İ", "I")
                    sonuc[duzeltilmis_anahtar] = deger.strip()

            ai_yetkinlikler = [
                y.strip()
                for y in sonuc.get("YETKINLIKLER", "").split(",")
                if y.strip()
            ]

            # 'HAYIR' kelimesi içinde geçiyorsa kabul et (bazen 'HAYIR.' veya boşluklu dönebilir)
            tutarlilik_durumu = sonuc.get("TUTARLI", "").upper()
            tutarlilik_notu = ""

            if "HAYIR" in tutarlilik_durumu:
                tutarlilik_notu = sonuc.get("ACIKLAMA", "").strip()
                # AI 'HAYIR' dediği halde açıklama boş bıraktıysa uyarı yine de görünsün
                if not tutarlilik_notu:
                    tutarlilik_notu = "CV'deki ad soyad / okul / bölüm bilgileri form bilgileriyle uyuşmuyor."

            return ai_yetkinlikler, tutarlilik_notu

        except Exception:
            if deneme < 2:
                time.sleep(3)
                continue
            else:
                return [], ""

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

def proje_secim_gerekcesi_olustur(en_iyi_satir, aday_yetkinlikler, ad_soyad, bolum,
                                  sonuclar_df=None, staj_gunu=None, key=None):
    """Seçilen projenin neden bu adaya atandığını DETAYLI biçimde açıklayan bir metin üretir.

    Önce deterministik bir analiz (eşleşen/eksik yetkinlikler, uyum puanı) hazırlanır;
    API anahtarı varsa yapay zeka bunu akıcı, kişiselleştirilmiş bir gerekçeye dönüştürür.
    """
    aranan_listesi = [y.strip() for y in str(en_iyi_satir['aranan_yetkinlikler']).split(",") if y.strip()]
    ortak = [y for y in aranan_listesi if y in aday_yetkinlikler]
    eksik = [y for y in aranan_listesi if y not in aday_yetkinlikler]
    ekstra = [y for y in aday_yetkinlikler if y not in aranan_listesi]
    puan = en_iyi_satir['Uyum Puanı (%)']
    proje_adi = en_iyi_satir['proje_adi']
    departman = en_iyi_satir['departman']
    aciklama = en_iyi_satir.get('aciklama', '') if hasattr(en_iyi_satir, 'get') else en_iyi_satir['aciklama']

    # --- Deterministik (yapay zeka olmadan da anlamlı) taban metin ---
    if puan >= 70:
        puan_yorum = "çok güçlü bir eşleşme"
    elif puan >= 40:
        puan_yorum = "iyi düzeyde bir eşleşme"
    else:
        puan_yorum = "kısmi bir eşleşme (yine de en yakın seçenek)"

    taban = (
        f"**{proje_adi}** — *{departman}*\n\n"
        f"**Genel değerlendirme:** Bu proje, sistemdeki tüm projeler arasında profilinizle "
        f"**%{puan}** uyum puanı alarak {puan_yorum} gösterdi. Uyum puanı, projenin aradığı "
        f"{len(aranan_listesi)} yetkinlikten kaçının sizde bulunduğuna göre hesaplanır.\n\n"
        f"**Sizi bu projeye uygun kılan yetkinlikler ({len(ortak)}/{len(aranan_listesi)}):** "
        f"{', '.join(ortak) if ortak else 'doğrudan eşleşen yok, ancak genel profiliniz en yakın bu projeye düşüyor'}.\n\n"
    )
    if eksik:
        taban += (
            f"**Staj sürecinde geliştirebileceğiniz yönler:** {', '.join(eksik)}. "
            f"Bu yetkinlikler projenin kapsamında yer alıyor; ekip ve mentor desteğiyle bunları "
            f"uygulamalı olarak öğrenmeniz bekleniyor.\n\n"
        )

    # --- Aynı puanlı projeler arasında neden BU proje 1. sırada? ---
    if sonuclar_df is not None and "Uyum Puanı (%)" in sonuclar_df.columns:
        ayni_puanlilar = sonuclar_df[sonuclar_df["Uyum Puanı (%)"] == puan]
        if len(ayni_puanlilar) > 1:
            digerleri = [
                p for p in ayni_puanlilar["proje_adi"].tolist() if p != proje_adi
            ][:5]
            es_sayi = int(en_iyi_satir.get("Eşleşen Yetkinlik Sayısı", len(ortak))) \
                if hasattr(en_iyi_satir, "get") else len(ortak)
            taban += (
                f"**Neden aynı puanlı projeler arasından bu proje 1. sırada?** "
                f"Bu projeyle birlikte toplam **{len(ayni_puanlilar)} proje** aynı **%{puan}** uyum "
                f"puanını aldı (ör. {', '.join(digerleri)}). Eşitlik durumunda sistem şu sıraya göre "
                f"öne çıkarır: (1) yüzde aynıysa **mutlak eşleşen yetkinlik sayısı** daha fazla olan "
                f"(bu projede {es_sayi} yetkinlik doğrudan örtüşüyor), (2) sonra **staj sürenize "
                f"({staj_gunu} gün) en uygun** minimum süreli proje. Bu projenin gereksinimleri "
                f"bu iki ölçütte diğerlerine göre profilinize daha yakın düştüğü için ilk sıraya "
                f"kondu. Diğer aynı puanlı projeler de sizin için uygun alternatiflerdir; tablodan "
                f"inceleyebilirsiniz.\n\n"
            )
    if ekstra:
        taban += (
            f"**Projeye katabileceğiniz ek değer:** {', '.join(ekstra[:8])} gibi yetkinlikleriniz "
            f"projenin doğrudan gereksinimi olmasa da çıktının kalitesini artırabilir.\n\n"
        )
    taban += f"**Proje kapsamı:** {aciklama}"

    if not key:
        return taban

    esitlik_bilgisi = "Bu puanı alan tek proje bu."
    if sonuclar_df is not None and "Uyum Puanı (%)" in sonuclar_df.columns:
        ayni = sonuclar_df[sonuclar_df["Uyum Puanı (%)"] == puan]
        if len(ayni) > 1:
            esitlik_bilgisi = (
                f"Aynı %{puan} puanı {len(ayni)} proje aldı. Bu proje 1. sıraya kondu çünkü eşitlikte "
                f"önce mutlak eşleşen yetkinlik sayısı ({len(ortak)}), sonra adayın staj süresine "
                f"({staj_gunu} gün) uygunluk dikkate alınıyor ve bu proje bu ölçütlerde önde."
            )

    prompt = f"""Sen FLO'da stajyer yerleştirmesi yapan bir İK uzmanısın. Aşağıdaki eşleştirme sonucunu,
adaya hitap eden, açık ve motive edici bir "Bu proje neden size atandı?" açıklamasına dönüştür.

Aday: {ad_soyad} ({bolum})
Adayın yetkinlikleri: {', '.join(aday_yetkinlikler)}
Seçilen proje: {proje_adi} ({departman})
Proje açıklaması: {aciklama}
Projenin aradığı yetkinlikler: {', '.join(aranan_listesi)}
Adayda bulunan eşleşen yetkinlikler: {', '.join(ortak) if ortak else 'yok'}
Adayda eksik olan yetkinlikler: {', '.join(eksik) if eksik else 'yok'}
Uyum puanı: %{puan}
Eşitlik/sıralama durumu: {esitlik_bilgisi}

Açıklama şu 5 başlığı içersin (markdown ** ile kalın başlıklar kullan, her başlık 2-3 cümle):
1. **Neden bu proje?** — genel uyum ve puanın anlamı
2. **Hangi yetkinlikleriniz işe yarayacak?** — eşleşen yetkinlikleri projedeki somut görevlerle ilişkilendir
3. **Bu stajda ne öğreneceksiniz?** — eksik yetkinlikler ve projenin kazandıracakları
4. **Neden diğer aynı puanlı projeler değil de bu?** — yukarıdaki eşitlik/sıralama durumunu sade bir dille açıkla (eşitlik yoksa bu başlıkta puanın neden en yüksek olduğunu söyle)
5. **Beklentiler** — stajın sonunda ortaya çıkması beklenen çıktı

Toplam 200-300 kelime. Uydurma bilgi ekleme, sadece verilenleri yorumla."""

    for _ in range(2):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
            metin = response.text.strip()
            if len(metin) > 120:
                return metin
        except Exception:
            pass
    return taban


def projeleri_eslestir(aday_yetkinlikler_listesi, staj_gunu=None):
    conn = sqlite3.connect('flo_stajyer.db')
    df = pd.read_sql_query("SELECT * FROM projeler", conn)
    conn.close()

    uyum_puanlari = []
    eslesen_sayilari = []

    for index, row in df.iterrows():
        aranan_metin = row["aranan_yetkinlikler"]
        aranan_listesi = [y.strip() for y in str(aranan_metin).split(",") if y.strip()]
        aranan_sayisi = len(aranan_listesi)

        if aranan_sayisi == 0:
            uyum_puanlari.append(0)
            eslesen_sayilari.append(0)
            continue

        ortak_yetkinlikler = set(aranan_listesi).intersection(set(aday_yetkinlikler_listesi))
        uyum_yuzdesi = (len(ortak_yetkinlikler) / aranan_sayisi) * 100

        uyum_puanlari.append(round(uyum_yuzdesi, 2))
        eslesen_sayilari.append(len(ortak_yetkinlikler))

    df["Uyum Puanı (%)"] = uyum_puanlari
    df["Eşleşen Yetkinlik Sayısı"] = eslesen_sayilari

    # Aynı uyum puanına sahip projeler için mantıklı bir sıralama önceliği:
    # 1) Uyum puanı yüksek olan
    # 2) Mutlak eşleşen yetkinlik sayısı fazla olan (yüzde aynı olsa da daha çok yetkinlik örtüşüyorsa öne)
    # 3) Adayın staj süresine en uygun (min_staj_gunu'ye yakın / altında) proje
    if staj_gunu is not None and "min_staj_gunu" in df.columns:
        df["_staj_uygunluk"] = (df["min_staj_gunu"].fillna(0) - float(staj_gunu)).abs()
    else:
        df["_staj_uygunluk"] = df.get("min_staj_gunu", 0)

    df_sonuc = df.sort_values(
        by=["Uyum Puanı (%)", "Eşleşen Yetkinlik Sayısı", "_staj_uygunluk"],
        ascending=[False, False, True]
    ).drop(columns="_staj_uygunluk").reset_index(drop=True)
    return df_sonuc

st.subheader("👤 Kişisel ve Eğitim Bilgileriniz")

# Bu seçim kutusu BİLEREK formun dışında: Streamlit formları sadece "Gönder" butonuna
# basılınca güncellenir, ama biz "Lise" seçilir seçilmez lise listesinin anında
# görünmesini istiyoruz. Form dışındaki widget'lar her seçimde anında sayfayı yeniler.
egitim_seviyesi = st.selectbox(
    "Eğitim Durumunuz",
    ["Lise", "Üniversite (Ön Lisans)", "Üniversite (Lisans)", "Yüksek Lisans", "Doktora"],
    key="egitim_seviyesi_secimi"
)

lise_adi_nihai = ""
if egitim_seviyesi == "Lise":
    lise_col1, lise_col2 = st.columns(2)
    with lise_col1:
        lise_secimi = st.selectbox("Liseniz* (Yazarak arayabilirsiniz)", liseler_listesi, key="lise_secimi")
    with lise_col2:
        lise_diger = st.text_input("Lisenizi 'Diğer' seçtiyseniz buraya yazın:", key="lise_diger")
    lise_adi_nihai = lise_diger if lise_secimi == "Diğer (Listede Yok)" and lise_diger else lise_secimi

with st.form("kurumsal_basvuru_formu"):
    col1, col2 = st.columns(2)
    with col1:
        ad_soyad = st.text_input("Adınız ve Soyadınız*")
        eposta = st.text_input("E-posta Adresiniz*", placeholder="ornek@eposta.com")

        if egitim_seviyesi != "Lise":
            universite = st.selectbox("Üniversiteniz* (Yazarak arayabilirsiniz)", universiteler_listesi)
            universite_diger = st.text_input("Üniversitenizi 'Diğer' seçtiyseniz buraya yazın:")
            bolum = st.selectbox("Okuduğunuz Bölüm* (Yazarak arayabilirsiniz)", bolumler_listesi)
            bolum_diger = st.text_input("Bölümünüzü 'Diğer' seçtiyseniz buraya yazın:")
        else:
            universite = universite_diger = bolum = bolum_diger = ""
            st.caption("ℹ️ Lise öğrencisi olduğunuz için üniversite/bölüm bilgisi istenmiyor. "
                       "Lise bilginizi yukarıdaki alandan girdiniz.")

    with col2:
        telefon = st.text_input("Telefon Numaranız", placeholder="05xx xxx xx xx (isteğe bağlı)")

        if egitim_seviyesi == "Lise":
            sinif = st.selectbox("Kaçıncı Sınıftasınız?", ["Hazırlık", "9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"])
        else:
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
    if egitim_seviyesi == "Lise":
        nihai_bolum = "-"
        nihai_universite = "-"
        temel_bilgiler_eksik = not ad_soyad or not eposta or not lise_adi_nihai
        eksik_mesaji = "Lütfen Ad Soyad, E-posta ve Liseniz alanlarını zorunlu olarak doldurun."
    else:
        nihai_bolum = bolum_diger if bolum == "Diğer (Listede Yok)" and bolum_diger else bolum
        nihai_universite = universite_diger if universite == "Diğer (Listede Yok)" and universite_diger else universite
        temel_bilgiler_eksik = not ad_soyad or not nihai_bolum or not eposta
        eksik_mesaji = "Lütfen Ad Soyad, Bölüm ve E-posta alanlarını zorunlu olarak doldurun."

    if temel_bilgiler_eksik:
        st.error(eksik_mesaji)
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
            with st.spinner('Yapay zeka CV\'nizi okuyup form bilgilerinizle karşılaştırıyor...'):
                cv_metni = pdf_metin_cikar(yuklenen_cv)
                ai_yetkinlikler, cv_tutarlilik_notu = cv_analiz_ve_dogrulama_yap(
                    cv_metni, yetkinlik_havuzu, ad_soyad, nihai_bolum, nihai_universite, sinif, api_key
                )

                # Yapay zeka bir şey yakalayamasa (veya API çalışmasa) bile
                # basit yerel kontrol ile bariz uyuşmazlıkları yakala.
                if not cv_tutarlilik_notu:
                    cv_tutarlilik_notu = yerel_tutarlilik_kontrolu(
                        cv_metni, ad_soyad, nihai_universite, nihai_bolum
                    )

                # Buradaki st.error satırlarını kaldırdık çünkü aşağıda sonuçlarla beraber göstereceğiz.

                if ai_yetkinlikler:
                    final_yetkinlikler = list(set(final_yetkinlikler + ai_yetkinlikler))
                    st.toast('Yapay zeka CV analizinizi tamamladı!', icon='🤖')

        if hedef_metni.strip():
            with st.spinner('Yapay zeka hedeflerinizi analiz ediyor...'):
                metin_yetkinlikler = metin_analiz_et(hedef_metni, yetkinlik_havuzu, api_key)

                if metin_yetkinlikler:
                    final_yetkinlikler = list(set(final_yetkinlikler + metin_yetkinlikler))
                    st.toast('Hedefleriniz analiz edildi!', icon='🎯')
        
        # CV ile form bilgileri uyuşmuyorsa NET bir uyarı mesajı bas (her durumda görünür)
        if cv_tutarlilik_notu:
            st.error(
                "❌ **Bilgi eşleşmedi!** Yüklediğiniz CV'deki bilgiler ile forma girdiğiniz "
                "bilgiler (ad soyad / okul / bölüm) örtüşmüyor.\n\n"
                f"**Uyuşmayan bilgi:** {cv_tutarlilik_notu}\n\n"
                "Lütfen form bilgilerinizi veya doğru CV'yi kontrol edip tekrar deneyin. "
                "Başvurunuz kaydedildi ancak İK ekibi tarafından ayrıca incelenecektir."
            )

        if final_yetkinlikler:
            st.snow()
            sonuclar_df = projeleri_eslestir(final_yetkinlikler, staj_gunu=staj_gunu)

            if sonuclar_df.empty:
                st.warning("Seçtiğiniz yetkinliklere uygun bir proje bulunamadı.")
            else:
                # Hata olsa bile projeleri listelemeye kaldığı yerden devam et
                bilgi_etiketi = lise_adi_nihai if egitim_seviyesi == "Lise" else nihai_bolum
                st.success(f"**{ad_soyad}** ({bilgi_etiketi}) için en uygun projeler:")
                st.dataframe(sonuclar_df, width="stretch")

                # 3. Başvuruyu veritabanına kaydet (Hata veren silinmiş kısım eklendi)
                en_iyi_satir = sonuclar_df.iloc[0]
                basvuru_kaydet(
                    ad_soyad, egitim_seviyesi, sinif, nihai_bolum, final_yetkinlikler, staj_gunu,
                    en_iyi_satir['departman'], en_iyi_satir['proje_adi'], en_iyi_satir['Uyum Puanı (%)'],
                    eposta=eposta, telefon=telefon, cv_tutarlilik_notu=cv_tutarlilik_notu,
                    lise_adi=lise_adi_nihai
                )
                st.toast(f"{ad_soyad} için başvuru geçmişe kaydedildi!", icon='📝')

                # 4. Seçilen projenin NEDEN seçildiğini DETAYLI açıklayan bilgilendirme notu
                with st.spinner('Bu projenin neden seçildiği değerlendiriliyor...'):
                    secim_gerekcesi = proje_secim_gerekcesi_olustur(
                        en_iyi_satir, final_yetkinlikler, ad_soyad, nihai_bolum,
                        sonuclar_df=sonuclar_df, staj_gunu=staj_gunu, key=api_key or None
                    )
                st.info(f"ℹ️ **Bu proje neden seçildi?**\n\n{secim_gerekcesi}")

                # 5. Stajyere seçilen proje + tarihli haftalık çalışma programını e-posta ile gönder
                if smtp_ayarlari and api_key:
                    with st.spinner('Yapay zeka size özel haftalık çalışma programı hazırlıyor ve e-posta gönderiyor...'):
                        program, program_kaynak = haftalik_program_olustur(
                            en_iyi_satir['proje_adi'], en_iyi_satir['departman'],
                            en_iyi_satir['aciklama'], final_yetkinlikler, staj_gunu, api_key
                        )
                        gonderildi, eposta_mesaji = staj_programi_eposta_gonder(
                            eposta, ad_soyad, en_iyi_satir['proje_adi'], en_iyi_satir['departman'],
                            en_iyi_satir['aciklama'],
                            secim_gerekcesi.replace("**", "").replace("*", ""),
                            program, smtp_ayarlari
                        )
                    if gonderildi:
                        st.success(f"📧 {eposta_mesaji}")
                        if program_kaynak == "varsayilan":
                            st.caption("ℹ️ Yapay zeka programı üretilemediği için genel bir şablon kullanıldı.")
                        with st.expander("Gönderilen haftalık çalışma programını görüntüle"):
                            for h in program:
                                st.markdown(
                                    f"**{h['hafta']}. Hafta** "
                                    f"({h['baslangic'].strftime('%d.%m.%Y')} - {h['bitis'].strftime('%d.%m.%Y')}) "
                                    f"— {h['baslik']}"
                                )
                                for g in h['gorevler']:
                                    st.markdown(f"- {g}")
                    else:
                        st.warning(f"📧 {eposta_mesaji}")
                elif not smtp_ayarlari:
                    st.caption("ℹ️ Çalışma programı e-postası gönderilemedi: sistemde SMTP ayarları tanımlı değil.")

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
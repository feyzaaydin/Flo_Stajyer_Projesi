import streamlit as st
import pandas as pd
import PyPDF2
from google import genai
import plotly.express as px
import io
import time
import re
import json
import difflib

from okullar import universiteler_listesi
from bolumler import bolumler_listesi
from liseler import liseler_listesi
from database import FLO_DEPARTMANLARI
from veritabani_islemleri import semayi_kontrol_et_ve_onar, basvuru_kaydet
from eposta_gonder import haftalik_program_olustur, staj_programi_eposta_gonder, GEMINI_MODEL

semayi_kontrol_et_ve_onar()

st.sidebar.image("flo.jpg", width="stretch")
st.sidebar.header("⚙️ Sistem.")

# API anahtarını önce güvenli sistem ayarlarından (.streamlit/secrets.toml) okumayı dene.
# Orada tanımlıysa kullanıcı her seferinde elle girmek zorunda kalmaz.
try:
    secrets_api_key = str(st.secrets["GEMINI_API_KEY"]).strip()
except Exception:
    secrets_api_key = ""


def _gecerli_anahtar_gorunumu(deger):
    """Google AI Studio API anahtarları 'AIza' ile başlar. 'AQ.' ile başlayan değer
    geçici bir OAuth oturum jetonudur ve generateContent çağrılarında 401 verir."""
    return bool(deger) and deger.startswith("AIza")


if _gecerli_anahtar_gorunumu(secrets_api_key):
    # Sistemde geçerli görünen bir anahtar var; kullanıcıya sormaya gerek yok.
    api_key = secrets_api_key
    st.sidebar.success("✅ API anahtarı sistemde kayıtlı, tekrar girmenize gerek yok.")
else:
    # Sistemdeki anahtar yok ya da geçersiz görünüyor: elle girme alanını aç.
    if secrets_api_key:
        st.sidebar.warning(
            "⚠️ secrets.toml içindeki GEMINI_API_KEY bir Google AI Studio API anahtarına "
            "benzemiyor ('AIza...' ile başlamalı). Geçerli bir anahtarı aşağıya "
            "yapıştırabilirsiniz; bu oturum için onu kullanır."
        )
    elle_girilen = st.sidebar.text_input(
        "Gemini API Anahtarı Girin (AIza...)", type="password"
    ).strip()
    api_key = elle_girilen or secrets_api_key
    st.sidebar.info(
        "Yapay zeka özellikleri için Google AI Studio'dan alınmış bir API anahtarı gerekir: "
        "https://aistudio.google.com/apikey"
    )

# Elle girilen anahtar da 'AIza' ile başlamıyorsa kullanıcıyı uyar (ama engelleme).
if api_key and not _gecerli_anahtar_gorunumu(api_key):
    st.sidebar.warning(
        "⚠️ Girilen değer 'AIza...' ile başlamıyor. 'AQ.' ile başlayan değerler "
        "geçici oturum jetonudur ve çalışmaz. Google Cloud Console > API'ler ve Hizmetler "
        "> Kimlik Bilgileri > API anahtarı oluştur adımıyla da kalıcı bir anahtar alabilirsiniz."
    )

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
    """CV'yi DERİNLEMESİNE analiz eder ve form bilgileriyle tutarlılığını kontrol eder.

    Dönüş: (yetkinlikler, tutarlilik_notu, cv_profili)
    cv_profili, projelerin sıfırdan üretilebilmesi için gereken zengin bilgiyi taşır:
    eğitim, teknik beceriler, programlama dilleri, teknolojiler, deneyimler,
    kişisel projeler, ilgi alanları, sektör deneyimi ve genel seviye.
    """
    bos_profil = {
        "egitim": "", "teknik_beceriler": [], "programlama_dilleri": [],
        "teknolojiler": [], "deneyimler": [], "projeler": [],
        "ilgi_alanlari": [], "sektor_deneyimi": [], "seviye": "",
    }

    prompt = f"""Sen SIFIR TOLERANSLI bir CV analiz ve doğrulama uzmanısın. İki görevin var.

GÖREV 1 - DERİN CV ANALİZİ:
CV'den şu bilgileri ÇIKAR (CV'de yoksa boş bırak, ASLA uydurma):
- egitim: bölüm ve okul bilgisi (tek cümle)
- teknik_beceriler: CV'de geçen teknik beceriler
- programlama_dilleri: CV'de geçen programlama dilleri
- teknolojiler: framework, kütüphane, araç, veritabanı, platform adları
- deneyimler: staj/iş deneyimleri ("Pozisyon - Şirket - süre" biçiminde kısa)
- projeler: CV'de anlatılan kişisel/okul projeleri (kısa başlık)
- ilgi_alanlari: adayın ilgi duyduğu alanlar
- sektor_deneyimi: varsa çalıştığı sektörler
- seviye: adayın genel yetkinlik seviyesi. SADECE şunlardan biri: "Başlangıç", "Orta", "İleri"

Ayrıca şu havuzdan eşleşen yetkinlikleri seç (SADECE bu havuzdaki kelimeler):
{', '.join(yetkinlikler)}

GÖREV 2 - BİLGİ TUTARLILIK KONTROLÜ:
Adayın forma girdiği bilgiler:
Ad Soyad: {form_ad_soyad}
Üniversite: {form_universite}
Bölüm: {form_bolum}
Sınıf: {form_sinif}

CV'deki bilgilerle formdaki bilgileri karşılaştır. Ad soyad, üniversite veya bölüm
AÇIKÇA farklıysa tutarli=false yaz ve hangi bilginin uyuşmadığını aciklama'ya yaz.
Uyumluysa tutarli=true, aciklama boş. Kesinlikle tahmin yapma.

CV Metni:
\"\"\"
{cv_metni[:6000]}
\"\"\"

SADECE şu JSON nesnesini döndür, başka hiçbir metin yazma:
{{
  "yetkinlikler": ["havuzdan eşleşen yetkinlikler"],
  "tutarli": true,
  "aciklama": "",
  "profil": {{
    "egitim": "",
    "teknik_beceriler": [],
    "programlama_dilleri": [],
    "teknolojiler": [],
    "deneyimler": [],
    "projeler": [],
    "ilgi_alanlari": [],
    "sektor_deneyimi": [],
    "seviye": "Orta"
  }}
}}"""

    for deneme in range(3):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            veri = _json_ayikla(response.text)
            if not isinstance(veri, dict):
                raise ValueError("JSON çözümlenemedi")

            # Modelin havuz dışına çıkmasını engelle
            ai_yetkinlikler = [
                str(y).strip() for y in (veri.get("yetkinlikler") or [])
                if str(y).strip() in yetkinlikler
            ]

            tutarlilik_notu = ""
            if veri.get("tutarli") is False:
                tutarlilik_notu = str(veri.get("aciklama", "")).strip()
                # AI 'tutarsız' deyip açıklama boş bıraktıysa uyarı yine de görünsün
                if not tutarlilik_notu:
                    tutarlilik_notu = "CV'deki ad soyad / okul / bölüm bilgileri form bilgileriyle uyuşmuyor."

            profil = dict(bos_profil)
            gelen_profil = veri.get("profil") or {}
            if isinstance(gelen_profil, dict):
                for anahtar, varsayilan in bos_profil.items():
                    deger = gelen_profil.get(anahtar)
                    if isinstance(varsayilan, list):
                        if isinstance(deger, str):
                            deger = re.split(r";|,|\n", deger)
                        profil[anahtar] = [
                            str(d).strip(" -•\t") for d in (deger or []) if str(d).strip(" -•\t")
                        ]
                    elif deger:
                        profil[anahtar] = str(deger).strip()

            return ai_yetkinlikler, tutarlilik_notu, profil

        except Exception:
            if deneme < 2:
                time.sleep(3)
                continue
            return [], "", dict(bos_profil)

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
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            return [yetenek.strip() for yetenek in response.text.split(",") if yetenek.strip()]
        except Exception:
            if deneme < 2:
                time.sleep(3)
                continue
            else:
                return [] # Hata durumunda sistemi çökertmez, boş geçer

def _gemini_hata_mesaji(hata):
    """Gemini API hatalarını kullanıcıya anlaşılır Türkçe mesaja çevirir."""
    metin = str(hata)
    if "UNAUTHENTICATED" in metin or "401" in metin or "API key not valid" in metin \
            or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in metin or "API_KEY_INVALID" in metin:
        return (
            "Gemini API anahtarı geçersiz. Sistemdeki anahtar bir API anahtarı değil "
            "(geçici oturum jetonu olabilir). Google AI Studio'dan "
            "(https://aistudio.google.com/app/apikey) 'AIza...' ile başlayan bir anahtar alıp "
            ".streamlit/secrets.toml içindeki GEMINI_API_KEY değerini güncelleyin."
        )
    if "429" in metin or "RESOURCE_EXHAUSTED" in metin or "quota" in metin.lower():
        return "Gemini API kullanım kotası doldu. Bir süre sonra tekrar deneyin."
    if "404" in metin or "not found" in metin.lower() or "NOT_FOUND" in metin:
        return (f"'{GEMINI_MODEL}' modeline erişilemiyor. Anahtarınızın bu modele erişimi "
                "olmayabilir veya model adı değişmiş olabilir.")
    if "PERMISSION_DENIED" in metin or "403" in metin:
        return "Gemini API erişimi reddedildi (403). Anahtarın yetkileri kısıtlı olabilir."
    return f"Yapay zeka servisine ulaşılamadı ({metin[:200]})."


def _json_ayikla(ham_metin):
    """Model cevabından JSON nesnesi/dizisi çıkarır (```json çitlerini temizler)."""
    metin = (ham_metin or "").strip()
    metin = re.sub(r"^```(?:json)?|```$", "", metin, flags=re.MULTILINE).strip()

    # Önce metnin tamamını çözmeyi dene: dizi/nesne yapısı olduğu gibi korunur.
    try:
        return json.loads(metin)
    except ValueError:
        pass

    # Olmazsa metnin içine gömülü ilk dizi ya da nesneyi yakala.
    for desen in (r"\[.*\]", r"\{.*\}"):
        eslesme = re.search(desen, metin, flags=re.DOTALL)
        if eslesme:
            try:
                return json.loads(eslesme.group(0))
            except ValueError:
                continue
    return None


def _benzer_mi(metin_a, metin_b, esik=0.72):
    """İki proje adının/açıklamasının birbirinin kopyası sayılıp sayılmayacağını ölçer."""
    a = _sadelestir(metin_a).strip()
    b = _sadelestir(metin_b).strip()
    if not a or not b:
        return False
    if a == b:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= esik


def _projeyi_normalize_et(ham_proje, aday_anahtar_kelimeleri):
    """AI'dan gelen tek bir proje sözlüğünü doğrular ve standart yapıya çevirir.
    Geçersiz ya da CV ile alakasızsa None döner."""
    if not isinstance(ham_proje, dict):
        return None

    def _metin(anahtar, varsayilan=""):
        return str(ham_proje.get(anahtar, varsayilan) or "").strip()

    def _liste(anahtar):
        deger = ham_proje.get(anahtar) or []
        if isinstance(deger, str):
            deger = re.split(r";|\n|,", deger)
        return [str(d).strip(" -•\t") for d in deger if str(d).strip(" -•\t")]

    proje_adi = _metin("proje_adi")
    aciklama = _metin("aciklama")
    if not proje_adi or not aciklama:
        return None

    # Departman FLO'nun gerçek organizasyon şemasında olmalı; uydurma isim kabul edilmez.
    departman = _metin("departman")
    if departman not in FLO_DEPARTMANLARI:
        eslesen = [d for d in FLO_DEPARTMANLARI if _sadelestir(d) == _sadelestir(departman)]
        departman = eslesen[0] if eslesen else "Belirtilmedi (İK ile görüşülmeli)"

    zorluk = _metin("zorluk_seviyesi", "Orta")
    if zorluk not in ("Başlangıç", "Orta", "İleri"):
        zorluk = "Orta"

    try:
        uyum_puani = round(float(ham_proje.get("uyum_puani", 0)), 2)
    except (TypeError, ValueError):
        uyum_puani = 0.0
    uyum_puani = max(0.0, min(100.0, uyum_puani))

    teknolojiler = _liste("teknolojiler")
    kazanilacak = _liste("kazanilacak_beceriler")
    kapsam = _liste("kapsam")

    # ALAKA KONTROLÜ: proje, adayın CV'sinden gelen en az bir anahtar kelimeye
    # (yetkinlik / dil / teknoloji) dokunmalı. Aksi halde "genel proje" sayılıp elenir.
    proje_metni = _sadelestir(" ".join(
        [proje_adi, aciklama, _metin("amac"), _metin("uygunluk_gerekcesi")]
        + teknolojiler + kazanilacak + kapsam
    ))
    alakali = any(
        anahtar and _sadelestir(anahtar) in proje_metni
        for anahtar in aday_anahtar_kelimeleri
    )
    if not alakali:
        return None

    return {
        "proje_adi": proje_adi,
        "departman": departman,
        "aciklama": aciklama,
        "amac": _metin("amac"),
        "uygunluk_gerekcesi": _metin("uygunluk_gerekcesi"),
        "teknolojiler": teknolojiler,
        "zorluk_seviyesi": zorluk,
        "kapsam": kapsam,
        "kazanilacak_beceriler": kazanilacak,
        "uyum_puani": uyum_puani,
    }


MAKSIMUM_PROJE_SAYISI = 3


def cv_ye_ozel_projeler_uret(cv_profili, final_yetkinlikler, ad_soyad, bolum,
                             egitim_seviyesi, sinif, staj_gunu, hedef_metni, key):
    """Adayın CV'sine özel, SIFIRDAN 1-3 proje fikri üretir.

    Hazır proje havuzu KULLANILMAZ; her öneri bu adayın profilinden türetilir.
    Dönüş: (projeler_listesi, hata_mesaji)
    """
    profil = cv_profili or {}
    diller = profil.get("programlama_dilleri", [])
    teknolojiler = profil.get("teknolojiler", [])
    teknik = profil.get("teknik_beceriler", [])
    deneyimler = profil.get("deneyimler", [])
    cv_projeleri = profil.get("projeler", [])
    ilgi = profil.get("ilgi_alanlari", [])
    sektor = profil.get("sektor_deneyimi", [])
    seviye = profil.get("seviye") or "Orta"

    # Alaka kontrolünde kullanılacak anahtar kelimeler
    aday_anahtar_kelimeleri = [
        k for k in (list(final_yetkinlikler) + diller + teknolojiler + teknik + ilgi + sektor)
        if len(str(k).strip()) >= 3
    ]
    if not aday_anahtar_kelimeleri and bolum and bolum != "-":
        aday_anahtar_kelimeleri = [bolum]

    hafta_sayisi = max(1, round(int(staj_gunu) / 7)) if staj_gunu else 4

    def _satir(baslik, deger):
        if isinstance(deger, list):
            deger = ", ".join(str(d) for d in deger)
        deger = str(deger or "").strip()
        return f"- {baslik}: {deger}\n" if deger else ""

    aday_ozeti = (
        _satir("Ad Soyad", ad_soyad)
        + _satir("Eğitim durumu", f"{egitim_seviyesi} / {sinif}")
        + _satir("Bölüm", bolum)
        + _satir("CV'den eğitim bilgisi", profil.get("egitim"))
        + _satir("Programlama dilleri", diller)
        + _satir("Teknolojiler / araçlar", teknolojiler)
        + _satir("Teknik beceriler", teknik)
        + _satir("Yetkinlikler", final_yetkinlikler)
        + _satir("Staj/iş deneyimleri", deneyimler)
        + _satir("CV'deki projeler", cv_projeleri)
        + _satir("İlgi alanları", ilgi)
        + _satir("Sektör deneyimi", sektor)
        + _satir("Genel seviye", seviye)
        + _satir("Adayın kendi hedef metni", (hedef_metni or "").strip()[:500])
    )

    departman_listesi_metni = "\n".join(f"- {d}" for d in FLO_DEPARTMANLARI)

    prompt = f"""Sen FLO ayakkabı ve spor perakende şirketinde stajyer projelerini TASARLAYAN
deneyimli bir İK/proje yöneticisisin. Hazır bir proje listesinden seçim YAPMIYORSUN;
bu adayın profiline özel, daha önce var olmayan proje fikirlerini SIFIRDAN tasarlıyorsun.

ADAYIN PROFİLİ:
{aday_ozeti}Staj süresi: {staj_gunu} gün (yaklaşık {hafta_sayisi} hafta)

GÖREV:
Bu adaya özel EN FAZLA {MAKSIMUM_PROJE_SAYISI} adet staj projesi fikri tasarla.

KURALLAR:
1. Proje sayısı 1, 2 veya 3 olabilir. Sadece gerçekten güçlü ve birbirinden farklı fikirler
   varsa 3 yaz; zorlama, doldurma proje URETME. Emin degilsen daha az proje oner.
2. Her proje bu adayın CV'sindeki SOMUT becerilere, dillere, teknolojilere veya deneyimlere
   doğrudan dayanmalı. "Python ile Veri Analizi Projesi" gibi genel/klişe başlıklar YASAK.
3. Projeler birbirinden BELİRGİN ŞEKİLDE FARKLI olmalı: farklı departman, farklı problem
   alanı, farklı çıktı türü. Aynı fikrin varyasyonlarını yazma.
4. Projeler FLO'nun gerçek iş yapısında (perakende, e-ticaret, ayakkabı/giyim ürün yönetimi,
   lojistik, pazarlama, mağazacılık) uygulanabilir olmalı.
5. Proje kapsamı {staj_gunu} günlük ({hafta_sayisi} hafta) bir stajda bitirilebilir olmalı.
6. Adayın mevcut becerilerini KULLANDIRMALI ama aynı zamanda 1-2 yeni beceri ÖĞRETMELİ.
7. departman alanına SADECE aşağıdaki listeden BİREBİR bir değer yaz:
{departman_listesi_metni}
8. uyum_puani: bu projenin adayın profiline uygunluğu (0-100 arası tam sayı). Gerçekçi ol.

SADECE şu JSON dizisini döndür, başka hiçbir metin yazma:
[
  {{
    "proje_adi": "spesifik ve özgün proje adı",
    "departman": "listeden birebir departman adı",
    "aciklama": "projenin 2-3 cümlelik açıklaması",
    "amac": "projenin FLO için amacı, 1-2 cümle",
    "uygunluk_gerekcesi": "bu projenin neden TAM OLARAK bu CV'ye uygun olduğu; adayın CV'sindeki somut beceri/deneyimlere isim vererek açıkla",
    "teknolojiler": ["kullanılacak teknoloji/araç/yöntem"],
    "zorluk_seviyesi": "Başlangıç veya Orta veya İleri",
    "kapsam": ["yapılabilecek temel özellik/aşama 1", "özellik 2", "özellik 3"],
    "kazanilacak_beceriler": ["bu projeyle gelişecek beceri 1", "beceri 2"],
    "uyum_puani": 85
  }}
]"""

    son_hata = "Yapay zeka şu anda size özel proje üretemedi."
    for deneme in range(3):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            veri = _json_ayikla(response.text)
            if isinstance(veri, dict):
                veri = veri.get("projeler") or [veri]
            if not isinstance(veri, list):
                raise ValueError("Beklenen JSON dizisi gelmedi")

            projeler = []
            for ham in veri:
                proje = _projeyi_normalize_et(ham, aday_anahtar_kelimeleri)
                if not proje:
                    continue
                # Birbirine çok benzeyen projeleri ele
                if any(
                    _benzer_mi(proje["proje_adi"], mevcut["proje_adi"])
                    or _benzer_mi(proje["aciklama"], mevcut["aciklama"], esik=0.80)
                    for mevcut in projeler
                ):
                    continue
                projeler.append(proje)
                # KOD SEVİYESİNDE ÜST SINIR
                if len(projeler) >= MAKSIMUM_PROJE_SAYISI:
                    break

            if projeler:
                projeler.sort(key=lambda p: p["uyum_puani"], reverse=True)
                return projeler[:MAKSIMUM_PROJE_SAYISI], ""

            son_hata = ("Yapay zeka üretilen proje fikirlerini CV'nizle yeterince ilişkili bulmadı. "
                        "Daha ayrıntılı bir CV yükleyip ya da hedeflerinizi yazıp tekrar deneyin.")
        except Exception as hata:
            son_hata = _gemini_hata_mesaji(hata)
            # Kimlik doğrulama / erişim hatalarında tekrar denemek anlamsız
            if any(k in str(hata) for k in ("UNAUTHENTICATED", "401", "403",
                                            "PERMISSION_DENIED", "API_KEY_INVALID")):
                return [], son_hata

        if deneme < 2:
            time.sleep(2)

    return [], son_hata


def proje_secim_gerekcesi_olustur(secilen_proje, aday_yetkinlikler, ad_soyad, bolum,
                                  tum_projeler=None, staj_gunu=None, cv_profili=None, key=None):
    """Üretilen ana projenin neden bu adaya özel tasarlandığını DETAYLI açıklar."""
    profil = cv_profili or {}
    proje_adi = secilen_proje["proje_adi"]
    departman = secilen_proje["departman"]
    aciklama = secilen_proje["aciklama"]
    teknolojiler = secilen_proje.get("teknolojiler", [])
    kazanilacak = secilen_proje.get("kazanilacak_beceriler", [])
    kapsam = secilen_proje.get("kapsam", [])
    puan = secilen_proje.get("uyum_puani", 0)
    zorluk = secilen_proje.get("zorluk_seviyesi", "Orta")

    aday_havuzu = set(
        list(aday_yetkinlikler)
        + profil.get("programlama_dilleri", [])
        + profil.get("teknolojiler", [])
        + profil.get("teknik_beceriler", [])
    )
    mevcut_olanlar = [t for t in teknolojiler if t in aday_havuzu]
    ogrenilecekler = [t for t in teknolojiler if t not in aday_havuzu]

    # --- Deterministik taban metin (yapay zeka olmasa da anlamlı) ---
    taban = (
        f"**{proje_adi}** — *{departman}*\n\n"
        f"**Bu proje sizin için sıfırdan tasarlandı.** Hazır bir proje havuzundan seçilmedi; "
        f"CV'nizdeki eğitim bilgisi, teknik beceriler, deneyimler ve ilgi alanları okunarak "
        f"size özel üretildi. Profil uygunluğu: **%{puan}**, zorluk seviyesi: **{zorluk}**.\n\n"
        f"**Neden bu proje size uygun:** {secilen_proje.get('uygunluk_gerekcesi') or aciklama}\n\n"
    )
    if secilen_proje.get("amac"):
        taban += f"**Projenin amacı:** {secilen_proje['amac']}\n\n"
    if mevcut_olanlar:
        taban += (
            f"**Hâlihazırda kullanabileceğiniz birikim:** {', '.join(mevcut_olanlar)}. "
            f"Bu proje bu birikimi ilk günden üretime dönüştürmenizi sağlıyor.\n\n"
        )
    if ogrenilecekler:
        taban += (
            f"**Staj boyunca yeni öğrenecekleriniz:** {', '.join(ogrenilecekler)}. "
            f"Bunlar mentor desteğiyle uygulamalı olarak kazandırılacak.\n\n"
        )
    if kazanilacak:
        taban += f"**Bu projeyle gelişecek beceriler:** {', '.join(kazanilacak)}.\n\n"
    if tum_projeler and len(tum_projeler) > 1:
        digerleri = [p["proje_adi"] for p in tum_projeler if p["proje_adi"] != proje_adi]
        taban += (
            f"**Neden diğer önerilerden önce bu?** Size özel toplam {len(tum_projeler)} proje "
            f"üretildi ({', '.join(digerleri)}). Bu proje profil uygunluğu en yüksek olan "
            f"(%{puan}) öneri olduğu için ana öneri olarak sunuldu; diğerleri de sizin için "
            f"tasarlanmış geçerli alternatiflerdir.\n\n"
        )
    taban += f"**Proje kapsamı:** {aciklama}"

    if not key:
        return taban

    prompt = f"""Sen FLO'da stajyer yerleştirmesi yapan bir İK uzmanısın. Aşağıdaki proje, bu adayın
CV'sine özel olarak SIFIRDAN tasarlandı (hazır bir havuzdan seçilmedi). Bunu adaya hitap eden,
açık ve motive edici bir "Bu proje neden size özel tasarlandı?" açıklamasına dönüştür.

Aday: {ad_soyad} ({bolum})
Adayın yetkinlikleri: {', '.join(aday_yetkinlikler) or 'belirtilmemiş'}
CV'den programlama dilleri: {', '.join(profil.get('programlama_dilleri', [])) or 'yok'}
CV'den teknolojiler: {', '.join(profil.get('teknolojiler', [])) or 'yok'}
CV'den deneyimler: {', '.join(profil.get('deneyimler', [])) or 'yok'}
Adayın seviyesi: {profil.get('seviye') or 'Orta'}
Staj süresi: {staj_gunu} gün

Tasarlanan proje: {proje_adi} ({departman})
Açıklama: {aciklama}
Amaç: {secilen_proje.get('amac', '')}
Uygunluk gerekçesi: {secilen_proje.get('uygunluk_gerekcesi', '')}
Kullanılacak teknolojiler: {', '.join(teknolojiler) or 'belirtilmemiş'}
Zorluk seviyesi: {zorluk}
Kapsam: {'; '.join(kapsam) or 'belirtilmemiş'}
Kazandıracağı beceriler: {', '.join(kazanilacak) or 'belirtilmemiş'}
Profil uygunluğu: %{puan}
Üretilen toplam alternatif sayısı: {len(tum_projeler) if tum_projeler else 1}

Açıklama şu 5 başlığı içersin (markdown ** ile kalın başlıklar, her başlık 2-3 cümle):
1. **Neden bu proje size özel tasarlandı?** — CV'nizdeki hangi somut bilgilerden yola çıkıldı
2. **Hangi becerileriniz işe yarayacak?** — mevcut becerileri projedeki somut görevlerle eşleştir
3. **Bu stajda ne öğreneceksiniz?** — yeni teknolojiler ve kazanılacak beceriler
4. **Zorluk ve kapsam** — seviyenize göre neden bu ölçekte tasarlandığı
5. **Beklentiler** — stajın sonunda ortaya çıkması beklenen somut çıktı

Toplam 220-320 kelime. Uydurma bilgi ekleme, sadece verilenleri yorumla."""

    for _ in range(2):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            metin = response.text.strip()
            if len(metin) > 120:
                return metin
        except Exception:
            pass
    return taban


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
        cv_profili = {}

        if yuklenen_cv:
            with st.spinner('Yapay zeka CV\'nizi okuyup form bilgilerinizle karşılaştırıyor...'):
                cv_metni = pdf_metin_cikar(yuklenen_cv)
                ai_yetkinlikler, cv_tutarlilik_notu, cv_profili = cv_analiz_ve_dogrulama_yap(
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

        # --- CV'ye ÖZEL PROJE ÜRETİMİ (hazır proje havuzu kullanılmaz) ---
        if not api_key:
            st.error(
                "Size özel proje üretebilmek için sol menüden Gemini API anahtarını girmelisiniz. "
                "Projeler artık hazır bir listeden seçilmiyor, yapay zeka tarafından üretiliyor."
            )
            st.stop()

        with st.spinner('Yapay zeka CV\'nize özel proje fikirleri tasarlıyor...'):
            uretilen_projeler, uretim_hatasi = cv_ye_ozel_projeler_uret(
                cv_profili, final_yetkinlikler, ad_soyad, nihai_bolum,
                egitim_seviyesi, sinif, staj_gunu, hedef_metni, api_key
            )

        if not uretilen_projeler:
            st.warning(
                f"⚠️ {uretim_hatasi}\n\n"
                "İpucu: CV'nizde teknik becerileriniz, kullandığınız teknolojiler ve "
                "deneyimleriniz ne kadar açık yazılırsa öneriler o kadar isabetli olur."
            )
        else:
            st.snow()
            ana_proje = uretilen_projeler[0]

            bilgi_etiketi = lise_adi_nihai if egitim_seviyesi == "Lise" else nihai_bolum
            st.success(
                f"**{ad_soyad}** ({bilgi_etiketi}) için yapay zeka tarafından sıfırdan tasarlanan "
                f"{len(uretilen_projeler)} proje önerisi:"
            )

            # 1) Üretilen projeleri kart olarak göster
            ZORLUK_RENKLERI = {"Başlangıç": "🟢", "Orta": "🟡", "İleri": "🔴"}
            for sira, proje in enumerate(uretilen_projeler, start=1):
                etiket = "⭐ Ana Öneri" if sira == 1 else f"Alternatif {sira - 1}"
                with st.container(border=True):
                    st.markdown(
                        f"#### {etiket} — {proje['proje_adi']}\n"
                        f"*{proje['departman']}*"
                    )
                    ust1, ust2 = st.columns(2)
                    ust1.metric("Profil Uygunluğu", f"%{proje['uyum_puani']:g}")
                    ust2.metric(
                        "Zorluk Seviyesi",
                        f"{ZORLUK_RENKLERI.get(proje['zorluk_seviyesi'], '⚪')} {proje['zorluk_seviyesi']}"
                    )

                    st.markdown(f"**📄 Açıklama:** {proje['aciklama']}")
                    if proje.get("amac"):
                        st.markdown(f"**🎯 Amaç:** {proje['amac']}")
                    if proje.get("uygunluk_gerekcesi"):
                        st.markdown(f"**🧩 Neden bu CV'ye uygun:** {proje['uygunluk_gerekcesi']}")
                    if proje.get("teknolojiler"):
                        st.markdown(f"**🛠️ Kullanılacak teknolojiler:** {', '.join(proje['teknolojiler'])}")

                    alt1, alt2 = st.columns(2)
                    with alt1:
                        if proje.get("kapsam"):
                            st.markdown("**📦 Kapsam / temel özellikler:**")
                            for madde in proje["kapsam"]:
                                st.markdown(f"- {madde}")
                    with alt2:
                        if proje.get("kazanilacak_beceriler"):
                            st.markdown("**📈 Geliştireceğiniz beceriler:**")
                            for beceri in proje["kazanilacak_beceriler"]:
                                st.markdown(f"- {beceri}")

            # 2) Başvuruyu veritabanına kaydet.
            # NOT: Üretilen projeler bir "proje havuzu" olarak SAKLANMIYOR. Sadece başvuru
            # geçmişi (stajyerler tablosu) için ana önerinin adı/departmanı/puanı yazılıyor;
            # Admin paneli bu kolonları listeliyor ve İK bu bilgi olmadan başvuruyu takip edemez.
            basvuru_kaydet(
                ad_soyad, egitim_seviyesi, sinif, nihai_bolum, final_yetkinlikler, staj_gunu,
                ana_proje['departman'], ana_proje['proje_adi'], ana_proje['uyum_puani'],
                eposta=eposta, telefon=telefon, cv_tutarlilik_notu=cv_tutarlilik_notu,
                lise_adi=lise_adi_nihai
            )
            st.toast(f"{ad_soyad} için başvuru geçmişe kaydedildi!", icon='📝')

            # 3) Ana projenin neden bu adaya tasarlandığını DETAYLI anlatan not
            with st.spinner('Bu projenin neden size özel tasarlandığı açıklanıyor...'):
                secim_gerekcesi = proje_secim_gerekcesi_olustur(
                    ana_proje, final_yetkinlikler, ad_soyad, nihai_bolum,
                    tum_projeler=uretilen_projeler, staj_gunu=staj_gunu,
                    cv_profili=cv_profili, key=api_key
                )
            st.info(f"ℹ️ **Bu proje neden seçildi?**\n\n{secim_gerekcesi}")

            # 4) Stajyere ana proje + tarihli haftalık çalışma programını e-posta ile gönder
            if smtp_ayarlari:
                with st.spinner('Yapay zeka size özel haftalık çalışma programı hazırlıyor ve e-posta gönderiyor...'):
                    program, program_kaynak = haftalik_program_olustur(
                        ana_proje['proje_adi'], ana_proje['departman'],
                        ana_proje['aciklama'], final_yetkinlikler, staj_gunu, api_key,
                        teknolojiler=ana_proje.get('teknolojiler')
                    )
                    gonderildi, eposta_mesaji = staj_programi_eposta_gonder(
                        eposta, ad_soyad, ana_proje['proje_adi'], ana_proje['departman'],
                        ana_proje['aciklama'],
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
            else:
                st.caption("ℹ️ Çalışma programı e-postası gönderilemedi: sistemde SMTP ayarları tanımlı değil.")

            # 5) Üretilen önerilerin özeti: tablo, grafikler ve indirilebilir rapor
            rapor_df = pd.DataFrame([
                {
                    "Proje Adı": p["proje_adi"],
                    "Departman": p["departman"],
                    "Profil Uygunluğu (%)": p["uyum_puani"],
                    "Zorluk": p["zorluk_seviyesi"],
                    "Açıklama": p["aciklama"],
                    "Amaç": p.get("amac", ""),
                    "Neden Uygun": p.get("uygunluk_gerekcesi", ""),
                    "Teknolojiler": ", ".join(p.get("teknolojiler", [])),
                    "Kapsam": " | ".join(p.get("kapsam", [])),
                    "Kazanılacak Beceriler": ", ".join(p.get("kazanilacak_beceriler", [])),
                }
                for p in uretilen_projeler
            ])

            with st.expander("📊 Önerilerin karşılaştırmalı özeti"):
                st.dataframe(rapor_df, width="stretch", hide_index=True)

                col1, col2 = st.columns(2)
                with col1:
                    fig_pie = px.pie(
                        rapor_df, values='Profil Uygunluğu (%)', names='Departman',
                        title="Önerilen Departman Dağılımı",
                        color_discrete_sequence=['#F25C05', '#1E1E1E', '#FF8A4C', '#D3D3D3']
                    )
                    st.plotly_chart(fig_pie, width="stretch", key="pie")
                with col2:
                    fig_bar = px.bar(
                        rapor_df, x='Proje Adı', y='Profil Uygunluğu (%)',
                        title="Projelerin Profil Uygunluğu",
                        color_discrete_sequence=['#F25C05']
                    )
                    st.plotly_chart(fig_bar, width="stretch", key="bar")

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                rapor_df.to_excel(writer, index=False, sheet_name='Proje Onerileri')

            dosya_adi = ad_soyad.replace(" ", "_")
            st.download_button(
                label="📥 Bu Raporu İndir (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"{dosya_adi}_proje_onerileri.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
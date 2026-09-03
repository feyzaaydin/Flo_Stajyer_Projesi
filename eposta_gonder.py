import smtplib
import ssl
import json
import re
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google import genai


def _hafta_sayisi(staj_gunu):
    """Staj gününü haftaya çevirir (en az 1 hafta)."""
    try:
        return max(1, round(int(staj_gunu) / 7))
    except (TypeError, ValueError):
        return 4


def _tarihlendir(program_satirlari, bugun):
    program = []
    for i, (baslik, gorevler) in enumerate(program_satirlari):
        baslangic = bugun + datetime.timedelta(days=7 * i)
        bitis = baslangic + datetime.timedelta(days=6)
        program.append({
            "hafta": i + 1,
            "baslik": baslik,
            "gorevler": gorevler,
            "baslangic": baslangic,
            "bitis": bitis,
        })
    return program


def _yapay_zeka_program_ayikla(ham_metin, hafta_sayisi):
    """Modelin döndürdüğü metinden hafta listesini çıkarır. Önce JSON, olmazsa
    'HAFTA n | başlık | görevler' satır formatı denenir."""
    metin = ham_metin.strip()
    # Olası ```json ... ``` çitlerini temizle
    metin = re.sub(r"^```(?:json)?|```$", "", metin, flags=re.MULTILINE).strip()

    # 1) JSON dizisi dene
    eslesme = re.search(r"\[.*\]", metin, flags=re.DOTALL)
    if eslesme:
        try:
            veri = json.loads(eslesme.group(0))
            satirlar = []
            for oge in veri:
                baslik = str(oge.get("baslik") or oge.get("title") or "").strip()
                ham_gorevler = oge.get("gorevler") or oge.get("tasks") or []
                if isinstance(ham_gorevler, str):
                    ham_gorevler = re.split(r";|\n", ham_gorevler)
                gorevler = [str(g).strip(" -•\t") for g in ham_gorevler if str(g).strip(" -•\t")]
                if baslik or gorevler:
                    satirlar.append((baslik or f"{len(satirlar) + 1}. Hafta", gorevler))
            if satirlar:
                return satirlar[:hafta_sayisi]
        except (ValueError, AttributeError):
            pass

    # 2) Satır formatı: "HAFTA 1 | başlık | görev; görev"
    satirlar = []
    for satir in metin.split("\n"):
        if "|" not in satir:
            continue
        parcalar = [p.strip() for p in satir.split("|")]
        if len(parcalar) < 3:
            continue
        baslik = re.sub(r"(?i)^\s*hafta\s*\d+\s*[:\-]?\s*", "", parcalar[1]).strip() or parcalar[1]
        gorevler = [g.strip(" -•\t") for g in re.split(r";|\n", parcalar[2]) if g.strip(" -•\t")]
        if gorevler:
            satirlar.append((baslik, gorevler))
    return satirlar[:hafta_sayisi]


def haftalik_program_olustur(proje_adi, departman, proje_aciklama, yetkinlikler, staj_gunu, key):
    """Yapay zeka ile projeye özel, haftalara bölünmüş bir çalışma programı üretir.

    Dönüş: (program, kaynak) — kaynak "ai" veya "varsayilan".
    program: [{'hafta','baslik','gorevler','baslangic','bitis'}, ...]
    """
    hafta_sayisi = _hafta_sayisi(staj_gunu)
    bugun = datetime.date.today()

    prompt = f"""Sen FLO ayakkabı ve spor perakende şirketinde stajyer yöneten deneyimli bir proje yöneticisisin.
Aşağıdaki SPESİFİK staj projesi için {hafta_sayisi} haftalık, birbirinden FARKLI ve projeye ÖZGÜ bir çalışma programı hazırla.

Proje adı: {proje_adi}
Departman: {departman}
Proje açıklaması: {proje_aciklama}
Stajyerin yetkinlikleri: {', '.join(yetkinlikler)}

KURALLAR:
- Her haftanın başlığı ve görevleri BİRBİRİNDEN FARKLI olmalı; "haftalık hedef belirleme, görevleri yürütme, ilerleme raporu" gibi genel/tekrarlayan ifadeler KULLANMA.
- Görevler doğrudan bu projenin açıklamasındaki işe (veri, analiz, tasarım, saha, sunum vb.) atıfta bulunsun.
- 1. hafta: oryantasyon + veri/kaynak toplama. Orta haftalar: analiz/üretim/uygulama. Son hafta: sonuç, rapor ve sunum.
- Her hafta 3-4 somut görev.

SADECE şu JSON dizisini döndür, başka hiçbir metin yazma:
[
  {{"baslik": "1. haftanın kısa başlığı", "gorevler": ["görev 1", "görev 2", "görev 3"]}},
  ... toplam {hafta_sayisi} hafta ...
]"""

    for _ in range(2):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
            satirlar = _yapay_zeka_program_ayikla(response.text, hafta_sayisi)
            if len(satirlar) >= max(1, hafta_sayisi - 1):
                return _tarihlendir(satirlar, bugun), "ai"
        except Exception:
            pass

    # Yapay zeka başarısız olursa: en azından haftaları birbirinden farklı kılan varsayılan
    kaba_asamalar = [
        ("Oryantasyon ve Kaynak Toplama",
         [f"{departman} ekibiyle tanışma ve proje hedeflerinin netleştirilmesi",
          f"'{proje_adi}' için gerekli veri, doküman ve araçların toplanması",
          "Benzer çalışmaların ve sektör örneklerinin incelenmesi"]),
        ("Mevcut Durum Analizi",
         [f"Toplanan verilerin '{proje_adi}' kapsamında düzenlenmesi ve incelenmesi",
          "Öne çıkan bulguların ve sorun alanlarının çıkarılması",
          "Mentor ile ara değerlendirme"]),
        ("Geliştirme ve Uygulama",
         [f"{proje_aciklama[:80].strip()}... doğrultusunda çözüm/çıktı üretilmesi",
          "Üretilen çıktının test edilmesi ve revize edilmesi",
          "Ekipten geri bildirim alınması"]),
        ("Detaylandırma ve İyileştirme",
         ["Çıktının eksik yönlerinin tamamlanması",
          "İkinci tur test ve doğrulama",
          "Sonuç metriklerinin derlenmesi"]),
        ("Raporlama ve Sunum",
         [f"'{proje_adi}' sonuçlarının rapor haline getirilmesi",
          "Sunum dosyasının hazırlanması",
          f"{departman} ekibine final sunumu"]),
    ]
    if hafta_sayisi <= len(kaba_asamalar):
        secilen = kaba_asamalar[:hafta_sayisi - 1] + [kaba_asamalar[-1]] if hafta_sayisi >= 2 else kaba_asamalar[:1]
    else:
        orta = kaba_asamalar[2]
        secilen = kaba_asamalar[:2] + [
            (f"Uygulama Aşaması {i}", [g for g in orta[1]]) for i in range(1, hafta_sayisi - 2)
        ] + [kaba_asamalar[-1]]
    return _tarihlendir(secilen[:hafta_sayisi], bugun), "varsayilan"


def _program_html(program):
    satirlar = ""
    for h in program:
        gorev_ler = "".join(f"<li>{g}</li>" for g in h["gorevler"])
        satirlar += f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;white-space:nowrap;vertical-align:top;">
            <b>{h['hafta']}. Hafta</b><br>
            <span style="color:#666;font-size:12px;">
              {h['baslangic'].strftime('%d.%m.%Y')} - {h['bitis'].strftime('%d.%m.%Y')}
            </span>
          </td>
          <td style="padding:8px;border:1px solid #ddd;vertical-align:top;">
            <b>{h['baslik']}</b>
            <ul style="margin:6px 0 0 18px;padding:0;">{gorev_ler}</ul>
          </td>
        </tr>"""
    return f"""
    <table style="border-collapse:collapse;width:100%;font-size:14px;">
      <thead>
        <tr style="background:#F25C05;color:#fff;">
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Tarih</th>
          <th style="padding:8px;border:1px solid #ddd;text-align:left;">Çalışma İçeriği</th>
        </tr>
      </thead>
      <tbody>{satirlar}</tbody>
    </table>"""


def _program_metin(program):
    parcalar = []
    for h in program:
        tarih = f"{h['baslangic'].strftime('%d.%m.%Y')} - {h['bitis'].strftime('%d.%m.%Y')}"
        gorevler = "\n".join(f"   - {g}" for g in h["gorevler"])
        parcalar.append(f"{h['hafta']}. Hafta ({tarih}) - {h['baslik']}\n{gorevler}")
    return "\n\n".join(parcalar)


def staj_programi_eposta_gonder(alici_eposta, ad_soyad, proje_adi, departman,
                                proje_aciklama, secim_gerekcesi, program, smtp_ayarlari):
    """Stajyere seçilen proje + haftalık çalışma programını e-posta ile gönderir.

    smtp_ayarlari: {'host','port','user','password','from'} sözlüğü.
    Dönüş: (basarili: bool, mesaj: str)
    """
    gerekli = ("host", "port", "user", "password")
    if not smtp_ayarlari or any(not smtp_ayarlari.get(k) for k in gerekli):
        return False, "E-posta gönderimi yapılandırılmamış (SMTP ayarları eksik)."

    gonderen = smtp_ayarlari.get("from") or smtp_ayarlari["user"]

    konu = f"FLO Stajyer Programınız - {proje_adi}"

    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#1E1E1E;max-width:640px;margin:auto;">
      <h2 style="color:#F25C05;">FLO Stajyer Başvuru Sonucunuz</h2>
      <p>Merhaba <b>{ad_soyad}</b>,</p>
      <p>Başvurunuz değerlendirildi ve yetkinliklerinize en uygun staj projesi belirlendi:</p>
      <div style="background:#f6f6f6;border-left:4px solid #F25C05;padding:12px 16px;margin:12px 0;">
        <b style="font-size:16px;">{proje_adi}</b><br>
        <span style="color:#666;">{departman}</span>
        <p style="margin:8px 0 0;">{proje_aciklama}</p>
      </div>
      <h3 style="color:#F25C05;">Bu proje neden seçildi?</h3>
      <p>{secim_gerekcesi}</p>
      <h3 style="color:#F25C05;">Haftalık Çalışma Programınız</h3>
      {_program_html(program)}
      <p style="margin-top:16px;color:#666;font-size:12px;">
        Bu e-posta FLO Stajyer Başvuru Sistemi tarafından otomatik oluşturulmuştur.
      </p>
    </div>"""

    metin = (
        f"Merhaba {ad_soyad},\n\n"
        f"Başvurunuz değerlendirildi. Size en uygun staj projesi:\n\n"
        f"{proje_adi} ({departman})\n{proje_aciklama}\n\n"
        f"Bu proje neden seçildi?\n{secim_gerekcesi}\n\n"
        f"HAFTALIK ÇALIŞMA PROGRAMI\n\n{_program_metin(program)}\n\n"
        f"FLO Stajyer Başvuru Sistemi"
    )

    mesaj = MIMEMultipart("alternative")
    mesaj["Subject"] = konu
    mesaj["From"] = gonderen
    mesaj["To"] = alici_eposta
    mesaj.attach(MIMEText(metin, "plain", "utf-8"))
    mesaj.attach(MIMEText(html, "html", "utf-8"))

    port = int(smtp_ayarlari["port"])
    try:
        if port == 465:
            baglam = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_ayarlari["host"], port, context=baglam) as sunucu:
                sunucu.login(smtp_ayarlari["user"], smtp_ayarlari["password"])
                sunucu.send_message(mesaj)
        else:
            with smtplib.SMTP(smtp_ayarlari["host"], port) as sunucu:
                sunucu.starttls(context=ssl.create_default_context())
                sunucu.login(smtp_ayarlari["user"], smtp_ayarlari["password"])
                sunucu.send_message(mesaj)
        return True, f"Çalışma programı {alici_eposta} adresine gönderildi."
    except Exception as e:
        return False, f"E-posta gönderilemedi: {e}"

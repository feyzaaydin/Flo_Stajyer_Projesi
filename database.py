import sqlite3

# FLO'nun gerçek organizasyon şemasındaki departmanlar (GMY = Genel Müdür Yardımcılığı).
# Tüm proje atamaları ve eşleştirmeler SADECE bu listedeki departmanlara göre yapılır.
FLO_DEPARTMANLARI = [
    "AYAKKABI ÜRÜN YÖNETİMİ GENEL MÜDÜR YRD.",
    "BİLGİ TEKNOLOJİLERİ GMY",
    "CEO YARDIMCILIĞI (MALİ İŞLER, İK, LOJİSTİK, İÇ DENETİM)",
    "E-TİCARET, ALTERNATİF SATIŞ KANALLARI VE PLANLAMA GMY",
    "FLO TÜRKİYE PERAKENDE GMY",
    "GİYİM & AKSESUAR ÜRÜN YÖNETİMİ GMY",
    "GLOBAL İŞ GELİŞTİRME VE STRATEJİ GMY",
    "IN STREET VE MONOBRAND GENEL MÜDÜR YARD.",
    "KATEGORİ YÖNETİMİ GENEL MÜDÜR YRD.",
    "PAZARLAMA VE BÜYÜME GENEL MÜDÜR YARD.",
    "TEDARİK OPERASYONLARI GENEL MÜDÜR YARD.",
    "YURT DIŞI SATIŞ KANALLARI GMY",
]

def veritabani_olustur():
    conn = sqlite3.connect('flo_stajyer.db')
    c = conn.cursor()

    # NOT: Sabit 'projeler' havuzu KALDIRILDI. Projeler artık başvuru anında
    # yapay zeka tarafından adayın CV'sine özel olarak üretiliyor
    # (bkz. basvuru_formu.py -> cv_ye_ozel_projeler_uret). Eski kurulumlarda kalmış
    # olabilecek tabloyu temizliyoruz.
    c.execute('DROP TABLE IF EXISTS projeler')

    # stajyerler tablosu DROP edilmiyor: database.py tekrar çalıştırılsa bile
    # birikmiş başvuru geçmişi silinmesin diye IF NOT EXISTS kullanılıyor.
    c.execute('''
        CREATE TABLE IF NOT EXISTS stajyerler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_soyad TEXT,
            egitim_seviyesi TEXT,
            sinif TEXT,
            bolum TEXT,
            yetkinlikler TEXT,
            staj_gunu INTEGER,
            en_uygun_departman TEXT,
            en_uygun_proje TEXT,
            uyum_puani REAL,
            basvuru_tarihi TEXT,
            dogrulanmamis_yetkinlikler TEXT,
            cv_tutarlilik_notu TEXT,
            eposta TEXT,
            telefon TEXT,
            durum TEXT
        )
    ''')

    # MİGRASYON: Tablo daha önce eski şemayla oluşturulmuş olabilir
    # (en_uygun_departman, en_uygun_proje, uyum_puani, basvuru_tarihi, doğrulama kolonları olmadan).
    # Var olan veriyi silmeden eksik kolonları sonradan ekliyoruz.
    c.execute("PRAGMA table_info(stajyerler)")
    mevcut_kolonlar = [satir[1] for satir in c.fetchall()]

    eklenecek_kolonlar = {
        "en_uygun_departman": "TEXT",
        "en_uygun_proje": "TEXT",
        "uyum_puani": "REAL",
        "basvuru_tarihi": "TEXT",
        "dogrulanmamis_yetkinlikler": "TEXT",
        "cv_tutarlilik_notu": "TEXT",
        "eposta": "TEXT",
        "telefon": "TEXT",
        "durum": "TEXT",
        "lise_adi": "TEXT"
    }

    for kolon, tip in eklenecek_kolonlar.items():
        if kolon not in mevcut_kolonlar:
            c.execute(f"ALTER TABLE stajyerler ADD COLUMN {kolon} {tip}")
            print(f"Migrasyon: '{kolon}' kolonu stajyerler tablosuna eklendi.")

    # Durum bilgisi olmayan (eski) kayıtlara varsayılan durum ata
    c.execute("UPDATE stajyerler SET durum = 'Beklemede' WHERE durum IS NULL OR durum = ''")
    
    conn.commit()
    conn.close()
    print("Veritabanı hazır: stajyerler tablosu oluşturuldu/güncellendi. "
          "Sabit proje havuzu kullanılmıyor; projeler yapay zeka ile üretiliyor.")

if __name__ == "__main__":
    veritabani_olustur()
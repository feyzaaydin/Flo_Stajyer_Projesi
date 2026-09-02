import sqlite3
import datetime
import pandas as pd


def semayi_kontrol_et_ve_onar():
    """stajyerler tablosu eski şemayla oluşturulmuş olabilir; eksik kolonları
    veri kaybı olmadan sonradan ekler. Tablo hiç yoksa dokunmaz (database.py
    çalıştırılmalı)."""
    conn = sqlite3.connect('flo_stajyer.db')
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stajyerler'")
    if c.fetchone():
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
            "durum": "TEXT"
        }
        for kolon, tip in eklenecek_kolonlar.items():
            if kolon not in mevcut_kolonlar:
                c.execute(f"ALTER TABLE stajyerler ADD COLUMN {kolon} {tip}")
        c.execute("UPDATE stajyerler SET durum = 'Beklemede' WHERE durum IS NULL OR durum = ''")
        conn.commit()
    conn.close()


def basvuru_kaydet(ad_soyad, egitim_seviyesi, sinif, bolum, yetkinlikler_listesi, staj_gunu,
                    en_uygun_departman, en_uygun_proje, uyum_puani,
                    eposta="", telefon="", dogrulanmamis_yetkinlikler=None, cv_tutarlilik_notu=""):
    conn = sqlite3.connect('flo_stajyer.db')
    c = conn.cursor()
    tarih = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dogrulanmamis_str = ", ".join(dogrulanmamis_yetkinlikler) if dogrulanmamis_yetkinlikler else ""
    c.execute('''
        INSERT INTO stajyerler
            (ad_soyad, egitim_seviyesi, sinif, bolum, yetkinlikler, staj_gunu,
             en_uygun_departman, en_uygun_proje, uyum_puani, basvuru_tarihi,
             dogrulanmamis_yetkinlikler, cv_tutarlilik_notu, eposta, telefon, durum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ad_soyad, egitim_seviyesi, sinif, bolum, ", ".join(yetkinlikler_listesi), staj_gunu,
          en_uygun_departman, en_uygun_proje, uyum_puani, tarih,
          dogrulanmamis_str, cv_tutarlilik_notu, eposta, telefon, "Beklemede"))
    conn.commit()
    conn.close()


def durum_guncelle(basvuru_id, yeni_durum):
    conn = sqlite3.connect('flo_stajyer.db')
    c = conn.cursor()
    c.execute("UPDATE stajyerler SET durum = ? WHERE id = ?", (yeni_durum, int(basvuru_id)))
    conn.commit()
    conn.close()


def gecmis_basvurulari_getir():
    conn = sqlite3.connect('flo_stajyer.db')
    df = pd.read_sql_query('''
        SELECT id AS "ID", ad_soyad AS "Ad Soyad", eposta AS "E-posta", telefon AS "Telefon",
               bolum AS "Bölüm", egitim_seviyesi AS "Eğitim",
               sinif AS "Sınıf", en_uygun_departman AS "Önerilen Departman",
               en_uygun_proje AS "Önerilen Proje", uyum_puani AS "Uyum Puanı (%)",
               cv_tutarlilik_notu AS "CV Tutarlılık Notu", durum AS "Durum",
               basvuru_tarihi AS "Başvuru Tarihi"
        FROM stajyerler
        ORDER BY id DESC
    ''', conn)
    conn.close()
    return df
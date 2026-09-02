import sqlite3

# Veritabanına bağlan
conn = sqlite3.connect('flo_stajyer.db')
c = conn.cursor()

# İnsan Kaynakları projelerini sadece sosyal/yönetimsel kelimelerle güncelle
c.execute("""
    UPDATE projeler 
    SET aranan_yetkinlikler = 'İletişim, Liderlik, İşe Alım, Takım Çalışması, Excel, Performans Yönetimi' 
    WHERE departman = 'İnsan Kaynakları'
""")

# Bilgi Teknolojileri projelerini sadece sert/teknik kelimelerle güncelle
c.execute("""
    UPDATE projeler 
    SET aranan_yetkinlikler = 'Python, SQL, React, Node.js, Veri Analizi, API, Makine Öğrenmesi' 
    WHERE departman = 'Bilgi Teknolojileri'
""")

# Dijital Pazarlama gibi diğer departmanları da düzeltebiliriz
c.execute("""
    UPDATE projeler 
    SET aranan_yetkinlikler = 'SEO, Sosyal Medya, İçerik Üretimi, E-Ticaret, Pazarlama' 
    WHERE departman = 'Dijital Pazarlama'
""")

# Değişiklikleri kaydet ve kapat
conn.commit()
conn.close()

print("✅ Veritabanı başarıyla güncellendi ve etiketler temizlendi!")
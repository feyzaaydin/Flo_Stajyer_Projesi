# ARTIK KULLANILMIYOR (deprecated)
#
# Bu betik, eskiden veritabanında tutulan sabit 'projeler' havuzundaki
# 'aranan_yetkinlikler' etiketlerini toplu güncellemek için yazılmıştı.
#
# Sistem mimarisi değişti: sabit proje havuzu tamamen kaldırıldı. Projeler artık
# başvuru anında, adayın CV'sine özel olarak yapay zeka tarafından üretiliyor
# (bkz. basvuru_formu.py -> cv_ye_ozel_projeler_uret). 'projeler' tablosu artık
# oluşturulmuyor, dolayısıyla bu betiğin güncelleyebileceği bir veri yok.
#
# Dosya, geçmişe referans olsun diye silinmedi; çalıştırıldığında sadece uyarı verir.

print(
    "⚠️  Bu betik artık kullanılmıyor.\n"
    "    Sabit proje havuzu ('projeler' tablosu) kaldırıldı; projeler yapay zeka\n"
    "    tarafından her başvuru için CV'ye özel olarak üretiliyor.\n"
    "    Veritabanı şemasını hazırlamak için: python database.py"
)

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

    c.execute('DROP TABLE IF EXISTS projeler')

    # PROJELER TABLOSU (min_staj_gunu sütunu eklendi)
    c.execute('''
        CREATE TABLE projeler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proje_adi TEXT,
            departman TEXT,
            aranan_yetkinlikler TEXT,
            aciklama TEXT,
            min_staj_gunu INTEGER
        )
    ''')

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
        "durum": "TEXT"
    }

    for kolon, tip in eklenecek_kolonlar.items():
        if kolon not in mevcut_kolonlar:
            c.execute(f"ALTER TABLE stajyerler ADD COLUMN {kolon} {tip}")
            print(f"Migrasyon: '{kolon}' kolonu stajyerler tablosuna eklendi.")

    # Durum bilgisi olmayan (eski) kayıtlara varsayılan durum ata
    c.execute("UPDATE stajyerler SET durum = 'Beklemede' WHERE durum IS NULL OR durum = ''")
    
    # Her proje FLO_DEPARTMANLARI listesindeki gerçek bir departmana bağlanır.
    # Her departmana birden fazla proje verilerek eşleştirmenin tek bir projeye
    # bağımlı kalması (çok "bağımsız"/dağınık olması) engellenir.
    yeni_projeler = [
        # AYAKKABI ÜRÜN YÖNETİMİ GENEL MÜDÜR YRD.
        ("Ayakkabı Trend ve Rakip Analizi", "AYAKKABI ÜRÜN YÖNETİMİ GENEL MÜDÜR YRD.", "Tasarım, Analitik Düşünme, Araştırma",
         "Yurt içi ve yurt dışındaki rakip markaların (spor, günlük, klasik ayakkabı segmentlerinde) yeni sezon koleksiyonları taranarak "
         "öne çıkan renk, kalıp ve materyal trendleri belirlenir. Sosyal medya ve moda platformlarından görsel referanslar toplanır, "
         "bulgular ürün yönetimi ekibine bir trend raporu ve sunum halinde aktarılır.", 20),
        ("Sezonluk Koleksiyon Performans Raporu", "AYAKKABI ÜRÜN YÖNETİMİ GENEL MÜDÜR YRD.", "Excel, Veri Analizi, Raporlama",
         "Geçmiş sezonlara ait satış verileri Excel üzerinde derlenerek hangi ürün gruplarının, renklerin ve numaraların en çok "
         "sattığı analiz edilir. Stokta kalan/az satan ürünler tespit edilip, bir sonraki sezon koleksiyon kararlarına girdi "
         "olacak bir performans raporu hazırlanır.", 30),

        # BİLGİ TEKNOLOJİLERİ GMY
        ("Stok Takip Otomasyonu", "BİLGİ TEKNOLOJİLERİ GMY", "Python, SQL, Problem Çözme",
         "Mağaza ve depo stok verilerinin manuel takip yerine otomatik güncellenmesini sağlayan bir Python/SQL betiği geliştirilir. "
         "Kritik stok seviyesinin altına düşen ürünler için otomatik uyarı mekanizması kurulur ve süreç, gerçek zamanlı bir "
         "stok panosu ile görselleştirilir.", 40),
        ("Mobil Uygulama Geliştirme Desteği", "BİLGİ TEKNOLOJİLERİ GMY", "Mobil Uygulama Geliştirme, API, Python",
         "FLO'nun mobil uygulama ekibine, yeni bir özelliğin (örn. beden önerisi, favori listesi bildirimleri) uçtan uca "
         "geliştirilmesinde destek verilir. API entegrasyonları test edilir, hata senaryoları belgelenir ve özellik canlıya "
         "alınmadan önce kullanıcı testleri koordine edilir.", 60),
        ("Bulut Altyapı Geçiş Projesi", "BİLGİ TEKNOLOJİLERİ GMY", "Bulut Teknolojileri (Cloud), Siber Güvenlik, API",
         "Şirket içi bazı sistemlerin bulut altyapısına (Azure/AWS) taşınması sürecinde envanter çıkarma, geçiş öncesi risk "
         "değerlendirmesi ve temel güvenlik kontrol listelerinin hazırlanmasına destek verilir. Geçiş sonrası performans ve "
         "erişim testleri raporlanır.", 60),
        ("Müşteri Destek Chatbotu", "BİLGİ TEKNOLOJİLERİ GMY", "Python, Makine Öğrenmesi, SQL",
         "Sık sorulan müşteri sorularını (kargo takibi, iade süreci, beden tablosu vb.) otomatik yanıtlayan bir yapay zeka "
         "destekli chatbot prototipi geliştirilir. Geçmiş müşteri hizmetleri kayıtları SQL üzerinden analiz edilerek en sık "
         "karşılaşılan senaryolar modele öğretilir ve doğruluk oranı test edilir.", 60),

        # CEO YARDIMCILIĞI (MALİ İŞLER, İK, LOJİSTİK, İÇ DENETİM)
        ("Personel Eğitim Programı Geliştirme", "CEO YARDIMCILIĞI (MALİ İŞLER, İK, LOJİSTİK, İÇ DENETİM)", "Eğitim ve Gelişim, Sunum Becerisi, İletişim",
         "Yeni işe başlayan personel ve stajyerler için bir oryantasyon eğitim programı tasarlanır. Şirket kültürü, temel "
         "prosedürler ve departmanlar arası işleyişi anlatan sunum/eğitim materyalleri hazırlanır ve pilot bir eğitim "
         "oturumu sunulur (İK).", 20),
        ("Çalışan Bağlılığı Anketi Analizi", "CEO YARDIMCILIĞI (MALİ İŞLER, İK, LOJİSTİK, İÇ DENETİM)", "Veri Analizi, Araştırma, Raporlama",
         "Şirket genelinde uygulanan çalışan memnuniyet/bağlılık anketinin sonuçları departman ve kıdem bazında analiz edilir. "
         "Memnuniyeti düşüren temel faktörler belirlenip yönetime sunulacak bir bulgular ve öneriler raporu hazırlanır (İK).", 20),
        ("Kampanya ve Fiyatlandırma Analizi", "CEO YARDIMCILIĞI (MALİ İŞLER, İK, LOJİSTİK, İÇ DENETİM)", "Excel, Finansal Analiz, Veri Analizi",
         "Geçmiş dönem indirim ve kampanya verileri incelenerek hangi kampanya tiplerinin ciro ve kâr marjına ne yönde etki "
         "ettiği hesaplanır. Farklı fiyatlandırma senaryoları için basit bir finansal model kurulup yönetime karar destek "
         "raporu sunulur (Mali İşler).", 30),
        ("Sözleşme ve Uyum Takip Sistemi", "CEO YARDIMCILIĞI (MALİ İŞLER, İK, LOJİSTİK, İÇ DENETİM)", "Hukuk ve Uyum, Excel, Raporlama",
         "Tedarikçi ve mağaza kira sözleşmelerinin süre, yenileme tarihi ve temel yükümlülük bilgileri tek bir dijital "
         "takip tablosuna aktarılır. Süresi yaklaşan sözleşmeler için otomatik hatırlatma mantığı kurulur, eksik/riskli "
         "maddeler işaretlenerek İç Denetim'e raporlanır.", 30),
        ("Depo ve Sevkiyat Optimizasyonu", "CEO YARDIMCILIĞI (MALİ İŞLER, İK, LOJİSTİK, İÇ DENETİM)", "Excel, Veri Analizi, Lojistik",
         "Depodan mağazalara yapılan sevkiyat süreçleri incelenerek teslimat sürelerini uzatan darboğazlar tespit edilir. "
         "Rota ve sevkiyat sıklığı verileri Excel üzerinde analiz edilip, süreç iyileştirme önerileri içeren bir rapor "
         "hazırlanır (Lojistik).", 30),

        # E-TİCARET, ALTERNATİF SATIŞ KANALLARI VE PLANLAMA GMY
        ("Müşteri Deneyimi İyileştirmesi", "E-TİCARET, ALTERNATİF SATIŞ KANALLARI VE PLANLAMA GMY", "UI/UX Tasarım, Analitik Düşünme",
         "flo.com.tr üzerindeki satın alma yolculuğu (ürün arama, sepete ekleme, ödeme) adım adım incelenerek kullanıcıyı "
         "zorlayan noktalar tespit edilir. Tespit edilen sorunlar için basit arayüz iyileştirme önerileri (wireframe düzeyinde) "
         "hazırlanır.", 30),
        ("E-Ticaret Sitesi UX Testi", "E-TİCARET, ALTERNATİF SATIŞ KANALLARI VE PLANLAMA GMY", "UI/UX Tasarım, Kullanıcı Deneyimi Araştırması, Problem Çözme",
         "Gerçek kullanıcılarla (arkadaş çevresi/gönüllü test grubu) flo.com.tr üzerinde kullanılabilirlik testleri düzenlenir. "
         "Kullanıcıların takıldığı adımlar not edilip video/ekran kaydıyla belgelenir, bulgular önceliklendirilmiş bir "
         "iyileştirme listesi halinde sunulur.", 30),
        ("Terk Edilen Sepet Analizi", "E-TİCARET, ALTERNATİF SATIŞ KANALLARI VE PLANLAMA GMY", "Veri Analizi, Analitik Düşünme, Raporlama",
         "Sepete ürün eklenip satın alma tamamlanmadan siteden ayrılan kullanıcıların verileri incelenir; kargo ücreti, "
         "ödeme adımı sayısı, stok durumu gibi olası nedenler test edilir. Sepet terk oranını azaltmaya yönelik somut "
         "önerilerle bir rapor hazırlanır.", 30),
        ("Alternatif Satış Kanalları Performans Analizi", "E-TİCARET, ALTERNATİF SATIŞ KANALLARI VE PLANLAMA GMY", "Veri Analizi, E-Ticaret Yönetimi, Raporlama",
         "Trendyol, Hepsiburada gibi pazaryeri kanalları ile flo.com.tr'nin satış, iade ve kâr marjı performansları "
         "karşılaştırılır. Hangi kanalın hangi ürün grubunda daha güçlü olduğu belirlenip kanal bazlı bir strateji "
         "önerisi sunulur.", 30),

        # FLO TÜRKİYE PERAKENDE GMY
        ("Yeni Mağaza Açılış Süreç Yönetimi", "FLO TÜRKİYE PERAKENDE GMY", "Proje Yönetimi, Organizasyon Becerisi, Bütçe Yönetimi",
         "Yeni açılacak bir mağazanın açılış sürecine (yer seçimi kriterleri, zaman çizelgesi, bütçe kalemleri, ekip "
         "koordinasyonu) destek verilir. Açılış öncesi kontrol listesi (checklist) hazırlanır ve sürecin ilerleyişi "
         "haftalık olarak raporlanır.", 40),
        ("Mağaza Vitrin ve Görsel Pazarlama Tasarımı", "FLO TÜRKİYE PERAKENDE GMY", "Grafik Tasarım, Tasarım, Fotoğrafçılık",
         "Yeni sezon koleksiyonu için mağaza vitrini ve iç mekan görsel teşhir konsepti tasarlanır. Renk paleti, ürün "
         "yerleşimi ve tabela/afiş tasarımları hazırlanıp pilot bir mağazada uygulanabilirliği değerlendirilir.", 20),
        ("Mağaza Müşteri Memnuniyeti Anket Analizi", "FLO TÜRKİYE PERAKENDE GMY", "Veri Analizi, Araştırma, Müşteri İlişkileri Yönetimi",
         "Mağaza içi müşteri memnuniyeti anketleri (personel ilgisi, ürün çeşitliliği, bekleme süresi vb.) analiz edilir. "
         "Mağaza bazında memnuniyet skorları karşılaştırılıp, en düşük skorlu alanlara yönelik iyileştirme önerileri "
         "raporlanır.", 20),

        # GİYİM & AKSESUAR ÜRÜN YÖNETİMİ GMY
        ("Aksesuar Trend Analizi", "GİYİM & AKSESUAR ÜRÜN YÖNETİMİ GMY", "Tasarım, Analitik Düşünme, Araştırma",
         "Çanta, çorap, bakım ürünleri gibi aksesuar kategorilerinde öne çıkan yeni sezon trendleri araştırılır. Rakip "
         "markaların aksesuar ürün gamı incelenip FLO'nun ürün yönetimi ekibine sunulacak bir trend ve fırsat raporu "
         "hazırlanır.", 20),
        ("Giyim Koleksiyonu Fiyatlandırma Analizi", "GİYİM & AKSESUAR ÜRÜN YÖNETİMİ GMY", "Excel, Finansal Analiz, Veri Analizi",
         "Giyim kategorisindeki ürünlerin maliyet, rakip fiyatlaması ve tarihsel satış verileri karşılaştırılarak "
         "kategori bazında bir fiyatlandırma stratejisi analizi yapılır. Fiyat/talep esnekliğine dair basit bir "
         "değerlendirme raporu hazırlanır.", 30),

        # GLOBAL İŞ GELİŞTİRME VE STRATEJİ GMY
        ("Sürdürülebilirlik Raporu Hazırlığı", "GLOBAL İŞ GELİŞTİRME VE STRATEJİ GMY", "Araştırma, Raporlama, Sürdürülebilirlik",
         "Şirketin yıllık sürdürülebilirlik raporu için departmanlardan veri toplanır (enerji kullanımı, geri dönüşüm "
         "oranları, sosyal sorumluluk projeleri vb.). Toplanan veriler düzenlenip raporun ilgili bölümlerinin taslak "
         "metinleri yazılır.", 20),
        ("Rakip ve Pazar Analizi Raporu", "GLOBAL İŞ GELİŞTİRME VE STRATEJİ GMY", "Araştırma, Analitik Düşünme, Raporlama",
         "Yurt içi ve yurt dışı ayakkabı/perakende sektöründeki başlıca rakiplerin büyüme stratejileri, mağaza sayıları "
         "ve dijital yatırımları araştırılır. Bulgular, üst yönetime sunulacak bir pazar konumlandırma ve fırsat "
         "raporunda derlenir.", 30),

        # IN STREET VE MONOBRAND GENEL MÜDÜR YARD.
        ("Monobrand Mağaza Konsept Tasarımı", "IN STREET VE MONOBRAND GENEL MÜDÜR YARD.", "Tasarım, Grafik Tasarım, Proje Yönetimi",
         "Tek marka (monobrand) mağazalar için yeni bir iç mekan ve teşhir konsepti tasarlanır. Konsept, uygulanabilirlik "
         "açısından bütçe ve zaman çizelgesiyle birlikte bir sunum halinde hazırlanır.", 30),
        ("In Street Mağazalar Performans Karşılaştırması", "IN STREET VE MONOBRAND GENEL MÜDÜR YARD.", "Excel, Veri Analizi, Raporlama",
         "Farklı lokasyonlardaki In Street mağazalarının metrekare başına satış, ziyaretçi sayısı ve dönüşüm oranı "
         "verileri karşılaştırılır. En iyi ve en zayıf performans gösteren mağazalar tespit edilip nedenleri üzerine "
         "bir analiz raporu hazırlanır.", 20),

        # KATEGORİ YÖNETİMİ GENEL MÜDÜR YRD.
        ("Kategori Bazlı Satış Performans Analizi", "KATEGORİ YÖNETİMİ GENEL MÜDÜR YRD.", "Excel, Veri Analizi, Analitik Düşünme",
         "Spor, günlük, klasik gibi ürün kategorilerinin dönemsel satış, iade ve kâr marjı verileri karşılaştırılır. "
         "Büyüyen ve gerileyen kategoriler tespit edilip kategori yöneticilerine sunulacak bir performans karnesi "
         "hazırlanır.", 30),
        ("Ürün Kategorileme ve Sınıflandırma Optimizasyonu", "KATEGORİ YÖNETİMİ GENEL MÜDÜR YRD.", "SQL, Veri Analizi, Problem Çözme",
         "Ürünlerin veri tabanındaki mevcut kategori/alt kategori yapısı incelenir, yanlış veya eksik sınıflandırılmış "
         "ürünler SQL sorgularıyla tespit edilir. Daha tutarlı bir kategori ağacı önerisi hazırlanıp örnek verilerle "
         "test edilir.", 30),

        # PAZARLAMA VE BÜYÜME GENEL MÜDÜR YARD.
        ("Sosyal Medya Kampanyası", "PAZARLAMA VE BÜYÜME GENEL MÜDÜR YARD.", "İletişim, Tasarım, Sosyal Medya",
         "Yeni sezon koleksiyonunu tanıtacak bir sosyal medya kampanyası (Instagram/TikTok) uçtan uca planlanır: içerik "
         "takvimi, görsel konsept ve paylaşım metinleri hazırlanır; kampanya sonunda etkileşim metrikleri (beğeni, "
         "erişim, tıklama) raporlanır.", 20),
        ("SEO ve Blog Optimizasyonu", "PAZARLAMA VE BÜYÜME GENEL MÜDÜR YARD.", "SEO, İçerik Üretimi",
         "flo.com.tr blog sayfalarının arama motoru sıralamasını iyileştirmek için anahtar kelime araştırması yapılır, "
         "mevcut içerikler SEO kurallarına göre güncellenir ve yeni blog yazısı önerileri hazırlanır.", 30),
        ("Influencer İş Birlikleri Yönetimi", "PAZARLAMA VE BÜYÜME GENEL MÜDÜR YARD.", "Sosyal Medya, İletişim, Influencer İş Birlikleri",
         "Spor ve moda alanında uygun influencer/içerik üreticileri araştırılıp bir aday listesi oluşturulur. Seçilen "
         "iş birlikleri için brief hazırlanır, paylaşım takvimi koordine edilir ve kampanya sonuçları (erişim, "
         "dönüşüm) takip edilir.", 20),
        ("Ürün Tanıtım Video İçerikleri", "PAZARLAMA VE BÜYÜME GENEL MÜDÜR YARD.", "Video Düzenleme, Fotoğrafçılık, İçerik Üretimi",
         "Yeni sezon ayakkabı koleksiyonu için sosyal medyada kullanılacak kısa tanıtım videoları çekilir/düzenlenir. "
         "Video senaryosu, çekim planı ve son kurgu aşamaları uçtan uca yürütülür.", 20),
        ("Marka Kimliği Yenileme Çalışması", "PAZARLAMA VE BÜYÜME GENEL MÜDÜR YARD.", "Marka Yönetimi, Grafik Tasarım, Sunum Becerisi",
         "Bir alt marka veya kampanya için görsel kimlik (logo kullanımı, renk paleti, tipografi) ve iletişim dili "
         "önerisi hazırlanır. Öneriler, farklı mecralarda (sosyal medya, mağaza içi, ambalaj) nasıl görüneceğini "
         "gösteren bir mockup sunumuyla desteklenir.", 30),

        # TEDARİK OPERASYONLARI GENEL MÜDÜR YARD.
        ("Tedarikçi Performans Değerlendirmesi", "TEDARİK OPERASYONLARI GENEL MÜDÜR YARD.", "Excel, Raporlama, Müzakere",
         "Mevcut tedarikçilerin zamanında teslimat oranı, ürün kalite şikayetleri ve fiyat rekabetçiliği verileri "
         "derlenerek karşılaştırmalı bir tedarikçi karnesi (scorecard) hazırlanır. Düşük performanslı tedarikçiler "
         "için iyileştirme/görüşme önerileri sunulur.", 30),
        ("Üretim Planlama ve Kapasite Analizi", "TEDARİK OPERASYONLARI GENEL MÜDÜR YARD.", "Excel, Veri Analizi, Süreç İyileştirme",
         "Üretim/tedarik takviminin mevcut talep tahminleriyle ne ölçüde uyumlu olduğu incelenir. Kapasite fazlası "
         "veya darboğaz yaşanan dönemler tespit edilip, planlama sürecini iyileştirecek öneriler bir rapor halinde "
         "sunulur.", 30),

        # YURT DIŞI SATIŞ KANALLARI GMY
        ("Yurt Dışı Pazar Giriş Stratejisi Araştırması", "YURT DIŞI SATIŞ KANALLARI GMY", "Araştırma, Yabancı Dil (İngilizce), Analitik Düşünme",
         "FLO'nun henüz güçlü şekilde yer almadığı bir yurt dışı pazarında rekabet ortamı, tüketici alışkanlıkları ve "
         "yasal gereklilikler İngilizce kaynaklardan araştırılır. Bulgular, pazara giriş için fırsat ve riskleri özetleyen "
         "bir strateji notunda toplanır.", 30),
        ("Uluslararası Distribütör Performans Takibi", "YURT DIŞI SATIŞ KANALLARI GMY", "Excel, Raporlama, Müzakere",
         "Yurt dışındaki distribütör ortakların dönemsel satış hedefleri ile gerçekleşen satışları karşılaştırılır. "
         "Hedefin altında kalan distribütörler tespit edilip, olası nedenler ve aksiyon önerileri içeren bir performans "
         "raporu hazırlanır.", 30),
    ]
    
    c.executemany("INSERT INTO projeler (proje_adi, departman, aranan_yetkinlikler, aciklama, min_staj_gunu) VALUES (?, ?, ?, ?, ?)", yeni_projeler)
    conn.commit()
    conn.close()
    print(f"Veritabanı güncellendi: {len(yeni_projeler)} proje, {len(FLO_DEPARTMANLARI)} departmana dağıtıldı!")

if __name__ == "__main__":
    veritabani_olustur()
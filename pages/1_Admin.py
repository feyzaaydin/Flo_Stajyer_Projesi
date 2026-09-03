import streamlit as st
import pandas as pd
from veritabani_islemleri import (
    semayi_kontrol_et_ve_onar,
    gecmis_basvurulari_getir,
    basvuru_guncelle,
    basvuru_sil,
    DUZENLENEBILIR_KOLONLAR,
)

semayi_kontrol_et_ve_onar()

st.title("🔒 Admin Paneli")
st.caption("Bu sayfa sadece yetkili ekip üyeleri içindir. Stajyer başvurularının kişisel bilgilerini içerir.")

# --- Basit şifre koruması ---
# Şifre .streamlit/secrets.toml içinde ADMIN_PASSWORD olarak tanımlanmalı.
# Doğru şifre girilene kadar hiçbir başvuru verisi ekrana çizilmez.
if "admin_giris_yapildi" not in st.session_state:
    st.session_state.admin_giris_yapildi = False

if not st.session_state.admin_giris_yapildi:
    girilen_sifre = st.text_input("Admin Şifresi", type="password")
    giris_butonu = st.button("Giriş Yap")

    if giris_butonu:
        try:
            dogru_sifre = st.secrets["ADMIN_PASSWORD"]
        except Exception:
            st.error(
                "Sistem yöneticisi henüz bir admin şifresi tanımlamamış. "
                ".streamlit/secrets.toml dosyasına ADMIN_PASSWORD eklenmeli."
            )
            st.stop()

        if girilen_sifre == dogru_sifre:
            st.session_state.admin_giris_yapildi = True
            st.rerun()
        else:
            st.error("Şifre yanlış.")

    st.stop()  # Şifre doğrulanmadan aşağıdaki hiçbir satır çalışmaz

# --- Şifre doğrulandıktan sonrası ---
col_baslik, col_cikis = st.columns([5, 1])
with col_baslik:
    st.subheader("📋 Şimdiye Kadar Başvuran Stajyerler")
with col_cikis:
    if st.button("Çıkış Yap"):
        st.session_state.admin_giris_yapildi = False
        st.rerun()

gecmis_df = gecmis_basvurulari_getir()

if gecmis_df.empty:
    st.caption("Henüz kaydedilmiş bir başvuru yok.")
else:
    st.caption(
        "Tabloyu doğrudan hücrelere tıklayarak düzenleyebilirsiniz (durum, ad soyad, e-posta, "
        "önerilen proje vb.). Satır silmek için satırı seçip klavyeden **Delete** tuşuna basın. "
        "Değişiklikler **Değişiklikleri Kaydet** butonuna basınca veritabanına yazılır."
    )

    DURUM_SECENEKLERI = ["Beklemede", "Kabul Edildi", "Reddedildi", "Görüşmeye Çağrıldı", "İncelemede"]

    kolon_ayarlari = {
        "ID": st.column_config.NumberColumn("ID", disabled=True),
        "Başvuru Tarihi": st.column_config.TextColumn("Başvuru Tarihi", disabled=True),
        "Durum": st.column_config.SelectboxColumn(
            "Durum", options=DURUM_SECENEKLERI, required=True
        ),
        "Uyum Puanı (%)": st.column_config.NumberColumn("Uyum Puanı (%)", min_value=0, max_value=100),
    }
    # Ekranda görünüp DB'de karşılığı olmayan / düzenlenmesi mantıksız kolonları kilitle
    duzenlenebilir_ekran_adlari = set(DUZENLENEBILIR_KOLONLAR.keys())
    kilitli_kolonlar = [
        col for col in gecmis_df.columns
        if col not in duzenlenebilir_ekran_adlari
    ]

    duzenlenmis_df = st.data_editor(
        gecmis_df,
        column_config=kolon_ayarlari,
        disabled=kilitli_kolonlar,
        hide_index=True,
        width="stretch",
        num_rows="dynamic",
        key="gecmis_editor",
    )

    if st.button("💾 Değişiklikleri Kaydet"):
        eski = gecmis_df.set_index("ID")
        # Yeni eklenen (ID'si boş) satırları yok say – başvurular sadece formdan gelir
        yeni = duzenlenmis_df.dropna(subset=["ID"])
        yeni = yeni[yeni["ID"] != ""].copy()
        yeni["ID"] = yeni["ID"].astype(int)
        yeni = yeni.set_index("ID")

        silinen_idler = [i for i in eski.index if i not in yeni.index]
        for basvuru_id in silinen_idler:
            basvuru_sil(basvuru_id)

        guncellenen_sayisi = 0
        for basvuru_id, satir in yeni.iterrows():
            if basvuru_id not in eski.index:
                continue
            degisiklikler = {}
            for ekran_adi, db_kolonu in DUZENLENEBILIR_KOLONLAR.items():
                if ekran_adi not in yeni.columns:
                    continue
                yeni_deger = satir[ekran_adi]
                eski_deger = eski.loc[basvuru_id, ekran_adi]
                if pd.isna(yeni_deger) and pd.isna(eski_deger):
                    continue
                if yeni_deger != eski_deger:
                    degisiklikler[db_kolonu] = None if pd.isna(yeni_deger) else yeni_deger
            if degisiklikler:
                basvuru_guncelle(basvuru_id, degisiklikler)
                guncellenen_sayisi += 1

        if guncellenen_sayisi or silinen_idler:
            mesajlar = []
            if guncellenen_sayisi:
                mesajlar.append(f"{guncellenen_sayisi} başvuru güncellendi")
            if silinen_idler:
                mesajlar.append(f"{len(silinen_idler)} başvuru silindi")
            st.success(" • ".join(mesajlar) + ".")
            st.rerun()
        else:
            st.info("Herhangi bir değişiklik yapılmadı.")

    st.caption(f"Toplam {len(gecmis_df)} başvuru kaydedildi.")
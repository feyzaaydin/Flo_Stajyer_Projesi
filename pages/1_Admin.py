import streamlit as st
from veritabani_islemleri import semayi_kontrol_et_ve_onar, gecmis_basvurulari_getir, durum_guncelle

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
    duzenlenmis_df = st.data_editor(
        gecmis_df,
        column_config={
            "Durum": st.column_config.SelectboxColumn(
                "Durum",
                options=["Beklemede", "Kabul Edildi", "Reddedildi"],
                required=True
            ),
            "ID": st.column_config.NumberColumn("ID", disabled=True)
        },
        disabled=[col for col in gecmis_df.columns if col != "Durum"],
        hide_index=True,
        width="stretch",
        key="gecmis_editor"
    )

    if st.button("💾 Durum Değişikliklerini Kaydet"):
        degisen_satirlar = duzenlenmis_df[duzenlenmis_df["Durum"] != gecmis_df["Durum"]]
        for _, satir in degisen_satirlar.iterrows():
            durum_guncelle(satir["ID"], satir["Durum"])
        if len(degisen_satirlar) > 0:
            st.success(f"{len(degisen_satirlar)} başvurunun durumu güncellendi!")
            st.rerun()
        else:
            st.info("Herhangi bir değişiklik yapılmadı.")

    st.caption(f"Toplam {len(gecmis_df)} başvuru kaydedildi.")
import sys
import os
import streamlit as st

# st.navigation ile çalışan sayfaların (basvuru_formu.py, pages/1_Admin.py) bu klasördeki
# diğer modülleri (okullar.py, database.py, veritabani_islemleri.py vb.) bulabilmesi için
# proje klasörünü Python'un arama yoluna ekliyoruz.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="FLO Kariyer", layout="wide")

sayfalar = [
    st.Page("basvuru_formu.py", title="Stajyer Başvurusu", icon="👟", default=True),
    st.Page("pages/1_Admin.py", title="Admin", icon="🔒"),
]

secilen_sayfa = st.navigation(sayfalar)
secilen_sayfa.run()
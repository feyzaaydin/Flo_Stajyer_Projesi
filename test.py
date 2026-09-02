import google.generativeai as genai

# Buraya kendi API anahtarını tırnak içinde yaz
api_key = "SENIN_API_ANAHTARIN"
genai.configure(api_key=api_key)

print("Kullanılabilir Modeller:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
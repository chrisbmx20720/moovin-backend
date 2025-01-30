
import os

file_path = "Backend/api/google_credentials/credentials.json"

if os.path.exists(file_path):
    print("✅ Archivo encontrado")
else:
    print("❌ Archivo NO encontrado")
"""
Plantilla de configuracion. Copiar a config.py y rellenar con valores reales.
config.py esta en .gitignore por contener secretos.
"""
import os

# --- Google Sheets (backend de AppSheet, solo lectura desde este proyecto) ---
SPREADSHEET_ID = "TU_SPREADSHEET_ID_AQUI"
CREDENTIALS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "credentials", "service_account.json"
)

# --- AppSheet REST API (para descargar documentos: PDFs, imagenes) ---
APPSHEET_APP_ID   = "TU_APPSHEET_APP_ID_AQUI"
APPSHEET_APP_NAME = "TU_APP_NAME_AQUI"
APPSHEET_API_KEY  = "TU_APPSHEET_API_KEY_AQUI"
APPSHEET_API_URL  = f"https://api.appsheet.com/api/v2/apps/{APPSHEET_APP_ID}/tables"

# --- Anthropic (chat_assistant.py / claude_query.py) ---
# Estos scripts leen ANTHROPIC_API_KEY desde variable de entorno (os.getenv),
# no se setea aqui. En Windows: setx ANTHROPIC_API_KEY "tu_key"

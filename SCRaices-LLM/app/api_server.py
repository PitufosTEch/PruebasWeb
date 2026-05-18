"""
API Proxy - Sirve datos de Google Sheets via HTTP con CORS.
Usa la misma service account que el proyecto.

Uso local:  python api_server.py
Endpoint:   GET http://localhost:5050/api/data?tables=Proyectos,Beneficiario,...

Para deploy en Render/Railway/Vercel:
  - Variable de entorno GOOGLE_CREDENTIALS_JSON con el contenido del service account JSON
  - O incluir credentials/service_account.json en el deploy
"""
import os
import sys
import json
import time
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials

# ============================================================
# CONFIGURACION
# ============================================================
SPREADSHEET_ID = "1JAxxP9W6LJzns5rmGIo7mfk227qMLwsq-gFMCvHU0Zk"
CACHE_TTL = 300  # 5 minutos de cache
PORT = int(os.environ.get('PORT', 5050))

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# ============================================================
# APP
# ============================================================
app = Flask(__name__)
CORS(app)  # Permitir requests desde cualquier origen

# Cache simple: {table_name: {data: [...], timestamp: float}}
_cache = {}
_sheets_client = None


def get_credentials():
    """Obtiene credenciales de service account (archivo o env var)"""
    # Opcion 1: Variable de entorno (para deploy)
    creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    if creds_json:
        info = json.loads(creds_json)
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    # Opcion 2: Archivo local
    creds_path = Path(__file__).parent.parent / 'credentials' / 'service_account.json'
    if creds_path.exists():
        return Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)

    raise RuntimeError("No se encontraron credenciales. Configura GOOGLE_CREDENTIALS_JSON o credentials/service_account.json")


def get_spreadsheet():
    """Obtiene el spreadsheet (singleton)"""
    global _sheets_client
    if _sheets_client is None:
        creds = get_credentials()
        client = gspread.authorize(creds)
        _sheets_client = client.open_by_key(SPREADSHEET_ID)
    return _sheets_client


def get_table_data(table_name):
    """Lee datos de una hoja con cache"""
    now = time.time()

    # Verificar cache
    if table_name in _cache:
        cached = _cache[table_name]
        if now - cached['timestamp'] < CACHE_TTL:
            return cached['data']

    # Leer de Google Sheets
    ss = get_spreadsheet()
    try:
        sheet = ss.worksheet(table_name)
    except gspread.exceptions.WorksheetNotFound:
        return {'error': f'Hoja "{table_name}" no encontrada'}

    # get_all_values es mas robusto que get_all_records (maneja duplicados)
    all_values = sheet.get_all_values()
    if not all_values:
        return {'count': 0, 'rows': []}

    headers = all_values[0]
    rows = []
    for r in range(1, len(all_values)):
        row = {}
        for c in range(len(headers)):
            val = all_values[r][c] if c < len(all_values[r]) else ''
            row[headers[c]] = val
        rows.append(row)

    result = {'count': len(rows), 'rows': rows}

    # Guardar en cache
    _cache[table_name] = {'data': result, 'timestamp': now}

    return result


# ============================================================
# ENDPOINTS
# ============================================================

@app.route('/api/data', methods=['GET'])
def api_data():
    """
    GET /api/data?tables=Tabla1,Tabla2,...
    Retorna JSON con datos de cada tabla solicitada.
    """
    tables_param = request.args.get('tables', '')
    if not tables_param:
        return jsonify({'error': 'Parametro "tables" requerido. Ej: ?tables=Proyectos,Beneficiario'}), 400

    table_names = [t.strip() for t in tables_param.split(',') if t.strip()]
    result = {}

    for name in table_names:
        try:
            result[name] = get_table_data(name)
        except Exception as e:
            result[name] = {'error': str(e)}

    return jsonify(result)


@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    """Limpia el cache de datos"""
    global _cache
    _cache = {}
    return jsonify({'status': 'ok', 'message': 'Cache limpiado'})


@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'cache_entries': len(_cache),
        'cache_ttl': CACHE_TTL
    })


@app.route('/', methods=['GET'])
def index():
    """Pagina de info"""
    return jsonify({
        'name': 'SCRaices Data API',
        'endpoints': {
            'GET /api/data?tables=...': 'Obtener datos de tablas',
            'POST /api/clear-cache': 'Limpiar cache',
            'GET /api/health': 'Health check'
        },
        'tables_disponibles': 'Proyectos,Beneficiario,Despacho,soldepacho,Ejecucion,Solpago,Maestros,Tabla_pago,Tipologias',
        'cache_ttl_seconds': CACHE_TTL
    })


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print(f"SCRaices Data API")
    print(f"  Endpoint: http://localhost:{PORT}/api/data?tables=Proyectos")
    print(f"  Cache TTL: {CACHE_TTL}s")
    print(f"  CORS: habilitado")
    print()
    app.run(host='0.0.0.0', port=PORT, debug=True)

"""
Leer datos TE1 desde Google Sheet.

Sheet ID: 1QCoIpiQKV1LB6XgUwwoC_e4crRD5mIANLxon9ZVwsg8

Uso:
    python leer_te1.py                  # Muestra todo
    python leer_te1.py Temuco           # Filtra por comuna
    python leer_te1.py --actualizar     # Ejecuta scraper + upload + lee
"""
import sys
import json
import subprocess
from pathlib import Path


TE1_SHEET_ID = "1QCoIpiQKV1LB6XgUwwoC_e4crRD5mIANLxon9ZVwsg8"
SCRAPER_PATH = r"C:\Users\migue\OneDrive\Escritorio\Proyectos Claude\TE1\sec_te1_scraper.py"
UPLOAD_PATH = r"C:\Users\migue\OneDrive\Escritorio\Proyectos Claude\TE1\upload_to_sheets.py"
CREDENTIALS_PATH = "G:/Mi unidad/00 - Proyectos/CLAUDE-CODE/SCRaices-LLM/credentials/service_account.json"


def actualizar_te1():
    """Ejecuta scraper + upload al Sheet"""
    print("Ejecutando scraper TE1...")
    r1 = subprocess.run(
        [sys.executable, SCRAPER_PATH],
        capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL
    )
    if r1.returncode != 0:
        print(f"Error scraper: {r1.stderr[:500]}")
        return False
    print("Scraper OK. Subiendo a Google Sheets...")

    r2 = subprocess.run(
        [sys.executable, UPLOAD_PATH],
        capture_output=True, text=True, timeout=120
    )
    if r2.returncode != 0:
        print(f"Error upload: {r2.stderr[:500]}")
        return False
    print("Upload OK.")
    return True


def leer_te1(comuna=None):
    """Lee datos TE1 desde Google Sheet"""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("Instalando gspread...")
        subprocess.run([sys.executable, "-m", "pip", "install", "gspread"], capture_output=True)
        import gspread
        from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(TE1_SHEET_ID)
    datos = sh.sheet1.get_all_records()

    if comuna:
        datos = [d for d in datos if d.get("Comuna", "").lower() == comuna.lower()]

    return datos


def main():
    args = sys.argv[1:]

    if "--actualizar" in args:
        actualizar_te1()
        args = [a for a in args if a != "--actualizar"]

    comuna = args[0] if args else None
    datos = leer_te1(comuna)

    print(f"\nRegistros TE1: {len(datos)}")
    if comuna:
        print(f"Filtro: {comuna}")

    if datos:
        print(f"Columnas: {list(datos[0].keys())}")
        print()
        for d in datos[:10]:
            print(d)
        if len(datos) > 10:
            print(f"... y {len(datos) - 10} más")


if __name__ == "__main__":
    main()

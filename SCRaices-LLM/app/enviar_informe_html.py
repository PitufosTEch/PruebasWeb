"""
enviar_informe_html.py
======================
Abre el dashboard con Playwright, genera el HTML multi-obras y lo envía por correo.

Uso local:
    python enviar_informe_html.py
    python enviar_informe_html.py --para otro@mail.cl
    python enviar_informe_html.py --solo-guardar

En GitHub Actions, las credenciales se pasan como variables de entorno:
    GMAIL_EMAIL, GMAIL_APP_PASSWORD
"""

import argparse
import json
import logging
import os
import smtplib
import sys
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DASHBOARD_URL        = "https://pitufostech.github.io/PruebasWeb/SCRaices-LLM/dashboard/index_live_v3.html"
GMAIL_CFG_FILE       = Path(r"C:\Users\rodri\.claude\gmail_config.json")
OUTPUT_DIR           = Path(os.environ.get("OUTPUT_DIR", "/tmp/informes_html" if os.name != "nt" else r"C:\Users\rodri\.claude\informes_html"))
LOG_FILE             = Path(os.environ.get("LOG_FILE",   "/tmp/informe_html.log" if os.name != "nt" else r"C:\Users\rodri\.claude\logs\informe_html.log"))

DESTINATARIOS_DEFAULT = ["rlagos@scraices.cl", "aespinoza@scraices.cl"]
REMITENTE_NOMBRE     = "SG Raíces Control"
TIMEOUT_CARGA        = 300   # segundos esperando que cargue el dashboard

# ─────────────────────────────────────────────────────────────────────────────
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _leer_credenciales() -> tuple[str, str]:
    """Lee email + app_password desde env vars (cloud) o config local (Windows)."""
    email = os.environ.get("GMAIL_EMAIL")
    pw    = os.environ.get("GMAIL_APP_PASSWORD")
    if email and pw:
        return email, pw
    if GMAIL_CFG_FILE.exists():
        cfg = json.loads(GMAIL_CFG_FILE.read_text())
        return cfg["email"], cfg["app_password"]
    raise RuntimeError(
        "No se encontraron credenciales Gmail. "
        "Define GMAIL_EMAIL y GMAIL_APP_PASSWORD como variables de entorno."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. CAPTURAR HTML DESDE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def capturar_html() -> Path:
    log.info("Iniciando Playwright...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx  = browser.new_context(accept_downloads=True)
        page = ctx.new_page()

        log.info(f"Cargando dashboard: {DASHBOARD_URL}")
        page.goto(DASHBOARD_URL, timeout=60_000)

        log.info(f"Esperando carga inicial del dashboard (hasta {TIMEOUT_CARGA}s)...")
        try:
            page.wait_for_selector("text=Estado General", state="visible", timeout=TIMEOUT_CARGA * 1000)
        except PlaywrightTimeout:
            log.error("Timeout: el dashboard no terminó de cargar.")
            browser.close()
            raise

        log.info("Navegando a pestaña 'Estado General'...")
        page.click("text=Estado General")
        page.wait_for_timeout(2000)

        try:
            page.wait_for_selector("button:has-text('HTML navegable')", state="visible", timeout=30_000)
        except PlaywrightTimeout:
            log.error("Timeout: botón 'HTML navegable' no apareció.")
            browser.close()
            raise

        log.info("Haciendo click en 'HTML navegable'...")
        with page.expect_download(timeout=60_000) as dl_info:
            page.click("button:has-text('HTML navegable')")

        download = dl_info.value
        fname = download.suggested_filename or f"Informes_MultiObras_{datetime.now().strftime('%Y%m%d')}.html"
        dest  = OUTPUT_DIR / fname
        download.save_as(str(dest))
        log.info(f"HTML guardado: {dest} ({dest.stat().st_size // 1024} KB)")

        browser.close()
        return dest


# ─────────────────────────────────────────────────────────────────────────────
# 2. ENVIAR POR CORREO
# ─────────────────────────────────────────────────────────────────────────────
def enviar_correo(html_path: Path, destinatarios: list[str]):
    remitente, app_pw = _leer_credenciales()

    fecha  = datetime.now().strftime("%d.%m.%Y")
    asunto = f"Informes Ejecutivos Multi Obras — {fecha}"

    msg            = MIMEMultipart()
    msg["From"]    = f"{REMITENTE_NOMBRE} <{remitente}>"
    msg["To"]      = ", ".join(destinatarios)
    msg["Subject"] = asunto

    cuerpo = f"""Estimado/a,

Se adjunta el Informe Ejecutivo Multi Obras generado automáticamente el {fecha}.

El archivo HTML contiene:
  - Resumen de avance por obra (KPIs, contrato, programa de obra)
  - Checkpoints del proyecto (HPC, TE1, V.AS, R.AS, F1, Artef., Empalme, V.DOM, Recep.)
  - Curvas S de control (Total, Todos los Grupos y por Grupo)
  - Ritmos de Mano de Obra y Despachos
  - Detalle de viviendas por beneficiario

Abrir el archivo directamente en el navegador para navegar entre obras.

Generado automáticamente — Panel de Control v3 SG Raíces.
"""
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    with open(html_path, "rb") as f:
        part = MIMEBase("text", "html")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{html_path.name}"')
    msg.attach(part)

    log.info(f"Enviando correo a: {', '.join(destinatarios)}...")
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=120) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(remitente, app_pw)
        server.sendmail(remitente, destinatarios, msg.as_string())

    log.info("Correo enviado exitosamente.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--para", nargs="+", default=DESTINATARIOS_DEFAULT,
                        help="Uno o más destinatarios (separados por espacio)")
    parser.add_argument("--solo-guardar", action="store_true")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"INFORME HTML MULTI OBRAS — {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    log.info("=" * 60)

    try:
        html_path = capturar_html()
    except Exception as e:
        log.error(f"Error al capturar HTML: {e}")
        sys.exit(1)

    if args.solo_guardar:
        log.info(f"--solo-guardar activo. Archivo: {html_path}")
    else:
        try:
            enviar_correo(html_path, args.para)
        except Exception as e:
            log.error(f"Error al enviar correo: {e}")
            sys.exit(1)

    log.info("COMPLETADO.")


if __name__ == "__main__":
    main()

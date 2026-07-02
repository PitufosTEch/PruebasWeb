"""
enviar_informes.py
==================
Lee destinatarios y asignaciones desde Firebase (personal_global + personal_obra),
construye un correo por persona con los archivos que le corresponden según su rol
y los despacha vía Gmail SMTP.

Regla de envío:
  curvas_s           → PDF Ejecutivo (Curvas S)  — todos los proyectos (rol global)
                                                  — solo sus proyectos  (rol no-global)
  html_navegable     → HTML EjecutivoHTML         — archivo único global
  residente          → PDF Residente              — solo sus proyectos asignados
  por_capataz        → PDF Capataz INDIVIDUAL     — solo sus proyectos + solo su PDF
  adquisiciones_html → HTML Adquisiciones         — archivo único global

Modo local : credenciales desde gmail_config.json
Modo cloud : credenciales desde env vars GMAIL_EMAIL, GMAIL_APP_PASSWORD

Uso standalone:
    python enviar_informes.py
    python enviar_informes.py --pdf-dir /ruta/a/archivos
"""

import io
import json
import os
import re
import smtplib
import sys
import unicodedata
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

FIREBASE        = "https://scraices-dashboard-default-rtdb.firebaseio.com"
_LOCAL_GMAIL    = Path(r"C:\Users\rodri\.claude\gmail_config.json")
_LOCAL_PDF_DIR  = Path(r"C:\Users\rodri\.claude\informes_pdf")

# Proyectos activos del dashboard (en orden)
PROYECTOS = [
    ("P126", "El_Maiten"),
    ("P119", "Nuke_Mapu"),
    ("P127", "Nuevo_Cunco"),
    ("P39",  "El_Coihue"),
    ("P14",  "Com_Madihue"),
    ("P116", "Sonia_Quilaleo"),
    ("P12",  "Juan_Huilcan_Tolten"),
    ("P38",  "Aliwen"),
    ("P31",  "Trovolhue"),
    ("P131", "Raices_Melipeuco"),
]
PROY_IDS = [p for p, _ in PROYECTOS]

# Roles que reciben informes de todos los proyectos (no dependen de asignación)
ROLES_GLOBALES = {"gerente", "coordinador", "logistica", "rrhh"}

# Mapa tipo_informe → (prefijo, extensión, es_global, es_capataz_individual)
#   es_global=True        → archivo único sin proyecto
#   es_capataz_individual → buscar por slug del nombre del capataz en el filename
TIPO_ARCHIVO = {
    "curvas_s":          ("Informe_Ejecutivo",    ".pdf",  False, False),
    "html_navegable":    ("Informe_EjecutivoHTML", ".html", True,  False),
    "residente":         ("Informe_Residente",     ".pdf",  False, False),
    "por_capataz":       ("Informe_Capataz",       ".pdf",  False, True),
    "adquisiciones_html":("Informe_Adquisiciones", ".html", True,  False),
    "estados_pago_html": ("Informe_EstadosPago",   ".html", True,  False),
}


def _slug(nombre: str) -> str:
    """Convierte nombre a slug ASCII-safe (mismo algoritmo que capturar_informes_dashboard.py)."""
    nfd = unicodedata.normalize("NFD", nombre)
    ascii_str = nfd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^\w]", "_", ascii_str).strip("_")


def _get_gmail():
    if os.environ.get("GMAIL_APP_PASSWORD"):
        return os.environ["GMAIL_EMAIL"], os.environ["GMAIL_APP_PASSWORD"]
    cfg = json.loads(_LOCAL_GMAIL.read_text())
    return cfg["email"], cfg["app_password"]


def _fetch_firebase(endpoint):
    r = requests.get(f"{FIREBASE}/{endpoint}.json", timeout=30)
    return r.json() or {}


def _buscar_archivos_proy(pdf_dir: Path, prefijo: str, pid: str, fecha: str) -> list:
    """Encuentra archivos por proyecto: Informe_Ejecutivo_P126_..._20260629.pdf"""
    return sorted(pdf_dir.glob(f"{prefijo}_{pid}_*_{fecha}*"))


def _buscar_archivo_global(pdf_dir: Path, prefijo: str, fecha: str) -> list:
    """Encuentra el archivo global único: Informe_EjecutivoHTML_20260629.html"""
    return sorted(pdf_dir.glob(f"{prefijo}_{fecha}*"))


def _buscar_archivo_capataz(pdf_dir: Path, pid: str, nombre_capataz: str, fecha: str) -> list:
    """
    Encuentra el PDF individual del capataz:
    Informe_Capataz_{pid}__{slug}_{fecha}.pdf
    """
    slug = _slug(nombre_capataz)
    return sorted(pdf_dir.glob(f"Informe_Capataz_{pid}_*_{slug}_{fecha}*.pdf"))


def construir_plan_envio(pdf_dir: Path, fecha: str) -> dict:
    """
    Retorna {correo: {"nombre": str, "archivos": [Path], "tipos": [str]}}
    leyendo personal_global y personal_obra desde Firebase.
    """
    pg = _fetch_firebase("personal_global")  # global_key → {correo, nombre, rol, informes}
    po = _fetch_firebase("personal_obra")    # proy_id    → {key: {rol, nombre, global_key}}

    # Mapa global_key → proyectos asignados (solo los del dashboard)
    gk_proyectos = defaultdict(set)
    for proy_id, personas in po.items():
        if proy_id not in PROY_IDS:
            continue
        if not isinstance(personas, dict):
            continue
        for _, p in personas.items():
            if isinstance(p, dict) and p.get("global_key"):
                gk_proyectos[str(p["global_key"])].add(proy_id)

    plan = {}  # correo → {nombre, archivos: [], tipos: set}

    for gk, persona in pg.items():
        correo   = persona.get("correo", "").strip()
        nombre   = persona.get("nombre", "")
        rol      = persona.get("rol", "")
        informes = persona.get("informes", [])

        if not correo or not informes:
            continue

        archivos = []
        for tipo in informes:
            if tipo not in TIPO_ARCHIVO:
                continue
            prefijo, ext, es_global, es_capataz_individual = TIPO_ARCHIVO[tipo]

            if es_global:
                # Archivo único con todos los proyectos integrados
                archivos.extend(_buscar_archivo_global(pdf_dir, prefijo, fecha))

            elif es_capataz_individual:
                # PDF específico del capataz: solo sus proyectos, solo su archivo
                for pid in sorted(gk_proyectos.get(str(gk), [])):
                    archivos.extend(_buscar_archivo_capataz(pdf_dir, pid, nombre, fecha))

            elif rol in ROLES_GLOBALES:
                # Recibe el informe de TODOS los proyectos
                for pid in PROY_IDS:
                    archivos.extend(_buscar_archivos_proy(pdf_dir, prefijo, pid, fecha))

            else:
                # Solo sus proyectos asignados
                for pid in sorted(gk_proyectos.get(str(gk), [])):
                    archivos.extend(_buscar_archivos_proy(pdf_dir, prefijo, pid, fecha))

        if archivos:
            if correo not in plan:
                plan[correo] = {"nombre": nombre, "archivos": [], "tipos": set(informes)}
            plan[correo]["archivos"].extend(archivos)
            plan[correo]["tipos"].update(informes)

    # Deduplicar archivos manteniendo orden
    for correo in plan:
        seen = set()
        dedup = []
        for p in plan[correo]["archivos"]:
            if p not in seen:
                seen.add(p)
                dedup.append(p)
        plan[correo]["archivos"] = dedup

    return plan


def enviar_correo(remitente, app_pw, correo_dest, nombre, archivos, fecha_display, semana):
    n_pdf  = sum(1 for f in archivos if f.suffix == ".pdf")
    n_html = sum(1 for f in archivos if f.suffix == ".html")

    asunto = f"Informes SG Raíces — Semana {semana} ({fecha_display}) — {nombre}"

    lista = "\n".join(f"    {f.name}" for f in sorted(archivos, key=lambda x: x.name))
    body = f"""Estimado/a {nombre},

Se adjuntan sus informes de avance de obra SG Raíces al {fecha_display}:

{lista}

  PDFs:  {n_pdf}   |   HTMLs: {n_html}   |   Total: {len(archivos)} archivos

Los archivos HTML se abren directamente en cualquier navegador.

Generado automáticamente — Panel de Control v3 SG Raíces.
"""

    msg = MIMEMultipart()
    msg["From"]    = f"SG Raices Control <{remitente}>"
    msg["To"]      = correo_dest
    msg["Subject"] = asunto
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for archivo in archivos:
        with open(archivo, "rb") as f:
            data = f.read()
        if archivo.suffix == ".html":
            part = MIMEBase("text", "html")
            part.set_payload(data)
        else:
            part = MIMEBase("application", "pdf")
            part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{archivo.name}"')
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=120) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(remitente, app_pw)
        server.sendmail(remitente, [correo_dest], msg.as_string())


def main(pdf_dir: Path = None, fecha: str = None):
    if pdf_dir is None:
        pdf_dir = _LOCAL_PDF_DIR
    pdf_dir = Path(pdf_dir)

    remitente, app_pw = _get_gmail()
    if fecha:
        from datetime import datetime
        _d         = datetime.strptime(fecha, "%Y%m%d").date()
        fecha_str  = fecha
    else:
        _d         = date.today()
        fecha_str  = _d.strftime("%Y%m%d")
    fecha_display = _d.strftime("%d.%m.%Y")
    semana        = _d.isocalendar()[1]

    print("Leyendo asignaciones desde Firebase...")
    plan = construir_plan_envio(pdf_dir, fecha_str)

    if not plan:
        print(f"No se encontraron archivos del {fecha_str} o destinatarios configurados.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"PLAN DE ENVÍO — {fecha_display}  (Semana {semana})")
    print(f"{'='*60}")
    for correo, datos in sorted(plan.items(), key=lambda x: x[1]["nombre"]):
        print(f"  {datos['nombre']:<28} {correo:<38} {len(datos['archivos'])} archivos")
    print(f"  {'─'*58}")
    print(f"  Total destinatarios: {len(plan)}")
    print()

    errores = []
    for correo, datos in sorted(plan.items(), key=lambda x: x[1]["nombre"]):
        try:
            print(f"  Enviando a {datos['nombre']} ({correo}) — {len(datos['archivos'])} archivos...", end=" ")
            enviar_correo(remitente, app_pw, correo, datos["nombre"],
                          datos["archivos"], fecha_display, semana)
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            errores.append((correo, str(e)))

    print(f"\nEnvíos completados: {len(plan) - len(errores)} OK, {len(errores)} errores")
    if errores:
        for correo, err in errores:
            print(f"  ERROR {correo}: {err}")

    return plan, errores


if __name__ == "__main__":
    pdf_dir_arg = None
    if "--pdf-dir" in sys.argv:
        idx = sys.argv.index("--pdf-dir")
        if idx + 1 < len(sys.argv):
            pdf_dir_arg = Path(sys.argv[idx + 1])
    result = main(pdf_dir_arg)
    if result:
        _, errores = result
        if errores:
            sys.exit(1)

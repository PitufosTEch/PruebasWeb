"""
ejecutar_informes_cloud.py
==========================
Orquestador cloud para la generación y envío de informes.

Modo DIARIO  (ENVIAR_CORREOS no configurado):
    1. Captura todos los reportes del dashboard → PDFs + HTMLs
    2. Sube los archivos a Google Drive (carpeta organizada por fecha)

Modo LUNES / envío  (ENVIAR_CORREOS=1):
    1. Captura todos los reportes del dashboard → PDFs + HTMLs
    2. Sube los archivos a Google Drive
    3. Envía correos personalizados a cada destinatario según Firebase

Variables de entorno requeridas:
    GOOGLE_REFRESH_TOKEN, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    GMAIL_EMAIL, GMAIL_APP_PASSWORD
    FIREBASE_URL
    DRIVE_FOLDER_INFORMES_ID   — ID de la carpeta raíz en Drive para los informes
    ENVIAR_CORREOS             — "1" para disparar el envío (solo lunes)
"""

import os
import sys
import time
from pathlib import Path

# Agregar directorio actual al path para importar módulos locales
sys.path.insert(0, str(Path(__file__).parent))


def subir_a_drive(pdf_dir: Path, fecha: str):
    """Sube todos los archivos generados a una subcarpeta de Drive organizada por fecha."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import curvas_cloud_utils as _ccu

    folder_raiz = os.environ.get("DRIVE_FOLDER_INFORMES_ID")
    if not folder_raiz:
        print("  [Drive] DRIVE_FOLDER_INFORMES_ID no configurado — omitiendo subida")
        return

    creds = _ccu.get_credentials()  # usa SCOPES_DEFAULT: spreadsheets + drive
    service = build("drive", "v3", credentials=creds)

    # Crear subcarpeta con la fecha si no existe
    nombre_subcarpeta = f"Informes_{fecha}"
    query = (f"name='{nombre_subcarpeta}' and "
             f"'{folder_raiz}' in parents and "
             f"mimeType='application/vnd.google-apps.folder' and trashed=false")
    res = service.files().list(q=query, fields="files(id,name)").execute()
    carpetas = res.get("files", [])
    if carpetas:
        subfolder_id = carpetas[0]["id"]
        print(f"  [Drive] Carpeta existente: {nombre_subcarpeta}")
    else:
        meta = {"name": nombre_subcarpeta, "mimeType": "application/vnd.google-apps.folder",
                "parents": [folder_raiz]}
        subfolder = service.files().create(body=meta, fields="id").execute()
        subfolder_id = subfolder["id"]
        print(f"  [Drive] Carpeta creada: {nombre_subcarpeta}")

    # Subir cada archivo generado hoy
    archivos = sorted(pdf_dir.glob(f"*_{fecha}*"))
    ok = 0
    for archivo in archivos:
        mime = "application/pdf" if archivo.suffix == ".pdf" else "text/html"
        media = MediaFileUpload(str(archivo), mimetype=mime, resumable=True)
        meta_file = {"name": archivo.name, "parents": [subfolder_id]}
        service.files().create(body=meta_file, media_body=media, fields="id").execute()
        ok += 1
    print(f"  [Drive] {ok} archivos subidos a carpeta '{nombre_subcarpeta}'")


ADMIN_EMAIL = "rlagos@scraices.cl"


def _enviar_resumen_admin(plan: dict, errores: list, fecha: str):
    """Envía correo de resumen HTML del proceso completo a Rodrigo Lagos."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    remitente  = os.environ.get("GMAIL_EMAIL", "")
    app_pw     = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not remitente or not app_pw:
        print("  [Resumen] Sin credenciales Gmail — omitiendo resumen")
        return

    from datetime import date
    fecha_display = date.today().strftime("%d.%m.%Y")
    semana        = date.today().isocalendar()[1]

    correos_error = {c for c, _ in errores}
    n_ok    = len([c for c in plan if c not in correos_error])
    n_err   = len(correos_error)
    n_total = sum(len(d["archivos"]) for d in plan.values())

    asunto = (
        f"[SG Raíces] Resumen envío semanal — Sem {semana} ({fecha_display}) — "
        f"{n_ok} OK / {n_err} errores"
    )

    # ── Tarjetas por destinatario ─────────────────────────────────────────────
    tarjetas_html = ""
    for correo, datos in sorted(plan.items(), key=lambda x: x[1]["nombre"]):
        archivos  = sorted(datos["archivos"], key=lambda x: x.name)
        es_error  = correo in correos_error
        err_msg   = next((e for c, e in errores if c == correo), "") if es_error else ""
        borde     = "#d03b3b" if es_error else "#0ca30c"
        icono     = "✗" if es_error else "✓"
        ic_bg     = "#fde8e8" if es_error else "#e8f9e8"
        ic_color  = "#d03b3b" if es_error else "#0ca30c"
        filas_arch = "".join(
            f'<tr><td style="padding:2px 0 2px 8px;font-size:12px;'
            f'color:#52514e;font-family:monospace;">{f.name}</td></tr>'
            for f in archivos
        )
        if es_error:
            filas_arch += (
                f'<tr><td style="padding:4px 0 2px 8px;font-size:12px;'
                f'color:#d03b3b;font-weight:600;">Error: {err_msg}</td></tr>'
            )
        tarjetas_html += f"""
        <tr><td style="padding:6px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" style="border-left:3px solid {borde};
            background:#ffffff;border-radius:0 6px 6px 0;border:1px solid #e1e0d9;
            border-left:4px solid {borde};">
            <tr>
              <td width="36" style="padding:10px 10px 10px 14px;vertical-align:top;">
                <span style="display:inline-block;width:24px;height:24px;border-radius:50%;
                  background:{ic_bg};color:{ic_color};font-weight:700;font-size:14px;
                  text-align:center;line-height:24px;">{icono}</span>
              </td>
              <td style="padding:10px 14px 10px 0;vertical-align:top;">
                <div style="font-size:14px;font-weight:600;color:#0b0b0b;">{datos['nombre']}</div>
                <div style="font-size:12px;color:#898781;margin-top:1px;">{correo}
                  &nbsp;·&nbsp;
                  <span style="background:#f1efe8;border-radius:4px;padding:1px 7px;
                    font-size:11px;color:#52514e;">{len(archivos)} archivo{'s' if len(archivos)!=1 else ''}</span>
                </div>
                <table style="margin-top:6px;width:100%;" cellpadding="0" cellspacing="0">
                  {filas_arch}
                </table>
              </td>
            </tr>
          </table>
        </td></tr>"""

    # ── Sección de errores (si hay) ───────────────────────────────────────────
    seccion_errores = ""
    if n_err:
        seccion_errores = f"""
        <tr><td style="padding:24px 0 8px;">
          <div style="font-size:13px;font-weight:600;color:#d03b3b;
            text-transform:uppercase;letter-spacing:.05em;">
            ✗ Errores ({n_err})
          </div>
        </td></tr>"""

    # ── HTML completo ─────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1efe8;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1efe8;padding:32px 16px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

  <!-- HEADER -->
  <tr><td style="background:#0b0b0b;border-radius:10px 10px 0 0;padding:28px 32px;">
    <div style="font-size:11px;font-weight:600;color:#898781;letter-spacing:.1em;
      text-transform:uppercase;margin-bottom:6px;">SG Raíces · Control de obras</div>
    <div style="font-size:22px;font-weight:700;color:#ffffff;">
      Resumen envío semanal
    </div>
    <div style="font-size:13px;color:#c3c2b7;margin-top:4px;">
      Semana {semana} &nbsp;·&nbsp; {fecha_display}
    </div>
  </td></tr>

  <!-- KPI ROW -->
  <tr><td style="background:#ffffff;padding:0 32px;">
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
      <tr>
        <td width="33%" style="text-align:center;padding:16px 8px;
          background:#e8f9e8;border-radius:8px;margin:4px;">
          <div style="font-size:32px;font-weight:700;color:#0ca30c;">{n_ok}</div>
          <div style="font-size:11px;color:#3b6d11;font-weight:600;
            text-transform:uppercase;letter-spacing:.05em;">Enviados OK</div>
        </td>
        <td width="6px"></td>
        <td width="33%" style="text-align:center;padding:16px 8px;
          background:{'#fde8e8' if n_err else '#f1efe8'};border-radius:8px;">
          <div style="font-size:32px;font-weight:700;
            color:{'#d03b3b' if n_err else '#898781'};">{n_err}</div>
          <div style="font-size:11px;color:{'#a32d2d' if n_err else '#5f5e5a'};
            font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Errores</div>
        </td>
        <td width="6px"></td>
        <td width="33%" style="text-align:center;padding:16px 8px;
          background:#f1efe8;border-radius:8px;">
          <div style="font-size:32px;font-weight:700;color:#0b0b0b;">{n_total}</div>
          <div style="font-size:11px;color:#5f5e5a;font-weight:600;
            text-transform:uppercase;letter-spacing:.05em;">Archivos</div>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- CUERPO -->
  <tr><td style="background:#ffffff;padding:0 32px 28px;">
    <div style="height:1px;background:#e1e0d9;margin-bottom:20px;"></div>
    <div style="font-size:13px;font-weight:600;color:#0ca30c;
      text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px;">
      ✓ Envíos exitosos ({n_ok})
    </div>
    <table width="100%" cellpadding="0" cellspacing="0">
      {tarjetas_html}
      {seccion_errores}
    </table>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#0b0b0b;border-radius:0 0 10px 10px;
    padding:16px 32px;text-align:center;">
    <div style="font-size:11px;color:#52514e;">
      Generado automáticamente · Orquestador cloud SG Raíces
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""

    texto_plano = (
        f"Resumen envío semanal SG Raíces — Sem {semana} ({fecha_display})\n"
        f"Enviados OK: {n_ok}  |  Errores: {n_err}  |  Archivos: {n_total}\n\n"
        + "\n".join(
            f"{'OK' if c not in correos_error else 'ERROR'}  {d['nombre']} <{c}>  "
            f"({len(d['archivos'])} archivos)"
            for c, d in sorted(plan.items(), key=lambda x: x[1]["nombre"])
        )
    )

    msg = MIMEMultipart("alternative")
    msg["From"]    = f"SG Raices Control <{remitente}>"
    msg["To"]      = ADMIN_EMAIL
    msg["Subject"] = asunto
    msg.attach(MIMEText(texto_plano, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    time.sleep(3)  # pausa tras ráfaga de 16 correos para evitar rate limiting
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(remitente, app_pw)
        server.sendmail(remitente, [ADMIN_EMAIL], msg.as_string())

    print(f"  [Resumen] Correo de resumen enviado a {ADMIN_EMAIL}")


def main():
    fecha    = time.strftime("%Y%m%d")
    enviar   = os.environ.get("ENVIAR_CORREOS", "0") == "1"

    print(f"{'='*60}")
    print(f"Orquestador informes cloud — {fecha}")
    print(f"Modo: {'CAPTURA + ENVÍO' if enviar else 'CAPTURA DIARIA'}")
    print(f"{'='*60}\n")

    # ── 0. Escribir datos de despachos en Firebase (ANTES del capture) ────
    print("► Paso 0: Publicar despachos en Firebase")
    try:
        from inyectar_despachos import escribir_despachos_firebase
        escribir_despachos_firebase()
    except Exception as e:
        print(f"  [Despachos] ERROR en Paso 0: {e} — continuando sin despachos en Firebase")

    # ── 1. Capturar reportes ───────────────────────────────────────────────
    print("\n► Paso 1: Capturar reportes del dashboard")
    from capturar_informes_dashboard import main as capturar
    pdf_dir = capturar()

    # ── 1.5. Inyectar datos de despachos en el HTML de adquisiciones ──────
    print("\n► Paso 1.5: Inyectar proyección de despachos en informe adquisiciones")
    try:
        from inyectar_despachos import inyectar_resumen_despachos
        inyectar_resumen_despachos(pdf_dir, fecha)
    except Exception as e:
        print(f"  [Despachos] ERROR: {e} — continuando sin inyección")

    # ── 1.6. Actualizar dashboard en vivo con tab Despachos ───────────────
    print("\n► Paso 1.6: Actualizar dashboard en vivo (index_live_v3.html)")
    try:
        from inyectar_despachos import inyectar_en_dashboard
        inyectar_en_dashboard()
    except Exception as e:
        print(f"  [Dashboard] ERROR: {e} — continuando sin actualizar dashboard")

    # ── 2. Subir a Drive ───────────────────────────────────────────────────
    print("\n► Paso 2: Subir archivos a Google Drive")
    try:
        subir_a_drive(pdf_dir, fecha)
    except Exception as e:
        print(f"  [Drive] ERROR: {e} — continuando sin subida")

    # ── 3. Enviar correos (solo si ENVIAR_CORREOS=1) ────────────────────
    if enviar:
        print("\n► Paso 3: Enviar correos")
        from enviar_informes import main as enviar_correos
        resultado = enviar_correos(pdf_dir, fecha=fecha)

        print("\n► Paso 4: Enviar resumen al administrador")
        try:
            plan_enviado, errores_envio = resultado if resultado else ({}, [])
            _enviar_resumen_admin(plan_enviado, errores_envio, fecha)
        except Exception as e:
            print(f"  [Resumen] ERROR enviando resumen: {e}")
    else:
        print("\n► Paso 3: Envío omitido (modo diario)")

    print(f"\n{'='*60}")
    print("Orquestador finalizado OK")


if __name__ == "__main__":
    main()

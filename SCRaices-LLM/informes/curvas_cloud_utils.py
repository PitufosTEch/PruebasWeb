"""
curvas_cloud_utils.py
=====================
Utilidades compartidas para ejecución cloud de los scripts de Curvas S.

Modo CLOUD  — si existe la variable de entorno GOOGLE_REFRESH_TOKEN:
  - Credenciales Google desde env vars (sin archivo local)
  - OUTPUT_DIR   → directorio temporal del sistema
  - Drive IDs    → Firebase RTDB en /curvas_drive_ids/{nombre}
  - GitHub token → env var GITHUB_TOKEN
  - Log          → solo stdout

Modo LOCAL — sin GOOGLE_REFRESH_TOKEN:
  - Credenciales Google desde C:\\Users\\rodri\\.claude\\sheets_drive_token.json
  - OUTPUT_DIR   → G:\\... (Google Drive montado) o temp como fallback
  - Drive IDs    → drive_ids_{nombre}.json en OneDrive local
  - GitHub token → gh CLI o C:\\Users\\rodri\\.claude\\github_token.txt
  - Log          → stdout + archivo en C:\\Users\\rodri\\.claude\\logs\\
"""

import logging
import os
import json
import tempfile
from pathlib import Path

import requests
from googleapiclient.http import MediaFileUpload

# ─── RUTAS LOCALES ────────────────────────────────────────────────────────────
_LOCAL_TOKEN      = r"C:\Users\rodri\.claude\sheets_drive_token.json"
_LOCAL_OUTPUT     = (
    r"G:\.shortcut-targets-by-id\11lBqk00ApGZmO32OhDCJ6yjoOnzZniOI"
    r"\Coordinacion de Obras\SEGUIMIENTO DE OBRA\GANTT\Archivos de trabajo"
)
_LOCAL_IDS_DIR    = r"C:\Users\rodri\OneDrive\Documentos Claude Code"
_LOCAL_LOG_DIR    = r"C:\Users\rodri\.claude\logs"
_LOCAL_GH_TOKEN   = r"C:\Users\rodri\.claude\github_token.txt"

FIREBASE_URL = os.environ.get(
    "FIREBASE_URL",
    "https://scraices-dashboard-default-rtdb.firebaseio.com",
)

# Alias para compatibilidad con scripts que importan TOKEN_FILE directamente
TOKEN_FILE = _LOCAL_TOKEN

SCOPES_DEFAULT = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ─── DETECCIÓN DE ENTORNO ─────────────────────────────────────────────────────
def is_cloud() -> bool:
    """True si se está ejecutando en entorno cloud (GitHub Actions u otro)."""
    return bool(os.environ.get("GOOGLE_REFRESH_TOKEN"))


# ─── LOGGING ──────────────────────────────────────────────────────────────────
def setup_logging(nombre: str) -> logging.Logger:
    """
    Configura logging. Cloud → solo stdout. Local → stdout + archivo.
    Devuelve el logger configurado.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if not is_cloud():
        log_dir = Path(_LOCAL_LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"curvas_{nombre}.log"
        handlers.append(logging.FileHandler(str(log_file), encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(nombre)


# ─── CREDENCIALES GOOGLE ──────────────────────────────────────────────────────
def get_credentials(scopes=None):
    """
    Devuelve credenciales Google válidas.
    Cloud  → desde env vars GOOGLE_REFRESH_TOKEN / CLIENT_ID / CLIENT_SECRET.
    Local  → desde sheets_drive_token.json con renovación automática.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    _scopes = scopes or SCOPES_DEFAULT

    if is_cloud():
        creds = Credentials(
            token=None,
            refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            token_uri="https://oauth2.googleapis.com/token",
            scopes=_scopes,
        )
        creds.refresh(Request())
        return creds

    # Modo local
    creds = Credentials.from_authorized_user_file(_LOCAL_TOKEN, _scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(_LOCAL_TOKEN, "w") as f:
            f.write(creds.to_json())
    return creds


# ─── DIRECTORIO DE SALIDA ─────────────────────────────────────────────────────
def get_output_dir() -> str:
    """
    Directorio donde se guardan los PNG generados.
    Cloud  → directorio temporal (los PNG se suben a Drive y se eliminan).
    Local  → G:\\... si existe, sino temporal.
    """
    if is_cloud():
        return tempfile.mkdtemp(prefix="curvas_s_")

    if Path(_LOCAL_OUTPUT).exists():
        return _LOCAL_OUTPUT

    # G: no disponible (computador sin Drive montado)
    tmp = tempfile.mkdtemp(prefix="curvas_s_")
    logging.getLogger("curvas_cloud_utils").warning(
        f"G: no disponible — usando directorio temporal: {tmp}"
    )
    return tmp


# ─── DRIVE IDs ────────────────────────────────────────────────────────────────
def _fb_key(filename: str) -> str:
    """Convierte nombre de archivo en clave Firebase-safe (sin puntos)."""
    return filename.replace(".", "_DOT_")


def _fb_key_restore(key: str) -> str:
    """Restaura clave Firebase a nombre de archivo original."""
    return key.replace("_DOT_", ".")


def load_drive_ids(nombre: str, defaults: dict = None) -> dict:
    """
    Carga Drive IDs.
    Cloud  → Firebase RTDB en /curvas_drive_ids/{nombre}.
    Local  → drive_ids_{nombre}.json en OneDrive local.
    Fallback: `defaults` si ninguna fuente tiene datos.
    """
    _defaults = defaults or {}

    if is_cloud():
        url = f"{FIREBASE_URL}/curvas_drive_ids/{nombre}.json"
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if data:
                    restored = {_fb_key_restore(k): v for k, v in data.items()}
                    logging.getLogger("curvas_cloud_utils").info(
                        f"Drive IDs leídos desde Firebase ({nombre}): {len(restored)} archivos."
                    )
                    return restored
        except Exception as e:
            logging.getLogger("curvas_cloud_utils").warning(
                f"Firebase no disponible para {nombre}: {e}"
            )
        return dict(_defaults)

    # Modo local
    local_file = Path(_LOCAL_IDS_DIR) / f"drive_ids_{nombre}.json"
    if local_file.exists():
        with open(local_file, encoding="utf-8") as f:
            return json.load(f)
    return dict(_defaults)


# ─── DRIVE ORGANIZADO ─────────────────────────────────────────────────────────
_DRIVE_CURVAS_BASE   = "Archivos Dashboard"
_DRIVE_CURVAS_FOLDER = "Curvas PNG"


def get_output_dir_obra(obra_folder: str) -> str:
    """
    Directorio local donde se guardan los PNG de un proyecto antes de subir a Drive.
    Cloud  → carpeta temporal del sistema.
    Local  → G:\\Mi unidad\\Archivos Dashboard\\Curvas PNG\\{obra_folder} (se crea si no existe).
    """
    if is_cloud():
        return tempfile.mkdtemp(prefix=f"curvas_{obra_folder}_")
    base = Path(r"G:\Mi unidad\Archivos Dashboard\Curvas PNG") / obra_folder
    try:
        base.mkdir(parents=True, exist_ok=True)
        return str(base)
    except Exception:
        tmp = tempfile.mkdtemp(prefix=f"curvas_{obra_folder}_")
        logging.getLogger("curvas_cloud_utils").warning(
            f"Ruta local no disponible — usando temp: {tmp}"
        )
        return tmp


def _get_or_create_drive_folder(drive_svc, nombre: str, parent_id: str = None) -> str:
    """Busca carpeta por nombre en Drive (bajo parent_id o en root). Crea si no existe."""
    q = f"mimeType='application/vnd.google-apps.folder' and name='{nombre}' and trashed=false"
    q += f" and '{parent_id}' in parents" if parent_id else " and 'root' in parents"
    res = drive_svc.files().list(q=q, fields="files(id)", pageSize=5).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    body = {"name": nombre, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    folder = drive_svc.files().create(body=body, fields="id").execute()
    logging.getLogger("curvas_cloud_utils").info(
        f"Carpeta Drive creada: '{nombre}' → id={folder['id']}"
    )
    return folder["id"]


def actualizar_drive_organizado(
    drive_svc, outdir: str, chart_names: list,
    obra_folder: str, nombre_ccu: str
) -> dict:
    """
    Sube los PNGs de un proyecto a:
      Mi unidad / Archivos Dashboard / Curvas PNG / {obra_folder} /

    Lógica de reemplazo sin acumulación:
    - Archivo con ID guardado → actualiza contenido in-place (mismo ID → misma URL →
      fórmulas IMAGE() siguen funcionando). Si estaba en carpeta incorrecta, lo mueve.
    - Archivo sin ID (primera vez o ID perdido) → crea en la carpeta correcta.

    Persiste IDs (Firebase en cloud, JSON en local) y retorna dict {filename: drive_id}.
    """
    _log = logging.getLogger("curvas_cloud_utils")
    _log.info(f"Drive → {_DRIVE_CURVAS_BASE}/{_DRIVE_CURVAS_FOLDER}/{obra_folder} ...")

    # Navegar / crear estructura de carpetas
    parent_id = _get_or_create_drive_folder(drive_svc, _DRIVE_CURVAS_BASE)
    curvas_id = _get_or_create_drive_folder(drive_svc, _DRIVE_CURVAS_FOLDER, parent_id)
    obra_id   = _get_or_create_drive_folder(drive_svc, obra_folder, curvas_id)

    drive_ids = load_drive_ids(nombre_ccu)
    nuevos: dict = {}

    for chart_name in chart_names:
        path = Path(outdir) / chart_name
        if not path.exists():
            _log.warning(f"  No encontrado: {chart_name}, saltando.")
            continue

        media       = MediaFileUpload(str(path), mimetype="image/png", resumable=False)
        existing_id = drive_ids.get(chart_name, "")

        if existing_id:
            try:
                meta    = drive_svc.files().get(fileId=existing_id, fields="parents").execute()
                parents = meta.get("parents", [])
                if obra_id in parents:
                    drive_svc.files().update(fileId=existing_id, media_body=media).execute()
                    _log.info(f"  Actualizado in-place: {chart_name}")
                else:
                    kw = dict(fileId=existing_id, media_body=media,
                              addParents=obra_id, fields="id")
                    if parents:
                        kw["removeParents"] = ",".join(parents)
                    drive_svc.files().update(**kw).execute()
                    _log.info(f"  Movido + actualizado: {chart_name}")
                nuevos[chart_name] = existing_id
                continue
            except Exception as exc:
                _log.warning(f"  update() falló ({exc}), recreando {chart_name}...")

        # Crear nuevo en carpeta correcta
        res = drive_svc.files().create(
            body={"name": chart_name, "mimeType": "image/png", "parents": [obra_id]},
            media_body=media, fields="id"
        ).execute()
        new_id = res["id"]
        drive_svc.permissions().create(
            fileId=new_id, body={"type": "anyone", "role": "reader"},
        ).execute()
        nuevos[chart_name] = new_id
        _log.info(f"  Creado nuevo: {chart_name} → id={new_id}")

    drive_ids.update(nuevos)
    save_drive_ids(nombre_ccu, drive_ids)
    return drive_ids


def save_drive_ids(nombre: str, ids: dict) -> None:
    """
    Guarda Drive IDs.
    Cloud  → Firebase RTDB en /curvas_drive_ids/{nombre}.
    Local  → drive_ids_{nombre}.json en OneDrive local.
    """
    if is_cloud():
        url = f"{FIREBASE_URL}/curvas_drive_ids/{nombre}.json"
        try:
            safe_ids = {_fb_key(k): v for k, v in ids.items()}
            r = requests.put(url, json=safe_ids, timeout=20)
            r.raise_for_status()
            logging.getLogger("curvas_cloud_utils").info(
                f"Drive IDs guardados en Firebase ({nombre}): {len(ids)} archivos."
            )
        except Exception as e:
            logging.getLogger("curvas_cloud_utils").error(
                f"Error guardando Drive IDs en Firebase ({nombre}): {e}"
            )
        return

    # Modo local
    local_file = Path(_LOCAL_IDS_DIR) / f"drive_ids_{nombre}.json"
    with open(local_file, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2, ensure_ascii=False)
    logging.getLogger("curvas_cloud_utils").info(
        f"Drive IDs guardados en {local_file}"
    )


# ─── TOKEN GITHUB ─────────────────────────────────────────────────────────────
def get_github_token() -> str | None:
    """
    Obtiene el token de GitHub.
    Cloud  → env var GITHUB_TOKEN.
    Local  → gh CLI o archivo github_token.txt.
    """
    # Env var (cloud y local)
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok

    # gh CLI (local)
    try:
        import subprocess
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            tok = result.stdout.strip()
            if tok:
                return tok
    except Exception:
        pass

    # Archivo manual (local fallback)
    token_path = Path(_LOCAL_GH_TOKEN)
    if token_path.exists():
        tok = token_path.read_text().strip()
        if tok:
            return tok

    return None

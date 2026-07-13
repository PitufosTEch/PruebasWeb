"""
sincronizar_tipologias.py
=========================
Extrae tipologías de AppSheet (IndexedDB) con Playwright y las escribe
a Firebase RTDB en /tipologias_sync.

Usa la misma autenticación que leer_appsheet.py (APPSHEET_COOKIES_B64).
"""

import base64
import datetime
import json
import logging
import os
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

APPSHEET_URL = "https://www.appsheet.com/start/e07d4aa1-e59e-4b9b-bf4c-32582e74e8fc?platform=desktop"
FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://scraices-dashboard-default-rtdb.firebaseio.com")
AUTH_FILE    = str(Path.home() / ".claude" / "appsheet_auth.json")

# Mismo wait que leer_appsheet.py — espera que carguen los beneficiarios (tabla 4)
JS_WAIT = """
() => {
    try {
        if (typeof AppModel === 'undefined') return false;
        var t = AppModel.Tables[4];
        if (!t || !t.Rows) return false;
        return Object.keys(t.Rows).length > 50;
    } catch(e) { return false; }
}
"""

# Extrae tipologías desde IndexedDB.  Mismo algoritmo que el SYNC_SCRIPT
# del estado_proyectos.html pero devuelve el objeto en vez de copiarlo.
JS_EXTRACT = """
async () => {
  const DB = 'e07d4aa1-e59e-4b9b-bf4c-32582e74e8fc||519201981|';

  async function dec(rec) {
    const b  = new Uint8Array(rec.data);
    const ds = new DecompressionStream('deflate');
    const w  = ds.writable.getWriter(), r = ds.readable.getReader();
    w.write(b); w.close();
    const parts = [];
    for (;;) { const {done, value} = await r.read(); if (done) break; parts.push(value); }
    const tot = parts.reduce((s, c) => s + c.length, 0);
    const out = new Uint8Array(tot); let off = 0;
    for (const p of parts) { out.set(p, off); off += p.length; }
    return JSON.parse(new TextDecoder().decode(out));
  }

  const db = await new Promise((ok, er) => {
    const q = indexedDB.open(DB);
    q.onsuccess = e => ok(e.target.result);
    q.onerror   = e => er(e.target.error);
  });

  async function getKey(k) {
    return new Promise((ok, er) => {
      const tx  = db.transaction('keyvaluepairs', 'readonly');
      const req = tx.objectStore('keyvaluepairs').get(k);
      req.onsuccess = e => ok(e.target.result);
      req.onerror   = e => er(e.target.error);
    });
  }

  let tRows = [], pRows = [], bRows = [];
  for (let i = 0; i < 3;  i++) { try { const r = await getKey('Tipologias~#'  + i); if (r) tRows.push(...await dec(r)); } catch(e) {} }
  for (let i = 0; i < 2;  i++) { try { const r = await getKey('Proyectos~#'   + i); if (r) pRows.push(...await dec(r)); } catch(e) {} }
  for (let i = 0; i < 20; i++) { try { const r = await getKey('Beneficiario~#' + i); if (r) bRows.push(...await dec(r)); } catch(e) {} }
  db.close();

  const tipMap = {};
  for (const t of tRows) { if (t[1]) tipMap[t[1]] = {code:t[2], tipo:t[3], dorm:+t[7]||0, fam:t[9]||''}; }

  const projMap = {};
  for (const p of pRows) { if (p[1] && p[3]) projMap[p[1]] = p[3]; }

  function bodDesc(code) {
    if (!code) return '';
    if (/RC1700/.test(code))   return '17.0m2 Madera';
    if (/RC1600/.test(code))   return '16.0m2 Madera';
    if (/RC144013/.test(code)) return '14.4m2 Acero';
    if (/RC1440/.test(code))   return '14.4m2 Madera';
    if (/^AM/.test(code))      return '17.0m2 Madera';
    if (/FM13/.test(code))     return '14.4m2 Acero';
    if (/FM12/.test(code))     return '14.4m2 Madera';
    if (/EM14|FM14/.test(code))return '16.0m2 Madera';
    return code;
  }

  const byProj = {};
  for (const b of bRows) {
    const name = projMap[b[2]]; if (!name) continue;
    if (!byProj[name]) byProj[name] = {viv:{}, rc:{}};
    if (b[10]) byProj[name].viv[b[10]] = (byProj[name].viv[b[10]] || 0) + 1;
    if (b[11]) byProj[name].rc[b[11]]  = (byProj[name].rc[b[11]]  || 0) + 1;
  }

  const result = {};
  for (const [name, d] of Object.entries(byProj)) {
    const e = {tipVivBase:'',cantVivBase:0,tipViv3D:'',cantViv3D:0,
                tipDisc2D:'',cantDisc2D:0,tipDisc3D:'',cantDisc3D:0,tipRC:'',cantRC:0};
    for (const [h, cnt] of Object.entries(d.viv)) {
      const t = tipMap[h]; if (!t) continue;
      if (t.fam==='Vivienda'       && t.dorm===2) { if (!e.tipVivBase) e.tipVivBase=t.code; e.cantVivBase+=cnt; }
      else if (t.fam==='Vivienda'  && t.dorm===3) { if (!e.tipViv3D)   e.tipViv3D=t.code;   e.cantViv3D+=cnt; }
      else if (t.fam==='Vivienda Disc.' && t.dorm===2) { if (!e.tipDisc2D) e.tipDisc2D=t.code; e.cantDisc2D+=cnt; }
      else if (t.fam==='Vivienda Disc.' && t.dorm===3) { if (!e.tipDisc3D) e.tipDisc3D=t.code; e.cantDisc3D+=cnt; }
      else if (!e.tipVivBase) { e.tipVivBase=t.code; e.cantVivBase+=cnt; }
    }
    if (!e.tipVivBase && e.tipViv3D) {
      e.tipVivBase=e.tipViv3D; e.cantVivBase=e.cantViv3D; e.tipViv3D=''; e.cantViv3D=0;
    }
    for (const [h, cnt] of Object.entries(d.rc)) {
      const t = tipMap[h]; if (!t) continue;
      e.tipRC = bodDesc(t.code); e.cantRC += cnt;
    }
    result[name] = e;
  }
  return result;
}
"""


def _abrir_appsheet_con_auth(pw, storage_state):
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    ctx  = browser.new_context(storage_state=storage_state)
    page = ctx.new_page()

    log.info("Navegando a AppSheet...")
    page.goto(APPSHEET_URL, wait_until="domcontentloaded", timeout=60_000)

    url = page.url
    if "accounts.google.com" in url or "signin" in url.lower():
        raise RuntimeError(
            "AppSheet redirigió a Google login — sesión expirada. "
            "Regenera APPSHEET_COOKIES_B64 con: python leer_appsheet.py --setup"
        )

    log.info("Esperando que AppSheet cargue datos (hasta 150s)...")
    page.wait_for_function(JS_WAIT, timeout=150_000)
    page.wait_for_timeout(3_000)   # margen extra para que IndexedDB sincronice

    log.info("Extrayendo tipologías desde IndexedDB...")
    result = page.evaluate(JS_EXTRACT)

    ctx.close()
    browser.close()
    return result


def extraer_tipologias() -> dict:
    cookies_b64 = os.environ.get("APPSHEET_COOKIES_B64", "").strip()

    if cookies_b64:
        log.info("Modo cloud: usando APPSHEET_COOKIES_B64")
        cookies_json   = base64.b64decode(cookies_b64).decode("utf-8")
        storage_state  = json.loads(cookies_json)
        if "origins" not in storage_state:
            storage_state["origins"] = []
    elif os.path.exists(AUTH_FILE):
        log.info(f"Modo local: usando {AUTH_FILE}")
        storage_state = AUTH_FILE
    else:
        raise RuntimeError(
            "No hay autenticación disponible.\n"
            "  Cloud: configura APPSHEET_COOKIES_B64 como GitHub Secret\n"
            "  Local: ejecuta python leer_appsheet.py --setup"
        )

    with sync_playwright() as pw:
        return _abrir_appsheet_con_auth(pw, storage_state)


def escribir_firebase(data: dict):
    url = f"{FIREBASE_URL}/tipologias_sync.json"
    payload = {
        "_updated": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": data,
    }
    r = requests.put(url, json=payload, timeout=30)
    r.raise_for_status()
    log.info(f"Firebase actualizado: {len(data)} proyectos → tipologias_sync")


def main():
    result = extraer_tipologias()
    if not result:
        raise RuntimeError("Sin datos de tipologías (resultado vacío)")
    log.info(f"Extraídos: {len(result)} proyectos")
    escribir_firebase(result)
    print(json.dumps({"status": "ok", "proyectos": len(result)}, ensure_ascii=False))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    try:
        main()
    except Exception as e:
        log.error(f"Error fatal: {e}")
        sys.exit(1)

"""
sincronizar_soldespachos.py
============================
Lee tabla Despacho desde AppSheet (AppModel.Tables via Playwright),
filtra registros con Fecha >= hoy (despachos futuros planificados),
une capataz desde Firebase /grupos.json,
y escribe el resultado en Firebase RTDB bajo /despachos_data/{pid}.

Uso:
  python sincronizar_soldespachos.py              # sync normal (ventana 28 días)
  python sincronizar_soldespachos.py --inspect    # muestra campos y primeras filas
  python sincronizar_soldespachos.py --ventana 60 # ventana de N días (default: 28)
"""

import argparse
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

APPSHEET_URL  = "https://www.appsheet.com/start/e07d4aa1-e59e-4b9b-bf4c-32582e74e8fc?platform=desktop"
FIREBASE_URL  = os.environ.get("FIREBASE_URL", "https://scraices-dashboard-default-rtdb.firebaseio.com")
AUTH_FILE     = str(Path.home() / ".claude" / "appsheet_auth.json")

VENTANA_DIAS_DEFAULT = 28

# ── JS: espera que Beneficiario (tabla 4) tenga filas ─────────────────────────
JS_WAIT = r"""
() => {
    try {
        if (typeof AppModel === 'undefined') return false;
        var t = AppModel.Tables[4];
        if (!t || !t.Rows) return false;
        return Object.keys(t.Rows).length > 50;
    } catch(e) { return false; }
}
"""

# ── JS: extrae despachos con Fecha futura desde AppModel.Tables ───────────────
# Usa raw string (r"""...""") para evitar warning de Python con \d en JS.
JS_EXTRACT = r"""
(ventanaDias) => {
    // ── 1. Encontrar tabla con campo Fecha y Tipo_despacho ────────────────
    var despIdx = -1;
    var camposDisponibles = [];
    var muestraFila = null;

    for (var i = 0; i < AppModel.Tables.length; i++) {
        var tbl = AppModel.Tables[i];
        if (!tbl || !tbl.Rows) continue;
        var keys = Object.keys(tbl.Rows);
        if (keys.length === 0) continue;
        var row0 = tbl.Rows[keys[0]];
        // Buscar tabla con IDU_desp O IDU_soldesp
        if ('IDU_desp' in row0 || 'IDU_soldesp' in row0) {
            if (despIdx < 0) {
                despIdx = i;
                camposDisponibles = Object.keys(row0);
                muestraFila = row0;
            }
        }
    }

    // ── 2. Leer Beneficiario (tabla 4) para nombre ────────────────────────
    var benMap = {};
    var tblBen = AppModel.Tables[4];
    if (tblBen && tblBen.Rows) {
        Object.values(tblBen.Rows).forEach(function(b) {
            var idB = String(b.ID_Benef || b.IDU_ben || '');
            if (!idB) return;
            var nom = String(b['Nombre completo'] || '').trim();
            if (!nom) nom = ((b.APELLIDOS || '') + ' ' + (b.NOMBRES || '')).toUpperCase().trim();
            benMap[idB] = {
                nombre: nom,
                ID_proy: String(b.ID_Proy || b.ID_proy || '')
            };
        });
    }

    // ── 3. Parsear fecha ───────────────────────────────────────────────────
    function parseDate(v) {
        if (!v) return null;
        var s = String(v).trim();
        if (!s || s === '—' || s === '-') return null;
        var d;
        if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
            d = new Date(s.substring(0, 10));
        } else if (/^\d{2}\/\d{2}\/\d{4}$/.test(s)) {
            var p = s.split('/');
            // DD/MM/YYYY (formato chileno)
            d = new Date(p[2] + '-' + p[1] + '-' + p[0]);
            if (isNaN(d.getTime())) d = new Date(p[2] + '-' + p[0] + '-' + p[1]);
        } else {
            d = new Date(s);
        }
        return isNaN(d.getTime()) ? null : d;
    }

    // ── 4. Filtrar registros futuros ───────────────────────────────────────
    var hoy = new Date();
    hoy.setHours(0,0,0,0);
    var limFin = new Date(hoy.getTime() + ventanaDias * 86400000);

    var registros = [];
    if (despIdx >= 0) {
        var tblDesp = AppModel.Tables[despIdx];
        Object.values(tblDesp.Rows).forEach(function(row) {
            var fv = row['Fecha'];
            var fd = parseDate(fv);
            if (!fd) return;
            if (fd < hoy || fd > limFin) return;

            var idB  = String(row['ID_Benef'] || '');
            var idP  = String(row['ID_proy']  || row['ID_Proy'] || '');
            var tipo = String(row['Tipo_despacho'] || '').trim();
            var nom  = String(row['Nombre completo'] || '').trim();
            if (!nom && benMap[idB]) nom = benMap[idB].nombre;
            if (!idP && benMap[idB]) idP = benMap[idB].ID_proy;
            var nomProy = String(row['Nombre proyecto'] || '').trim();
            var fechaStr = fd.toISOString().substring(0, 10);

            registros.push({
                IDU: String(row['IDU_desp'] || row['IDU_soldesp'] || ''),
                ID_Benef: idB,
                ID_proy:  idP,
                nombre:   nom,
                nombre_proy: nomProy,
                tipo:     tipo,
                fecha:    fechaStr
            });
        });
    }

    return {
        despIdx:           despIdx,
        camposDisponibles: camposDisponibles,
        muestraFila:       muestraFila,
        registros:         registros
    };
}
"""


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_storage_state():
    cookies_b64 = os.environ.get("APPSHEET_COOKIES_B64", "").strip()
    if cookies_b64:
        log.info("Modo cloud: usando APPSHEET_COOKIES_B64")
        ss = json.loads(base64.b64decode(cookies_b64).decode("utf-8"))
        if "origins" not in ss:
            ss["origins"] = []
        return ss
    if os.path.exists(AUTH_FILE):
        log.info(f"Modo local: usando {AUTH_FILE}")
        return AUTH_FILE
    raise RuntimeError(
        "Sin autenticación disponible.\n"
        "  Cloud: configura APPSHEET_COOKIES_B64\n"
        "  Local: ejecuta python leer_appsheet.py --setup"
    )


def _abrir_appsheet(pw, storage_state, ventana_dias: int):
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx  = browser.new_context(storage_state=storage_state)
    page = ctx.new_page()

    log.info("Navegando a AppSheet...")
    page.goto(APPSHEET_URL, wait_until="domcontentloaded", timeout=60_000)

    if "accounts.google.com" in page.url or "signin" in page.url.lower():
        raise RuntimeError("Sesión expirada. Ejecuta: python leer_appsheet.py --setup")

    log.info("Esperando AppModel (hasta 150s)...")
    page.wait_for_function(JS_WAIT, timeout=150_000)
    page.wait_for_timeout(4_000)

    log.info("Extrayendo despachos futuros...")
    result = page.evaluate(JS_EXTRACT, ventana_dias)
    ctx.close()
    browser.close()
    return result


def extraer_despachos(ventana_dias: int) -> dict:
    ss = _get_storage_state()
    with sync_playwright() as pw:
        return _abrir_appsheet(pw, ss, ventana_dias)


# ── Capataz desde Firebase /grupos.json ───────────────────────────────────────

def _cargar_capataz_map() -> dict:
    """Retorna {ID_Benef: capataz} leyendo /grupos.json de Firebase."""
    try:
        r = requests.get(f"{FIREBASE_URL}/grupos.json", timeout=15)
        r.raise_for_status()
        grupos_raw = r.json() or {}
    except Exception as e:
        log.warning(f"No se pudo cargar grupos.json: {e}")
        return {}

    cap_map = {}
    for pid, grps in grupos_raw.items():
        if not isinstance(grps, list):
            continue
        for g in grps:
            cap = g.get("capataz", "")
            for bid in g.get("beneficiarios", []):
                if bid and cap:
                    cap_map[str(bid)] = cap
    log.info(f"Capataz map: {len(cap_map)} beneficiarios")
    return cap_map


# ── Normalizar tipo de despacho ───────────────────────────────────────────────

def _normalizar_tipo(tipo: str) -> list:
    """
    'Tipo_despacho' puede traer múltiples etapas separadas por ' , '.
    Retorna lista de etiquetas normalizadas.
    """
    import re
    partes = [p.strip() for p in re.split(r'\s*,\s*', tipo) if p.strip()]
    resultado = []
    for p in partes:
        # Intentar extraer número de etapa: "28- Ventanas" → "28 Ventanas"
        m = re.match(r'^(\d+)-?\s*(.+)$', p)
        if m:
            num = m.group(1).zfill(2)
            nom = m.group(2).strip()
            resultado.append(f"{num} {nom}")
        else:
            resultado.append(p)
    return resultado


# ── Construcción payload Firebase ─────────────────────────────────────────────

def construir_payload(registros: list, cap_map: dict, ventana_dias: int) -> dict:
    hoy    = datetime.date.today()
    fin    = hoy + datetime.timedelta(days=ventana_dias)

    def mes_str(d: datetime.date) -> str:
        meses = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        return f"{meses[d.month-1]} {d.year}"

    periodo = mes_str(hoy) if mes_str(hoy) == mes_str(fin) else f"{mes_str(hoy)}–{mes_str(fin)}"

    # Deduplicar por IDU (mismo despacho puede aparecer varias veces)
    vistos: set = set()
    registros_uniq = []
    for r in registros:
        key = r.get("IDU") or f"{r['ID_Benef']}|{r['tipo']}|{r['fecha']}"
        if key not in vistos:
            vistos.add(key)
            registros_uniq.append(r)
    registros = registros_uniq

    # pid → id_benef → {nombre, capataz, etapas: set}
    por_proy: dict = {}
    for r in registros:
        pid = r["ID_proy"]
        idB = r["ID_Benef"]
        if not pid or not idB:
            continue
        if pid not in por_proy:
            por_proy[pid] = {}
        if idB not in por_proy[pid]:
            por_proy[pid][idB] = {
                "nombre":  r["nombre"] or idB,
                "capataz": cap_map.get(idB, ""),
                "etapas":  []
            }
        for et in _normalizar_tipo(r["tipo"]):
            if et not in por_proy[pid][idB]["etapas"]:
                por_proy[pid][idB]["etapas"].append(et)

    payload = {}
    for pid, bens in por_proy.items():
        bens_list = []
        for idB, info in bens.items():
            etapas_str = ", ".join(f"[SOL] {e}" for e in info["etapas"]) if info["etapas"] else "[SOL] Despacho programado"
            bens_list.append({
                "nombre":  info["nombre"],
                "capataz": info["capataz"],
                "mes1":    etapas_str
            })
        payload[pid] = {
            "titulo":        pid,
            "meses":         [periodo],
            "beneficiarios": bens_list
        }

    return payload


# ── Firebase ──────────────────────────────────────────────────────────────────

def escribir_firebase(payload: dict) -> bool:
    try:
        resp = requests.put(f"{FIREBASE_URL}/despachos_data.json", json=payload, timeout=30)
        resp.raise_for_status()
        n_bens = sum(len(v["beneficiarios"]) for v in payload.values())
        log.info(f"Firebase /despachos_data actualizado: {len(payload)} proyectos, {n_bens} beneficiarios")
        return True
    except Exception as e:
        log.error(f"ERROR Firebase: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sincronizar despachos futuros AppSheet → Firebase")
    parser.add_argument("--inspect",  action="store_true", help="Solo inspecciona; no escribe Firebase")
    parser.add_argument("--ventana",  type=int, default=VENTANA_DIAS_DEFAULT,
                        help=f"Días hacia adelante (default: {VENTANA_DIAS_DEFAULT})")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

    log.info(f"Extrayendo despachos futuros (ventana: {args.ventana} días)...")
    data = extraer_despachos(args.ventana)

    log.info(f"Tabla despachos en índice AppModel: {data['despIdx']}")
    log.info(f"Registros encontrados en ventana:   {len(data['registros'])}")

    if args.inspect or data["despIdx"] < 0:
        print("\n=== INSPECCIÓN ===")
        print(f"Índice tabla: {data['despIdx']}")
        print(f"Campos: {json.dumps(data['camposDisponibles'], ensure_ascii=False, indent=2)}")
        if data["muestraFila"]:
            safe = {k: str(v) for k, v in (data["muestraFila"] or {}).items()}
            print(f"\nMuestra (primer registro):\n{json.dumps(safe, ensure_ascii=False, indent=2)}")
        print(f"\nPrimeros 5 registros en ventana:")
        for r in data["registros"][:5]:
            print(f"  {json.dumps(r, ensure_ascii=False)}")
        if data["despIdx"] < 0:
            log.error("No se encontró tabla de despachos en AppModel")
            sys.exit(1)
        return

    cap_map = _cargar_capataz_map()
    payload = construir_payload(data["registros"], cap_map, args.ventana)
    n_bens  = sum(len(v["beneficiarios"]) for v in payload.values())
    log.info(f"Payload construido: {len(payload)} proyectos, {n_bens} beneficiarios")

    for pid, v in payload.items():
        log.info(f"  {pid}: {len(v['beneficiarios'])} beneficiarios")

    ok = escribir_firebase(payload)
    print(json.dumps({
        "status":       "ok" if ok else "error",
        "proyectos":    len(payload),
        "beneficiarios": n_bens
    }, ensure_ascii=False))

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

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
    // ── 1. Encontrar tabla soldepacho (IDU_soldesp) ───────────────────────
    var solIdx = -1;
    var camposDisponibles = [];
    var muestraFila = null;

    for (var i = 0; i < AppModel.Tables.length; i++) {
        var tbl = AppModel.Tables[i];
        if (!tbl || !tbl.Rows) continue;
        var keys = Object.keys(tbl.Rows);
        if (keys.length === 0) continue;
        var row0 = tbl.Rows[keys[0]];
        if ('IDU_soldesp' in row0) {
            solIdx = i;
            camposDisponibles = Object.keys(row0);
            muestraFila = row0;
            break;
        }
    }

    // ── 2. Leer Beneficiario (tabla 4) para nombre y proyecto ────────────
    var benMap = {};
    var tblBen = AppModel.Tables[4];
    if (tblBen && tblBen.Rows) {
        Object.values(tblBen.Rows).forEach(function(b) {
            var idB = String(b.ID_Benef || b.IDU_ben || '');
            if (!idB) return;
            var nom = ((b.APELLIDOS || '') + ' ' + (b.NOMBRES || '')).toUpperCase().trim();
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
            d = new Date(p[2] + '-' + p[1] + '-' + p[0]);
            if (isNaN(d.getTime())) d = new Date(p[2] + '-' + p[0] + '-' + p[1]);
        } else {
            d = new Date(s);
        }
        return isNaN(d.getTime()) ? null : d;
    }

    // ── 4. Ventana: lunes al viernes de la semana actual ──────────────────
    var hoy = new Date();
    hoy.setHours(0,0,0,0);
    // Si ventanaDias > 0 → usar ventana genérica; si = 0 → semana actual (lun-vie)
    var limIni, limFin;
    if (ventanaDias === 0) {
        var dow = hoy.getDay();  // 0=dom,1=lun,...,6=sab
        var diffLun = (dow === 0) ? -6 : 1 - dow;
        limIni = new Date(hoy.getTime() + diffLun * 86400000);
        limFin = new Date(limIni.getTime() + 4 * 86400000);  // viernes
    } else {
        limIni = hoy;
        limFin = new Date(hoy.getTime() + ventanaDias * 86400000);
    }

    // ── 5. Identificar campo "Fecha a despachar" ──────────────────────────
    var CANDIDATOS_FECHA = [
        'Fecha a despachar', 'Fecha_a_despachar', 'fecha_a_despachar',
        'Fecha_despacho', 'fecha_despacho', 'FechaDespacho',
        'fecha_programada', 'Fecha_programada', 'Fecha', 'fecha'
    ];
    var campoFecha = null;
    for (var ci = 0; ci < CANDIDATOS_FECHA.length; ci++) {
        if (camposDisponibles.indexOf(CANDIDATOS_FECHA[ci]) >= 0) {
            campoFecha = CANDIDATOS_FECHA[ci];
            break;
        }
    }

    // ── 6. Identificar campo tipo de despacho ─────────────────────────────
    var CANDIDATOS_TIPO = ['Tipo_despacho', 'tipo_despacho', 'etapa', 'Etapa', 'Tipo', 'tipo'];
    var campoTipo = null;
    for (var ti = 0; ti < CANDIDATOS_TIPO.length; ti++) {
        if (camposDisponibles.indexOf(CANDIDATOS_TIPO[ti]) >= 0) {
            campoTipo = CANDIDATOS_TIPO[ti];
            break;
        }
    }

    // ── 7. Filtrar registros en ventana + vencidos pendientes ────────────────
    var registros = [];   // dentro de la semana actual (excepto Despachado)
    var vencidos  = [];   // fecha < lunes actual, Estado=Pendiente
    if (solIdx >= 0 && campoFecha) {
        var tblSol = AppModel.Tables[solIdx];
        Object.values(tblSol.Rows).forEach(function(row) {
            var fv = row[campoFecha];
            var fd = parseDate(fv);
            if (!fd) return;
            fd.setHours(0,0,0,0);

            var est1 = String(row['Estado']   || '').trim().toLowerCase();
            var est2 = String(row['Estado 2'] || '').trim().toLowerCase();
            // Nunca incluir los ya completamente despachados
            if (est1 === 'despachado' || est2 === 'despachado') return;

            var idB      = String(row['ID_Benef'] || row['ID_benef'] || '');
            var idP      = String(row['ID_proy']  || row['ID_Proy']  || '');
            var tipo     = campoTipo ? String(row[campoTipo] || '').trim() : '';
            var ben      = benMap[idB] || {};
            var nom      = String(row['Nombre'] || ben.nombre || idB).trim();
            if (!nom) nom = ben.nombre || idB;
            if (!idP && ben.ID_proy) idP = ben.ID_proy;
            var fechaStr = fd.toISOString().substring(0, 10);
            var desc     = String(row['Elemento pendiente'] || row['elemento_pendiente'] || '').trim();

            if (fd >= limIni && fd <= limFin) {
                // Despacho programado para esta semana
                registros.push({
                    IDU:         String(row['IDU_soldesp'] || ''),
                    ID_Benef:    idB,
                    ID_proy:     idP,
                    nombre:      nom,
                    tipo:        tipo,
                    fecha:       fechaStr,
                    descripcion: desc
                });
            } else if (fd < limIni && (est1 === 'pendiente' || est2 === 'pendiente')) {
                // Pendiente vencido: debió despacharse antes de esta semana
                vencidos.push({
                    IDU:         String(row['IDU_soldesp'] || ''),
                    ID_Benef:    idB,
                    ID_proy:     idP,
                    nombre:      nom,
                    tipo:        tipo,
                    fecha:       fechaStr,
                    descripcion: desc
                });
            }
        });
    }

    return {
        solIdx:            solIdx,
        camposDisponibles: camposDisponibles,
        campoFecha:        campoFecha,
        campoTipo:         campoTipo,
        muestraFila:       muestraFila,
        limIni:            limIni ? limIni.toISOString().substring(0,10) : null,
        limFin:            limFin ? limFin.toISOString().substring(0,10) : null,
        registros:         registros,
        vencidos:          vencidos
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

def construir_payload(registros: list, vencidos: list, cap_map: dict, ventana_dias: int) -> dict:
    hoy = datetime.date.today()
    fin = hoy + datetime.timedelta(days=ventana_dias)

    def mes_str(d: datetime.date) -> str:
        meses = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        return f"{meses[d.month-1]} {d.year}"

    periodo = mes_str(hoy) if mes_str(hoy) == mes_str(fin) else f"{mes_str(hoy)}–{mes_str(fin)}"

    def _dedup(lista: list) -> list:
        vistos: set = set()
        out = []
        for r in lista:
            key = r.get("IDU") or f"{r['ID_Benef']}|{r['tipo']}|{r['fecha']}"
            if key not in vistos:
                vistos.add(key)
                out.append(r)
        return out

    registros = _dedup(registros)
    vencidos  = _dedup(vencidos)

    # pid → id_benef → {nombre, capataz, etapas, vencidos_det}
    por_proy: dict = {}

    def _asegurar_ben(pid, idB, nombre):
        if pid not in por_proy:
            por_proy[pid] = {}
        if idB not in por_proy[pid]:
            por_proy[pid][idB] = {
                "nombre":       nombre or idB,
                "capataz":      cap_map.get(idB, ""),
                "etapas":       [],
                "vencidos_det": []
            }

    for r in registros:
        pid = r["ID_proy"]; idB = r["ID_Benef"]
        if not pid or not idB:
            continue
        _asegurar_ben(pid, idB, r["nombre"])
        for et in _normalizar_tipo(r["tipo"]):
            if et not in por_proy[pid][idB]["etapas"]:
                por_proy[pid][idB]["etapas"].append(et)

    for r in vencidos:
        pid = r["ID_proy"]; idB = r["ID_Benef"]
        if not pid or not idB:
            continue
        _asegurar_ben(pid, idB, r["nombre"])
        entry = {
            "fecha":      r["fecha"],
            "tipo":       r["tipo"],
            "descripcion": r.get("descripcion", "")
        }
        por_proy[pid][idB]["vencidos_det"].append(entry)

    payload = {}
    for pid, bens in por_proy.items():
        bens_list = []
        for idB, info in bens.items():
            etapas_str = ", ".join(f"[SOL] {e}" for e in info["etapas"]) if info["etapas"] else ""
            ben_entry: dict = {
                "nombre":  info["nombre"],
                "capataz": info["capataz"],
                "mes1":    etapas_str
            }
            if info["vencidos_det"]:
                ben_entry["vencidos"] = info["vencidos_det"]
            bens_list.append(ben_entry)
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
    parser.add_argument("--ventana",  type=int, default=0,
                        help="Días hacia adelante (default: 0 = semana actual lun-vie)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

    ventana_label = f"semana actual (lun-vie)" if args.ventana == 0 else f"{args.ventana} días"
    log.info(f"Extrayendo soldespachos (ventana: {ventana_label})...")
    data = extraer_despachos(args.ventana)

    log.info(f"Tabla soldepacho en índice AppModel: {data.get('solIdx', -1)}")
    log.info(f"Campo fecha identificado: {data.get('campoFecha')}")
    log.info(f"Ventana: {data.get('limIni')} a {data.get('limFin')}")
    log.info(f"Registros encontrados: {len(data['registros'])}")

    if args.inspect or data.get("solIdx", -1) < 0:
        print("\n=== INSPECCIÓN ===")
        print(f"Tabla soldepacho en índice: {data.get('solIdx', -1)}")
        print(f"Campo fecha: {data.get('campoFecha')} | Campo tipo: {data.get('campoTipo')}")
        print(f"Ventana: {data.get('limIni')} a {data.get('limFin')}")
        print(f"Campos disponibles: {json.dumps(data['camposDisponibles'], ensure_ascii=False, indent=2)}")
        if data.get("muestraFila"):
            safe = {k: str(v) for k, v in data["muestraFila"].items()}
            print(f"\nMuestra (primer registro):\n{json.dumps(safe, ensure_ascii=False, indent=2)}")
        print(f"\nPrimeros 5 registros en ventana:")
        for r in data["registros"][:5]:
            print(f"  {json.dumps(r, ensure_ascii=False)}")
        if data.get("solIdx", -1) < 0:
            log.error("No se encontró tabla soldepacho en AppModel — verifica que AppSheet cargó correctamente")
            sys.exit(1)
        return

    log.info(f"Vencidos encontrados:  {len(data.get('vencidos', []))}")
    cap_map = _cargar_capataz_map()
    payload = construir_payload(data["registros"], data.get("vencidos", []), cap_map, args.ventana)
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

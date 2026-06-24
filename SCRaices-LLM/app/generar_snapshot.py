"""
generar_snapshot.py
===================
Genera el snapshot PROCESADO del dashboard para carga instantanea.

Abre el dashboard real con Playwright, espera a que termine la carga EN VIVO
(lectura de Sheets via Apps Script) y extrae el cache procesado que el propio
dashboard guarda en localStorage ('scraices_v3_cache'). Asi reutilizamos la
logica de procesamiento del HTML (processRawData) sin duplicarla, y el snapshot
resultante es pequeno (<5 MB) en vez de los ~100 MB del JSON crudo.

El workflow data_snapshot.yml publica el resultado en la rama data-snapshot.

Uso local:
    python generar_snapshot.py                 # escribe ./data_snapshot.json
    SNAPSHOT_OUT=/ruta/x.json python generar_snapshot.py
"""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DASHBOARD_URL = "https://pitufostech.github.io/PruebasWeb/SCRaices-LLM/dashboard/index_live_v3.html"
OUT = Path(os.environ.get("SNAPSHOT_OUT", "data_snapshot.json"))
TIMEOUT_LIVE = 540  # segundos esperando a que termine la carga en vivo (~4 min reales)

# El dashboard expone el payload procesado en window.__SNAPSHOT__ tras cada
# carga (sin el limite de 4.5 MB de localStorage). Lo leemos de ahi.
GET_SNAPSHOT_JS = "() => window.__SNAPSHOT__ ? JSON.stringify(window.__SNAPSHOT__) : null"


def main() -> int:
    logs: list[str] = []
    payload = None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context().new_page()
        page.on("console", lambda m: logs.append(m.text))
        page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))

        print(f"Abriendo {DASHBOARD_URL}")
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60_000)

        # Esperar a que el dashboard complete la carga EN VIVO y popule el
        # cache procesado fresco. El HTML loguea "[LIVE] Datos ..." al terminar.
        # Requerimos el log de LIVE para no capturar un snapshot viejo restaurado.
        deadline = time.time() + TIMEOUT_LIVE
        start = time.time()
        while time.time() < deadline:
            raw = page.evaluate(GET_SNAPSHOT_JS)
            live_done = any("[LIVE] Datos" in line for line in logs)
            if raw and live_done:
                payload = json.loads(raw)
                break
            if int(time.time() - start) % 30 < 3:
                print(f"  ...esperando carga en vivo ({int(time.time()-start)}s, "
                      f"data={'si' if raw else 'no'}, live={'si' if live_done else 'no'})")
            time.sleep(3)

        # Fallback: si el live no logueo a tiempo pero ya hay payload, usarlo
        if payload is None:
            raw = page.evaluate(GET_SNAPSHOT_JS)
            if raw:
                print("WARN: usando payload sin confirmacion de log [LIVE]")
                payload = json.loads(raw)

        if payload is None:
            print("--- ultimos logs de consola del dashboard ---")
            for line in logs[-40:]:
                print("  ", line)

        browser.close()

    if not payload:
        print("ERROR: no se obtuvo cache procesado del dashboard")
        return 1

    n_proy = len(payload.get("PROYECTOS_DATA", []))
    n_benef = len(payload.get("BENEFICIARIOS_DATA", []))
    if n_proy < 1:
        print(f"ERROR: snapshot sin proyectos (benef={n_benef})")
        return 1

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    kb = OUT.stat().st_size / 1024
    print(f"Snapshot OK: {kb:.0f} KB | proyectos={n_proy} beneficiarios={n_benef}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
ejecutar_curvas_cloud.py
========================
Orquestador para ejecución cloud (GitHub Actions) de todos los scripts
de Curvas S + sincronización del dashboard.

Equivalente cloud de ejecutar_curvas_semanal.bat

Orden de ejecución:
  1.  curvas_automatico.py       (P119 - Ñuke Mapu)
  2.  curvas_automatico_aliwen.py     (P38)
  3.  curvas_automatico_coihue.py    (P39)
  4.  curvas_automatico_cunco.py     (P127)
  5.  curvas_automatico_huilcan.py   (P12)
  6.  curvas_automatico_madihue.py   (P14)
  7.  curvas_automatico_maiten.py    (P126)
  8.  curvas_automatico_melipeuco.py (P131)
  9.  curvas_automatico_quilaleo.py  (P116)
  10. curvas_automatico_trovolhue.py (P31)
  11. sincronizar_dashboard.py
  12. actualizar_gantt_programa.py

Variables de entorno requeridas (GitHub Secrets):
  GOOGLE_REFRESH_TOKEN   — refresh token OAuth Google
  GOOGLE_CLIENT_ID       — client_id de la app OAuth
  GOOGLE_CLIENT_SECRET   — client_secret de la app OAuth
  GITHUB_TOKEN           — token GitHub con permisos de escritura al repo
  FIREBASE_URL           — (opcional) URL del RTDB, default scraices-dashboard

Uso:
  python ejecutar_curvas_cloud.py
"""

import importlib.util
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("orchestrator")

HERE = Path(__file__).parent

SCRIPTS_EN_ORDEN = [
    ("P119 - Ñuke Mapu",       "curvas_automatico"),
    ("P38  - Aliwen",          "curvas_automatico_aliwen"),
    ("P39  - El Coihue",       "curvas_automatico_coihue"),
    ("P127 - Nuevo Cunco",     "curvas_automatico_cunco"),
    ("P12  - Juan Huilcan",    "curvas_automatico_huilcan"),
    ("P14  - Com. Madihue",    "curvas_automatico_madihue"),
    ("P126 - El Maitén",       "curvas_automatico_maiten"),
    ("P131 - Raíces Melipeuco","curvas_automatico_melipeuco"),
    ("P116 - Sonia Quilaleo",  "curvas_automatico_quilaleo"),
    ("P31  - Trovolhue",       "curvas_automatico_trovolhue"),
    ("P28  - Elsa Pinchulaf",  "curvas_automatico_pinchulaf"),
    # ── Proyectos futuros — descomentar cuando tengan script ──────────────────
    # ("P118 - El Canelo",              "curvas_automatico_el_canelo"),          # Rural Araucanía 2024
    # ("P123 - Peumayen 2023",          "curvas_automatico_peumayen_2023"),      # Rural Araucanía 2024
    # ("P128 - Com. José Carvajal",     "curvas_automatico_jose_carvajal"),      # Rural Araucanía 2024
    # ("P129 - Nuevo Gorbea",           "curvas_automatico_nuevo_gorbea"),       # Rural Araucanía 2024
    # ("P132 - Com. Fermín Manquilef",  "curvas_automatico_fermin_manquilef"),   # Rural Araucanía 2024
    # ("P145 - Perkenko 2025",          "curvas_automatico_perkenko"),           # Rural Araucanía 2025
    # ("P146 - Demanda Villarrica 2025","curvas_automatico_villarrica_2025"),    # Rural Araucanía 2025
    # ("P147 - Ruka Antü",              "curvas_automatico_ruka_antu"),          # Rural Araucanía 2025
    # ("P150 - Llaima Antu",            "curvas_automatico_llaima_antu"),        # Rural Araucanía 2025
    # ("P152 - Ayün Ruka",              "curvas_automatico_ayun_ruka"),          # Rural Araucanía 2025
    # ("P153 - Vilcún Mapu",            "curvas_automatico_vilcun_mapu"),        # Rural Araucanía 2025
    # ("P154 - Com. José Carvajal 2",   "curvas_automatico_carvajal_2"),         # Rural Araucanía 2025
    # ("P155 - Los Arrayanes",          "curvas_automatico_arrayanes"),          # Rural Araucanía 2025
    # ("P156 - Poyen Ruka",             "curvas_automatico_poyen_ruka"),         # Rural Araucanía 2025
    # ("P164 - Conún Huenu",            "curvas_automatico_conun_huenu"),        # Rural Araucanía 2026
    # ("P166 - Malalhue",               "curvas_automatico_malalhue"),           # Rural Araucanía 2026
    # ("P167 - Witran Donguil",         "curvas_automatico_witran_donguil"),     # Rural Araucanía 2026
    # ("P168 - Raíces de Perquenco",    "curvas_automatico_perquenco"),          # Rural Araucanía 2026
    # ("P170 - Los Copihues de Cunco",  "curvas_automatico_copihues_cunco"),     # Rural Araucanía 2026
    # ("P171 - Raíces de Trovolhue",    "curvas_automatico_trovolhue_2026"),     # Rural Araucanía 2026
    # ("P172 - Raíces Costeras",        "curvas_automatico_raices_costeras"),    # Rural Araucanía 2026
]

POST_SCRIPTS = [
    ("Sincronizar Dashboard",      "sincronizar_dashboard"),
    ("Actualizar Gantt Programa",  "actualizar_gantt_programa"),
    ("Calcular Avance Gantt",      "calcular_avance_gantt"),
]


def run_module(label: str, module_name: str) -> bool:
    """Importa y ejecuta main() del módulo. Devuelve True si tuvo éxito."""
    log.info(f"\n{'='*65}")
    log.info(f"  INICIO: {label}")
    log.info(f"{'='*65}")
    t0 = datetime.now()

    spec = importlib.util.spec_from_file_location(
        module_name, HERE / f"{module_name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        mod.main()
        elapsed = (datetime.now() - t0).total_seconds()
        log.info(f"  COMPLETADO: {label}  ({elapsed:.1f}s)")
        return True
    except SystemExit as e:
        if e.code == 0:
            log.info(f"  COMPLETADO (exit 0): {label}")
            return True
        log.error(f"  FALLO (exit {e.code}): {label}")
        return False
    except Exception:
        elapsed = (datetime.now() - t0).total_seconds()
        log.error(f"  ERROR en {label} ({elapsed:.1f}s):\n{traceback.format_exc()}")
        return False


def main():
    inicio = datetime.now()
    log.info("=" * 65)
    log.info(f"ORQUESTADOR CURVAS S — {inicio.strftime('%d/%m/%Y %H:%M UTC')}")
    log.info("=" * 65)

    resultados = {}

    # ── Curvas S de cada proyecto ─────────────────────────────────────────────
    for label, module in SCRIPTS_EN_ORDEN:
        ok = run_module(label, module)
        resultados[label] = ok

    # ── Sincronización y actualización post-proceso ───────────────────────────
    for label, module in POST_SCRIPTS:
        ok = run_module(label, module)
        resultados[label] = ok

    # ── Resumen final ──────────────────────────────────────────────────────────
    elapsed = (datetime.now() - inicio).total_seconds()
    exitosos = sum(1 for ok in resultados.values() if ok)
    fallidos  = sum(1 for ok in resultados.values() if not ok)

    log.info(f"\n{'='*65}")
    log.info(f"RESUMEN FINAL — {elapsed:.0f}s total")
    log.info(f"{'='*65}")
    for label, ok in resultados.items():
        estado = "OK   " if ok else "FALLO"
        log.info(f"  {estado}  {label}")
    log.info(f"\n  Exitosos: {exitosos}/{len(resultados)}  |  Fallidos: {fallidos}")
    log.info("=" * 65)

    if fallidos > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

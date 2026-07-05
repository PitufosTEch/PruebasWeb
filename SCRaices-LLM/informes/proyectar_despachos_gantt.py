"""
proyectar_despachos_gantt.py
============================
Actualiza las proyecciones de despacho en Proyeccion_Despachos_2026.xlsx
usando la Carta Gantt (Curva S programado) con SPI=1.15 (15% adelanto al
programa), en lugar del SPI real del proyecto (que puede ser ~1.5–1.9,
generando proyecciones excesivamente optimistas).

Metodología:
  - Entradas [SOL] = solicitudes confirmadas → NO se mueven (quedan en su mes)
  - Entradas [MC]  = proyecciones Monte Carlo → se re-proyectan con SPI=1.15
  - P50_ajustado = P50_actual × (SPI_real / SPI_objetivo)
  - Las etapas [MC] se distribuyen linealmente en P50_ajustado días
  - Se asigna mes1/mes2/mes3 según el mes calendario en que cae cada etapa
  - Etapas que quedan fuera de jul-sep 2026 se eliminan de la vista (→ "—")

Uso:
    python proyectar_despachos_gantt.py [--spi 1.15] [--preview]
    --spi N     Factor de adelanto sobre el programa (default: 1.15)
    --preview   No guarda ni sube; solo muestra qué cambiaría
"""

import io
import re
import sys
import math
import argparse
from datetime import date, timedelta
from pathlib import Path

SPI_OBJETIVO_DEFAULT = 1.15

# Ventana de meses que muestra el informe (Jul–Sep 2026)
TODAY       = date.today()   # fecha base para proyectar
MES1        = (date(2026, 7, 1),  date(2026, 7, 31))
MES2        = (date(2026, 8, 1),  date(2026, 8, 31))
MES3        = (date(2026, 9, 1),  date(2026, 9, 30))

DRIVE_FILE_ID = "1fPYmvioQvYJjKUMuQgDayf3BnSSEJ7Mp"   # mismo que inyectar_despachos.py

PROJECT_SHEETS = ["P116", "P119", "P12", "P126", "P127", "P131", "P14", "P28", "P31", "P38", "P39"]


# ── Utilidades ────────────────────────────────────────────────────────────────

def _date_to_mes(d: date) -> int:
    """Retorna 1/2/3 si la fecha cae en Jul/Ago/Sep 2026, o 0 si fuera del rango."""
    if MES1[0] <= d <= MES1[1]: return 1
    if MES2[0] <= d <= MES2[1]: return 2
    if MES3[0] <= d <= MES3[1]: return 3
    return 0


def _parse_etapas_celda(texto) -> list[dict]:
    """
    Extrae etapas de una celda mes1/mes2/mes3.
    Retorna lista de {tag: 'MC'|'SOL', nombre: '01 Fundaciones Viv.'}
    """
    texto = str(texto or "").strip()
    if texto in ("—", "-", "", "None"):
        return []
    # Dividir por coma y parsear tag+nombre
    resultado = []
    for parte in texto.split(","):
        parte = parte.strip()
        m = re.match(r"^\[(MC|SOL)\]\s*(.+)$", parte)
        if m:
            resultado.append({"tag": m.group(1), "nombre": m.group(2).strip()})
        elif parte:
            # Sin tag, tratamos como MC
            resultado.append({"tag": "MC", "nombre": parte})
    return resultado


def _formatear_celda(etapas: list[dict]) -> str:
    """Convierte lista de etapas a texto para la celda."""
    if not etapas:
        return "—"
    return ", ".join(f"[{e['tag']}] {e['nombre']}" for e in etapas)


# ── Core: re-proyección por beneficiario ─────────────────────────────────────

def _reproyectar_beneficiario(
    mes1_val, mes2_val, mes3_val,
    p50_raw, spi_real: float, spi_objetivo: float
) -> tuple[str, str, str, str, int | None]:
    """
    Re-proyecta las etapas [MC] de un beneficiario con el nuevo SPI objetivo.
    Retorna (nuevo_mes1, nuevo_mes2, nuevo_mes3, resumen_cambio, p50_ajustado_dias).
    p50_ajustado_dias es None cuando no se pudo calcular (sin P50 o sin [MC]).
    """
    # 1) Parsear etapas actuales
    etapas_actuales = {
        1: _parse_etapas_celda(mes1_val),
        2: _parse_etapas_celda(mes2_val),
        3: _parse_etapas_celda(mes3_val),
    }

    # 2) Separar [SOL] (fijas) y [MC] (a re-proyectar), preservando orden
    sol_por_mes: dict[int, list] = {1: [], 2: [], 3: []}
    mc_ordenadas: list[dict] = []  # todas las [MC] en orden mes1→mes2→mes3

    for mes in (1, 2, 3):
        for e in etapas_actuales[mes]:
            if e["tag"] == "SOL":
                sol_por_mes[mes].append(e)
            else:
                mc_ordenadas.append(e)

    # Si no hay etapas [MC] pendientes, no hay nada que re-proyectar
    if not mc_ordenadas:
        return (
            _formatear_celda(etapas_actuales[1]),
            _formatear_celda(etapas_actuales[2]),
            _formatear_celda(etapas_actuales[3]),
            "sin [MC]",
            None,
        )

    # 3) Leer P50 actual
    try:
        p50_actual = float(str(p50_raw or "").replace("—", "").strip())
        if math.isnan(p50_actual) or p50_actual <= 0:
            raise ValueError
    except (ValueError, TypeError):
        # Sin P50: no podemos re-proyectar
        return (
            _formatear_celda(etapas_actuales[1]),
            _formatear_celda(etapas_actuales[2]),
            _formatear_celda(etapas_actuales[3]),
            "sin P50",
            None,
        )

    # 4) Ajustar P50 por cambio de SPI
    #    P50_prog = P50_actual × SPI_real   (tiempo del programa)
    #    P50_adj  = P50_prog  / SPI_obj     (tiempo con SPI objetivo)
    p50_ajustado = p50_actual * (spi_real / spi_objetivo)

    # 5) Distribuir las etapas [MC] linealmente en P50_ajustado días
    n = len(mc_ordenadas)
    nuevas_mc: dict[int, list] = {1: [], 2: [], 3: []}
    for k, etapa in enumerate(mc_ordenadas, start=1):
        dia_k = (k / n) * p50_ajustado
        fecha_k = TODAY + timedelta(days=dia_k)
        mes = _date_to_mes(fecha_k)
        if mes:
            nuevas_mc[mes].append(etapa)
        # Si mes==0 (fuera de jul-sep), la etapa cae después de septiembre → no se muestra

    # 6) Combinar [SOL] fijas + [MC] re-proyectadas
    nuevo_mes = {
        m: sol_por_mes[m] + nuevas_mc[m]
        for m in (1, 2, 3)
    }

    resumen = (
        f"P50 {p50_actual:.0f}d→{p50_ajustado:.0f}d  "
        f"[MC]: {n} etapas → "
        f"mes1:{len(nuevas_mc[1])} mes2:{len(nuevas_mc[2])} mes3:{len(nuevas_mc[3])}"
    )

    return (
        _formatear_celda(nuevo_mes[1]),
        _formatear_celda(nuevo_mes[2]),
        _formatear_celda(nuevo_mes[3]),
        resumen,
        round(p50_ajustado),
    )


# ── Procesamiento de cada hoja de proyecto ───────────────────────────────────

def _procesar_hoja(ws, spi_objetivo: float, preview: bool = False) -> int:
    """
    Itera las filas de beneficiarios de una hoja y re-proyecta.
    Retorna cantidad de filas modificadas.
    """
    # Leer SPI real del proyecto (celda H2 tiene forma "SPI 1.884")
    h2 = str(ws["H2"].value or "").replace("SPI", "").strip()
    try:
        spi_real = float(h2)
    except ValueError:
        spi_real = 1.0

    # Solo re-proyectar si el proyecto va por encima del ritmo objetivo.
    # Proyectos con SPI_real ≤ SPI_objetivo (atrasados o en ritmo normal) ya tienen
    # proyecciones conservadoras — no corresponde cambiarlas.
    if spi_real <= spi_objetivo:
        msg = "sin avance real" if spi_real < 0.1 else f"SPI {spi_real:.4f} ≤ objetivo"
        print(f"  {msg} → sin re-proyección (proyecciones conservadoras se mantienen)")
        return 0

    print(f"  SPI real={spi_real:.4f}  →  SPI objetivo={spi_objetivo}  "
          f"(factor de ajuste P50: ×{spi_real/spi_objetivo:.3f})")

    modificadas = 0

    for row_idx in range(6, ws.max_row + 1):
        b_nombre = str(ws.cell(row_idx, 2).value or "").strip()
        if not b_nombre or b_nombre.startswith("  GRUPO"):
            continue

        # Columnas: J=10(mes1), K=11(mes2), L=12(mes3), N=14(P50)
        mes1_cell = ws.cell(row_idx, 10)
        mes2_cell = ws.cell(row_idx, 11)
        mes3_cell = ws.cell(row_idx, 12)
        p50_raw   = ws.cell(row_idx, 14).value

        # Si todas las celdas son "—" → beneficiario sin pendientes
        todo_dash = all(
            str(c.value or "").strip() in ("—", "-", "", "None")
            for c in (mes1_cell, mes2_cell, mes3_cell)
        )
        if todo_dash:
            continue

        n_mes1, n_mes2, n_mes3, resumen, p50_adj = _reproyectar_beneficiario(
            mes1_cell.value, mes2_cell.value, mes3_cell.value,
            p50_raw, spi_real, spi_objetivo,
        )

        # Verificar si hubo cambio real
        cambio = (
            str(mes1_cell.value or "") != n_mes1 or
            str(mes2_cell.value or "") != n_mes2 or
            str(mes3_cell.value or "") != n_mes3
        )

        if cambio:
            modificadas += 1
            nombre_corto = b_nombre[:35]
            print(f"    {nombre_corto:<35} {resumen}")
            if not preview:
                mes1_cell.value = n_mes1
                mes2_cell.value = n_mes2
                mes3_cell.value = n_mes3
                # Actualizar P50/P10/P90 con valores ajustados al SPI objetivo
                # para que el reporte muestre días coherentes con la proyección
                if p50_adj is not None:
                    ws.cell(row_idx, 14).value = p50_adj                    # P50
                    ws.cell(row_idx, 13).value = max(1, round(p50_adj * 0.75))  # P10
                    ws.cell(row_idx, 15).value = round(p50_adj * 1.35)         # P90

    return modificadas


# ── Descarga y subida Drive ───────────────────────────────────────────────────

def _descargar_excel() -> bytes:
    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(Path(__file__).parent.parent / "curvas_s"))
    import curvas_cloud_utils as _ccu
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    creds   = _ccu.get_credentials()
    service = build("drive", "v3", credentials=creds)
    meta    = service.files().get(fileId=DRIVE_FILE_ID, fields="mimeType").execute()
    if meta["mimeType"] == "application/vnd.google-apps.spreadsheet":
        req = service.files().export_media(
            fileId=DRIVE_FILE_ID,
            mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        req = service.files().get_media(fileId=DRIVE_FILE_ID)

    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def _subir_excel(contenido: bytes) -> bool:
    sys.path.insert(0, str(Path(__file__).parent.parent / "curvas_s"))
    import curvas_cloud_utils as _ccu
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    creds   = _ccu.get_credentials()
    service = build("drive", "v3", credentials=creds)

    media = MediaIoBaseUpload(
        io.BytesIO(contenido),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=True,
    )
    service.files().update(fileId=DRIVE_FILE_ID, media_body=media).execute()
    print("  [Drive] Proyeccion_Despachos_2026.xlsx actualizado en Drive ✓")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Re-proyecta despachos con SPI objetivo")
    parser.add_argument("--spi", type=float, default=SPI_OBJETIVO_DEFAULT,
                        help=f"SPI objetivo para proyección (default: {SPI_OBJETIVO_DEFAULT})")
    parser.add_argument("--preview", action="store_true",
                        help="Muestra cambios sin guardar ni subir a Drive")
    args = parser.parse_args()

    spi_obj = args.spi
    preview = args.preview

    print(f"{'='*60}")
    print(f"Proyectar Despachos Gantt — SPI objetivo: {spi_obj}")
    print(f"Fecha base: {TODAY}   Modo: {'PREVIEW' if preview else 'ACTUALIZAR'}")
    print(f"{'='*60}\n")

    print("► Descargando Excel de Drive...")
    try:
        datos = _descargar_excel()
    except Exception as e:
        print(f"  ERROR descargando: {e}")
        sys.exit(1)

    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(datos))

    total_modificadas = 0
    for pid in PROJECT_SHEETS:
        if pid not in wb.sheetnames:
            print(f"\n[{pid}] hoja no encontrada — omitiendo")
            continue
        print(f"\n► {pid}")
        mod = _procesar_hoja(wb[pid], spi_obj, preview=preview)
        print(f"  → {mod} filas actualizadas")
        total_modificadas += mod

    print(f"\n{'='*60}")
    print(f"Total filas modificadas: {total_modificadas}")

    if preview:
        print("Modo PREVIEW — no se guardaron cambios")
        return

    if total_modificadas == 0:
        print("Sin cambios — no se sube a Drive")
        return

    print("\n► Subiendo Excel actualizado a Drive...")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    try:
        _subir_excel(buf.read())
    except Exception as e:
        # Si falla la subida, guardar copia local
        local = Path(__file__).parent / "Proyeccion_Despachos_SPI115.xlsx"
        buf.seek(0)
        local.write_bytes(buf.read())
        print(f"  [Drive] ERROR: {e}")
        print(f"  Guardado local: {local}")

    # También actualizar Firebase /despachos_data y /despachos_html
    print("\n► Actualizando Firebase con los nuevos datos...")
    try:
        from inyectar_despachos import (
            escribir_despachos_firebase,
            escribir_despachos_data_firebase,
        )
        escribir_despachos_firebase()
        escribir_despachos_data_firebase()
        print("  Firebase /despachos_html y /despachos_data actualizados ✓")
    except Exception as e:
        print(f"  [Firebase] ERROR: {e}")

    print("\nListo.")


if __name__ == "__main__":
    main()

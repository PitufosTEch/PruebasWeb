"""
Script para exportar la estructura de la base de datos a archivos de ejemplo.
Genera un archivo por tabla con: columnas, tipos y muestra de datos.
"""
import os
import sys
import pandas as pd
from pathlib import Path

# Añadir el directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

from sheets_connection import SheetsConnection
from data_manager import DataManager

OUTPUT_DIR = Path(__file__).parent.parent / "ejemplo de estructura"

def export_table_structure(dm: DataManager, table_name: str, output_dir: Path):
    """Exporta la estructura de una tabla a un archivo CSV"""
    try:
        df = dm.get_table_data(table_name)

        # Crear archivo con muestra de datos (máximo 10 filas)
        sample_df = df.head(10)

        # Sanitizar nombre de archivo (remover caracteres no válidos)
        safe_name = table_name.replace("/", "_").replace("\\", "_").replace(":", "_")

        # Guardar CSV con muestra
        csv_path = output_dir / f"{safe_name}.csv"
        sample_df.to_csv(csv_path, index=False, encoding='utf-8-sig')

        return {
            "tabla": table_name,
            "filas_total": len(df),
            "columnas": len(df.columns),
            "columnas_lista": list(df.columns),
            "archivo": csv_path.name
        }
    except Exception as e:
        return {
            "tabla": table_name,
            "error": str(e)
        }

def main():
    print("=" * 60)
    print("EXPORTADOR DE ESTRUCTURA DE BASE DE DATOS")
    print("=" * 60)

    # Crear directorio de salida
    OUTPUT_DIR.mkdir(exist_ok=True)

    print(f"\nDirectorio de salida: {OUTPUT_DIR}")

    # Conectar
    print("\nConectando a Google Sheets...")
    dm = DataManager()

    sheets = dm.available_sheets
    print(f"Encontradas {len(sheets)} hojas/tablas")

    # Exportar cada tabla
    resumen = []
    for i, table in enumerate(sheets):
        print(f"  [{i+1}/{len(sheets)}] Exportando: {table}...", end=" ")
        result = export_table_structure(dm, table, OUTPUT_DIR)
        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            print(f"OK ({result['filas_total']} filas, {result['columnas']} cols)")
        resumen.append(result)

    # Crear archivo de resumen
    print("\nGenerando resumen...")

    resumen_text = ["# ESTRUCTURA DE BASE DE DATOS SCRAICES", ""]
    resumen_text.append(f"Total de tablas: {len(sheets)}")
    resumen_text.append("")
    resumen_text.append("## LISTADO DE TABLAS")
    resumen_text.append("")

    for r in resumen:
        if "error" in r:
            resumen_text.append(f"### ❌ {r['tabla']}")
            resumen_text.append(f"Error: {r['error']}")
        else:
            resumen_text.append(f"### {r['tabla']}")
            resumen_text.append(f"- Filas: {r['filas_total']}")
            resumen_text.append(f"- Columnas ({r['columnas']}): {', '.join(r['columnas_lista'][:20])}")
            if r['columnas'] > 20:
                resumen_text.append(f"  ... y {r['columnas'] - 20} columnas más")
            resumen_text.append(f"- Archivo: `{r['archivo']}`")
        resumen_text.append("")

    # Guardar resumen
    resumen_path = OUTPUT_DIR / "_RESUMEN_ESTRUCTURA.md"
    with open(resumen_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(resumen_text))

    print(f"\n✅ Exportación completada!")
    print(f"   - {len([r for r in resumen if 'error' not in r])} tablas exportadas")
    print(f"   - Resumen guardado en: {resumen_path}")
    print(f"\nRevisa la carpeta: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()

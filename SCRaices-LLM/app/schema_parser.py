"""
Parser para extraer la estructura de tablas desde el HTML de AppSheet
"""
import re
import json
from pathlib import Path

HTML_PATH = Path(__file__).parent.parent / "Application Documentation.html"

def parse_schema():
    """Extrae la estructura de tablas, columnas y relaciones del HTML"""

    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    schema = {
        "tables": {},
        "relationships": []
    }

    # Encontrar todas las tablas
    table_pattern = r'<h5 id="table_([^"]+)">\s*<label[^>]*>Table name</label>\s*</h5>'
    table_matches = re.finditer(table_pattern, html)

    # Patron alternativo para nombres de tabla
    table_name_pattern = r'Table name</label></td><td>([^<]+)</td>'
    table_names = re.findall(table_name_pattern, html)

    # Encontrar secciones de columnas por tabla
    # Buscar patrones de columnas con su tabla asociada
    column_section_pattern = r'<h3 id="table_([^_]+)_Schema_col\d+">Column \d+:\s*([^<]+)</h3>\s*<table[^>]*>(.*?)</table>'

    # Patron para extraer info de columnas
    col_name_pattern = r'Column name</label></td><td>([^<]+)</td>'
    col_type_pattern = r'title="Column data type">Type</label></td><td>([^<]+)</td>'
    col_key_pattern = r'title="This column uniquely identifies rows from this table.">Key</label></td><td>([^<]+)</td>'
    col_type_qualifier_pattern = r'Type Qualifier</label></td><td>([^<]+)</td>'

    current_table = None

    # Dividir por secciones de tabla
    table_sections = re.split(r'<h5 id="table_', html)

    for section in table_sections[1:]:  # Skip first empty section
        # Extraer nombre de tabla
        table_match = re.search(r'^([^"]+)"', section)
        if not table_match:
            continue

        table_id = table_match.group(1)

        # Buscar el nombre real de la tabla
        name_match = re.search(r'Table name</label></td><td>([^<]+)</td>', section)
        table_name = name_match.group(1) if name_match else table_id

        schema["tables"][table_name] = {
            "columns": [],
            "primary_key": None,
            "foreign_keys": []
        }

        # Encontrar todas las columnas de esta tabla
        col_sections = re.split(r'<h3 id="[^"]*_Schema_col\d+">', section)

        for col_section in col_sections[1:]:
            col_info = {}

            # Nombre de columna
            name_match = re.search(col_name_pattern, col_section)
            if name_match:
                col_info["name"] = name_match.group(1).strip()
            else:
                continue

            # Tipo de columna
            type_match = re.search(col_type_pattern, col_section)
            if type_match:
                col_info["type"] = type_match.group(1).strip()

            # Es clave primaria?
            key_match = re.search(col_key_pattern, col_section)
            if key_match and key_match.group(1).strip() == "Yes":
                col_info["is_key"] = True
                schema["tables"][table_name]["primary_key"] = col_info["name"]
            else:
                col_info["is_key"] = False

            # Type Qualifier (contiene info de referencias)
            qualifier_match = re.search(col_type_qualifier_pattern, col_section)
            if qualifier_match:
                qualifier_str = qualifier_match.group(1)
                # Buscar referencia a otra tabla
                ref_match = re.search(r'"ReferencedTableName":"([^"]+)"', qualifier_str)
                if ref_match:
                    ref_table = ref_match.group(1)
                    col_info["references"] = ref_table
                    schema["tables"][table_name]["foreign_keys"].append({
                        "column": col_info["name"],
                        "references_table": ref_table
                    })
                    schema["relationships"].append({
                        "from_table": table_name,
                        "from_column": col_info["name"],
                        "to_table": ref_table
                    })

            schema["tables"][table_name]["columns"].append(col_info)

    return schema


def save_schema(schema, output_path=None):
    """Guarda el schema en formato JSON"""
    if output_path is None:
        output_path = Path(__file__).parent / "schema.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    return output_path


def print_summary(schema):
    """Imprime un resumen del schema"""
    print(f"\n=== RESUMEN DEL SCHEMA ===")
    print(f"Total de tablas: {len(schema['tables'])}")
    print(f"Total de relaciones: {len(schema['relationships'])}")

    total_cols = sum(len(t['columns']) for t in schema['tables'].values())
    print(f"Total de columnas: {total_cols}")

    # Tablas con mas columnas
    print(f"\n--- Tablas principales ---")
    sorted_tables = sorted(schema['tables'].items(), key=lambda x: len(x[1]['columns']), reverse=True)
    for name, info in sorted_tables[:10]:
        pk = info['primary_key'] or 'N/A'
        fks = len(info['foreign_keys'])
        print(f"  {name}: {len(info['columns'])} cols, PK: {pk}, FKs: {fks}")

    # Relaciones
    print(f"\n--- Algunas relaciones ---")
    for rel in schema['relationships'][:15]:
        print(f"  {rel['from_table']}.{rel['from_column']} -> {rel['to_table']}")


if __name__ == "__main__":
    print("Parseando estructura de la documentacion...")
    schema = parse_schema()

    output_path = save_schema(schema)
    print(f"\nSchema guardado en: {output_path}")

    print_summary(schema)

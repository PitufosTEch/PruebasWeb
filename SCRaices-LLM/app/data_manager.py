"""
Data Manager - Gestiona datos y relaciones entre tablas
"""
import json
import pandas as pd
from pathlib import Path
from sheets_connection import SheetsConnection

SCHEMA_PATH = Path(__file__).parent / "schema.json"


class DataManager:
    def __init__(self):
        self.conn = SheetsConnection()
        self.schema = self._load_schema()
        self._cache = {}  # Cache de dataframes cargados
        self._available_sheets = None

    def _load_schema(self):
        """Carga el schema de la base de datos"""
        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"tables": {}, "relationships": []}

    @property
    def available_sheets(self):
        """Lista de hojas disponibles en el spreadsheet"""
        if self._available_sheets is None:
            self._available_sheets = self.conn.get_sheet_names()
        return self._available_sheets

    def get_table_info(self, table_name: str) -> dict:
        """Obtiene información de una tabla (columnas, PK, FKs)"""
        # Buscar en schema (puede tener _Schema suffix)
        schema_name = f"{table_name}_Schema"
        if schema_name in self.schema["tables"]:
            return self.schema["tables"][schema_name]
        if table_name in self.schema["tables"]:
            return self.schema["tables"][table_name]
        return None

    def get_table_data(self, table_name: str) -> pd.DataFrame:
        """Carga datos de una tabla (con cache)"""
        if table_name in self._cache:
            return self._cache[table_name]

        if table_name not in self.available_sheets:
            raise ValueError(f"Tabla '{table_name}' no encontrada. Disponibles: {self.available_sheets[:10]}...")

        df = self.conn.get_sheet_data(table_name)
        self._cache[table_name] = df
        return df

    def get_relationships_for_table(self, table_name: str) -> list:
        """Obtiene todas las relaciones de una tabla"""
        schema_name = f"{table_name}_Schema"
        relations = []

        for rel in self.schema.get("relationships", []):
            if rel["from_table"] in [table_name, schema_name]:
                relations.append({
                    "type": "outgoing",
                    "column": rel["from_column"],
                    "references": rel["to_table"]
                })
            if rel["to_table"] == table_name:
                relations.append({
                    "type": "incoming",
                    "from_table": rel["from_table"].replace("_Schema", ""),
                    "from_column": rel["from_column"]
                })

        return relations

    def find_join_path(self, table1: str, table2: str) -> list:
        """Encuentra el camino para hacer JOIN entre dos tablas"""
        # Buscar relación directa
        for rel in self.schema.get("relationships", []):
            from_table = rel["from_table"].replace("_Schema", "")
            to_table = rel["to_table"]

            if from_table == table1 and to_table == table2:
                return [{
                    "from": table1,
                    "to": table2,
                    "on_column": rel["from_column"],
                    "join_type": "left"
                }]
            if from_table == table2 and to_table == table1:
                return [{
                    "from": table2,
                    "to": table1,
                    "on_column": rel["from_column"],
                    "join_type": "right"
                }]

        return None

    def join_tables(self, table1: str, table2: str, how: str = "left") -> pd.DataFrame:
        """Une dos tablas basándose en sus relaciones"""
        df1 = self.get_table_data(table1)
        df2 = self.get_table_data(table2)

        # Encontrar la columna de relación
        join_path = self.find_join_path(table1, table2)

        if not join_path:
            # Intentar encontrar columnas con nombres similares
            common_cols = set(df1.columns) & set(df2.columns)
            if common_cols:
                join_col = list(common_cols)[0]
                return pd.merge(df1, df2, on=join_col, how=how, suffixes=(f'_{table1}', f'_{table2}'))
            raise ValueError(f"No se encontró relación entre {table1} y {table2}")

        # Usar la relación encontrada
        join_info = join_path[0]
        fk_column = join_info["on_column"]

        # Encontrar PK de la tabla referenciada
        table2_info = self.get_table_info(table2)
        pk_column = table2_info["primary_key"] if table2_info else None

        if pk_column and fk_column in df1.columns and pk_column in df2.columns:
            return pd.merge(df1, df2, left_on=fk_column, right_on=pk_column, how=how, suffixes=(f'_{table1}', f'_{table2}'))

        # Fallback: buscar columna FK en df1 que matchee con alguna en df2
        for col in df1.columns:
            if col in df2.columns:
                return pd.merge(df1, df2, on=col, how=how, suffixes=(f'_{table1}', f'_{table2}'))

        raise ValueError(f"No se pudo hacer JOIN entre {table1} y {table2}")

    def query_with_joins(self, main_table: str, related_tables: list = None) -> pd.DataFrame:
        """Consulta una tabla principal con sus tablas relacionadas"""
        result = self.get_table_data(main_table)

        if related_tables:
            for rel_table in related_tables:
                try:
                    result = self.join_tables(main_table, rel_table)
                    main_table = None  # Siguiente join usa el resultado
                except Exception as e:
                    print(f"Warning: No se pudo unir con {rel_table}: {e}")

        return result

    def search_in_tables(self, search_term: str, tables: list = None) -> dict:
        """Busca un término en múltiples tablas"""
        results = {}
        tables_to_search = tables or self.available_sheets  # Buscar en todas

        for table in tables_to_search:
            try:
                df = self.get_table_data(table)
                # Buscar en todas las columnas de texto
                mask = df.apply(lambda col: col.astype(str).str.contains(search_term, case=False, na=False)).any(axis=1)
                matches = df[mask]
                if len(matches) > 0:
                    results[table] = matches
            except Exception as e:
                continue

        return results

    def get_schema_summary(self) -> str:
        """Genera un resumen del schema para el LLM"""
        summary = []
        summary.append(f"Base de datos con {len(self.available_sheets)} hojas disponibles.\n")

        # Tablas principales (las que tienen más relaciones)
        main_tables = ["Proyectos", "Beneficiario", "Levantamiento", "Ejecucion", "usuarios", "APR"]

        for table in main_tables:
            if table in self.available_sheets:
                info = self.get_table_info(table)
                rels = self.get_relationships_for_table(table)

                summary.append(f"\n## {table}")
                if info:
                    summary.append(f"- Clave primaria: {info.get('primary_key', 'N/A')}")
                    summary.append(f"- Columnas: {len(info.get('columns', []))}")

                if rels:
                    summary.append("- Relaciones:")
                    for r in rels[:5]:
                        if r["type"] == "outgoing":
                            summary.append(f"  - {r['column']} -> {r['references']}")

        return "\n".join(summary)


if __name__ == "__main__":
    dm = DataManager()

    print("=== Data Manager Test ===\n")
    print(f"Hojas disponibles: {len(dm.available_sheets)}")
    print(f"Primeras 10: {dm.available_sheets[:10]}\n")

    # Probar carga de una tabla
    print("Cargando tabla 'Proyectos'...")
    try:
        df = dm.get_table_data("Proyectos")
        print(f"Filas: {len(df)}, Columnas: {len(df.columns)}")
        print(f"Columnas: {list(df.columns)[:10]}...")
    except Exception as e:
        print(f"Error: {e}")

    # Mostrar relaciones
    print("\nRelaciones de 'Proyectos':")
    rels = dm.get_relationships_for_table("Proyectos")
    for r in rels[:5]:
        print(f"  {r}")

    print("\n" + dm.get_schema_summary())

"""
Motor de consultas básicas - Permite buscar, filtrar y agregar datos
"""
import pandas as pd
import re
from data_manager import DataManager


class QueryEngine:
    def __init__(self):
        self.dm = DataManager()
        self.last_result = None

    def search(self, term: str, tables: list = None) -> dict:
        """Busca un término en las tablas especificadas"""
        results = self.dm.search_in_tables(term, tables)
        return results

    def get_table(self, table_name: str) -> pd.DataFrame:
        """Obtiene datos de una tabla"""
        return self.dm.get_table_data(table_name)

    def filter_table(self, table_name: str, column: str, value: str, operator: str = "equals") -> pd.DataFrame:
        """Filtra una tabla por una columna"""
        df = self.dm.get_table_data(table_name)

        if column not in df.columns:
            raise ValueError(f"Columna '{column}' no existe. Disponibles: {list(df.columns)}")

        if operator == "equals":
            mask = df[column].astype(str) == str(value)
        elif operator == "contains":
            mask = df[column].astype(str).str.contains(str(value), case=False, na=False)
        elif operator == "greater":
            mask = pd.to_numeric(df[column], errors='coerce') > float(value)
        elif operator == "less":
            mask = pd.to_numeric(df[column], errors='coerce') < float(value)
        else:
            mask = df[column].astype(str) == str(value)

        self.last_result = df[mask]
        return self.last_result

    def group_and_count(self, table_name: str, group_by: str) -> pd.DataFrame:
        """Agrupa y cuenta registros"""
        df = self.dm.get_table_data(table_name)

        if group_by not in df.columns:
            raise ValueError(f"Columna '{group_by}' no existe")

        result = df.groupby(group_by).size().reset_index(name='Cantidad')
        result = result.sort_values('Cantidad', ascending=False)
        self.last_result = result
        return result

    def group_and_sum(self, table_name: str, group_by: str, sum_column: str) -> pd.DataFrame:
        """Agrupa y suma una columna numérica"""
        df = self.dm.get_table_data(table_name)

        if group_by not in df.columns or sum_column not in df.columns:
            raise ValueError(f"Columna no encontrada")

        df[sum_column] = pd.to_numeric(df[sum_column], errors='coerce')
        result = df.groupby(group_by)[sum_column].sum().reset_index()
        result = result.sort_values(sum_column, ascending=False)
        self.last_result = result
        return result

    def join_and_query(self, table1: str, table2: str, filter_col: str = None, filter_val: str = None) -> pd.DataFrame:
        """Une dos tablas y opcionalmente filtra"""
        df = self.dm.join_tables(table1, table2)

        if filter_col and filter_val:
            if filter_col in df.columns:
                df = df[df[filter_col].astype(str).str.contains(str(filter_val), case=False, na=False)]

        self.last_result = df
        return df

    def get_summary_stats(self, table_name: str) -> dict:
        """Obtiene estadísticas resumidas de una tabla"""
        df = self.dm.get_table_data(table_name)

        stats = {
            "total_filas": len(df),
            "total_columnas": len(df.columns),
            "columnas": list(df.columns),
            "columnas_numericas": [],
            "columnas_texto": []
        }

        for col in df.columns:
            if pd.to_numeric(df[col], errors='coerce').notna().sum() > len(df) * 0.5:
                stats["columnas_numericas"].append(col)
            else:
                stats["columnas_texto"].append(col)

        return stats

    def parse_natural_query(self, query: str) -> dict:
        """
        Intenta parsear una consulta en lenguaje natural básica.
        Retorna un diccionario con la acción a realizar.
        """
        query_lower = query.lower()

        # Patrones básicos
        patterns = {
            "count": r"(?:cuantos?|cantidad|total|numero)\s+(?:de\s+)?(\w+)",
            "list": r"(?:lista|muestra|ver|mostrar)\s+(?:los?\s+)?(\w+)",
            "filter": r"(\w+)\s+(?:de|en|con)\s+(\w+)\s*[=:]\s*(.+)",
            "search": r"(?:busca|encuentra|buscar)\s+['\"]?(.+?)['\"]?\s+en\s+(\w+)",
            "group": r"(?:agrupar?|por)\s+(\w+)\s+(?:en|de)\s+(\w+)",
        }

        result = {"action": None, "params": {}}

        # Detectar acción de contar
        if any(word in query_lower for word in ["cuantos", "cuántos", "cantidad", "total de"]):
            # Buscar tabla mencionada
            for table in self.dm.available_sheets:
                if table.lower() in query_lower:
                    result["action"] = "count"
                    result["params"]["table"] = table
                    break

        # Detectar búsqueda
        elif any(word in query_lower for word in ["busca", "buscar", "encuentra", "encontrar"]):
            result["action"] = "search"
            # Extraer término entre comillas o después de "busca"
            match = re.search(r'(?:busca|encuentra)[r]?\s+["\']?([^"\']+)["\']?', query_lower)
            if match:
                result["params"]["term"] = match.group(1).strip()

        # Detectar listado
        elif any(word in query_lower for word in ["lista", "muestra", "ver", "mostrar"]):
            for table in self.dm.available_sheets:
                if table.lower() in query_lower:
                    result["action"] = "list"
                    result["params"]["table"] = table
                    break

        return result

    def execute_parsed_query(self, parsed: dict) -> tuple:
        """Ejecuta una consulta parseada y retorna (resultado, mensaje)"""
        action = parsed.get("action")
        params = parsed.get("params", {})

        if action == "count":
            table = params.get("table")
            if table:
                df = self.get_table(table)
                return df, f"La tabla '{table}' tiene {len(df)} registros."

        elif action == "search":
            term = params.get("term")
            if term:
                results = self.search(term)
                total = sum(len(df) for df in results.values())
                msg = f"Se encontraron {total} coincidencias para '{term}' en {len(results)} tablas."
                return results, msg

        elif action == "list":
            table = params.get("table")
            if table:
                df = self.get_table(table)
                return df, f"Mostrando {len(df)} registros de '{table}'."

        return None, "No pude entender la consulta. Intenta con: 'muestra Proyectos' o 'busca [término]'"


# Consultas predefinidas útiles
PRESET_QUERIES = {
    "proyectos_por_comuna": {
        "name": "Proyectos por Comuna",
        "description": "Cantidad de proyectos agrupados por comuna",
        "action": lambda qe: qe.group_and_count("Proyectos", "COMUNA")
    },
    "beneficiarios_por_proyecto": {
        "name": "Beneficiarios por Proyecto",
        "description": "Cantidad de beneficiarios por cada proyecto",
        "action": lambda qe: qe.group_and_count("Beneficiario", "ID_Proy")
    },
    "resumen_proyectos": {
        "name": "Resumen de Proyectos",
        "description": "Lista todos los proyectos con nombre y comuna",
        "action": lambda qe: qe.get_table("Proyectos")[["ID_proy", "NOMBRE_PROYECTO", "COMUNA", "PERIODO"]]
    },
    "usuarios_activos": {
        "name": "Usuarios del Sistema",
        "description": "Lista de usuarios registrados",
        "action": lambda qe: qe.get_table("usuarios")
    }
}


if __name__ == "__main__":
    qe = QueryEngine()

    print("=== Query Engine Test ===\n")

    # Test consulta natural
    queries = [
        "cuantos proyectos hay",
        "muestra los beneficiarios",
        "busca Temuco"
    ]

    for q in queries:
        print(f"\nConsulta: '{q}'")
        parsed = qe.parse_natural_query(q)
        print(f"Parseado: {parsed}")
        result, msg = qe.execute_parsed_query(parsed)
        print(f"Resultado: {msg}")

    # Test consultas predefinidas
    print("\n\n=== Consultas Predefinidas ===")
    for key, preset in PRESET_QUERIES.items():
        print(f"\n{preset['name']}:")
        try:
            result = preset["action"](qe)
            print(result.head())
        except Exception as e:
            print(f"Error: {e}")

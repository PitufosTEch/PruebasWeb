"""
Motor de consultas con Claude - Interpreta preguntas en lenguaje natural
"""
import os
import json
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic
from data_manager import DataManager
from tabla_docs import get_prompt_context, TABLA_DOCS

load_dotenv(Path(__file__).parent / ".env")
SCHEMA_PATH = Path(__file__).parent / "schema.json"

# Límite de mensajes en el historial para no exceder tokens
MAX_HISTORY_MESSAGES = 10


class ClaudeQueryEngine:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no encontrada")

        self.client = Anthropic(api_key=api_key)
        self.dm = DataManager()
        self.conversation_history = []
        self.last_query_result = None  # Para referencias como "de estos", "los anteriores"

    def _get_table_structure(self, table_name: str) -> str:
        """Obtiene la estructura real de una tabla desde los datos"""
        try:
            df = self.dm.get_table_data(table_name)
            cols = list(df.columns)[:15]  # Limitar a 15 columnas
            return f"{table_name}: {', '.join(cols)}"
        except Exception:
            return f"{table_name}: (no disponible)"

    def _get_system_prompt(self) -> str:
        """Prompt de sistema optimizado para consultas"""
        available_sheets = self.dm.available_sheets

        # Obtener estructura real de las tablas principales
        main_tables = ["Proyectos", "Beneficiario", "Levantamiento", "Ejecucion", "Despacho", "usuarios"]
        structures = []
        for table in main_tables:
            if table in available_sheets:
                structures.append(self._get_table_structure(table))

        # Obtener documentación de columnas
        docs_context = get_prompt_context()

        return f"""Eres un experto en análisis de datos de SCRaices (construcción de viviendas sociales en Chile).

## TABLAS DISPONIBLES ({len(available_sheets)} en total):
{', '.join(available_sheets[:30])}{'...' if len(available_sheets) > 30 else ''}

## ESTRUCTURA DE TABLAS PRINCIPALES (columnas reales):
{chr(10).join(structures)}

{docs_context}

## RELACIONES CONOCIDAS:
- Beneficiario.ID_Proy -> Proyectos.ID_proy
- Levantamiento.ID_Benef -> Beneficiario.ID_Benef
- Levantamiento.ID_proy -> Proyectos.ID_proy
- Ejecucion.ID_benef -> Beneficiario.ID_Benef
- Ejecucion.ID_Proy -> Proyectos.ID_proy

## INSTRUCCIONES:
1. Genera código Pandas que responda EXACTAMENTE lo que pide el usuario
2. El código debe usar 'dm' (DataManager) y retornar un DataFrame
3. Si el usuario hace preguntas de seguimiento ("de estos", "cuales", etc.), usa el contexto anterior

## RESPONDE SIEMPRE EN JSON:
{{
    "explicacion": "Respuesta clara y concisa para el usuario",
    "razonamiento": "Explica brevemente: 1) Qué tablas usas, 2) Qué columnas son relevantes, 3) Cómo las relacionas (si aplica)",
    "tablas_usadas": ["lista", "de", "tablas"],
    "codigo": "CÓDIGO PANDAS - una sola expresión que retorne DataFrame"
}}

## PATRONES DE CÓDIGO:

Filtrar: dm.get_table_data("Tabla").query("columna == 'valor'")
Contar por grupo: dm.get_table_data("Tabla").groupby("columna").size().reset_index(name="Cantidad")
Sumar por grupo: dm.get_table_data("Tabla").groupby("columna")["col_num"].sum().reset_index()
Unir tablas: dm.get_table_data("T1").merge(dm.get_table_data("T2"), left_on="fk", right_on="pk")
Top N: df.nlargest(N, "columna") o df.head(N)
Buscar texto: df[df["col"].str.contains("texto", case=False, na=False)]
Valores únicos: df["columna"].unique() o df["columna"].value_counts()
Resultado anterior: df_anterior (disponible si hay consulta previa)

## IMPORTANTE:
- Usa nombres EXACTOS de columnas (respeta mayúsculas/minúsculas)
- Para fechas usa pd.to_datetime() si es necesario
- El código debe ser UNA expresión, no múltiples líneas
- Si no estás seguro de una columna, incluye .columns en la respuesta para mostrarlas
"""

    def _add_context_to_question(self, user_question: str) -> str:
        """Agrega contexto del resultado anterior si la pregunta lo requiere"""
        context_keywords = ["estos", "esos", "anteriores", "de ellos", "cuales de", "filtrar", "de esos"]

        if any(kw in user_question.lower() for kw in context_keywords) and self.last_query_result is not None:
            # Agregar información del resultado anterior
            df = self.last_query_result
            context = f"\n[CONTEXTO: El resultado anterior tiene {len(df)} filas. "
            context += f"Columnas: {list(df.columns)}. "
            if len(df) <= 20:
                context += f"Datos: {df.to_dict('records')}"
            else:
                context += f"Primeras filas: {df.head(5).to_dict('records')}"
            context += "]\n"
            return user_question + context

        return user_question

    def query(self, user_question: str) -> dict:
        """Procesa una pregunta del usuario con historial de conversación"""

        # Agregar contexto si es una pregunta de seguimiento
        enriched_question = self._add_context_to_question(user_question)

        # Agregar la pregunta al historial
        self.conversation_history.append({"role": "user", "content": enriched_question})

        # Limitar el historial para no exceder tokens
        if len(self.conversation_history) > MAX_HISTORY_MESSAGES:
            self.conversation_history = self.conversation_history[-MAX_HISTORY_MESSAGES:]

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=self._get_system_prompt(),
            messages=self.conversation_history
        )

        assistant_message = response.content[0].text

        # Guardar respuesta en historial
        self.conversation_history.append({"role": "assistant", "content": assistant_message})

        # Parsear JSON
        try:
            json_str = assistant_message
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            result = json.loads(json_str.strip())

            # Ejecutar código
            if "codigo" in result and result["codigo"]:
                try:
                    df_result = self._execute_code(result["codigo"])
                    result["datos"] = df_result
                    result["exito"] = True
                    # Guardar resultado para consultas de seguimiento
                    self.last_query_result = df_result
                except Exception as e:
                    result["error_ejecucion"] = str(e)
                    result["exito"] = False

            return result

        except json.JSONDecodeError:
            return {
                "explicacion": assistant_message,
                "exito": False
            }

    def _validate_code(self, code: str) -> bool:
        """Valida que el código sea seguro antes de ejecutarlo"""
        # Palabras prohibidas que podrían ser peligrosas
        # Nota: evitar palabras que pueden aparecer en nombres de columnas (ej: 'file' en 'file_ROL_DET')
        forbidden = [
            "import ", "open(", "exec(", "eval(", "__", "os.", "sys.",
            "subprocess", "shutil", "pathlib", ".write(", ".delete(",
            ".remove(", "rmdir", "unlink", "file(", "builtins"
        ]
        code_lower = code.lower()
        for word in forbidden:
            if word in code_lower:
                return False
        return True

    def _execute_code(self, code: str) -> pd.DataFrame:
        """Ejecuta código pandas de forma segura"""
        # Validar código antes de ejecutar
        if not self._validate_code(code):
            raise ValueError("El código contiene operaciones no permitidas")

        dm = self.dm

        # Funciones seguras permitidas
        safe_builtins = {
            "len": len, "sum": sum, "min": min, "max": max,
            "str": str, "int": int, "float": float,
            "list": list, "dict": dict, "range": range,
            "sorted": sorted, "True": True, "False": False,
            "None": None, "abs": abs, "round": round
        }

        # Variables disponibles para el código
        local_vars = {"dm": dm, "pd": pd}

        # Si hay un resultado anterior, hacerlo disponible
        if self.last_query_result is not None:
            local_vars["df_anterior"] = self.last_query_result

        try:
            exec(f"result = {code}", safe_builtins, local_vars)
        except SyntaxError as e:
            raise ValueError(f"Error de sintaxis en el código: {e}")
        except KeyError as e:
            raise ValueError(f"Columna o clave no encontrada: {e}")
        except Exception as e:
            raise ValueError(f"Error al ejecutar: {type(e).__name__}: {e}")

        result = local_vars.get("result")

        # Convertir resultado a DataFrame
        if isinstance(result, pd.DataFrame):
            return result
        elif isinstance(result, pd.Series):
            return result.reset_index()
        elif isinstance(result, (int, float)):
            return pd.DataFrame({"Resultado": [result]})
        elif isinstance(result, (list, tuple)):
            return pd.DataFrame({"Resultado": result})
        elif isinstance(result, dict):
            return pd.DataFrame([result])
        elif hasattr(result, '__iter__') and not isinstance(result, str):
            return pd.DataFrame({"Resultado": list(result)})
        else:
            return pd.DataFrame({"Resultado": [str(result)]})

    def clear_history(self):
        """Limpia el historial de conversación y el contexto"""
        self.conversation_history = []
        self.last_query_result = None

    def get_table_info(self, table_name: str) -> dict:
        """Obtiene información detallada de una tabla"""
        try:
            df = self.dm.get_table_data(table_name)
            info = {
                "nombre": table_name,
                "filas": len(df),
                "columnas": list(df.columns),
                "tipos": {col: str(df[col].dtype) for col in df.columns},
                "muestra": df.head(3).to_dict('records')
            }
            return info
        except Exception as e:
            return {"error": str(e)}

    def get_available_tables(self) -> list:
        """Lista todas las tablas disponibles"""
        return self.dm.available_sheets


if __name__ == "__main__":
    engine = ClaudeQueryEngine()

    tests = [
        "¿Cuántos proyectos hay en Temuco?",
        "Muestra los proyectos en ejecución",
        "Beneficiarios por comuna"
    ]

    for q in tests:
        print(f"\n>>> {q}")
        r = engine.query(q)
        print(f"Explicación: {r.get('explicacion', 'N/A')}")
        if "datos" in r:
            print(r["datos"].head())
        if "error_ejecucion" in r:
            print(f"Error: {r['error_ejecucion']}")

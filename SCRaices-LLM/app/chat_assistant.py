"""
Chat Assistant - Motor del asistente de chat SCRaices

Detecta intención del usuario y ejecuta:
- Consultas de datos via Claude API
- Generación de reportes via ReportesEngine
"""
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

import pandas as pd
from dotenv import load_dotenv
from anthropic import Anthropic

from sheets_connection import SheetsConnection
from data_manager import DataManager
from reportes_engine import ReportesEngine
from claude_query import ClaudeQueryEngine
from etapas_engine import EtapasEngine

load_dotenv(Path(__file__).parent / ".env")

# Directorio para guardar reportes generados
REPORTES_DIR = Path(__file__).parent.parent / "reportes"
REPORTES_DIR.mkdir(exist_ok=True)


class IntentType(Enum):
    """Tipos de intención detectados"""
    SALUDO = "saludo"
    AYUDA = "ayuda"
    REPORTE_RESUMEN_BENEFICIARIO = "reporte_resumen_beneficiario"
    REPORTE_PAGO_MO_GRUPO = "reporte_pago_mo_grupo"
    REPORTE_ANALISIS_COMPARATIVO = "reporte_analisis_comparativo"
    DASHBOARD_CONTRATOS = "dashboard_contratos"
    FICHA_PROYECTO = "ficha_proyecto"
    COMPARATIVO_PROYECTOS = "comparativo_proyectos"
    GASTOS_PROYECTO = "gastos_proyecto"
    CIERRE_VIVIENDAS = "cierre_viviendas"
    CONSULTA_DATOS = "consulta_datos"
    DESCONOCIDO = "desconocido"


@dataclass
class ChatResponse:
    """Respuesta del asistente"""
    mensaje: str
    tipo_intent: IntentType
    archivo_generado: Optional[str] = None
    nombre_archivo: Optional[str] = None
    datos: Optional[Any] = None
    error: bool = False


class ChatAssistant:
    """
    Asistente de chat para SCRaices.
    Maneja consultas de datos y generación de reportes.
    """

    def __init__(self):
        self.conn = SheetsConnection()
        self.dm = DataManager()
        self.reportes_engine = ReportesEngine(self.conn)
        self.claude_engine = ClaudeQueryEngine()
        self.etapas_engine = EtapasEngine(self.dm)

        # Patrones para detectar reportes
        self._init_patterns()

    def _init_patterns(self):
        """Inicializa patrones regex para detección de intención"""

        # Patrones de saludo
        self.saludos = [
            r'^hola\b', r'^buenas?\b', r'^buenos?\b', r'^hey\b', r'^hi\b',
            r'^qué tal', r'^como estas', r'^saludos'
        ]

        # Patrones de ayuda
        self.ayuda = [
            r'\bayuda\b', r'\bhelp\b', r'qué puedes hacer', r'cómo funciona',
            r'qué reportes', r'opciones disponibles', r'comandos'
        ]

        # Patrones para Resumen de Beneficiario
        self.patron_resumen_beneficiario = [
            r'resumen\s+(?:de\s+)?(?:beneficiario|beneficiaria)\s+(?:para\s+)?(.+?)\s+(?:de|del|en)\s+(.+)',
            r'reporte\s+(?:de\s+)?(?:beneficiario|beneficiaria)\s+(?:para\s+)?(.+?)\s+(?:de|del|en)\s+(.+)',
            r'(?:beneficiario|beneficiaria)\s+(.+?)\s+(?:de|del|proyecto)\s+(.+)',
        ]

        # Patrones para Resumen Pago M.O Grupo
        self.patron_pago_mo_grupo = [
            r'resumen\s+(?:de\s+)?pagos?\s+(?:m\.?o\.?|mano\s+de\s+obra)\s+(?:de\s+)?(?:grupos?|proyecto)?\s*(?:para\s+)?(.+)',
            r'pagos?\s+(?:m\.?o\.?|mano\s+de\s+obra)\s+(?:de|del|para)\s+(.+)',
            r'excel\s+(?:de\s+)?pagos?\s+(?:para\s+)?(.+)',
        ]

        # Patrones para Análisis Comparativo M.O
        self.patron_analisis_comparativo = [
            r'an[aá]lisis\s+comparativo\s+(?:de\s+)?(?:m\.?o\.?|mano\s+de\s+obra)\s+(?:para\s+)?(.+)',
            r'comparativo\s+(?:m\.?o\.?|mano\s+de\s+obra)\s+(?:de|del|para)\s+(.+)',
            r'comparar\s+(?:m\.?o\.?|mano\s+de\s+obra)\s+(?:base|presupuesto)\s+(?:vs|con)\s+(?:real|pagos?)\s+(?:de|del|para)\s+(.+)',
            r'desviaci[oó]n\s+(?:de\s+)?(?:m\.?o\.?|mano\s+de\s+obra)\s+(?:de|del|para)\s+(.+)',
        ]

        # Patrones para Dashboard de Contratos/Plazos
        self.patron_dashboard_contratos = [
            r'dashboard\s+(?:de\s+)?contratos',
            r'resumen\s+(?:de\s+)?(?:contratos|plazos)',
            r'tabla\s+(?:de\s+)?(?:contratos|plazos)',
            r'contratos\s+(?:y|con)\s+plazos',
            r'plazos\s+(?:de\s+)?proyectos',
            r'estado\s+(?:de\s+)?(?:los\s+)?contratos',
            r'proyectos\s+(?:con\s+)?(?:sus\s+)?plazos',
            r'vencimiento(?:s)?\s+(?:de\s+)?(?:contratos|proyectos)',
        ]

        # Patrones para Ficha de Proyecto
        self.patron_ficha_proyecto = [
            r'ficha\s+(?:del?\s+)?proyecto\s+(.+)',
            r'ficha\s+(?:de\s+)?(.+)',
            r'informaci[oó]n\s+(?:del?\s+)?proyecto\s+(.+)',
            r'datos\s+(?:del?\s+)?proyecto\s+(.+)',
            r'detalle\s+(?:del?\s+)?proyecto\s+(.+)',
            r'proyecto\s+(.+)\s+(?:ficha|info|datos)',
        ]

        # Patrones para Comparativo entre Proyectos
        self.patron_comparativo_proyectos = [
            r'compar(?:ar?|aci[oó]n)\s+(?:de\s+)?(?:los\s+)?(?:ritmos?\s+(?:de\s+)?)?(?:despachos?)?\s*(?:entre\s+)?(.+?)\s+(?:y|con|vs\.?)\s+(.+)',
            r'compar(?:ar?|aci[oó]n)\s+(?:entre\s+)?(.+?)\s+(?:y|con|vs\.?)\s+(.+)',
            r'(.+?)\s+(?:vs\.?|versus)\s+(.+)',
        ]

        # Patrones para Gastos por Proyecto
        self.patron_gastos_proyecto = [
            r'gastos?\s+(?:generales?\s+)?(?:del?\s+)?(?:proyecto\s+)?(.+)',
            r'gastos?\s+(?:y\s+)?rendiciones?\s+(?:del?\s+)?(?:proyecto\s+)?(.+)',
            r'informe\s+(?:de\s+)?gastos?\s+(?:del?\s+)?(?:proyecto\s+)?(.+)',
            r'reporte\s+(?:de\s+)?gastos?\s+(?:del?\s+)?(?:proyecto\s+)?(.+)',
        ]

        # Patrones para Cierre de Viviendas por Grupo
        self.patron_cierre_viviendas = [
            r'cierre\s+(?:de\s+)?viviendas?\s+(?:del?\s+)?(?:grupo\s+)?(?:para\s+)?(.+)',
            r'd[ií]as?\s+(?:de\s+)?ejecuci[oó]n\s+(?:del?\s+)?(?:grupo\s+|proyecto\s+)?(.+)',
            r'tiempos?\s+(?:de\s+)?ejecuci[oó]n\s+(?:por\s+casa\s+)?(?:del?\s+)?(.+)',
            r'an[aá]lisis\s+(?:de\s+)?(?:d[ií]as?\s+)?(?:de\s+)?ejecuci[oó]n\s+(?:del?\s+)?(.+)',
            r'recepci[oó]n\s+(?:de\s+)?viviendas?\s+(?:del?\s+)?(.+)',
        ]

    def _detectar_intent(self, mensaje: str) -> Tuple[IntentType, Dict[str, str]]:
        """
        Detecta la intención del usuario y extrae parámetros.

        Returns:
            Tuple con (IntentType, dict de parámetros extraídos)
        """
        mensaje_lower = mensaje.lower().strip()

        # Detectar saludos
        for patron in self.saludos:
            if re.search(patron, mensaje_lower):
                return IntentType.SALUDO, {}

        # Detectar ayuda
        for patron in self.ayuda:
            if re.search(patron, mensaje_lower):
                return IntentType.AYUDA, {}

        # Detectar Comparativo entre Proyectos
        for patron in self.patron_comparativo_proyectos:
            match = re.search(patron, mensaje_lower)
            if match:
                proyecto1 = match.group(1).strip()
                proyecto2 = match.group(2).strip()
                # Limpiar palabras sueltas
                proyecto1 = re.sub(r'^(?:los\s+|de\s+|del\s+|proyecto\s+)', '', proyecto1)
                proyecto2 = re.sub(r'^(?:los\s+|de\s+|del\s+|proyecto\s+)', '', proyecto2)
                return IntentType.COMPARATIVO_PROYECTOS, {
                    "proyecto1": proyecto1,
                    "proyecto2": proyecto2
                }

        # Detectar Gastos por Proyecto
        for patron in self.patron_gastos_proyecto:
            match = re.search(patron, mensaje_lower)
            if match:
                proyecto = match.group(1).strip()
                proyecto = re.sub(r'^(?:de\s+|del\s+|para\s+)', '', proyecto)
                return IntentType.GASTOS_PROYECTO, {"proyecto": proyecto}

        # Detectar Cierre de Viviendas por Grupo
        for patron in self.patron_cierre_viviendas:
            match = re.search(patron, mensaje_lower)
            if match:
                proyecto = match.group(1).strip()
                proyecto = re.sub(r'^(?:de\s+|del\s+|para\s+)', '', proyecto)
                return IntentType.CIERRE_VIVIENDAS, {"proyecto": proyecto}

        # Detectar Dashboard de Contratos/Plazos
        for patron in self.patron_dashboard_contratos:
            if re.search(patron, mensaje_lower):
                return IntentType.DASHBOARD_CONTRATOS, {}

        # Detectar Ficha de Proyecto
        for patron in self.patron_ficha_proyecto:
            match = re.search(patron, mensaje_lower)
            if match:
                proyecto = match.group(1).strip()
                return IntentType.FICHA_PROYECTO, {"proyecto": proyecto}

        # Detectar Análisis Comparativo M.O (más específico, verificar primero)
        for patron in self.patron_analisis_comparativo:
            match = re.search(patron, mensaje_lower)
            if match:
                proyecto = match.group(1).strip()
                return IntentType.REPORTE_ANALISIS_COMPARATIVO, {"proyecto": proyecto}

        # Detectar Resumen Pago M.O Grupo
        for patron in self.patron_pago_mo_grupo:
            match = re.search(patron, mensaje_lower)
            if match:
                proyecto = match.group(1).strip()
                return IntentType.REPORTE_PAGO_MO_GRUPO, {"proyecto": proyecto}

        # Detectar Resumen de Beneficiario
        for patron in self.patron_resumen_beneficiario:
            match = re.search(patron, mensaje_lower)
            if match:
                beneficiario = match.group(1).strip()
                proyecto = match.group(2).strip()
                return IntentType.REPORTE_RESUMEN_BENEFICIARIO, {
                    "beneficiario": beneficiario,
                    "proyecto": proyecto
                }

        # Si no coincide con ningún patrón de reporte, es una consulta de datos
        return IntentType.CONSULTA_DATOS, {}

    def _responder_saludo(self) -> ChatResponse:
        """Genera respuesta a un saludo"""
        mensaje = """¡Hola! Soy el asistente de SCRaices. Puedo ayudarte con:

**Consultas de datos:**
- "¿Cuántos proyectos hay en Temuco?"
- "Beneficiarios del proyecto Ñuke Mapu"
- "Despachos pendientes esta semana"

**Generación de reportes:**
- **Resumen de Beneficiario:** "Resumen de beneficiario María Matus de Campesinos Esforzados"
- **Pagos M.O de Grupo:** "Resumen de pagos M.O para Mi Nuevo Hogar"
- **Análisis Comparativo M.O:** "Análisis comparativo de M.O para Com. Pedro Antivil"

**Tablas de resumen:**
- **Dashboard de Contratos:** "Dashboard de contratos" o "Resumen de plazos"
- **Ficha de Proyecto:** "Ficha del proyecto Ñuke Mapu" o "Ficha Ñuke Mapu"
- **Comparativo de Proyectos:** "Comparación de Pedro Antivil y Newen Ruka"
- **Gastos por Proyecto:** "Gastos de Raíces de Lanco" o "Informe de gastos proyecto X"
- **Cierre de Viviendas:** "Cierre de viviendas de Valles de Gorbea" o "Días de ejecución de Puyehue"

¿En qué puedo ayudarte?"""

        return ChatResponse(
            mensaje=mensaje,
            tipo_intent=IntentType.SALUDO
        )

    def _responder_ayuda(self) -> ChatResponse:
        """Genera respuesta de ayuda"""
        reportes = self.reportes_engine.get_reportes_disponibles()

        mensaje = """**Asistente SCRaices - Ayuda**

**Reportes disponibles:**
"""
        for r in reportes:
            mensaje += f"\n- **{r['nombre']}**\n"
            mensaje += f"  {r['descripcion']}\n"
            mensaje += f"  _Ejemplo: {r['ejemplo']}_\n"

        mensaje += """
**Consultas de datos:**
Puedes hacer preguntas en lenguaje natural sobre los datos:
- Proyectos, beneficiarios, despachos
- Pagos, ejecución, tipologías
- Filtros, conteos, agrupaciones

**Ejemplos:**
- "¿Cuántos beneficiarios tiene el proyecto X?"
- "Muestra los despachos del último mes"
- "Total de pagos aprobados por maestro"
"""

        return ChatResponse(
            mensaje=mensaje,
            tipo_intent=IntentType.AYUDA
        )

    def _generar_resumen_beneficiario(self, beneficiario: str, proyecto: str) -> ChatResponse:
        """Genera el reporte Resumen de Beneficiario"""
        try:
            # Generar datos del reporte
            reporte = self.reportes_engine.generar_resumen_beneficiario(
                nombre_beneficiario=beneficiario,
                nombre_proyecto=proyecto
            )

            if not reporte.get("encontrado"):
                return ChatResponse(
                    mensaje=f"No pude encontrar al beneficiario '{beneficiario}' en el proyecto '{proyecto}'. "
                           f"Error: {reporte.get('error', 'Desconocido')}",
                    tipo_intent=IntentType.REPORTE_RESUMEN_BENEFICIARIO,
                    error=True
                )

            # Generar PDF
            nombre_benef = reporte['identificacion']['Nombre'].replace(' ', '_')[:30]
            fecha_gen = datetime.now().strftime("%Y%m%d_%H%M")
            nombre_archivo = f"Resumen_{nombre_benef}_{fecha_gen}.pdf"
            ruta_archivo = str(REPORTES_DIR / nombre_archivo)

            self.reportes_engine.generar_pdf_resumen_beneficiario(reporte, ruta_archivo)

            # Mensaje de respuesta
            ident = reporte['identificacion']
            proy = reporte['proyecto']
            tip = reporte.get('tipologias', {})
            desp = reporte.get('despachos', {})
            pag = reporte.get('pagos', {})

            mensaje = f"""He generado el **Resumen de Beneficiario** para:

**{ident['Nombre']}** ({ident['RUT']})
- Proyecto: {proy['NOMBRE_PROYECTO']}
- Tipología: {tip.get('Vivienda', 'N/A')}

**Resumen:**
- Despachos realizados: {desp.get('total', 0)}
- Solicitudes de pago: {pag.get('total', 0)}
- Total aprobado: ${pag.get('total_aprobado', 0):,.0f}
- Total pendiente: ${pag.get('total_pendiente', 0):,.0f}

📄 El reporte PDF está disponible para descarga en el sidebar."""

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.REPORTE_RESUMEN_BENEFICIARIO,
                archivo_generado=ruta_archivo,
                nombre_archivo=nombre_archivo,
                datos=reporte
            )

        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar el reporte: {str(e)}",
                tipo_intent=IntentType.REPORTE_RESUMEN_BENEFICIARIO,
                error=True
            )

    def _generar_pago_mo_grupo(self, proyecto: str) -> ChatResponse:
        """Genera el reporte Resumen de Pago M.O de Grupo"""
        try:
            nombre_limpio = re.sub(r'[^a-zA-Z0-9_]', '_', proyecto)[:30]
            fecha_gen = datetime.now().strftime("%Y%m%d_%H%M")
            nombre_archivo = f"Pagos_MO_{nombre_limpio}_{fecha_gen}.xlsx"
            ruta_archivo = str(REPORTES_DIR / nombre_archivo)

            self.reportes_engine.generar_resumen_pago_mo_grupo(
                nombre_proyecto=proyecto,
                ruta_salida=ruta_archivo
            )

            mensaje = f"""He generado el **Resumen de Pagos M.O** para el proyecto.

📊 El archivo Excel contiene:
- Resumen del proyecto
- Pagos por beneficiario
- Detalle de todos los pagos
- Resumen por maestro

📁 El archivo está disponible para descarga en el sidebar."""

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.REPORTE_PAGO_MO_GRUPO,
                archivo_generado=ruta_archivo,
                nombre_archivo=nombre_archivo
            )

        except ValueError as e:
            return ChatResponse(
                mensaje=f"No pude encontrar el proyecto '{proyecto}'. Verifica el nombre e intenta de nuevo.",
                tipo_intent=IntentType.REPORTE_PAGO_MO_GRUPO,
                error=True
            )
        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar el reporte: {str(e)}",
                tipo_intent=IntentType.REPORTE_PAGO_MO_GRUPO,
                error=True
            )

    def _generar_analisis_comparativo(self, proyecto: str) -> ChatResponse:
        """Genera el reporte Análisis Comparativo de M.O"""
        try:
            nombre_limpio = re.sub(r'[^a-zA-Z0-9_]', '_', proyecto)[:30]
            fecha_gen = datetime.now().strftime("%Y%m%d_%H%M")
            nombre_archivo = f"Analisis_MO_{nombre_limpio}_{fecha_gen}.pdf"
            ruta_archivo = str(REPORTES_DIR / nombre_archivo)

            self.reportes_engine.generar_analisis_comparativo_mo(
                nombre_proyecto=proyecto,
                ruta_salida=ruta_archivo
            )

            mensaje = f"""He generado el **Análisis Comparativo de M.O** para el proyecto.

📊 El PDF contiene:
- Resumen ejecutivo con tipologías y totales
- Comparación Base vs Real por beneficiario
- Análisis de desviación por familia de pago
- Identificación de sobrecostos y ahorros

📄 El reporte está disponible para descarga en el sidebar."""

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.REPORTE_ANALISIS_COMPARATIVO,
                archivo_generado=ruta_archivo,
                nombre_archivo=nombre_archivo
            )

        except ValueError as e:
            return ChatResponse(
                mensaje=f"No pude encontrar el proyecto '{proyecto}'. Verifica el nombre e intenta de nuevo.",
                tipo_intent=IntentType.REPORTE_ANALISIS_COMPARATIVO,
                error=True
            )
        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar el reporte: {str(e)}",
                tipo_intent=IntentType.REPORTE_ANALISIS_COMPARATIVO,
                error=True
            )

    def _generar_ficha_proyecto(self, nombre_proyecto: str) -> ChatResponse:
        """Genera la ficha completa de un proyecto"""
        try:
            # Buscar proyecto
            proyectos = self.dm.get_table_data('Proyectos')
            mask = proyectos['NOMBRE_PROYECTO'].str.contains(nombre_proyecto, case=False, na=False)
            proy_encontrados = proyectos[mask]

            if proy_encontrados.empty:
                return ChatResponse(
                    mensaje=f"No encontré ningún proyecto con el nombre '{nombre_proyecto}'.",
                    tipo_intent=IntentType.FICHA_PROYECTO,
                    error=True
                )

            proy = proy_encontrados.iloc[0]
            id_proy = proy['ID_proy']
            nombre_proy = proy['NOMBRE_PROYECTO']

            # Obtener plazos
            plazos = self.etapas_engine.get_plazos_proyecto(id_proy)

            # Obtener beneficiarios
            beneficiarios = self.dm.get_table_data('Beneficiario')
            benef_proy = beneficiarios[beneficiarios['ID_Proy'] == id_proy]
            n_beneficiarios = len(benef_proy)

            # Obtener tipologías del proyecto y crear diccionario
            tipologias = self.dm.get_table_data('Tipologias')
            tip_dict = {}
            for _, t in tipologias.iterrows():
                tip_id = t['IDU_tipol']
                familia = t['Familia']
                caract = t['caracterizacion']
                dorm = t.get('dormitorios', '')
                plantas = t.get('plantas', '')
                tipologia = t.get('tipologia', '')

                if familia == 'Vivienda':
                    desc = f"Viv {dorm}D {plantas}P {caract}"
                else:
                    desc = f"{tipologia} {caract}"
                tip_dict[tip_id] = desc

            # Obtener montos
            try:
                montos = self.dm.get_table_data('Montos')
                montos_proy = montos[montos['ID_proy'] == id_proy].copy()

                cols_monto = ['Base', 'RAL', 'Ampliacion1', 'Ampliacion2', 'Terreno',
                              'Conexiones', 'Discapacidad', 'entorno', 'mejvivienda',
                              'incremento', 'homologacion', 'ajuste_ppto']

                for col in cols_monto:
                    if col in montos_proy.columns:
                        montos_proy[col] = pd.to_numeric(montos_proy[col], errors='coerce').fillna(0)

                monto_base = (montos_proy['Base'].sum() + montos_proy['RAL'].sum() +
                              montos_proy['Ampliacion1'].sum() + montos_proy['Ampliacion2'].sum() +
                              montos_proy['Terreno'].sum() + montos_proy['Conexiones'].sum() +
                              montos_proy['Discapacidad'].sum() + montos_proy['entorno'].sum() +
                              montos_proy['mejvivienda'].sum())

                monto_incremento = (montos_proy['incremento'].sum() +
                                    montos_proy['homologacion'].sum() +
                                    montos_proy['ajuste_ppto'].sum())

                monto_total = monto_base + monto_incremento
            except Exception:
                monto_base = 0
                monto_incremento = 0
                monto_total = 0

            # Formatear fechas
            fecha_inicio_str = ""
            fecha_termino_str = ""
            if plazos.get('fecha_inicio'):
                fecha_inicio_str = plazos['fecha_inicio'].strftime('%d/%m/%Y')
            if plazos.get('fecha_termino'):
                fecha_termino_str = plazos['fecha_termino'].strftime('%d/%m/%Y')

            # Construir mensaje
            mensaje = f"""## Ficha del Proyecto: {nombre_proy}

### Información General
| Campo | Valor |
|-------|-------|
| **ID** | {id_proy} |
| **Código Rukan** | {proy.get('cod_rukan', 'N/A')} |
| **Comuna** | {proy.get('COMUNA', '')} |
| **Periodo** | {proy.get('PERIODO', '')} |
| **Estado** | {proy.get('estado_general', '')} |
| **Encargado** | {str(proy.get('Encargado', '')).replace('@scraices.cl', '')} |
| **Total Beneficiarios** | {n_beneficiarios} |
| **Monto Base Original** | {monto_base:,.0f} UF |
| **Monto Incrementado** | {monto_incremento:,.0f} UF |
| **Monto Total Proyecto** | **{monto_total:,.0f} UF** |

### Plazos del Contrato
| Campo | Valor |
|-------|-------|
| Fecha Inicio | {fecha_inicio_str} |
| Duración Original | {plazos.get('duracion_original', 'N/A')} días |
| Duración Total | {plazos.get('duracion_total', 'N/A')} días |
| Fecha Término | {fecha_termino_str} |
| Días Transcurridos | {plazos.get('dias_transcurridos', 'N/A')} |
| **Días Restantes** | **{plazos.get('dias_restantes', 'N/A')}** |
| Avance Tiempo | {plazos.get('avance_tiempo', 0):.1f}% |
| Estado Plazo | {plazos.get('estado_plazo', 'N/A')} |

### Listado de Beneficiarios y Tipologías
"""
            # Crear listado de beneficiarios con tipologías y estado
            listado_benef = []
            for i, (_, b) in enumerate(benef_proy.iterrows(), 1):
                nombre = f"{b['NOMBRES']} {b['APELLIDOS']}"
                tip_viv_id = b.get('Tipologia Vivienda', '')
                tip_rc_id = b.get('Tipologia RC', '')

                tip_viv = tip_dict.get(tip_viv_id, 'Sin asignar') if tip_viv_id else 'Sin asignar'
                tip_rc = tip_dict.get(tip_rc_id, 'Sin asignar') if tip_rc_id else 'Sin asignar'

                # Estado y Hábil para construir
                estado = b.get('Estado', '')
                habil = b.get('Habil para construir', '')
                habil_str = 'Sí' if str(habil).upper() == 'TRUE' else 'No'

                listado_benef.append({
                    'N°': i,
                    'Beneficiario': nombre,
                    'Estado': estado,
                    'Hábil': habil_str,
                    'Tipología Vivienda': tip_viv,
                    'Tipología RC': tip_rc
                })

            # Crear DataFrame de beneficiarios
            df_beneficiarios = pd.DataFrame(listado_benef)

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.FICHA_PROYECTO,
                datos=df_beneficiarios
            )

        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar la ficha: {str(e)}",
                tipo_intent=IntentType.FICHA_PROYECTO,
                error=True
            )

    def _generar_dashboard_contratos(self) -> ChatResponse:
        """Genera el dashboard de contratos y plazos"""
        try:
            df = self.etapas_engine.get_dashboard_contratos()

            # Contar estados
            vencidos = len(df[df['Estado_Plazo'] == 'vencido'])
            proximo_vencer = len(df[df['Estado_Plazo'] == 'proximo_vencer'])
            en_tiempo = len(df[df['Estado_Plazo'] == 'en_tiempo'])
            finalizados = len(df[df['Estado_General'].str.lower().str.contains('finalizado', na=False)])

            mensaje = f"""**Dashboard de Contratos y Plazos**

**Resumen:** {len(df)} proyectos activos
- Vencidos: {vencidos}
- Próximos a vencer: {proximo_vencer}
- En tiempo: {en_tiempo}
- Finalizados: {finalizados}

La tabla muestra todos los proyectos con sus plazos, ordenados por días restantes (los más urgentes primero)."""

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.DASHBOARD_CONTRATOS,
                datos=df
            )

        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar el dashboard: {str(e)}",
                tipo_intent=IntentType.DASHBOARD_CONTRATOS,
                error=True
            )

    def _generar_comparativo_proyectos(self, nombre_proy1: str, nombre_proy2: str) -> ChatResponse:
        """Genera un PDF comparativo entre dos proyectos (despachos y pagos por tipología)"""
        try:
            from fpdf import FPDF

            # Buscar proyectos
            proyectos = self.dm.get_table_data('Proyectos')

            # Proyecto 1
            mask1 = proyectos['NOMBRE_PROYECTO'].str.contains(nombre_proy1, case=False, na=False)
            proy1_df = proyectos[mask1]
            if proy1_df.empty:
                return ChatResponse(
                    mensaje=f"No encontré el proyecto '{nombre_proy1}'.",
                    tipo_intent=IntentType.COMPARATIVO_PROYECTOS,
                    error=True
                )
            proy1 = proy1_df.iloc[0]
            id_proy1 = proy1['ID_proy']
            nombre_proy1_full = proy1['NOMBRE_PROYECTO']

            # Proyecto 2
            mask2 = proyectos['NOMBRE_PROYECTO'].str.contains(nombre_proy2, case=False, na=False)
            proy2_df = proyectos[mask2]
            if proy2_df.empty:
                return ChatResponse(
                    mensaje=f"No encontré el proyecto '{nombre_proy2}'.",
                    tipo_intent=IntentType.COMPARATIVO_PROYECTOS,
                    error=True
                )
            proy2 = proy2_df.iloc[0]
            id_proy2 = proy2['ID_proy']
            nombre_proy2_full = proy2['NOMBRE_PROYECTO']

            # Obtener tipologías
            tipologias = self.dm.get_table_data('Tipologias')

            def get_tipologia_info(tip_id):
                tip = tipologias[tipologias['IDU_tipol'] == tip_id]
                if tip.empty:
                    return {'dormitorios': 'N/A', 'bodega': 'No', 'desc': 'Sin asignar'}
                t = tip.iloc[0]
                dorm = t.get('dormitorios', 'N/A')
                familia = t.get('Familia', '')
                tipologia = t.get('tipologia', '')
                caract = t.get('caracterizacion', '')
                bodega = 'Sí' if 'bodega' in str(tipologia).lower() or 'bodega' in str(caract).lower() else 'No'
                if familia == 'R.Complementario':
                    bodega = 'Sí' if 'bodega' in str(tipologia).lower() else 'N/A'
                return {'dormitorios': dorm, 'bodega': bodega, 'desc': f"{dorm} {caract}".strip()}

            # Obtener beneficiarios
            beneficiarios = self.dm.get_table_data('Beneficiario')
            benef1 = beneficiarios[beneficiarios['ID_Proy'] == id_proy1]
            benef2 = beneficiarios[beneficiarios['ID_Proy'] == id_proy2]

            # Obtener despachos
            despachos = self.dm.get_table_data('Despacho')
            desp1 = despachos[despachos['ID_proy'] == id_proy1].copy()
            desp2 = despachos[despachos['ID_proy'] == id_proy2].copy()

            # Calcular ritmo de despachos
            def calcular_ritmo(desp_df):
                if desp_df.empty:
                    return {'total': 0, 'por_tipo': {}, 'fechas': []}
                desp_df = desp_df.copy()
                desp_df['Fecha'] = pd.to_datetime(desp_df['Fecha'], errors='coerce')
                desp_df = desp_df.dropna(subset=['Fecha'])
                if desp_df.empty:
                    return {'total': 0, 'por_tipo': {}, 'fechas': []}

                total = len(desp_df)

                # Separar tipos de despacho combinados (ej: "01- Fund,06- Alcan" -> ["01- Fund", "06- Alcan"])
                por_tipo = {}
                for tipo_raw in desp_df['Tipo_despacho'].dropna():
                    # Separar por coma si hay múltiples etapas en una guía
                    etapas = [e.strip() for e in str(tipo_raw).split(',') if e.strip()]
                    for etapa in etapas:
                        # Normalizar nombre (tomar solo código y nombre principal)
                        etapa_limpia = etapa.strip()
                        if etapa_limpia:
                            por_tipo[etapa_limpia] = por_tipo.get(etapa_limpia, 0) + 1

                fechas = desp_df['Fecha'].sort_values()
                if len(fechas) > 1:
                    dias_entre = (fechas.iloc[-1] - fechas.iloc[0]).days
                    prom_dias = dias_entre / (len(fechas) - 1) if len(fechas) > 1 else 0
                else:
                    prom_dias = 0

                return {
                    'total': total,
                    'total_etapas': sum(por_tipo.values()),  # Total de etapas despachadas
                    'por_tipo': por_tipo,
                    'fecha_inicio': fechas.iloc[0] if len(fechas) > 0 else None,
                    'fecha_fin': fechas.iloc[-1] if len(fechas) > 0 else None,
                    'promedio_dias_entre_despachos': round(prom_dias, 1)
                }

            ritmo1 = calcular_ritmo(desp1)
            ritmo2 = calcular_ritmo(desp2)

            # Obtener pagos (Solpago)
            solpagos = self.dm.get_table_data('Solpago')

            def parsear_monto(valor):
                """Convierte monto de formato texto a número"""
                if pd.isna(valor) or valor == '':
                    return 0
                # Formato: $966.683,00 -> 966683.00
                s = str(valor).replace('$', '').replace('.', '').replace(',', '.').strip()
                try:
                    return float(s)
                except:
                    return 0

            def get_pagos_por_tipologia(benef_df, solpagos_df, tipologias_df):
                """Agrupa pagos por tipo de vivienda (dormitorios)"""
                # Familias de pago que son Mano de Obra (etapas constructivas)
                familias_mo = [
                    '01 - Fundaciones', '02 - 1era Etapa', '03 - 2da Etapa',
                    '04 - Gasfiteria', '05 - Cerámica', '06 - Pintura',
                    '07 - Eléctricidad', '08 - Obras Exteriores', '11 - Recepcion'
                ]

                result = {}
                for _, b in benef_df.iterrows():
                    tip_viv_id = b.get('Tipologia Vivienda', '')
                    tip_info = get_tipologia_info(tip_viv_id)
                    dorm = tip_info['dormitorios']
                    bodega = tip_info['bodega']

                    # Filtrar pagos de este beneficiario (solo etapas de M.O)
                    pagos_benef = solpagos_df[solpagos_df['ID_Benef'] == b['ID_Benef']]
                    pagos_benef = pagos_benef[pagos_benef['Familia_pago'].isin(familias_mo)]

                    # Parsear montos
                    total_pagado = sum(parsear_monto(m) for m in pagos_benef['monto'])

                    key = f"{dorm} dorm"
                    if key not in result:
                        result[key] = {'total': 0, 'n_casas': 0, 'con_bodega': 0}
                    result[key]['total'] += total_pagado
                    result[key]['n_casas'] += 1
                    if bodega == 'Sí':
                        result[key]['con_bodega'] += 1

                # Calcular promedios
                for key in result:
                    if result[key]['n_casas'] > 0:
                        result[key]['promedio'] = result[key]['total'] / result[key]['n_casas']
                    else:
                        result[key]['promedio'] = 0

                return result

            pagos1 = get_pagos_por_tipologia(benef1, solpagos, tipologias)
            pagos2 = get_pagos_por_tipologia(benef2, solpagos, tipologias)

            # Generar PDF
            class ComparativoPDF(FPDF):
                def header(self):
                    self.set_fill_color(44, 44, 44)
                    self.rect(0, 0, 210, 20, 'F')
                    self.set_text_color(255, 255, 255)
                    self.set_font('Helvetica', 'B', 14)
                    self.cell(0, 20, 'Comparativo de Proyectos - SCRaices', 0, 1, 'C')
                    self.set_text_color(0, 0, 0)
                    self.ln(5)

                def footer(self):
                    self.set_y(-15)
                    self.set_font('Helvetica', 'I', 8)
                    self.set_text_color(128)
                    self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

            pdf = ComparativoPDF()
            pdf.add_page()

            # Título
            pdf.set_font('Helvetica', 'B', 16)
            pdf.set_text_color(196, 30, 58)
            pdf.cell(0, 10, f'{nombre_proy1_full} vs {nombre_proy2_full}', 0, 1, 'C')
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Helvetica', '', 10)
            pdf.cell(0, 6, f'Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
            pdf.ln(10)

            # Sección 1: Información General
            pdf.set_font('Helvetica', 'B', 12)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, '1. INFORMACIÓN GENERAL', 0, 1, 'L', True)
            pdf.ln(3)

            pdf.set_font('Helvetica', '', 10)
            col_w = 63
            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(col_w, 7, 'Concepto', 1, 0, 'C')
            pdf.cell(col_w, 7, nombre_proy1_full[:25], 1, 0, 'C')
            pdf.cell(col_w, 7, nombre_proy2_full[:25], 1, 1, 'C')

            pdf.set_font('Helvetica', '', 10)
            pdf.cell(col_w, 6, 'Total Beneficiarios', 1, 0, 'L')
            pdf.cell(col_w, 6, str(len(benef1)), 1, 0, 'C')
            pdf.cell(col_w, 6, str(len(benef2)), 1, 1, 'C')

            pdf.cell(col_w, 6, 'Total Guías de Despacho', 1, 0, 'L')
            pdf.cell(col_w, 6, str(ritmo1['total']), 1, 0, 'C')
            pdf.cell(col_w, 6, str(ritmo2['total']), 1, 1, 'C')

            pdf.cell(col_w, 6, 'Total Etapas Despachadas', 1, 0, 'L')
            pdf.cell(col_w, 6, str(ritmo1.get('total_etapas', 0)), 1, 0, 'C')
            pdf.cell(col_w, 6, str(ritmo2.get('total_etapas', 0)), 1, 1, 'C')

            pdf.cell(col_w, 6, 'Guías por Beneficiario', 1, 0, 'L')
            dpb1 = round(ritmo1['total'] / len(benef1), 1) if len(benef1) > 0 else 0
            dpb2 = round(ritmo2['total'] / len(benef2), 1) if len(benef2) > 0 else 0
            pdf.cell(col_w, 6, str(dpb1), 1, 0, 'C')
            pdf.cell(col_w, 6, str(dpb2), 1, 1, 'C')
            pdf.ln(8)

            # Sección 2: Ritmo de Despachos
            pdf.set_font('Helvetica', 'B', 12)
            pdf.cell(0, 8, '2. RITMO DE DESPACHOS', 0, 1, 'L', True)
            pdf.ln(3)

            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(col_w, 7, 'Métrica', 1, 0, 'C')
            pdf.cell(col_w, 7, nombre_proy1_full[:25], 1, 0, 'C')
            pdf.cell(col_w, 7, nombre_proy2_full[:25], 1, 1, 'C')

            pdf.set_font('Helvetica', '', 10)
            fecha_ini1 = ritmo1.get('fecha_inicio')
            fecha_ini2 = ritmo2.get('fecha_inicio')
            pdf.cell(col_w, 6, 'Primer despacho', 1, 0, 'L')
            pdf.cell(col_w, 6, fecha_ini1.strftime('%d/%m/%Y') if fecha_ini1 else 'N/A', 1, 0, 'C')
            pdf.cell(col_w, 6, fecha_ini2.strftime('%d/%m/%Y') if fecha_ini2 else 'N/A', 1, 1, 'C')

            fecha_fin1 = ritmo1.get('fecha_fin')
            fecha_fin2 = ritmo2.get('fecha_fin')
            pdf.cell(col_w, 6, 'Último despacho', 1, 0, 'L')
            pdf.cell(col_w, 6, fecha_fin1.strftime('%d/%m/%Y') if fecha_fin1 else 'N/A', 1, 0, 'C')
            pdf.cell(col_w, 6, fecha_fin2.strftime('%d/%m/%Y') if fecha_fin2 else 'N/A', 1, 1, 'C')

            pdf.cell(col_w, 6, 'Días prom. entre despachos', 1, 0, 'L')
            pdf.cell(col_w, 6, f"{ritmo1.get('promedio_dias_entre_despachos', 0)} días", 1, 0, 'C')
            pdf.cell(col_w, 6, f"{ritmo2.get('promedio_dias_entre_despachos', 0)} días", 1, 1, 'C')

            # Despachos por tipo
            pdf.ln(3)
            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(0, 6, 'Despachos por Tipo de Etapa:', 0, 1, 'L')

            todos_tipos = set(list(ritmo1.get('por_tipo', {}).keys()) + list(ritmo2.get('por_tipo', {}).keys()))
            pdf.set_font('Helvetica', '', 9)
            for tipo in sorted(todos_tipos):
                cant1 = ritmo1.get('por_tipo', {}).get(tipo, 0)
                cant2 = ritmo2.get('por_tipo', {}).get(tipo, 0)
                pdf.cell(col_w, 5, str(tipo)[:30], 1, 0, 'L')
                pdf.cell(col_w, 5, str(cant1), 1, 0, 'C')
                pdf.cell(col_w, 5, str(cant2), 1, 1, 'C')

            pdf.ln(8)

            # Sección 3: Pagos por Tipología
            pdf.set_font('Helvetica', 'B', 12)
            pdf.cell(0, 8, '3. PAGOS M.O POR TIPOLOGÍA DE VIVIENDA', 0, 1, 'L', True)
            pdf.ln(3)

            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(40, 7, 'Tipología', 1, 0, 'C')
            pdf.cell(35, 7, 'N° Casas', 1, 0, 'C')
            pdf.cell(35, 7, 'Con Bodega', 1, 0, 'C')
            pdf.cell(40, 7, 'Total Pagado', 1, 0, 'C')
            pdf.cell(40, 7, 'Promedio/Casa', 1, 1, 'C')

            # Proyecto 1
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_fill_color(220, 220, 220)
            pdf.cell(190, 6, nombre_proy1_full, 1, 1, 'L', True)

            pdf.set_font('Helvetica', '', 9)
            for tip, data in sorted(pagos1.items()):
                pdf.cell(40, 5, tip, 1, 0, 'L')
                pdf.cell(35, 5, str(data['n_casas']), 1, 0, 'C')
                pdf.cell(35, 5, str(data['con_bodega']), 1, 0, 'C')
                pdf.cell(40, 5, f"${data['total']:,.0f}", 1, 0, 'R')
                pdf.cell(40, 5, f"${data['promedio']:,.0f}", 1, 1, 'R')

            # Proyecto 2
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(190, 6, nombre_proy2_full, 1, 1, 'L', True)

            pdf.set_font('Helvetica', '', 9)
            for tip, data in sorted(pagos2.items()):
                pdf.cell(40, 5, tip, 1, 0, 'L')
                pdf.cell(35, 5, str(data['n_casas']), 1, 0, 'C')
                pdf.cell(35, 5, str(data['con_bodega']), 1, 0, 'C')
                pdf.cell(40, 5, f"${data['total']:,.0f}", 1, 0, 'R')
                pdf.cell(40, 5, f"${data['promedio']:,.0f}", 1, 1, 'R')

            pdf.ln(8)

            # Sección 4: Comparación Directa de Tipologías Similares
            pdf.set_font('Helvetica', 'B', 12)
            pdf.cell(0, 8, '4. COMPARACIÓN DIRECTA POR TIPOLOGÍA', 0, 1, 'L', True)
            pdf.ln(3)

            pdf.set_font('Helvetica', 'B', 10)
            pdf.cell(40, 7, 'Tipología', 1, 0, 'C')
            pdf.cell(50, 7, f'Prom. {nombre_proy1_full[:15]}', 1, 0, 'C')
            pdf.cell(50, 7, f'Prom. {nombre_proy2_full[:15]}', 1, 0, 'C')
            pdf.cell(50, 7, 'Diferencia', 1, 1, 'C')

            pdf.set_font('Helvetica', '', 9)
            tipologias_comunes = set(pagos1.keys()) & set(pagos2.keys())
            for tip in sorted(tipologias_comunes):
                prom1 = pagos1[tip]['promedio']
                prom2 = pagos2[tip]['promedio']
                diff = prom1 - prom2
                diff_pct = (diff / prom2 * 100) if prom2 > 0 else 0

                pdf.cell(40, 5, tip, 1, 0, 'L')
                pdf.cell(50, 5, f"${prom1:,.0f}", 1, 0, 'R')
                pdf.cell(50, 5, f"${prom2:,.0f}", 1, 0, 'R')

                if diff > 0:
                    pdf.set_text_color(196, 30, 58)  # Rojo si proy1 > proy2
                    pdf.cell(50, 5, f"+${diff:,.0f} ({diff_pct:+.1f}%)", 1, 1, 'R')
                else:
                    pdf.set_text_color(40, 167, 69)  # Verde si proy1 < proy2
                    pdf.cell(50, 5, f"${diff:,.0f} ({diff_pct:+.1f}%)", 1, 1, 'R')
                pdf.set_text_color(0, 0, 0)

            # Guardar PDF
            fecha_gen = datetime.now().strftime("%Y%m%d_%H%M")
            nombre_p1 = re.sub(r'[^a-zA-Z0-9]', '', nombre_proy1)[:15]
            nombre_p2 = re.sub(r'[^a-zA-Z0-9]', '', nombre_proy2)[:15]
            nombre_archivo = f"Comparativo_{nombre_p1}_vs_{nombre_p2}_{fecha_gen}.pdf"
            ruta_archivo = str(REPORTES_DIR / nombre_archivo)

            pdf.output(ruta_archivo)

            # Mensaje resumen
            mensaje = f"""**Comparativo generado:** {nombre_proy1_full} vs {nombre_proy2_full}

**Ritmo de Despachos:**
| Métrica | {nombre_proy1_full[:20]} | {nombre_proy2_full[:20]} |
|---------|------------|------------|
| Total Guías | {ritmo1['total']} | {ritmo2['total']} |
| Total Etapas | {ritmo1.get('total_etapas', 0)} | {ritmo2.get('total_etapas', 0)} |
| Guías/Benef | {dpb1} | {dpb2} |
| Días prom. entre desp. | {ritmo1.get('promedio_dias_entre_despachos', 0)} | {ritmo2.get('promedio_dias_entre_despachos', 0)} |

**Pagos M.O promedio por tipología:**
"""
            for tip in sorted(tipologias_comunes):
                prom1 = pagos1[tip]['promedio']
                prom2 = pagos2[tip]['promedio']
                diff = prom1 - prom2
                mensaje += f"- **{tip}**: ${prom1:,.0f} vs ${prom2:,.0f} (dif: ${diff:+,.0f})\n"

            mensaje += "\n📄 El PDF con el análisis completo está disponible en el sidebar."

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.COMPARATIVO_PROYECTOS,
                archivo_generado=ruta_archivo,
                nombre_archivo=nombre_archivo
            )

        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar el comparativo: {str(e)}",
                tipo_intent=IntentType.COMPARATIVO_PROYECTOS,
                error=True
            )

    def _generar_gastos_proyecto(self, nombre_proyecto: str) -> ChatResponse:
        """Genera el informe de Gastos Generales y Rendiciones de un proyecto"""
        try:
            from generar_informe_gg import generar_informe_gg_rendiciones

            ruta = generar_informe_gg_rendiciones(nombre_proyecto)

            if ruta is None:
                return ChatResponse(
                    mensaje=f"No encontré el proyecto '{nombre_proyecto}'. Verifica el nombre.",
                    tipo_intent=IntentType.GASTOS_PROYECTO,
                    error=True
                )

            nombre_archivo = Path(ruta).name

            mensaje = f"""He generado el **Informe de Gastos por Proyecto**.

El PDF contiene:
- **Gastos Generales**: Facturas de pago directo por categoría (Áridos, Conservador, Notaría, etc.)
- **Rendiciones**: Reembolsos solicitados por clase y por usuario
- **Resumen Ejecutivo**: Totales y Top 5 de cada categoría

📄 El archivo está disponible para descarga en el sidebar."""

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.GASTOS_PROYECTO,
                archivo_generado=str(REPORTES_DIR / nombre_archivo),
                nombre_archivo=nombre_archivo
            )

        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar el informe de gastos: {str(e)}",
                tipo_intent=IntentType.GASTOS_PROYECTO,
                error=True
            )

    def _generar_cierre_viviendas(self, nombre_proyecto: str) -> ChatResponse:
        """Genera el informe de Cierre de Viviendas (días de ejecución por casa)"""
        try:
            from generar_dias_ejecucion import generar_informe_dias_ejecucion

            # Buscar proyecto
            proyecto = self.reportes_engine._buscar_proyecto(nombre_proyecto)
            if not proyecto:
                return ChatResponse(
                    mensaje=f"No encontré el proyecto '{nombre_proyecto}'. Verifica el nombre.",
                    tipo_intent=IntentType.CIERRE_VIVIENDAS,
                    error=True
                )

            id_proy = proyecto['ID_proy']
            nombre_proy = proyecto['NOMBRE_PROYECTO']

            # Generar nombre de archivo
            nombre_limpio = nombre_proy.replace(' ', '_').replace('°', '')[:30]
            fecha_gen = datetime.now().strftime("%Y%m%d_%H%M")
            nombre_archivo = f"Cierre_Viviendas_{nombre_limpio}_{fecha_gen}.pdf"
            ruta_archivo = str(REPORTES_DIR / nombre_archivo)

            # Generar informe
            proyectos_ids = [(id_proy, nombre_proy)]
            ruta, resumen = generar_informe_dias_ejecucion(proyectos_ids, ruta_archivo)

            if not resumen:
                return ChatResponse(
                    mensaje=f"No hay datos de cierre de viviendas para '{nombre_proy}'. "
                           f"Verifica que existan fechas de despacho y recepción.",
                    tipo_intent=IntentType.CIERRE_VIVIENDAS,
                    error=True
                )

            r = resumen[0]
            mensaje = f"""He generado el **Informe de Cierre de Viviendas** para **{nombre_proy}**.

**Resumen:**
- Casas con datos completos: {r['casas']}
- Promedio días de ejecución: {r['promedio']:.0f} días
- Mínimo: {r['minimo']} días
- Máximo: {r['maximo']} días

El PDF incluye detalle por beneficiario con fecha de 1er despacho, recepción y días de ejecución.

📄 El archivo está disponible para descarga en el sidebar."""

            return ChatResponse(
                mensaje=mensaje,
                tipo_intent=IntentType.CIERRE_VIVIENDAS,
                archivo_generado=ruta_archivo,
                nombre_archivo=nombre_archivo,
                datos=resumen
            )

        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al generar el informe de cierre de viviendas: {str(e)}",
                tipo_intent=IntentType.CIERRE_VIVIENDAS,
                error=True
            )

    def _consulta_datos(self, mensaje: str) -> ChatResponse:
        """Procesa una consulta de datos usando Claude"""
        try:
            resultado = self.claude_engine.query(mensaje)

            if resultado.get('exito'):
                explicacion = resultado.get('explicacion', '')
                datos = resultado.get('datos')

                # Formatear respuesta
                respuesta = f"{explicacion}"

                if datos is not None and len(datos) > 0:
                    # Limitar filas mostradas
                    if len(datos) > 10:
                        respuesta += f"\n\n_Mostrando 10 de {len(datos)} resultados._"

                return ChatResponse(
                    mensaje=respuesta,
                    tipo_intent=IntentType.CONSULTA_DATOS,
                    datos=datos
                )
            else:
                error = resultado.get('error_ejecucion', resultado.get('explicacion', 'Error desconocido'))
                return ChatResponse(
                    mensaje=f"No pude procesar esa consulta. {error}",
                    tipo_intent=IntentType.CONSULTA_DATOS,
                    error=True
                )

        except Exception as e:
            return ChatResponse(
                mensaje=f"Error al procesar la consulta: {str(e)}",
                tipo_intent=IntentType.CONSULTA_DATOS,
                error=True
            )

    def procesar_mensaje(self, mensaje: str) -> ChatResponse:
        """
        Procesa un mensaje del usuario y retorna la respuesta apropiada.

        Args:
            mensaje: Texto del mensaje del usuario

        Returns:
            ChatResponse con la respuesta del asistente
        """
        if not mensaje or not mensaje.strip():
            return ChatResponse(
                mensaje="No recibí ningún mensaje. ¿En qué puedo ayudarte?",
                tipo_intent=IntentType.DESCONOCIDO
            )

        # Detectar intención
        intent, params = self._detectar_intent(mensaje)

        # Ejecutar acción según intención
        if intent == IntentType.SALUDO:
            return self._responder_saludo()

        elif intent == IntentType.AYUDA:
            return self._responder_ayuda()

        elif intent == IntentType.REPORTE_RESUMEN_BENEFICIARIO:
            return self._generar_resumen_beneficiario(
                params.get('beneficiario', ''),
                params.get('proyecto', '')
            )

        elif intent == IntentType.REPORTE_PAGO_MO_GRUPO:
            return self._generar_pago_mo_grupo(params.get('proyecto', ''))

        elif intent == IntentType.REPORTE_ANALISIS_COMPARATIVO:
            return self._generar_analisis_comparativo(params.get('proyecto', ''))

        elif intent == IntentType.DASHBOARD_CONTRATOS:
            return self._generar_dashboard_contratos()

        elif intent == IntentType.FICHA_PROYECTO:
            return self._generar_ficha_proyecto(params.get('proyecto', ''))

        elif intent == IntentType.COMPARATIVO_PROYECTOS:
            return self._generar_comparativo_proyectos(
                params.get('proyecto1', ''),
                params.get('proyecto2', '')
            )

        elif intent == IntentType.GASTOS_PROYECTO:
            return self._generar_gastos_proyecto(params.get('proyecto', ''))

        elif intent == IntentType.CIERRE_VIVIENDAS:
            return self._generar_cierre_viviendas(params.get('proyecto', ''))

        elif intent == IntentType.CONSULTA_DATOS:
            return self._consulta_datos(mensaje)

        else:
            return ChatResponse(
                mensaje="No entendí tu solicitud. Escribe 'ayuda' para ver las opciones disponibles.",
                tipo_intent=IntentType.DESCONOCIDO
            )

    def limpiar_historial(self):
        """Limpia el historial de conversación del motor de consultas"""
        self.claude_engine.clear_history()

    def get_reportes_disponibles(self) -> List[dict]:
        """Retorna la lista de reportes disponibles"""
        return self.reportes_engine.get_reportes_disponibles()


# === TEST ===
if __name__ == "__main__":
    assistant = ChatAssistant()

    tests = [
        "Hola",
        "ayuda",
        "¿Cuántos proyectos hay?",
        "Análisis comparativo de M.O para Ñuke Mapu",
        "Resumen de pagos M.O para Mi Nuevo Hogar",
    ]

    for msg in tests:
        print(f"\n>>> {msg}")
        response = assistant.procesar_mensaje(msg)
        print(f"Intent: {response.tipo_intent.value}")
        print(f"Mensaje: {response.mensaje[:200]}...")
        if response.archivo_generado:
            print(f"Archivo: {response.nombre_archivo}")

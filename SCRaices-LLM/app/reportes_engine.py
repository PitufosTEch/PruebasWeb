"""
Motor de Reportes - Genera reportes tipo predefinidos
"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any

try:
    from fpdf import FPDF
    PDF_DISPONIBLE = True
except ImportError:
    PDF_DISPONIBLE = False

CONFIG_PATH = Path(__file__).parent.parent / "config" / "reportes_config.json"


class ReportesEngine:
    """Motor para generación de reportes tipo predefinidos"""

    def __init__(self, sheets_connection):
        """
        Args:
            sheets_connection: Instancia de SheetsConnection para acceder a datos
        """
        self.conn = sheets_connection
        self.config = self._load_config()
        self._cache = {}

    def _load_config(self) -> dict:
        """Carga configuración de reportes desde JSON"""
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"reportes": {}}

    def reload_config(self):
        """Recarga la configuración"""
        self.config = self._load_config()
        self._cache = {}

    def get_reportes_disponibles(self) -> List[dict]:
        """Lista los reportes tipo disponibles"""
        reportes = []
        for key, cfg in self.config.get("reportes", {}).items():
            reportes.append({
                "codigo": key,
                "nombre": cfg.get("nombre", key),
                "descripcion": cfg.get("descripcion", ""),
                "parametros": cfg.get("parametros_requeridos", []),
                "ejemplo": cfg.get("ejemplo_invocacion", "")
            })
        return reportes

    # ========================================================================
    # REPORTE: RESUMEN DE BENEFICIARIO
    # ========================================================================

    def _get_tabla_con_duplicados(self, nombre_tabla: str) -> pd.DataFrame:
        """
        Lee una tabla que puede tener columnas duplicadas.
        Renombra duplicados agregando _1, _2, etc.
        """
        worksheet = self.conn.spreadsheet.worksheet(nombre_tabla)
        all_values = worksheet.get_all_values()

        if not all_values:
            return pd.DataFrame()

        headers = all_values[0]

        # Renombrar duplicados
        seen = {}
        new_headers = []
        for h in headers:
            if h in seen:
                seen[h] += 1
                new_headers.append(f'{h}_{seen[h]}')
            else:
                seen[h] = 0
                new_headers.append(h)

        return pd.DataFrame(all_values[1:], columns=new_headers)

    def _buscar_proyecto(self, nombre_proyecto: str) -> Optional[dict]:
        """Busca un proyecto por nombre (parcial)"""
        proyectos = self.conn.get_sheet_data('Proyectos')

        # Buscar por nombre (contiene, case insensitive)
        mask = proyectos['NOMBRE_PROYECTO'].str.contains(nombre_proyecto, case=False, na=False)
        encontrados = proyectos[mask]

        if encontrados.empty:
            return None

        row = encontrados.iloc[0]
        return {
            'ID_proy': row['ID_proy'],
            'NOMBRE_PROYECTO': row['NOMBRE_PROYECTO'],
            'COMUNA': row['COMUNA'],
            'PERIODO': row.get('PERIODO', ''),
            'Encargado': row.get('Encargado', ''),
            'estado_general': row.get('estado_general', ''),
            'fecha_inicio': row.get('fecha_inicio', ''),
            'duracion': row.get('duracion', '')
        }

    def _buscar_beneficiario(self, nombre_benef: str, id_proy: str) -> Optional[dict]:
        """Busca un beneficiario por nombre/apellido en un proyecto"""
        beneficiarios = self.conn.get_sheet_data('Beneficiario')

        # Filtrar por proyecto
        benef_proy = beneficiarios[beneficiarios['ID_Proy'] == id_proy]

        # Buscar por apellido (contiene, case insensitive)
        # Intentar con cada palabra del nombre
        palabras = nombre_benef.split()
        for palabra in palabras:
            if len(palabra) > 3:  # Ignorar palabras muy cortas
                mask = benef_proy['APELLIDOS'].str.contains(palabra, case=False, na=False)
                encontrados = benef_proy[mask]
                if not encontrados.empty:
                    return encontrados.iloc[0].to_dict()

        # Si no encuentra por apellido, buscar por nombre
        for palabra in palabras:
            if len(palabra) > 3:
                mask = benef_proy['NOMBRES'].str.contains(palabra, case=False, na=False)
                encontrados = benef_proy[mask]
                if not encontrados.empty:
                    return encontrados.iloc[0].to_dict()

        return None

    def _buscar_beneficiario_por_id(self, id_benef: str) -> Optional[dict]:
        """Busca un beneficiario por ID directo"""
        beneficiarios = self.conn.get_sheet_data('Beneficiario')
        mask = beneficiarios['ID_Benef'] == id_benef
        encontrados = beneficiarios[mask]

        if encontrados.empty:
            return None
        return encontrados.iloc[0].to_dict()

    def _get_tipologias_dict(self) -> dict:
        """
        Obtiene diccionario de tipologías {IDU_tipol: descripcion_formateada}

        Formato de descripción:
        - Vivienda: "Vivienda 2D 1P 59.18 m2" (Familia + Dormitorios + Plantas + m2)
        - R. Complementario: "Bodega 14.4 m2" (Tipologia + m2)
        """
        if 'tipologias_dict' in self._cache:
            return self._cache['tipologias_dict']

        tipologias = self.conn.get_sheet_data('Tipologias')

        tipol_dict = {}
        for _, row in tipologias.iterrows():
            id_tip = row.get('IDU_tipol', '')
            if not id_tip:
                continue

            familia = str(row.get('Familia', '')).strip()
            tipologia = str(row.get('tipologia', '')).strip()
            dormitorios = str(row.get('dormitorios', '')).strip()
            plantas = str(row.get('plantas', '')).strip()
            caracterizacion = str(row.get('caracterizacion', '')).strip()

            # Formar descripción según tipo
            if familia.lower() == 'vivienda':
                # Vivienda: "Vivienda 2D 1P 59.18 m2"
                partes = [familia]
                if dormitorios:
                    partes.append(f"{dormitorios}D")
                if plantas:
                    partes.append(f"{plantas}P")
                if caracterizacion:
                    partes.append(caracterizacion)
                descripcion = " ".join(partes)
            else:
                # R. Complementario, Bodega, etc: "Bodega 14.4 m2"
                partes = []
                if tipologia:
                    partes.append(tipologia)
                elif familia:
                    partes.append(familia)
                if caracterizacion:
                    partes.append(caracterizacion)
                descripcion = " ".join(partes)

            tipol_dict[id_tip] = descripcion

        self._cache['tipologias_dict'] = tipol_dict
        return tipol_dict

    def _get_descripcion_tipologia(self, id_tipologia: str) -> str:
        """Obtiene la descripción formateada de una tipología por su ID"""
        if not id_tipologia:
            return ""
        tipol_dict = self._get_tipologias_dict()
        return tipol_dict.get(id_tipologia, id_tipologia)

    def _get_despachos_beneficiario(self, id_benef: str) -> pd.DataFrame:
        """Obtiene despachos de un beneficiario"""
        despachos = self.conn.get_sheet_data('Despacho')
        desp_benef = despachos[despachos['ID_Benef'] == id_benef].copy()

        # Ordenar por fecha
        if 'Fecha' in desp_benef.columns and not desp_benef.empty:
            desp_benef['Fecha'] = pd.to_datetime(desp_benef['Fecha'], errors='coerce')
            desp_benef = desp_benef.sort_values('Fecha')

        return desp_benef

    def _get_pagos_beneficiario(self, id_benef: str) -> pd.DataFrame:
        """Obtiene solicitudes de pago de un beneficiario"""
        solpago = self.conn.get_sheet_data('Solpago')
        pagos_benef = solpago[solpago['ID_Benef'] == id_benef].copy()

        # Ordenar por fecha
        if 'fecha' in pagos_benef.columns and not pagos_benef.empty:
            pagos_benef['fecha'] = pd.to_datetime(pagos_benef['fecha'], errors='coerce')
            pagos_benef = pagos_benef.sort_values('fecha')

        return pagos_benef

    def _get_ejecucion_beneficiario(self, id_benef: str) -> pd.DataFrame:
        """Obtiene registros de ejecución de un beneficiario"""
        ejecucion = self._get_tabla_con_duplicados('Ejecucion')
        # Columna es 'ID_benef' (minúscula)
        ejec_benef = ejecucion[ejecucion['ID_benef'] == id_benef].copy()
        return ejec_benef

    def _get_solicitudes_despacho_beneficiario(self, id_benef: str) -> pd.DataFrame:
        """
        Obtiene solicitudes de despacho de un beneficiario.
        Tabla: soldepacho
        """
        # Leer con manejo especial por caracteres
        worksheet = self.conn.spreadsheet.worksheet('soldepacho')
        all_values = worksheet.get_all_values()
        if not all_values:
            return pd.DataFrame()

        headers = all_values[0]
        soldesp = pd.DataFrame(all_values[1:], columns=headers)

        # Filtrar por beneficiario
        sol_benef = soldesp[soldesp['ID_Benef'] == id_benef].copy()

        # Convertir fecha programada
        if 'Fecha' in sol_benef.columns and not sol_benef.empty:
            sol_benef['Fecha'] = pd.to_datetime(sol_benef['Fecha'], errors='coerce')
            sol_benef = sol_benef.sort_values('Fecha')

        return sol_benef

    def _get_maestros_dict(self) -> dict:
        """Obtiene diccionario de maestros {id: nombre_completo}"""
        if 'maestros_dict' in self._cache:
            return self._cache['maestros_dict']

        maestros = self._get_tabla_con_duplicados('Maestros')

        maestros_dict = {}
        for _, row in maestros.iterrows():
            id_m = row.get('IDU_maestros', '')
            nombre = f"{row.get('Nombres', '')} {row.get('Apellidos', '')}".strip()
            if id_m:
                maestros_dict[id_m] = nombre

        self._cache['maestros_dict'] = maestros_dict
        return maestros_dict

    def generar_resumen_beneficiario(
        self,
        nombre_beneficiario: str,
        nombre_proyecto: str,
        id_benef: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Genera el reporte RESUMEN_BENEFICIARIO.

        Args:
            nombre_beneficiario: Nombre o apellido del beneficiario
            nombre_proyecto: Nombre del proyecto
            id_benef: ID directo del beneficiario (opcional, si se conoce)

        Returns:
            dict con todas las secciones del reporte
        """
        resultado = {
            "tipo_reporte": "RESUMEN_BENEFICIARIO",
            "fecha_generacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "parametros": {
                "nombre_beneficiario": nombre_beneficiario,
                "nombre_proyecto": nombre_proyecto
            },
            "encontrado": False,
            "error": None
        }

        # 1. Buscar proyecto
        proyecto = self._buscar_proyecto(nombre_proyecto)
        if not proyecto:
            resultado["error"] = f"Proyecto '{nombre_proyecto}' no encontrado"
            return resultado

        resultado["proyecto"] = proyecto
        id_proy = proyecto['ID_proy']

        # 2. Buscar beneficiario
        if id_benef:
            beneficiario = self._buscar_beneficiario_por_id(id_benef)
        else:
            beneficiario = self._buscar_beneficiario(nombre_beneficiario, id_proy)

        if not beneficiario:
            resultado["error"] = f"Beneficiario '{nombre_beneficiario}' no encontrado en proyecto {id_proy}"
            return resultado

        resultado["encontrado"] = True
        id_benef = beneficiario['ID_Benef']

        # 3. Sección IDENTIFICACIÓN (sin ID interno)
        resultado["identificacion"] = {
            "Nombre": f"{beneficiario.get('NOMBRES', '')} {beneficiario.get('APELLIDOS', '')}".strip(),
            "RUT": f"{beneficiario.get('RUT', '')}-{beneficiario.get('DV', '')}",
            "Estado_civil": beneficiario.get('ESTADO_CIVIL', ''),
            "Telefono": beneficiario.get('TELEFONO', ''),
            "Email": beneficiario.get('EMAIL', ''),
            "WhatsApp": beneficiario.get('WHATSAPP', '')
        }

        # 4. Sección PROYECTO (del beneficiario)
        resultado["proyecto_beneficiario"] = {
            "ID_Proy": beneficiario.get('ID_Proy', ''),
            "Estado": beneficiario.get('Estado', ''),
            "Habil_para_construir": beneficiario.get('Habil para construir', ''),
            "Fecha_habil": beneficiario.get('fecha_habil_para_const', '')
        }

        # 5. Sección TIPOLOGÍAS (con descripción en vez de ID)
        id_tip_viv = beneficiario.get('Tipologia Vivienda', '')
        id_tip_rc = beneficiario.get('Tipologia RC', '')
        resultado["tipologias"] = {
            "Vivienda": self._get_descripcion_tipologia(id_tip_viv),
            "Recinto_Complementario": self._get_descripcion_tipologia(id_tip_rc)
        }

        # 6. Sección UBICACIÓN
        resultado["ubicacion"] = {
            "Direccion_RSH": beneficiario.get('DIRECCION_RSH', ''),
            "Direccion_Postal": beneficiario.get('DIRECCION_POST', ''),
            "Comuna": beneficiario.get('COMUNA', '')
        }

        # 7. Sección APROBACIONES
        resultado["aprobaciones"] = {
            "Legal": beneficiario.get('Aprob_legal', ''),
            "Social": beneficiario.get('Aprob_social', ''),
            "Tecnico": beneficiario.get('Aprob_tecnico', '')
        }

        # 8. Sección TERRENO/LEGAL
        resultado["terreno_legal"] = {
            "N_Rol": beneficiario.get('N_ROL', ''),
            "CBR": beneficiario.get('CBR', ''),
            "Decreto": beneficiario.get('DECRETO', ''),
            "Permiso_edif": beneficiario.get('Permiso_edif', ''),
            "Num_permiso": beneficiario.get('Num_permiso', '')
        }

        # 9. Sección DESPACHOS
        despachos = self._get_despachos_beneficiario(id_benef)
        despachos_lista = []
        for _, d in despachos.iterrows():
            fecha = d.get('Fecha', '')
            if pd.notna(fecha) and hasattr(fecha, 'strftime'):
                fecha = fecha.strftime('%d/%m/%Y')
            despachos_lista.append({
                "Fecha": fecha,
                "Guia": d.get('Guia', ''),
                "Etapas": d.get('Tipo_despacho', ''),
                "Camion": d.get('Camion', ''),
                "Chofer": d.get('Chofer', '')
            })

        resultado["despachos"] = {
            "total": len(despachos),
            "detalle": despachos_lista
        }

        # 9.1 Sección SOLICITUDES DE DESPACHO (pendientes)
        solicitudes_desp = self._get_solicitudes_despacho_beneficiario(id_benef)
        hoy = datetime.now()

        # Obtener guías ya despachadas para comparar
        guias_despachadas = set()
        fechas_despachadas = set()
        for d in despachos_lista:
            if d.get('Fecha'):
                fechas_despachadas.add(d['Fecha'])

        solicitudes_lista = []
        solicitudes_pendientes = []
        for _, s in solicitudes_desp.iterrows():
            fecha_prog = s.get('Fecha', '')
            fecha_str = ''
            es_futuro = False

            if pd.notna(fecha_prog) and hasattr(fecha_prog, 'strftime'):
                fecha_str = fecha_prog.strftime('%d/%m/%Y')
                es_futuro = fecha_prog > hoy

            tipo_despacho = s.get('Tipo_despacho', '')
            es_adicional = 'adicional' in tipo_despacho.lower()

            sol_item = {
                "Fecha_creacion": s.get('fecha_creacion', ''),
                "Fecha_programada": fecha_str,
                "Tipo_despacho": tipo_despacho,
                "Observacion": s.get('observacion', ''),
                "Es_futuro": es_futuro,
                "Es_adicional": es_adicional
            }

            # Campos adicionales solo para tipo Adicional
            if es_adicional:
                sol_item["Detalle_material"] = s.get('desc_adicional', '')
                aprueba = s.get('aprueba_adicional', '')
                if aprueba.lower() == 'true':
                    sol_item["Estado_aprobacion"] = "Aprobado"
                elif aprueba.lower() == 'false':
                    sol_item["Estado_aprobacion"] = "Rechazado"
                else:
                    sol_item["Estado_aprobacion"] = "Pendiente"

            solicitudes_lista.append(sol_item)

            # Si la fecha es futura, es pendiente
            if es_futuro:
                solicitudes_pendientes.append(sol_item)

        resultado["solicitudes_despacho"] = {
            "total": len(solicitudes_lista),
            "pendientes": len(solicitudes_pendientes),
            "detalle_pendientes": solicitudes_pendientes,
            "detalle_todas": solicitudes_lista
        }

        # 10. Sección SOLICITUDES DE PAGO (mejorada)
        pagos = self._get_pagos_beneficiario(id_benef)
        maestros_dict = self._get_maestros_dict()

        pagos_lista = []
        total_aprobado = 0
        total_pendiente = 0
        total_rechazado = 0

        # Para resumen por maestro
        resumen_maestros = {}

        for _, p in pagos.iterrows():
            fecha = p.get('fecha', '')
            if pd.notna(fecha) and hasattr(fecha, 'strftime'):
                fecha = fecha.strftime('%d/%m/%Y')

            monto_str = p.get('monto', '0')
            try:
                # Limpiar formato de monto ($1.234,56 -> 1234.56)
                monto_clean = str(monto_str).replace('$', '').replace('.', '').replace(',', '.')
                monto_num = float(monto_clean) if monto_clean else 0
            except:
                monto_num = 0

            estado = str(p.get('Estado', '')).strip()
            estado_lower = estado.lower()

            if 'aprobado' in estado_lower:
                total_aprobado += monto_num
            elif 'rechazado' in estado_lower:
                total_rechazado += monto_num
            else:
                total_pendiente += monto_num

            id_maestro = p.get('maestro', '')
            nombre_maestro = maestros_dict.get(id_maestro, id_maestro)

            # Acumular para resumen por maestro
            if id_maestro not in resumen_maestros:
                resumen_maestros[id_maestro] = {
                    "Nombre": nombre_maestro,
                    "Total": 0,
                    "Aprobado": 0,
                    "Pendiente": 0,
                    "Cantidad": 0
                }
            resumen_maestros[id_maestro]["Total"] += monto_num
            resumen_maestros[id_maestro]["Cantidad"] += 1
            if 'aprobado' in estado_lower:
                resumen_maestros[id_maestro]["Aprobado"] += monto_num
            else:
                resumen_maestros[id_maestro]["Pendiente"] += monto_num

            pagos_lista.append({
                "Fecha": fecha,
                "Familia": p.get('Familia_pago', ''),
                "Tipo": p.get('Tipo_pago', ''),
                "Monto": monto_str,
                "Monto_num": monto_num,
                "Estado": estado,
                "Observacion": p.get('Observacion', ''),
                "Maestro_ID": id_maestro,
                "Maestro_Nombre": nombre_maestro
            })

        # Convertir resumen_maestros a lista ordenada por total
        resumen_maestros_lista = []
        for id_m, datos in resumen_maestros.items():
            resumen_maestros_lista.append({
                "ID": id_m,
                "Nombre": datos["Nombre"],
                "Cantidad_pagos": datos["Cantidad"],
                "Total": datos["Total"],
                "Aprobado": datos["Aprobado"],
                "Pendiente": datos["Pendiente"]
            })
        resumen_maestros_lista.sort(key=lambda x: x["Total"], reverse=True)

        resultado["pagos"] = {
            "total": len(pagos),
            "total_aprobado": total_aprobado,
            "total_pendiente": total_pendiente,
            "total_rechazado": total_rechazado,
            "total_general": total_aprobado + total_pendiente + total_rechazado,
            "detalle": pagos_lista,
            "resumen_maestros": resumen_maestros_lista
        }

        # 11. Sección EJECUCIÓN
        ejecucion = self._get_ejecucion_beneficiario(id_benef)
        resultado["ejecucion"] = {
            "total_registros": len(ejecucion),
            "fecha_primer_registro": ejecucion['Fecha_creacion'].min() if not ejecucion.empty else None,
            "fecha_ultimo_registro": ejecucion['Fecha_creacion'].max() if not ejecucion.empty else None
        }

        return resultado

    def formatear_resumen_beneficiario(self, reporte: dict) -> str:
        """
        Formatea el reporte RESUMEN_BENEFICIARIO como texto legible.
        """
        if not reporte.get("encontrado"):
            return f"ERROR: {reporte.get('error', 'Desconocido')}"

        lineas = []
        lineas.append("=" * 60)
        lineas.append(f"RESUMEN DE BENEFICIARIO")
        lineas.append(f"Generado: {reporte['fecha_generacion']}")
        lineas.append("=" * 60)

        # Identificación
        id_data = reporte.get("identificacion", {})
        lineas.append("\n--- IDENTIFICACION ---")
        lineas.append(f"Nombre: {id_data.get('Nombre', '')}")
        lineas.append(f"RUT: {id_data.get('RUT', '')}")
        lineas.append(f"Estado civil: {id_data.get('Estado_civil', '')}")
        lineas.append(f"Telefono: {id_data.get('Telefono', '')}")
        lineas.append(f"Email: {id_data.get('Email', '')}")

        # Proyecto
        proy_data = reporte.get("proyecto_beneficiario", {})
        lineas.append("\n--- PROYECTO ---")
        lineas.append(f"ID_Proy: {proy_data.get('ID_Proy', '')}")
        lineas.append(f"Estado: {proy_data.get('Estado', '')}")
        lineas.append(f"Habil para construir: {proy_data.get('Habil_para_construir', '')}")
        lineas.append(f"Fecha habil: {proy_data.get('Fecha_habil', '')}")

        # Tipologías
        tip_data = reporte.get("tipologias", {})
        lineas.append("\n--- TIPOLOGIAS ---")
        lineas.append(f"Vivienda: {tip_data.get('Vivienda', '')}")
        lineas.append(f"Recinto Complementario: {tip_data.get('Recinto_Complementario', '')}")

        # Ubicación
        ubi_data = reporte.get("ubicacion", {})
        lineas.append("\n--- UBICACION ---")
        lineas.append(f"Direccion RSH: {ubi_data.get('Direccion_RSH', '')}")
        lineas.append(f"Direccion Postal: {ubi_data.get('Direccion_Postal', '')}")
        lineas.append(f"Comuna: {ubi_data.get('Comuna', '')}")

        # Aprobaciones
        apr_data = reporte.get("aprobaciones", {})
        lineas.append("\n--- APROBACIONES ---")
        lineas.append(f"Legal: {apr_data.get('Legal', '')} | Social: {apr_data.get('Social', '')} | Tecnico: {apr_data.get('Tecnico', '')}")

        # Terreno/Legal
        ter_data = reporte.get("terreno_legal", {})
        lineas.append("\n--- TERRENO/LEGAL ---")
        lineas.append(f"N Rol: {ter_data.get('N_Rol', '')}")
        lineas.append(f"CBR: {ter_data.get('CBR', '')}")
        lineas.append(f"Decreto: {ter_data.get('Decreto', '')}")

        # Despachos
        desp_data = reporte.get("despachos", {})
        lineas.append("\n--- DESPACHOS ---")
        lineas.append(f"Total: {desp_data.get('total', 0)}")
        for d in desp_data.get("detalle", []):
            lineas.append(f"  {d['Fecha']} | Guia: {d['Guia']}")
            lineas.append(f"    Etapas: {d['Etapas']}")

        # Pagos
        pag_data = reporte.get("pagos", {})
        lineas.append("\n--- SOLICITUDES DE PAGO ---")
        lineas.append(f"Total: {pag_data.get('total', 0)}")
        for p in pag_data.get("detalle", []):
            lineas.append(f"  {p['Fecha']} | {p['Estado']} | ${p['Monto']}")
            lineas.append(f"    Tipo: {p['Tipo'][:50]}...")
            lineas.append(f"    Maestro: {p['Maestro_Nombre']}")

        # Ejecución
        eje_data = reporte.get("ejecucion", {})
        lineas.append("\n--- REGISTROS DE EJECUCION ---")
        lineas.append(f"Total registros: {eje_data.get('total_registros', 0)}")

        lineas.append("\n" + "=" * 60)

        return "\n".join(lineas)

    def generar_pdf_resumen_beneficiario(
        self,
        reporte: dict,
        ruta_salida: Optional[str] = None
    ) -> str:
        """
        Genera un PDF del reporte RESUMEN_BENEFICIARIO.

        Args:
            reporte: Diccionario con el reporte generado
            ruta_salida: Ruta donde guardar el PDF (opcional)

        Returns:
            str: Ruta del archivo PDF generado
        """
        if not PDF_DISPONIBLE:
            raise ImportError("La biblioteca fpdf2 no está instalada. Ejecute: pip install fpdf2")

        if not reporte.get("encontrado"):
            raise ValueError(f"Reporte no válido: {reporte.get('error', 'Desconocido')}")

        # Crear PDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Fuentes
        pdf.set_font("Helvetica", "B", 16)

        # Título
        proy = reporte.get("proyecto", {})
        ident = reporte.get("identificacion", {})

        pdf.cell(0, 10, "RESUMEN DE BENEFICIARIO", ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Generado: {reporte['fecha_generacion']}", ln=True, align="C")
        pdf.ln(5)

        # Proyecto
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, f"{proy.get('NOMBRE_PROYECTO', '')} ({proy.get('ID_proy', '')})", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Comuna: {proy.get('COMUNA', '')} | Periodo: {proy.get('PERIODO', '')}", ln=True)
        pdf.ln(5)

        # === IDENTIFICACIÓN ===
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(0, 7, "IDENTIFICACION", ln=True, fill=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Nombre: {ident.get('Nombre', '')}", ln=True)
        pdf.cell(0, 6, f"RUT: {ident.get('RUT', '')}", ln=True)
        pdf.ln(3)

        # === TIPOLOGÍAS ===
        tip = reporte.get("tipologias", {})
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "TIPOLOGIAS", ln=True, fill=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Vivienda: {tip.get('Vivienda', '')}", ln=True)
        pdf.cell(0, 6, f"Recinto Complementario: {tip.get('Recinto_Complementario', '')}", ln=True)
        pdf.ln(3)

        # === UBICACIÓN Y APROBACIONES ===
        ubi = reporte.get("ubicacion", {})
        apr = reporte.get("aprobaciones", {})
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "UBICACION Y ESTADO", ln=True, fill=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Direccion: {ubi.get('Direccion_RSH', '')} | Comuna: {ubi.get('Comuna', '')}", ln=True)
        legal = "Si" if apr.get('Legal') == 'TRUE' else "No"
        social = "Si" if apr.get('Social') == 'TRUE' else "No"
        tecnico = "Si" if apr.get('Tecnico') == 'TRUE' else "No"
        pdf.cell(0, 6, f"Aprobaciones - Legal: {legal} | Social: {social} | Tecnico: {tecnico}", ln=True)
        pdf.ln(3)

        # === DESPACHOS ===
        desp = reporte.get("despachos", {})
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"DESPACHOS REALIZADOS ({desp.get('total', 0)} total)", ln=True, fill=True)
        pdf.set_font("Helvetica", "", 9)

        # Tabla de despachos
        col_widths = [25, 30, 135]
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths[0], 6, "Fecha", border=1)
        pdf.cell(col_widths[1], 6, "Guia", border=1)
        pdf.cell(col_widths[2], 6, "Etapas", border=1, ln=True)

        pdf.set_font("Helvetica", "", 8)
        for d in desp.get("detalle", []):
            pdf.cell(col_widths[0], 5, str(d.get('Fecha', ''))[:10], border=1)
            pdf.cell(col_widths[1], 5, str(d.get('Guia', ''))[:15], border=1)
            pdf.cell(col_widths[2], 5, str(d.get('Etapas', ''))[:75], border=1, ln=True)
        pdf.ln(3)

        # === SOLICITUDES DE DESPACHO PENDIENTES ===
        sol_desp = reporte.get("solicitudes_despacho", {})
        if sol_desp.get("pendientes", 0) > 0:
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 7, f"SOLICITUDES DE DESPACHO PENDIENTES ({sol_desp.get('pendientes', 0)})", ln=True, fill=True)
            pdf.set_font("Helvetica", "", 9)
            for s in sol_desp.get("detalle_pendientes", []):
                pdf.cell(0, 5, f"  {s.get('Fecha_programada', '')} -> {s.get('Tipo_despacho', '')[:70]}", ln=True)
                if s.get("Es_adicional"):
                    pdf.set_font("Helvetica", "I", 8)
                    pdf.cell(0, 4, f"      Material: {s.get('Detalle_material', '')[:60]} | Estado: {s.get('Estado_aprobacion', '')}", ln=True)
                    pdf.set_font("Helvetica", "", 9)
            pdf.ln(3)

        # === SOLICITUDES DE PAGO ===
        pag = reporte.get("pagos", {})
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"SOLICITUDES DE PAGO ({pag.get('total', 0)} total)", ln=True, fill=True)

        # Tabla de pagos
        col_widths_pag = [22, 35, 28, 20, 50, 35]
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(col_widths_pag[0], 5, "Fecha", border=1)
        pdf.cell(col_widths_pag[1], 5, "Familia", border=1)
        pdf.cell(col_widths_pag[2], 5, "Monto", border=1)
        pdf.cell(col_widths_pag[3], 5, "Estado", border=1)
        pdf.cell(col_widths_pag[4], 5, "Tipo", border=1)
        pdf.cell(col_widths_pag[5], 5, "Maestro", border=1, ln=True)

        pdf.set_font("Helvetica", "", 7)
        for p in pag.get("detalle", []):
            estado_short = "OK" if "aprobado" in str(p.get('Estado', '')).lower() else p.get('Estado', '')[:8]
            pdf.cell(col_widths_pag[0], 4, str(p.get('Fecha', ''))[:10], border=1)
            pdf.cell(col_widths_pag[1], 4, str(p.get('Familia', ''))[:18], border=1)
            pdf.cell(col_widths_pag[2], 4, str(p.get('Monto', ''))[:14], border=1)
            pdf.cell(col_widths_pag[3], 4, estado_short, border=1)
            pdf.cell(col_widths_pag[4], 4, str(p.get('Tipo', ''))[:28], border=1)
            pdf.cell(col_widths_pag[5], 4, str(p.get('Maestro_Nombre', ''))[:18], border=1, ln=True)
        pdf.ln(3)

        # === TOTALES ===
        pdf.set_font("Helvetica", "B", 10)
        total_gen = pag.get('total_general', 0)
        total_apr = pag.get('total_aprobado', 0)
        total_pen = pag.get('total_pendiente', 0)
        pdf.cell(0, 6, f"TOTAL GENERAL: ${total_gen:,.0f}".replace(",", "."), ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, f"  Aprobado: ${total_apr:,.0f}  |  Pendiente: ${total_pen:,.0f}".replace(",", "."), ln=True)
        pdf.ln(3)

        # === RESUMEN POR MAESTRO ===
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "RESUMEN POR MAESTRO", ln=True, fill=True)

        col_widths_m = [80, 25, 40, 45]
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_widths_m[0], 5, "Maestro", border=1)
        pdf.cell(col_widths_m[1], 5, "Pagos", border=1)
        pdf.cell(col_widths_m[2], 5, "Total", border=1)
        pdf.cell(col_widths_m[3], 5, "Aprobado", border=1, ln=True)

        pdf.set_font("Helvetica", "", 8)
        for m in pag.get("resumen_maestros", []):
            pdf.cell(col_widths_m[0], 5, str(m.get('Nombre', ''))[:40], border=1)
            pdf.cell(col_widths_m[1], 5, str(m.get('Cantidad_pagos', '')), border=1, align="C")
            pdf.cell(col_widths_m[2], 5, f"${m.get('Total', 0):,.0f}".replace(",", "."), border=1, align="R")
            pdf.cell(col_widths_m[3], 5, f"${m.get('Aprobado', 0):,.0f}".replace(",", "."), border=1, align="R", ln=True)

        # Generar nombre de archivo si no se proporciona
        if not ruta_salida:
            nombre_benef = ident.get('Nombre', 'beneficiario').replace(' ', '_')[:30]
            fecha_gen = datetime.now().strftime("%Y%m%d_%H%M")
            ruta_salida = f"Resumen_{nombre_benef}_{fecha_gen}.pdf"

        # Guardar PDF
        pdf.output(ruta_salida)

        return ruta_salida

    # ========================================================================
    # REPORTE: RESUMEN DE PAGO M.O DE GRUPOS
    # ========================================================================

    def generar_resumen_pago_mo_grupo(
        self,
        nombre_proyecto: str,
        ruta_salida: Optional[str] = None
    ) -> str:
        """
        Genera un Excel con el resumen de pagos de mano de obra de un proyecto/grupo.

        Args:
            nombre_proyecto: Nombre del proyecto (búsqueda parcial)
            ruta_salida: Ruta donde guardar el Excel (opcional)

        Returns:
            str: Ruta del archivo Excel generado
        """
        import os
        import re

        # Buscar proyecto
        proyecto = self._buscar_proyecto(nombre_proyecto)
        if not proyecto:
            raise ValueError(f"Proyecto '{nombre_proyecto}' no encontrado")

        id_proy = proyecto['ID_proy']
        nombre_proy = proyecto['NOMBRE_PROYECTO']

        # Obtener datos
        beneficiarios = self.conn.get_sheet_data('Beneficiario')
        solpago = self.conn.get_sheet_data('Solpago')

        # Filtrar por proyecto
        benef_proy = beneficiarios[beneficiarios['ID_Proy'] == id_proy]
        pagos_proy = solpago[solpago['ID_proy'] == id_proy]

        maestros_dict = self._get_maestros_dict()

        # === HOJA 1: RESUMEN PROYECTO ===
        resumen_proy_data = {
            'Campo': ['Proyecto', 'ID', 'Comuna', 'Periodo', 'Beneficiarios', 'Total Pagos', 'Fecha Reporte'],
            'Valor': [
                nombre_proy,
                id_proy,
                proyecto.get('COMUNA', ''),
                proyecto.get('PERIODO', ''),
                len(benef_proy),
                len(pagos_proy),
                datetime.now().strftime('%d/%m/%Y %H:%M')
            ]
        }
        df_resumen_proy = pd.DataFrame(resumen_proy_data)

        # === HOJA 2: RESUMEN POR BENEFICIARIO ===
        resumen_benef = []

        for _, b in benef_proy.iterrows():
            id_benef = b['ID_Benef']
            nombre = f"{b.get('NOMBRES', '')} {b.get('APELLIDOS', '')}".strip()

            # Pagos de este beneficiario
            pagos_b = pagos_proy[pagos_proy['ID_Benef'] == id_benef]

            total = 0
            aprobado = 0
            pendiente = 0

            for _, p in pagos_b.iterrows():
                monto_str = str(p.get('monto', '0'))
                try:
                    monto = float(monto_str.replace('$', '').replace('.', '').replace(',', '.'))
                except:
                    monto = 0
                total += monto
                if 'aprobado' in str(p.get('Estado', '')).lower():
                    aprobado += monto
                else:
                    pendiente += monto

            # Tipología
            tip_id = b.get('Tipologia Vivienda', '')
            tip_desc = self._get_descripcion_tipologia(tip_id) if tip_id else ''

            resumen_benef.append({
                'Beneficiario': nombre,
                'RUT': f"{b.get('RUT', '')}-{b.get('DV', '')}",
                'Tipologia': tip_desc,
                'Comuna': b.get('COMUNA', ''),
                'Cant_Pagos': len(pagos_b),
                'Total': total,
                'Aprobado': aprobado,
                'Pendiente': pendiente
            })

        df_resumen_benef = pd.DataFrame(resumen_benef)

        # Agregar fila de totales
        if not df_resumen_benef.empty:
            totales_benef = {
                'Beneficiario': 'TOTAL GRUPO',
                'RUT': '',
                'Tipologia': '',
                'Comuna': '',
                'Cant_Pagos': df_resumen_benef['Cant_Pagos'].sum(),
                'Total': df_resumen_benef['Total'].sum(),
                'Aprobado': df_resumen_benef['Aprobado'].sum(),
                'Pendiente': df_resumen_benef['Pendiente'].sum()
            }
            df_resumen_benef = pd.concat([df_resumen_benef, pd.DataFrame([totales_benef])], ignore_index=True)

        # === HOJA 3: DETALLE DE PAGOS ===
        detalle_pagos = []

        for _, p in pagos_proy.iterrows():
            id_benef = p['ID_Benef']
            # Buscar nombre beneficiario
            benef_row = benef_proy[benef_proy['ID_Benef'] == id_benef]
            if not benef_row.empty:
                nombre_benef = f"{benef_row.iloc[0]['NOMBRES']} {benef_row.iloc[0]['APELLIDOS']}".strip()
            else:
                nombre_benef = str(id_benef)

            monto_str = str(p.get('monto', '0'))
            try:
                monto = float(monto_str.replace('$', '').replace('.', '').replace(',', '.'))
            except:
                monto = 0

            id_maestro = p.get('maestro', '')
            nombre_maestro = maestros_dict.get(id_maestro, id_maestro)

            detalle_pagos.append({
                'Fecha': p.get('fecha', ''),
                'Beneficiario': nombre_benef,
                'Familia': p.get('Familia_pago', ''),
                'Tipo_Pago': p.get('Tipo_pago', ''),
                'Monto': monto,
                'Estado': p.get('Estado', ''),
                'Maestro': nombre_maestro,
                'Observacion': p.get('Observacion', '')
            })

        df_detalle = pd.DataFrame(detalle_pagos)

        # === HOJA 4: RESUMEN POR MAESTRO ===
        resumen_maestro = {}

        for _, p in pagos_proy.iterrows():
            id_maestro = p.get('maestro', '')
            nombre_maestro = maestros_dict.get(id_maestro, id_maestro) or 'Sin asignar'

            monto_str = str(p.get('monto', '0'))
            try:
                monto = float(monto_str.replace('$', '').replace('.', '').replace(',', '.'))
            except:
                monto = 0

            if nombre_maestro not in resumen_maestro:
                resumen_maestro[nombre_maestro] = {'Cant_Pagos': 0, 'Total': 0, 'Aprobado': 0, 'Pendiente': 0}

            resumen_maestro[nombre_maestro]['Cant_Pagos'] += 1
            resumen_maestro[nombre_maestro]['Total'] += monto
            if 'aprobado' in str(p.get('Estado', '')).lower():
                resumen_maestro[nombre_maestro]['Aprobado'] += monto
            else:
                resumen_maestro[nombre_maestro]['Pendiente'] += monto

        df_maestros = pd.DataFrame([
            {'Maestro': k, **v} for k, v in resumen_maestro.items()
        ]).sort_values('Total', ascending=False) if resumen_maestro else pd.DataFrame()

        # Agregar total
        if not df_maestros.empty:
            total_maestros = {
                'Maestro': 'TOTAL',
                'Cant_Pagos': df_maestros['Cant_Pagos'].sum(),
                'Total': df_maestros['Total'].sum(),
                'Aprobado': df_maestros['Aprobado'].sum(),
                'Pendiente': df_maestros['Pendiente'].sum()
            }
            df_maestros = pd.concat([df_maestros, pd.DataFrame([total_maestros])], ignore_index=True)

        # === GUARDAR EXCEL ===
        if not ruta_salida:
            nombre_limpio = re.sub(r'[^a-zA-Z0-9_]', '_', nombre_proy)[:30]
            fecha_gen = datetime.now().strftime("%Y%m%d")
            ruta_salida = f"Resumen_Pagos_{nombre_limpio}_{fecha_gen}.xlsx"

        with pd.ExcelWriter(ruta_salida, engine='openpyxl') as writer:
            df_resumen_proy.to_excel(writer, sheet_name='Resumen Proyecto', index=False)
            df_resumen_benef.to_excel(writer, sheet_name='Por Beneficiario', index=False)
            df_detalle.to_excel(writer, sheet_name='Detalle Pagos', index=False)
            df_maestros.to_excel(writer, sheet_name='Por Maestro', index=False)

        return ruta_salida


    # ========================================================================
    # REPORTE: ANÁLISIS COMPARATIVO DE M.O (Base vs Real)
    # ========================================================================

    def generar_analisis_comparativo_mo(
        self,
        nombre_proyecto: str,
        ruta_salida: Optional[str] = None
    ) -> str:
        """
        Genera un PDF con el análisis comparativo de M.O Base vs Pagos Reales.

        Args:
            nombre_proyecto: Nombre del proyecto (búsqueda parcial)
            ruta_salida: Ruta donde guardar el PDF (opcional)

        Returns:
            str: Ruta del archivo PDF generado
        """
        import os
        import re

        if not PDF_DISPONIBLE:
            raise ImportError("La biblioteca fpdf2 no está instalada. Ejecute: pip install fpdf2")

        # Buscar proyecto
        proyecto = self._buscar_proyecto(nombre_proyecto)
        if not proyecto:
            raise ValueError(f"Proyecto '{nombre_proyecto}' no encontrado")

        id_proy = proyecto['ID_proy']
        nombre_proy = proyecto['NOMBRE_PROYECTO']
        comuna_proy = proyecto.get('COMUNA', '')
        periodo_proy = proyecto.get('PERIODO', '')

        # === OBTENER DATOS ===
        # Tipologías del proyecto
        tipologias = self.conn.get_sheet_data('Tipologias')
        tip_proy = tipologias[tipologias['ID_proy'] == id_proy]

        # Crear diccionario de tipologías e identificar IDs de RC
        tipologias_dict = {}
        rc_tipologia_ids = set()

        for _, row in tip_proy.iterrows():
            if row['Familia'] == 'Vivienda':
                desc = f"Vivienda {row['dormitorios']}D {row['plantas']}P {row['caracterizacion']}"
                tipo = 'Vivienda'
            else:
                desc = f"R.C. {row['caracterizacion']}"
                tipo = 'R.Comp'
                rc_tipologia_ids.add(row['IDU_tipol'])
            tipologias_dict[row['IDU_tipol']] = {'descripcion': desc, 'tipo': tipo}

        # Beneficiarios del proyecto
        beneficiarios_df = self.conn.get_sheet_data('Beneficiario')
        ben_proy = beneficiarios_df[beneficiarios_df['ID_Proy'] == id_proy]

        beneficiarios = []
        for _, row in ben_proy.iterrows():
            apellido = row['APELLIDOS'].split()[0] if row['APELLIDOS'] else ''
            inicial = row['NOMBRES'].split()[0][0] if row['NOMBRES'] else ''
            nombre_corto = f"{apellido} {inicial}."

            beneficiarios.append({
                'id': row['ID_Benef'],
                'nombre': nombre_corto,
                'tipologia_viv': row.get('Tipologia Vivienda', ''),
                'tipologia_rc': row.get('Tipologia RC', '')
            })

        # Contar viviendas y RC por tipología
        viviendas_por_tip = {}
        rc_por_tip = {}
        for ben in beneficiarios:
            if ben['tipologia_viv']:
                viviendas_por_tip[ben['tipologia_viv']] = viviendas_por_tip.get(ben['tipologia_viv'], 0) + 1
            if ben['tipologia_rc']:
                rc_por_tip[ben['tipologia_rc']] = rc_por_tip.get(ben['tipologia_rc'], 0) + 1

        total_viviendas = sum(viviendas_por_tip.values())
        total_rc = sum(rc_por_tip.values())

        # Tabla M.O Base
        tabla_pago = self.conn.get_sheet_data('Tabla_pago')
        mo_base = tabla_pago[tabla_pago['ID_proy'] == id_proy]

        # Pagos Reales
        solpago = self.conn.get_sheet_data('Solpago')
        pagos_proy = solpago[solpago['ID_proy'] == id_proy]

        # === PROCESAR M.O BASE ===
        def parse_monto(m):
            if not m or m == '-':
                return 0
            try:
                return float(m)
            except:
                return 0

        mo_base = mo_base.copy()
        mo_base['monto_num'] = mo_base['monto'].apply(parse_monto)

        base_por_tipologia = {}
        for tipol_id, info in tipologias_dict.items():
            subset = mo_base[mo_base['IDU_Tipol'] == tipol_id]
            total = subset['monto_num'].sum()

            base_familia = {}
            for fam, monto in subset.groupby('familia_pago')['monto_num'].sum().items():
                if info['tipo'] == 'R.Comp':
                    fam_key = f"RC {fam}" if not str(fam).startswith('RC ') else fam
                else:
                    fam_key = fam
                base_familia[fam_key] = monto

            base_por_tipologia[tipol_id] = {
                'descripcion': info['descripcion'],
                'tipo': info['tipo'],
                'total_base': total,
                'base_por_familia': base_familia
            }

        # === PROCESAR PAGOS REALES ===
        def parse_monto_real(m):
            if not m:
                return 0
            try:
                m = str(m).replace('$', '').replace('.', '').replace(',', '.')
                return float(m)
            except:
                return 0

        pagos_proy = pagos_proy.copy()
        pagos_proy['monto_num'] = pagos_proy['monto'].apply(parse_monto_real)

        # Filtrar solo aprobados
        pagos_aprobados = pagos_proy[pagos_proy['Estado'].str.lower().str.contains('aprobad', na=False)].copy()
        pagos_aprobados['es_rc'] = pagos_aprobados['tipologia'].isin(rc_tipologia_ids)

        # Pagos por beneficiario y familia
        pagos_por_benef_familia = {}
        for ben in beneficiarios:
            ben_pagos = pagos_aprobados[pagos_aprobados['ID_Benef'] == ben['id']]
            pagos_familia = {}
            for _, pago in ben_pagos.iterrows():
                fam = pago['Familia_pago']
                monto = pago['monto_num']
                if pago['es_rc']:
                    fam_key = f"RC {fam}" if not str(fam).startswith('RC ') else fam
                else:
                    fam_key = fam
                pagos_familia[fam_key] = pagos_familia.get(fam_key, 0) + monto

            pagos_por_benef_familia[ben['id']] = {
                'nombre': ben['nombre'],
                'tipologia_viv': ben['tipologia_viv'],
                'tipologia_rc': ben['tipologia_rc'],
                'pagos': pagos_familia,
                'total': ben_pagos['monto_num'].sum()
            }

        # Total por familia
        total_por_familia = {}
        for ben_id, data in pagos_por_benef_familia.items():
            for fam, monto in data['pagos'].items():
                total_por_familia[fam] = total_por_familia.get(fam, 0) + monto

        # === CALCULAR BASE ESPERADA Y DESVIACIÓN ===
        base_esperada_familia = {}
        for tipol_id, data in base_por_tipologia.items():
            if data['tipo'] == 'Vivienda':
                cant_ben = viviendas_por_tip.get(tipol_id, 0)
            else:
                cant_ben = rc_por_tip.get(tipol_id, 0)

            for familia, monto in data['base_por_familia'].items():
                if familia not in base_esperada_familia:
                    base_esperada_familia[familia] = 0
                base_esperada_familia[familia] += monto * cant_ben

        # Desviación por familia
        desviacion_familia = {}
        todas_familias = set(list(base_esperada_familia.keys()) + list(total_por_familia.keys()))
        for familia in todas_familias:
            base = base_esperada_familia.get(familia, 0)
            real = total_por_familia.get(familia, 0)
            desv = real - base
            desv_pct = (desv / base * 100) if base > 0 else (100 if real > 0 else 0)
            desviacion_familia[familia] = {
                'base': base,
                'real': real,
                'desviacion': desv,
                'desviacion_pct': desv_pct
            }

        # Totales
        total_base = sum(base_esperada_familia.values())
        total_real = sum(total_por_familia.values())
        total_desviacion = total_real - total_base
        total_desv_pct = (total_desviacion / total_base * 100) if total_base > 0 else 0

        # === GENERAR PDF ===
        pdf = FPDF('L', 'mm', 'A4')
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Header
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, 'ANALISIS COMPARATIVO M.O', new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, 'Base Autorizada vs Pagos Reales', new_x="LMARGIN", new_y="NEXT", align='C')
        pdf.ln(3)

        # Info proyecto
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(0, 8, f'Proyecto: {nombre_proy}', new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, f'ID: {id_proy} | Comuna: {comuna_proy} | Fecha: {datetime.now().strftime("%d/%m/%Y")}', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        # === RESUMEN EJECUTIVO ===
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 8, 'RESUMEN EJECUTIVO', new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)

        # Tabla tipologías
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(200, 200, 200)
        pdf.cell(120, 7, 'Tipologia', 1, align='L', fill=True)
        pdf.cell(30, 7, 'Cantidad', 1, align='C', fill=True)
        pdf.cell(50, 7, 'Base Unitaria', 1, new_x="LMARGIN", new_y="NEXT", align='R', fill=True)

        pdf.set_font('Helvetica', '', 9)
        for tipol_id, data in base_por_tipologia.items():
            if data['tipo'] == 'Vivienda':
                cant = viviendas_por_tip.get(tipol_id, 0)
            else:
                cant = rc_por_tip.get(tipol_id, 0)
            if cant == 0:
                continue

            pdf.cell(120, 6, data['descripcion'], 1, align='L')
            pdf.cell(30, 6, str(cant), 1, align='C')
            pdf.cell(50, 6, f"${data['total_base']:,.0f}".replace(',', '.'), 1, new_x="LMARGIN", new_y="NEXT", align='R')

        pdf.ln(2)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 6, f'Total: {total_viviendas} Viviendas + {total_rc} Recintos Complementarios', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Totales comparativos
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(50, 7, 'M.O Base Esperado:', border=0)
        pdf.cell(50, 7, f'${total_base:,.0f}'.replace(',', '.'), border=0)
        pdf.cell(50, 7, 'Total Pagado:', border=0)
        pdf.cell(50, 7, f'${total_real:,.0f}'.replace(',', '.'), border=0, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(50, 7, 'Desviacion:', border=0)
        color = (0, 128, 0) if total_desviacion <= 0 else (200, 0, 0)
        pdf.set_text_color(*color)
        signo = '+' if total_desviacion > 0 else ''
        pdf.cell(100, 7, f'{signo}${total_desviacion:,.0f} ({total_desv_pct:+.1f}%)'.replace(',', '.'), border=0, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

        # === PAGOS POR FAMILIA Y BENEFICIARIO ===
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 8, 'PAGOS REALES POR FAMILIA Y BENEFICIARIO (Monto y % desviacion)', new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)

        # Ordenar familias
        familias_viv = sorted([f for f in todas_familias if f and not str(f).startswith('RC ')])
        familias_rc = sorted([f for f in todas_familias if f and str(f).startswith('RC ')])
        familias_ordenadas = familias_viv + familias_rc

        ancho_disponible = 277
        col_familia = 40

        def get_base_unitaria_benef(ben, familia):
            es_familia_rc = str(familia).startswith('RC ')
            if es_familia_rc:
                tip_id = ben['tipologia_rc']
                if tip_id and tip_id in base_por_tipologia:
                    return base_por_tipologia[tip_id]['base_por_familia'].get(familia, 0)
            else:
                tip_id = ben['tipologia_viv']
                if tip_id and tip_id in base_por_tipologia:
                    return base_por_tipologia[tip_id]['base_por_familia'].get(familia, 0)
            return 0

        benef_grupos = [beneficiarios[i:i+10] for i in range(0, len(beneficiarios), 10)]

        for grupo_idx, grupo in enumerate(benef_grupos):
            if grupo_idx > 0:
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, f'PAGOS POR FAMILIA (cont.)', new_x="LMARGIN", new_y="NEXT", fill=True)
                pdf.ln(2)

            col_benef = (ancho_disponible - col_familia) / len(grupo)

            # Header
            pdf.set_font('Helvetica', 'B', 6)
            pdf.set_fill_color(200, 200, 200)
            pdf.cell(col_familia, 7, 'Familia', 1, align='L', fill=True)
            for ben in grupo:
                pdf.cell(col_benef, 7, ben['nombre'][:10], 1, align='C', fill=True)
            pdf.ln()

            # Filas
            pdf.set_font('Helvetica', '', 5)
            for familia in familias_ordenadas:
                if not familia:
                    continue

                if str(familia).startswith('RC '):
                    pdf.set_fill_color(255, 250, 230)
                    fill = True
                else:
                    fill = False

                pdf.cell(col_familia, 5, str(familia)[:22], 1, align='L', fill=fill)

                for ben in grupo:
                    monto = pagos_por_benef_familia[ben['id']]['pagos'].get(familia, 0)
                    base = get_base_unitaria_benef(ben, familia)

                    if monto > 0:
                        if base > 0:
                            desv_pct = ((monto - base) / base) * 100
                            # Colorear si desviación > 10%
                            if desv_pct > 10:
                                pdf.set_text_color(200, 0, 0)  # Rojo - sobrecosto
                            elif desv_pct < -10:
                                pdf.set_text_color(0, 128, 0)  # Verde - ahorro
                            txt = f"${monto/1000:.0f}k({desv_pct:+.0f}%)"
                            pdf.cell(col_benef, 5, txt, 1, align='R', fill=fill)
                            pdf.set_text_color(0, 0, 0)  # Restaurar color
                        else:
                            txt = f"${monto/1000:.0f}k"
                            pdf.cell(col_benef, 5, txt, 1, align='R', fill=fill)
                    elif base > 0:
                        pdf.set_text_color(200, 0, 0)
                        pdf.cell(col_benef, 5, "(-100%)", 1, align='C', fill=fill)
                        pdf.set_text_color(0, 0, 0)
                    else:
                        pdf.cell(col_benef, 5, '-', 1, align='C', fill=fill)
                pdf.ln()

            # Total por beneficiario
            pdf.set_font('Helvetica', 'B', 6)
            pdf.set_fill_color(220, 220, 220)
            pdf.cell(col_familia, 6, 'TOTAL', 1, align='L', fill=True)
            for ben in grupo:
                total_ben = pagos_por_benef_familia[ben['id']]['total']
                base_ben = 0
                if ben['tipologia_viv'] and ben['tipologia_viv'] in base_por_tipologia:
                    base_ben += base_por_tipologia[ben['tipologia_viv']]['total_base']
                if ben['tipologia_rc'] and ben['tipologia_rc'] in base_por_tipologia:
                    base_ben += base_por_tipologia[ben['tipologia_rc']]['total_base']

                if base_ben > 0:
                    desv_ben = ((total_ben - base_ben) / base_ben) * 100
                    # Colorear si desviación > 10%
                    if desv_ben > 10:
                        pdf.set_text_color(200, 0, 0)  # Rojo - sobrecosto
                    elif desv_ben < -10:
                        pdf.set_text_color(0, 128, 0)  # Verde - ahorro
                    pdf.cell(col_benef, 6, f"${total_ben/1000:.0f}k({desv_ben:+.0f}%)", 1, align='R', fill=True)
                    pdf.set_text_color(0, 0, 0)  # Restaurar color
                else:
                    pdf.cell(col_benef, 6, f"${total_ben/1000:.0f}k", 1, align='R', fill=True)
            pdf.ln()

        pdf.ln(2)
        pdf.set_font('Helvetica', 'I', 7)
        pdf.cell(0, 4, 'Nota: Montos en miles (k). Entre parentesis: % desviacion vs base. Filas amarillas = RC.', new_x="LMARGIN", new_y="NEXT")

        # === ANÁLISIS DE DESVIACIÓN POR FAMILIA ===
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 8, 'ANALISIS DE DESVIACION POR FAMILIA', new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)

        # Header
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_fill_color(200, 200, 200)
        pdf.cell(80, 7, 'Familia de Pago', 1, align='L', fill=True)
        pdf.cell(45, 7, 'Base Esperada', 1, align='R', fill=True)
        pdf.cell(45, 7, 'Real Pagado', 1, align='R', fill=True)
        pdf.cell(45, 7, 'Desviacion', 1, align='R', fill=True)
        pdf.cell(25, 7, '%', 1, new_x="LMARGIN", new_y="NEXT", align='C', fill=True)

        def sort_key(item):
            fam, data = item
            es_rc = 1 if str(fam).startswith('RC ') else 0
            return (es_rc, -abs(data['desviacion']))

        familias_sorted = sorted(desviacion_familia.items(), key=sort_key)

        pdf.set_font('Helvetica', '', 8)
        for familia, data in familias_sorted:
            if not familia or (data['base'] == 0 and data['real'] == 0):
                continue

            if str(familia).startswith('RC '):
                pdf.set_fill_color(255, 250, 230)
                fill = True
            else:
                fill = False

            pdf.cell(80, 6, str(familia)[:40], 1, align='L', fill=fill)
            pdf.cell(45, 6, f"${data['base']:,.0f}".replace(',', '.'), 1, align='R', fill=fill)
            pdf.cell(45, 6, f"${data['real']:,.0f}".replace(',', '.'), 1, align='R', fill=fill)

            # Colorear desviación solo si > 10% en valor absoluto
            if data['desviacion_pct'] > 10:
                pdf.set_text_color(200, 0, 0)  # Rojo - sobrecosto > 10%
                signo = '+'
            elif data['desviacion_pct'] < -10:
                pdf.set_text_color(0, 128, 0)  # Verde - ahorro > 10%
                signo = ''
            else:
                pdf.set_text_color(0, 0, 0)  # Negro - desviación <= 10%
                signo = '+' if data['desviacion'] > 0 else ''

            pdf.cell(45, 6, f"{signo}${data['desviacion']:,.0f}".replace(',', '.'), 1, align='R', fill=fill)
            pdf.cell(25, 6, f"{data['desviacion_pct']:+.0f}%", 1, new_x="LMARGIN", new_y="NEXT", align='C', fill=fill)
            pdf.set_text_color(0, 0, 0)

        # Total
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_fill_color(200, 200, 200)
        pdf.cell(80, 7, 'TOTAL', 1, align='L', fill=True)
        pdf.cell(45, 7, f"${total_base:,.0f}".replace(',', '.'), 1, align='R', fill=True)
        pdf.cell(45, 7, f"${total_real:,.0f}".replace(',', '.'), 1, align='R', fill=True)

        # Colorear total solo si desviación > 10%
        if total_desv_pct > 10:
            pdf.set_text_color(200, 0, 0)  # Rojo - sobrecosto > 10%
        elif total_desv_pct < -10:
            pdf.set_text_color(0, 128, 0)  # Verde - ahorro > 10%
        else:
            pdf.set_text_color(0, 0, 0)  # Negro - desviación <= 10%

        signo = '+' if total_desviacion > 0 else ''
        pdf.cell(45, 7, f"{signo}${total_desviacion:,.0f}".replace(',', '.'), 1, align='R', fill=True)
        pdf.cell(25, 7, f"{total_desv_pct:+.1f}%", 1, new_x="LMARGIN", new_y="NEXT", align='C', fill=True)
        pdf.set_text_color(0, 0, 0)

        # Interpretación
        pdf.ln(5)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 7, 'Interpretacion:', new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Helvetica', '', 9)

        mayores_sobrecostos = [(f, d) for f, d in familias_sorted if d['desviacion'] > 0][:3]
        mayores_ahorros = [(f, d) for f, d in familias_sorted if d['desviacion'] < 0][:3]

        if mayores_sobrecostos:
            pdf.ln(2)
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 6, 'Familias con sobrecosto:', new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            for fam, data in mayores_sobrecostos:
                pdf.cell(0, 5, f"  - {fam}: +${data['desviacion']:,.0f} ({data['desviacion_pct']:+.0f}%)".replace(',', '.'), new_x="LMARGIN", new_y="NEXT")

        if mayores_ahorros:
            pdf.ln(2)
            pdf.set_text_color(0, 128, 0)
            pdf.cell(0, 6, 'Familias con ahorro:', new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            for fam, data in mayores_ahorros:
                pdf.cell(0, 5, f"  - {fam}: ${data['desviacion']:,.0f} ({data['desviacion_pct']:+.0f}%)".replace(',', '.'), new_x="LMARGIN", new_y="NEXT")

        # === GUARDAR PDF ===
        if not ruta_salida:
            nombre_limpio = re.sub(r'[^a-zA-Z0-9_]', '_', nombre_proy)[:30]
            fecha_gen = datetime.now().strftime("%Y%m%d")
            os.makedirs('reportes', exist_ok=True)
            ruta_salida = f"reportes/Analisis_MO_{nombre_limpio}_{fecha_gen}.pdf"

        pdf.output(ruta_salida)
        return ruta_salida


# === TEST ===
if __name__ == "__main__":
    from sheets_connection import SheetsConnection

    conn = SheetsConnection()
    engine = ReportesEngine(conn)

    print("=== Reportes Disponibles ===")
    for r in engine.get_reportes_disponibles():
        print(f"  - {r['codigo']}: {r['nombre']}")
        print(f"    {r['descripcion']}")
        print(f"    Ejemplo: {r['ejemplo']}")
        print()

    # Test: Generar reporte de Maria Matus
    print("\n=== Test: Resumen de Beneficiario ===")
    reporte = engine.generar_resumen_beneficiario(
        nombre_beneficiario="Matus Acuña",
        nombre_proyecto="Campesinos Esforzados"
    )

    if reporte.get("encontrado"):
        print(engine.formatear_resumen_beneficiario(reporte))
    else:
        print(f"Error: {reporte.get('error')}")

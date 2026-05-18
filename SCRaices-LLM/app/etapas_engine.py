"""
Motor de Etapas - Lógica de control y predicción de despachos
"""
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

CONFIG_PATH = Path(__file__).parent.parent / "config" / "etapas_config.json"


class EtapasEngine:
    """Motor para análisis de etapas de construcción y predicción de despachos"""

    def __init__(self, data_manager):
        self.dm = data_manager
        self.config = self._load_config()
        self._cache_despachos = None
        self._cache_beneficiarios = None
        self._cache_proyectos = None

    def _load_config(self) -> dict:
        """Carga configuración de etapas desde JSON"""
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"etapas": {}, "colores": {}, "secuencia_principal": []}

    def reload_config(self):
        """Recarga la configuración (útil si se modifica en caliente)"""
        self.config = self._load_config()

    # === ACCESO A DATOS ===

    def _get_despachos(self) -> pd.DataFrame:
        """Obtiene tabla de despachos con cache"""
        if self._cache_despachos is None:
            self._cache_despachos = self.dm.get_table_data("Despacho")
        return self._cache_despachos

    def _get_beneficiarios(self) -> pd.DataFrame:
        """Obtiene tabla de beneficiarios con cache"""
        if self._cache_beneficiarios is None:
            self._cache_beneficiarios = self.dm.get_table_data("Beneficiario")
        return self._cache_beneficiarios

    def _get_proyectos(self) -> pd.DataFrame:
        """Obtiene tabla de proyectos con cache"""
        if self._cache_proyectos is None:
            self._cache_proyectos = self.dm.get_table_data("Proyectos")
        return self._cache_proyectos

    def clear_cache(self):
        """Limpia el cache de datos"""
        self._cache_despachos = None
        self._cache_beneficiarios = None
        self._cache_proyectos = None

    # === MÉTODOS PRINCIPALES ===

    def get_despachos_beneficiario(self, id_benef: int) -> pd.DataFrame:
        """Obtiene todos los despachos de un beneficiario"""
        df = self._get_despachos()
        # Asegurar que ID_Benef sea comparable
        df_benef = df[df["ID_Benef"].astype(str) == str(id_benef)].copy()

        # Convertir fecha si existe
        if "Fecha" in df_benef.columns:
            df_benef["Fecha"] = pd.to_datetime(df_benef["Fecha"], errors="coerce")
            df_benef = df_benef.sort_values("Fecha")

        return df_benef

    def get_beneficiarios_proyecto(self, id_proy: str) -> pd.DataFrame:
        """Obtiene beneficiarios de un proyecto"""
        df = self._get_beneficiarios()
        # Manejar case sensitivity: ID_Proy en Beneficiario
        df_proy = df[df["ID_Proy"].astype(str) == str(id_proy)].copy()
        return df_proy

    def get_proyectos_activos(self) -> pd.DataFrame:
        """Obtiene proyectos en ejecución"""
        df = self._get_proyectos()
        # Filtrar por estado si existe la columna
        if "estado_general" in df.columns:
            df_activos = df[df["estado_general"].str.lower().str.contains("ejecuci", na=False)]
        else:
            df_activos = df
        return df_activos

    def _mapear_tipo_despacho_a_etapas(self, tipo_despacho: str) -> list:
        """Mapea un tipo de despacho a sus códigos de etapa.
        Soporta campos con múltiples tipos separados por coma."""
        if pd.isna(tipo_despacho):
            return []

        tipo_str = str(tipo_despacho).strip().lower()

        # Mapeo con patrones ordenados de más específico a más genérico
        mapeo = [
            ("ceramico muro", "08_CERAMICO_MURO"),
            ("ceramicos muro", "08_CERAMICO_MURO"),
            ("muro", "08_CERAMICO_MURO"),
            ("ceramico piso", "07_CERAMICO_PISO"),
            ("ceramicos piso", "07_CERAMICO_PISO"),
            ("pintura interior", "10_PINTURA_INT"),
            ("pintura ext", "09_PINTURA_EXT"),
            ("pintura r.c", "09_PINTURA_EXT"),
            ("pintura", "09_PINTURA_EXT"),
            ("fundacion", "01_FUNDACIONES"),
            ("fundaciones", "01_FUNDACIONES"),
            ("1era", "02_1ERA_ETAPA"),
            ("primera", "02_1ERA_ETAPA"),
            ("2da", "03_2DA_ETAPA"),
            ("segunda", "03_2DA_ETAPA"),
            ("ventana", "28_VENTANAS"),
            ("eifs", "29_EIFS"),
            ("aislacion", "29_EIFS"),
            ("gasfiteria", "13_GASFITERIA"),
            ("quincalleria", "30_QUINCALLERIA_VIV"),
            ("alcantarillado", "12_ALCANTARILLADO"),
            ("sol. ac", "11_SOL_AC"),
            ("cocina", "11_SOL_AC"),
            ("calefont", "11_SOL_AC"),
        ]

        # Separar por coma para manejar múltiples tipos en un registro
        partes = [p.strip() for p in tipo_str.split(",")]

        etapas_encontradas = set()
        for parte in partes:
            for patron, etapa in mapeo:
                if patron in parte and etapa not in etapas_encontradas:
                    etapas_encontradas.add(etapa)
                    break  # Solo un match por parte

        return list(etapas_encontradas)

    def get_estado_etapas(self, id_benef: int) -> dict:
        """
        Calcula el estado de cada etapa para un beneficiario.

        Returns:
            dict: {
                "etapa_key": {
                    "nombre": str,
                    "estado": "despachado" | "en_tiempo" | "atencion" | "critico" | "bloqueado",
                    "fecha_despacho": datetime | None,
                    "dias_transcurridos": int | None,
                    "dias_restantes": int | None
                }
            }
        """
        despachos = self.get_despachos_beneficiario(id_benef)
        resultado = {}
        hoy = datetime.now()

        # Identificar etapas completadas
        etapas_completadas = set()
        fechas_etapas = {}

        for _, row in despachos.iterrows():
            tipo = row.get("Tipo_despacho", "")
            etapa_keys = self._mapear_tipo_despacho_a_etapas(tipo)
            for etapa_key in etapa_keys:
                etapas_completadas.add(etapa_key)
                if pd.notna(row.get("Fecha")):
                    fecha = pd.to_datetime(row["Fecha"])
                    if etapa_key not in fechas_etapas or fecha > fechas_etapas[etapa_key]:
                        fechas_etapas[etapa_key] = fecha

        # Procesar cada etapa de la configuración
        for etapa_key, config in self.config.get("etapas", {}).items():
            info = {
                "nombre": config.get("nombre", etapa_key),
                "estado": "bloqueado",
                "fecha_despacho": None,
                "dias_transcurridos": None,
                "dias_restantes": None,
                "critico": config.get("critico", False)
            }

            if etapa_key in etapas_completadas:
                # Etapa completada
                info["estado"] = "despachado"
                info["fecha_despacho"] = fechas_etapas.get(etapa_key)
            else:
                # Verificar si puede iniciar (dependencias cumplidas)
                dependencia = config.get("dependencia")
                dependencia_multiple = config.get("dependencia_multiple", [])

                puede_iniciar = True
                fecha_ref = None

                if dependencia:
                    if dependencia not in etapas_completadas:
                        puede_iniciar = False
                    else:
                        fecha_ref = fechas_etapas.get(dependencia)

                if dependencia_multiple:
                    for dep in dependencia_multiple:
                        if dep not in etapas_completadas:
                            puede_iniciar = False
                            break
                    # Usar la fecha más reciente de las dependencias
                    if puede_iniciar:
                        fechas_deps = [fechas_etapas.get(d) for d in dependencia_multiple if d in fechas_etapas]
                        if fechas_deps:
                            fecha_ref = max(fechas_deps)

                if config.get("es_inicio", False):
                    puede_iniciar = True
                    fecha_ref = None

                if puede_iniciar and fecha_ref:
                    # Calcular días descontando la duración en obra de la dependencia
                    dias_brutos = (hoy - fecha_ref).days

                    # Restar duración de obra de la etapa previa
                    duracion_previa = 0
                    dep_key = dependencia
                    if not dep_key and dependencia_multiple:
                        # Usar la dependencia con mayor duración
                        for d in dependencia_multiple:
                            d_cfg = self.config.get("etapas", {}).get(d, {})
                            duracion_previa = max(duracion_previa, d_cfg.get("duracion", 0))
                    elif dep_key:
                        dep_cfg = self.config.get("etapas", {}).get(dep_key, {})
                        duracion_previa = dep_cfg.get("duracion", 0)

                    # Días efectivos = días desde despacho - duración obra previa
                    dias = max(0, dias_brutos - duracion_previa)
                    info["dias_transcurridos"] = dias
                    info["dias_brutos"] = dias_brutos
                    info["duracion_previa"] = duracion_previa

                    tiempo_optimo = config.get("tiempo_optimo")
                    tiempo_alerta = config.get("tiempo_alerta")

                    if tiempo_optimo is not None and tiempo_alerta is not None:
                        info["dias_restantes"] = tiempo_alerta - dias

                        if dias <= tiempo_optimo:
                            info["estado"] = "en_tiempo"
                        elif dias <= tiempo_alerta:
                            info["estado"] = "atencion"
                        else:
                            info["estado"] = "critico"
                    else:
                        info["estado"] = "en_tiempo"
                elif puede_iniciar and config.get("es_inicio", False):
                    info["estado"] = "en_tiempo"

            resultado[etapa_key] = info

        return resultado

    def get_alertas_proyecto(self, id_proy: str) -> list:
        """
        Genera lista de alertas críticas para un proyecto.

        Returns:
            list: [{
                "id_benef": int,
                "nombre": str,
                "etapa": str,
                "mensaje": str,
                "prioridad": int (1=máxima),
                "dias_atraso": int
            }]
        """
        beneficiarios = self.get_beneficiarios_proyecto(id_proy)
        alertas = []

        for _, benef in beneficiarios.iterrows():
            id_benef = benef.get("ID_Benef")
            nombre = f"{benef.get('NOMBRES', '')} {benef.get('APELLIDOS', '')}".strip()
            estado = benef.get("Estado", "")

            # Solo procesar beneficiarios en ejecución
            if estado and "ejecuci" not in str(estado).lower():
                continue

            estados_etapas = self.get_estado_etapas(id_benef)

            for etapa_key, info in estados_etapas.items():
                if info["estado"] == "critico":
                    dias_atraso = info.get("dias_transcurridos", 0)
                    config_etapa = self.config.get("etapas", {}).get(etapa_key, {})
                    tiempo_alerta = config_etapa.get("tiempo_alerta", 0)

                    # Calcular prioridad (menor = más urgente)
                    prioridad = 3
                    if info.get("critico", False):
                        prioridad = 1
                    elif dias_atraso > tiempo_alerta + 7:
                        prioridad = 2

                    alertas.append({
                        "id_benef": id_benef,
                        "nombre": nombre or f"Beneficiario {id_benef}",
                        "etapa": info["nombre"],
                        "etapa_key": etapa_key,
                        "mensaje": f"{info['nombre']} atrasado {dias_atraso - tiempo_alerta} días",
                        "prioridad": prioridad,
                        "dias_atraso": dias_atraso - tiempo_alerta if tiempo_alerta else dias_atraso
                    })
                elif info["estado"] == "atencion":
                    dias_restantes = info.get("dias_restantes", 0)

                    if dias_restantes <= 3:  # Alerta si quedan 3 días o menos
                        alertas.append({
                            "id_benef": id_benef,
                            "nombre": nombre or f"Beneficiario {id_benef}",
                            "etapa": info["nombre"],
                            "etapa_key": etapa_key,
                            "mensaje": f"{info['nombre']} - {dias_restantes} días restantes",
                            "prioridad": 4,
                            "dias_atraso": 0
                        })

        # Ordenar por prioridad
        alertas.sort(key=lambda x: (x["prioridad"], -x["dias_atraso"]))

        return alertas

    def get_prediccion_despachos(self, id_proy: str) -> pd.DataFrame:
        """
        Genera predicción de próximos despachos necesarios.

        Returns:
            DataFrame con columnas: ID_Benef, Nombre, Etapa_Siguiente, Fecha_Sugerida, Urgencia
        """
        beneficiarios = self.get_beneficiarios_proyecto(id_proy)
        predicciones = []
        hoy = datetime.now()

        for _, benef in beneficiarios.iterrows():
            id_benef = benef.get("ID_Benef")
            nombre = f"{benef.get('NOMBRES', '')} {benef.get('APELLIDOS', '')}".strip()
            estado = benef.get("Estado", "")

            # Solo procesar beneficiarios activos
            if estado and "ejecuci" not in str(estado).lower() and "preparacion" not in str(estado).lower():
                continue

            estados_etapas = self.get_estado_etapas(id_benef)

            # Encontrar etapa más urgente pendiente
            for etapa_key in self.config.get("secuencia_principal", []):
                info = estados_etapas.get(etapa_key, {})

                if info.get("estado") in ["en_tiempo", "atencion", "critico"]:
                    # Esta es la siguiente etapa a despachar
                    config_etapa = self.config.get("etapas", {}).get(etapa_key, {})
                    tiempo_optimo = config_etapa.get("tiempo_optimo", 7)

                    # Calcular fecha sugerida
                    if info.get("dias_transcurridos") is not None:
                        dias_restantes = tiempo_optimo - info["dias_transcurridos"]
                        fecha_sugerida = hoy + timedelta(days=max(0, dias_restantes))
                    else:
                        fecha_sugerida = hoy + timedelta(days=tiempo_optimo or 7)

                    # Determinar urgencia
                    if info["estado"] == "critico":
                        urgencia = "URGENTE"
                    elif info["estado"] == "atencion":
                        urgencia = "Pronto"
                    else:
                        urgencia = "Normal"

                    predicciones.append({
                        "ID_Benef": id_benef,
                        "Nombre": nombre or f"Beneficiario {id_benef}",
                        "Etapa_Siguiente": info.get("nombre", etapa_key),
                        "Fecha_Sugerida": fecha_sugerida.strftime("%d/%m/%Y"),
                        "Fecha_Orden": fecha_sugerida,
                        "Urgencia": urgencia,
                        "Dias_Restantes": info.get("dias_restantes")
                    })
                    break  # Solo la primera etapa pendiente

        if not predicciones:
            return pd.DataFrame(columns=["ID_Benef", "Nombre", "Etapa_Siguiente", "Fecha_Sugerida", "Urgencia"])

        df = pd.DataFrame(predicciones)
        df = df.sort_values("Fecha_Orden")

        return df[["ID_Benef", "Nombre", "Etapa_Siguiente", "Fecha_Sugerida", "Urgencia"]]

    def get_resumen_proyecto(self, id_proy: str) -> dict:
        """
        Genera métricas generales del proyecto.

        Returns:
            dict: {
                "total_beneficiarios": int,
                "en_tiempo": int,
                "atencion": int,
                "criticos": int,
                "bloqueados": int,
                "completados": int,
                "porcentaje_avance": float
            }
        """
        beneficiarios = self.get_beneficiarios_proyecto(id_proy)

        resumen = {
            "total_beneficiarios": 0,
            "en_tiempo": 0,
            "atencion": 0,
            "criticos": 0,
            "bloqueados": 0,
            "completados": 0,
            "porcentaje_avance": 0.0
        }

        total_etapas = len(self.config.get("secuencia_principal", []))
        etapas_completadas_total = 0
        beneficiarios_activos = 0

        for _, benef in beneficiarios.iterrows():
            estado = benef.get("Estado", "")

            # Solo contar beneficiarios activos
            if estado and "eliminado" in str(estado).lower():
                continue

            resumen["total_beneficiarios"] += 1
            id_benef = benef.get("ID_Benef")
            estados_etapas = self.get_estado_etapas(id_benef)

            # Contar etapas completadas para este beneficiario
            etapas_completas = sum(1 for info in estados_etapas.values() if info["estado"] == "despachado")
            etapas_completadas_total += etapas_completas

            # Clasificar el estado general del beneficiario
            tiene_critico = any(info["estado"] == "critico" for info in estados_etapas.values())
            tiene_atencion = any(info["estado"] == "atencion" for info in estados_etapas.values())
            todo_completado = all(info["estado"] == "despachado" for info in estados_etapas.values()
                                 if estados_etapas)
            todo_bloqueado = all(info["estado"] == "bloqueado" for info in estados_etapas.values()
                                if estados_etapas)

            if todo_completado and estados_etapas:
                resumen["completados"] += 1
            elif tiene_critico:
                resumen["criticos"] += 1
            elif tiene_atencion:
                resumen["atencion"] += 1
            elif todo_bloqueado:
                resumen["bloqueados"] += 1
            else:
                resumen["en_tiempo"] += 1

            beneficiarios_activos += 1

        # Calcular porcentaje de avance
        if beneficiarios_activos > 0 and total_etapas > 0:
            resumen["porcentaje_avance"] = (etapas_completadas_total / (beneficiarios_activos * total_etapas)) * 100

        return resumen

    def get_secuencia_completa(self) -> list:
        """
        Genera la secuencia completa de etapas ordenada por dependencias.
        Agrupa etapas que comparten la misma dependencia.

        Returns:
            list de dicts: [{"key": str, "nombre": str, "dependencia": str|None}]
        """
        etapas = self.config.get("etapas", {})
        # Construir orden por dependencias (BFS desde las de inicio)
        ordenadas = []
        procesadas = set()

        # Primero las de inicio
        for key, cfg in etapas.items():
            if cfg.get("es_inicio", False):
                ordenadas.append(key)
                procesadas.add(key)

        # Luego iterar agregando las que dependen de las ya procesadas
        changed = True
        while changed:
            changed = False
            for key, cfg in etapas.items():
                if key in procesadas:
                    continue
                dep = cfg.get("dependencia")
                dep_mult = cfg.get("dependencia_multiple", [])
                if dep and dep in procesadas:
                    ordenadas.append(key)
                    procesadas.add(key)
                    changed = True
                elif dep_mult and all(d in procesadas for d in dep_mult):
                    ordenadas.append(key)
                    procesadas.add(key)
                    changed = True

        # Reordenar con BFS: agrupa etapas con misma dependencia juntas
        # antes de descender al siguiente nivel
        from collections import deque

        grupos = {}
        for key in ordenadas:
            cfg = etapas[key]
            dep = cfg.get("dependencia") or ",".join(cfg.get("dependencia_multiple", [])) or "_inicio"
            if dep not in grupos:
                grupos[dep] = []
            grupos[dep].append(key)

        resultado = []
        visitados = set()
        cola = deque()

        # Semillas: etapas de inicio
        for key in ordenadas:
            if etapas[key].get("es_inicio", False):
                cola.append(key)

        while cola:
            key = cola.popleft()
            if key in visitados:
                continue
            visitados.add(key)
            resultado.append(key)

            # Agregar todos los hijos directos de este nodo (misma dependencia, juntos)
            hijos = grupos.get(key, [])
            for hijo in hijos:
                if hijo not in visitados:
                    cola.append(hijo)

        # Agregar cualquier etapa que no se haya alcanzado (por dependencia_multiple)
        for key in ordenadas:
            if key not in visitados:
                resultado.append(key)

        return resultado

    def get_matriz_estado(self, id_proy: str) -> pd.DataFrame:
        """
        Genera matriz de estado para visualización (beneficiarios x etapas).
        Incluye TODAS las etapas configuradas, ordenadas por dependencias.

        Returns:
            DataFrame con beneficiarios en filas y etapas en columnas.
            Cada celda contiene "estado|dias" (ej: "despachado|5").
        """
        beneficiarios = self.get_beneficiarios_proyecto(id_proy)
        etapas_secuencia = self.get_secuencia_completa()
        etapas_cfg = self.config.get("etapas", {})

        rows = []
        for _, benef in beneficiarios.iterrows():
            estado = benef.get("Estado", "")
            if estado and "eliminado" in str(estado).lower():
                continue

            id_benef = benef.get("ID_Benef")
            nombre = f"{benef.get('NOMBRES', '')} {benef.get('APELLIDOS', '')}".strip()
            estados = self.get_estado_etapas(id_benef)

            row = {
                "ID_Benef": id_benef,
                "Nombre": nombre or f"Beneficiario {id_benef}"
            }

            # Guardar fecha de fundación para ordenar
            info_fund = estados.get("01_FUNDACIONES", {})
            row["_fecha_fund"] = info_fund.get("fecha_despacho") if info_fund.get("estado") == "despachado" else None

            # Recopilar fechas de despacho para calcular días entre etapas
            fechas_despacho = {}
            for ek in etapas_secuencia:
                inf = estados.get(ek, {})
                if inf.get("estado") == "despachado" and inf.get("fecha_despacho"):
                    fechas_despacho[ek] = inf["fecha_despacho"]

            for etapa_key in etapas_secuencia:
                info = estados.get(etapa_key, {})
                etapa_config = etapas_cfg.get(etapa_key, {})
                nombre_etapa = etapa_config.get("nombre", etapa_key)

                estado_val = info.get("estado", "bloqueado")
                dias = ""

                if estado_val == "despachado" and etapa_key in fechas_despacho:
                    # Días entre esta etapa y su dependencia
                    dep = etapa_config.get("dependencia")
                    dep_mult = etapa_config.get("dependencia_multiple", [])
                    fecha_prev = None
                    if dep and dep in fechas_despacho:
                        fecha_prev = fechas_despacho[dep]
                    elif dep_mult:
                        fechas_deps = [fechas_despacho[d] for d in dep_mult if d in fechas_despacho]
                        if fechas_deps:
                            fecha_prev = max(fechas_deps)
                    if fecha_prev:
                        dias_entre = (fechas_despacho[etapa_key] - fecha_prev).days
                        dias = str(dias_entre)
                elif info.get("dias_transcurridos") is not None:
                    dias = str(info["dias_transcurridos"])

                row[nombre_etapa] = f"{estado_val}|{dias}"

            rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Ordenar: primero los que tienen fundación despachada (por fecha asc),
        # luego sin fundación en orden alfabético
        df["_tiene_fund"] = df["_fecha_fund"].notna()
        # Asignar fecha lejana a los sin fundación para que queden al final
        fecha_lejana = pd.Timestamp("2099-12-31")
        df["_fecha_sort"] = df["_fecha_fund"].fillna(fecha_lejana)
        df = df.sort_values(
            by=["_tiene_fund", "_fecha_sort", "Nombre"],
            ascending=[False, True, True]
        )
        df = df.drop(columns=["_tiene_fund", "_fecha_fund", "_fecha_sort"]).reset_index(drop=True)

        return df

    def get_kanban_acciones(self, id_proy: str) -> dict:
        """
        Genera tarjetas Kanban agrupadas por urgencia para el panel de acciones.

        Returns:
            dict con 4 listas:
            {
                "solicitar_ya": [...],    # 🔴 Etapas que ya deberían haberse solicitado
                "solicitar_pronto": [...], # 🟡 Etapas que deben solicitarse pronto
                "en_obra": [...],          # 🔨 Etapas despachadas cuya obra está en curso
                "al_dia": [...]            # ✅ Beneficiarios sin acciones pendientes
            }
            Cada tarjeta: {
                "id_benef", "nombre", "etapa", "etapa_key",
                "dias_efectivos", "dias_restantes", "duracion_previa",
                "mensaje", "etapas_despachadas" (lista de etapas ya despachadas con días)
            }
        """
        beneficiarios = self.get_beneficiarios_proyecto(id_proy)
        etapas_config = self.config.get("etapas", {})

        kanban = {
            "solicitar_ya": [],
            "solicitar_pronto": [],
            "en_obra": [],
            "terminado": []
        }

        for _, benef in beneficiarios.iterrows():
            estado_benef = benef.get("Estado", "")
            if estado_benef and "eliminado" in str(estado_benef).lower():
                continue

            id_benef = benef.get("ID_Benef")
            nombre = f"{benef.get('NOMBRES', '')} {benef.get('APELLIDOS', '')}".strip()
            nombre = nombre or f"Beneficiario {id_benef}"

            estados = self.get_estado_etapas(id_benef)

            # Recopilar etapas despachadas con días
            etapas_despachadas = []
            for ek, info in estados.items():
                if info["estado"] == "despachado" and info.get("fecha_despacho"):
                    dias_desde = (datetime.now() - info["fecha_despacho"]).days
                    cfg = etapas_config.get(ek, {})
                    duracion = cfg.get("duracion", 0)
                    en_obra = dias_desde < duracion
                    etapas_despachadas.append({
                        "nombre": info["nombre"],
                        "dias": dias_desde,
                        "duracion": duracion,
                        "en_obra": en_obra
                    })

            # Buscar etapas pendientes que requieren acción
            tiene_accion = False
            for etapa_key, info in estados.items():
                if info["estado"] in ("critico", "atencion", "en_tiempo") and info.get("dias_transcurridos") is not None:
                    cfg = etapas_config.get(etapa_key, {})
                    tiempo_optimo = cfg.get("tiempo_optimo")
                    tiempo_alerta = cfg.get("tiempo_alerta")

                    tarjeta = {
                        "id_benef": id_benef,
                        "nombre": nombre,
                        "etapa": info["nombre"],
                        "etapa_key": etapa_key,
                        "dias_efectivos": info["dias_transcurridos"],
                        "dias_brutos": info.get("dias_brutos", info["dias_transcurridos"]),
                        "dias_restantes": info.get("dias_restantes"),
                        "duracion_previa": info.get("duracion_previa", 0),
                        "critico": info.get("critico", False),
                        "etapas_despachadas": etapas_despachadas
                    }

                    if info["estado"] == "critico":
                        dias_atraso = info["dias_transcurridos"] - (tiempo_alerta or 0)
                        tarjeta["mensaje"] = f"Solicitar {info['nombre']} — {dias_atraso} días de atraso"
                        kanban["solicitar_ya"].append(tarjeta)
                        tiene_accion = True
                    elif info["estado"] == "atencion":
                        tarjeta["mensaje"] = f"Solicitar {info['nombre']} — quedan {info.get('dias_restantes', '?')} días"
                        kanban["solicitar_pronto"].append(tarjeta)
                        tiene_accion = True
                    elif info["estado"] == "en_tiempo" and info["dias_transcurridos"] > 0:
                        tarjeta["mensaje"] = f"{info['nombre']} — {info.get('dias_restantes', '?')} días restantes"
                        kanban["en_obra"].append(tarjeta)
                        tiene_accion = True

            # Verificar si hay etapas en obra (despachadas recientemente)
            if not tiene_accion and etapas_despachadas:
                hay_en_obra = any(e["en_obra"] for e in etapas_despachadas)
                if hay_en_obra:
                    kanban["en_obra"].append({
                        "id_benef": id_benef,
                        "nombre": nombre,
                        "etapa": "",
                        "etapa_key": "",
                        "dias_efectivos": 0,
                        "dias_brutos": 0,
                        "dias_restantes": None,
                        "duracion_previa": 0,
                        "critico": False,
                        "mensaje": "Obra a Tiempo",
                        "etapas_despachadas": etapas_despachadas
                    })
                elif etapas_despachadas:
                    kanban["terminado"].append({
                        "id_benef": id_benef,
                        "nombre": nombre,
                        "etapa": "",
                        "etapa_key": "",
                        "dias_efectivos": 0,
                        "dias_brutos": 0,
                        "dias_restantes": None,
                        "duracion_previa": 0,
                        "critico": False,
                        "mensaje": "Todo despachado",
                        "etapas_despachadas": etapas_despachadas
                    })

        # Ordenar cada columna: primero por etapa (agrupar misma etapa), luego por urgencia
        kanban["solicitar_ya"].sort(key=lambda x: (x.get("etapa_key", ""), -1 if x["critico"] else 0, -x["dias_efectivos"]))
        kanban["solicitar_pronto"].sort(key=lambda x: (x.get("etapa_key", ""), x.get("dias_restantes") or 999))
        kanban["en_obra"].sort(key=lambda x: (x.get("etapa_key", ""), x.get("nombre", "")))

        return kanban

    def get_reglas_etapas(self) -> list:
        """
        Retorna las reglas de etapas para visualización.

        Returns:
            list de dicts con info de cada etapa y sus reglas
        """
        reglas = []
        etapas = self.config.get("etapas", {})

        for etapa_key, config in etapas.items():
            dep = config.get("dependencia", "")
            dep_nombre = ""
            if dep and dep in etapas:
                dep_nombre = etapas[dep].get("nombre", dep)

            dep_multiple = config.get("dependencia_multiple", [])
            deps_multiples_nombres = []
            for d in dep_multiple:
                if d in etapas:
                    deps_multiples_nombres.append(etapas[d].get("nombre", d))

            reglas.append({
                "codigo": config.get("codigo", ""),
                "nombre": config.get("nombre", etapa_key),
                "duracion": config.get("duracion"),
                "tiempo_optimo": config.get("tiempo_optimo"),
                "tiempo_alerta": config.get("tiempo_alerta"),
                "dependencia": dep_nombre,
                "dependencias_multiples": ", ".join(deps_multiples_nombres) if deps_multiples_nombres else "",
                "critico": config.get("critico", False),
                "es_inicio": config.get("es_inicio", False),
            })

        return reglas

    # === UTILIDADES DE VISUALIZACIÓN ===

    @staticmethod
    def render_semaforo(estado: str) -> str:
        """Convierte estado a emoji de semáforo"""
        emojis = {
            "despachado": "✅",
            "en_tiempo": "🟢",
            "atencion": "🟡",
            "critico": "🔴",
            "bloqueado": "⚪"
        }
        return emojis.get(estado, "⚪")

    def get_colores(self) -> dict:
        """Obtiene configuración de colores"""
        return self.config.get("colores", {
            "en_tiempo": "#22c55e",
            "atencion": "#eab308",
            "critico": "#ef4444",
            "bloqueado": "#9ca3af",
            "despachado": "#3b82f6"
        })

    # === PLAZOS DE CONTRATO ===

    def get_plazos_proyecto(self, id_proy: str) -> dict:
        """
        Calcula los plazos de contrato de un proyecto.

        Lógica:
        - Fecha término = fecha_inicio + duracion (días)
        - Si hay prórrogas, se suman a la duración

        Returns:
            dict: {
                "fecha_inicio": datetime | None,
                "duracion_original": int | None,
                "prorroga1": int | None,
                "prorroga2": int | None,
                "duracion_total": int | None,
                "fecha_termino": datetime | None,
                "dias_transcurridos": int | None,
                "dias_restantes": int | None,
                "avance_tiempo": float | None,
                "estado_plazo": str  # "en_tiempo", "proximo_vencer", "vencido"
            }
        """
        proyectos = self._get_proyectos()
        proy = proyectos[proyectos["ID_proy"].astype(str) == str(id_proy)]

        if len(proy) == 0:
            return {"error": "Proyecto no encontrado"}

        row = proy.iloc[0]
        resultado = {
            "id_proy": id_proy,
            "nombre": row.get("NOMBRE_PROYECTO", ""),
            "fecha_inicio": None,
            "duracion_original": None,
            "prorroga1": None,
            "prorroga2": None,
            "duracion_total": None,
            "fecha_termino": None,
            "dias_transcurridos": None,
            "dias_restantes": None,
            "avance_tiempo": None,
            "estado_plazo": "sin_datos"
        }

        # Parsear fecha de inicio
        fecha_inicio_str = row.get("fecha_inicio", "")
        if fecha_inicio_str and pd.notna(fecha_inicio_str):
            try:
                resultado["fecha_inicio"] = pd.to_datetime(fecha_inicio_str, dayfirst=True)
            except:
                pass

        # Parsear duración
        duracion = row.get("duracion", None)
        if duracion and pd.notna(duracion):
            try:
                resultado["duracion_original"] = int(duracion)
            except:
                pass

        # Parsear prórrogas
        for prorr_field, prorr_key in [("Prorroga1", "prorroga1"), ("Prorroga2", "prorroga2")]:
            prorr_val = row.get(prorr_field, None)
            if prorr_val and pd.notna(prorr_val) and str(prorr_val).strip():
                try:
                    resultado[prorr_key] = int(prorr_val)
                except:
                    pass

        # Calcular duración total
        if resultado["duracion_original"]:
            duracion_total = resultado["duracion_original"]
            if resultado["prorroga1"]:
                duracion_total += resultado["prorroga1"]
            if resultado["prorroga2"]:
                duracion_total += resultado["prorroga2"]
            resultado["duracion_total"] = duracion_total

        # Calcular fecha de término
        if resultado["fecha_inicio"] and resultado["duracion_total"]:
            resultado["fecha_termino"] = resultado["fecha_inicio"] + timedelta(days=resultado["duracion_total"])

        # Calcular días transcurridos y restantes
        hoy = datetime.now()
        if resultado["fecha_inicio"]:
            resultado["dias_transcurridos"] = (hoy - resultado["fecha_inicio"]).days

        if resultado["fecha_termino"]:
            resultado["dias_restantes"] = (resultado["fecha_termino"] - hoy).days

        # Calcular avance en tiempo
        if resultado["duracion_total"] and resultado["dias_transcurridos"] is not None:
            resultado["avance_tiempo"] = min(100, (resultado["dias_transcurridos"] / resultado["duracion_total"]) * 100)

        # Determinar estado del plazo
        if resultado["dias_restantes"] is not None:
            if resultado["dias_restantes"] < 0:
                resultado["estado_plazo"] = "vencido"
            elif resultado["dias_restantes"] <= 30:
                resultado["estado_plazo"] = "proximo_vencer"
            else:
                resultado["estado_plazo"] = "en_tiempo"

        return resultado

    def get_resumen_plazos_todos(self) -> pd.DataFrame:
        """
        Genera tabla resumen de plazos para todos los proyectos activos.

        Returns:
            DataFrame con columnas:
            - ID_proy, Nombre, Comuna, fecha_inicio, duracion_original,
            - prorroga1, prorroga2, duracion_total, fecha_termino,
            - dias_transcurridos, dias_restantes, avance_tiempo, estado_plazo
        """
        proyectos = self._get_proyectos()

        # Filtrar proyectos activos (con fecha de inicio)
        proyectos_activos = proyectos[
            proyectos["fecha_inicio"].notna() &
            (proyectos["fecha_inicio"] != "")
        ]

        resultados = []
        for _, row in proyectos_activos.iterrows():
            id_proy = row.get("ID_proy", "")
            plazos = self.get_plazos_proyecto(id_proy)

            # Formatear fechas para display
            fecha_inicio_str = ""
            fecha_termino_str = ""
            if plazos.get("fecha_inicio"):
                fecha_inicio_str = plazos["fecha_inicio"].strftime("%d/%m/%Y")
            if plazos.get("fecha_termino"):
                fecha_termino_str = plazos["fecha_termino"].strftime("%d/%m/%Y")

            resultados.append({
                "ID_proy": id_proy,
                "Nombre": plazos.get("nombre", ""),
                "Comuna": row.get("COMUNA", ""),
                "Fecha_Inicio": fecha_inicio_str,
                "Duracion": plazos.get("duracion_original"),
                "Prorroga1": plazos.get("prorroga1") or "",
                "Prorroga2": plazos.get("prorroga2") or "",
                "Duracion_Total": plazos.get("duracion_total"),
                "Fecha_Termino": fecha_termino_str,
                "Dias_Transcurridos": plazos.get("dias_transcurridos"),
                "Dias_Restantes": plazos.get("dias_restantes"),
                "Avance_Tiempo_%": round(plazos.get("avance_tiempo") or 0, 1),
                "Estado_Plazo": plazos.get("estado_plazo", "")
            })

        df = pd.DataFrame(resultados)

        # Ordenar por días restantes (los más urgentes primero)
        if "Dias_Restantes" in df.columns and len(df) > 0:
            df = df.sort_values("Dias_Restantes", ascending=True)

        return df

    # === DASHBOARD DE CONTRATOS ===

    def get_dashboard_contratos(self, dias_inicio_max: int = 800) -> pd.DataFrame:
        """
        Genera Dashboard de Control de Contratos.

        Incluye proyectos que:
        - Tienen contrato vencido
        - Están terminados
        - Iniciaron en los últimos N días

        Args:
            dias_inicio_max: Máximo de días desde inicio de contrato (default 800)

        Returns:
            DataFrame con columnas:
            - ID_proy, Nombre, Comuna, Periodo
            - Fecha_Inicio, Duracion, Prorrogas, Duracion_Total, Fecha_Termino
            - Dias_Transcurridos, Dias_Restantes, Avance_Tiempo_%
            - Estado_Plazo, Estado_General
            - Beneficiarios, Encargado
        """
        proyectos = self._get_proyectos()
        beneficiarios = self._get_beneficiarios()
        hoy = datetime.now()

        resultados = []

        for _, row in proyectos.iterrows():
            id_proy = str(row.get("ID_proy", ""))
            if not id_proy or id_proy.strip() == "":
                continue

            # Obtener plazos
            plazos = self.get_plazos_proyecto(id_proy)

            # Filtrar: solo proyectos con fecha de inicio
            if not plazos.get("fecha_inicio"):
                continue

            dias_desde_inicio = plazos.get("dias_transcurridos", 0) or 0
            estado_plazo = plazos.get("estado_plazo", "sin_datos")
            estado_general = str(row.get("estado_general", "")).lower()

            # Filtrar según criterios:
            # - Contrato vencido
            # - Terminado
            # - Inicio en últimos N días
            es_vencido = estado_plazo == "vencido"
            es_terminado = "terminado" in estado_general or "finalizado" in estado_general
            es_reciente = dias_desde_inicio <= dias_inicio_max

            if not (es_vencido or es_terminado or es_reciente):
                continue

            # Contar beneficiarios
            benef_proy = beneficiarios[beneficiarios["ID_Proy"].astype(str) == id_proy]
            n_beneficiarios = len(benef_proy)

            # Formatear fechas
            fecha_inicio_str = ""
            fecha_termino_str = ""
            if plazos.get("fecha_inicio"):
                fecha_inicio_str = plazos["fecha_inicio"].strftime("%d/%m/%Y")
            if plazos.get("fecha_termino"):
                fecha_termino_str = plazos["fecha_termino"].strftime("%d/%m/%Y")

            # Detectar prórrogas (archivo PDF)
            tiene_prorroga = ""
            p1 = row.get("Prorroga1", "")
            p2 = row.get("Prorroga2", "")
            if p1 and pd.notna(p1) and "pdf" in str(p1).lower():
                tiene_prorroga = "SI"
            if p2 and pd.notna(p2) and "pdf" in str(p2).lower():
                tiene_prorroga = "SI"

            resultados.append({
                "ID_proy": id_proy,
                "Nombre": plazos.get("nombre", "")[:30],
                "Comuna": str(row.get("COMUNA", ""))[:15],
                "Periodo": str(row.get("PERIODO", ""))[:20],
                "Fecha_Inicio": fecha_inicio_str,
                "Duracion": plazos.get("duracion_original"),
                "Prorroga": tiene_prorroga,
                "Duracion_Total": plazos.get("duracion_total"),
                "Fecha_Termino": fecha_termino_str,
                "Dias_Transcurridos": plazos.get("dias_transcurridos"),
                "Dias_Restantes": plazos.get("dias_restantes"),
                "Avance_Tiempo_%": round(plazos.get("avance_tiempo") or 0, 1),
                "Estado_Plazo": estado_plazo,
                "Estado_General": row.get("estado_general", ""),
                "Beneficiarios": n_beneficiarios,
                "Encargado": str(row.get("Encargado", "")).replace("@scraices.cl", "")[:15]
            })

        df = pd.DataFrame(resultados)

        # Ordenar por días restantes
        if "Dias_Restantes" in df.columns and len(df) > 0:
            df = df.sort_values("Dias_Restantes", ascending=True)

        return df

    # === ANÁLISIS DE DESPACHOS Y RENDIMIENTO ===

    def get_analisis_despachos_rendimiento(self, dias_inicio_max: int = 800) -> pd.DataFrame:
        """
        Genera Análisis de Despachos y Rendimiento por proyecto.

        Incluye proyectos que:
        - Tienen contrato vencido
        - Están terminados
        - Iniciaron en los últimos N días

        Args:
            dias_inicio_max: Máximo de días desde inicio de contrato (default 800)

        Returns:
            DataFrame con KPIs de despachos:
            - Total_Despachos, Total_Etapas
            - Primer_Despacho, Ultimo_Despacho
            - Dias_Perdidos (antes de iniciar), Dias_Actividad
            - Intensidad_Activa (desp/día sin días perdidos)
            - Intensidad_Real (desp/día con días perdidos)
            - Desp_Semana, Desp_Mes
            - Promedio_Semanal, Max_Semanal
            - Promedio_Mensual, Max_Mensual
            - Desp_por_Beneficiario, Etapas_por_Beneficiario
        """
        proyectos = self._get_proyectos()
        beneficiarios = self._get_beneficiarios()
        despachos = self._get_despachos()
        hoy = datetime.now()

        resultados = []

        for _, row in proyectos.iterrows():
            id_proy = str(row.get("ID_proy", ""))
            if not id_proy or id_proy.strip() == "":
                continue

            # Obtener plazos
            plazos = self.get_plazos_proyecto(id_proy)

            # Filtrar: solo proyectos con fecha de inicio
            if not plazos.get("fecha_inicio"):
                continue

            dias_desde_inicio = plazos.get("dias_transcurridos", 0) or 0
            estado_plazo = plazos.get("estado_plazo", "sin_datos")
            estado_general = str(row.get("estado_general", "")).lower()

            # Filtrar según criterios
            es_vencido = estado_plazo == "vencido"
            es_terminado = "terminado" in estado_general or "finalizado" in estado_general
            es_reciente = dias_desde_inicio <= dias_inicio_max

            if not (es_vencido or es_terminado or es_reciente):
                continue

            # Obtener despachos del proyecto
            desp_proy = despachos[despachos["ID_proy"].astype(str) == id_proy].copy()
            if "Fecha" in desp_proy.columns:
                desp_proy["Fecha"] = pd.to_datetime(desp_proy["Fecha"], errors="coerce")
                desp_proy = desp_proy.dropna(subset=["Fecha"])
                # Filtrar fechas erróneas (futuro lejano)
                desp_proy = desp_proy[desp_proy["Fecha"] < hoy + timedelta(days=30)]

            # Contar beneficiarios
            benef_proy = beneficiarios[beneficiarios["ID_Proy"].astype(str) == id_proy]
            n_beneficiarios = len(benef_proy)

            n_despachos = len(desp_proy)

            # Si no hay despachos, registrar con valores nulos
            if n_despachos == 0:
                resultados.append({
                    "ID_proy": id_proy,
                    "Nombre": plazos.get("nombre", "")[:25],
                    "Beneficiarios": n_beneficiarios,
                    "Total_Despachos": 0,
                    "Total_Etapas": 0,
                    "Primer_Despacho": None,
                    "Ultimo_Despacho": None,
                    "Dias_Perdidos": None,
                    "Dias_Actividad": None,
                    "Dias_Totales": None,
                    "Intensidad_Activa": None,
                    "Intensidad_Real": None,
                    "Desp_Semana": None,
                    "Desp_Mes": None,
                    "Prom_Semanal": None,
                    "Max_Semanal": None,
                    "Prom_Mensual": None,
                    "Max_Mensual": None,
                    "Desp_por_Benef": None,
                    "Etapas_por_Benef": None,
                    "Pct_Contrato_Usado": None
                })
                continue

            # Calcular métricas
            fecha_contrato = plazos.get("fecha_inicio")
            fecha_primer = desp_proy["Fecha"].min()
            fecha_ultimo = desp_proy["Fecha"].max()
            duracion_contrato = plazos.get("duracion_total") or plazos.get("duracion_original") or 1

            dias_perdidos = (fecha_primer - fecha_contrato).days if fecha_contrato else None
            dias_actividad = (fecha_ultimo - fecha_primer).days
            dias_totales = (fecha_ultimo - fecha_contrato).days if fecha_contrato else dias_actividad

            # Contar etapas (separadas por coma en Tipo_despacho)
            total_etapas = 0
            for _, d_row in desp_proy.iterrows():
                tipo = str(d_row.get("Tipo_despacho", ""))
                etapas = [e.strip() for e in tipo.split(",") if e.strip()]
                total_etapas += len(etapas)

            # Intensidades
            intensidad_activa = n_despachos / max(dias_actividad, 1)
            intensidad_real = n_despachos / max(dias_totales, 1)

            # Despachos por semana y mes (calculado)
            desp_semana = n_despachos / max(dias_totales / 7, 1)
            desp_mes = n_despachos / max(dias_totales / 30, 1)

            # Estadísticas por semana calendario
            desp_proy["Semana"] = desp_proy["Fecha"].dt.isocalendar().week.astype(str) + "-" + desp_proy["Fecha"].dt.year.astype(str)
            por_semana = desp_proy.groupby("Semana").size()
            prom_semanal = por_semana.mean() if len(por_semana) > 0 else 0
            max_semanal = por_semana.max() if len(por_semana) > 0 else 0

            # Estadísticas por mes calendario
            desp_proy["Mes"] = desp_proy["Fecha"].dt.to_period("M")
            por_mes = desp_proy.groupby("Mes").size()
            prom_mensual = por_mes.mean() if len(por_mes) > 0 else 0
            max_mensual = por_mes.max() if len(por_mes) > 0 else 0

            # Por beneficiario
            desp_por_benef = n_despachos / max(n_beneficiarios, 1)
            etapas_por_benef = total_etapas / max(n_beneficiarios, 1)

            # % contrato usado al último despacho
            pct_contrato = (dias_totales / duracion_contrato) * 100 if dias_totales else None

            resultados.append({
                "ID_proy": id_proy,
                "Nombre": plazos.get("nombre", "")[:25],
                "Beneficiarios": n_beneficiarios,
                "Total_Despachos": n_despachos,
                "Total_Etapas": total_etapas,
                "Primer_Despacho": fecha_primer.strftime("%d/%m/%Y") if pd.notna(fecha_primer) else None,
                "Ultimo_Despacho": fecha_ultimo.strftime("%d/%m/%Y") if pd.notna(fecha_ultimo) else None,
                "Dias_Perdidos": dias_perdidos,
                "Dias_Actividad": dias_actividad,
                "Dias_Totales": dias_totales,
                "Intensidad_Activa": round(intensidad_activa, 2),
                "Intensidad_Real": round(intensidad_real, 2),
                "Desp_Semana": round(desp_semana, 1),
                "Desp_Mes": round(desp_mes, 1),
                "Prom_Semanal": round(prom_semanal, 1),
                "Max_Semanal": int(max_semanal),
                "Prom_Mensual": round(prom_mensual, 1),
                "Max_Mensual": int(max_mensual),
                "Desp_por_Benef": round(desp_por_benef, 1),
                "Etapas_por_Benef": round(etapas_por_benef, 1),
                "Pct_Contrato_Usado": round(pct_contrato, 1) if pct_contrato else None
            })

        df = pd.DataFrame(resultados)

        # Ordenar por intensidad real (descendente)
        if "Intensidad_Real" in df.columns and len(df) > 0:
            df = df.sort_values("Intensidad_Real", ascending=False)

        return df


# === TEST ===
if __name__ == "__main__":
    from data_manager import DataManager

    dm = DataManager()
    engine = EtapasEngine(dm)

    print("=== Test EtapasEngine ===\n")

    # Probar configuración
    print(f"Etapas configuradas: {len(engine.config.get('etapas', {}))}")
    print(f"Secuencia principal: {engine.config.get('secuencia_principal', [])}")

    # Probar con un proyecto
    try:
        proyectos = engine.get_proyectos_activos()
        print(f"\nProyectos activos: {len(proyectos)}")

        if len(proyectos) > 0:
            id_proy = proyectos.iloc[0]["ID_proy"]
            print(f"\nProbando con proyecto: {id_proy}")

            # Resumen
            resumen = engine.get_resumen_proyecto(id_proy)
            print(f"\nResumen del proyecto:")
            for k, v in resumen.items():
                print(f"  {k}: {v}")

            # Alertas
            alertas = engine.get_alertas_proyecto(id_proy)
            print(f"\nAlertas: {len(alertas)}")
            for a in alertas[:3]:
                print(f"  [{a['prioridad']}] {a['nombre']}: {a['mensaje']}")

            # Predicciones
            predicciones = engine.get_prediccion_despachos(id_proy)
            print(f"\nPróximos despachos: {len(predicciones)}")
            if len(predicciones) > 0:
                print(predicciones.head(3).to_string(index=False))

    except Exception as e:
        print(f"Error: {e}")

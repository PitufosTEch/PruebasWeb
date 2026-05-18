"""
Documentacion de tablas y columnas para el asistente de consultas.
Edita este archivo para mejorar las respuestas de Claude.

IMPORTANTE: Las FKs tienen variaciones de mayusculas/minusculas:
- ID_Proy vs ID_proy
- ID_Benef vs ID_benef

ESTRUCTURA GENERAL:
- Proyectos (1) -> Beneficiario (N): Un proyecto tiene muchos beneficiarios
- Beneficiario es la unidad central para: Ejecucion, Despacho, documentacion, Resumen_insp
"""

TABLA_DOCS = {
    # ==================== TABLAS PRINCIPALES ====================
    "Proyectos": {
        "descripcion": "Informacion general de proyectos de vivienda social (TABLA CENTRAL)",
        "pk": "ID_proy",
        "columnas": {
            "ID_proy": "PK - Identificador unico del proyecto (ej: P01, P02)",
            "Cod_obra": "Codigo de obra",
            "NOMBRE_PROYECTO": "Nombre descriptivo del proyecto",
            "COMUNA": "Comuna donde se ubica el proyecto",
            "PERIODO": "Periodo o ano del proyecto",
            "estado_general": "Estado: En ejecucion, Terminado, Pendiente",
            "Encargado": "FK->usuarios - Usuario encargado",
            "Jefe_ob1": "FK->usuarios - Jefe de obra 1",
            "Jefe_ob_2": "FK->usuarios - Jefe de obra 2",
            "Social": "FK->usuarios - Encargado social",
            "TIPOLOGIA 1": "Tipologia de vivienda 1",
        }
    },
    "Beneficiario": {
        "descripcion": "Datos de beneficiarios (familias) que reciben viviendas. Un proyecto tiene muchos beneficiarios.",
        "pk": "ID_Benef",
        "columnas": {
            "ID_Benef": "PK - Identificador unico del beneficiario (numerico: 1, 2, 3...)",
            "ID_Proy": "FK->Proyectos (MAYUSCULA en Proy) - Valores: P01, P02...",
            "Cod_Obra": "Codigo de obra",
            "Estado": "Estado del beneficiario: Ejecucion, Preparacion, Eliminado, Subsidiado, Terminado",
            "Habil para construir": "Boolean - Si puede iniciar construccion",
            "steelframe": "Boolean - Si es construccion steel frame",
            "NOMBRES": "Nombres del beneficiario",
            "APELLIDOS": "Apellidos del beneficiario",
            "RUT": "RUT del beneficiario",
            "COMUNA": "Comuna de residencia",
            "DIRECCION_RSH": "Direccion segun Registro Social de Hogares",
        }
    },
    "Ejecucion": {
        "descripcion": "Registro de avance de ejecucion de obras por beneficiario",
        "pk": "IDU_E",
        "columnas": {
            "IDU_E": "PK - Identificador unico de ejecucion",
            "ID_benef": "FK->Beneficiario (MINUSCULA en benef!)",
            "ID_Proy": "FK->Proyectos (MAYUSCULA en Proy)",
            "Fecha_creacion": "Fecha de creacion del registro",
            "F_INICIO": "Fecha de inicio de obras",
            "E_Obra": "Estado de la obra (ej: En fundacion, Radier, Terminada)",
            "C_Carp": "Control carpinteria - estado/verificacion",
            "C_rad": "Control radier - estado/verificacion",
            "alerta_logist": "Alerta de logistica",
        }
    },
    "Levantamiento": {
        "descripcion": "Datos del levantamiento tecnico inicial del terreno",
        "pk": "IDU_L",
        "columnas": {
            "IDU_L": "PK - Identificador unico de levantamiento",
            "ID_Benef": "FK->Beneficiario (MAYUSCULA)",
            "ID_proy": "FK->Proyectos (MINUSCULA en proy!)",
            "Fecha": "Fecha del levantamiento",
            "Usuario": "Usuario que registro",
            "Creador": "FK->usuarios - Usuario creador",
            "COORDENADAS": "Coordenadas GPS del terreno",
            "N_ROL": "Numero de rol del terreno",
            "FUENTE_AGUA": "Fuente de agua potable",
            "Nom_APR": "FK->APR - Agua Potable Rural",
            "ELECTRICIDAD": "Situacion electrica",
            "ALCANT": "Situacion alcantarillado",
        }
    },

    # ==================== SISTEMA DE DESPACHOS ====================
    # Flujo: soldepacho (solicitud) -> Despacho (ejecutado)
    "soldepacho": {
        "descripcion": "Solicitudes de despacho de materiales (ANTES de ejecutar)",
        "pk": "IDU_soldesp",
        "columnas": {
            "IDU_soldesp": "PK - Identificador unico de solicitud",
            "ID_Benef": "FK->Beneficiario",
            "ID_proy": "FK->Proyectos",
            "Tipo_despacho": "Tipo de despacho solicitado",
            "Fecha": "Fecha de solicitud",
            "Estado": "Estado de la solicitud: Pendiente, Aprobado, Despachado",
        }
    },
    "Despacho": {
        "descripcion": "Registro de despachos de materiales EJECUTADOS a beneficiarios. Clave para control de etapas.",
        "pk": "IDU_desp",
        "columnas": {
            "IDU_desp": "PK - Identificador unico del despacho",
            "ID_Benef": "FK->Beneficiario (MAYUSCULA)",
            "ID_proy": "FK->Proyectos (MINUSCULA en proy!)",
            "Cod_obra": "Codigo de obra",
            "usuario": "Usuario que registro el despacho",
            "Tipo_despacho": "Tipo de despacho - CLAVE para identificar etapa (fundacion, radier, 1era, 2da, ventanas, etc.)",
            "Tipo_pendiente": "Tipo de pendiente asociado",
            "Fecha": "Fecha del despacho - CLAVE para calcular tiempos entre etapas",
            "Guia": "Numero de guia de despacho",
            "Camion": "Identificacion del camion",
            "Chofer": "Nombre del chofer",
            "Observaciones": "Descripcion detallada de materiales despachados",
            "Estado": "Estado del despacho: Pendiente, Completado, Cancelado",
        },
        "etapas_construccion": {
            "01_FUNDACIONES": "Despacho de materiales para fundaciones",
            "04_RADIER": "Despacho de materiales para radier",
            "02_1ERA_ETAPA": "Despacho de 1era etapa (estructura)",
            "28_VENTANAS": "Despacho de ventanas (CRITICO - max 7 dias)",
            "03_2DA_ETAPA": "Despacho de 2da etapa (terminaciones)",
            "07_CERAMICO_PISO": "Despacho de ceramicos piso",
            "08_CERAMICO_MURO": "Despacho de ceramicos muro",
            "13_GASFITERIA": "Despacho de gasfiteria"
        }
    },
    "Pendientes": {
        "descripcion": "Pendientes de obra - materiales o trabajos pendientes por entregar/completar",
        "pk": "IDU_pend",
        "columnas": {
            "IDU_pend": "PK - Identificador unico",
            "ID_Benef": "FK->Beneficiario",
            "ID_proy": "FK->Proyectos",
            "Tipo_pendiente": "Tipo de pendiente",
            "Descripcion": "Descripcion del pendiente",
            "Estado": "Estado: Pendiente, En proceso, Resuelto",
        }
    },

    # ==================== DOCUMENTACION ====================
    "documentacion": {
        "descripcion": "Control de documentacion legal y administrativa por beneficiario",
        "pk": "IDU_docs",
        "columnas": {
            "IDU_docs": "PK - Identificador unico",
            "ID_proy": "FK->Proyectos (MINUSCULA!)",
            "ID_benef": "FK->Beneficiario (MINUSCULA!)",
            "IDU_L": "FK->Levantamiento",
            "carnet": "Archivo carnet de identidad",
            "contrato": "Archivo contrato firmado",
            "C_RSH": "Certificado Registro Social de Hogares",
            "C_ahorro": "Certificado de ahorro",
            "C_permiso": "Permiso de edificacion",
            "C_recepcion": "Recepcion municipal",
            "C_dominio": "Certificado de dominio",
            "C_inhab": "Certificado de inhabitabilidad",
        }
    },

    # ==================== INSPECCIONES Y AVANCE ====================
    "Resumen_insp": {
        "descripcion": "Resumen CONSOLIDADO de inspecciones - avance por partida (un registro por beneficiario)",
        "pk": "ID_U",
        "columnas": {
            "ID_U": "PK - Identificador unico",
            "ID_Benef": "FK->Beneficiario",
            "Nombre": "Nombre del beneficiario",
            "Proyecto": "Nombre del proyecto",
            "marcador": "Marcador de avance general (numerador)",
            "total_marcador": "Total del marcador (denominador) - Avance = marcador/total_marcador*100",
            "T_A_Fundacion": "Avance fundacion (% 0-100)",
            "T_A_Radier": "Avance radier (% 0-100)",
            "T_A_E_Tabiques": "Avance tabiques (% 0-100)",
            "T_A_E_Techumbre": "Avance techumbre (% 0-100)",
            "T_A_Cubierta": "Avance cubierta (% 0-100)",
            "T_A_vent": "Avance ventanas (% 0-100)",
        }
    },
    "res_insp_precal": {
        "descripcion": "Inspecciones detalladas de precalificacion - antes de aprobar etapas",
        "pk": "ID_insp",
        "columnas": {
            "ID_insp": "PK - Identificador unico de inspeccion",
            "ID_Benef": "FK->Beneficiario",
            "ID_proy": "FK->Proyectos",
            "Fecha": "Fecha de la inspeccion",
            "Inspector": "Usuario inspector",
            "Resultado": "Resultado de la inspeccion",
        }
    },
    "cominsp": {
        "descripcion": "Comentarios de inspecciones - observaciones durante visitas",
        "pk": "ID_cominsp",
        "columnas": {
            "ID_cominsp": "PK - Identificador unico",
            "ID_Benef": "FK->Beneficiario",
            "ID_proy": "FK->Proyectos",
            "Fecha": "Fecha del comentario",
            "Usuario": "Usuario que comento",
            "Comentario": "Texto del comentario/observacion",
        }
    },

    # ==================== TABLAS FINANCIERAS ====================
    "Solpago": {
        "descripcion": "Solicitudes de pago - a nivel de BENEFICIARIO (pagos por avance de obra)",
        "pk": "IDU_solpago",
        "columnas": {
            "IDU_solpago": "PK - Identificador unico",
            "ID_Benef": "FK->Beneficiario",
            "ID_proy": "FK->Proyectos",
            "Monto": "Monto solicitado",
            "Estado": "Estado: Pendiente, Aprobado, Pagado",
            "Fecha": "Fecha de solicitud",
            "Tipo_pago": "Tipo de pago (etapa de obra)",
        }
    },
    "Montos": {
        "descripcion": "Montos de subsidio asignados por BENEFICIARIO",
        "pk": "IDU_monto",
        "columnas": {
            "IDU_monto": "PK - Identificador unico",
            "ID_Benef": "FK->Beneficiario",
            "ID_proy": "FK->Proyectos",
            "Monto_subsidio": "Monto total del subsidio",
            "Monto_ahorro": "Monto de ahorro del beneficiario",
            "Monto_total": "Monto total (subsidio + ahorro)",
        }
    },
    "controlEEPP": {
        "descripcion": "Control de Entidades Patrocinantes - organizaciones que gestionan proyectos",
        "pk": "ID_EEPP",
        "columnas": {
            "ID_EEPP": "PK - Identificador unico",
            "ID_proy": "FK->Proyectos",
            "Entidad": "Nombre de la entidad patrocinante",
            "Estado": "Estado del control",
            "Fecha": "Fecha del registro",
        }
    },

    # ==================== POSTVENTA ====================
    "postventa": {
        "descripcion": "Reclamos y solicitudes POST-ENTREGA de vivienda",
        "pk": "ID_PV",
        "columnas": {
            "ID_PV": "PK - Identificador unico",
            "ID_Benef": "FK->Beneficiario",
            "ID_proy": "FK->Proyectos",
            "Fecha": "Fecha del reclamo",
            "Tipo": "Tipo de reclamo/solicitud",
            "Estado": "Estado: Pendiente, En proceso, Resuelto",
            "Descripcion": "Descripcion del problema",
        }
    },
    "postventa_detalle": {
        "descripcion": "Detalle de acciones/seguimiento de reclamos postventa",
        "pk": "ID_PV_det",
        "columnas": {
            "ID_PV_det": "PK - Identificador unico",
            "ID_PV": "FK->postventa",
            "Fecha": "Fecha de la accion",
            "Accion": "Accion realizada",
            "Usuario": "Usuario responsable",
        }
    },

    # ==================== TABLAS DE COMENTARIOS ====================
    "combenef": {
        "descripcion": "Comentarios/notas sobre beneficiarios",
        "pk": "ID_combenef",
        "columnas": {
            "ID_combenef": "PK",
            "ID_Benef": "FK->Beneficiario",
            "Comentario": "Texto del comentario",
            "Fecha": "Fecha",
            "Usuario": "Usuario que comento",
        }
    },
    "comproy": {
        "descripcion": "Comentarios/notas sobre proyectos",
        "pk": "ID_comproy",
        "columnas": {
            "ID_comproy": "PK",
            "ID_proy": "FK->Proyectos",
            "Comentario": "Texto del comentario",
            "Fecha": "Fecha",
            "Usuario": "Usuario que comento",
        }
    },
    "comdesp": {
        "descripcion": "Comentarios/notas sobre despachos",
        "pk": "ID_comdesp",
        "columnas": {
            "ID_comdesp": "PK",
            "ID_desp": "FK->Despacho",
            "Comentario": "Texto del comentario",
            "Fecha": "Fecha",
            "Usuario": "Usuario que comento",
        }
    },

    # ==================== CONFIGURACION ====================
    "usuarios": {
        "descripcion": "Usuarios del sistema",
        "pk": "email",
        "columnas": {
            "email": "PK - Email del usuario",
            "Nombre": "Nombre completo",
            "Rol": "Rol: Admin, Inspector, Coordinador, etc.",
            "activo": "Si el usuario esta activo",
        }
    },
    "Tipologias": {
        "descripcion": "Tipos de vivienda disponibles por proyecto",
        "pk": "ID_tipologia",
        "columnas": {
            "ID_tipologia": "PK - Identificador unico",
            "ID_proy": "FK->Proyectos",
            "Nombre": "Nombre de la tipologia",
            "Metros_cuadrados": "Metros cuadrados",
            "Descripcion": "Descripcion de la tipologia",
        }
    },
    "APR": {
        "descripcion": "Agua Potable Rural - servicios de agua",
        "pk": "ID_APR",
        "columnas": {
            "ID_APR": "PK",
            "Nombre": "Nombre del APR",
            "Comuna": "Comuna",
            "Contacto": "Informacion de contacto",
        }
    },
    "Partidas": {
        "descripcion": "Partidas de construccion (etapas de obra)",
        "pk": "ID_partida",
        "columnas": {
            "ID_partida": "PK",
            "Nombre": "Nombre de la partida (Fundacion, Radier, etc.)",
            "Orden": "Orden de ejecucion",
        }
    },
    "Materiales": {
        "descripcion": "Catalogo de materiales de construccion",
        "pk": "ID_material",
        "columnas": {
            "ID_material": "PK",
            "Nombre": "Nombre del material",
            "Unidad": "Unidad de medida",
            "Categoria": "Categoria del material",
        }
    },
}

# Relaciones entre tablas (para JOINs)
# NOTA: Manejar case sensitivity en columnas FK
RELACIONES = {
    # Beneficiario es central
    "Beneficiario->Proyectos": {
        "tabla_origen": "Beneficiario",
        "columna_fk": "ID_Proy",  # MAYUSCULA
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",  # minuscula
    },
    "Levantamiento->Beneficiario": {
        "tabla_origen": "Levantamiento",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "Levantamiento->Proyectos": {
        "tabla_origen": "Levantamiento",
        "columna_fk": "ID_proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "Ejecucion->Beneficiario": {
        "tabla_origen": "Ejecucion",
        "columna_fk": "ID_benef",  # minuscula!
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "Ejecucion->Proyectos": {
        "tabla_origen": "Ejecucion",
        "columna_fk": "ID_Proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "Despacho->Beneficiario": {
        "tabla_origen": "Despacho",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "Despacho->Proyectos": {
        "tabla_origen": "Despacho",
        "columna_fk": "ID_proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "soldepacho->Beneficiario": {
        "tabla_origen": "soldepacho",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "soldepacho->Proyectos": {
        "tabla_origen": "soldepacho",
        "columna_fk": "ID_proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "documentacion->Beneficiario": {
        "tabla_origen": "documentacion",
        "columna_fk": "ID_benef",  # minuscula!
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "documentacion->Proyectos": {
        "tabla_origen": "documentacion",
        "columna_fk": "ID_proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "Resumen_insp->Beneficiario": {
        "tabla_origen": "Resumen_insp",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "Solpago->Beneficiario": {
        "tabla_origen": "Solpago",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "Solpago->Proyectos": {
        "tabla_origen": "Solpago",
        "columna_fk": "ID_proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "Montos->Beneficiario": {
        "tabla_origen": "Montos",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "Pendientes->Beneficiario": {
        "tabla_origen": "Pendientes",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "postventa->Beneficiario": {
        "tabla_origen": "postventa",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "postventa_detalle->postventa": {
        "tabla_origen": "postventa_detalle",
        "columna_fk": "ID_PV",
        "tabla_destino": "postventa",
        "columna_pk": "ID_PV",
    },
    "Tipologias->Proyectos": {
        "tabla_origen": "Tipologias",
        "columna_fk": "ID_proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "combenef->Beneficiario": {
        "tabla_origen": "combenef",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
    "comproy->Proyectos": {
        "tabla_origen": "comproy",
        "columna_fk": "ID_proy",
        "tabla_destino": "Proyectos",
        "columna_pk": "ID_proy",
    },
    "cominsp->Beneficiario": {
        "tabla_origen": "cominsp",
        "columna_fk": "ID_Benef",
        "tabla_destino": "Beneficiario",
        "columna_pk": "ID_Benef",
    },
}

# Ejemplos de consultas utiles (actualizados con JOINs complejos)
EJEMPLOS_CONSULTAS = [
    # Consultas simples
    {
        "pregunta": "Cuantos proyectos hay por comuna?",
        "tablas": ["Proyectos"],
        "codigo": 'dm.get_table_data("Proyectos").groupby("COMUNA").size().reset_index(name="Cantidad")',
    },
    {
        "pregunta": "Beneficiarios del proyecto P01",
        "tablas": ["Beneficiario"],
        "codigo": 'dm.get_table_data("Beneficiario").query("ID_Proy == \'P01\'")[["ID_Benef", "NOMBRES", "APELLIDOS", "Estado"]]',
    },
    {
        "pregunta": "Beneficiarios por estado",
        "tablas": ["Beneficiario"],
        "codigo": 'dm.get_table_data("Beneficiario").groupby("Estado").size().reset_index(name="Cantidad")',
    },
    # Consultas de avance
    {
        "pregunta": "Avance promedio por proyecto",
        "tablas": ["Resumen_insp", "Beneficiario"],
        "codigo": 'dm.get_table_data("Resumen_insp").assign(avance=lambda x: x["marcador"]/x["total_marcador"]*100).groupby("Proyecto")["avance"].mean().reset_index(name="Avance_Promedio")',
    },
    {
        "pregunta": "Beneficiarios con avance menor al 50%",
        "tablas": ["Resumen_insp"],
        "codigo": 'dm.get_table_data("Resumen_insp").assign(avance=lambda x: x["marcador"]/x["total_marcador"]*100).query("avance < 50")[["ID_Benef", "Nombre", "Proyecto", "avance"]]',
    },
    # Consultas con JOIN
    {
        "pregunta": "Despachos por proyecto con nombre del proyecto",
        "tablas": ["Despacho", "Proyectos"],
        "codigo": 'dm.get_table_data("Despacho").merge(dm.get_table_data("Proyectos")[["ID_proy", "NOMBRE_PROYECTO"]], left_on="ID_proy", right_on="ID_proy").groupby("NOMBRE_PROYECTO").size().reset_index(name="Total_Despachos")',
    },
    {
        "pregunta": "Beneficiarios con documentacion incompleta (sin permiso)",
        "tablas": ["documentacion", "Beneficiario"],
        "codigo": 'dm.get_table_data("documentacion").query("C_permiso != C_permiso or C_permiso == \'\'").merge(dm.get_table_data("Beneficiario")[["ID_Benef", "NOMBRES", "APELLIDOS"]], left_on="ID_benef", right_on="ID_Benef")[["ID_benef", "NOMBRES", "APELLIDOS"]]',
    },
    {
        "pregunta": "Cantidad de despachos por beneficiario",
        "tablas": ["Despacho"],
        "codigo": 'dm.get_table_data("Despacho").groupby("ID_Benef").size().reset_index(name="Total_Despachos").sort_values("Total_Despachos", ascending=False)',
    },
    # Consultas financieras
    {
        "pregunta": "Total solicitudes de pago por proyecto",
        "tablas": ["Solpago"],
        "codigo": 'dm.get_table_data("Solpago").groupby("ID_proy").size().reset_index(name="Total_Solicitudes")',
    },
    # Consultas de postventa
    {
        "pregunta": "Reclamos postventa por proyecto",
        "tablas": ["postventa"],
        "codigo": 'dm.get_table_data("postventa").groupby("ID_proy").size().reset_index(name="Total_Reclamos")',
    },
]


def get_tabla_doc(tabla_nombre: str) -> dict:
    """Obtiene la documentacion de una tabla"""
    return TABLA_DOCS.get(tabla_nombre, {})


def get_all_tablas() -> list:
    """Lista todas las tablas documentadas"""
    return list(TABLA_DOCS.keys())


def get_columnas_descripcion(tabla_nombre: str) -> str:
    """Genera texto descriptivo de las columnas de una tabla"""
    doc = TABLA_DOCS.get(tabla_nombre, {})
    if not doc:
        return "Sin documentacion"

    lines = [f"**{tabla_nombre}**: {doc.get('descripcion', '')}"]
    lines.append(f"PK: `{doc.get('pk', 'N/A')}`")
    for col, desc in doc.get("columnas", {}).items():
        lines.append(f"- `{col}`: {desc}")
    return "\n".join(lines)


def get_prompt_context() -> str:
    """Genera contexto para el prompt de Claude"""
    context = ["## DOCUMENTACION DE TABLAS:\n"]

    # Agrupar por categoria
    categorias = {
        "PRINCIPALES": ["Proyectos", "Beneficiario", "Ejecucion", "Levantamiento"],
        "DESPACHOS": ["soldepacho", "Despacho", "Pendientes"],
        "DOCUMENTACION": ["documentacion"],
        "INSPECCIONES": ["Resumen_insp", "res_insp_precal", "cominsp"],
        "FINANCIERAS": ["Solpago", "Montos", "controlEEPP"],
        "POSTVENTA": ["postventa", "postventa_detalle"],
        "COMENTARIOS": ["combenef", "comproy", "comdesp"],
        "CONFIGURACION": ["usuarios", "Tipologias", "APR", "Partidas", "Materiales"],
    }

    for categoria, tablas in categorias.items():
        context.append(f"\n### {categoria}")
        for tabla in tablas:
            doc = TABLA_DOCS.get(tabla, {})
            if doc:
                context.append(f"\n**{tabla}** (PK: {doc.get('pk', '?')}): {doc.get('descripcion', '')}")
                for col, desc in list(doc.get("columnas", {}).items())[:8]:  # Limitar columnas
                    context.append(f"  - {col}: {desc}")
                if len(doc.get("columnas", {})) > 8:
                    context.append(f"  - ... y {len(doc.get('columnas', {})) - 8} columnas mas")

    # Agregar relaciones importantes
    context.append("\n## RELACIONES CLAVE (para JOINs):")
    context.append("- Proyectos (1) -> Beneficiario (N): Un proyecto tiene muchos beneficiarios")
    context.append("- CUIDADO con case sensitivity:")
    context.append("  - Beneficiario.ID_Proy (mayuscula) -> Proyectos.ID_proy (minuscula)")
    context.append("  - documentacion.ID_benef (minuscula) -> Beneficiario.ID_Benef (mayuscula)")
    context.append("- Para JOINs usar: merge(df1, df2, left_on='col1', right_on='col2')")

    return "\n".join(context)


def get_relacion(tabla_origen: str, tabla_destino: str) -> dict:
    """Obtiene la relacion entre dos tablas"""
    key = f"{tabla_origen}->{tabla_destino}"
    return RELACIONES.get(key, {})


def get_join_columns(tabla1: str, tabla2: str) -> tuple:
    """Retorna las columnas para hacer JOIN entre dos tablas"""
    rel = get_relacion(tabla1, tabla2)
    if rel:
        return (rel["columna_fk"], rel["columna_pk"])
    # Intentar relacion inversa
    rel = get_relacion(tabla2, tabla1)
    if rel:
        return (rel["columna_pk"], rel["columna_fk"])
    return (None, None)

# SCRaices-LLM

Sistema interno de SCRaices para:
1. Analizar datos de construcción de viviendas (lectura desde Google Sheets).
2. Generar reportes (PDF/Excel) de obra, postventa, RRHH, etc.
3. Servir un dashboard de control de obra en GitHub Pages.
4. Respaldar la base Firebase del dashboard.

> Este archivo es la guía operativa del proyecto. Si trabajas desde Claude Code Online, léelo primero — junto con los `.md` anidados a los que apunta.

---

## Estructura del proyecto

```
SCRaices-LLM/
├── app/                  Scripts Python (data + reportes + chat LLM)
│   ├── config.example.py    plantilla de config (config.py real esta en .gitignore)
│   ├── config.py            local, NO commitear (APPSHEET_API_KEY, SPREADSHEET_ID)
│   ├── data_manager.py      conexion a Google Sheets via service account
│   ├── reportes_engine.py   genera reportes (resumen beneficiario, MO, etc.)
│   ├── generar_*.py         scripts puntuales para cada tipo de reporte
│   ├── chat_assistant.py    interfaz chat con Claude API sobre los datos
│   ├── etapas_engine.py     logica de % avance y estados de etapas
│   ├── RELACIONES_TABLAS.md doc de la BD (referenciar antes de query)
│   └── schema.json          schema parseado de AppSheet
│
├── dashboard/            Dashboard publicado en GitHub Pages
│   ├── index_live_v3.html   produccion (link publico)
│   ├── dashboard-obras.jsx  componente React principal
│   ├── panel_coordinador.html
│   ├── te1-set.js           dataset precalculado de TE1 (embebido)
│   ├── sw.js, manifest.json PWA
│   └── mockup_*.html        prototipos
│
├── apps_script/          Google Apps Script (corre en script.google.com)
│   ├── EmailReport.gs       reporte semanal por mail
│   ├── FirebaseBackup.gs    backup automatico del RTDB (ver BACKUP_FIREBASE.md)
│   ├── BACKUP_FIREBASE.md   doc completa del sistema de backup
│   └── Code.gs              utilidades varias
│
├── portal/               Portal de proyecto (vista publica por proyecto/vivienda)
│   ├── index.html
│   ├── proyecto.html
│   └── vivienda.html
│
├── config/               Configuracion JSON
│   ├── etapas_config.json   dependencias y tiempos entre etapas
│   └── reportes_config.json
│
├── credentials/          [.gitignored] service_account.json de Google
├── output/               [.gitignored] PDFs generados (regenerables)
└── reportes/             Plantillas y assets de reportes
```

---

## Lógica de negocio crítica

### % Avance de vivienda (`etapas_engine.py`)

- Tabla `Ejecucion` en AppSheet: **cada fila es un DELTA, no un snapshot**. Para obtener el total acumulado de una vivienda hay que SUMAR todas sus filas.
- Flujo de una etapa: `Despacho` → `Ejecucion (inspeccion del maestro)` → `Solpago (pago al maestro)`.
- **% Vivienda** = suma ponderada de 28 partidas A_* (pesos en `Application Documentation.html` original de AppSheet, no commiteado).
- **% Recepción Conforme (RC)** = promedio simple de 19 partidas AB_*.
- **% Habilitación** = nodo único A_Habilitacion.
- **% Total = 70% · %Viv + 25% · %RC + 5% · %Hab**.
- ⚠ La columna `A_Art_Baño` usa `ñ` (Unicode `ñ`). NO usar `A_Art_Bano`, no matchea.

### Estados visuales en el dashboard

- 🟢 Verde: < 7 días desde última solicitud
- 🟡 Amarillo: 7-14 días
- 🔴 Rojo: > 14 días sin solicitud

### Cadena principal de tablas

`Proyectos` → `Beneficiario` → `Ejecucion` / `Solpago` / `Despacho` / `documentacion` / `postventa`

⚠ Atención mayúsculas: `Beneficiario.ID_Proy` (P mayúscula) vs `Solpago.ID_proy` (p minúscula). Casi nunca se notan en logs.

Detalle completo del esquema y patrones de consulta: ver `app/RELACIONES_TABLAS.md`.

---

## Conexión a datos

### Google Sheets (lectura, vía service account)

```python
from data_manager import DataManager
dm = DataManager()
df = dm.get_table_data('Beneficiario')   # devuelve DataFrame
```

Requiere `credentials/service_account.json` con permisos al Sheet. Spreadsheet ID y rutas en `app/config.py` (local).

### AppSheet REST API (descarga de documentos)

Para PDFs y fotos almacenados en AppSheet (carnets, contratos, fotos de inspección, comprobantes de pago):

1. POST a `{API_URL}/{tabla}/Action` con `Action: Find` y header `ApplicationAccessKey`.
2. La respuesta devuelve URLs firmadas (con signature, temporales) por cada columna File/Image.
3. GET a esa URL descarga el archivo.

Tablas con documentos relevantes: `documentacion`, `Ejecucion`, `Levantamiento`, `postventa`, `Solpago`, `Reg_pago_ex_det`.

⚠ Timeout mínimo 60s — la API es lenta.

### Firebase Realtime Database (lectura y escritura desde el dashboard)

URL: `https://scraices-dashboard-default-rtdb.firebaseio.com`

Nodos editables:
- `grupos` — agrupación de casas + asignación de capataz
- `observaciones`, `actividades`, `consultas`, `muestras_hormigon`, `sugerencias`
- `proyectos_terminados`, `ocultados`
- `resumen_comentarios/{pId}/{obsId}`

Las API keys del lado web (`firebaseConfig.apiKey`) en el HTML son intencionalmente públicas — el control real son las Security Rules del proyecto Firebase.

⚠ **Reglas actuales: abiertas** (lectura/escritura sin auth). Esto es una vulnerabilidad pendiente de endurecer. El sistema de backup (ver más abajo) funciona gracias a esto.

---

## Backup Firebase

Sistema automático instalado el 2026-05-17. Doc completa: **`apps_script/BACKUP_FIREBASE.md`**.

- Trigger diario 03:00 (hora Chile) → backup completo a Drive
- Health-check 09:00 → alerta si el último backup tiene > 26h
- Retención: 30 días + snapshot mensual permanente
- Restauración granular por nodo con `restaurarNodo()` (con simulador previo)

---

## Reportes disponibles

| # | Reporte | Archivo | Output |
|---|---|---|---|
| 1 | Análisis de Postventa | `app/generar_postventa_analisis.py` | `output/Analisis_Postventa_Regular_Completo.pdf` |
| 2 | Resumen Beneficiario | `reportes_engine.py::generar_resumen_beneficiario()` | PDF individual |
| 3 | Resumen Pago MO Grupo | `reportes_engine.py::generar_resumen_pago_mo_grupo()` | Excel 4 hojas |
| 4 | Análisis Comparativo MO | `reportes_engine.py::generar_analisis_comparativo_mo()` | PDF Base vs Real |
| 5 | Informe GG y Rendiciones | `app/generar_informe_gg.py` | PDF |
| 6 | Días de Ejecución | `app/generar_dias_ejecucion.py` | PDF comparativo |
| 7 | Tiempos entre Etapas | `app/generar_tiempos_etapas.py` | PDF 1era→2da Etapa por carpintero |

Comando típico: `cd app && python generar_<reporte>.py`.

**Estilo visual estándar de los PDFs**: escala de grises + rojo oscuro `#8C3232`, tipografía sin emojis (Unicode rompe en algunas fuentes), salto de página antes de tablas largas.

---

## Cómo levantar cada cosa

| Necesito... | Cómo |
|---|---|
| Generar un reporte | `cd SCRaices-LLM/app && python generar_<algo>.py` (requiere `config.py` y `credentials/` locales) |
| Editar el dashboard | Editar `dashboard/index_live_v3.html`, commit + push → GitHub Pages se actualiza solo |
| Probar el dashboard local | Abrir `dashboard/index_live_v3.html` directo en navegador (es estático) |
| Mandar reporte por mail | `apps_script/EmailReport.gs` corriendo en script.google.com |
| Backup manual de Firebase | En el Apps Script "SCRaices - Backup Firebase" → función `backupAhora` |
| Restaurar un nodo de Firebase | Ver `apps_script/BACKUP_FIREBASE.md` |
| Chatear sobre los datos | `cd SCRaices-LLM/app && python chat_assistant.py` (requiere `ANTHROPIC_API_KEY` en env) |

---

## Convenciones

- **Print en Windows**: NO usar caracteres Unicode (checkmark ✓, X ✗) — romp consola. Usar ASCII (`OK`, `FAIL`).
- **fpdf2**: ignorar DeprecationWarnings de `ln=`, son cosméticos.
- **Mensajes de commit**: `feat:`, `fix:`, `perf:`, `refactor:`, `docs:` (estilo Conventional Commits).
- **Comentarios en código**: inglés OK. Documentación y CLAUDE.md: español.

---

## Limitaciones conocidas

1. **Reglas de Firebase abiertas** — vulnerabilidad de privacidad (cualquiera con la URL del RTDB puede leer/escribir). Tarea pendiente: endurecer + agregar auth al script de backup.
2. **`Application Documentation.html` no está en el repo** — es el export original de AppSheet de 4MB. Si lo necesitas, regéneralo desde AppSheet con "Export documentation".
3. **`output/` regenerado** — los PDFs no se versionan. Cada quien los genera localmente.
4. **Backup granularidad 24h** — restaurar pierde los cambios del día.

---

## Archivos relacionados

- `apps_script/BACKUP_FIREBASE.md` — backup Firebase completo
- `app/RELACIONES_TABLAS.md` — esquema de BD detallado
- `Etapas.md` — definición de etapas y dependencias
- Repo: `https://github.com/PitufosTEch/PruebasWeb`
- Dashboard publicado: `https://pitufostech.github.io/PruebasWeb/SCRaices-LLM/dashboard/index_live_v3.html`

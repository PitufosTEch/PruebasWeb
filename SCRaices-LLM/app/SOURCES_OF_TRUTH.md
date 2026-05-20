# Fuentes de Verdad — Tab "Estado General"

Este documento registra **de dónde sale cada dato** que aparece en el tab "Estado General" del dashboard. Es de uso interno y privado al equipo — no se expone en el dashboard ni en los informes públicos.

Mantener sincronizado con el código de `SCRaices-LLM/dashboard/index_live_v3.html`.

---

## Resumen rápido

| Checkpoint en el informe | Fuente | Tabla / Nodo | Columna / Campo | Notas |
|---|---|---|---|---|
| **HPC** | AppSheet Sheet | `Beneficiario` | `Habil para construir` (sí/no) → flag `b.habil` | Si "Si"/"sí"/true/1 → prendido. Procesado en `index_live_v3.html` L441 |
| **TE1** | **Triple fuente** (OR logico) — ver § TE1 | (varias) | (varias) | Marca prendida si CUALQUIERA de las tres fuentes tiene dato |
| **V.AS** (Visita Inspector AS) | AppSheet Sheet | `Seguimiento` | matcher: `must=['visita','as']`, `not=['dom','f1','resol']` | Ver § Matching dinámico |
| **R.AS** (Resol. Aprob AS) | AppSheet Sheet | `Seguimiento` | matcher: `must=['resol','as']`, `not=['dom','f1']` | |
| **V.F1** (Visita F1) | AppSheet Sheet | `Seguimiento` | matcher: `must=['visita','f1']`, `not=['fecha','dom']` | |
| **F1** (Fecha F1) | AppSheet Sheet | `Seguimiento` | matcher: `must=['f1']`, `not=['visita','dom','tf','t1']` | |
| **Artef.** (Artefactado) | AppSheet Sheet | `Seguimiento` | matcher: `must=['artefact']` | |
| **Empalme** | AppSheet Sheet | `Seguimiento` | matcher: `must=['empalme']` | ⚠ Cuidado: el nombre `empalme` también existe en `Beneficiario` (campo cierre). En este tab se usa el de `Seguimiento`. |
| **V.DOM** (Visita DOM) | AppSheet Sheet | `Seguimiento` | matcher: `must=['visita','dom']`, `not=['fecha']` | |
| **F.V.DOM** (Fecha V. DOM) | AppSheet Sheet | `Seguimiento` | matcher: `must=['fecha','dom']`, `not=['recep']` | |
| **Recep.** (Recepción DOM, n° doc) | AppSheet Sheet | `Seguimiento` | matcher: `must=['recep']`, `not=['fecha']` | Valor esperado: número/string del documento |
| **F.Recep** (Fecha Recepción) | AppSheet Sheet | `Beneficiario` (preferente) o `Seguimiento` | `F_R_dom` en Beneficiario → flag `b.fecha_recepcion`; fallback a `Seguimiento` matcher `must=['fecha','recep']` | Si cualquiera de las dos está → prendido |
| ❌ **T1** | — | — | — | **Eliminado por solicitud del usuario** (2026-05-19). |

---

## Datos derivados (no checkpoints)

| Dato en el informe | Fuente | Detalle |
|---|---|---|
| **% Avance** (columna "% Av") | AppSheet Sheet `Ejecucion` | Cada fila es un delta. Suma acumulada por ID_Benef → `INSPECCIONES_DATA[id].pct_total`. Fórmula: `0.70·%Viv + 0.25·%RC + 0.05·%Hab`. Detalle en `app/etapas_engine.py` y CLAUDE.md. |
| **M.O. Pagado (acum, Aprob.)** | AppSheet Sheet `Solpago` | Filtrado al cargar: solo filas con `Estado` que incluya "aprobad" (case-insensitive). Suma de `monto` por ID_Benef. Procesado en `index_live_v3.html` L624. |
| **Ritmo Pagos M.O. mensual** | Mismo `Solpago` filtrado | Agrupación por `YYYY-MM` de la columna `fecha`/`Fecha`. Últimos 12 meses. |
| **Ritmo Despachos mensual** | AppSheet Sheet `Despacho` | Conteo de filas por mes. **TEMPORAL (v1):** es proxy de actividad; pendiente reemplazar por % avance real de `Ejecucion` deltas. |
| **Tipología** (subtítulo del beneficiario) | AppSheet Sheet `Tipologias` + `Beneficiario.Tipologia Vivienda` / `Tipologia RC` | Concatena familia + dormitorios + plantas + caracterización. |
| **Estado General** (texto en expandido) | Calculado | `getEstadoGeneral(estadoEtapas)` — basado en días desde última solicitud. |
| **Comentarios destacados** | Firebase RTDB | Solo los marcados con estrella. Ver § Filtro por estrella. |
| **Grupos + Capataz** (headers de bloques) | Firebase RTDB | Nodo `grupos/{proyectoId}` con `[{ id, nombre, capataz, beneficiarios:[ID_Benef,...] }]`. Editable desde tab "Configuración". |

---

## TE1 — triple fuente (OR lógico)

A pedido del usuario (2026-05-19), el checkpoint **TE1** se considera prendido si **cualquiera** de estas tres fuentes tiene dato:

### Fuente 1: Set pre-calculado (legacy)
- Archivo: `dashboard/te1-set.js`
- Variable global: `BENEF_CON_TE1` (Set de IDs)
- Origen: extracción manual del Sheet TE1 separado (`1QCoIpiQKV1LB6XgUwwoC_e4crRD5mIANLxon9ZVwsg8`, `Hoja 1`)
- Se regenera offline cuando se actualiza el TE1

### Fuente 2: Perfil del beneficiario (PDF en AppSheet)
- Tabla: `Beneficiario` de AppSheet
- Columna: detectada dinámicamente — cualquier columna cuyo nombre normalizado contenga `te1` (excluyendo `te10`, `te11`, `te12`)
- Valor: cualquier cosa no vacía (`nan`/`no`/`false` se ignoran). En la práctica es el campo donde el operador sube el PDF del documento TE1
- Procesado en `index_live_v3.html` ~L500
- Log en consola: `[LIVE] TE1: columnas detectadas en Beneficiario: [...]` y `[LIVE] TE1 desde perfil Beneficiario: N`

### Fuente 3: Tabla Seguimiento Cierre de Obras
- Tabla: `Seguimiento`
- Columna: detectada dinámicamente (regla `must=['te1'], not=['te10','te11','te12']`)
- Procesado tras el procesamiento de Seguimiento (~L770)
- Log en consola: `[LIVE] TE1 desde Seguimiento: N. Total con TE1: X/Y`

### Debug
Cada beneficiario tiene `_te1_sources = { embedded, profile, seguimiento }` (booleanos por fuente) para inspeccionar de dónde vino el match.

---

## Comentario corto por grupo (tab Viviendas)

Agregado el 2026-05-19. Cada grupo (capataz) puede tener un comentario corto de estado (ej: "cubierta terminada, falta DOM").

- Persiste en Firebase como campo `comentario` del objeto grupo, dentro del nodo `grupos/{proyectoId}`
- Estructura: `grupos/{proyectoId} = [{ id, nombre, capataz, beneficiarios, comentario }]`
- Editable inline en el `GrupoHeader` del tab Viviendas
- **Visible también en el informe Estado General** como "Nota del Coordinador" (banner ámbar debajo del header de cada grupo, siempre visible aunque el grupo esté colapsado). Cambio a partir de 2026-05-19 por pedido del usuario: es información compartible para que el público externo entienda el juicio del coordinador sobre el avance de cada grupo geográfico.
- Componente: `GrupoHeader` en `index_live_v3.html` ~L1810, callback `onUpdateComentario` → `actualizarComentarioGrupo` en App (~L4180)
- Max 200 caracteres, plaintext

---

## Matching dinámico de columnas (Seguimiento)

La tabla `Seguimiento` de AppSheet puede tener nombres de columna ligeramente distintos según versión (mayúsculas/tildes/puntos/guiones bajos). El dashboard usa **matching normalizado**:

```js
normCol("Visita AS")        // → "visitaas"
normCol("F_visita_AS")      // → "fvisitaas"
normCol("Fecha Visita AS")  // → "fechavisitaas"
```

Una columna matchea un checkpoint si su forma normalizada contiene **todos** los `must` y **ninguno** de los `not`.

Reglas activas (alineadas con el código en `index_live_v3.html` ~L660):

```js
SEG_RULES = {
  visita_as:     { must: ['visita', 'as'],   not: ['dom', 'f1', 'resol'] },
  resol_as:      { must: ['resol',  'as'],   not: ['dom', 'f1'] },
  visita_f1:     { must: ['visita', 'f1'],   not: ['fecha', 'dom'] },
  fecha_f1:      { must: ['f1'],             not: ['visita', 'dom', 'tf', 't1'] },
  artefactado:   { must: ['artefact'],       not: [] },
  empalme:       { must: ['empalme'],        not: [] },
  visita_dom:    { must: ['visita', 'dom'],  not: ['fecha'] },
  fecha_v_dom:   { must: ['fecha', 'dom'],   not: ['recep'] },
  recepcion_dom: { must: ['recep'],          not: ['fecha'] },
  fecha_recep:   { must: ['fecha', 'recep'], not: [] },
  obs:           { must: ['obs'],            not: ['vac'] }
};
```

**Para verificar qué columna real matcheó cada checkpoint:**
- Abrir consola del navegador (F12) en el dashboard
- Leer logs `[LIVE] Match por checkpoint: {...}`
- O abrir el **panel "Diagnóstico fuente Seguimiento"** en el tab Estado General (muestra match en vivo)

Si un matcher resuelve a la columna incorrecta o a `null`, ajustar `SEG_RULES` y este documento.

---

## Filtro por estrella (comentarios públicos)

El tab "Estado General" se comparte fuera del depto, por lo tanto:

- Las **observaciones por vivienda** se guardan en Firebase RTDB en `observaciones/{ID_Benef}/[{id, texto, fecha}, ...]`
- Cada observación tiene un botón ⭐ (estrella) en el tab "Viviendas"
- Al hacer click, se crea/borra un registro en `resumen_comentarios/{ID_Proy}/{obs.id}` en Firebase
- **El tab "Estado General" SOLO muestra los comentarios cuyo `obs.id` está en `resumen_comentarios[ID_Proy]`** (los demás son privados)

Implementación:
- Toggle de la estrella: `index_live_v3.html` L1627–L1644 (componente `ViviendaCard`)
- Carga de `resumenComentarios` desde Firebase: L3766
- Filtrado en Estado General: `EstadoGeneralTab.datos` memo (~L2959), variable `starredIds` y `obsPublicas`

**Excluidos explícitamente** del informe público (datos internos operativos):
- `Beneficiario.Observacion ` (con espacio al final, campo crudo AppSheet)
- `Seguimiento.obs` (observaciones del operador AS)
- Comentarios de Firebase **sin estrella**

---

## Tablas AppSheet leídas

Definidas en `index_live_v3.html` L234 (`TABLES_TO_FETCH`). El Apps Script (`apps_script/Code.gs`) las expone vía endpoint `?tables=...`.

Endpoint Apps Script actual:
```
https://script.google.com/macros/s/AKfycbx_mSt3xEeXZYn7R2fkt5drp3Pfllxdj71tJo0-2iSqW28OAgwgpzoH_2NI_erM5yB-/exec
```

Lista completa que se descarga:
- `Proyectos`, `Beneficiario`, `Tipologias`, `Maestros`, `controlBGB`, `controlEEPP`, **`Seguimiento`** (lote 1)
- `Despacho`, `soldepacho`, `Tabla_pago` (lote 2)
- `Ejecucion`, `Solpago` (lote 3)
- `combenef` (lote 4 - comentarios)

Para listar todas las hojas reales del Sheet (útil cuando el nombre de la hoja `Seguimiento` no matchea):
```
GET {endpoint}?action=manifest
→ { "tables": {"Proyectos": 312, "Beneficiario": 307, ...}, "timestamp": "..." }
```

---

## Historial de cambios

| Fecha | Cambio | Quién |
|---|---|---|
| 2026-05-19 | Doc creada. Eliminado checkpoint T1. Matcher de columnas Seguimiento reescrito a normalización + keywords (mustHave/mustNotHave) para tolerar variantes AppSheet. | Claude (a pedido del usuario) |
| 2026-05-19 | TE1 ampliado a triple fuente (set embebido + PDF en perfil Beneficiario + columna en Seguimiento). Nueva regla de match `te1` en `SEG_RULES`. Comentario corto editable a nivel grupo persistido en Firebase (`grupos/{pId}/[].comentario`). | Claude (a pedido del usuario) |
| 2026-05-19 | Nota del coordinador (comentario por grupo) ahora se muestra también en el informe Estado General como banner ámbar. | Claude (a pedido del usuario) |
| 2026-05-19 | Matcher de Seguimiento ampliado: cada checkpoint acepta múltiples alternativas (must/not), cubriendo variantes abreviadas tipo `V_AS`, `F_V_AS`, `F_R_AS`, `V_F1`, etc. — no solo nombres con palabras completas. Fetch ahora prueba 4 nombres de tabla (`Seguimiento`, `Seguimiento Cierre de Obras`, `Seguimiento_Cierre`, `SeguimientoCierre`). Debug panel: muestra tabla usada, valor de muestra por checkpoint, fila completa, botón Copiar diagnóstico. | Claude (a pedido del usuario tras detectar que casos como Natalie Aguirre y Rudes Collihuin con datos reales no se reflejaban) |
| 2026-05-19 | **Hallazgo crítico:** existen DOS hojas en el Sheet — `Seguimiento` (1 fila vieja legacy P01) y `Seguimiento Cierre de Obras` (la real con muchas filas). El selector ahora **elige por mayor cantidad de filas**, no por orden. Reglas SEG_RULES corregidas a los nombres reales detectados: `V_acsan`, `R_aprobsan`, `Artef_elect`, `R_rdom`. Debug panel ahora muestra reporte de candidatas (cuántas filas y errores por cada nombre probado). | Claude (tras ver el sample real de la hoja) |

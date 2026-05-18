# Backup Firebase SCRaices

Sistema de respaldo automático del Realtime Database `scraices-dashboard-default-rtdb`.

## Qué respalda

Todo el árbol del RTDB (nodos editables del dashboard):

| Nodo | Para qué sirve |
|---|---|
| `grupos` | Agrupación de casas por proyecto |
| `observaciones` | Observaciones por proyecto |
| `actividades` | Actividades por vivienda |
| `consultas` | Consultas registradas |
| `muestras_hormigon` | Muestras de hormigón |
| `sugerencias` | Sugerencias enviadas desde el dashboard |
| `proyectos_terminados` | Marca manual de cierre |
| `ocultados` | Items ocultados de la vista |
| `resumen_comentarios/{pId}/{obsId}` | Resumen de comentarios |

NO respalda Google Sheets ni AppSheet — esos viven en otro lado y solo se leen.

## Dónde vive

- **Código**: `apps_script/FirebaseBackup.gs` (en este repo)
- **Proyecto Apps Script**: `script.google.com` → "SCRaices - Backup Firebase" (cuenta `aespinoza@scraices.cl`)
- **Carpeta de backups en Drive**: `Backups_Firebase_SCRaices/` en la raíz del Drive del usuario
  - `diario/firebase_YYYY-MM-DD_HH-mm.json` (retención 30 días)
  - `mensual/firebase_YYYY-MM-DD.json` (un snapshot del día 1, permanente)

## Cuándo corre

- **03:00 hora Chile (`America/Santiago`)** → `backupDiario()` ejecuta el respaldo + envía mail OK a `aespinoza@scraices.cl`
- **09:00 hora Chile** → `verificarSalud()` revisa que el último backup tenga < 26h, si no manda alerta

## Instalación inicial (ya hecha 2026-05-17)

Si hay que reinstalar (cuenta nueva, script perdido, etc.):

1. Abrir `https://script.google.com` con cuenta `aespinoza@scraices.cl`
2. Nuevo proyecto → nombrarlo `SCRaices - Backup Firebase`
3. Copiar el contenido completo de `FirebaseBackup.gs` y pegar en el editor
4. Guardar (Ctrl+S)
5. Seleccionar función `instalar` → ▶ Ejecutar
6. Autorizar permisos (Drive + Mail + UrlFetch + Triggers): cuenta → Avanzado → Permitir
7. Verificar en logs: "Backup manual OK ..." y "Trigger ... creado"

## Cómo restaurar

### Restauración parcial (caso común)

Cuando se rompió UN nodo y los demás tienen cambios legítimos:

1. En el editor de Apps Script, ejecutar `listarBackups()` para ver disponibles
2. (Opcional pero recomendado) Editar `simularRestaurarNodo()`:
   ```javascript
   var NOMBRE_BACKUP = 'firebase_2026-05-17_03-00.json';
   var NODO          = 'grupos';
   ```
   Guardar y ejecutar `simularRestaurarNodo` — valida todo sin escribir a Firebase
3. Si la simulación pasa, editar `restaurarNodo()` con los mismos valores y ejecutar
4. El script hace un `backupAhora()` antes del PUT, por si la restauración misma sale mal

Paths anidados válidos: `grupos`, `grupos/abc123`, `resumen_comentarios/PROY01`, `proyectos_terminados`.

### Restauración total

Cuando se perdió/corrompió toda la BD:

1. Editar `restaurarDesdeBackup()` con el nombre del archivo
2. Ejecutar — sobreescribe TODO el RTDB con el snapshot

## Notificaciones

| Asunto | Cuándo |
|---|---|
| `OK: Backup Firebase SCRaices DD/MM/YYYY HH:mm` | Cada día tras el backup de las 03:00 |
| `ALERTA: Backup Firebase SCRaices fallo` | El backup tiró excepción |
| `ALERTA: Backup Firebase SCRaices - desactualizado` | A las 09:00 el último backup tiene > 26h |
| `ALERTA: Backup Firebase SCRaices - sin backups` | La carpeta `diario/` está vacía |

Destinatario configurado en `EMAIL_ALERTAS` (constante al inicio de `FirebaseBackup.gs`).

## Limitaciones conocidas

1. **Granularidad de 24h**: cambios entre 03:00 y el incidente se pierden al restaurar. Si se necesita más fino, bajar el intervalo a cada N horas (Apps Script soporta triggers de minutos).
2. **Depende de reglas abiertas**: hoy el RTDB permite lectura/escritura sin auth — por eso el script funciona sin token. Si se endurecen las reglas (recomendado por seguridad), el script necesita un service account de Firebase. Tarea pendiente.
3. **El backup vive en el Drive del mismo usuario**: si la cuenta se compromete, el atacante también accede a los backups. Si se requiere defensa en profundidad, copiar mensualmente a otra cuenta / disco externo.

## Cómo desactivar temporalmente

En el editor: ejecutar `desinstalar()` (borra los triggers, NO borra los backups acumulados).

## Mantenimiento

- **Cambiar email de alertas**: editar `EMAIL_ALERTAS` en el .gs y volver a pegar en el editor
- **Cambiar retención**: editar `RETENCION_DIAS`
- **Cambiar hora del trigger**: editar `.atHour(3)` y `.atHour(9)` en `instalar()`, luego volver a ejecutar `instalar()` (limpia y recrea triggers)

/**
 * FirebaseBackup.gs
 *
 * Respaldo diario de Firebase Realtime Database (scraices-dashboard) a Google Drive.
 *
 * INSTALACION (una sola vez):
 *   1. Abrir https://script.google.com  ->  Nuevo proyecto
 *   2. Pegar este archivo completo
 *   3. Ejecutar la funcion  instalar()   y autorizar permisos
 *      Esto crea la carpeta de backups, hace un backup inmediato y
 *      programa el trigger diario a las 03:00 (hora Chile).
 *
 * MANTENIMIENTO:
 *   - listarBackups()         imprime los backups existentes
 *   - backupAhora()           backup manual (util antes de cambios riesgosos)
 *   - verificarSalud()        chequea que el ultimo backup tenga < 26h
 *   - restaurarDesdeBackup()  restaura TODA la BD desde un snapshot
 *   - restaurarNodo()         restaura SOLO un nodo (ej: grupos) preservando los demas
 *   - simularRestaurarNodo()  dry-run: valida todo el flujo sin tocar Firebase
 *   - desinstalar()           borra los triggers (no borra los backups)
 *
 * NOTIFICACIONES:
 *   - Backup OK     -> mail diario a EMAIL_ALERTAS
 *   - Backup fallo  -> mail con asunto "ALERTA: ..."
 *   - Sin backup en 26h -> mail con asunto "ALERTA: ..."  (corre 09:00)
 */

var FIREBASE_URL    = 'https://scraices-dashboard-default-rtdb.firebaseio.com';
var CARPETA_RAIZ    = 'Backups_Firebase_SCRaices';
var RETENCION_DIAS  = 30;
var EMAIL_ALERTAS   = 'aespinoza@scraices.cl';
var TZ              = 'America/Santiago';
var SALUD_HORAS_MAX = 26;  // si el ultimo backup tiene mas que esto, alerta

// ---------- Instalacion ----------

function instalar() {
  var folder = obtenerOCrearCarpetaRaiz();
  Logger.log('Carpeta raiz: ' + folder.getUrl());

  backupAhora();

  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    var fn = triggers[i].getHandlerFunction();
    if (fn === 'backupDiario' || fn === 'verificarSalud') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger('backupDiario')
    .timeBased()
    .atHour(3)
    .everyDays(1)
    .inTimezone(TZ)
    .create();
  ScriptApp.newTrigger('verificarSalud')
    .timeBased()
    .atHour(9)
    .everyDays(1)
    .inTimezone(TZ)
    .create();

  Logger.log('Trigger backupDiario      creado para las 03:00 ' + TZ);
  Logger.log('Trigger verificarSalud    creado para las 09:00 ' + TZ);
}

function desinstalar() {
  var triggers = ScriptApp.getProjectTriggers();
  var n = 0;
  for (var i = 0; i < triggers.length; i++) {
    var fn = triggers[i].getHandlerFunction();
    if (fn === 'backupDiario' || fn === 'verificarSalud') {
      ScriptApp.deleteTrigger(triggers[i]);
      n++;
    }
  }
  Logger.log('Triggers eliminados: ' + n + ' (los archivos de backup NO se borran)');
}

// ---------- Ejecucion ----------

function backupDiario() {
  try {
    var info = ejecutarBackup();
    var stats = aplicarRetencion();
    Logger.log('Backup OK: ' + info.path + ' (' + info.sizeKB + ' KB)');
    enviarMailExito(info, stats);
  } catch (e) {
    var msg = 'Error en backup Firebase SCRaices: ' + e.message + '\n\n' + e.stack;
    Logger.log(msg);
    try {
      MailApp.sendEmail(EMAIL_ALERTAS, 'ALERTA: Backup Firebase SCRaices fallo', msg);
    } catch (e2) {
      Logger.log('Tampoco se pudo mandar el mail de alerta: ' + e2.message);
    }
    throw e;
  }
}

function verificarSalud() {
  var raiz   = obtenerOCrearCarpetaRaiz();
  var diario = obtenerOCrearSubcarpeta(raiz, 'diario');
  var files  = diario.getFiles();

  var ultimo = null;
  while (files.hasNext()) {
    var f = files.next();
    if (!ultimo || f.getDateCreated() > ultimo.getDateCreated()) ultimo = f;
  }

  var ahora = new Date();
  if (!ultimo) {
    MailApp.sendEmail(EMAIL_ALERTAS,
      'ALERTA: Backup Firebase SCRaices - sin backups',
      'La carpeta ' + CARPETA_RAIZ + '/diario esta vacia. Revisa el Apps Script.');
    Logger.log('Sin backups en la carpeta - alerta enviada');
    return;
  }

  var horas = (ahora - ultimo.getDateCreated()) / 36e5;
  if (horas > SALUD_HORAS_MAX) {
    MailApp.sendEmail(EMAIL_ALERTAS,
      'ALERTA: Backup Firebase SCRaices - desactualizado',
      'El ultimo backup tiene ' + horas.toFixed(1) + 'h (limite: ' + SALUD_HORAS_MAX + 'h).\n' +
      'Archivo: ' + ultimo.getName() + '\n' +
      'URL: ' + ultimo.getUrl() + '\n\n' +
      'Revisa los triggers en script.google.com');
    Logger.log('ALERTA: ultimo backup hace ' + horas.toFixed(1) + 'h');
  } else {
    Logger.log('Salud OK: ultimo backup hace ' + horas.toFixed(1) + 'h (' + ultimo.getName() + ')');
  }
}

function enviarMailExito(info, stats) {
  var fecha = Utilities.formatDate(new Date(), TZ, 'dd/MM/yyyy HH:mm');
  var asunto = 'OK: Backup Firebase SCRaices ' + fecha;
  var cuerpo = '';
  cuerpo += 'Backup completado correctamente.\n\n';
  cuerpo += 'Fecha: ' + fecha + ' (' + TZ + ')\n';
  cuerpo += 'Tamano: ' + info.sizeKB + ' KB\n';
  cuerpo += 'Archivo: ' + info.path + '\n';
  cuerpo += 'Backups en retencion: ' + stats.totalDiarios + ' (limite ' + RETENCION_DIAS + ')\n';
  if (stats.eliminados > 0) cuerpo += 'Eliminados por retencion: ' + stats.eliminados + '\n';
  cuerpo += '\n--\nGenerado por FirebaseBackup.gs';
  MailApp.sendEmail(EMAIL_ALERTAS, asunto, cuerpo);
}

function backupAhora() {
  var info = ejecutarBackup();
  Logger.log('Backup manual OK: ' + info.path + ' (' + info.sizeKB + ' KB)');
  return info;
}

function ejecutarBackup() {
  var resp = UrlFetchApp.fetch(FIREBASE_URL + '/.json', {
    muteHttpExceptions: true,
    followRedirects: true
  });
  var code = resp.getResponseCode();
  if (code !== 200) {
    throw new Error('Firebase respondio HTTP ' + code + ': ' + resp.getContentText().substring(0, 300));
  }
  var contenido = resp.getContentText();
  if (!contenido || contenido === 'null') {
    throw new Error('Firebase devolvio vacio / null (revisa reglas de lectura)');
  }

  var ahora = new Date();
  var raiz   = obtenerOCrearCarpetaRaiz();
  var diario = obtenerOCrearSubcarpeta(raiz, 'diario');

  var stamp  = Utilities.formatDate(ahora, TZ, 'yyyy-MM-dd_HH-mm');
  var name   = 'firebase_' + stamp + '.json';
  var blob   = Utilities.newBlob(contenido, 'application/json', name);
  var file   = diario.createFile(blob);

  if (ahora.getDate() === 1) {
    var mensual = obtenerOCrearSubcarpeta(raiz, 'mensual');
    var stampM  = Utilities.formatDate(ahora, TZ, 'yyyy-MM-dd');
    mensual.createFile(Utilities.newBlob(contenido, 'application/json', 'firebase_' + stampM + '.json'));
  }

  return {
    path: file.getUrl(),
    sizeKB: Math.round(contenido.length / 1024)
  };
}

function aplicarRetencion() {
  var raiz   = obtenerOCrearCarpetaRaiz();
  var diario = obtenerOCrearSubcarpeta(raiz, 'diario');
  var files  = diario.getFiles();

  var lista = [];
  while (files.hasNext()) {
    var f = files.next();
    lista.push({ id: f.getId(), name: f.getName(), date: f.getDateCreated() });
  }
  lista.sort(function(a, b) { return b.date - a.date; });

  var eliminados = 0;
  for (var i = RETENCION_DIAS; i < lista.length; i++) {
    DriveApp.getFileById(lista[i].id).setTrashed(true);
    Logger.log('Retencion: enviado a papelera ' + lista[i].name);
    eliminados++;
  }
  return { totalDiarios: Math.min(lista.length, RETENCION_DIAS), eliminados: eliminados };
}

// ---------- Utilidades ----------

function obtenerOCrearCarpetaRaiz() {
  var it = DriveApp.getRootFolder().getFoldersByName(CARPETA_RAIZ);
  if (it.hasNext()) return it.next();
  return DriveApp.getRootFolder().createFolder(CARPETA_RAIZ);
}

function obtenerOCrearSubcarpeta(parent, nombre) {
  var it = parent.getFoldersByName(nombre);
  if (it.hasNext()) return it.next();
  return parent.createFolder(nombre);
}

function listarBackups() {
  var raiz   = obtenerOCrearCarpetaRaiz();
  var diario = obtenerOCrearSubcarpeta(raiz, 'diario');
  var files  = diario.getFiles();
  var lista  = [];
  while (files.hasNext()) {
    var f = files.next();
    lista.push({
      name: f.getName(),
      date: Utilities.formatDate(f.getDateCreated(), TZ, 'yyyy-MM-dd HH:mm'),
      sizeKB: Math.round(f.getSize() / 1024),
      url: f.getUrl()
    });
  }
  lista.sort(function(a, b) { return a.name < b.name ? 1 : -1; });
  Logger.log('Total backups diarios: ' + lista.length);
  for (var i = 0; i < lista.length; i++) {
    Logger.log(lista[i].date + '  ' + lista[i].sizeKB + ' KB  ' + lista[i].name);
  }
  return lista;
}

/**
 * Restaurar un backup completo a Firebase.
 *
 * USO MANUAL (no automatico - lo ejecutas tu cuando lo necesites):
 *   1. En listarBackups() ubica el archivo que quieres restaurar
 *   2. Copia su nombre exacto, ej: "firebase_2026-05-17_03-00.json"
 *   3. Edita la linea de NOMBRE_BACKUP abajo
 *   4. Ejecuta restaurarDesdeBackup()
 *
 * IMPORTANTE: PUT a la raiz SOBREESCRIBE todo el RTDB. Tomate un backupAhora()
 * INMEDIATAMENTE ANTES de restaurar, por si necesitas volver atras.
 */
function restaurarDesdeBackup() {
  var NOMBRE_BACKUP = 'firebase_YYYY-MM-DD_HH-mm.json';  // <-- EDITAR

  if (NOMBRE_BACKUP.indexOf('YYYY') >= 0) {
    throw new Error('Edita NOMBRE_BACKUP con el nombre exacto del archivo a restaurar');
  }

  var raiz   = obtenerOCrearCarpetaRaiz();
  var diario = obtenerOCrearSubcarpeta(raiz, 'diario');
  var it     = diario.getFilesByName(NOMBRE_BACKUP);
  if (!it.hasNext()) {
    it = obtenerOCrearSubcarpeta(raiz, 'mensual').getFilesByName(NOMBRE_BACKUP);
  }
  if (!it.hasNext()) throw new Error('No encontre el archivo: ' + NOMBRE_BACKUP);

  var contenido = it.next().getBlob().getDataAsString();
  Logger.log('Snapshot de seguridad ANTES de restaurar...');
  backupAhora();

  var resp = UrlFetchApp.fetch(FIREBASE_URL + '/.json', {
    method: 'put',
    contentType: 'application/json',
    payload: contenido,
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  if (code !== 200) {
    throw new Error('Restore fallo HTTP ' + code + ': ' + resp.getContentText().substring(0, 300));
  }
  Logger.log('Restore OK desde ' + NOMBRE_BACKUP);
}

/**
 * Restaurar UN SOLO nodo desde un backup, dejando el resto de Firebase intacto.
 *
 * USO MANUAL:
 *   1. listarBackups() para ver los disponibles
 *   2. Edita NOMBRE_BACKUP con el archivo a usar
 *   3. Edita NODO con el path a restaurar:
 *        'grupos'                       (raiz completa de grupos)
 *        'grupos/abc123'                (un grupo especifico)
 *        'resumen_comentarios/PROY01'   (comentarios de un proyecto)
 *   4. Ejecuta restaurarNodo()
 *
 * NOTA: el nodo se SOBREESCRIBE con el contenido del backup. Si en el backup el
 * nodo no existe, la funcion aborta SIN tocar Firebase (no borra). Se hace un
 * backupAhora() antes por seguridad.
 */
function restaurarNodo() {
  var NOMBRE_BACKUP = 'firebase_YYYY-MM-DD_HH-mm.json';  // <-- EDITAR
  var NODO          = 'grupos';                          // <-- EDITAR (sin '/' inicial)

  if (NOMBRE_BACKUP.indexOf('YYYY') >= 0) {
    throw new Error('Edita NOMBRE_BACKUP con el nombre exacto del archivo');
  }
  if (!NODO || NODO.charAt(0) === '/' || NODO.indexOf('..') >= 0) {
    throw new Error('NODO invalido: usa formato "grupos" o "grupos/abc123", sin barra inicial');
  }

  var raiz   = obtenerOCrearCarpetaRaiz();
  var diario = obtenerOCrearSubcarpeta(raiz, 'diario');
  var it     = diario.getFilesByName(NOMBRE_BACKUP);
  if (!it.hasNext()) {
    it = obtenerOCrearSubcarpeta(raiz, 'mensual').getFilesByName(NOMBRE_BACKUP);
  }
  if (!it.hasNext()) throw new Error('No encontre el archivo: ' + NOMBRE_BACKUP);

  var arbol = JSON.parse(it.next().getBlob().getDataAsString());

  var partes = NODO.split('/');
  var valor = arbol;
  for (var i = 0; i < partes.length; i++) {
    if (valor === null || typeof valor !== 'object' || !(partes[i] in valor)) {
      throw new Error('El nodo "' + NODO + '" no existe en el backup (falto en "' + partes[i] + '"). No se toca Firebase.');
    }
    valor = valor[partes[i]];
  }

  Logger.log('Snapshot de seguridad ANTES de restaurar nodo "' + NODO + '"...');
  backupAhora();

  var url = FIREBASE_URL + '/' + NODO + '.json';
  var resp = UrlFetchApp.fetch(url, {
    method: 'put',
    contentType: 'application/json',
    payload: JSON.stringify(valor),
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  if (code !== 200) {
    throw new Error('Restore de nodo fallo HTTP ' + code + ': ' + resp.getContentText().substring(0, 300));
  }
  Logger.log('Nodo "' + NODO + '" restaurado desde ' + NOMBRE_BACKUP);
}

/**
 * Simula restaurarNodo() SIN escribir a Firebase.
 * Valida que: el archivo existe, el JSON parsea, el path navega correctamente.
 * Muestra cuantas claves/items tiene el nodo para que veas si es lo esperado.
 * Usalo para ganar confianza antes de correr restaurarNodo() de verdad.
 */
function simularRestaurarNodo() {
  var NOMBRE_BACKUP = 'firebase_YYYY-MM-DD_HH-mm.json';  // <-- EDITAR
  var NODO          = 'grupos';                          // <-- EDITAR

  if (NOMBRE_BACKUP.indexOf('YYYY') >= 0) {
    throw new Error('Edita NOMBRE_BACKUP con el nombre exacto del archivo');
  }

  var raiz   = obtenerOCrearCarpetaRaiz();
  var diario = obtenerOCrearSubcarpeta(raiz, 'diario');
  var it     = diario.getFilesByName(NOMBRE_BACKUP);
  if (!it.hasNext()) {
    it = obtenerOCrearSubcarpeta(raiz, 'mensual').getFilesByName(NOMBRE_BACKUP);
  }
  if (!it.hasNext()) throw new Error('NO encontre el archivo: ' + NOMBRE_BACKUP);

  var blob = it.next().getBlob();
  Logger.log('[1/4] Archivo encontrado: ' + NOMBRE_BACKUP + ' (' + Math.round(blob.getBytes().length / 1024) + ' KB)');

  var arbol;
  try { arbol = JSON.parse(blob.getDataAsString()); }
  catch (e) { throw new Error('JSON corrupto: ' + e.message); }
  Logger.log('[2/4] JSON parseado OK. Nodos raiz: ' + Object.keys(arbol).join(', '));

  var partes = NODO.split('/');
  var valor = arbol;
  for (var i = 0; i < partes.length; i++) {
    if (valor === null || typeof valor !== 'object' || !(partes[i] in valor)) {
      throw new Error('El nodo "' + NODO + '" NO existe en el backup (falto en "' + partes[i] + '")');
    }
    valor = valor[partes[i]];
  }
  Logger.log('[3/4] Path "' + NODO + '" navegado OK');

  var resumen;
  if (valor === null) resumen = 'null (vacio)';
  else if (typeof valor !== 'object') resumen = typeof valor + ': ' + String(valor).substring(0, 100);
  else if (Array.isArray(valor)) resumen = 'array con ' + valor.length + ' items';
  else resumen = 'objeto con ' + Object.keys(valor).length + ' claves: ' + Object.keys(valor).slice(0, 10).join(', ');
  Logger.log('[4/4] Contenido a restaurar -> ' + resumen);

  Logger.log('SIMULACION OK. Si ejecutas restaurarNodo() con estos mismos valores, Firebase ' +
             'sobreescribira "' + NODO + '" con lo de arriba. Nada se ha tocado todavia.');
}

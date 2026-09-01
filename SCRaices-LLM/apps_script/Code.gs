/**
 * Google Apps Script STANDALONE - Data API para Dashboard SCRaices
 *
 * INSTALACION (como proyecto independiente):
 * 1. Ir a https://script.google.com
 * 2. Nuevo proyecto → pegar este codigo
 * 3. Implementar → Nueva implementacion → App web
 *    - Ejecutar como: Yo
 *    - Quien tiene acceso: Cualquier usuario
 * 4. Autorizar cuando pregunte (necesita acceso a Sheets)
 * 5. Copiar la URL generada
 *
 * ENDPOINT (JSON directo):
 *   GET {URL}?tables=Proyectos,Beneficiario,...
 *
 * ENDPOINT (JSONP - sin restriccion CORS):
 *   GET {URL}?tables=Proyectos,...&callback=miFuncion
 *   → responde: miFuncion({"Proyectos":{...}})
 */

var SPREADSHEET_ID = "1JAxxP9W6LJzns5rmGIo7mfk227qMLwsq-gFMCvHU0Zk";

function doGet(e) {
  var callback = null;
  try {
    callback = (e && e.parameter && e.parameter.callback) ? String(e.parameter.callback) : null;
    var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : '';
    var sheetId = (e && e.parameter && e.parameter.sheetId) ? e.parameter.sheetId : SPREADSHEET_ID;

    // Accion especial: push_snapshot → lee hojas y sube a GitHub
    // Protegida con token secreto almacenado en Script Properties (clave PUSH_TOKEN).
    // Llamar con: ?action=push_snapshot&token=TU_TOKEN
    if (action === 'push_snapshot') {
      var expectedToken = PropertiesService.getScriptProperties().getProperty('PUSH_TOKEN');
      var givenToken    = (e && e.parameter && e.parameter.token) ? e.parameter.token : '';
      if (!expectedToken || givenToken !== expectedToken) {
        return respond({ error: 'token invalido' }, null);
      }
      pushSnapshot();
      return respond({ ok: true, ts: new Date().toISOString() }, null);
    }

    var ss = SpreadsheetApp.openById(sheetId);

    // Manifest: returns row counts per table (lightweight, for smart sync)
    if (action === 'manifest') {
      var allSheets = ss.getSheets();
      var tables = {};
      for (var s = 0; s < allSheets.length; s++) {
        var sheet = allSheets[s];
        var name = sheet.getName();
        tables[name] = sheet.getLastRow() - 1;
      }
      return respond({ tables: tables, timestamp: new Date().toISOString() }, callback);
    }

    var tablesParam = (e && e.parameter && e.parameter.tables) ? e.parameter.tables : '';

    if (!tablesParam) {
      return respond({ error: 'Parametro "tables" requerido. Ej: ?tables=Proyectos,Beneficiario' }, callback);
    }

    var tableNames = tablesParam.split(',').map(function(t) { return t.trim(); });
    var result = {};

    for (var i = 0; i < tableNames.length; i++) {
      var name = tableNames[i];
      try {
        var sheet = ss.getSheetByName(name);
        if (!sheet) {
          result[name] = { error: 'Hoja no encontrada' };
          continue;
        }

        var data = sheet.getDataRange().getValues();
        if (data.length === 0) {
          result[name] = { headers: [], rows: [] };
          continue;
        }

        var headers = data[0];
        var rows = [];

        for (var r = 1; r < data.length; r++) {
          var row = {};
          for (var c = 0; c < headers.length; c++) {
            var val = data[r][c];
            if (val instanceof Date) {
              val = Utilities.formatDate(val, ss.getSpreadsheetTimeZone(), "yyyy-MM-dd'T'HH:mm:ss");
            }
            row[headers[c]] = val;
          }
          rows.push(row);
        }

        result[name] = { count: rows.length, rows: rows };

      } catch (err) {
        result[name] = { error: err.message };
      }
    }

    return respond(result, callback);

  } catch (err) {
    return respond({ error: err.message }, callback);
  }
}

// ── Snapshot automático → GitHub ──────────────────────────────────────────────
// Tablas que se incluyen en el snapshot (igual que fetchAllData del dashboard).
// Ejecucion omitida: tabla demasiado grande para Apps Script.
var SNAPSHOT_TABLES = [
  "Proyectos", "Tipologias", "Maestros", "controlBGB", "controlEEPP",
  "Beneficiario", "Seguimiento",
  "Seguimiento Cierre de Obras", "Seguimiento_Cierre", "SeguimientoCierre",
  "documentacion", "Documentacion",
  "Despacho", "soldepacho", "Tabla_pago", "Montos",
  "Solpago", "combenef"
];
var GITHUB_REPO   = "PitufosTEch/PruebasWeb";
var GITHUB_BRANCH = "data-snapshot";
var GITHUB_FILE   = "data_snapshot.json";

/**
 * Lee todas las tablas del spreadsheet y sube el JSON crudo a GitHub.
 * Llamar desde un trigger de tiempo (cada 15 min).
 * Prerequisito: guardar el token en Script Properties con clave GITHUB_TOKEN.
 */
function pushSnapshot() {
  var ss;
  try {
    ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  } catch (e) {
    Logger.log("ERROR abriendo spreadsheet: " + e.message);
    return;
  }

  var result = { ts: new Date().getTime() };

  for (var i = 0; i < SNAPSHOT_TABLES.length; i++) {
    var name = SNAPSHOT_TABLES[i];
    try {
      var sheet = ss.getSheetByName(name);
      if (!sheet) {
        result[name] = { error: "Hoja no encontrada" };
        continue;
      }
      var data = sheet.getDataRange().getValues();
      if (data.length === 0) {
        result[name] = { headers: [], rows: [] };
        continue;
      }
      var headers = data[0];
      var rows = [];
      for (var r = 1; r < data.length; r++) {
        var row = {};
        for (var c = 0; c < headers.length; c++) {
          var val = data[r][c];
          if (val instanceof Date) {
            val = Utilities.formatDate(val, ss.getSpreadsheetTimeZone(), "yyyy-MM-dd'T'HH:mm:ss");
          }
          row[headers[c]] = val;
        }
        rows.push(row);
      }
      result[name] = { count: rows.length, rows: rows };
      Logger.log("OK " + name + ": " + rows.length + " filas");
    } catch (e) {
      result[name] = { error: e.message };
      Logger.log("ERROR " + name + ": " + e.message);
    }
  }

  var json = JSON.stringify(result);
  Logger.log("Tamaño JSON: " + Math.round(json.length / 1024) + " KB");
  pushToGitHub_(json);
}

function pushToGitHub_(content) {
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) {
    Logger.log("ERROR: GITHUB_TOKEN no configurado en Propiedades del script");
    return;
  }

  var url = "https://api.github.com/repos/" + GITHUB_REPO + "/contents/" + GITHUB_FILE;
  var headers = {
    "Authorization": "token " + token,
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "GAS-Snapshot/1.0"
  };

  // Obtener SHA actual del archivo (necesario para actualizarlo)
  var sha = null;
  try {
    var getResp = UrlFetchApp.fetch(url + "?ref=" + GITHUB_BRANCH, {
      headers: headers,
      muteHttpExceptions: true
    });
    if (getResp.getResponseCode() === 200) {
      sha = JSON.parse(getResp.getContentText()).sha;
      Logger.log("SHA actual: " + sha.substring(0, 8) + "...");
    }
  } catch (e) {
    Logger.log("No se pudo leer SHA actual: " + e.message);
  }

  var payload = {
    message: "data: snapshot " + new Date().toISOString().substring(0, 16) + "Z",
    content: Utilities.base64Encode(content, Utilities.Charset.UTF_8),
    branch: GITHUB_BRANCH
  };
  if (sha) payload.sha = sha;

  try {
    var putResp = UrlFetchApp.fetch(url, {
      method: "put",
      headers: headers,
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
    var code = putResp.getResponseCode();
    if (code === 200 || code === 201) {
      Logger.log("✓ Snapshot publicado en GitHub (HTTP " + code + ")");
    } else {
      Logger.log("ERROR HTTP " + code + ": " + putResp.getContentText().substring(0, 300));
    }
  } catch (e) {
    Logger.log("ERROR fetch GitHub: " + e.message);
  }
}

// Responde en JSON o JSONP segun si hay callback
function respond(data, callback) {
  var json = JSON.stringify(data);
  if (callback) {
    // JSONP: el browser ejecuta el script sin restriccion CORS
    return ContentService
      .createTextOutput(callback + '(' + json + ')')
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService
    .createTextOutput(json)
    .setMimeType(ContentService.MimeType.JSON);
}

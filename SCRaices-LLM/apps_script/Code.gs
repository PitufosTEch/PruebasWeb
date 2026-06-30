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

/**
 * Google Apps Script STANDALONE - Data API para Dashboard SCRaices
 *
 * INSTALACION (como proyecto independiente):
 * 1. Ir a https://script.google.com
 * 2. Nuevo proyecto → pegar este codigo
 * 3. Implementar → Nueva implementacion → App web
 *    - Ejecutar como: Yo
 *    - Quien tiene acceso: Cualquier persona
 * 4. Autorizar cuando pregunte (necesita acceso a Sheets)
 * 5. Copiar la URL generada
 *
 * ENDPOINT:
 *   GET {URL}?tables=Proyectos,Beneficiario,Despacho,soldepacho,Ejecucion,Solpago,Maestros,Tabla_pago,Tipologias,controlBGB,controlEEPP
 *   GET {URL}?tables=Proyectos  (una sola tabla)
 *   GET {URL}?sheetId=XXXX&tables=Hoja1  (leer otro spreadsheet)
 */

var SPREADSHEET_ID = "1JAxxP9W6LJzns5rmGIo7mfk227qMLwsq-gFMCvHU0Zk";

function doGet(e) {
  try {
    var sheetId = e.parameter.sheetId || SPREADSHEET_ID;
    var ss = SpreadsheetApp.openById(sheetId);
    var tablesParam = e.parameter.tables || '';

    if (!tablesParam) {
      return jsonResponse({ error: 'Parametro "tables" requerido. Ej: ?tables=Proyectos,Beneficiario' });
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
            // Convertir fechas a string ISO
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

    return jsonResponse(result);

  } catch (err) {
    return jsonResponse({ error: err.message });
  }
}

function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * EmailReport.gs - Envia reporte de proyectos terminados y activos
 * Destinatarios: rlagos@scraices.cl, aespinoza@scraices.cl
 * Para probar: ejecutar testEnviarReporte()
 * Para automatizar: crear trigger semanal con enviarReporteProyectos
 */

var EMAIL_DESTINATARIOS = 'rlagos@scraices.cl,aespinoza@scraices.cl';
var FIREBASE_URL = 'https://scraices-dashboard-default-rtdb.firebaseio.com';

function enviarReporteProyectos() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var proyectos = getSheetDataEmail(ss, 'Proyectos');
  var beneficiarios = getSheetDataEmail(ss, 'Beneficiario');

  var terminadosManual = {};
  try {
    var fbResp = UrlFetchApp.fetch(FIREBASE_URL + '/proyectos_terminados.json');
    var fbData = JSON.parse(fbResp.getContentText());
    if (fbData) terminadosManual = fbData;
  } catch (e) {
    Logger.log('No se pudo leer Firebase: ' + e.message);
  }

  var terminados = [];
  var activos = [];
  var hoy = new Date();
  var unAnoAtras = new Date(hoy.getTime() - 365 * 24 * 60 * 60 * 1000);

  for (var i = 0; i < proyectos.length; i++) {
    var p = proyectos[i];
    var pid = String(p['ID_proy'] || '');
    var nombre = String(p['NOMBRE_PROYECTO'] || '');
    var comuna = String(p['COMUNA'] || '');
    var estado = String(p['estado_general'] || '').toLowerCase();

    if (!nombre || nombre === 'nan' || nombre === '') continue;
    if (!estado.match(/ejecuci|finalizado/i)) continue;

    var bens = beneficiarios.filter(function(b) { return String(b['ID_Proy']) === pid; });
    var nViv = bens.length;
    if (nViv === 0) continue;

    var nRecep = 0;
    var ultimaRecep = null;
    for (var j = 0; j < bens.length; j++) {
      var frd = String(bens[j]['F_R_dom'] || '').trim();
      if (frd && frd !== 'nan' && frd !== '' && frd !== 'NaT' && frd !== 'None') {
        nRecep++;
        var fechaR = parseFechaEmail(frd);
        if (fechaR && (!ultimaRecep || fechaR > ultimaRecep)) ultimaRecep = fechaR;
      }
    }

    var fi = parseFechaEmail(p['fecha_inicio']);
    var dur = parseInt(p['duracion']) || 0;
    var venc = null;
    if (fi && dur > 0) venc = new Date(fi.getTime() + dur * 24 * 60 * 60 * 1000);

    var finTabla = estado.indexOf('finalizado') >= 0;
    var finRecep = nRecep === nViv && nViv > 0;
    var finManual = terminadosManual[pid] ? true : false;
    var esFinalizado = finTabla || finRecep || finManual;

    var motivoManual = finManual ? (terminadosManual[pid].motivo || '') : '';
    var fechaManual = finManual ? (terminadosManual[pid].fecha || '') : '';

    var fechaFin = ultimaRecep;
    if (!fechaFin && finManual && fechaManual) fechaFin = parseFechaEmail(fechaManual);

    var origen = '';
    if (finRecep) origen = 'Recepciones completas';
    else if (finManual) origen = 'Manual: ' + motivoManual;
    else if (finTabla) origen = 'AppSheet';

    var tz = 'America/Santiago';
    var row = {
      nombre: nombre,
      comuna: comuna,
      nViv: nViv,
      nRecep: nRecep,
      inicio: fi ? Utilities.formatDate(fi, tz, 'dd/MM/yyyy') : '',
      plazo: dur + 'd',
      vencimiento: venc ? Utilities.formatDate(venc, tz, 'dd/MM/yyyy') : '',
      ultimaRecep: ultimaRecep ? Utilities.formatDate(ultimaRecep, tz, 'dd/MM/yyyy') : '',
      fechaFin: fechaFin ? Utilities.formatDate(fechaFin, tz, 'dd/MM/yyyy') : '',
      origen: origen,
      esFinalizado: esFinalizado
    };

    if (esFinalizado && fechaFin && fechaFin > unAnoAtras) {
      terminados.push(row);
    } else if (!esFinalizado) {
      if (venc) {
        var diasR = Math.floor((venc - hoy) / (1000 * 60 * 60 * 24));
        row.diasRestantes = diasR;
        row.estadoPlazo = diasR < 0 ? 'VENCIDO ' + Math.abs(diasR) + 'd' : diasR + 'd';
        row.colorPlazo = diasR < 0 ? '#ef4444' : diasR <= 90 ? '#f59e0b' : '#22c55e';
      } else {
        row.diasRestantes = null;
        row.estadoPlazo = '';
        row.colorPlazo = '#94a3b8';
      }
      activos.push(row);
    }
  }

  terminados.sort(function(a, b) { return (b.fechaFin || '').localeCompare(a.fechaFin || ''); });
  activos.sort(function(a, b) { return (a.diasRestantes || 9999) - (b.diasRestantes || 9999); });

  var htmlT = generarTablaTerminados(terminados);
  var htmlA = generarTablaActivos(activos);
  var fecha = Utilities.formatDate(hoy, 'America/Santiago', 'dd/MM/yyyy');
  var dashUrl = 'https://pitufostech.github.io/PruebasWeb/SCRaices-LLM/dashboard/index_live_v3.html';

  var body = '';
  body += '<div style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;">';
  body += '<div style="background:#0f172a;color:white;padding:16px 24px;border-radius:10px 10px 0 0;">';
  body += '<h1 style="margin:0;font-size:18px;">SCRaices - Reporte de Proyectos</h1>';
  body += '<p style="margin:4px 0 0;font-size:12px;color:#94a3b8;">Generado: ' + fecha + '</p>';
  body += '</div>';
  body += '<div style="padding:20px;background:#f8fafc;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px;">';
  body += '<h2 style="font-size:15px;color:#059669;margin:0 0 12px;">Proyectos Terminados (ultimo ano) - ' + terminados.length + '</h2>';
  body += htmlT;
  body += '<h2 style="font-size:15px;color:#2563eb;margin:24px 0 12px;">Proyectos en Ejecucion - ' + activos.length + '</h2>';
  body += htmlA;
  body += '<p style="font-size:11px;color:#9ca3af;margin-top:20px;text-align:center;">';
  body += 'Dashboard: <a href="' + dashUrl + '">Abrir Dashboard v3</a></p>';
  body += '</div></div>';

  GmailApp.sendEmail(EMAIL_DESTINATARIOS, 'SCRaices - Reporte Proyectos ' + fecha, 'Ver version HTML', {htmlBody: body});
  Logger.log('Reporte enviado a: ' + EMAIL_DESTINATARIOS);
  Logger.log('Terminados: ' + terminados.length + ', Activos: ' + activos.length);
}

function generarTablaTerminados(rows) {
  if (rows.length === 0) return '<p style="color:#9ca3af;font-size:13px;">Sin proyectos terminados en el ultimo ano</p>';
  var html = '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:#d1fae5;border-bottom:2px solid #059669;">';
  html += '<th style="padding:8px;text-align:left;">Proyecto</th>';
  html += '<th style="padding:8px;text-align:left;">Comuna</th>';
  html += '<th style="padding:8px;text-align:center;">Viv</th>';
  html += '<th style="padding:8px;text-align:center;">Recepciones</th>';
  html += '<th style="padding:8px;text-align:center;">Ultima Recepcion</th>';
  html += '<th style="padding:8px;text-align:left;">Origen</th>';
  html += '</tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var bg = i % 2 === 0 ? '#ffffff' : '#f0fdf4';
    var rc = r.nRecep === r.nViv ? '#059669' : '#f59e0b';
    html += '<tr style="background:' + bg + ';border-bottom:1px solid #e2e8f0;">';
    html += '<td style="padding:8px;font-weight:600;">' + r.nombre + '</td>';
    html += '<td style="padding:8px;color:#6b7280;">' + r.comuna + '</td>';
    html += '<td style="padding:8px;text-align:center;font-weight:700;">' + r.nViv + '</td>';
    html += '<td style="padding:8px;text-align:center;font-weight:700;color:' + rc + ';">' + r.nRecep + '/' + r.nViv + '</td>';
    html += '<td style="padding:8px;text-align:center;">' + r.ultimaRecep + '</td>';
    html += '<td style="padding:8px;font-size:11px;color:#6b7280;">' + r.origen + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function generarTablaActivos(rows) {
  if (rows.length === 0) return '<p style="color:#9ca3af;font-size:13px;">Sin proyectos activos</p>';
  var html = '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html += '<thead><tr style="background:#dbeafe;border-bottom:2px solid #2563eb;">';
  html += '<th style="padding:8px;text-align:left;">Proyecto</th>';
  html += '<th style="padding:8px;text-align:left;">Comuna</th>';
  html += '<th style="padding:8px;text-align:center;">Viv</th>';
  html += '<th style="padding:8px;text-align:center;">Recepciones</th>';
  html += '<th style="padding:8px;text-align:center;">Inicio</th>';
  html += '<th style="padding:8px;text-align:center;">Plazo</th>';
  html += '<th style="padding:8px;text-align:center;">Vencimiento</th>';
  html += '<th style="padding:8px;text-align:center;">Plazo Restante</th>';
  html += '</tr></thead><tbody>';
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var bg = i % 2 === 0 ? '#ffffff' : '#eff6ff';
    var rc = r.nRecep > 0 ? '#2563eb' : '#94a3b8';
    html += '<tr style="background:' + bg + ';border-bottom:1px solid #e2e8f0;">';
    html += '<td style="padding:8px;font-weight:600;">' + r.nombre + '</td>';
    html += '<td style="padding:8px;color:#6b7280;">' + r.comuna + '</td>';
    html += '<td style="padding:8px;text-align:center;font-weight:700;">' + r.nViv + '</td>';
    html += '<td style="padding:8px;text-align:center;font-weight:700;color:' + rc + ';">' + r.nRecep + '/' + r.nViv + '</td>';
    html += '<td style="padding:8px;text-align:center;">' + r.inicio + '</td>';
    html += '<td style="padding:8px;text-align:center;">' + r.plazo + '</td>';
    html += '<td style="padding:8px;text-align:center;">' + r.vencimiento + '</td>';
    html += '<td style="padding:8px;text-align:center;font-weight:700;color:' + r.colorPlazo + ';">' + r.estadoPlazo + '</td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function parseFechaEmail(val) {
  if (!val) return null;
  var s = String(val).trim();
  if (s === '' || s === 'nan' || s === 'NaT' || s === 'None') return null;
  if (s.indexOf('T') > 0) {
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }
  if (val instanceof Date) return val;
  var parts = s.split(/[\/\-]/);
  if (parts.length === 3) {
    var a = parseInt(parts[0]);
    var b = parseInt(parts[1]);
    var c = parseInt(parts[2]);
    if (parts[0].length === 4) return new Date(a, b - 1, c);
    if (a > 12) return new Date(c, b - 1, a);
    return new Date(c, a - 1, b);
  }
  return null;
}

function getSheetDataEmail(ss, sheetName) {
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) return [];
  var data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  var headers = data[0];
  var rows = [];
  for (var r = 1; r < data.length; r++) {
    var row = {};
    for (var c = 0; c < headers.length; c++) {
      row[headers[c]] = data[r][c];
    }
    rows.push(row);
  }
  return rows;
}

function testEnviarReporte() {
  enviarReporteProyectos();
}

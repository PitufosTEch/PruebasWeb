/**
 * EmailReport.gs — Envia reporte de proyectos terminados y activos
 *
 * INSTALACION:
 * 1. Agregar este archivo al mismo proyecto Apps Script del Dashboard
 * 2. Configurar EMAIL_DESTINATARIOS con los correos
 * 3. Ejecutar enviarReporteProyectos() manualmente o con trigger
 *
 * TRIGGER AUTOMATICO (opcional):
 * 1. En Apps Script: Activadores (reloj) → Agregar activador
 * 2. Funcion: enviarReporteProyectos
 * 3. Frecuencia: Semanal (ej: lunes 8am)
 */

var EMAIL_DESTINATARIOS = 'coordinadorobras@scraices.cl'; // Separar con coma si son varios
var FIREBASE_URL = 'https://scraices-dashboard-default-rtdb.firebaseio.com';

function enviarReporteProyectos() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);

  // 1. Leer datos
  var proyectos = getSheetData(ss, 'Proyectos');
  var beneficiarios = getSheetData(ss, 'Beneficiario');

  // 2. Leer proyectos terminados manualmente desde Firebase
  var terminadosManual = {};
  try {
    var fbResp = UrlFetchApp.fetch(FIREBASE_URL + '/proyectos_terminados.json');
    var fbData = JSON.parse(fbResp.getContentText());
    if (fbData) terminadosManual = fbData;
  } catch (e) {
    Logger.log('No se pudo leer Firebase: ' + e.message);
  }

  // 3. Procesar proyectos
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

    // Solo proyectos en ejecucion o finalizados
    if (!estado.match(/ejecuci|finalizado/i)) continue;

    // Contar beneficiarios y recepciones
    var bens = beneficiarios.filter(function(b) { return String(b['ID_Proy']) === pid; });
    var nViv = bens.length;
    if (nViv === 0) continue;

    var nRecep = 0;
    var ultimaRecep = null;

    for (var j = 0; j < bens.length; j++) {
      var frd = String(bens[j]['F_R_dom'] || '').trim();
      if (frd && frd !== 'nan' && frd !== '' && frd !== 'NaT' && frd !== 'None') {
        nRecep++;
        var fechaR = parseFecha(frd);
        if (fechaR && (!ultimaRecep || fechaR > ultimaRecep)) {
          ultimaRecep = fechaR;
        }
      }
    }

    // Plazo
    var fi = parseFecha(p['fecha_inicio']);
    var dur = parseInt(p['duracion']) || 0;
    var venc = null;
    if (fi && dur > 0) {
      venc = new Date(fi.getTime() + dur * 24 * 60 * 60 * 1000);
    }

    // Determinar si esta finalizado
    var finTabla = estado.indexOf('finalizado') >= 0;
    var finRecep = nRecep === nViv && nViv > 0;
    var finManual = terminadosManual[pid] ? true : false;
    var esFinalizado = finTabla || finRecep || finManual;

    var motivoManual = finManual ? (terminadosManual[pid].motivo || '') : '';
    var fechaManual = finManual ? (terminadosManual[pid].fecha || '') : '';

    // Fecha de finalizacion
    var fechaFin = ultimaRecep;
    if (!fechaFin && finManual && fechaManual) {
      fechaFin = parseFecha(fechaManual);
    }

    // Determinar origen de finalizacion
    var origen = '';
    if (finRecep) origen = 'Recepciones completas';
    else if (finManual) origen = 'Manual: ' + motivoManual;
    else if (finTabla) origen = 'AppSheet';

    var row = {
      nombre: nombre,
      comuna: comuna,
      nViv: nViv,
      nRecep: nRecep,
      inicio: fi ? Utilities.formatDate(fi, 'America/Santiago', 'dd/MM/yyyy') : '—',
      plazo: dur + 'd',
      vencimiento: venc ? Utilities.formatDate(venc, 'America/Santiago', 'dd/MM/yyyy') : '—',
      ultimaRecep: ultimaRecep ? Utilities.formatDate(ultimaRecep, 'America/Santiago', 'dd/MM/yyyy') : '—',
      fechaFin: fechaFin ? Utilities.formatDate(fechaFin, 'America/Santiago', 'dd/MM/yyyy') : '—',
      origen: origen,
      esFinalizado: esFinalizado
    };

    if (esFinalizado && fechaFin && fechaFin > unAnoAtras) {
      terminados.push(row);
    } else if (!esFinalizado) {
      // Calcular dias restantes
      if (venc) {
        var diasR = Math.floor((venc - hoy) / (1000 * 60 * 60 * 24));
        row.diasRestantes = diasR;
        row.estadoPlazo = diasR < 0 ? 'VENCIDO ' + Math.abs(diasR) + 'd' : diasR <= 90 ? diasR + 'd' : diasR + 'd';
        row.colorPlazo = diasR < 0 ? '#ef4444' : diasR <= 90 ? '#f59e0b' : '#22c55e';
      } else {
        row.diasRestantes = null;
        row.estadoPlazo = '—';
        row.colorPlazo = '#94a3b8';
      }
      activos.push(row);
    }
  }

  // Ordenar
  terminados.sort(function(a, b) { return b.fechaFin < a.fechaFin ? -1 : 1; });
  activos.sort(function(a, b) { return (a.diasRestantes || 9999) - (b.diasRestantes || 9999); });

  // 4. Generar HTML
  var htmlTerminados = generarTablaTerminados(terminados);
  var htmlActivos = generarTablaActivos(activos);

  // 5. Enviar correo
  var fecha = Utilities.formatDate(hoy, 'America/Santiago', 'dd/MM/yyyy');

  MailApp.sendEmail({
    to: EMAIL_DESTINATARIOS,
    subject: 'SCRaices — Reporte Proyectos ' + fecha,
    htmlBody: '<div style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto;">' +
      '<div style="background:#0f172a;color:white;padding:16px 24px;border-radius:10px 10px 0 0;">' +
        '<h1 style="margin:0;font-size:18px;">SCRaices — Reporte de Proyectos</h1>' +
        '<p style="margin:4px 0 0;font-size:12px;color:#94a3b8;">Generado: ' + fecha + '</p>' +
      '</div>' +
      '<div style="padding:20px;background:#f8fafc;border:1px solid #e2e8f0;border-top:none;">' +
        '<h2 style="font-size:15px;color:#059669;margin:0 0 12px;">Proyectos Terminados (ultimo ano) — ' + terminados.length + '</h2>' +
        htmlTerminados +
        '<h2 style="font-size:15px;color:#2563eb;margin:24px 0 12px;">Proyectos en Ejecucion — ' + activos.length + '</h2>' +
        htmlActivos +
        '<p style="font-size:11px;color:#9ca3af;margin-top:20px;text-align:center;">Dashboard: <a href="https://pitufostech.github.io/PruebasWeb/SCRaices-LLM/dashboard/index_live_v3.html">Abrir Dashboard v3</a></p>' +
      '</div>' +
    '</div>'
  });

  Logger.log('Reporte enviado a: ' + EMAIL_DESTINATARIOS);
  Logger.log('Terminados: ' + terminados.length + ', Activos: ' + activos.length);
}

function generarTablaTerminados(rows) {
  if (rows.length === 0) return '<p style="color:#9ca3af;font-size:13px;">Sin proyectos terminados en el ultimo ano</p>';

  var html = '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
    '<thead><tr style="background:#d1fae5;border-bottom:2px solid #059669;">' +
    '<th style="padding:8px;text-align:left;">Proyecto</th>' +
    '<th style="padding:8px;text-align:left;">Comuna</th>' +
    '<th style="padding:8px;text-align:center;">Viv</th>' +
    '<th style="padding:8px;text-align:center;">Recepciones</th>' +
    '<th style="padding:8px;text-align:center;">Ultima Recepcion</th>' +
    '<th style="padding:8px;text-align:left;">Origen</th>' +
    '</tr></thead><tbody>';

  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var bg = i % 2 === 0 ? '#ffffff' : '#f0fdf4';
    html += '<tr style="background:' + bg + ';border-bottom:1px solid #e2e8f0;">' +
      '<td style="padding:8px;font-weight:600;">' + r.nombre + '</td>' +
      '<td style="padding:8px;color:#6b7280;">' + r.comuna + '</td>' +
      '<td style="padding:8px;text-align:center;font-weight:700;">' + r.nViv + '</td>' +
      '<td style="padding:8px;text-align:center;font-weight:700;color:' + (r.nRecep === r.nViv ? '#059669' : '#f59e0b') + ';">' + r.nRecep + '/' + r.nViv + '</td>' +
      '<td style="padding:8px;text-align:center;">' + r.ultimaRecep + '</td>' +
      '<td style="padding:8px;font-size:11px;color:#6b7280;">' + r.origen + '</td>' +
      '</tr>';
  }

  html += '</tbody></table>';
  return html;
}

function generarTablaActivos(rows) {
  if (rows.length === 0) return '<p style="color:#9ca3af;font-size:13px;">Sin proyectos activos</p>';

  var html = '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
    '<thead><tr style="background:#dbeafe;border-bottom:2px solid #2563eb;">' +
    '<th style="padding:8px;text-align:left;">Proyecto</th>' +
    '<th style="padding:8px;text-align:left;">Comuna</th>' +
    '<th style="padding:8px;text-align:center;">Viv</th>' +
    '<th style="padding:8px;text-align:center;">Recepciones</th>' +
    '<th style="padding:8px;text-align:center;">Inicio</th>' +
    '<th style="padding:8px;text-align:center;">Plazo</th>' +
    '<th style="padding:8px;text-align:center;">Vencimiento</th>' +
    '<th style="padding:8px;text-align:center;">Plazo Restante</th>' +
    '</tr></thead><tbody>';

  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var bg = i % 2 === 0 ? '#ffffff' : '#eff6ff';
    html += '<tr style="background:' + bg + ';border-bottom:1px solid #e2e8f0;">' +
      '<td style="padding:8px;font-weight:600;">' + r.nombre + '</td>' +
      '<td style="padding:8px;color:#6b7280;">' + r.comuna + '</td>' +
      '<td style="padding:8px;text-align:center;font-weight:700;">' + r.nViv + '</td>' +
      '<td style="padding:8px;text-align:center;font-weight:700;color:' + (r.nRecep > 0 ? '#2563eb' : '#94a3b8') + ';">' + r.nRecep + '/' + r.nViv + '</td>' +
      '<td style="padding:8px;text-align:center;">' + r.inicio + '</td>' +
      '<td style="padding:8px;text-align:center;">' + r.plazo + '</td>' +
      '<td style="padding:8px;text-align:center;">' + r.vencimiento + '</td>' +
      '<td style="padding:8px;text-align:center;font-weight:700;color:' + r.colorPlazo + ';">' + r.estadoPlazo + '</td>' +
      '</tr>';
  }

  html += '</tbody></table>';
  return html;
}

function parseFecha(val) {
  if (!val) return null;
  var s = String(val).trim();
  if (s === '' || s === 'nan' || s === 'NaT' || s === 'None') return null;

  // ISO format: 2025-10-22T07:00:00
  if (s.indexOf('T') > 0) {
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }

  // Try date object
  if (val instanceof Date) return val;

  // DD/MM/YYYY or MM/DD/YYYY
  var parts = s.split(/[\/\-]/);
  if (parts.length === 3) {
    var a = parseInt(parts[0]);
    var b = parseInt(parts[1]);
    var c = parseInt(parts[2]);
    if (parts[0].length === 4) return new Date(a, b - 1, c); // YYYY-MM-DD
    if (a > 12) return new Date(c, b - 1, a); // DD/MM/YYYY
    return new Date(c, a - 1, b); // MM/DD/YYYY
  }

  return null;
}

function getSheetData(ss, sheetName) {
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

/**
 * Funcion de prueba - envia el reporte inmediatamente
 */
function testEnviarReporte() {
  enviarReporteProyectos();
}

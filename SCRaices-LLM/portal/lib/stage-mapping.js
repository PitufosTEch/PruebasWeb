/**
 * StageMapping — Shared stage/progress logic extracted from Dashboard v3
 * Single source of truth for stage codes, mapping, and %Total calculation
 */
(function(global) {
  'use strict';

  const SECUENCIA_PRINCIPAL = [
    "01_FUNDACIONES", "12_ALCANTARILLADO", "02_1ERA_ETAPA", "28_VENTANAS",
    "29_EIFS", "03_2DA_ETAPA", "13_GASFITERIA", "07_CERAMICO_PISO",
    "08_CERAMICO_MURO", "09_PINTURA_EXT", "10_PINTURA_INT", "14_OBRAS_EXT"
  ];

  const LINEA_CRITICA = [
    "01_FUNDACIONES", "12_ALCANTARILLADO",
    "02_1ERA_ETAPA", "28_VENTANAS", "29_EIFS",
    "03_2DA_ETAPA",
    "13_GASFITERIA",
    "07_CERAMICO_PISO", "08_CERAMICO_MURO"
  ];

  const PESOS_VIV = {
    'A_Fund': 0.02, 'A_Radier': 0.04, 'A_Planta_Alc': 0.01,
    'A_E_Tabiques': 0.06, 'A_E_Techumbre': 0.04, 'A_rev Ext': 0.06,
    'A_vent': 0.03, 'A_Cubierta': 0.03, 'A_Ent_Cielo': 0.02,
    'A_ent_alero': 0.02, 'A_Red_AP': 0.03, 'A_Red_Elect': 0.04,
    'A_rev_ZS': 0.04, 'A_rev_ZH': 0.02, 'A_Aisl_Muro': 0.04,
    'A_Aisl_Cielo': 0.03, 'A_Cer_Piso': 0.05, 'A_Cer_muro': 0.03,
    'A_pint_Ext': 0.04, 'A_pint_int': 0.02, 'A_puertas': 0.05,
    'A_molduras': 0.02, 'A_Art_Baño': 0.05, 'A_Art_cocina': 0.02,
    'A_Art_Elec': 0.04, 'A_AP_Ext': 0.05, 'A_ALC_Ext': 0.05,
    'A_Ins_Elec_Ext': 0.05
  };

  // Map a single despacho segment text to a stage code
  function mapearSegmento(segmento) {
    if (!segmento) return null;
    const t = segmento.toLowerCase().trim();
    if (t.includes("fundacion") && !t.includes("eifs") && !t.includes("aislacion")) return "01_FUNDACIONES";
    if (t.includes("alcantarillado")) return "12_ALCANTARILLADO";
    if (t.includes("1era")) return "02_1ERA_ETAPA";
    if (t.includes("ventana")) return "28_VENTANAS";
    if (t.includes("eifs") || t.includes("aislacion fund")) return "29_EIFS";
    if (t.includes("2da")) return "03_2DA_ETAPA";
    if (t.includes("piso") && t.includes("ceram")) return "07_CERAMICO_PISO";
    if (t.includes("07-") && t.includes("piso")) return "07_CERAMICO_PISO";
    if (t.includes("muro") && t.includes("ceram")) return "08_CERAMICO_MURO";
    if (t.includes("08-") && t.includes("muro")) return "08_CERAMICO_MURO";
    if (t.includes("pintura ext") || t.includes("09-")) return "09_PINTURA_EXT";
    if (t.includes("pintura int") || t.includes("10-")) return "10_PINTURA_INT";
    if (t.includes("pintura") && t.includes("r.c")) return "09_PINTURA_EXT";
    if (t.includes("gasfiter") || t.includes("sol. ac") || t.includes("artefact") || t.includes("cocina") || t.includes("calefont")) return "13_GASFITERIA";
    if (t.includes("obra") && t.includes("ext")) return "14_OBRAS_EXT";
    if (t.includes("ap ext") || t.includes("05-")) return "14_OBRAS_EXT";
    return null;
  }

  // Map a full Tipo_despacho (may contain multiple comma-separated segments)
  function mapearTipoDespacho(tipo) {
    if (!tipo) return [];
    const etapas = [];
    tipo.split(',').forEach(seg => {
      const key = mapearSegmento(seg);
      if (key && !etapas.includes(key)) etapas.push(key);
    });
    return etapas;
  }

  // Get dispatched stages for a beneficiary from despacho records
  function getEtapasDespachadas(despachos) {
    const etapas = new Set();
    despachos.forEach(d => {
      mapearTipoDespacho(d.Tipo_despacho || '').forEach(e => etapas.add(e));
    });
    return etapas;
  }

  // Check if all critical line stages are dispatched
  function lineaCriticaCompleta(etapasDespachadas) {
    return LINEA_CRITICA.every(e => etapasDespachadas.has(e));
  }

  // Calculate despacho progress %
  function calcAvanceDespacho(etapasDespachadas) {
    const n = SECUENCIA_PRINCIPAL.filter(s => etapasDespachadas.has(s)).length;
    return Math.round(n / SECUENCIA_PRINCIPAL.length * 100);
  }

  // Parse a date string to ISO (YYYY-MM-DD)
  function parseDate(raw) {
    if (!raw || String(raw).trim() === '' || ['nan','NaT','None','none'].includes(String(raw).toLowerCase())) return null;
    const s = String(raw).split(' ')[0].split('T')[0];
    // Try YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    // Try MM/DD/YYYY or DD/MM/YYYY
    const parts = s.split(/[\/\-]/);
    if (parts.length === 3) {
      if (parts[0].length === 4) return s; // already ISO
      const [a, b, c] = parts.map(Number);
      if (a > 12) return `${c}-${String(b).padStart(2,'0')}-${String(a).padStart(2,'0')}`; // DD/MM/YYYY
      return `${c}-${String(a).padStart(2,'0')}-${String(b).padStart(2,'0')}`; // MM/DD/YYYY
    }
    return null;
  }

  // Format ISO date to DD/MM/YYYY
  function formatFecha(iso) {
    if (!iso) return '—';
    const p = iso.split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : iso;
  }

  // Format money
  function formatPeso(n) {
    if (n >= 1e9) return '$' + (n/1e9).toFixed(1) + 'B';
    if (n >= 1e6) return '$' + Math.round(n/1e6) + 'M';
    return '$' + n.toLocaleString('es-CL', { maximumFractionDigits: 0 });
  }

  function parseMonto(val) {
    if (!val || val === '' || val === 'nan') return 0;
    const s = String(val).replace(/\$/g, '').replace(/\./g, '').replace(/,/g, '.').trim();
    const n = parseFloat(s);
    return isNaN(n) ? 0 : Math.round(n);
  }

  // Determine semaforo for a project
  function calcSemaforo(diasRestantes, criticas, delta) {
    if ((diasRestantes !== null && diasRestantes < 0) || criticas >= 3) return 'rojo';
    if ((diasRestantes !== null && diasRestantes <= 90) || criticas > 0 || delta < -10) return 'amarillo';
    return 'verde';
  }

  global.StageMapping = {
    SECUENCIA_PRINCIPAL,
    LINEA_CRITICA,
    PESOS_VIV,
    mapearSegmento,
    mapearTipoDespacho,
    getEtapasDespachadas,
    lineaCriticaCompleta,
    calcAvanceDespacho,
    parseDate,
    formatFecha,
    formatPeso,
    parseMonto,
    calcSemaforo
  };

})(typeof window !== 'undefined' ? window : this);

/**
 * Dashboard de Control de Obras - SCRaices
 * Panel de seguimiento de etapas de construcción por proyecto y beneficiario
 *
 * Autor: Claude Code / SCRaices Team
 * Versión: 1.0
 */

import React, { useState, useMemo, useCallback } from 'react';
import {
  Search, ChevronDown, ChevronRight, AlertTriangle, CheckCircle2,
  Clock, AlertCircle, Home, Building2, Calendar, FileText,
  TrendingUp, Users, Package, Filter, RefreshCw, Eye
} from 'lucide-react';

// ============================================================================
// CONFIGURACIÓN DE ETAPAS (basado en config/etapas_config.json)
// ============================================================================
const ETAPAS_CONFIG = {
  "01_FUNDACIONES": {
    codigo: "01", nombre: "Fundaciones", duracion: 3,
    tiempo_optimo: null, tiempo_alerta: null, dependencia: null,
    es_inicio: true, critico: false
  },
  "12_ALCANTARILLADO": {
    codigo: "12", nombre: "Alcantarillado", duracion: 3,
    tiempo_optimo: null, tiempo_alerta: null, dependencia: "01_FUNDACIONES",
    flexible: true, critico: false
  },
  "02_1ERA_ETAPA": {
    codigo: "02", nombre: "1era Etapa", duracion: 21,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "01_FUNDACIONES",
    critico: true
  },
  "28_VENTANAS": {
    codigo: "28", nombre: "Ventanas", duracion: 1,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "02_1ERA_ETAPA",
    critico: true
  },
  "29_EIFS": {
    codigo: "29", nombre: "EIFS", duracion: 3,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "02_1ERA_ETAPA",
    critico: false
  },
  "03_2DA_ETAPA": {
    codigo: "03", nombre: "2da Etapa", duracion: 10,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "02_1ERA_ETAPA",
    critico: true
  },
  "07_CERAMICO_PISO": {
    codigo: "07", nombre: "Cerámico Piso", duracion: 7,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "02_1ERA_ETAPA",
    critico: false
  },
  "09_PINTURA_EXT": {
    codigo: "09", nombre: "Pintura Ext.", duracion: 7,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "02_1ERA_ETAPA",
    critico: false
  },
  "08_CERAMICO_MURO": {
    codigo: "08", nombre: "Cerámico Muro", duracion: 3,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "03_2DA_ETAPA",
    critico: true
  },
  "10_PINTURA_INT": {
    codigo: "10", nombre: "Pintura Int.", duracion: 7,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "03_2DA_ETAPA",
    critico: false
  },
  "13_GASFITERIA": {
    codigo: "13", nombre: "Gasfitería", duracion: 5,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "08_CERAMICO_MURO",
    critico: true
  },
  "11_SOL_AC": {
    codigo: "11", nombre: "Artefactos", duracion: 3,
    tiempo_optimo: 7, tiempo_alerta: 14, dependencia: "08_CERAMICO_MURO",
    critico: true
  }
};

// Secuencia principal de etapas críticas (ruta crítica)
const SECUENCIA_PRINCIPAL = [
  "01_FUNDACIONES", "02_1ERA_ETAPA", "28_VENTANAS", "03_2DA_ETAPA",
  "08_CERAMICO_MURO", "13_GASFITERIA", "11_SOL_AC"
];

// Colores del sistema
const COLORES = {
  en_tiempo: "#22c55e",    // Verde
  atencion: "#eab308",     // Amarillo
  critico: "#ef4444",      // Rojo
  bloqueado: "#6b7280",    // Gris
  despachado: "#3b82f6",   // Azul
  solicitado: "#8b5cf6"    // Púrpura
};

// ============================================================================
// DATOS DE EJEMPLO (simula datos de Google Sheets)
// ============================================================================
const PROYECTOS_DATA = [
  { ID_proy: "P93", NOMBRE_PROYECTO: "Grupo Panguipulli DS 10 N2", COMUNA: "Panguipulli", estado_general: "En ejecución" },
  { ID_proy: "P94", NOMBRE_PROYECTO: "Grupo Panguipulli DS 10 N3", COMUNA: "Panguipulli", estado_general: "En ejecución" },
  { ID_proy: "P92", NOMBRE_PROYECTO: "Lago Ranco", COMUNA: "Lago Ranco", estado_general: "En ejecución" },
  { ID_proy: "P87", NOMBRE_PROYECTO: "Raíces de Lanco", COMUNA: "Lanco", estado_general: "En ejecución" },
  { ID_proy: "P26", NOMBRE_PROYECTO: "Truful Truful", COMUNA: "Cunco", estado_general: "En ejecución" },
  { ID_proy: "P19", NOMBRE_PROYECTO: "Los Valles de Gorbea", COMUNA: "Gorbea", estado_general: "En ejecución" }
];

// Beneficiarios de ejemplo con diferentes estados
const BENEFICIARIOS_DATA = [
  // Proyecto P93 - Panguipulli N2
  { ID_Benef: 1001, ID_Proy: "P93", NOMBRES: "Juan Carlos", APELLIDOS: "Pérez Muñoz", Estado: "Ejecución", tipologia: "Casa + RC" },
  { ID_Benef: 1002, ID_Proy: "P93", NOMBRES: "María Elena", APELLIDOS: "González Soto", Estado: "Ejecución", tipologia: "Casa" },
  { ID_Benef: 1003, ID_Proy: "P93", NOMBRES: "Pedro Antonio", APELLIDOS: "Sánchez Rivas", Estado: "Ejecución", tipologia: "Casa + RC" },
  { ID_Benef: 1004, ID_Proy: "P93", NOMBRES: "Ana María", APELLIDOS: "Torres Vega", Estado: "Ejecución", tipologia: "Casa" },
  { ID_Benef: 1005, ID_Proy: "P93", NOMBRES: "Roberto", APELLIDOS: "Fuentes Díaz", Estado: "Ejecución", tipologia: "Casa + RC" },
  { ID_Benef: 1006, ID_Proy: "P93", NOMBRES: "Carmen", APELLIDOS: "López Araya", Estado: "Ejecución", tipologia: "Casa" },
  // Proyecto P94 - Panguipulli N3
  { ID_Benef: 2001, ID_Proy: "P94", NOMBRES: "Luis Alberto", APELLIDOS: "Martínez Caro", Estado: "Ejecución", tipologia: "Casa + RC" },
  { ID_Benef: 2002, ID_Proy: "P94", NOMBRES: "Rosa Isabel", APELLIDOS: "Hernández Paz", Estado: "Ejecución", tipologia: "Casa" },
  { ID_Benef: 2003, ID_Proy: "P94", NOMBRES: "Miguel Ángel", APELLIDOS: "Rodríguez Luna", Estado: "Ejecución", tipologia: "Casa + RC" },
  { ID_Benef: 2004, ID_Proy: "P94", NOMBRES: "Patricia", APELLIDOS: "Vargas Mora", Estado: "Ejecución", tipologia: "Casa" },
  // Proyecto P92 - Lago Ranco
  { ID_Benef: 3001, ID_Proy: "P92", NOMBRES: "Francisco", APELLIDOS: "Silva Parra", Estado: "Ejecución", tipologia: "Casa + RC" },
  { ID_Benef: 3002, ID_Proy: "P92", NOMBRES: "Claudia", APELLIDOS: "Muñoz Reyes", Estado: "Ejecución", tipologia: "Casa" },
  { ID_Benef: 3003, ID_Proy: "P92", NOMBRES: "Jorge", APELLIDOS: "Contreras Ríos", Estado: "Ejecución", tipologia: "Casa + RC" },
  // Proyecto P87 - Lanco
  { ID_Benef: 4001, ID_Proy: "P87", NOMBRES: "Sergio", APELLIDOS: "Espinoza Vera", Estado: "Ejecución", tipologia: "Casa" },
  { ID_Benef: 4002, ID_Proy: "P87", NOMBRES: "Mónica", APELLIDOS: "Castillo Bravo", Estado: "Ejecución", tipologia: "Casa + RC" },
];

// Despachos de ejemplo (simulan datos reales)
const DESPACHOS_DATA = [
  // Beneficiario 1001 - Muy avanzado, en alerta en gasfitería
  { ID_Benef: 1001, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-08-15", Guia: "G-1001" },
  { ID_Benef: 1001, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-08-25", Guia: "G-1002" },
  { ID_Benef: 1001, Tipo_despacho: "28- Ventanas", Fecha: "2024-09-05", Guia: "G-1003" },
  { ID_Benef: 1001, Tipo_despacho: "03- 2da Etapa Viv.", Fecha: "2024-09-20", Guia: "G-1004" },
  { ID_Benef: 1001, Tipo_despacho: "08- Cerámico Muro", Fecha: "2024-10-05", Guia: "G-1005" },
  // Falta gasfitería - hace 25+ días del cerámico muro = CRÍTICO

  // Beneficiario 1002 - En 2da etapa, en tiempo
  { ID_Benef: 1002, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-10-01", Guia: "G-2001" },
  { ID_Benef: 1002, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-10-12", Guia: "G-2002" },
  { ID_Benef: 1002, Tipo_despacho: "28- Ventanas", Fecha: "2024-10-20", Guia: "G-2003" },
  { ID_Benef: 1002, Tipo_despacho: "03- 2da Etapa Viv.", Fecha: "2024-11-01", Guia: "G-2004" },
  // Esperando cerámico - dentro de tiempo

  // Beneficiario 1003 - En atención (amarillo)
  { ID_Benef: 1003, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-09-01", Guia: "G-3001" },
  { ID_Benef: 1003, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-09-15", Guia: "G-3002" },
  { ID_Benef: 1003, Tipo_despacho: "28- Ventanas", Fecha: "2024-09-25", Guia: "G-3003" },
  // Esperando 2da etapa - hace ~12 días = ATENCIÓN

  // Beneficiario 1004 - Recién iniciado
  { ID_Benef: 1004, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-11-01", Guia: "G-4001" },
  // Esperando 1era etapa - en tiempo

  // Beneficiario 1005 - Sin iniciar aún (solo solicitado)

  // Beneficiario 1006 - Crítico en 1era etapa
  { ID_Benef: 1006, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-09-20", Guia: "G-6001" },
  // Esperando 1era etapa hace mucho = CRÍTICO

  // Proyecto P94
  { ID_Benef: 2001, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-10-10", Guia: "G-7001" },
  { ID_Benef: 2001, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-10-25", Guia: "G-7002" },

  { ID_Benef: 2002, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-10-15", Guia: "G-8001" },
  { ID_Benef: 2002, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-10-28", Guia: "G-8002" },
  { ID_Benef: 2002, Tipo_despacho: "28- Ventanas", Fecha: "2024-11-05", Guia: "G-8003" },

  { ID_Benef: 2003, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-09-25", Guia: "G-9001" },
  // Esperando 1era etapa = CRÍTICO

  { ID_Benef: 2004, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-10-20", Guia: "G-10001" },
  { ID_Benef: 2004, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-11-02", Guia: "G-10002" },

  // Proyecto P92
  { ID_Benef: 3001, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-08-20", Guia: "G-11001" },
  { ID_Benef: 3001, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-09-01", Guia: "G-11002" },
  { ID_Benef: 3001, Tipo_despacho: "28- Ventanas", Fecha: "2024-09-10", Guia: "G-11003" },
  { ID_Benef: 3001, Tipo_despacho: "03- 2da Etapa Viv.", Fecha: "2024-09-25", Guia: "G-11004" },
  { ID_Benef: 3001, Tipo_despacho: "08- Cerámico Muro", Fecha: "2024-10-10", Guia: "G-11005" },
  { ID_Benef: 3001, Tipo_despacho: "13- Gasfitería", Fecha: "2024-10-20", Guia: "G-11006" },
  { ID_Benef: 3001, Tipo_despacho: "11- Sol. AC", Fecha: "2024-10-25", Guia: "G-11007" },
  // COMPLETADO

  { ID_Benef: 3002, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-10-01", Guia: "G-12001" },
  { ID_Benef: 3002, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-10-15", Guia: "G-12002" },

  { ID_Benef: 3003, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-10-05", Guia: "G-13001" },

  // Proyecto P87
  { ID_Benef: 4001, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-10-10", Guia: "G-14001" },
  { ID_Benef: 4001, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-10-25", Guia: "G-14002" },
  { ID_Benef: 4001, Tipo_despacho: "28- Ventanas", Fecha: "2024-11-02", Guia: "G-14003" },

  { ID_Benef: 4002, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-09-15", Guia: "G-15001" },
  { ID_Benef: 4002, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-09-28", Guia: "G-15002" },
  // En atención para 2da etapa
];

// Solicitudes de despacho pendientes
const SOLICITUDES_DATA = [
  { ID_Benef: 1002, Tipo_despacho: "08- Cerámico Muro", Fecha: "2024-11-10", fecha_creacion: "2024-11-05" },
  { ID_Benef: 1003, Tipo_despacho: "03- 2da Etapa Viv.", Fecha: "2024-11-08", fecha_creacion: "2024-11-03" },
  { ID_Benef: 1004, Tipo_despacho: "02- 1era Etapa Viv.", Fecha: "2024-11-12", fecha_creacion: "2024-11-08" },
  { ID_Benef: 1005, Tipo_despacho: "01- Fundaciones Viv.", Fecha: "2024-11-15", fecha_creacion: "2024-11-10" },
  { ID_Benef: 2001, Tipo_despacho: "28- Ventanas", Fecha: "2024-11-08", fecha_creacion: "2024-11-04" },
  { ID_Benef: 3002, Tipo_despacho: "28- Ventanas", Fecha: "2024-11-10", fecha_creacion: "2024-11-06" },
];

// ============================================================================
// FUNCIONES DE UTILIDAD
// ============================================================================

/**
 * Mapea tipo de despacho a código de etapa
 */
const mapearTipoDespacho = (tipo) => {
  if (!tipo) return null;
  const tipoLower = tipo.toLowerCase();

  const mapeo = [
    { patron: "fundacion", etapa: "01_FUNDACIONES" },
    { patron: "1era", etapa: "02_1ERA_ETAPA" },
    { patron: "primera", etapa: "02_1ERA_ETAPA" },
    { patron: "ventana", etapa: "28_VENTANAS" },
    { patron: "2da", etapa: "03_2DA_ETAPA" },
    { patron: "segunda", etapa: "03_2DA_ETAPA" },
    { patron: "ceramico muro", etapa: "08_CERAMICO_MURO" },
    { patron: "muro", etapa: "08_CERAMICO_MURO" },
    { patron: "ceramico piso", etapa: "07_CERAMICO_PISO" },
    { patron: "piso", etapa: "07_CERAMICO_PISO" },
    { patron: "pintura int", etapa: "10_PINTURA_INT" },
    { patron: "pintura ext", etapa: "09_PINTURA_EXT" },
    { patron: "gasfiter", etapa: "13_GASFITERIA" },
    { patron: "eifs", etapa: "29_EIFS" },
    { patron: "aislacion", etapa: "29_EIFS" },
    { patron: "alcantarillado", etapa: "12_ALCANTARILLADO" },
    { patron: "sol. ac", etapa: "11_SOL_AC" },
    { patron: "cocina", etapa: "11_SOL_AC" },
    { patron: "calefont", etapa: "11_SOL_AC" },
  ];

  for (const { patron, etapa } of mapeo) {
    if (tipoLower.includes(patron)) return etapa;
  }
  return null;
};

/**
 * Calcula días transcurridos desde una fecha
 */
const calcularDias = (fecha) => {
  if (!fecha) return null;
  const fechaDate = new Date(fecha);
  const hoy = new Date();
  const diff = hoy - fechaDate;
  return Math.floor(diff / (1000 * 60 * 60 * 24));
};

/**
 * Calcula el estado de etapas para un beneficiario
 */
const calcularEstadoEtapas = (idBenef, despachos, solicitudes) => {
  const despachosbenef = despachos.filter(d => d.ID_Benef === idBenef);
  const solicitudesbenef = solicitudes.filter(s => s.ID_Benef === idBenef);

  // Identificar etapas completadas y sus fechas
  const etapasCompletadas = {};
  despachosbenef.forEach(d => {
    const etapaKey = mapearTipoDespacho(d.Tipo_despacho);
    if (etapaKey) {
      etapasCompletadas[etapaKey] = {
        fecha: d.Fecha,
        guia: d.Guia,
        dias: calcularDias(d.Fecha)
      };
    }
  });

  // Identificar etapas solicitadas
  const etapasSolicitadas = {};
  solicitudesbenef.forEach(s => {
    const etapaKey = mapearTipoDespacho(s.Tipo_despacho);
    if (etapaKey) {
      etapasSolicitadas[etapaKey] = {
        fechaProgramada: s.Fecha,
        fechaCreacion: s.fecha_creacion,
        diasEsperando: calcularDias(s.fecha_creacion)
      };
    }
  });

  const resultado = {};
  const hoy = new Date();

  Object.entries(ETAPAS_CONFIG).forEach(([etapaKey, config]) => {
    const info = {
      key: etapaKey,
      nombre: config.nombre,
      codigo: config.codigo,
      estado: "bloqueado",
      fechaDespacho: null,
      guia: null,
      diasTranscurridos: null,
      diasRestantes: null,
      critico: config.critico,
      solicitado: false
    };

    // Verificar si está despachado
    if (etapasCompletadas[etapaKey]) {
      info.estado = "despachado";
      info.fechaDespacho = etapasCompletadas[etapaKey].fecha;
      info.guia = etapasCompletadas[etapaKey].guia;
      info.diasTranscurridos = etapasCompletadas[etapaKey].dias;
    }
    // Verificar si está solicitado
    else if (etapasSolicitadas[etapaKey]) {
      info.estado = "solicitado";
      info.solicitado = true;
      info.fechaProgramada = etapasSolicitadas[etapaKey].fechaProgramada;
      info.diasEsperando = etapasSolicitadas[etapaKey].diasEsperando;
    }
    // Verificar si puede iniciar
    else {
      const dependencia = config.dependencia;
      let puedeIniciar = config.es_inicio || false;
      let fechaRef = null;

      if (dependencia && etapasCompletadas[dependencia]) {
        puedeIniciar = true;
        fechaRef = etapasCompletadas[dependencia].fecha;
      }

      if (puedeIniciar && fechaRef) {
        // Calcular días efectivos (restando duración de etapa previa)
        const diasBrutos = calcularDias(fechaRef);
        const depConfig = ETAPAS_CONFIG[dependencia] || {};
        const duracionPrevia = depConfig.duracion || 0;
        const diasEfectivos = Math.max(0, diasBrutos - duracionPrevia);

        info.diasTranscurridos = diasEfectivos;

        const tiempoOptimo = config.tiempo_optimo;
        const tiempoAlerta = config.tiempo_alerta;

        if (tiempoOptimo !== null && tiempoAlerta !== null) {
          info.diasRestantes = tiempoAlerta - diasEfectivos;

          if (diasEfectivos <= tiempoOptimo) {
            info.estado = "en_tiempo";
          } else if (diasEfectivos <= tiempoAlerta) {
            info.estado = "atencion";
          } else {
            info.estado = "critico";
          }
        } else {
          info.estado = "en_tiempo";
        }
      } else if (config.es_inicio) {
        info.estado = "en_tiempo";
      }
    }

    resultado[etapaKey] = info;
  });

  return resultado;
};

/**
 * Obtiene última etapa despachada
 */
const getUltimaEtapa = (estadoEtapas) => {
  let ultima = null;
  let maxFecha = null;

  Object.entries(estadoEtapas).forEach(([key, info]) => {
    if (info.estado === "despachado" && info.fechaDespacho) {
      const fecha = new Date(info.fechaDespacho);
      if (!maxFecha || fecha > maxFecha) {
        maxFecha = fecha;
        ultima = info;
      }
    }
  });

  return ultima;
};

/**
 * Obtiene próxima etapa pendiente (crítica)
 */
const getProximaEtapaCritica = (estadoEtapas) => {
  for (const etapaKey of SECUENCIA_PRINCIPAL) {
    const info = estadoEtapas[etapaKey];
    if (info && info.estado !== "despachado") {
      return info;
    }
  }
  return null;
};

/**
 * Calcula avance de vivienda (etapas completadas / total ruta crítica)
 */
const calcularAvance = (estadoEtapas) => {
  const completadas = SECUENCIA_PRINCIPAL.filter(
    key => estadoEtapas[key]?.estado === "despachado"
  ).length;
  return {
    completadas,
    total: SECUENCIA_PRINCIPAL.length,
    porcentaje: Math.round((completadas / SECUENCIA_PRINCIPAL.length) * 100)
  };
};

/**
 * Determina el estado general del beneficiario (el más crítico)
 */
const getEstadoGeneral = (estadoEtapas) => {
  let hayCritico = false;
  let hayAtencion = false;

  Object.values(estadoEtapas).forEach(info => {
    if (info.estado === "critico") hayCritico = true;
    if (info.estado === "atencion") hayAtencion = true;
  });

  if (hayCritico) return "critico";
  if (hayAtencion) return "atencion";
  return "en_tiempo";
};

// ============================================================================
// COMPONENTES UI
// ============================================================================

/**
 * Badge de estado con color
 */
const EstadoBadge = ({ estado, size = "normal" }) => {
  const estilos = {
    despachado: { bg: "bg-blue-500/20", text: "text-blue-400", border: "border-blue-500/30" },
    en_tiempo: { bg: "bg-green-500/20", text: "text-green-400", border: "border-green-500/30" },
    atencion: { bg: "bg-yellow-500/20", text: "text-yellow-400", border: "border-yellow-500/30" },
    critico: { bg: "bg-red-500/20", text: "text-red-400", border: "border-red-500/30" },
    bloqueado: { bg: "bg-gray-500/20", text: "text-gray-400", border: "border-gray-500/30" },
    solicitado: { bg: "bg-purple-500/20", text: "text-purple-400", border: "border-purple-500/30" }
  };

  const iconos = {
    despachado: <CheckCircle2 className="w-3 h-3" />,
    en_tiempo: <Clock className="w-3 h-3" />,
    atencion: <AlertCircle className="w-3 h-3" />,
    critico: <AlertTriangle className="w-3 h-3" />,
    bloqueado: <Clock className="w-3 h-3" />,
    solicitado: <FileText className="w-3 h-3" />
  };

  const estilo = estilos[estado] || estilos.bloqueado;
  const icono = iconos[estado] || iconos.bloqueado;
  const sizeClass = size === "small" ? "text-xs px-1.5 py-0.5" : "text-sm px-2 py-1";

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border ${estilo.bg} ${estilo.text} ${estilo.border} ${sizeClass}`}>
      {icono}
      <span className="capitalize">{estado.replace("_", " ")}</span>
    </span>
  );
};

/**
 * Chip de etapa en el timeline
 */
const EtapaChip = ({ info, showDetails = false }) => {
  const colores = {
    despachado: "bg-blue-500",
    en_tiempo: "bg-green-500",
    atencion: "bg-yellow-500",
    critico: "bg-red-500 animate-pulse",
    bloqueado: "bg-gray-600",
    solicitado: "bg-purple-500"
  };

  const tooltipContent = () => {
    if (info.estado === "despachado") {
      return `${info.nombre}\nGuía: ${info.guia}\nHace ${info.diasTranscurridos} días`;
    }
    if (info.estado === "solicitado") {
      return `${info.nombre}\nSolicitado\nEsperando ${info.diasEsperando} días`;
    }
    if (info.diasTranscurridos !== null) {
      return `${info.nombre}\n${info.diasTranscurridos} días desde etapa anterior`;
    }
    return info.nombre;
  };

  return (
    <div className="relative group">
      <div
        className={`w-8 h-8 rounded-full ${colores[info.estado]} flex items-center justify-center text-white text-xs font-bold cursor-pointer transition-transform hover:scale-110`}
        title={tooltipContent()}
      >
        {info.codigo}
      </div>
      {showDetails && info.estado !== "bloqueado" && (
        <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[10px] text-gray-400 whitespace-nowrap">
          {info.estado === "despachado" && `${info.diasTranscurridos}d`}
          {info.estado === "solicitado" && "📋"}
          {(info.estado === "critico" || info.estado === "atencion") && `${info.diasTranscurridos}d`}
        </div>
      )}
    </div>
  );
};

/**
 * Barra de progreso
 */
const BarraProgreso = ({ porcentaje, size = "normal" }) => {
  const height = size === "small" ? "h-1.5" : "h-2.5";

  let color = "bg-green-500";
  if (porcentaje < 30) color = "bg-red-400";
  else if (porcentaje < 60) color = "bg-yellow-400";
  else if (porcentaje < 90) color = "bg-blue-400";

  return (
    <div className={`w-full bg-gray-700 rounded-full ${height} overflow-hidden`}>
      <div
        className={`${height} ${color} rounded-full transition-all duration-500`}
        style={{ width: `${porcentaje}%` }}
      />
    </div>
  );
};

/**
 * Card de KPI
 */
const KPICard = ({ titulo, valor, icono: Icono, color, subtitulo }) => {
  const colores = {
    green: "from-green-500/20 to-green-600/5 border-green-500/30 text-green-400",
    yellow: "from-yellow-500/20 to-yellow-600/5 border-yellow-500/30 text-yellow-400",
    red: "from-red-500/20 to-red-600/5 border-red-500/30 text-red-400",
    blue: "from-blue-500/20 to-blue-600/5 border-blue-500/30 text-blue-400",
    gray: "from-gray-500/20 to-gray-600/5 border-gray-500/30 text-gray-400"
  };

  return (
    <div className={`bg-gradient-to-br ${colores[color]} border rounded-xl p-4`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-400 text-sm">{titulo}</p>
          <p className="text-2xl font-bold text-white mt-1">{valor}</p>
          {subtitulo && <p className="text-xs text-gray-500 mt-1">{subtitulo}</p>}
        </div>
        <div className={`p-3 rounded-lg bg-black/20`}>
          <Icono className="w-6 h-6" />
        </div>
      </div>
    </div>
  );
};

/**
 * Card de vivienda/beneficiario
 */
const ViviendaCard = ({ beneficiario, estadoEtapas, expanded, onToggle }) => {
  const avance = calcularAvance(estadoEtapas);
  const estadoGeneral = getEstadoGeneral(estadoEtapas);
  const ultimaEtapa = getUltimaEtapa(estadoEtapas);
  const proximaEtapa = getProximaEtapaCritica(estadoEtapas);

  const borderColor = {
    critico: "border-red-500/50 shadow-red-500/20",
    atencion: "border-yellow-500/50 shadow-yellow-500/20",
    en_tiempo: "border-green-500/30"
  };

  return (
    <div className={`bg-gray-800/50 border ${borderColor[estadoGeneral]} rounded-xl overflow-hidden shadow-lg transition-all duration-300 hover:shadow-xl`}>
      {/* Header clickeable */}
      <div
        className="p-4 cursor-pointer hover:bg-gray-700/30 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {expanded ? (
              <ChevronDown className="w-5 h-5 text-gray-400" />
            ) : (
              <ChevronRight className="w-5 h-5 text-gray-400" />
            )}
            <div className="flex items-center gap-2">
              {beneficiario.tipologia.includes("RC") ? (
                <Building2 className="w-5 h-5 text-blue-400" />
              ) : (
                <Home className="w-5 h-5 text-gray-400" />
              )}
              <div>
                <h3 className="font-semibold text-white">
                  {beneficiario.APELLIDOS}
                </h3>
                <p className="text-xs text-gray-400">{beneficiario.tipologia}</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Avance */}
            <div className="text-right">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-400">{avance.completadas}/{avance.total}</span>
                <span className="text-lg font-bold text-white">{avance.porcentaje}%</span>
              </div>
              <div className="w-24">
                <BarraProgreso porcentaje={avance.porcentaje} size="small" />
              </div>
            </div>

            {/* Estado badge */}
            <EstadoBadge estado={estadoGeneral} />
          </div>
        </div>

        {/* Timeline mini */}
        <div className="mt-4 flex items-center gap-1">
          {SECUENCIA_PRINCIPAL.map((etapaKey, idx) => {
            const info = estadoEtapas[etapaKey];
            return (
              <React.Fragment key={etapaKey}>
                <EtapaChip info={info} showDetails={false} />
                {idx < SECUENCIA_PRINCIPAL.length - 1 && (
                  <div className={`flex-1 h-0.5 ${
                    info?.estado === "despachado" ? "bg-blue-500" : "bg-gray-600"
                  }`} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Última actividad y alerta */}
        <div className="mt-3 flex items-center justify-between text-sm">
          <div className="text-gray-400">
            {ultimaEtapa ? (
              <>
                <span>Última: </span>
                <span className="text-white">{ultimaEtapa.nombre}</span>
                <span className="text-gray-500"> — Guía #{ultimaEtapa.guia?.replace("G-", "")} — </span>
                <span className={`font-medium ${
                  estadoGeneral === "critico" ? "text-red-400" :
                  estadoGeneral === "atencion" ? "text-yellow-400" : "text-green-400"
                }`}>
                  hace {ultimaEtapa.diasTranscurridos} días
                </span>
              </>
            ) : (
              <span className="text-yellow-400">Sin despachos registrados</span>
            )}
          </div>

          {/* Inspección placeholder */}
          <div className="flex items-center gap-1 text-gray-500">
            <Eye className="w-4 h-4" />
            <span>Insp: 0%</span>
          </div>
        </div>

        {/* Alerta si está crítico */}
        {estadoGeneral === "critico" && proximaEtapa && (
          <div className="mt-3 p-2 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="flex items-center gap-2 text-red-400 text-sm">
              <AlertTriangle className="w-4 h-4 animate-pulse" />
              <span>
                {proximaEtapa.nombre} atrasado {proximaEtapa.diasTranscurridos - 14} días —
                ¿Por qué no se ha solicitado?
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Panel expandido */}
      {expanded && (
        <div className="border-t border-gray-700 p-4 bg-gray-900/30">
          {/* Timeline detallado */}
          <div className="mb-4">
            <h4 className="text-sm font-medium text-gray-300 mb-3">Detalle de Etapas</h4>
            <div className="space-y-2">
              {Object.entries(estadoEtapas).map(([key, info]) => (
                <div key={key} className="flex items-center gap-3 text-sm">
                  <EtapaChip info={info} showDetails={false} />
                  <span className="text-gray-300 flex-1">{info.nombre}</span>
                  <span className="text-gray-500">
                    {info.estado === "despachado" && `Guía ${info.guia} — ${info.diasTranscurridos}d`}
                    {info.estado === "solicitado" && `Solicitado — esperando ${info.diasEsperando}d`}
                    {info.estado === "en_tiempo" && info.diasTranscurridos !== null && `${info.diasTranscurridos}d transcurridos`}
                    {info.estado === "atencion" && `⚠️ ${info.diasTranscurridos}d — quedan ${info.diasRestantes}d`}
                    {info.estado === "critico" && `🔴 ${info.diasTranscurridos}d — ${Math.abs(info.diasRestantes)}d de atraso`}
                    {info.estado === "bloqueado" && "Bloqueado"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Historial de despachos */}
          <div>
            <h4 className="text-sm font-medium text-gray-300 mb-2">Historial de Despachos</h4>
            <div className="bg-gray-800/50 rounded-lg p-3">
              {DESPACHOS_DATA.filter(d => d.ID_Benef === beneficiario.ID_Benef).length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-gray-500 text-left">
                      <th className="pb-2">Fecha</th>
                      <th className="pb-2">Etapa</th>
                      <th className="pb-2">Guía</th>
                      <th className="pb-2 text-right">Días</th>
                    </tr>
                  </thead>
                  <tbody className="text-gray-300">
                    {DESPACHOS_DATA
                      .filter(d => d.ID_Benef === beneficiario.ID_Benef)
                      .sort((a, b) => new Date(b.Fecha) - new Date(a.Fecha))
                      .map((d, idx) => (
                        <tr key={idx} className="border-t border-gray-700/50">
                          <td className="py-2">{new Date(d.Fecha).toLocaleDateString('es-CL')}</td>
                          <td className="py-2">{d.Tipo_despacho}</td>
                          <td className="py-2">{d.Guia}</td>
                          <td className="py-2 text-right text-gray-500">{calcularDias(d.Fecha)}d</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-gray-500 text-center py-2">Sin despachos registrados</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// COMPONENTE PRINCIPAL
// ============================================================================

const DashboardObras = () => {
  // Estados
  const [proyectoSeleccionado, setProyectoSeleccionado] = useState(PROYECTOS_DATA[0]?.ID_proy || "");
  const [busqueda, setBusqueda] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("todos");
  const [viviendaExpandida, setViviendaExpandida] = useState(null);

  // Datos filtrados del proyecto
  const beneficiariosProyecto = useMemo(() => {
    return BENEFICIARIOS_DATA.filter(b => b.ID_Proy === proyectoSeleccionado);
  }, [proyectoSeleccionado]);

  // Calcular estados de todas las viviendas
  const viviendasConEstado = useMemo(() => {
    return beneficiariosProyecto.map(benef => {
      const estadoEtapas = calcularEstadoEtapas(benef.ID_Benef, DESPACHOS_DATA, SOLICITUDES_DATA);
      const estadoGeneral = getEstadoGeneral(estadoEtapas);
      const avance = calcularAvance(estadoEtapas);

      return {
        ...benef,
        estadoEtapas,
        estadoGeneral,
        avance
      };
    });
  }, [beneficiariosProyecto]);

  // Filtrar por búsqueda y estado
  const viviendasFiltradas = useMemo(() => {
    return viviendasConEstado.filter(v => {
      // Filtro de búsqueda
      if (busqueda) {
        const termino = busqueda.toLowerCase();
        const nombre = `${v.NOMBRES} ${v.APELLIDOS}`.toLowerCase();
        if (!nombre.includes(termino)) return false;
      }

      // Filtro de estado
      if (filtroEstado !== "todos" && v.estadoGeneral !== filtroEstado) {
        return false;
      }

      return true;
    });
  }, [viviendasConEstado, busqueda, filtroEstado]);

  // KPIs del proyecto
  const kpis = useMemo(() => {
    const total = viviendasConEstado.length;
    const enTiempo = viviendasConEstado.filter(v => v.estadoGeneral === "en_tiempo").length;
    const atencion = viviendasConEstado.filter(v => v.estadoGeneral === "atencion").length;
    const criticos = viviendasConEstado.filter(v => v.estadoGeneral === "critico").length;

    const avancePromedio = total > 0
      ? Math.round(viviendasConEstado.reduce((sum, v) => sum + v.avance.porcentaje, 0) / total)
      : 0;

    return { total, enTiempo, atencion, criticos, avancePromedio };
  }, [viviendasConEstado]);

  // Proyecto actual
  const proyectoActual = PROYECTOS_DATA.find(p => p.ID_proy === proyectoSeleccionado);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-slate-900 to-zinc-900 text-white">
      {/* Header */}
      <header className="bg-gray-900/80 backdrop-blur-sm border-b border-gray-800 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-red-600 rounded-lg">
                <Building2 className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight">Panel de Control de Obras</h1>
                <p className="text-xs text-gray-400">SCRaices — Sistema de Control</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {/* Selector de proyecto */}
              <select
                value={proyectoSeleccionado}
                onChange={(e) => setProyectoSeleccionado(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {PROYECTOS_DATA.map(p => (
                  <option key={p.ID_proy} value={p.ID_proy}>
                    {p.NOMBRE_PROYECTO}
                  </option>
                ))}
              </select>

              {/* Botón sync */}
              <button className="p-2 bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-700 transition-colors">
                <RefreshCw className="w-5 h-5 text-gray-400" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* Info del proyecto */}
        <div className="mb-6">
          <div className="flex items-center gap-2 text-gray-400 text-sm mb-1">
            <Calendar className="w-4 h-4" />
            <span>Grupo: {proyectoActual?.COMUNA}</span>
            <span className="text-gray-600">•</span>
            <span>Código: {proyectoActual?.ID_proy}</span>
          </div>
          <h2 className="text-2xl font-bold">{proyectoActual?.NOMBRE_PROYECTO}</h2>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <KPICard
            titulo="Total Viviendas"
            valor={kpis.total}
            icono={Home}
            color="blue"
            subtitulo="en ejecución"
          />
          <KPICard
            titulo="En Tiempo"
            valor={kpis.enTiempo}
            icono={CheckCircle2}
            color="green"
            subtitulo="sin alertas"
          />
          <KPICard
            titulo="Atención"
            valor={kpis.atencion}
            icono={AlertCircle}
            color="yellow"
            subtitulo="próximos a vencer"
          />
          <KPICard
            titulo="Críticos"
            valor={kpis.criticos}
            icono={AlertTriangle}
            color="red"
            subtitulo="requieren acción"
          />
          <div className="col-span-2 md:col-span-1">
            <div className="bg-gradient-to-br from-gray-700/20 to-gray-800/5 border border-gray-600/30 rounded-xl p-4">
              <p className="text-gray-400 text-sm mb-2">Avance del Grupo</p>
              <div className="flex items-end gap-2">
                <span className="text-3xl font-bold">{kpis.avancePromedio}%</span>
                <TrendingUp className="w-5 h-5 text-green-400 mb-1" />
              </div>
              <div className="mt-2">
                <BarraProgreso porcentaje={kpis.avancePromedio} />
              </div>
            </div>
          </div>
        </div>

        {/* Filtros y búsqueda */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          {/* Búsqueda */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
            <input
              type="text"
              placeholder="Buscar beneficiario..."
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Filtro de estado */}
          <div className="flex items-center gap-2">
            <Filter className="w-5 h-5 text-gray-500" />
            <div className="flex gap-1 bg-gray-800 border border-gray-700 rounded-lg p-1">
              {[
                { key: "todos", label: "Todos", color: "gray" },
                { key: "critico", label: "Críticos", color: "red" },
                { key: "atencion", label: "Atención", color: "yellow" },
                { key: "en_tiempo", label: "En tiempo", color: "green" }
              ].map(({ key, label, color }) => (
                <button
                  key={key}
                  onClick={() => setFiltroEstado(key)}
                  className={`px-3 py-1.5 rounded text-sm transition-colors ${
                    filtroEstado === key
                      ? `bg-${color}-500/30 text-${color}-400 border border-${color}-500/50`
                      : "text-gray-400 hover:bg-gray-700"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Lista de viviendas */}
        <div className="space-y-4">
          {viviendasFiltradas.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Users className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No se encontraron viviendas con los filtros aplicados</p>
            </div>
          ) : (
            viviendasFiltradas
              // Ordenar: críticos primero, luego atención, luego en tiempo
              .sort((a, b) => {
                const orden = { critico: 0, atencion: 1, en_tiempo: 2 };
                return orden[a.estadoGeneral] - orden[b.estadoGeneral];
              })
              .map(vivienda => (
                <ViviendaCard
                  key={vivienda.ID_Benef}
                  beneficiario={vivienda}
                  estadoEtapas={vivienda.estadoEtapas}
                  expanded={viviendaExpandida === vivienda.ID_Benef}
                  onToggle={() => setViviendaExpandida(
                    viviendaExpandida === vivienda.ID_Benef ? null : vivienda.ID_Benef
                  )}
                />
              ))
          )}
        </div>

        {/* Leyenda */}
        <div className="mt-8 p-4 bg-gray-800/30 border border-gray-700/50 rounded-xl">
          <h4 className="text-sm font-medium text-gray-300 mb-3">Leyenda de Estados</h4>
          <div className="flex flex-wrap gap-4 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full bg-blue-500" />
              <span className="text-gray-400">Despachado</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full bg-purple-500" />
              <span className="text-gray-400">Solicitado</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full bg-green-500" />
              <span className="text-gray-400">En tiempo (&lt;7 días)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full bg-yellow-500" />
              <span className="text-gray-400">Atención (7-14 días)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full bg-red-500 animate-pulse" />
              <span className="text-gray-400">Crítico (&gt;14 días sin solicitud)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full bg-gray-600" />
              <span className="text-gray-400">Bloqueado (dependencia pendiente)</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-8 text-center text-gray-500 text-sm">
          <p>SCRaices — Panel de Control de Obras v1.0</p>
          <p className="text-xs mt-1">Última actualización: {new Date().toLocaleString('es-CL')}</p>
        </footer>
      </main>
    </div>
  );
};

export default DashboardObras;

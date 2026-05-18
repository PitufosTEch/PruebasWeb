# Etapas de Construcción - Sistema de Control y Predicción

## Configuración de Tiempos

> **Para modificar tiempos:** Editar el archivo `config/etapas_config.json`

### Semáforo de Estados

| Color | Estado | Condición |
|-------|--------|-----------|
| 🟢 Verde | EN TIEMPO | `días_transcurridos <= tiempo_optimo` |
| 🟡 Amarillo | ATENCIÓN | `tiempo_optimo < días_transcurridos <= tiempo_alerta` |
| 🔴 Rojo | CRÍTICO | `días_transcurridos > tiempo_alerta` |
| ⚪ Gris | BLOQUEADO | Falta etapa previa obligatoria |
| 🔵 Azul | COMPLETADO | Etapa despachada |

---

## Etapas de Vivienda (Configurables)

| Código | Etapa | Duración | T. Óptimo | T. Alerta | Dependencia |
|--------|-------|----------|-----------|-----------|-------------|
| 01 | Fundaciones Viv. | 3 días | - | - | Inicio |
| 04 | Radier | 7 días | 3 días | 7 días | 01-Fundaciones |
| 02 | 1era Etapa Viv. | 21 días | 3 días | 7 días | 04-Radier |
| 28 | Ventanas | 1 día | 3 días | **7 días** | 02-1era Etapa |
| 29 | EIFS (Aislación) | 3 días | 7 días | 14 días | 02-1era Etapa |
| 03 | 2da Etapa Viv. | 10 días | 21 días | 28 días | 02-1era Etapa |
| 07 | Cerámicos Piso | 7 días | 15 días | 30 días* | 02-1era Etapa |
| 09 | Pintura Exterior | 7 días | 15 días | 30 días* | 02-1era Etapa |
| 08 | Cerámicos Muro | 3 días | 3 días | 7 días | 03-2da Etapa |
| 10 | Pintura Interior | 7 días | 3 días | 10 días | 03-2da Etapa |
| 13 | Gasfitería Interior | 5 días | 3 días | 7 días | 08-Cerámico Muro |
| 11 | Sol. AC | 3 días | 3 días | 7 días | 08-Cerámico Muro |
| 30 | Quincallería Viv. | 2 días | 3 días | 7 días | 10+13 (ambas) |
| 12 | Alcantarillado Ext. | 3 días | - | - | 01-Fundaciones |

> *Cerámicos Piso y Pintura Exterior: Ventana flexible desde día 15 post-1era Etapa hasta 20 días post-2da Etapa

---

## Secuencia Principal (Columna Vertebral)

```
FUNDACIONES ──▶ RADIER ──▶ 1ERA ETAPA ──▶ 2DA ETAPA ──▶ CERÁM. MURO ──▶ GASFITERÍA ──▶ QUINCALLERÍA
    3d            7d          21d           10d            3d              5d              2d

                                                                          Total: ~54 días
```

---

## Diagrama de Dependencias

```
                                    ┌─── VENTANAS (28) ─────── [CRÍTICO: máx 7 días]
                                    │
                                    ├─── EIFS (29)
FUNDACIONES ─── RADIER ─── 1ERA ────┤
    (01)         (04)      ETAPA    ├─── CERÁM. PISO (07) ──┐
                           (02)     │                       │
      │                             ├─── PINTURA EXT (09) ──┤
      │                             │                       │
      │                             └─── 2DA ETAPA (03) ────┼─── CERÁM. MURO (08) ─┬─ GASFITERÍA (13) ─┐
      │                                                     │                      │                   │
      │                                                     └─── PINTURA INT (10) ─┤    SOL.AC (11) ───┤
      │                                                                            │                   │
      └─── ALCANTARILLADO (12)                                                     └───────────────────┴─── QUINCALLERÍA (30)
           [Flexible]
```

---

## Reglas de Alerta

### 🔴 Alertas Críticas (Requieren acción inmediata)

1. **VENTANAS sin despachar** → Si pasan **7 días** desde 1era Etapa
2. **2DA ETAPA sin iniciar** → Si pasan **28 días** desde 1era Etapa
3. **GASFITERÍA sin despachar** → Si pasan **7 días** desde Cerámico Muro

### 🟡 Alertas de Precaución

1. **Cualquier etapa** que supere su `tiempo_optimo` pero no alcance `tiempo_alerta`
2. **Etapas flexibles** (Cerámico Piso, Pintura Ext) acercándose al límite

---

## Notas de Implementación

- **Tiempo Óptimo**: Días esperados para despachar la siguiente etapa (meta)
- **Tiempo Alerta**: Días máximos antes de considerar crítico (límite)
- **Duración**: Tiempo que toma ejecutar la etapa en obra
- Los tiempos se cuentan desde la **fecha de despacho** de la etapa previa

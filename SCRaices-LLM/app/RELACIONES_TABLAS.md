# Documentacion de Relaciones entre Tablas - SCRaices

Este documento describe las relaciones entre las tablas principales del sistema SCRaices.
Generado a partir de "Application Documentation.html".

---

## DIAGRAMA DE RELACIONES PRINCIPALES

```
                            +------------------+
                            |    PROYECTOS     |
                            |------------------|
                            | PK: ID_proy      |
                            | NOMBRE_PROYECTO  |
                            | COMUNA           |
                            | PERIODO          |
                            | estado_general   |
                            +--------+---------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
+------------------+       +------------------+       +------------------+
|   BENEFICIARIO   |       |    EJECUCION     |       |     DESPACHO     |
|------------------|       |------------------|       |------------------|
| PK: ID_Benef     |       | PK: IDU_E        |       | PK: IDU_desp     |
| FK: ID_Proy      |       | FK: ID_benef     |       | FK: ID_Benef     |
| Nombre           |       | FK: ID_Proy      |       | FK: ID_proy      |
| RUT              |       | F_INICIO         |       | Tipo_despacho    |
| COMUNA           |       | E_Obra           |       | Fecha            |
| Estado           |       +--------+---------+       | Guia             |
+--------+---------+                |                 +------------------+
         |                          |
         |                          v
         |                +------------------+
         |                |   RESUMEN_INSP   |
         |                |------------------|
         |                | PK: ID_U         |
         |                | FK: ID_Benef     |
         |                | T_A_Fundacion    |
         |                | T_A_Radier       |
         |                | T_A_Tabiques     |
         |                +------------------+
         |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
+------------------+       +------------------+       +------------------+
|  LEVANTAMIENTO   |       |  DOCUMENTACION   |       |    POSTVENTA     |
|------------------|       |------------------|       |------------------|
| PK: IDU_L        |       | PK: IDU_docs     |       | PK: ID_PV        |
| FK: ID_Benef     |       | FK: ID_proy      |       | FK: ID_Proy      |
| FK: ID_proy      |       | FK: ID_benef     |       | FK: ID_Benef     |
| Fecha            |       | carnet           |       | Fecha            |
| COORDENADAS      |       | contrato         |       +------------------+
| FUENTE_AGUA      |       | C_permiso        |
+------------------+       +------------------+
```

---

## TABLAS PRINCIPALES

### 1. PROYECTOS (Tabla Central)
**Descripcion:** Informacion general de los proyectos de vivienda social.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `ID_proy` | PK | Identificador unico del proyecto (ej: P01, P02) |
| `Cod_obra` | Text | Codigo de obra |
| `NOMBRE_PROYECTO` | Text | Nombre descriptivo del proyecto |
| `COMUNA` | Text | Comuna donde se ubica |
| `PERIODO` | Text | Periodo o ano del proyecto |
| `estado_general` | Text | Estado: En ejecucion, Terminado, etc. |
| `Encargado` | Ref->usuarios | Usuario encargado del proyecto |
| `Jefe_ob1` | Ref->usuarios | Jefe de obra 1 |
| `Jefe_ob_2` | Ref->usuarios | Jefe de obra 2 |
| `Social` | Ref->usuarios | Encargado social |
| `TIPOLOGIA 1-7` | Text | Tipologias de vivienda disponibles |

**Tablas que referencian a Proyectos:** Beneficiario, Levantamiento, Ejecucion, Despacho, documentacion, controlEEPP, Tipologias, Montos, Solpago, Pendientes, postventa, Seguimiento, y 90+ mas.

---

### 2. BENEFICIARIO
**Descripcion:** Datos de los beneficiarios (familias) que recibiran viviendas.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `ID_Benef` | PK | Identificador unico del beneficiario |
| `ID_Proy` | Ref->Proyectos | Proyecto al que pertenece |
| `Cod_Obra` | Text | Codigo de obra |
| `Estado` | Text | Estado del beneficiario |
| `Habil para construir` | Bool | Si esta habilitado para iniciar construccion |
| `steelframe` | Bool | Si es construccion steel frame |
| `NOMBRES` | Text | Nombres del beneficiario |
| `APELLIDOS` | Text | Apellidos del beneficiario |
| `RUT` | Text | RUT del beneficiario |
| `COMUNA` | Text | Comuna de residencia |

**Tablas que referencian a Beneficiario:** Levantamiento, Ejecucion, Despacho, documentacion, Resumen_insp, postventa, controlEEPP, Seguimiento, cominsp, y 50+ mas.

---

### 3. EJECUCION (Avance de Obras)
**Descripcion:** Registro del avance de ejecucion de obras por beneficiario.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `IDU_E` | PK | Identificador unico de ejecucion |
| `ID_benef` | Ref->Beneficiario | **NOTA: minuscula en 'benef'** |
| `ID_Proy` | Ref->Proyectos | Proyecto asociado |
| `Fecha_creacion` | DateTime | Fecha de creacion del registro |
| `F_INICIO` | Date | Fecha de inicio de obras |
| `E_Obra` | Text | Estado de la obra |
| `C_Carp` | ? | [DUDA: Carpeta? Carpinteria?] |
| `C_rad` | ? | [DUDA: Radier?] |
| `alerta_logist` | Bool | Alerta de logistica |

**DUDA:** No veo columna explicita de "porcentaje de avance". Puede estar en `Resumen_insp` o calcularse.

---

### 4. LEVANTAMIENTO
**Descripcion:** Datos del levantamiento tecnico inicial del terreno.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `IDU_L` | PK | Identificador unico de levantamiento |
| `ID_Benef` | Ref->Beneficiario | Beneficiario asociado |
| `ID_proy` | Ref->Proyectos | **NOTA: minuscula en 'proy'** |
| `Fecha` | DateTime | Fecha del levantamiento |
| `Usuario` | Text | Usuario que registro |
| `Creador` | Ref->usuarios | Usuario creador |
| `COORDENADAS` | LatLong | Coordenadas del terreno |
| `N_ROL` | Text | Numero de rol |
| `FUENTE_AGUA` | Text | Fuente de agua potable |
| `Nom_APR` | Ref->APR | Nombre del APR (Agua Potable Rural) |
| `ELECTRICIDAD` | Text | Situacion electrica |
| `ALCANT` | Text | Alcantarillado |
| `CALICATA` | Text | Informacion de calicata |
| `image1-10` | Image | Fotos del terreno |

---

### 5. DESPACHO
**Descripcion:** Registro de despachos de materiales a beneficiarios.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `IDU_desp` | PK | Identificador unico del despacho |
| `ID_Benef` | Ref->Beneficiario | Beneficiario destinatario |
| `ID_proy` | Ref->Proyectos | **NOTA: minuscula en 'proy'** |
| `Cod_obra` | Text | Codigo de obra |
| `usuario` | Text | Usuario que registro |
| `Tipo_despacho` | Text | Tipo de despacho |
| `Tipo_pendiente` | Text | Tipo de pendiente |
| `Fecha` | Date | Fecha del despacho |
| `Guia` | Text | Numero de guia |
| `Camion` | Text | Identificacion del camion |
| `Chofer` | Text | Nombre del chofer |
| `Observaciones` | Text | Observaciones |
| `Image1`, `Image2` | Image | Fotos del despacho |
| `soldesp` | ? | [DUDA: Referencia a soldepacho?] |
| `V_fundacion_viv` | ? | [DUDA: Verificacion fundacion vivienda?] |
| `V_1eraet_viv` | ? | [DUDA: Verificacion 1era etapa?] |

---

### 6. DOCUMENTACION (Documentos por Beneficiario)
**Descripcion:** Control de documentacion legal y administrativa por beneficiario.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `IDU_docs` | PK | Identificador unico |
| `ID_proy` | Ref->Proyectos | Proyecto |
| `ID_benef` | Ref->Beneficiario | **NOTA: minuscula en 'benef'** |
| `IDU_L` | Ref->Levantamiento | Levantamiento asociado |
| `carnet` | Bool/File | Carnet de identidad |
| `contrato` | Bool/File | Contrato firmado |
| `mod_contrato` | Bool/File | Modificacion de contrato |
| `C_disc` | Bool | Certificado discapacidad |
| `C_RSH` | Bool | Registro Social de Hogares |
| `C_ahorro` | Bool | Certificado de ahorro |
| `C_matrimonio` | Bool | Certificado de matrimonio |
| `C_Infprev` | Bool | Informe previsional |
| `C_Fact_AP` | Bool | Factura agua potable |
| `C_Fact_elect` | Bool | Factura electricidad |
| `C_dominio` | Bool | Certificado de dominio |
| `C_permiso` | Bool | Permiso de edificacion |
| `C_recepcion` | Bool | Recepcion municipal |

---

### 7. RESUMEN_INSP (Inspecciones)
**Descripcion:** Resumen de inspecciones tecnicas y avances por partida.

| Columna | Tipo | Descripcion |
|---------|------|-------------|
| `ID_U` | PK | Identificador unico |
| `ID_Benef` | Ref->Beneficiario | Beneficiario inspeccionado |
| `Nombre` | Text | Nombre del beneficiario |
| `Proyecto` | Text | Nombre del proyecto |
| `titulo 1-3` | Text | Titulos de seccion |
| `marcador` | Number | Marcador de avance |
| `total_marcador` | Number | Total del marcador |
| `T_A_Fundacion` | Number | Avance fundacion |
| `T_A_Radier` | Number | Avance radier |
| `T_A_Planta_Alc` | Number | Avance planta alcantarillado |
| `T_A_E_Tabiques` | Number | Avance tabiques |
| `T_A_E_Techumbre` | Number | Avance techumbre |
| `T_A_rev Ext` | Number | Avance revestimiento exterior |
| `T_A_vent` | Number | Avance ventanas |
| `T_A_Cubierta` | Number | Avance cubierta |
| `T_A_Ent_Cielo` | Number | Avance cielo |

**NOTA:** Esta tabla parece contener el avance real por partida de construccion.

---

## RELACIONES CONFIRMADAS

```
Proyectos.ID_proy <-- Beneficiario.ID_Proy
Proyectos.ID_proy <-- Levantamiento.ID_proy
Proyectos.ID_proy <-- Ejecucion.ID_Proy
Proyectos.ID_proy <-- Despacho.ID_proy
Proyectos.ID_proy <-- documentacion.ID_proy

Beneficiario.ID_Benef <-- Levantamiento.ID_Benef
Beneficiario.ID_Benef <-- Ejecucion.ID_benef      (minuscula!)
Beneficiario.ID_Benef <-- Despacho.ID_Benef
Beneficiario.ID_Benef <-- documentacion.ID_benef  (minuscula!)
Beneficiario.ID_Benef <-- Resumen_insp.ID_Benef
Beneficiario.ID_Benef <-- postventa.ID_Benef

usuarios.email <-- Proyectos.Encargado
usuarios.email <-- Levantamiento.Creador
```

---

## DUDAS PENDIENTES (Revisar con Usuario)

### 1. Avance de Obras
- [ ] La columna de avance porcentual: esta en `Resumen_insp.marcador` o en otra tabla?
- [ ] Que significa `E_Obra` en Ejecucion? Es el estado de obra?
- [ ] Las columnas `C_Carp`, `C_rad` en Ejecucion que representan?

### 2. Despachos
- [ ] Cual es la diferencia entre `Despacho`, `soldepacho`, y `DetalleDespacho`?
- [ ] Las columnas `V_fundacion_viv`, `V_1eraet_viv` son verificaciones?

### 3. Inspecciones
- [ ] `Resumen_insp` es el resumen de inspecciones de avance de obra?
- [ ] Existe otra tabla de inspecciones mas detallada?
- [ ] `cominsp` que registra?

### 4. Case Sensitivity (IMPORTANTE!)
- [ ] Algunas FKs usan `ID_benef` (minuscula) y otras `ID_Benef` (mayuscula)
- [ ] Lo mismo con `ID_proy` vs `ID_Proy`
- [ ] Debo manejar ambos casos en las consultas?

---

## CONSULTAS DE EJEMPLO

### Beneficiarios por Proyecto
```python
dm.get_table_data("Beneficiario").groupby("ID_Proy").size().reset_index(name="Cantidad")
```

### Avance de Inspecciones por Beneficiario
```python
dm.get_table_data("Resumen_insp")[["ID_Benef", "Nombre", "Proyecto", "T_A_Fundacion", "T_A_Radier", "T_A_Tabiques"]]
```

### Despachos por Proyecto
```python
dm.get_table_data("Despacho").groupby("ID_proy")["IDU_desp"].count().reset_index(name="Total_Despachos")
```

### Documentacion Pendiente
```python
docs = dm.get_table_data("documentacion")
docs[docs["C_permiso"] == False][["ID_benef", "carnet", "contrato", "C_permiso"]]
```

---

*Ultima actualizacion: Generado automaticamente desde Application Documentation.html*

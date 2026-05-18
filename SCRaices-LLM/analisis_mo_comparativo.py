"""
Análisis Comparativo: M.O Base vs Pagos Reales
Proyecto: Com. Pedro Antivil - Versión 4
"""
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from fpdf import FPDF
from datetime import datetime
import os

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds = Credentials.from_service_account_file('credentials/service_account.json', scopes=SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key('1JAxxP9W6LJzns5rmGIo7mfk227qMLwsq-gFMCvHU0Zk')

ID_PROY = '122'
NOMBRE_PROY = 'Com. Pedro Antivil'

# === 1. OBTENER DATOS ===
print("Obteniendo datos...")

# Tipologías del proyecto
ws_tip = spreadsheet.worksheet('Tipologias')
tip_data = ws_tip.get_all_values()
df_tip = pd.DataFrame(tip_data[1:], columns=tip_data[0])
tip_proy = df_tip[df_tip['ID_proy'] == ID_PROY].copy()

# Crear diccionario de tipologías e identificar IDs de RC
tipologias_dict = {}
rc_tipologia_ids = set()  # IDs de tipologías que son R.Comp

for idx, row in tip_proy.iterrows():
    if row['Familia'] == 'Vivienda':
        desc = f"Vivienda {row['dormitorios']}D {row['plantas']}P {row['caracterizacion']}"
        tipo = 'Vivienda'
    else:
        desc = f"R.C. {row['caracterizacion']}"
        tipo = 'R.Comp'
        rc_tipologia_ids.add(row['IDU_tipol'])
    tipologias_dict[row['IDU_tipol']] = {'descripcion': desc, 'tipo': tipo}

print(f"Tipologías: {len(tipologias_dict)}, RC IDs: {rc_tipologia_ids}")

# Beneficiarios del proyecto
ws_ben = spreadsheet.worksheet('Beneficiario')
ben_data = ws_ben.get_all_values()
df_ben = pd.DataFrame(ben_data[1:], columns=ben_data[0])
ben_proy = df_ben[df_ben['ID_Proy'] == ID_PROY].copy()

# Crear lista de beneficiarios
beneficiarios = []
for idx, row in ben_proy.iterrows():
    apellido = row['APELLIDOS'].split()[0] if row['APELLIDOS'] else ''
    inicial = row['NOMBRES'].split()[0][0] if row['NOMBRES'] else ''
    nombre_corto = f"{apellido} {inicial}."

    beneficiarios.append({
        'id': row['ID_Benef'],
        'nombre': nombre_corto,
        'nombre_completo': f"{row['NOMBRES']} {row['APELLIDOS']}",
        'tipologia_viv': row.get('Tipologia Vivienda', ''),
        'tipologia_rc': row.get('Tipologia RC', '')
    })

print(f"Beneficiarios: {len(beneficiarios)}")

# Contar viviendas y RC por tipología
viviendas_por_tip = {}
rc_por_tip = {}
for ben in beneficiarios:
    tip_viv = ben['tipologia_viv']
    tip_rc = ben['tipologia_rc']
    if tip_viv:
        viviendas_por_tip[tip_viv] = viviendas_por_tip.get(tip_viv, 0) + 1
    if tip_rc:
        rc_por_tip[tip_rc] = rc_por_tip.get(tip_rc, 0) + 1

total_viviendas = sum(viviendas_por_tip.values())
total_rc = sum(rc_por_tip.values())
print(f"Viviendas: {total_viviendas}, RC: {total_rc}")

# Tabla M.O Base
ws_base = spreadsheet.worksheet('Tabla_pago')
base_data = ws_base.get_all_values()
df_base = pd.DataFrame(base_data[1:], columns=base_data[0])
mo_base = df_base[df_base['ID_proy'] == ID_PROY].copy()

# Pagos Reales
ws_pagos = spreadsheet.worksheet('Solpago')
pagos_data = ws_pagos.get_all_values()
df_pagos = pd.DataFrame(pagos_data[1:], columns=pagos_data[0])
pagos_proy = df_pagos[df_pagos['ID_proy'] == ID_PROY].copy()

# === 2. PROCESAR M.O BASE ===
def parse_monto(m):
    if not m or m == '-':
        return 0
    try:
        return float(m)
    except:
        return 0

mo_base['monto_num'] = mo_base['monto'].apply(parse_monto)

# Base por tipología
base_por_tipologia = {}
for tipol_id, info in tipologias_dict.items():
    subset = mo_base[mo_base['IDU_Tipol'] == tipol_id]
    total = subset['monto_num'].sum()

    # Base por familia - agregar prefijo RC si es R.Comp
    base_familia = {}
    for fam, monto in subset.groupby('familia_pago')['monto_num'].sum().items():
        if info['tipo'] == 'R.Comp':
            fam_key = f"RC {fam}" if not str(fam).startswith('RC ') else fam
        else:
            fam_key = fam
        base_familia[fam_key] = monto

    base_por_tipologia[tipol_id] = {
        'descripcion': info['descripcion'],
        'tipo': info['tipo'],
        'total_base': total,
        'base_por_familia': base_familia
    }

# === 3. PROCESAR PAGOS REALES ===
def parse_monto_real(m):
    if not m:
        return 0
    try:
        m = str(m).replace('$', '').replace('.', '').replace(',', '.')
        return float(m)
    except:
        return 0

pagos_proy['monto_num'] = pagos_proy['monto'].apply(parse_monto_real)

# Filtrar solo aprobados
pagos_aprobados = pagos_proy[pagos_proy['Estado'].str.lower().str.contains('aprobad', na=False)].copy()

# Detectar si el pago es de RC usando el ID de tipología
pagos_aprobados['es_rc'] = pagos_aprobados['tipologia'].isin(rc_tipologia_ids)
print(f"Pagos RC detectados: {pagos_aprobados['es_rc'].sum()}")

# Pagos por beneficiario y familia
pagos_por_benef_familia = {}
for ben in beneficiarios:
    ben_pagos = pagos_aprobados[pagos_aprobados['ID_Benef'] == ben['id']]
    pagos_familia = {}
    for idx, pago in ben_pagos.iterrows():
        fam = pago['Familia_pago']
        monto = pago['monto_num']
        if pago['es_rc']:
            fam_key = f"RC {fam}" if not str(fam).startswith('RC ') else fam
        else:
            fam_key = fam
        pagos_familia[fam_key] = pagos_familia.get(fam_key, 0) + monto

    pagos_por_benef_familia[ben['id']] = {
        'nombre': ben['nombre'],
        'tipologia_viv': ben['tipologia_viv'],
        'tipologia_rc': ben['tipologia_rc'],
        'pagos': pagos_familia,
        'total': ben_pagos['monto_num'].sum()
    }

# Total por familia
total_por_familia = {}
for ben_id, data in pagos_por_benef_familia.items():
    for fam, monto in data['pagos'].items():
        total_por_familia[fam] = total_por_familia.get(fam, 0) + monto

# === 4. CALCULAR BASE ESPERADA Y DESVIACIÓN ===
# Base esperada por familia (para todo el proyecto)
base_esperada_familia = {}
for tipol_id, data in base_por_tipologia.items():
    if data['tipo'] == 'Vivienda':
        cant_ben = viviendas_por_tip.get(tipol_id, 0)
    else:
        cant_ben = rc_por_tip.get(tipol_id, 0)

    for familia, monto in data['base_por_familia'].items():
        if familia not in base_esperada_familia:
            base_esperada_familia[familia] = 0
        base_esperada_familia[familia] += monto * cant_ben

# Base unitaria por familia (promedio por beneficiario, para calcular desviación individual)
# Para vivienda: usar base de la tipología del beneficiario
# Para RC: usar base de RC si tiene RC asignado
base_unitaria_familia = {}
for tipol_id, data in base_por_tipologia.items():
    for familia, monto in data['base_por_familia'].items():
        if familia not in base_unitaria_familia:
            base_unitaria_familia[familia] = {}
        base_unitaria_familia[familia][tipol_id] = monto

# Calcular desviación por familia
desviacion_familia = {}
todas_familias = set(list(base_esperada_familia.keys()) + list(total_por_familia.keys()))
for familia in todas_familias:
    base = base_esperada_familia.get(familia, 0)
    real = total_por_familia.get(familia, 0)
    desv = real - base
    desv_pct = (desv / base * 100) if base > 0 else (100 if real > 0 else 0)
    desviacion_familia[familia] = {
        'base': base,
        'real': real,
        'desviacion': desv,
        'desviacion_pct': desv_pct
    }

# Totales
total_base = sum(base_esperada_familia.values())
total_real = sum(total_por_familia.values())
total_desviacion = total_real - total_base
total_desv_pct = (total_desviacion / total_base * 100) if total_base > 0 else 0

print(f"\nTotal Base: ${total_base:,.0f}".replace(',', '.'))
print(f"Total Real: ${total_real:,.0f}".replace(',', '.'))
print(f"Desviación: ${total_desviacion:,.0f} ({total_desv_pct:+.1f}%)".replace(',', '.'))

# === 5. GENERAR PDF ===
class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 14)
        self.cell(0, 10, 'ANALISIS COMPARATIVO M.O', new_x="LMARGIN", new_y="NEXT", align='C')
        self.set_font('Helvetica', '', 10)
        self.cell(0, 6, 'Base Autorizada vs Pagos Reales', new_x="LMARGIN", new_y="NEXT", align='C')
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', align='C')

pdf = PDF('L', 'mm', 'A4')
pdf.add_page()
pdf.set_auto_page_break(auto=True, margin=15)

# Info del proyecto
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, f'Proyecto: {NOMBRE_PROY}', new_x="LMARGIN", new_y="NEXT")
pdf.set_font('Helvetica', '', 10)
pdf.cell(0, 6, f'ID: {ID_PROY} | Comuna: Teodoro Schmidt | Fecha: {datetime.now().strftime("%d/%m/%Y")}', new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)

# ============================================
# RESUMEN EJECUTIVO
# ============================================
pdf.set_fill_color(240, 240, 240)
pdf.set_font('Helvetica', 'B', 11)
pdf.cell(0, 8, 'RESUMEN EJECUTIVO', new_x="LMARGIN", new_y="NEXT", fill=True)
pdf.ln(2)

# Tabla de tipologías
pdf.set_font('Helvetica', 'B', 9)
pdf.set_fill_color(200, 200, 200)
pdf.cell(120, 7, 'Tipologia', 1, align='L', fill=True)
pdf.cell(30, 7, 'Cantidad', 1, align='C', fill=True)
pdf.cell(50, 7, 'Base Unitaria', 1, new_x="LMARGIN", new_y="NEXT", align='R', fill=True)

pdf.set_font('Helvetica', '', 9)
for tipol_id, data in base_por_tipologia.items():
    if data['tipo'] == 'Vivienda':
        cant = viviendas_por_tip.get(tipol_id, 0)
    else:
        cant = rc_por_tip.get(tipol_id, 0)

    if cant == 0:
        continue

    pdf.cell(120, 6, data['descripcion'], 1, align='L')
    pdf.cell(30, 6, str(cant), 1, align='C')
    pdf.cell(50, 6, f"${data['total_base']:,.0f}".replace(',', '.'), 1, new_x="LMARGIN", new_y="NEXT", align='R')

pdf.ln(2)
pdf.set_font('Helvetica', 'B', 10)
pdf.cell(0, 6, f'Total: {total_viviendas} Viviendas + {total_rc} Recintos Complementarios', new_x="LMARGIN", new_y="NEXT")
pdf.ln(2)

# Totales comparativos
pdf.set_font('Helvetica', '', 10)
pdf.cell(50, 7, 'M.O Base Esperado:', border=0)
pdf.cell(50, 7, f'${total_base:,.0f}'.replace(',', '.'), border=0)
pdf.cell(50, 7, 'Total Pagado:', border=0)
pdf.cell(50, 7, f'${total_real:,.0f}'.replace(',', '.'), border=0, new_x="LMARGIN", new_y="NEXT")

pdf.set_font('Helvetica', 'B', 10)
pdf.cell(50, 7, 'Desviacion:', border=0)
color = (0, 128, 0) if total_desviacion <= 0 else (200, 0, 0)
pdf.set_text_color(*color)
signo = '+' if total_desviacion > 0 else ''
pdf.cell(100, 7, f'{signo}${total_desviacion:,.0f} ({total_desv_pct:+.1f}%)'.replace(',', '.'), border=0, new_x="LMARGIN", new_y="NEXT")
pdf.set_text_color(0, 0, 0)
pdf.ln(3)

# ============================================
# PAGOS POR FAMILIA Y BENEFICIARIO
# ============================================
pdf.set_font('Helvetica', 'B', 11)
pdf.set_fill_color(240, 240, 240)
pdf.cell(0, 8, 'PAGOS REALES POR FAMILIA Y BENEFICIARIO (Monto y % desviacion)', new_x="LMARGIN", new_y="NEXT", fill=True)
pdf.ln(2)

# Ordenar familias: vivienda primero, RC después
familias_viv = sorted([f for f in todas_familias if f and not str(f).startswith('RC ')])
familias_rc = sorted([f for f in todas_familias if f and str(f).startswith('RC ')])
familias_ordenadas = familias_viv + familias_rc

# Calcular anchos - landscape A4 = 297mm, márgenes 10mm = 277mm disponible
ancho_disponible = 277
col_familia = 40
col_benef = (ancho_disponible - col_familia) / min(len(beneficiarios), 10)

# Función para obtener base unitaria por beneficiario y familia
def get_base_unitaria_benef(ben, familia):
    es_familia_rc = str(familia).startswith('RC ')
    if es_familia_rc:
        # Usar tipología RC del beneficiario
        tip_id = ben['tipologia_rc']
        if tip_id and tip_id in base_por_tipologia:
            return base_por_tipologia[tip_id]['base_por_familia'].get(familia, 0)
    else:
        # Usar tipología vivienda
        tip_id = ben['tipologia_viv']
        if tip_id and tip_id in base_por_tipologia:
            return base_por_tipologia[tip_id]['base_por_familia'].get(familia, 0)
    return 0

# Grupos de hasta 10 beneficiarios
benef_grupos = [beneficiarios[i:i+10] for i in range(0, len(beneficiarios), 10)]

for grupo_idx, grupo in enumerate(benef_grupos):
    if grupo_idx > 0:
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 8, f'PAGOS POR FAMILIA (cont.)', new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(2)

    col_benef = (ancho_disponible - col_familia) / len(grupo)

    # Header con nombres
    pdf.set_font('Helvetica', 'B', 6)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(col_familia, 7, 'Familia', 1, align='L', fill=True)
    for ben in grupo:
        pdf.cell(col_benef, 7, ben['nombre'][:10], 1, align='C', fill=True)
    pdf.ln()

    # Filas por familia
    pdf.set_font('Helvetica', '', 5)
    for familia in familias_ordenadas:
        if not familia:
            continue

        # Color para RC
        if str(familia).startswith('RC '):
            pdf.set_fill_color(255, 250, 230)
            fill = True
        else:
            fill = False

        pdf.cell(col_familia, 5, str(familia)[:22], 1, align='L', fill=fill)

        for ben in grupo:
            monto = pagos_por_benef_familia[ben['id']]['pagos'].get(familia, 0)
            base = get_base_unitaria_benef(ben, familia)

            if monto > 0:
                if base > 0:
                    desv_pct = ((monto - base) / base) * 100
                    # Formato: $XXXk (±XX%)
                    txt = f"${monto/1000:.0f}k({desv_pct:+.0f}%)"
                else:
                    txt = f"${monto/1000:.0f}k"
                pdf.cell(col_benef, 5, txt, 1, align='R', fill=fill)
            elif base > 0:
                # Tiene base pero no pago = -100%
                pdf.set_text_color(200, 0, 0)
                pdf.cell(col_benef, 5, "(-100%)", 1, align='C', fill=fill)
                pdf.set_text_color(0, 0, 0)
            else:
                pdf.cell(col_benef, 5, '-', 1, align='C', fill=fill)
        pdf.ln()

    # Total por beneficiario
    pdf.set_font('Helvetica', 'B', 6)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(col_familia, 6, 'TOTAL', 1, align='L', fill=True)
    for ben in grupo:
        total_ben = pagos_por_benef_familia[ben['id']]['total']
        # Calcular base total del beneficiario
        base_ben = 0
        tip_viv = ben['tipologia_viv']
        tip_rc = ben['tipologia_rc']
        if tip_viv and tip_viv in base_por_tipologia:
            base_ben += base_por_tipologia[tip_viv]['total_base']
        if tip_rc and tip_rc in base_por_tipologia:
            base_ben += base_por_tipologia[tip_rc]['total_base']

        if base_ben > 0:
            desv_ben = ((total_ben - base_ben) / base_ben) * 100
            pdf.cell(col_benef, 6, f"${total_ben/1000:.0f}k({desv_ben:+.0f}%)", 1, align='R', fill=True)
        else:
            pdf.cell(col_benef, 6, f"${total_ben/1000:.0f}k", 1, align='R', fill=True)
    pdf.ln()

pdf.ln(2)
pdf.set_font('Helvetica', 'I', 7)
pdf.cell(0, 4, 'Nota: Montos en miles (k). Entre parentesis: % desviacion vs base. Filas amarillas = RC.', new_x="LMARGIN", new_y="NEXT")

# ============================================
# ANÁLISIS DE DESVIACIÓN POR FAMILIA
# ============================================
pdf.add_page()
pdf.set_font('Helvetica', 'B', 11)
pdf.set_fill_color(240, 240, 240)
pdf.cell(0, 8, 'ANALISIS DE DESVIACION POR FAMILIA', new_x="LMARGIN", new_y="NEXT", fill=True)
pdf.ln(2)

# Header
pdf.set_font('Helvetica', 'B', 8)
pdf.set_fill_color(200, 200, 200)
pdf.cell(80, 7, 'Familia de Pago', 1, align='L', fill=True)
pdf.cell(45, 7, 'Base Esperada', 1, align='R', fill=True)
pdf.cell(45, 7, 'Real Pagado', 1, align='R', fill=True)
pdf.cell(45, 7, 'Desviacion', 1, align='R', fill=True)
pdf.cell(25, 7, '%', 1, new_x="LMARGIN", new_y="NEXT", align='C', fill=True)

# Ordenar: vivienda primero, luego RC
def sort_key(item):
    fam, data = item
    es_rc = 1 if str(fam).startswith('RC ') else 0
    return (es_rc, -abs(data['desviacion']))

familias_sorted = sorted(desviacion_familia.items(), key=sort_key)

pdf.set_font('Helvetica', '', 8)
for familia, data in familias_sorted:
    if not familia or (data['base'] == 0 and data['real'] == 0):
        continue

    if str(familia).startswith('RC '):
        pdf.set_fill_color(255, 250, 230)
        fill = True
    else:
        fill = False

    pdf.cell(80, 6, str(familia)[:40], 1, align='L', fill=fill)
    pdf.cell(45, 6, f"${data['base']:,.0f}".replace(',', '.'), 1, align='R', fill=fill)
    pdf.cell(45, 6, f"${data['real']:,.0f}".replace(',', '.'), 1, align='R', fill=fill)

    if data['desviacion'] > 0:
        pdf.set_text_color(200, 0, 0)
        signo = '+'
    elif data['desviacion'] < 0:
        pdf.set_text_color(0, 128, 0)
        signo = ''
    else:
        pdf.set_text_color(0, 0, 0)
        signo = ''

    pdf.cell(45, 6, f"{signo}${data['desviacion']:,.0f}".replace(',', '.'), 1, align='R', fill=fill)
    pdf.cell(25, 6, f"{data['desviacion_pct']:+.0f}%", 1, new_x="LMARGIN", new_y="NEXT", align='C', fill=fill)
    pdf.set_text_color(0, 0, 0)

# Total
pdf.set_font('Helvetica', 'B', 8)
pdf.set_fill_color(200, 200, 200)
pdf.cell(80, 7, 'TOTAL', 1, align='L', fill=True)
pdf.cell(45, 7, f"${total_base:,.0f}".replace(',', '.'), 1, align='R', fill=True)
pdf.cell(45, 7, f"${total_real:,.0f}".replace(',', '.'), 1, align='R', fill=True)

color = (200, 0, 0) if total_desviacion > 0 else (0, 128, 0)
pdf.set_text_color(*color)
signo = '+' if total_desviacion > 0 else ''
pdf.cell(45, 7, f"{signo}${total_desviacion:,.0f}".replace(',', '.'), 1, align='R', fill=True)
pdf.cell(25, 7, f"{total_desv_pct:+.1f}%", 1, new_x="LMARGIN", new_y="NEXT", align='C', fill=True)
pdf.set_text_color(0, 0, 0)

# Interpretación
pdf.ln(5)
pdf.set_font('Helvetica', 'B', 10)
pdf.cell(0, 7, 'Interpretacion:', new_x="LMARGIN", new_y="NEXT")
pdf.set_font('Helvetica', '', 9)

mayores_sobrecostos = [(f, d) for f, d in familias_sorted if d['desviacion'] > 0][:3]
mayores_ahorros = [(f, d) for f, d in familias_sorted if d['desviacion'] < 0][:3]

if mayores_sobrecostos:
    pdf.ln(2)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 6, 'Familias con sobrecosto:', new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    for fam, data in mayores_sobrecostos:
        pdf.cell(0, 5, f"  - {fam}: +${data['desviacion']:,.0f} ({data['desviacion_pct']:+.0f}%)".replace(',', '.'), new_x="LMARGIN", new_y="NEXT")

if mayores_ahorros:
    pdf.ln(2)
    pdf.set_text_color(0, 128, 0)
    pdf.cell(0, 6, 'Familias con ahorro:', new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    for fam, data in mayores_ahorros:
        pdf.cell(0, 5, f"  - {fam}: ${data['desviacion']:,.0f} ({data['desviacion_pct']:+.0f}%)".replace(',', '.'), new_x="LMARGIN", new_y="NEXT")

# Guardar
os.makedirs('reportes', exist_ok=True)
output_path = f'reportes/Analisis_MO_{NOMBRE_PROY.replace(" ", "_").replace(".", "")}_v4.pdf'
pdf.output(output_path)
print(f"\nPDF generado: {output_path}")

"""
Genera PDF de Análisis Completo de Postventa Regular
Versión 5 - Formato visual corregido
"""
import sys
sys.path.insert(0, '.')
from data_manager import DataManager
from fpdf import FPDF
from datetime import datetime
import pandas as pd
from collections import defaultdict

def generar_analisis_postventa(output_path: str = None):
    dm = DataManager()
    pv = dm.get_table_data('postventa')
    pv_det = dm.get_table_data('postventa_detalle')
    benef = dm.get_table_data('Beneficiario')
    proyectos = dm.get_table_data('Proyectos')

    pv_regular = pv[pv['tipoPV'].str.contains('regular', case=False, na=False)]

    benef_dict = {}
    for _, b in benef.iterrows():
        benef_dict[b['ID_Benef']] = str(b.get('APELLIDOS', ''))

    proy_dict = {}
    proy_viviendas = {}
    for _, p in proyectos.iterrows():
        proy_dict[p['ID_proy']] = str(p.get('NOMBRE_PROYECTO', ''))

    for _, b in benef.iterrows():
        pid = b['ID_Proy']
        if pid not in proy_viviendas:
            proy_viviendas[pid] = 0
        proy_viviendas[pid] += 1

    items_por_estado = {}
    items_por_area = {}
    items_por_origen = {}
    casos_por_proy = {}
    casos_data = []
    pendientes = []
    datos_por_comuna = defaultdict(lambda: {'items': [], 'areas': defaultdict(int), 'problemas': []})
    datos_por_especialidad = defaultdict(lambda: {'items': [], 'problemas': []})

    for _, caso in pv_regular.iterrows():
        id_pv = caso['IDU_PV']
        pid = caso['ID_Proy']
        origen = caso.get('origen', 'Sin origen')
        comuna = str(caso.get('Comuna', 'Sin comuna'))

        if pid not in casos_por_proy:
            casos_por_proy[pid] = 0
        casos_por_proy[pid] += 1

        detalles = pv_det[pv_det['IDU_PV'] == id_pv]
        nombre_proy = proy_dict.get(pid, str(pid))
        nombre_benef = benef_dict.get(caso['ID_Benef'], 'Desconocido')

        for _, det in detalles.iterrows():
            estado = det.get('Estado', 'Sin estado')
            area = det.get('area', 'Sin area')
            if not area or str(area).strip() == '':
                area = 'Sin area'

            problema_completo = str(det.get('detalle_obs', ''))

            items_por_estado[estado] = items_por_estado.get(estado, 0) + 1
            items_por_area[area] = items_por_area.get(area, 0) + 1
            items_por_origen[origen] = items_por_origen.get(origen, 0) + 1

            caso_item = {
                'proyecto': nombre_proy,
                'beneficiario': nombre_benef,
                'comuna': comuna,
                'fecha': str(caso.get('Fecha', ''))[:10],
                'origen': str(origen),
                'area': str(area),
                'problema': problema_completo,
                'estado': str(estado)
            }
            casos_data.append(caso_item)

            datos_por_comuna[comuna]['items'].append(caso_item)
            datos_por_comuna[comuna]['areas'][area] += 1
            if problema_completo:
                datos_por_comuna[comuna]['problemas'].append(problema_completo)

            datos_por_especialidad[area]['items'].append(caso_item)
            if problema_completo:
                datos_por_especialidad[area]['problemas'].append(problema_completo)

            if estado == 'Pendiente' or estado == '' or estado == 'Sin estado':
                pendientes.append(caso_item)

    proyectos_tasa = []
    for pid, casos in casos_por_proy.items():
        nombre = proy_dict.get(pid, str(pid))
        viviendas = proy_viviendas.get(pid, 0)
        tasa = (casos / viviendas * 100) if viviendas > 0 else 0
        proyectos_tasa.append({'nombre': nombre, 'casos': casos, 'viviendas': viviendas, 'tasa': tasa})
    proyectos_tasa.sort(key=lambda x: -x['tasa'])

    casos_data.sort(key=lambda x: (x['area'], x['proyecto'], x['fecha']))
    total_items = sum(items_por_estado.values())

    def extraer_temas_comunes(problemas_lista):
        texto = ' '.join(problemas_lista).lower()
        temas = {
            'filtracion': texto.count('filtracion') + texto.count('filtración') + texto.count('filtra'),
            'humedad': texto.count('humedad'),
            'puerta': texto.count('puerta'),
            'ventana': texto.count('ventana'),
            'llave/grifo': texto.count('llave') + texto.count('grifo'),
            'electrico': texto.count('electrico') + texto.count('eléctrico') + texto.count('luz'),
            'pintura': texto.count('pintura'),
            'piso/ceramica': texto.count('piso') + texto.count('ceramica') + texto.count('cerámica'),
            'techo/cielo': texto.count('techo') + texto.count('cielo'),
            'cañon/estufa': texto.count('cañon') + texto.count('cañón') + texto.count('estufa'),
            'lavaplatos': texto.count('lavaplatos') + texto.count('lavamanos'),
            'sello': texto.count('sello') + texto.count('silicona'),
        }
        return sorted([(k, v) for k, v in temas.items() if v > 0], key=lambda x: -x[1])

    # Crear PDF
    pdf = FPDF('L', 'mm', 'A4')
    pdf.set_auto_page_break(auto=True, margin=15)

    # Colores - Solo escala de grises + rojo oscuro
    GRIS_OSCURO = (70, 70, 70)
    GRIS_MEDIO = (110, 110, 110)
    GRIS_CLARO = (180, 180, 180)
    GRIS_FONDO = (245, 245, 245)
    ROJO = (140, 50, 50)  # Rojo oscuro

    pdf.add_page()

    # TITULO PRINCIPAL
    pdf.set_font('Helvetica', 'B', 18)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 12, 'Analisis de Postventa Regular', 0, 1, 'C')
    pdf.set_draw_color(*GRIS_MEDIO)
    pdf.set_line_width(0.5)
    pdf.line(40, pdf.get_y(), 257, pdf.get_y())
    pdf.ln(8)

    # ===== SECCION 1: RESUMEN =====
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 7, '1. RESUMEN EJECUTIVO', 0, 1, 'L')
    pdf.ln(2)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 5, f'Total casos: {len(pv_regular)}  |  Total items: {total_items}  |  Resueltos: {items_por_estado.get("Terminado", 0)} ({items_por_estado.get("Terminado", 0)/total_items*100:.1f}%)', 0, 1, 'L')
    pdf.ln(4)

    # Tabla Estado
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_fill_color(*GRIS_MEDIO)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(45, 5, 'Estado', 1, 0, 'C', True)
    pdf.cell(20, 5, 'Cant', 1, 0, 'C', True)
    pdf.cell(20, 5, '%', 1, 0, 'C', True)
    pdf.cell(10, 5, '', 0, 0)
    pdf.cell(45, 5, 'Especialidad', 1, 0, 'C', True)
    pdf.cell(20, 5, 'Cant', 1, 0, 'C', True)
    pdf.cell(20, 5, '%', 1, 0, 'C', True)
    pdf.cell(10, 5, '', 0, 0)
    pdf.cell(45, 5, 'Origen', 1, 0, 'C', True)
    pdf.cell(20, 5, 'Cant', 1, 0, 'C', True)
    pdf.cell(20, 5, '%', 1, 1, 'C', True)

    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(*GRIS_OSCURO)

    areas_sorted = sorted(items_por_area.items(), key=lambda x: -x[1])
    origenes_sorted = sorted(items_por_origen.items(), key=lambda x: -x[1])
    estados_sorted = sorted(items_por_estado.items(), key=lambda x: -x[1])

    max_filas = max(len(estados_sorted), len(areas_sorted), len(origenes_sorted))

    for i in range(max_filas):
        if i % 2 == 1:
            pdf.set_fill_color(*GRIS_FONDO)
            fill = True
        else:
            fill = False

        # Estado
        if i < len(estados_sorted):
            e, c = estados_sorted[i]
            pdf.cell(45, 4, e if e else 'Sin estado', 1, 0, 'L', fill)
            pdf.cell(20, 4, str(c), 1, 0, 'C', fill)
            pdf.cell(20, 4, f'{c/total_items*100:.1f}%', 1, 0, 'C', fill)
        else:
            pdf.cell(85, 4, '', 0, 0)

        pdf.cell(10, 4, '', 0, 0)

        # Especialidad
        if i < len(areas_sorted):
            a, c = areas_sorted[i]
            pdf.cell(45, 4, a[:22], 1, 0, 'L', fill)
            pdf.cell(20, 4, str(c), 1, 0, 'C', fill)
            pdf.cell(20, 4, f'{c/total_items*100:.1f}%', 1, 0, 'C', fill)
        else:
            pdf.cell(85, 4, '', 0, 0)

        pdf.cell(10, 4, '', 0, 0)

        # Origen
        if i < len(origenes_sorted):
            o, c = origenes_sorted[i]
            pdf.cell(45, 4, o[:22], 1, 0, 'L', fill)
            pdf.cell(20, 4, str(c), 1, 0, 'C', fill)
            pdf.cell(20, 4, f'{c/total_items*100:.1f}%', 1, 1, 'C', fill)
        else:
            pdf.ln()

    pdf.ln(6)

    # ===== SECCION 2: PROYECTOS =====
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 7, '2. PROYECTOS - TASA CASOS/VIVIENDA', 0, 1, 'L')
    pdf.ln(2)

    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(*GRIS_MEDIO)
    pdf.set_text_color(255, 255, 255)
    col_w = [62, 18, 22, 22, 8, 62, 18, 22, 22]
    pdf.cell(col_w[0], 5, 'Proyecto', 1, 0, 'C', True)
    pdf.cell(col_w[1], 5, 'Casos', 1, 0, 'C', True)
    pdf.cell(col_w[2], 5, 'Viviendas', 1, 0, 'C', True)
    pdf.cell(col_w[3], 5, 'Tasa', 1, 0, 'C', True)
    pdf.cell(col_w[4], 5, '', 0, 0)
    pdf.cell(col_w[5], 5, 'Proyecto', 1, 0, 'C', True)
    pdf.cell(col_w[6], 5, 'Casos', 1, 0, 'C', True)
    pdf.cell(col_w[7], 5, 'Viviendas', 1, 0, 'C', True)
    pdf.cell(col_w[8], 5, 'Tasa', 1, 1, 'C', True)

    pdf.set_font('Helvetica', '', 7)
    half = (len(proyectos_tasa) + 1) // 2

    for i in range(half):
        if i % 2 == 1:
            pdf.set_fill_color(*GRIS_FONDO)
            fill = True
        else:
            fill = False

        p = proyectos_tasa[i]
        if p['tasa'] > 100:
            pdf.set_text_color(*ROJO)
        else:
            pdf.set_text_color(*GRIS_OSCURO)

        pdf.cell(col_w[0], 4, p['nombre'][:30], 1, 0, 'L', fill)
        pdf.cell(col_w[1], 4, str(p['casos']), 1, 0, 'C', fill)
        pdf.cell(col_w[2], 4, str(p['viviendas']), 1, 0, 'C', fill)
        pdf.cell(col_w[3], 4, f"{p['tasa']:.1f}%", 1, 0, 'C', fill)
        pdf.cell(col_w[4], 4, '', 0, 0)

        if i + half < len(proyectos_tasa):
            p2 = proyectos_tasa[i + half]
            if p2['tasa'] > 100:
                pdf.set_text_color(*ROJO)
            else:
                pdf.set_text_color(*GRIS_OSCURO)
            pdf.cell(col_w[5], 4, p2['nombre'][:30], 1, 0, 'L', fill)
            pdf.cell(col_w[6], 4, str(p2['casos']), 1, 0, 'C', fill)
            pdf.cell(col_w[7], 4, str(p2['viviendas']), 1, 0, 'C', fill)
            pdf.cell(col_w[8], 4, f"{p2['tasa']:.1f}%", 1, 1, 'C', fill)
        else:
            pdf.ln()

    # Total
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(220, 220, 220)
    total_casos = sum(p['casos'] for p in proyectos_tasa)
    total_viv = sum(p['viviendas'] for p in proyectos_tasa)
    tasa_global = (total_casos / total_viv * 100) if total_viv > 0 else 0
    pdf.cell(col_w[0], 4, 'TOTAL', 1, 0, 'R', True)
    pdf.cell(col_w[1], 4, str(total_casos), 1, 0, 'C', True)
    pdf.cell(col_w[2], 4, str(total_viv), 1, 0, 'C', True)
    pdf.cell(col_w[3], 4, f'{tasa_global:.1f}%', 1, 1, 'C', True)

    # ===== SECCION 3: PENDIENTES =====
    pdf.add_page()  # Salto de pagina antes de seccion 3
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*ROJO)
    pdf.cell(0, 7, f'3. CASOS PENDIENTES ({len(pendientes)} items)', 0, 1, 'L')
    pdf.ln(2)

    # Header de tabla con numeracion
    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(*GRIS_MEDIO)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(10, 5, 'N', 1, 0, 'C', True)
    pdf.cell(50, 5, 'Proyecto', 1, 0, 'C', True)
    pdf.cell(42, 5, 'Beneficiario', 1, 0, 'C', True)
    pdf.cell(32, 5, 'Comuna', 1, 0, 'C', True)
    pdf.cell(22, 5, 'Fecha', 1, 0, 'C', True)
    pdf.cell(105, 5, 'Area', 1, 1, 'C', True)

    pdf.set_text_color(*GRIS_OSCURO)
    for idx, p in enumerate(pendientes):
        if pdf.get_y() > 170:
            pdf.add_page()
            # Repetir header
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_fill_color(*GRIS_MEDIO)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(10, 5, 'N', 1, 0, 'C', True)
            pdf.cell(50, 5, 'Proyecto', 1, 0, 'C', True)
            pdf.cell(42, 5, 'Beneficiario', 1, 0, 'C', True)
            pdf.cell(32, 5, 'Comuna', 1, 0, 'C', True)
            pdf.cell(22, 5, 'Fecha', 1, 0, 'C', True)
            pdf.cell(105, 5, 'Area', 1, 1, 'C', True)
            pdf.set_text_color(*GRIS_OSCURO)

        # Fila 1: Identificación con numeracion
        if idx % 2 == 0:
            pdf.set_fill_color(*GRIS_FONDO)
        else:
            pdf.set_fill_color(255, 255, 255)

        pdf.set_font('Helvetica', 'B', 7)
        pdf.cell(10, 5, str(idx + 1), 1, 0, 'C', True)
        pdf.cell(50, 5, p['proyecto'][:25], 1, 0, 'L', True)
        pdf.cell(42, 5, p['beneficiario'][:20], 1, 0, 'L', True)
        pdf.cell(32, 5, p['comuna'][:15], 1, 0, 'L', True)
        pdf.cell(22, 5, p['fecha'], 1, 0, 'C', True)
        pdf.cell(105, 5, p['area'], 1, 1, 'L', True)

        # Fila 2: Problema completo
        pdf.set_font('Helvetica', '', 7)
        problema_texto = p['problema'].replace('\n', ' ').replace('\r', ' ')

        # Calcular altura necesaria para el texto
        pdf.set_fill_color(255, 252, 250)
        x_antes = pdf.get_x()
        y_antes = pdf.get_y()

        # Usar multi_cell para el problema
        pdf.multi_cell(261, 4, f"Problema: {problema_texto}", 1, 'L', True)

        pdf.ln(1)

    # ===== SECCION 4: ANALISIS POR ESPECIALIDAD =====
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 7, '4. ANALISIS POR ESPECIALIDAD', 0, 1, 'L')
    pdf.ln(2)

    especialidades_ordenadas = sorted(datos_por_especialidad.keys(), key=lambda x: -len(datos_por_especialidad[x]['items']))

    for esp in especialidades_ordenadas:
        data = datos_por_especialidad[esp]
        total_esp = len(data['items'])
        if total_esp == 0:
            continue

        if pdf.get_y() > 160:
            pdf.add_page()

        pct_esp = (total_esp / total_items * 100) if total_items > 0 else 0

        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(*GRIS_MEDIO)
        pdf.cell(0, 6, f'{esp} - {total_esp} items ({pct_esp:.1f}%)', 0, 1, 'L')

        pdf.set_text_color(*GRIS_OSCURO)

        temas = extraer_temas_comunes(data['problemas'])
        if temas:
            pdf.set_font('Helvetica', '', 8)
            temas_text = 'Temas: ' + ', '.join([f'{t[0]}({t[1]})' for t in temas[:5]])
            pdf.cell(0, 4, temas_text, 0, 1, 'L')

        pdf.set_font('Helvetica', '', 7)
        ejemplos = 0
        for item in data['items']:
            if item['problema'] and len(item['problema']) > 10 and ejemplos < 2:
                problema_texto = item['problema'].replace('\n', ' ')[:150]
                pdf.set_x(15)
                pdf.cell(0, 4, f'- {problema_texto}...', 0, 1, 'L')
                ejemplos += 1

        pdf.ln(3)

    # ===== SECCION 5: LISTADO COMPLETO =====
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 7, f'5. LISTADO COMPLETO ({len(casos_data)} registros)', 0, 1, 'L')
    pdf.ln(2)

    casos_por_area = defaultdict(list)
    for c in casos_data:
        casos_por_area[c['area']].append(c)

    def header_listado():
        pdf.set_font('Helvetica', 'B', 6)
        pdf.set_fill_color(*GRIS_MEDIO)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(28, 4, 'Proyecto', 1, 0, 'C', True)
        pdf.cell(25, 4, 'Beneficiario', 1, 0, 'C', True)
        pdf.cell(20, 4, 'Comuna', 1, 0, 'C', True)
        pdf.cell(18, 4, 'Fecha', 1, 0, 'C', True)
        pdf.cell(150, 4, 'Problema', 1, 0, 'C', True)
        pdf.cell(20, 4, 'Estado', 1, 1, 'C', True)

    areas_ord = sorted(casos_por_area.keys(), key=lambda x: -len(casos_por_area[x]))

    for area in areas_ord:
        casos_area = casos_por_area[area]

        if pdf.get_y() > 170:
            pdf.add_page()

        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(*GRIS_MEDIO)
        pdf.cell(0, 5, f'Area: {area} ({len(casos_area)} items)', 0, 1, 'L')

        header_listado()

        pdf.set_font('Helvetica', '', 6)
        for i, c in enumerate(casos_area):
            if pdf.get_y() > 190:
                pdf.add_page()
                header_listado()
                pdf.set_font('Helvetica', '', 6)

            if c['estado'] == 'Pendiente' or not c['estado']:
                pdf.set_text_color(*ROJO)
            else:
                pdf.set_text_color(*GRIS_OSCURO)

            if i % 2 == 1:
                pdf.set_fill_color(*GRIS_FONDO)
                fill = True
            else:
                fill = False

            pdf.cell(28, 3.5, c['proyecto'][:14], 1, 0, 'L', fill)
            pdf.cell(25, 3.5, c['beneficiario'][:12], 1, 0, 'L', fill)
            pdf.cell(20, 3.5, c['comuna'][:10], 1, 0, 'L', fill)
            pdf.cell(18, 3.5, c['fecha'], 1, 0, 'C', fill)
            pdf.cell(150, 3.5, c['problema'][:90], 1, 0, 'L', fill)
            pdf.cell(20, 3.5, c['estado'][:10], 1, 1, 'C', fill)

        pdf.ln(3)

    # ===== SECCION 6: ANALISIS POR COMUNA =====
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 7, '6. ANALISIS POR COMUNA', 0, 1, 'L')
    pdf.ln(2)

    comunas_ordenadas = sorted(datos_por_comuna.keys(), key=lambda x: -len(datos_por_comuna[x]['items']))

    for comuna in comunas_ordenadas:
        data = datos_por_comuna[comuna]
        total_comuna = len(data['items'])
        if total_comuna == 0:
            continue

        if pdf.get_y() > 170:
            pdf.add_page()

        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(*GRIS_MEDIO)
        pdf.cell(0, 5, f'{comuna} ({total_comuna} items)', 0, 1, 'L')

        pdf.set_text_color(*GRIS_OSCURO)
        pdf.set_font('Helvetica', '', 8)

        areas_comuna = sorted(data['areas'].items(), key=lambda x: -x[1])
        area_principal = areas_comuna[0] if areas_comuna else ('Sin area', 0)
        pct_principal = (area_principal[1] / total_comuna * 100) if total_comuna > 0 else 0

        dist_text = ', '.join([f'{a}: {c}' for a, c in areas_comuna[:4]])
        pdf.cell(0, 4, f'Principal: {area_principal[0]} ({pct_principal:.0f}%) | Dist: {dist_text}', 0, 1, 'L')

        temas = extraer_temas_comunes(data['problemas'])
        if temas:
            temas_text = ', '.join([f'{t[0]}({t[1]})' for t in temas[:4]])
            pdf.cell(0, 4, f'Temas: {temas_text}', 0, 1, 'L')

        if pct_principal > 60:
            pdf.set_text_color(*ROJO)
            eval_text = f'Alerta: Problemas concentrados en {area_principal[0]}. Revisar contratista.'
        elif pct_principal > 40:
            pdf.set_text_color(*GRIS_MEDIO)
            eval_text = f'Tendencia hacia {area_principal[0]}.'
        else:
            pdf.set_text_color(*GRIS_CLARO)
            eval_text = 'Problemas distribuidos entre especialidades.'

        pdf.set_font('Helvetica', 'I', 7)
        pdf.cell(0, 4, eval_text, 0, 1, 'L')
        pdf.set_text_color(*GRIS_OSCURO)
        pdf.ln(3)

    # ===== RESUMEN FINAL =====
    if pdf.get_y() > 160:
        pdf.add_page()

    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*GRIS_OSCURO)
    pdf.cell(0, 7, 'RESUMEN Y RECOMENDACIONES', 0, 1, 'L')
    pdf.set_draw_color(*GRIS_CLARO)
    pdf.line(10, pdf.get_y(), 287, pdf.get_y())
    pdf.ln(3)

    pdf.set_font('Helvetica', '', 9)
    area_top = areas_sorted[0] if areas_sorted else ('Sin datos', 0)
    origen_top = origenes_sorted[0] if origenes_sorted else ('Sin datos', 0)

    recs = [
        f'1. {area_top[0]} concentra {area_top[1]/total_items*100:.0f}% de problemas. Reforzar control.',
        f'2. {origen_top[1]/total_items*100:.0f}% detectado en {origen_top[0]}. {"Mejorar control en obra." if origen_top[0] == "EGR" else ""}',
        f'3. Tasa global: {tasa_global:.1f}% casos/vivienda. {"OK" if tasa_global < 60 else "Alta, revisar procesos."}',
        f'4. {len(pendientes)} casos pendientes requieren atencion.',
    ]
    for r in recs:
        pdf.cell(0, 5, r, 0, 1, 'L')

    # Pie de pagina manual
    pdf.set_y(-15)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, f'Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')

    # Guardar
    if output_path is None:
        output_path = '../output/Analisis_Postventa_Regular_Completo.pdf'

    pdf.output(output_path)
    print(f'PDF generado: {output_path}')
    print(f'Paginas: {pdf.page_no()}')

    return output_path


if __name__ == "__main__":
    generar_analisis_postventa()

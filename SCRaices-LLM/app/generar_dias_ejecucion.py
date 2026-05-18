"""
Genera PDF de Días de Ejecución por Casa
Compara fecha de primer despacho vs fecha de recepción
"""
import sys
sys.path.insert(0, '.')
from data_manager import DataManager
from fpdf import FPDF
from datetime import datetime
import pandas as pd

def generar_informe_dias_ejecucion(proyectos_ids: list, output_path: str = None, incluir_habilitacion: bool = False):
    """
    Genera informe PDF de días de ejecución por casa

    Args:
        proyectos_ids: Lista de tuplas (ID_proy, nombre_proyecto)
        output_path: Ruta de salida del PDF
        incluir_habilitacion: Si True, incluye fecha de habilitación para construir
    """
    dm = DataManager()

    # Cargar datos
    beneficiarios = dm.get_table_data('Beneficiario')
    despachos = dm.get_table_data('Despacho')
    proyectos = dm.get_table_data('Proyectos')

    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.set_fill_color(51, 51, 51)
            self.set_text_color(255, 255, 255)
            self.cell(0, 12, 'Analisis de Dias de Ejecucion por Casa', 0, 1, 'C', True)
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f'Pagina {self.page_no()} - Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Título
    nombres_proy = [p[1] for p in proyectos_ids]
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(51, 51, 51)
    pdf.cell(0, 8, f'Comparativa: {" vs ".join([n.split()[-1] for n in nombres_proy])}', 0, 1, 'C')
    pdf.ln(3)

    # Descripción
    pdf.set_font('Helvetica', '', 9)
    if incluir_habilitacion:
        pdf.multi_cell(0, 5, 'Este informe muestra los tiempos por vivienda: Espera (habilitacion a 1er despacho), Ejecucion (1er despacho a recepcion) y Total (habilitacion a recepcion).')
    else:
        pdf.multi_cell(0, 5, 'Este informe muestra los dias de ejecucion por vivienda, calculados desde la fecha del primer despacho hasta la fecha de recepcion municipal.')
    pdf.ln(5)

    # Recopilar datos para resumen
    resumen_datos = []
    detalle_por_proyecto = {}

    for id_proy, nombre_proy in proyectos_ids:
        # Beneficiarios del proyecto con fecha recepción
        benef_proy = beneficiarios[beneficiarios['ID_Proy'] == id_proy].copy()

        # Obtener primer despacho por beneficiario (columna es ID_proy en minúscula)
        desp_proy = despachos[despachos['ID_proy'] == id_proy].copy()

        detalle_casas = []

        for _, benef in benef_proy.iterrows():
            id_benef = benef['ID_Benef']
            nombre = f"{benef.get('NOMBRES', '')} {benef.get('APELLIDOS', '')}"
            fecha_recepcion = benef.get('F_R_dom', '')
            fecha_habil = benef.get('fecha_habil_para_const', '')

            # Buscar primer despacho
            desp_benef = desp_proy[desp_proy['ID_Benef'] == id_benef]
            if desp_benef.empty:
                continue

            # Convertir fechas y encontrar la primera
            fechas_desp = []
            for _, d in desp_benef.iterrows():
                try:
                    f = pd.to_datetime(d['Fecha'], dayfirst=True)
                    fechas_desp.append(f)
                except:
                    pass

            if not fechas_desp:
                continue

            primer_despacho = min(fechas_desp)

            # Convertir fecha recepción
            if not fecha_recepcion or str(fecha_recepcion).strip() == '':
                continue

            try:
                fecha_rec = pd.to_datetime(fecha_recepcion, dayfirst=True)
            except:
                continue

            # Convertir fecha habilitación si existe
            fecha_hab_dt = None
            if incluir_habilitacion and fecha_habil and str(fecha_habil).strip() != '':
                try:
                    fecha_hab_dt = pd.to_datetime(fecha_habil, dayfirst=True)
                except:
                    pass

            # Calcular días
            dias = (fecha_rec - primer_despacho).days
            dias_total = None
            dias_espera = None
            if fecha_hab_dt:
                dias_total = (fecha_rec - fecha_hab_dt).days
                dias_espera = (primer_despacho - fecha_hab_dt).days

            if dias > 0:
                casa_data = {
                    'beneficiario': nombre.strip()[:30],
                    'primer_despacho': primer_despacho.strftime('%d/%m/%Y'),
                    'fecha_recepcion': fecha_rec.strftime('%d/%m/%Y'),
                    'dias': dias
                }
                if incluir_habilitacion:
                    casa_data['fecha_habil'] = fecha_hab_dt.strftime('%d/%m/%Y') if fecha_hab_dt else '-'
                    casa_data['dias_total'] = dias_total if dias_total else None
                    casa_data['dias_espera'] = dias_espera if dias_espera else None
                detalle_casas.append(casa_data)

        detalle_por_proyecto[nombre_proy] = detalle_casas

        if detalle_casas:
            promedio = sum(c['dias'] for c in detalle_casas) / len(detalle_casas)
            minimo = min(c['dias'] for c in detalle_casas)
            maximo = max(c['dias'] for c in detalle_casas)
            resumen_datos.append({
                'proyecto': nombre_proy,
                'casas': len(detalle_casas),
                'promedio': promedio,
                'minimo': minimo,
                'maximo': maximo
            })

    # SECCIÓN 1: RESUMEN EJECUTIVO
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(0, 8, '1. RESUMEN EJECUTIVO', 0, 1, 'L', True)
    pdf.ln(3)

    # Tabla resumen
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(51, 51, 51)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(70, 7, 'Proyecto', 1, 0, 'C', True)
    pdf.cell(25, 7, 'Casas', 1, 0, 'C', True)
    pdf.cell(30, 7, 'Promedio', 1, 0, 'C', True)
    pdf.cell(30, 7, 'Minimo', 1, 0, 'C', True)
    pdf.cell(30, 7, 'Maximo', 1, 1, 'C', True)

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(51, 51, 51)
    for r in resumen_datos:
        pdf.cell(70, 6, r['proyecto'][:35], 1, 0, 'L')
        pdf.cell(25, 6, str(r['casas']), 1, 0, 'C')
        pdf.cell(30, 6, f"{r['promedio']:.0f} dias", 1, 0, 'C')
        pdf.cell(30, 6, f"{r['minimo']} dias", 1, 0, 'C')
        pdf.cell(30, 6, f"{r['maximo']} dias", 1, 1, 'C')

    pdf.ln(8)

    # SECCIÓN 2: DETALLE POR PROYECTO
    for nombre_proy, detalle in detalle_por_proyecto.items():
        pdf.set_font('Helvetica', 'B', 11)
        pdf.set_fill_color(200, 200, 200)
        pdf.cell(0, 8, f'DETALLE: {nombre_proy}', 0, 1, 'L', True)
        pdf.ln(3)

        if not detalle:
            pdf.set_font('Helvetica', 'I', 9)
            pdf.cell(0, 6, 'Sin datos de ejecucion disponibles', 0, 1)
            pdf.ln(5)
            continue

        # Ordenar por días (mayor a menor)
        detalle_ordenado = sorted(detalle, key=lambda x: x['dias'], reverse=True)

        # Calcular promedio para colorear
        promedio = sum(c['dias'] for c in detalle) / len(detalle)

        if incluir_habilitacion:
            # Tabla extendida con habilitación (horizontal)
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_fill_color(51, 51, 51)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(45, 6, 'Beneficiario', 1, 0, 'C', True)
            pdf.cell(22, 6, 'Habilit.', 1, 0, 'C', True)
            pdf.cell(22, 6, '1er Desp.', 1, 0, 'C', True)
            pdf.cell(22, 6, 'Recepcion', 1, 0, 'C', True)
            pdf.cell(18, 6, 'Espera', 1, 0, 'C', True)
            pdf.cell(18, 6, 'Ejec.', 1, 0, 'C', True)
            pdf.cell(18, 6, 'Total', 1, 0, 'C', True)
            pdf.cell(20, 6, 'vs Prom', 1, 1, 'C', True)

            pdf.set_font('Helvetica', '', 7)
            for casa in detalle_ordenado:
                diff = casa['dias'] - promedio
                diff_pct = (diff / promedio) * 100 if promedio > 0 else 0

                pdf.set_text_color(51, 51, 51)
                pdf.cell(45, 5, casa['beneficiario'][:25], 1, 0, 'L')
                pdf.cell(22, 5, casa.get('fecha_habil', '-'), 1, 0, 'C')
                pdf.cell(22, 5, casa['primer_despacho'], 1, 0, 'C')
                pdf.cell(22, 5, casa['fecha_recepcion'], 1, 0, 'C')

                # Días de espera (habilitación -> 1er despacho)
                dias_espera = casa.get('dias_espera')
                pdf.cell(18, 5, f"{dias_espera}" if dias_espera else '-', 1, 0, 'C')

                # Colorear días ejecución según desviación
                if diff_pct > 15:
                    pdf.set_text_color(200, 0, 0)
                elif diff_pct < -15:
                    pdf.set_text_color(0, 128, 0)
                else:
                    pdf.set_text_color(51, 51, 51)

                pdf.cell(18, 5, f"{casa['dias']}", 1, 0, 'C')

                # Días total
                dias_total = casa.get('dias_total')
                pdf.set_text_color(51, 51, 51)
                pdf.cell(18, 5, f"{dias_total}" if dias_total else '-', 1, 0, 'C')

                signo = '+' if diff > 0 else ''
                if diff_pct > 15:
                    pdf.set_text_color(200, 0, 0)
                elif diff_pct < -15:
                    pdf.set_text_color(0, 128, 0)
                else:
                    pdf.set_text_color(51, 51, 51)
                pdf.cell(20, 5, f"{signo}{diff_pct:.0f}%", 1, 1, 'C')

            # Fila de promedio
            pdf.set_font('Helvetica', 'B', 7)
            pdf.set_text_color(51, 51, 51)
            pdf.set_fill_color(230, 230, 230)

            # Calcular promedios de espera y total
            dias_espera_list = [c['dias_espera'] for c in detalle if c.get('dias_espera')]
            dias_total_list = [c['dias_total'] for c in detalle if c.get('dias_total')]
            prom_espera = sum(dias_espera_list) / len(dias_espera_list) if dias_espera_list else 0
            prom_total = sum(dias_total_list) / len(dias_total_list) if dias_total_list else 0

            pdf.cell(111, 6, 'PROMEDIO', 1, 0, 'R', True)
            pdf.cell(18, 6, f"{prom_espera:.0f}" if prom_espera else '-', 1, 0, 'C', True)
            pdf.cell(18, 6, f"{promedio:.0f}", 1, 0, 'C', True)
            pdf.cell(18, 6, f"{prom_total:.0f}" if prom_total else '-', 1, 0, 'C', True)
            pdf.cell(20, 6, '-', 1, 1, 'C', True)
        else:
            # Tabla original sin habilitación
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_fill_color(51, 51, 51)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(60, 6, 'Beneficiario', 1, 0, 'C', True)
            pdf.cell(35, 6, '1er Despacho', 1, 0, 'C', True)
            pdf.cell(35, 6, 'Recepcion', 1, 0, 'C', True)
            pdf.cell(30, 6, 'Dias Ejecucion', 1, 0, 'C', True)
            pdf.cell(25, 6, 'vs Promedio', 1, 1, 'C', True)

            pdf.set_font('Helvetica', '', 8)
            for casa in detalle_ordenado:
                diff = casa['dias'] - promedio
                diff_pct = (diff / promedio) * 100 if promedio > 0 else 0

                pdf.set_text_color(51, 51, 51)
                pdf.cell(60, 5, casa['beneficiario'], 1, 0, 'L')
                pdf.cell(35, 5, casa['primer_despacho'], 1, 0, 'C')
                pdf.cell(35, 5, casa['fecha_recepcion'], 1, 0, 'C')

                # Colorear días según desviación
                if diff_pct > 15:
                    pdf.set_text_color(200, 0, 0)  # Rojo - más lento
                elif diff_pct < -15:
                    pdf.set_text_color(0, 128, 0)  # Verde - más rápido
                else:
                    pdf.set_text_color(51, 51, 51)

                pdf.cell(30, 5, f"{casa['dias']} dias", 1, 0, 'C')

                signo = '+' if diff > 0 else ''
                pdf.cell(25, 5, f"{signo}{diff:.0f} ({signo}{diff_pct:.0f}%)", 1, 1, 'C')

            # Fila de promedio
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(51, 51, 51)
            pdf.set_fill_color(230, 230, 230)
            pdf.cell(130, 6, 'PROMEDIO', 1, 0, 'R', True)
            pdf.cell(30, 6, f"{promedio:.0f} dias", 1, 0, 'C', True)
            pdf.cell(25, 6, '-', 1, 1, 'C', True)

        pdf.ln(8)

    # Guardar
    if output_path is None:
        output_path = '../output/Dias_Ejecucion_Comparativo.pdf'

    pdf.output(output_path)
    print(f'PDF generado: {output_path}')

    return output_path, resumen_datos


if __name__ == "__main__":
    # Proyectos a comparar
    proyectos = [
        ('P93', 'Grupo Panguipulli DS 10 N°2'),
        ('P94', 'Grupo Panguipulli DS 10 N°3')
    ]

    output_path = '../output/Dias_Ejecucion_Panguipulli_2_3.pdf'

    ruta, resumen = generar_informe_dias_ejecucion(proyectos, output_path)

    print("\nResumen:")
    for r in resumen:
        print(f"  - {r['proyecto']}: {r['casas']} casas, promedio {r['promedio']:.0f} dias (min: {r['minimo']}, max: {r['maximo']})")

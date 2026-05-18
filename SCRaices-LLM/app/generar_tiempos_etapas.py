"""
Genera PDF de Tiempos entre 1era y 2da Etapa por Carpintero
"""
import sys
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')
from data_manager import DataManager
from fpdf import FPDF
from datetime import datetime
import pandas as pd

def generar_informe_tiempos_etapas(proyectos_dict: dict, output_path: str = None):
    """
    Genera informe PDF de tiempos entre 1era y 2da etapa por carpintero

    Args:
        proyectos_dict: Dict {ID_proy: nombre_proyecto}
        output_path: Ruta de salida del PDF
    """
    dm = DataManager()

    solpago = dm.get_table_data('Solpago')
    maestros = dm.get_table_data('Maestros')
    despachos = dm.get_table_data('Despacho')
    beneficiarios = dm.get_table_data('Beneficiario')

    # Crear diccionario de maestros
    maestros_dict = {}
    for _, m in maestros.iterrows():
        maestros_dict[m['IDU_maestros']] = str(m['Nombres']) + ' ' + str(m['Apellidos'])

    # Recopilar todos los datos
    datos_por_proyecto = {}
    resumen_proyectos = []

    for id_proy, nombre_proy in proyectos_dict.items():
        benef_proy = beneficiarios[beneficiarios['ID_Proy'] == id_proy]
        desp_proy = despachos[despachos['ID_proy'] == id_proy]
        solp_proy = solpago[solpago['ID_proy'] == id_proy]

        pagos_1era = solp_proy[solp_proy['Familia_pago'].str.contains('02 - 1era Etapa', case=False, na=False)]
        pagos_2da = solp_proy[solp_proy['Familia_pago'].str.contains('03 - 2da Etapa', case=False, na=False)]

        casas_data = []

        for _, benef in benef_proy.iterrows():
            id_benef = benef['ID_Benef']
            nombre_benef = str(benef['APELLIDOS'])

            desp_benef = desp_proy[desp_proy['ID_Benef'] == id_benef]
            d1 = desp_benef[desp_benef['Tipo_despacho'].str.contains('02- 1era Etapa', na=False)]
            d2 = desp_benef[desp_benef['Tipo_despacho'].str.contains('03- 2da Etapa', na=False)]

            if d1.empty or d2.empty:
                continue

            try:
                fecha_1era = pd.to_datetime(d1.iloc[0]['Fecha'], dayfirst=True)
                fecha_2da = pd.to_datetime(d2.iloc[0]['Fecha'], dayfirst=True)
                dias = (fecha_2da - fecha_1era).days

                if dias < 0:
                    continue

                p1_benef = pagos_1era[pagos_1era['ID_Benef'] == id_benef]
                p2_benef = pagos_2da[pagos_2da['ID_Benef'] == id_benef]

                carpinteros_ids = set(p1_benef['maestro'].dropna().tolist() + p2_benef['maestro'].dropna().tolist())
                carpinteros_nombres = [maestros_dict.get(m, 'Desconocido')[:22] for m in carpinteros_ids]

                casas_data.append({
                    'beneficiario': nombre_benef[:25],
                    'fecha_1era': fecha_1era.strftime('%d/%m/%Y'),
                    'fecha_2da': fecha_2da.strftime('%d/%m/%Y'),
                    'dias': dias,
                    'carpinteros': ', '.join(carpinteros_nombres[:2]) if carpinteros_nombres else 'Sin registro'
                })
            except:
                pass

        casas_data.sort(key=lambda x: x['dias'], reverse=True)
        datos_por_proyecto[nombre_proy] = casas_data

        if casas_data:
            dias_list = [c['dias'] for c in casas_data]
            resumen_proyectos.append({
                'nombre': nombre_proy,
                'casas': len(casas_data),
                'promedio': sum(dias_list) / len(dias_list),
                'minimo': min(dias_list),
                'maximo': max(dias_list)
            })

    # Crear PDF
    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 12)
            self.set_fill_color(51, 51, 51)
            self.set_text_color(255, 255, 255)
            self.cell(0, 10, 'Analisis de Tiempos: 1era Etapa a 2da Etapa por Carpintero', 0, 1, 'C', True)
            self.ln(3)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
            self.cell(0, 10, f'Pagina {self.page_no()} - Generado: {fecha}', 0, 0, 'C')

    pdf = PDF('L', 'mm', 'A4')  # Landscape
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Resumen ejecutivo
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(51, 51, 51)
    pdf.cell(0, 8, 'RESUMEN EJECUTIVO', 0, 1, 'L')
    pdf.ln(2)

    # Tabla resumen
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(51, 51, 51)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(80, 7, 'Proyecto', 1, 0, 'C', True)
    pdf.cell(25, 7, 'Casas', 1, 0, 'C', True)
    pdf.cell(30, 7, 'Promedio', 1, 0, 'C', True)
    pdf.cell(25, 7, 'Minimo', 1, 0, 'C', True)
    pdf.cell(25, 7, 'Maximo', 1, 1, 'C', True)

    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(51, 51, 51)
    total_casas = 0
    for r in resumen_proyectos:
        pdf.cell(80, 6, r['nombre'], 1, 0, 'L')
        pdf.cell(25, 6, str(r['casas']), 1, 0, 'C')
        pdf.cell(30, 6, f"{r['promedio']:.0f} dias", 1, 0, 'C')
        pdf.cell(25, 6, f"{r['minimo']} dias", 1, 0, 'C')
        pdf.cell(25, 6, f"{r['maximo']} dias", 1, 1, 'C')
        total_casas += r['casas']

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(80, 6, 'TOTAL', 1, 0, 'R', True)
    pdf.cell(25, 6, str(total_casas), 1, 0, 'C', True)
    pdf.cell(80, 6, '', 1, 1, 'C', True)

    pdf.ln(8)

    # Detalle por proyecto
    for nombre_proy, casas in datos_por_proyecto.items():
        if not casas:
            continue

        # Check if we need a new page
        if pdf.get_y() > 160:
            pdf.add_page()

        dias_list = [c['dias'] for c in casas]
        promedio = sum(dias_list) / len(dias_list)

        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_fill_color(100, 100, 100)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 7, f'{nombre_proy} - {len(casas)} casas - Promedio: {promedio:.0f} dias', 0, 1, 'L', True)

        # Cabecera tabla
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_fill_color(180, 180, 180)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(55, 6, 'Beneficiario', 1, 0, 'C', True)
        pdf.cell(25, 6, '1era Etapa', 1, 0, 'C', True)
        pdf.cell(25, 6, '2da Etapa', 1, 0, 'C', True)
        pdf.cell(20, 6, 'Dias', 1, 0, 'C', True)
        pdf.cell(150, 6, 'Carpintero(s)', 1, 1, 'C', True)

        pdf.set_font('Helvetica', '', 8)
        for c in casas:
            # Colorear segun dias
            if c['dias'] > promedio * 1.5:
                pdf.set_text_color(180, 0, 0)  # Rojo - lento
            elif c['dias'] < promedio * 0.5:
                pdf.set_text_color(0, 128, 0)  # Verde - rapido
            else:
                pdf.set_text_color(51, 51, 51)

            pdf.cell(55, 5, c['beneficiario'], 1, 0, 'L')
            pdf.cell(25, 5, c['fecha_1era'], 1, 0, 'C')
            pdf.cell(25, 5, c['fecha_2da'], 1, 0, 'C')
            pdf.cell(20, 5, str(c['dias']), 1, 0, 'C')
            pdf.set_text_color(51, 51, 51)
            pdf.cell(150, 5, c['carpinteros'][:60], 1, 1, 'L')

        pdf.ln(5)

    # Guardar
    if output_path is None:
        output_path = '../output/Tiempos_1era_2da_Etapa_por_Carpintero.pdf'

    pdf.output(output_path)
    print('PDF generado:', output_path)
    print(f'Total: {total_casas} casas en {len(resumen_proyectos)} proyectos')

    return output_path, resumen_proyectos


if __name__ == "__main__":
    proyectos = {
        'P93': 'Grupo Panguipulli DS 10 N2',
        'P94': 'Grupo Panguipulli DS 10 N3',
        'P92': 'Lago Ranco',
        'P87': 'Raices de Lanco',
        'P26': 'Truful Truful',
        'P19': 'Los Valles de Gorbea',
        'P51': 'Puyehue',
        'P32': 'Newen Ruka',
    }

    generar_informe_tiempos_etapas(proyectos)

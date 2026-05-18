"""Script para generar informe de Gastos Generales y Rendiciones"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from fpdf import FPDF
from datetime import datetime
import pandas as pd
from data_manager import DataManager

def generar_informe_gg_rendiciones(nombre_proyecto: str):
    dm = DataManager()

    # Buscar proyecto
    proyectos = dm.get_table_data('Proyectos')
    mask = proyectos['NOMBRE_PROYECTO'].str.contains(nombre_proyecto, case=False, na=False)
    if mask.sum() == 0:
        print(f"Proyecto '{nombre_proyecto}' no encontrado")
        return None

    proy = proyectos[mask].iloc[0]
    id_proy = proy['ID_proy']
    nombre_proy = proy['NOMBRE_PROYECTO']

    # === DATOS GASTOS GENERALES ===
    pago_ex = dm.get_table_data('Reg_pago_ex')
    pago_ex_proy = pago_ex[pago_ex['ID_proy'] == id_proy].copy()
    pago_ex_det = dm.get_table_data('Reg_pago_ex_det')
    ids_cabecera = pago_ex_proy['IDU_regpx'].tolist()
    det_gg = pago_ex_det[pago_ex_det['IDU_regpx'].isin(ids_cabecera)].copy()

    def parse_monto(m):
        if pd.isna(m) or m == '':
            return 0
        s = str(m).replace('$', '').replace('.', '').replace(',', '.').strip()
        try:
            return float(s)
        except:
            return 0

    det_gg['monto_num'] = det_gg['monto'].apply(parse_monto)

    # === DATOS RENDICIONES ===
    rend = dm.get_table_data('rend_caja')
    rend_proy = rend[rend['Ccosto'] == id_proy].copy()
    rend_det = dm.get_table_data('rend_caja_det')
    ids_rend = rend_proy['IDU_Rendcaja'].tolist()
    det_rend = rend_det[rend_det['IDU_Rendcaja'].isin(ids_rend)].copy()
    det_rend['monto_num'] = det_rend['Monto'].apply(parse_monto)

    # === GENERAR PDF ===
    class InformeGGPDF(FPDF):
        def header(self):
            self.set_fill_color(44, 44, 44)
            self.rect(0, 0, 297, 15, 'F')
            self.set_text_color(255, 255, 255)
            self.set_font('Helvetica', 'B', 12)
            self.cell(0, 15, 'INFORME DE GASTOS GENERALES Y RENDICIONES - SCRaices', 0, 1, 'C')
            self.set_text_color(0, 0, 0)
            self.ln(2)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128)
            self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

    pdf = InformeGGPDF('L', 'mm', 'A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Título
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_text_color(196, 30, 58)
    pdf.cell(0, 10, f'Proyecto: {nombre_proy}', 0, 1, 'C')
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 6, f'ID: {id_proy} | Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
    pdf.ln(5)

    # ============ SECCIÓN 1: GASTOS GENERALES ============
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, '1. GASTOS GENERALES (Facturas - Pago Directo)', 0, 1, 'L', True)
    pdf.ln(3)

    # Resumen por tipo
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 7, 'Resumen por Categoria:', 0, 1, 'L')

    resumen_gg = det_gg.groupby('Tipo_pago').agg({'monto_num': ['sum', 'count']}).reset_index()
    resumen_gg.columns = ['Tipo', 'Total', 'Cantidad']
    resumen_gg = resumen_gg.sort_values('Total', ascending=False)

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(80, 7, 'Categoria', 1, 0, 'L', True)
    pdf.cell(30, 7, 'Cantidad', 1, 0, 'C', True)
    pdf.cell(50, 7, 'Total', 1, 0, 'R', True)
    pdf.cell(40, 7, '% del Total', 1, 1, 'C', True)

    total_gg = resumen_gg['Total'].sum()
    pdf.set_font('Helvetica', '', 9)
    for _, row in resumen_gg.iterrows():
        tipo = row['Tipo'] if row['Tipo'] else '(Sin categoria)'
        pct = (row['Total'] / total_gg * 100) if total_gg > 0 else 0
        pdf.cell(80, 6, str(tipo)[:40], 1, 0, 'L')
        pdf.cell(30, 6, str(int(row['Cantidad'])), 1, 0, 'C')
        pdf.cell(50, 6, f"${row['Total']:,.0f}".replace(',', '.'), 1, 0, 'R')
        pdf.cell(40, 6, f"{pct:.1f}%", 1, 1, 'C')

    # Total
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(80, 7, 'TOTAL GASTOS GENERALES', 1, 0, 'L', True)
    pdf.cell(30, 7, str(len(det_gg)), 1, 0, 'C', True)
    pdf.cell(50, 7, f"${total_gg:,.0f}".replace(',', '.'), 1, 0, 'R', True)
    pdf.cell(40, 7, '100%', 1, 1, 'C', True)
    pdf.ln(5)

    # Detalle de Gastos Generales
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 7, 'Detalle de Gastos:', 0, 1, 'L')

    # Unir con cabecera para tener fecha y descripcion
    det_gg_full = det_gg.merge(pago_ex_proy[['IDU_regpx', 'fecha', 'estado', 'descripcion']], on='IDU_regpx', how='left')

    # Obtener nombres de proveedores
    proveedores = dm.get_table_data('Reg_pago_proveed')
    prov_dict = dict(zip(proveedores['IDU_proveed'], proveedores['Nombre']))
    det_gg_full['proveedor_nombre'] = det_gg_full['proveedor'].map(prov_dict).fillna('')

    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(18, 6, 'Fecha', 1, 0, 'C', True)
    pdf.cell(22, 6, 'Categoria', 1, 0, 'C', True)
    pdf.cell(45, 6, 'Proveedor', 1, 0, 'L', True)
    pdf.cell(65, 6, 'Descripcion', 1, 0, 'L', True)
    pdf.cell(45, 6, 'Detalle Pago', 1, 0, 'L', True)
    pdf.cell(28, 6, 'Monto', 1, 1, 'R', True)

    pdf.set_font('Helvetica', '', 6)
    for _, row in det_gg_full.sort_values('fecha', ascending=False).head(60).iterrows():
        fecha = str(row.get('fecha', ''))[:10]
        tipo = str(row.get('Tipo_pago', ''))[:11]
        prov_nombre = str(row.get('proveedor_nombre', ''))[:22]
        descripcion = str(row.get('descripcion', ''))[:32]
        detalle = str(row.get('detalle_pago', '') or row.get('observaciones', ''))[:22]
        monto = row['monto_num']

        pdf.cell(18, 5, fecha, 1, 0, 'C')
        pdf.cell(22, 5, tipo, 1, 0, 'L')
        pdf.cell(45, 5, prov_nombre, 1, 0, 'L')
        pdf.cell(65, 5, descripcion, 1, 0, 'L')
        pdf.cell(45, 5, detalle, 1, 0, 'L')
        pdf.cell(28, 5, f"${monto:,.0f}".replace(',', '.'), 1, 1, 'R')

    if len(det_gg_full) > 60:
        pdf.set_font('Helvetica', 'I', 8)
        pdf.cell(0, 5, f'(Mostrando 60 de {len(det_gg_full)} registros)', 0, 1, 'C')

    # ============ SECCIÓN 2: RENDICIONES ============
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, '2. RENDICIONES (Reembolsos Solicitados)', 0, 1, 'L', True)
    pdf.ln(3)

    # Resumen por clase
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 7, 'Resumen por Clase:', 0, 1, 'L')

    resumen_rend = det_rend.groupby('clase').agg({'monto_num': ['sum', 'count']}).reset_index()
    resumen_rend.columns = ['Clase', 'Total', 'Cantidad']
    resumen_rend = resumen_rend.sort_values('Total', ascending=False)

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(100, 7, 'Clase', 1, 0, 'L', True)
    pdf.cell(30, 7, 'Cantidad', 1, 0, 'C', True)
    pdf.cell(50, 7, 'Total', 1, 0, 'R', True)
    pdf.cell(40, 7, '% del Total', 1, 1, 'C', True)

    total_rend = resumen_rend['Total'].sum()
    pdf.set_font('Helvetica', '', 9)
    for _, row in resumen_rend.iterrows():
        clase = row['Clase'] if row['Clase'] else '(Sin clase)'
        pct = (row['Total'] / total_rend * 100) if total_rend > 0 else 0
        pdf.cell(100, 6, str(clase)[:50], 1, 0, 'L')
        pdf.cell(30, 6, str(int(row['Cantidad'])), 1, 0, 'C')
        pdf.cell(50, 6, f"${row['Total']:,.0f}".replace(',', '.'), 1, 0, 'R')
        pdf.cell(40, 6, f"{pct:.1f}%", 1, 1, 'C')

    # Total
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(100, 7, 'TOTAL RENDICIONES', 1, 0, 'L', True)
    pdf.cell(30, 7, str(len(det_rend)), 1, 0, 'C', True)
    pdf.cell(50, 7, f"${total_rend:,.0f}".replace(',', '.'), 1, 0, 'R', True)
    pdf.cell(40, 7, '100%', 1, 1, 'C', True)
    pdf.ln(5)

    # Resumen por usuario
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 7, 'Resumen por Usuario (rendidor):', 0, 1, 'L')

    det_rend_user = det_rend.merge(rend_proy[['IDU_Rendcaja', 'usuario', 'Estado']], on='IDU_Rendcaja', how='left')
    resumen_user = det_rend_user.groupby('usuario').agg({'monto_num': ['sum', 'count']}).reset_index()
    resumen_user.columns = ['Usuario', 'Total', 'Cantidad']
    resumen_user = resumen_user.sort_values('Total', ascending=False)

    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(100, 7, 'Usuario', 1, 0, 'L', True)
    pdf.cell(30, 7, 'Cantidad', 1, 0, 'C', True)
    pdf.cell(50, 7, 'Total Rendido', 1, 1, 'R', True)

    pdf.set_font('Helvetica', '', 9)
    for _, row in resumen_user.head(15).iterrows():
        usuario = str(row['Usuario']).replace('@scraices.cl', '')[:40]
        pdf.cell(100, 6, usuario, 1, 0, 'L')
        pdf.cell(30, 6, str(int(row['Cantidad'])), 1, 0, 'C')
        pdf.cell(50, 6, f"${row['Total']:,.0f}".replace(',', '.'), 1, 1, 'R')

    pdf.ln(5)

    # Detalle de Rendiciones (últimas 50)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 7, 'Detalle de Rendiciones (ultimos 50 registros):', 0, 1, 'L')

    pdf.set_font('Helvetica', 'B', 7)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(20, 6, 'Fecha', 1, 0, 'C', True)
    pdf.cell(40, 6, 'Clase', 1, 0, 'L', True)
    pdf.cell(20, 6, 'Tipo Doc', 1, 0, 'C', True)
    pdf.cell(80, 6, 'Detalle', 1, 0, 'L', True)
    pdf.cell(30, 6, 'Monto', 1, 0, 'R', True)
    pdf.cell(35, 6, 'Usuario', 1, 1, 'L', True)

    pdf.set_font('Helvetica', '', 6)
    for _, row in det_rend_user.sort_values('fecha', ascending=False).head(50).iterrows():
        fecha = str(row.get('fecha', ''))[:10]
        clase = str(row.get('clase', ''))[:20]
        tipo_doc = str(row.get('tipo_doc', ''))[:10]
        detalle = str(row.get('Detalle', ''))[:40]
        monto = row['monto_num']
        usuario = str(row.get('usuario', '')).replace('@scraices.cl', '')[:15]

        pdf.cell(20, 5, fecha, 1, 0, 'C')
        pdf.cell(40, 5, clase, 1, 0, 'L')
        pdf.cell(20, 5, tipo_doc, 1, 0, 'C')
        pdf.cell(80, 5, detalle, 1, 0, 'L')
        pdf.cell(30, 5, f"${monto:,.0f}".replace(',', '.'), 1, 0, 'R')
        pdf.cell(35, 5, usuario, 1, 1, 'L')

    if len(det_rend_user) > 50:
        pdf.set_font('Helvetica', 'I', 8)
        pdf.cell(0, 5, f'(Mostrando 50 de {len(det_rend_user)} registros)', 0, 1, 'C')

    # ============ RESUMEN EJECUTIVO ============
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 10, '3. RESUMEN EJECUTIVO', 0, 1, 'L', True)
    pdf.ln(5)

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, f'Proyecto: {nombre_proy}', 0, 1, 'L')
    pdf.ln(3)

    # Tabla resumen
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(100, 8, 'Concepto', 1, 0, 'L', True)
    pdf.cell(40, 8, 'Cantidad', 1, 0, 'C', True)
    pdf.cell(60, 8, 'Monto Total', 1, 1, 'R', True)

    pdf.set_font('Helvetica', '', 10)
    pdf.cell(100, 7, 'Gastos Generales (Facturas Pago Directo)', 1, 0, 'L')
    pdf.cell(40, 7, str(len(det_gg)), 1, 0, 'C')
    pdf.cell(60, 7, f"${total_gg:,.0f}".replace(',', '.'), 1, 1, 'R')

    pdf.cell(100, 7, 'Rendiciones (Reembolsos)', 1, 0, 'L')
    pdf.cell(40, 7, str(len(det_rend)), 1, 0, 'C')
    pdf.cell(60, 7, f"${total_rend:,.0f}".replace(',', '.'), 1, 1, 'R')

    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(220, 220, 220)
    total_general = total_gg + total_rend
    pdf.cell(100, 8, 'TOTAL GENERAL', 1, 0, 'L', True)
    pdf.cell(40, 8, str(len(det_gg) + len(det_rend)), 1, 0, 'C', True)
    pdf.cell(60, 8, f"${total_general:,.0f}".replace(',', '.'), 1, 1, 'R', True)

    pdf.ln(10)

    # Principales categorías
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 7, 'Top 5 Categorias Gastos Generales:', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    for i, (_, row) in enumerate(resumen_gg.head(5).iterrows(), 1):
        tipo = row['Tipo'] if row['Tipo'] else '(Sin categoria)'
        pdf.cell(0, 6, f"  {i}. {tipo}: ${row['Total']:,.0f}".replace(',', '.'), 0, 1, 'L')

    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 7, 'Top 5 Clases Rendiciones:', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    for i, (_, row) in enumerate(resumen_rend.head(5).iterrows(), 1):
        clase = row['Clase'] if row['Clase'] else '(Sin clase)'
        pdf.cell(0, 6, f"  {i}. {clase}: ${row['Total']:,.0f}".replace(',', '.'), 0, 1, 'L')

    # Guardar
    nombre_limpio = nombre_proy.replace(' ', '_').replace('/', '_')[:30]
    ruta = f"../reportes/Gastos_GG_Rend_{nombre_limpio}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf.output(ruta)

    print(f'PDF generado: {ruta}')
    print(f'Gastos Generales: {len(det_gg)} registros, ${total_gg:,.0f}')
    print(f'Rendiciones: {len(det_rend)} registros, ${total_rend:,.0f}')
    print(f'TOTAL: ${total_general:,.0f}')

    return ruta

if __name__ == "__main__":
    generar_informe_gg_rendiciones("Raíces de Lanco")

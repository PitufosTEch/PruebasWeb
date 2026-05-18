"""Exportar proveedores de áridos a CSV"""
from sheets_connection import SheetsConnection
import pandas as pd

conn = SheetsConnection()

keywords = [
    'arido', 'árido', 'arena', 'grava', 'ripio', 'granular',
    'hormigon', 'hormigón', 'agregado', 'piedra', 'gravilla',
    'chancado', 'estabilizado', 'bolón', 'bolon'
]

def buscar_keywords(texto):
    if pd.isna(texto):
        return False
    texto_lower = str(texto).lower()
    return any(kw in texto_lower for kw in keywords)

# Cargar tablas
print("Cargando datos...")
df_prov = conn.get_sheet_data('Reg_pago_proveed')
df_det = conn.get_sheet_data('Reg_pago_ex_det')

# Buscar pagos con referencias a áridos
mask_obs = df_det['observaciones'].apply(buscar_keywords)
mask_det = df_det['detalle_pago'].apply(buscar_keywords)

pagos_aridos = df_det[mask_obs | mask_det].copy()

# Cruzar con proveedores
pagos_con_nombre = pagos_aridos.merge(
    df_prov[['IDU_proveed', 'Nombre', 'rut', 'email', 'telefono', 'Banco', 'cuenta']],
    left_on='proveedor',
    right_on='IDU_proveed',
    how='left'
)

# Agregar proveedores por nombre/email que no tengan pagos
mask_nombre = df_prov['Nombre'].apply(buscar_keywords)
mask_email = df_prov['email'].apply(buscar_keywords)
prov_directos = df_prov[mask_nombre | mask_email]

# Crear resumen por proveedor
resumen = pagos_con_nombre.groupby(['Nombre', 'rut', 'email', 'telefono', 'Banco', 'cuenta']).agg({
    'IDU_detpago': 'count',
    'monto': lambda x: pd.to_numeric(
        x.astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).sum()
}).reset_index()
resumen.columns = ['Nombre', 'RUT', 'Email', 'Telefono', 'Banco', 'Cuenta', 'Cantidad_Pagos', 'Monto_Total']

# Agregar proveedores directos que no estén en pagos
for _, row in prov_directos.iterrows():
    if row['Nombre'] not in resumen['Nombre'].values:
        nuevo = pd.DataFrame([{
            'Nombre': row['Nombre'],
            'RUT': row['rut'],
            'Email': row['email'],
            'Telefono': row['telefono'],
            'Banco': row['Banco'],
            'Cuenta': row['cuenta'],
            'Cantidad_Pagos': 0,
            'Monto_Total': 0
        }])
        resumen = pd.concat([resumen, nuevo], ignore_index=True)

# Ordenar por monto
resumen = resumen.sort_values('Monto_Total', ascending=False)

# Agregar columna de fuente
def clasificar_fuente(row):
    tiene_pagos = row['Cantidad_Pagos'] > 0
    en_nombre_email = buscar_keywords(str(row['Nombre'])) or buscar_keywords(str(row['Email']))

    if tiene_pagos and en_nombre_email:
        return 'Nombre/Email + Pagos'
    elif tiene_pagos:
        return 'Solo en Pagos'
    else:
        return 'Solo Nombre/Email'

resumen['Fuente'] = resumen.apply(clasificar_fuente, axis=1)

# Guardar CSV
output_path = '../proveedores_aridos.csv'
resumen.to_csv(output_path, index=False, encoding='utf-8-sig')

print(f"CSV guardado en: {output_path}")
print(f"Total proveedores: {len(resumen)}")
print(f"Monto total pagado: ${resumen['Monto_Total'].sum():,.0f}")
print("\nDesglose por fuente:")
print(resumen['Fuente'].value_counts().to_string())

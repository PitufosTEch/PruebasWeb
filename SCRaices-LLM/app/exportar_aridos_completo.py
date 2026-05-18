"""Exportar proveedores de áridos con Comuna y Proyecto"""
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

# Cargar todas las tablas necesarias
print("Cargando datos...")
df_prov = conn.get_sheet_data('Reg_pago_proveed')
df_det = conn.get_sheet_data('Reg_pago_ex_det')
df_pago = conn.get_sheet_data('Reg_pago_ex')
df_proy = conn.get_sheet_data('Proyectos')

# Buscar pagos con referencias a áridos
mask_obs = df_det['observaciones'].apply(buscar_keywords)
mask_det = df_det['detalle_pago'].apply(buscar_keywords)
pagos_aridos = df_det[mask_obs | mask_det].copy()

# Cruzar: detalle -> pago -> proyecto -> comuna
pagos_con_proy = pagos_aridos.merge(
    df_pago[['IDU_regpx', 'ID_proy']],
    on='IDU_regpx',
    how='left'
)

pagos_con_comuna = pagos_con_proy.merge(
    df_proy[['ID_proy', 'COMUNA', 'NOMBRE_PROYECTO', 'Cod_obra']],
    on='ID_proy',
    how='left'
)

# Agregar nombre del proveedor
pagos_completos = pagos_con_comuna.merge(
    df_prov[['IDU_proveed', 'Nombre', 'rut', 'email', 'telefono', 'Banco', 'cuenta']],
    left_on='proveedor',
    right_on='IDU_proveed',
    how='left'
)

# Crear resumen por proveedor con comunas donde trabajó
resumen = pagos_completos.groupby(['Nombre', 'rut', 'email', 'telefono', 'Banco', 'cuenta']).agg({
    'IDU_detpago': 'count',
    'monto': lambda x: pd.to_numeric(
        x.astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).sum(),
    'COMUNA': lambda x: ', '.join(sorted(set(str(v) for v in x.dropna() if str(v) != 'nan'))),
    'NOMBRE_PROYECTO': lambda x: ', '.join(sorted(set(str(v) for v in x.dropna() if str(v) != 'nan'))),
    'Cod_obra': lambda x: ', '.join(sorted(set(str(v) for v in x.dropna() if str(v) != 'nan')))
}).reset_index()

resumen.columns = ['Nombre', 'RUT', 'Email', 'Telefono', 'Banco', 'Cuenta',
                   'Cantidad_Pagos', 'Monto_Total', 'Comunas', 'Proyectos', 'Cod_Obras']

# Agregar proveedores por nombre/email que no tengan pagos
mask_nombre = df_prov['Nombre'].apply(buscar_keywords)
mask_email = df_prov['email'].apply(buscar_keywords)
prov_directos = df_prov[mask_nombre | mask_email]

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
            'Monto_Total': 0,
            'Comunas': '',
            'Proyectos': '',
            'Cod_Obras': ''
        }])
        resumen = pd.concat([resumen, nuevo], ignore_index=True)

# Ordenar por monto
resumen = resumen.sort_values('Monto_Total', ascending=False)

# Guardar CSV
output_path = '../proveedores_aridos.csv'
resumen.to_csv(output_path, index=False, encoding='utf-8-sig')

print(f"\nCSV guardado en: {output_path}")
print(f"Total proveedores: {len(resumen)}")
print(f"Monto total: ${resumen['Monto_Total'].sum():,.0f}")

# Mostrar comunas únicas
todas_comunas = set()
for comunas in resumen['Comunas']:
    if comunas:
        for c in comunas.split(', '):
            if c:
                todas_comunas.add(c)

print(f"\nComunas donde trabajan: {len(todas_comunas)}")
for c in sorted(todas_comunas):
    print(f"  - {c}")

"""Script para buscar proveedores de áridos en todas las tablas"""
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

# =====================================================
# 1. PROVEEDORES POR NOMBRE O EMAIL
# =====================================================
print("\n" + "=" * 70)
print("1. PROVEEDORES CON 'ÁRIDOS' EN NOMBRE O EMAIL")
print("=" * 70)

mask_nombre = df_prov['Nombre'].apply(buscar_keywords)
mask_email = df_prov['email'].apply(buscar_keywords)
prov_directos = df_prov[mask_nombre | mask_email]

for _, row in prov_directos.iterrows():
    print(f"\n{row['Nombre']}")
    print(f"  RUT: {row['rut']}")
    print(f"  Email: {row['email']}")
    print(f"  Banco: {row['Banco']} | Cuenta: {row['cuenta']}")

print(f"\n>>> Subtotal: {len(prov_directos)} proveedores")

# =====================================================
# 2. PAGOS CON REFERENCIA A ÁRIDOS EN OBSERVACIONES
# =====================================================
print("\n" + "=" * 70)
print("2. PAGOS CON REFERENCIA A ÁRIDOS (en observaciones/detalle)")
print("=" * 70)

mask_obs = df_det['observaciones'].apply(buscar_keywords)
mask_det = df_det['detalle_pago'].apply(buscar_keywords)

pagos_aridos = df_det[mask_obs | mask_det].copy()

# Cruzar con proveedores
pagos_con_nombre = pagos_aridos.merge(
    df_prov[['IDU_proveed', 'Nombre', 'rut', 'email']],
    left_on='proveedor',
    right_on='IDU_proveed',
    how='left'
)

# Agrupar por proveedor
resumen = pagos_con_nombre.groupby(['Nombre', 'rut', 'email']).agg({
    'IDU_detpago': 'count',
    'monto': lambda x: pd.to_numeric(
        x.astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce'
    ).sum()
}).reset_index()
resumen.columns = ['Proveedor', 'RUT', 'Email', 'Cantidad_Pagos', 'Monto_Total']
resumen = resumen.sort_values('Monto_Total', ascending=False)

for _, row in resumen.iterrows():
    if pd.notna(row['Proveedor']) and row['Proveedor']:
        print(f"\n{row['Proveedor']}")
        print(f"  RUT: {row['RUT']}")
        print(f"  Email: {row['Email']}")
        print(f"  Pagos: {int(row['Cantidad_Pagos'])}")
        monto = row['Monto_Total']
        if pd.notna(monto):
            print(f"  Monto Total: ${monto:,.0f}")

print(f"\n>>> Subtotal: {len(resumen)} proveedores con {len(pagos_aridos)} registros de pago")

# =====================================================
# 3. EJEMPLOS DE OBSERVACIONES
# =====================================================
print("\n" + "=" * 70)
print("3. EJEMPLOS DE OBSERVACIONES/DETALLES DE PAGO")
print("=" * 70)

for _, row in pagos_con_nombre.head(20).iterrows():
    prov = row['Nombre'] if pd.notna(row['Nombre']) else 'Sin nombre'
    obs = str(row['observaciones'])[:100] if pd.notna(row['observaciones']) else ''
    det = str(row['detalle_pago'])[:100] if pd.notna(row['detalle_pago']) else ''

    print(f"\nProveedor: {prov}")
    if obs and obs != 'nan':
        print(f"  Observación: {obs}")
    if det and det != 'nan':
        print(f"  Detalle: {det}")

# =====================================================
# 4. RESUMEN CONSOLIDADO
# =====================================================
print("\n" + "=" * 70)
print("RESUMEN CONSOLIDADO - PROVEEDORES DE ÁRIDOS")
print("=" * 70)

# Combinar todos los proveedores encontrados
todos_proveedores = set()
for _, row in prov_directos.iterrows():
    todos_proveedores.add((row['Nombre'], row['rut'], row['email']))
for _, row in resumen.iterrows():
    if pd.notna(row['Proveedor']):
        todos_proveedores.add((row['Proveedor'], row['RUT'], row['Email']))

print(f"\nTOTAL PROVEEDORES ÚNICOS: {len(todos_proveedores)}")
print("\nLista completa:")
for nombre, rut, email in sorted(todos_proveedores, key=lambda x: str(x[0])):
    if nombre:
        print(f"  - {nombre} (RUT: {rut})")

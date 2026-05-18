"""Analisis documental de un proyecto - extrae info util de PDFs"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
import fitz, pytesseract, io, os, re
from PIL import Image
from data_manager import DataManager

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ['TESSDATA_PREFIX'] = os.path.expanduser('~/tessdata')

BASE_F = 'G:/.shortcut-targets-by-id/1MAvN2Sk_sTSVzhnDoKkRn6QDBtMYCO10/documentacion_Files_'
BASE_I = 'G:/.shortcut-targets-by-id/1vd9MxZOu9kjEgzc35CaQrr1TRal92D1h/documentacion_Images'
ALL_F = os.listdir(BASE_F)

def read_pdf(filepath, max_pages=3):
    d = fitz.open(filepath)
    text = ''
    for i, page in enumerate(d):
        if i >= max_pages:
            break
        native = page.get_text()
        if len(native.strip()) > 30:
            text += native + '\n'
        else:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes('png')))
            text += pytesseract.image_to_string(img, lang='spa') + '\n'
    d.close()
    return text

def find_file(fname):
    prefix = fname.split('.pdf')[0]
    for f in ALL_F:
        if f == fname or f.startswith(prefix):
            return os.path.join(BASE_F, f)
    return None

def extract_after(text, label):
    m = re.search(label + r'\s*\n?\s*:?\s*(.+)', text, re.I)
    return m.group(1).strip().lstrip(':').strip() if m else None

def analizar_proyecto(id_proy):
    dm = DataManager()
    doc_t = dm.get_table_data('documentacion')
    ben = dm.get_table_data('Beneficiario')
    proy = dm.get_table_data('Proyectos')

    p = proy[proy['ID_proy'].astype(str) == str(id_proy)]
    nombre_proy = p.iloc[0]['NOMBRE_PROYECTO'] if len(p) > 0 else '?'

    bens = ben[ben['ID_Proy'].astype(str) == str(id_proy)]

    print('=' * 100)
    print(f'ANALISIS DOCUMENTAL — {nombre_proy} (Proyecto {id_proy})')
    print('=' * 100)
    print()

    for _, b in bens.iterrows():
        idb = str(b['ID_Benef'])
        nombre = f"{b.get('NOMBRES', '')} {b.get('APELLIDOS', '')}"
        d = doc_t[doc_t['ID_benef'].astype(str) == idb]
        if len(d) == 0:
            print(f'--- {nombre} ({idb}) --- SIN DOCUMENTACION')
            continue
        row = d.iloc[0]

        print(f'--- {nombre} ({idb}) ---')

        # ROL AVALUO
        val = str(row.get('C_ROL_det', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                rol = extract_after(text, r'N[uú]mero de Rol de Aval[uú]o')
                comuna = extract_after(text, r'Comuna')
                direccion = extract_after(text, r'Direcci[oó]n o Nombre del bien ra[ií]z')
                registrado = extract_after(text, r'Registrado a Nombre de')
                rut_reg = extract_after(text, r'RUN o RUT Registrado')
                avaluo = extract_after(text, r'AVAL[UÚ]O TOTAL')
                # Buscar monto en siguiente linea si avaluo es '$'
                if avaluo and avaluo.startswith('$'):
                    m = re.search(r'AVAL[UÚ]O TOTAL\s*\n?\s*:\s*\$\s*\n?\s*([\d\.\,]+)', text, re.I)
                    if m:
                        avaluo = '$' + m.group(1)
                sup_m = re.search(r'Superficie Suelo\s*\n?\s*\(Ha\)\s*\n?\s*:?\s*([\d,\.]+)', text, re.I)
                sup = sup_m.group(1) if sup_m else '?'
                print(f'  ROL Avaluo: {rol} | Comuna: {comuna} | Dir: {direccion}')
                print(f'    Registrado: {registrado} | RUT: {rut_reg}')
                print(f'    Avaluo: {avaluo} | Sup: {sup} ha')

        # CONTRATO
        val = str(row.get('contrato', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 5)
                m = re.search(r'CONTRATO DE CONSTRUCCI[OÓ]N\s+REP\s+NRO\s+(\d+)\s+otorgado el (\d+ de \w+ de \d+)', text, re.I)
                if m:
                    print(f'  Contrato: REP {m.group(1)} | Fecha: {m.group(2)}')
                else:
                    m2 = re.search(r'otorgado el (\d+ de \w+ de \d+)', text, re.I)
                    if m2:
                        print(f'  Contrato: Fecha {m2.group(1)}')

        # MOD CONTRATO
        val = str(row.get('mod_contrato', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 3)
                m = re.search(r'MODIFICACI[OÓ]N.*?otorgado el (\d+ de \w+ de \d+)', text, re.I)
                print(f'  Mod.Contrato: {m.group(1) if m else "SI (fecha no extraida)"}')

        # PERMISO EDIFICACION
        val = str(row.get('C_permiso', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                m_num = re.search(r'NUMERO DE PERMISO\s*\n?\s*(\d+)', text, re.I)
                m_rol = re.search(r'ROL\s*S\.?I\.?I\.?\s*\n?\s*([\d\s\-/]+)', text, re.I)
                m_sup = re.search(r'SUPERFICIE TOTAL TERRENO.*?([\d\.,]+)', text, re.I)
                print(f'  Permiso: N.{m_num.group(1) if m_num else "?"} | ROL SII: {m_rol.group(1).strip() if m_rol else "?"} | Sup.Terreno: {m_sup.group(1) if m_sup else "?"}m2')

        # ANTEPROYECTO
        val = str(row.get('anteproyecto', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                m_rol = re.search(r'ROL\s*S\.?I\.?I\.?\s*\n?\s*([\d\s\-/]+)', text, re.I)
                m_fecha = re.search(r'FECHA\s*[-:\s]*\n?\s*([\d/\-]+)', text, re.I)
                m_res = re.search(r'N[°*]\s*DE RESOLUCI[OÓ]N:?\s*\n?\s*(\d+)', text, re.I)
                print(f'  Anteproyecto: ROL {m_rol.group(1).strip() if m_rol else "?"} | Fecha: {m_fecha.group(1) if m_fecha else "?"} | Res: {m_res.group(1) if m_res else "?"}')

        # DOMINIO
        for col_dom in ['dominio_act', 'C_dominio']:
            val = str(row.get(col_dom, ''))
            if 'documentacion_' in val:
                fp = find_file(val.split('/')[-1])
                if fp:
                    text = read_pdf(fp, 4)
                    m = re.search(r'FOJAS\s+(\d+).*?N[°º]?\s*(\d+).*?REGISTRO DE PROPIEDAD.*?(\d{4})', text, re.I | re.S)
                    label = 'Dominio Act.' if col_dom == 'dominio_act' else 'Dominio'
                    if m:
                        print(f'  {label}: Fojas {m.group(1)}, N.{m.group(2)}, Ano {m.group(3)}')
                    else:
                        print(f'  {label}: SI (datos no extraidos)')
                break

        # ESTUDIO TITULO
        val = str(row.get('C_est_titulo', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 3)
                m_fecha = re.search(r'Temuco,?\s*(\d+ de \w+ \d+)', text, re.I)
                tiene_ok = 'disponibilidad' in text.lower() or 'validado' in text.lower() or 'conforme' in text.lower()
                print(f'  Est.Titulo: {m_fecha.group(1) if m_fecha else "?"} | {"OK - validado" if tiene_ok else "pendiente revision"}')

        # CONADI
        val = str(row.get('C_conadi', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 2)
                m_has = re.search(r'(\d[\d,\.]+)\s*(?:has?\.?|hect[aá]reas)', text, re.I)
                m_lote = re.search(r'(?:Lote|LT)\s*N[°º*]?\s*(\d+)', text, re.I)
                print(f'  CONADI: {m_has.group(1) if m_has else "?"} has | Lote: {m_lote.group(1) if m_lote else "?"}')

        # RSH
        val = str(row.get('C_RSH', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                m_folio = re.search(r'Folio\s+(\d+)', text, re.I)
                m_tramo = re.search(r'[Tt]ramo\s*[:\s]*(\d+)', text)
                m_calse = re.search(r'Calificaci[oó]n Socioecon[oó]mica\s*[:\s]*(\d+)', text, re.I)
                tramo = m_tramo.group(1) if m_tramo else (m_calse.group(1) if m_calse else '?')
                print(f'  RSH: Folio {m_folio.group(1) if m_folio else "?"} | CSE: {tramo}%')

        # CARNET
        val = str(row.get('carnet', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 1)
                m_rut = re.search(r'RUN\s+([\d\.\-]+)', text, re.I)
                m_venc = re.search(r'(\d{2}[\s\.]*\w+[\s\.]*\d{4})', text)
                if m_rut:
                    print(f'  Carnet: RUN {m_rut.group(1)}')

        # INFORME PREVIO
        val = str(row.get('C_Infprev', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                m_cert = re.search(r'CERTIFICADO\s*N[°*]?\s*\n?\s*[-/]?\s*(\d+)', text, re.I)
                m_fecha = re.search(r'(\d{2}/\d{2}/\d{4})', text)
                print(f'  Inf.Previo: Cert.{m_cert.group(1) if m_cert else "?"} | Fecha: {m_fecha.group(1) if m_fecha else "?"}')

        # T1 (TE1 Electrico)
        val = str(row.get('T1', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                m_folio = re.search(r'FOLIO\s*(?:INSCRIPCION)?\s*\n?\s*(\d+)', text, re.I)
                m_potencia = re.search(r'(?:Potencia|kW)\s*[:\s]*([\d,\.]+)', text, re.I)
                print(f'  TE1: Folio {m_folio.group(1) if m_folio else "?"} | Potencia: {m_potencia.group(1) if m_potencia else "?"}kW')

        # FACTIBILIDAD AP / ALC
        for col_ap, label_ap in [('C_Fact_AP', 'Fact.AP'), ('C_Fact_ALC', 'Fact.ALC')]:
            val = str(row.get(col_ap, ''))
            if 'documentacion_' in val:
                fp = find_file(val.split('/')[-1])
                if fp:
                    text = read_pdf(fp, 2)
                    m_res = re.search(r'RESOLUCI[OÓ]N\s+EXENTA\s+N[°*]?\s*(\d+)', text, re.I)
                    m_fecha = re.search(r'FECHA:\s*([\d/\-]+)', text, re.I)
                    print(f'  {label_ap}: Res.{m_res.group(1) if m_res else "?"} | Fecha: {m_fecha.group(1) if m_fecha else "?"}')

        # ACTA TERRENO
        val = str(row.get('actaterr', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                m_fecha = re.search(r'FECHA:\s*_?\s*([\d/\-\s]+\d{4})', text, re.I)
                m_exp = re.search(r'EXPEDIENTE\s*:\s*\n?\s*(.*)', text, re.I)
                print(f'  Acta Terreno: Fecha {m_fecha.group(1).strip() if m_fecha else "?"} | Exp: {m_exp.group(1).strip() if m_exp else "?"}')

        # F1
        val = str(row.get('F1', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 1)
                has_f1 = len(text.strip()) > 50
                print(f'  F1 Control: {"SI" if has_f1 else "?"} (ficha prerrecepcion)')

        # RECEPCION
        val = str(row.get('C_recepcion', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp)
                m_cert = re.search(r'N[°*]\s*DE CERTIFICADO\s*\n?\s*(\d+)', text, re.I)
                m_fecha = re.search(r'FECHA\s*\n?\s*([\d\-/]+)', text, re.I)
                print(f'  RECEPCION DEFINITIVA: Cert.{m_cert.group(1) if m_cert else "?"} | Fecha: {m_fecha.group(1) if m_fecha else "?"}')
        else:
            print(f'  Recepcion: PENDIENTE')

        # ESCRITURA
        val = str(row.get('C_escritura_perm', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 2)
                m = re.search(r'otorgado el (\d+ de \w+ de \d+)', text, re.I)
                print(f'  Escritura Permiso: {m.group(1) if m else "SI"}')

        # PROHIBICION
        val = str(row.get('prohibicion', ''))
        if 'documentacion_' in val:
            fp = find_file(val.split('/')[-1])
            if fp:
                text = read_pdf(fp, 2)
                is_declaracion = 'DECLARACION JURADA' in text.upper()
                print(f'  Prohibicion: {"Decl.Jurada tierra indigena" if is_declaracion else "SI"}')

        print()

if __name__ == '__main__':
    pid = sys.argv[1] if len(sys.argv) > 1 else '122'
    analizar_proyecto(pid)

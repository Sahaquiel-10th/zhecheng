"""Read the source workbook, resolving WPS DISPIMG identities without changing it."""
from pathlib import Path
import json, posixpath, re, sys, zipfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps, ImageDraw
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / '城院文创-实时更新.xlsx'
OUT = ROOT / 'catalog-draft'
OUT.joinpath('assets').mkdir(parents=True, exist_ok=True)
ROOT.joinpath('preview').mkdir(exist_ok=True)
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'xdr':'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

def category(name):
    if any(w in name for w in ['杯','叠盏']): return '杯盏茶饮'
    if any(w in name for w in ['书签','笔','明信片','文件袋','本子','日历']): return '纸笔书香'
    if any(w in name for w in ['丝巾','袋','雨伞']): return '随身好物'
    if any(w in name for w in ['非遗','装饰画']): return '非遗雅作'
    if '礼盒' in name: return '节令礼遇'
    return '生活小景'

with zipfile.ZipFile(SOURCE) as z:
    strings = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
    rels = {n.attrib['Id']:posixpath.normpath('xl/'+n.attrib['Target'])
            for n in ET.fromstring(z.read('xl/_rels/cellimages.xml.rels'))}
    image_map = {}
    for pic in ET.fromstring(z.read('xl/cellimages.xml')).findall('.//xdr:pic',NS):
        key = pic.find('.//xdr:cNvPr',NS).attrib['name']
        rid = pic.find('.//a:blip',NS).attrib['{'+NS['r']+'}embed']
        image_map[key] = rels[rid]
    products = []
    for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//s:sheetData/s:row',NS)[2:]:
        cells = {}
        for cell in row:
            col = re.sub(r'\d','',cell.attrib['r'])
            v = cell.find('s:v',NS)
            f = cell.find('s:f',NS)
            cells[col] = strings[int(v.text)] if cell.attrib.get('t')=='s' and v is not None else (f.text if f is not None else (v.text if v is not None else ''))
        if cells.get('A') and cells.get('B'):
            p = dict(id=int(cells['A']),row=int(row.attrib['r']),name=cells['B'].strip(),brand=cells.get('C','').strip(),spec=cells.get('D','').strip(),material=cells.get('E','').strip(),price=cells.get('F','').strip(),barcodes=[],images=[])
            p['category'] = category(p['name'])
            p['shortName'] = re.sub(r'^.*?·\s*','',p['name'])
            p['priceValue'] = float(re.search(r'[\d.]+',p['price']).group())
            products.append(p)
        if not products: continue
        p = products[-1]
        if cells.get('G'): p['barcodes'].append(cells['G'].strip())
        for col in ['H','I']:
            match = re.search(r'ID_[A-F0-9]+',cells.get(col,''))
            if not match: continue
            key = match.group()
            assert key in image_map, (p['name'],key)
            stem = Path(image_map[key]).stem
            full, thumb = f'assets/{stem}.webp', f'assets/{stem}-thumb.webp'
            if not (OUT/full).exists():
                im = Image.open(BytesIO(z.read(image_map[key]))).convert('RGB')
                im.thumbnail((1800,1800))
                im.save(OUT/full,'WEBP',quality=88)
                im.thumbnail((640,640))
                im.save(OUT/thumb,'WEBP',quality=83)
            p['images'].append({'full':full,'thumb':thumb})
    assert len(products)==39
    assert all(p['images'] for p in products)
    (OUT/'products.js').write_text('window.PRODUCTS = '+json.dumps(products,ensure_ascii=False,indent=2)+';\n')
    (ROOT/'preview'/'catalog-data.json').write_text(json.dumps(products,ensure_ascii=False,indent=2))
    sheet=Image.new('RGB',(1000,((len(products)+4)//5)*170),'#f1f3f4')
    draw=ImageDraw.Draw(sheet)
    for i,p in enumerate(products):
        im=Image.open(OUT/p['images'][0]['thumb'])
        im.thumbnail((184,140))
        x,y=(i%5)*200,(i//5)*170
        sheet.paste(im,(x+(200-im.width)//2,y))
        draw.text((x+10,y+145),str(p['id']),fill='black')
    sheet.save(ROOT/'preview'/'contact-sheet.jpg')
    print(json.dumps({'products':len(products),'product_images':sum(len(p['images']) for p in products),'categories':{c:sum(p['category']==c for p in products) for c in dict.fromkeys(p['category'] for p in products)}},ensure_ascii=False))

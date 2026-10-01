"""Render a staged product library from its exported GLBs, then make a review gallery.

Rendering exported geometry (rather than drafts) also checks material/texture bindings.
Only staging is modified; publish still verifies both live and staged tree hashes.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexa.three_d import render as R
from nexa.three_d.geometry import gltf
from nexa.three_d.manifest import load_manifest
from nexa.three_d.pipeline import ModelBuild
from update_model_library import tree_hash


def read_export(project, folder):
    doc = gltf.read_glb((folder / project.asset_path).read_bytes())
    saved = {}
    for i, tex in enumerate(doc.textures):
        data, mime = doc.images[tex['source']]
        rel = f'textures/catalog_{i}.' + ('png' if mime == 'image/png' else 'jpg')
        (folder / rel).parent.mkdir(exist_ok=True)
        (folder / rel).write_bytes(data)
        saved[i] = rel
    materials = [gltf.material_from_gltf(i, mat, saved) for i, mat in enumerate(doc.materials)]
    meshes = {}
    for node in doc.nodes:
        meshes.setdefault(node.name, []).extend((prim.mesh, materials[prim.material].id)
            for prim in node.primitives if prim.material is not None)
    if {p.id for p in project.parts} != set(meshes):
        raise ValueError(f'Exported parts differ from manifest: {project.id}')
    return ModelBuild(project.parts, meshes, {m.id:m for m in materials}, project.explosion_plan,
                      has_assembly=project.has_assembly)


def render_library(staging):
    from PIL import Image, ImageDraw, ImageFont
    report_path = staging / 'update_report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report['errors']:
        raise ValueError('Resolve staging errors before generating the gallery')
    cards = []
    count = len(report['projects'])
    sheet = Image.new('RGB', (1500, ((count+4)//5)*245+85), '#edf1f5')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 17)
    heading = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 28)
    draw.text((24,16),'NEXA / PRODUCT MODEL LIBRARY',font=heading,fill='#172334')
    draw.text((24,52),f'{count} models · studio previews from exported GLB files',font=font,fill='#5b6777')
    for i, item in enumerate(sorted(report['projects'],key=lambda x:x['id'])):
        folder = staging/'projects'/item['id']
        project = load_manifest(folder)
        print('RENDER',i+1,count,project.id,flush=True)
        build = read_export(project,folder)
        items = build.render_items()
        for view in ('front','back','left','right','top','bottom','iso'):
            path = folder / ('thumbnail.png' if view=='iso' else f'renders/{view}.png')
            path.parent.mkdir(exist_ok=True)
            result = R.render(items,view,512 if view=='iso' else 320,ssaa=2 if view=='iso' and item['kind']=='redesigned_product_study' else 1,
                              background='light',outline=False,texture_root=folder)
            path.write_bytes(R.png_bytes(result.image))
        if project.has_assembly:
            (folder/'renders/exploded.png').write_bytes(R.png_bytes(R.render(build.render_items(1.0),'iso',384,
                ssaa=1,background='light',outline=False,texture_root=folder).image))
        item['staged_hash'] = tree_hash(folder)
        thumb = Image.open(folder/'thumbnail.png').convert('RGB').resize((220,220),Image.Resampling.LANCZOS)
        x,y=(i%5)*300,(i//5)*245+85
        sheet.paste(thumb,(x+40,y))
        title=project.name if len(project.name)<34 else project.name[:31]+'…'
        draw.text((x+12,y+222),title,font=font,fill='#172334')
        name=html.escape(project.name)
        pid=html.escape(project.id)
        if item['kind']=='replaced_with_source_geometry':
            badge='Lưới tham chiếu sản phẩm'
        elif item['kind']=='redesigned_product_study':
            badge='Thiết kế lại hình học'
        elif item['kind']=='preserved_external_geometry':
            badge='Giữ lưới gốc · dựng lại ảnh'
        else:
            badge='Mô hình tham số'
        cards.append(f'<article data-name="{name.casefold()}"><img loading="lazy" src="projects/{pid}/thumbnail.png" alt="{name}">'
            f'<div class="content"><span>{badge}</span><h2>{name}</h2><p>{len(project.parts)} bộ phận · {project.category}</p>'
            f'<div class="views" data-id="{pid}"><button data-view="iso">3/4</button><button data-view="front">Trước</button>'
            f'<button data-view="left">Bên</button><button data-view="top">Trên</button>'+
            ('<button data-view="exploded">Tách bộ phận</button>' if project.has_assembly else '')+
            f'</div><a href="projects/{pid}/model.glb" download>Tải mô hình GLB</a></div></article>')
        # Preserve progress and publish hashes if an unrelated later preview fails.
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sheet.save(staging/'catalog.jpg',quality=94)
    page='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXA — Kho mô hình sản phẩm</title><style>
*{box-sizing:border-box}body{margin:0;background:#edf1f5;color:#172334;font:15px system-ui,sans-serif}
header{padding:48px 5vw 28px;background:#152233;color:white}header small{letter-spacing:4px;color:#95b6ce}
h1{font-size:clamp(30px,4vw,52px);margin:14px 0}header p{color:#c2d0de;max-width:750px;line-height:1.7}
input{display:block;margin:24px 5vw;padding:14px 18px;border:1px solid #ccd5df;border-radius:12px;width:min(90vw,520px);font:inherit}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:22px;padding:0 5vw 48px}
article{background:white;border-radius:18px;overflow:hidden;border:1px solid #d8e0e9}article[hidden]{display:none}
img{width:100%;aspect-ratio:1;object-fit:contain;display:block}.content{padding:22px}span{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#4b6b83}
h2{font-size:20px;margin:9px 0}p{color:#6b7885}button{background:#edf2f7;color:#24394f;border:0;border-radius:7px;padding:8px;cursor:pointer}
.views{display:flex;gap:5px;flex-wrap:wrap;margin:16px 0}button:focus,button:hover{background:#cadbea}a{color:#23677d;text-underline-offset:4px;font-size:13px}
</style><header><small>NEXA / PRODUCT STUDIES</small><h1>Kho mô hình sản phẩm</h1>
<p>Hình dáng, cấu tạo và vật liệu được trình bày trên nền studio. Mô hình tham khảo hình học không đồng nghĩa với bản CAD được hãng xác nhận.</p></header>
<input aria-label="Tìm mô hình" placeholder="Tìm tên mô hình…"><main>'''+''.join(cards)+'''</main><script>
document.querySelector('input').addEventListener('input',e=>document.querySelectorAll('article').forEach(a=>a.hidden=!a.dataset.name.includes(e.target.value.toLocaleLowerCase('vi'))));
document.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{let id=b.parentElement.dataset.id,v=b.dataset.view;b.closest('article').querySelector('img').src='projects/'+id+'/'+(v==='iso'?'thumbnail.png':'renders/'+v+'.png')}));
</script></html>'''
    (staging/'catalog.html').write_text(page,encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('staging',type=Path)
    render_library(parser.parse_args().staging.resolve())

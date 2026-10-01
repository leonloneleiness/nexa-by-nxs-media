"""Reproducible product studies for legacy generic library entries (millimetres).

These are visual product studies, not manufacturer CAD or fabrication drawings.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder
from nexa.three_d.generation.templates import details as D
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K, materials as M, profiles as P
from nexa.three_d.geometry.kernel import Shape


def keyboard(spec):
    """84-key ANSI 75% layout, 317 x 129 mm enclosure inspired by Keychron K2."""
    mats = MC.tech_materials(spec, primary="#30343a", secondary="#787d84", accent="#db603e")
    mats['keys'] = M.material('keys', 'plastic', '#969ba1', 0, .52)
    mats['modifiers'] = M.material('modifiers', 'plastic', '#4b5058', 0, .52)
    mats['legends'] = M.material('legends', 'plastic', '#ffffff', 0, .52)
    mats['legends'].textures['base_color'] = 'textures/key_legends.png'
    b = AssemblyBuilder(spec.name or 'Bàn phím cơ 84 phím', 'generic', mats)
    body = K.rounded_box(317, 129, 20, 3, segments=16).translate(0, 0, 12)
    cavity = K.rounded_box(303, 116, 20, 2, segments=12).translate(0, 0, 20)
    port = K.rounded_box(12, 8, 5, 2, segments=12).translate(-125, 64, 12)
    b.add('case', 'Vỏ nhôm và đáy', 'Aluminum case', 'shell', Shape(body-cavity-port, 'aluminum_dark'),
          explode_distance=25, explode_dir=(0,0,-1), explode_order=4)
    b.add('pcb', 'Bo mạch bàn phím', 'Keyboard PCB', 'electronics',
          Shape(K.rounded_box(300,113,1.6,2).translate(0,0,10.8), 'pcb'), parent_id='case',
          explode_distance=22, explode_order=3)
    plate = K.rounded_box(302,115,1.5,2).translate(0,0,17)
    # Each row spans 16 units; explicit widths keep Enter/Shift/spacebar realistic.
    rows = [
        [(x,1) for x in ['Esc']+[f'F{i}' for i in range(1,13)]+['Prt','Del','Home']],
        [(x,1) for x in ['`','1','2','3','4','5','6','7','8','9','0','-','=']]+[('Back',2),('PgUp',1)],
        [('Tab',1.5)]+[(x,1) for x in ['Q','W','E','R','T','Y','U','I','O','P','[',']']]+[('\\',1.5),('PgDn',1)],
        [('Caps',1.75)]+[(x,1) for x in ['A','S','D','F','G','H','J','K','L',';',"'"]]+[('Enter',2.25),('End',1)],
        [('Shift',2.25)]+[(x,1) for x in ['Z','X','C','V','B','N','M',',','.','/']]+[('Shift',1.75),('Up',1),('Fn',1)],
        [('Ctrl',1.25),('Win',1.25),('Alt',1.25),('Space',6.25),('Alt',1),('Fn',1),('Ctrl',1),('Left',1),('Down',1),('Right',1)],
    ]
    labels, holes, switches = [], [], []
    idx = 0
    for row, keys in enumerate(rows):
        x = -152
        y = 47.5-row*19
        for label, units in keys:
            w = units*19-1.5
            cx = x+units*19/2
            x += units*19
            holes.append(K.box(14,14,5).translate(cx,y,17))
            switches.append(K.rounded_box(13.8,13.8,5,1).translate(cx,y,18))
            cap = K.chamfer_box(w,17.5,8,1.7).translate(cx,y,25)
            # Shallow concavity, with a flat legend region at the front of the key.
            dish = K.cylinder(32, w+2, segments=64).rotate(0,90,0).translate(cx-w/2-1,y,60)
            mid = 'paint_accent' if label == 'Esc' else ('keys' if len(label)==1 else 'modifiers')
            b.add(f'key_{idx:02}', label, label+' key', 'keycap', Shape(cap-dish,mid,40), parent_id='plate',
                  explode_distance=16+row*2, explode_order=1, dimensions={'width_mm':w})
            # Small flat decal entirely inside the uncut top strip; texture contains glyphs and matching background.
            verts=np.array([[cx-5,y-7,29.02],[cx+5,y-7,29.02],[cx+5,y-1,29.02],[cx-5,y-1,29.02]])
            col, rr=idx%12,idx//12
            uv=np.array([[col/12,(rr+1)/7],[(col+1)/12,(rr+1)/7],[(col+1)/12,rr/7],[col/12,rr/7]])
            mesh=K.MeshData(verts,np.array([[0,1,2],[0,2,3]]),np.tile([0.,0.,1.],(4,1)),uv)
            b.drafts[-1].shapes.append(Shape(None,'legends',mesh=mesh))
            labels.append((label,mid))
            idx+=1
    b.add('plate','Tấm định vị switch','Switch plate','frame',Shape(plate-K.Solid.union_all(holes),'steel'),
          parent_id='case',explode_distance=28,explode_order=2)
    b.add('switches','84 switch cơ','Mechanical switches','electronics',Shape(K.Solid.union_all(switches),'plastic_black'),
          parent_id='pcb',explode_distance=18,explode_order=2)
    feet=[K.rounded_box(24,9,2,2).translate(x,y,1) for x in (-128,128) for y in (-48,48)]
    b.add('feet','Chân cao su chống trượt','Rubber feet','foot',Shape(K.Solid.union_all(feet),'rubber'),parent_id='case',
          explode_distance=10,explode_dir=(0,0,-1),explode_order=3)
    socket=K.rounded_box(11,7,4,1).translate(-125,61,12)-K.rounded_box(9,9,2.5,1).translate(-125,63,12)
    b.add('usb_c','Cổng USB-C','USB-C connector','electronics',Shape(socket,'steel'),parent_id='pcb')
    screws=D.screws_at([(x,y,3) for x in (-145,145) for y in (-54,54)],(0,0,-1),2)
    b.add('screws','Vít đáy','Case screws','screw',Shape(screws,'steel_black_oxide'),parent_id='case')
    b.metadata.update(product_study='75% mechanical keyboard',key_count=idx,legend_cells=labels,
                      reference_url='https://www.keychron.com/products/keychron-k2-wireless-mechanical-keyboard',
                      exact_replica=False)
    # +X is the front of the product in the application.
    b.rotate_all_z(90)
    return b.build()


def write_keyboard_texture(build, dest: Path):
    from PIL import Image, ImageDraw, ImageFont
    cells=build.metadata.get('legend_cells')
    if not cells:
        return
    colors={'keys':'#969ba1','modifiers':'#4b5058','paint_accent':'#db603e'}
    img=Image.new('RGB',(1536,448))
    draw=ImageDraw.Draw(img)
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    font=ImageFont.truetype(str(font_path),38) if font_path.exists() else ImageFont.load_default()
    for i,(label,mid) in enumerate(cells):
        x,y=i%12*128,i//12*64
        draw.rectangle((x,y,x+127,y+63),fill=colors[mid])
        draw.text((x+64,y+32),'' if label=='Space' else label,font=font,anchor='mm',fill='#f1f1ed')
    path=dest/'textures/key_legends.png'
    path.parent.mkdir(parents=True,exist_ok=True)
    img.save(path)


def tracked_display(spec):
    """Exterior-only tracked scale model; no functional weapon internals."""
    mats=MC.tech_materials(spec,primary='#68705a',secondary='#35392f',accent='#b5aa82')
    b=AssemblyBuilder(spec.name or 'Mô hình xe bánh xích','generic',mats)
    hull=K.hull_points([(-135,y,z) for y in (-54,54) for z in (30,75)]+
                       [(140,y,42) for y in (-53,53)]+[(115,y,78) for y in (-53,53)])
    b.add('hull','Thân xe','Hull','body',Shape(hull,'paint_primary'),explode_order=4)
    for sy,side in ((1,'left'),(-1,'right')):
        yc=sy*69
        # Closed racetrack profile, wheels, separate shoes and pins.
        ring=(K.rounded_box(292,24,70,34,segments=32)-K.rounded_box(276,30,54,26,segments=32)).translate(0,yc,37)
        shoes=[]
        for x in np.linspace(-109,109,23):
            for z in (3,71):
                shoes.append(K.chamfer_box(8.5,27,4,0.8).translate(x,yc,z))
        for end in (-1,1):
            for angle in np.linspace(-80,80,9):
                a=math.radians(angle)
                shoes.append(K.chamfer_box(8.5,27,4,.8).rotate(0,90-angle*end,0).translate(end*(111+34*math.cos(a)),yc,37+34*math.sin(a)))
        b.add('track_'+side,'Dải xích '+side,'Track '+side,'track',
              [Shape(ring,'steel_dark'),Shape(K.Solid.union_all(shoes),'steel_black_oxide')],parent_id='hull',
              explode_dir=(0,sy,0),explode_distance=45,explode_order=1)
        for i,x in enumerate((-110,-66,-22,22,66,110)):
            wheel=K.cylinder(24,19,segments=48).rotate(90,0,0).translate(x,yc+9.5,32)
            hub=K.cylinder(14,21,segments=36).rotate(90,0,0).translate(x,yc+10.5,32)
            rim=(K.cylinder(20,1.5,segments=48)-K.cylinder(17,2,segments=48)).rotate(90,0,0).translate(x,yc+sy*10.5+(1.5 if sy>0 else 0),32)
            bolts=D.screws_at([(x+10*math.cos(a),yc+sy*11,32+10*math.sin(a))
                               for a in np.linspace(0,2*math.pi,6,endpoint=False)],(0,sy,0),1.4)
            b.add(f'wheel_{side}_{i}','Bánh đỡ xích','Road wheel','wheel',
                  [Shape(wheel,'rubber'),Shape(hub,'paint_primary'),Shape(rim,'steel_dark'),Shape(bolts,'steel_zinc')],parent_id='hull',joint_axis=(0,1,0),
                  explode_dir=(0,sy,0),explode_distance=28,explode_order=2)
        fender=K.chamfer_box(290,31,3,1).translate(0,yc,80)
        b.add('fender_'+side,'Chắn bùn','Fender','shell',Shape(fender,'paint_secondary'),parent_id='hull',explode_distance=30)
    turret=K.hull_points([(x,y,82) for x in (-62,66) for y in (-44,44)]+
                         [(x,y,114) for x in (-44,38) for y in (-31,31)])
    b.add('turret','Tháp xoay mô hình','Display turret','shell',Shape(turret,'paint_primary'),parent_id='hull',
          joint_axis=(0,0,1),pivot=(0,0,82),explode_distance=50,explode_order=2)
    tube=(K.cylinder(5.5,125,segments=32)-K.cylinder(3.5,126,segments=32)).rotate(0,90,0).translate(44,0,98)
    b.add('display_tube','Ống trang trí','Display tube','trim',Shape(tube,'paint_secondary'),parent_id='turret',
          explode_dir=(1,0,0),explode_distance=30)
    for i,y in enumerate((-18,18)):
        hatch=K.cylinder(13,3,segments=48).translate(-12,y,114)
        handle=K.rounded_box(10,3,3,1).translate(-12,y,118)
        b.add('hatch_'+str(i),'Nắp cửa nóc','Roof hatch','shell',[Shape(hatch,'paint_secondary'),Shape(handle,'steel_dark')],parent_id='turret')
    vents=[K.box(1.8,70,2).translate(-90+i*4,0,77) for i in range(10)]
    b.add('deck_grille','Lưới khoang sau','Rear deck grille','trim',Shape(K.Solid.union_all(vents),'steel_black_oxide'),parent_id='hull')
    for sy in (-1,1):
        box=K.chamfer_box(55,15,18,2).translate(-15,sy*44,94)
        straps=K.Solid.union_all([K.box(2,15.4,18.4).translate(x,sy*44,94) for x in (-32,2)])
        b.add('stowage_'+str(sy),'Hộp đồ bên hông','Stowage box','shell',
              [Shape(box,'paint_secondary'),Shape(straps,'steel_dark')],parent_id='turret',explode_dir=(0,sy,0),explode_distance=25)
        lamp=K.cylinder(4.2,3.5,segments=32).rotate(0,90,0).translate(126,sy*43,60)
        lens=K.cylinder(3,0.5,segments=32).rotate(0,90,0).translate(129.5,sy*43,60)
        b.add('lamp_'+str(sy),'Đèn phía trước','Front lamp','trim',
              [Shape(lamp,'steel_dark'),Shape(lens,'glass')],parent_id='hull')
    optics=K.chamfer_box(12,26,8,1).translate(12,0,115)
    glass=K.box(.6,20,4).translate(18.1,0,116)
    b.add('optics','Cửa kính quan sát','Observation window','trim',
          [Shape(optics,'paint_secondary'),Shape(glass,'lens')],parent_id='turret')
    b.metadata.update(product_study='Exterior scale display model',exact_replica=False)
    return b.build()


def hex_case(spec):
    mats=MC.tech_materials(spec,primary='#785b40',secondary='#302b28',accent='#bc9562')
    b=AssemblyBuilder(spec.name or 'Hộp lục giác','generic',mats)
    outer=K.extrude(P.circle(60,6),48)
    inner=K.extrude(P.circle(56,6),49).translate(0,0,3)
    b.add('case','Thân hộp lục giác','Hexagonal case','shell',Shape(outer-inner,'paint_primary'))
    lid=K.extrude(P.circle(60,6),4).translate(0,0,49)
    lip=(K.extrude(P.circle(55.6,6),5)-K.extrude(P.circle(53.5,6),6)).translate(0,0,44)
    b.add('lid','Nắp và gờ định vị','Lid and locating lip','shell',Shape(lid+lip,'paint_secondary'),parent_id='case',explode_distance=35,explode_order=1)
    liner=K.extrude(P.circle(55.5,6),1.5).translate(0,0,3)
    b.add('liner','Lót đáy','Base liner','trim',Shape(liner,'rubber'),parent_id='case',explode_distance=15,explode_order=2)
    b.metadata.update(product_study='Hexagonal storage case',exact_replica=False)
    return b.build()

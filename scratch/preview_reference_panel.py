from pathlib import Path
source = Path('scratch/render_3d_ui.py').read_text(encoding='utf-8')
prefix = source.split('models = [{')[0]
exec(compile(prefix, str(Path('scratch/render_3d_ui.py').resolve()), 'exec'), globals())
preview_bridge = Fake3D({}, [])
preview_nexa = FakeNexa()
preview = render('ModelGenerationPanel.qml', {'nexa3d': preview_bridge, 'nexa': preview_nexa}, 980, 760, 'reference_panel_wide.png')
preview2 = render('ModelGenerationPanel.qml', {'nexa3d': preview_bridge, 'nexa': preview_nexa}, 640, 800, 'reference_panel_narrow.png')

fixture = ROOT / "results/product_redesign_20260930/projects/20260926-001132-5a56f5/thumbnail.png"
preview2.rootObject().setReference("front", QUrl.fromLocalFile(str(fixture)).toString())
preview2.show()
pump(0.5)
preview2.grabWindow().save(str(out / "reference_panel_selected.png"))
preview2.hide()

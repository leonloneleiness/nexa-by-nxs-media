from pathlib import Path

import numpy as np
import pytest

from nexa.three_d.generation.templates import catalog_products as products
from nexa.three_d.pipeline import GenerationPipeline, ModelBuild
from nexa.three_d.spec import ModelSpec
from nexa.three_d.geometry import gltf
from nexa.three_d.validator import validate_glb_bytes, Limits


@pytest.mark.parametrize('builder', [products.keyboard, products.tracked_display, products.hex_case])
def test_product_meshes_export_with_valid_hierarchy_and_materials(builder, tmp_path):
    asm = builder(ModelSpec(category='generic'))
    build = ModelBuild.from_assembly(asm)
    products.write_keyboard_texture(build, tmp_path)
    # Texture generation matches the regular pipeline.
    from nexa.three_d.geometry import materials as M
    M.write_textures(tmp_path, set(M.MICRO_TEXTURES))
    GenerationPipeline(None, None, None)._write_glbs(build, tmp_path)
    ids = {p.id for p in build.parts}
    for part in build.parts:
        assert part.parent_id is None or part.parent_id in ids
        assert part.triangles > 0
        for mesh, mid in build.meshes[part.id]:
            assert mid in build.materials
            assert np.isfinite(mesh.vertices).all()
            assert np.isfinite(mesh.normals).all()
    data = (tmp_path / 'model.glb').read_bytes()
    result = validate_glb_bytes(data, Limits(), 'model.glb')
    assert result.ok, result.errors
    assert len(gltf.read_glb(data).nodes) == len(ids)


def test_keyboard_is_a_full_size_84_key_product_not_single_key():
    asm = products.keyboard(ModelSpec(category='generic'))
    caps = [bp for bp in asm.parts if bp.part.category == 'keycap']
    assert len(caps) == asm.metadata['key_count'] == 84
    case = asm.part('case').part.bounds.size
    assert sorted(case) == pytest.approx([20, 129, 317], abs=.1)
    assert {'pcb', 'plate', 'switches', 'usb_c', 'feet'} <= {p.part.id for p in asm.parts}
    assert len(asm.metadata['legend_cells']) == 84


def test_tracks_include_individual_road_wheels_and_separate_covers():
    asm = products.tracked_display(ModelSpec(category='generic'))
    ids = {p.part.id for p in asm.parts}
    assert len([i for i in ids if i.startswith('wheel_')]) == 12
    assert {'track_left','track_right','fender_left','fender_right'} <= ids
    assert asm.metadata['exact_replica'] is False

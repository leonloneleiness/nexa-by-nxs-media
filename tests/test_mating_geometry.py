import pytest

from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry.fasteners import socket_screw, socket_dimensions
from nexa.three_d.generation.templates import machine
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.spec import normalize, validate_spec


@pytest.mark.parametrize("d,head,af", [(3, 5.5, 2.5), (4, 7, 3), (5, 8.5, 4), (6, 10, 5), (8, 13, 6)])
def test_socket_screw_nominal_envelope_and_socket(d, head, af):
    solid = socket_screw(d, 12)
    lo, hi = solid.bounds()
    assert hi - lo == pytest.approx([head, head, 12 + d], abs=1e-6)
    # Tool can enter along the socket; no decorative filled hexagon.
    probe = K.cylinder(af * 0.45, d * 0.45, segments=48).translate(0, 0, d * 0.5)
    assert solid.intersection_volume(probe) < 1e-7
    assert socket_dimensions(d)["socket_af"] == af


def test_custom_diameter_is_not_mislabelled_standard():
    assert socket_dimensions(3.04)["standard"] == "custom"
    with pytest.raises(ValueError):
        socket_screw(3, -1)


def test_washer_has_actual_clearance():
    washer = machine.flat_washer(3)
    # M3 ISO 7089 inner diameter 3.2 mm; shaft with 0.05 radial allowance fits.
    shaft = K.cylinder(1.55, 2, segments=64).translate(0, 0, -0.5)
    assert washer.intersection_volume(shaft) < 1e-7


@pytest.mark.parametrize("n,wheelbase", [(3, 250), (4, 250), (6, 450), (8, 900)])
def test_uav_clamp_holes_match_bolts_and_plates(n, wheelbase):
    asm = build_parametric(normalize(validate_spec({"category": "uav", "params": {"arm_count": n, "wheelbase_mm": wheelbase}})))
    clamps = asm.metadata["arm_clamps"]
    frame = asm.part("frame").solid
    for tag, xy in clamps["points_ros_mm"].items():
        arm = asm.part("arm_" + tag).solid
        hardware = asm.part("screws_" + tag).solid
        assert asm.part("screws_" + tag).part.dimensions["diameter"] == 3
        for x, y in xy:
            probe = K.cylinder(1.55, clamps["frame_grip_mm"] + 4, segments=48).translate(x, y, -3 * wheelbase / 250 - 1)
            assert frame.intersection_volume(probe) < 1e-5
            assert arm.intersection_volume(probe) < 1e-5
        assert frame.intersection_volume(hardware) < 1e-4
        assert arm.intersection_volume(hardware) < 1e-4
        # Nuts/heads must actually have supporting frame material around their holes.
        for x, y in xy:
            support = K.cylinder(3.4, 0.2, segments=48).translate(x, y, -3 * wheelbase / 250)
            assert frame.intersection_volume(support) > 2

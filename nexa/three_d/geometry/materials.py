"""Thư viện vật liệu PBR (metallic/roughness) và texture thủ tục (vân carbon, ren minh họa).

Màu khai báo theo sRGB (hex) rồi đổi sang tuyến tính vì glTF baseColorFactor là tuyến tính. Thông số lấy theo
giá trị PBR thường dùng (kim loại metallic=1, nhám 0,25–0,45; nhựa/cao su metallic=0).
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np

from nexa.three_d.models import Material

# Bảng màu tên tiếng Việt/Anh → sRGB hex (planner dùng để hiểu "thân carbon màu đen", "sơn đỏ trắng").
COLOR_NAMES: dict[str, str] = {
    "den": "#141518", "black": "#141518", "trang": "#e9ecef", "white": "#e9ecef", "xam": "#6b7078", "gray": "#6b7078",
    "grey": "#6b7078", "bac": "#c4c8cc", "silver": "#c4c8cc", "do": "#c1121f", "red": "#c1121f", "cam": "#f77f00",
    "orange": "#f77f00", "vang": "#f4c20d", "yellow": "#f4c20d", "xanh la": "#2b9348", "green": "#2b9348",
    "xanh duong": "#1d4ed8", "xanh": "#1d4ed8", "blue": "#1d4ed8", "xanh navy": "#14213d", "navy": "#14213d",
    "tim": "#7b2cbf", "purple": "#7b2cbf", "hong": "#e5609a", "pink": "#e5609a", "nau": "#7f4f24", "brown": "#7f4f24",
    "vang dong": "#c9a227", "gold": "#c9a227", "reu": "#606c38", "olive": "#606c38", "cat": "#c2b280", "sand": "#c2b280",
}


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_color(value: str, alpha: float = 1.0) -> list[float]:
    """'#rrggbb' → RGBA tuyến tính."""
    h = value.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"màu không hợp lệ: {value}")
    rgb = [srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)]
    return [round(x, 5) for x in rgb] + [float(alpha)]


def color_from_name(name: str | None, default: str) -> str:
    from nexa.utils.text import strip_accents
    if not name:
        return default
    n = strip_accents(name.lower()).strip()
    if n.startswith("#") and len(n) == 7:
        return n
    for key in sorted(COLOR_NAMES, key=len, reverse=True):
        if key in n:
            return COLOR_NAMES[key]
    return default


def material(mid: str, kind: str, color: str, metallic: float, roughness: float, *, alpha: float = 1.0,
             name: str = "", emissive: str | None = None, clearcoat: float = 0.0, textures: dict | None = None,
             normal_scale: float = 1.0) -> Material:
    return Material(id=mid, name=name or mid, kind=kind, base_color=hex_color(color, alpha), metallic=metallic,
                    roughness=roughness, emissive=hex_color(emissive)[:3] if emissive else [0.0, 0.0, 0.0],
                    clearcoat=clearcoat, textures=dict(textures or {}), normal_scale=normal_scale)


def library(primary: str = "#141518", secondary: str = "#2b2e33", accent: str = "#22d3ee") -> dict[str, Material]:
    """Bộ vật liệu chuẩn cho một mô hình (màu chính/phụ/nhấn do spec quyết định)."""
    mats = [
        material("carbon", "carbon", "#16171a", 0.0, 0.3, clearcoat=1.0, name="Sợi carbon",
                 textures={"base_color": "textures/carbon_basecolor.png", "normal": "textures/carbon_normal.png"},
                 normal_scale=0.6),
        material("paint_primary", "paint", primary, 0.0, 0.32, clearcoat=0.6, name="Sơn màu chính"),
        material("paint_secondary", "paint", secondary, 0.0, 0.38, clearcoat=0.4, name="Sơn màu phụ"),
        material("paint_accent", "paint", accent, 0.0, 0.3, clearcoat=0.5, name="Sơn điểm nhấn"),
        material("plastic_black", "plastic", "#1b1c1f", 0.0, 0.55, name="Nhựa đen nhám"),
        material("plastic_gray", "plastic", "#5c6068", 0.0, 0.5, name="Nhựa xám"),
        material("plastic_white", "plastic", "#e3e6ea", 0.0, 0.45, name="Nhựa trắng"),
        material("prop_plastic", "plastic", "#202226", 0.0, 0.35, name="Nhựa cánh quạt (PC gia cường)"),
        material("aluminum", "metal", "#c9ccd1", 1.0, 0.32, name="Nhôm"),
        material("aluminum_anodized", "metal", accent, 1.0, 0.35, name="Nhôm anod hóa"),
        material("aluminum_dark", "metal", "#3a3d42", 1.0, 0.38, name="Nhôm anod đen"),
        material("steel", "metal", "#b6b9be", 1.0, 0.3, name="Thép"),
        material("steel_zinc", "metal", "#c9ced4", 1.0, 0.26, name="Thép mạ kẽm"),
        material("steel_black_oxide", "metal", "#2b2c30", 0.9, 0.42, name="Thép nhuộm đen"),
        material("stainless", "metal", "#d2d5d8", 1.0, 0.22, name="Inox"),
        material("brass", "metal", "#d6b25a", 1.0, 0.3, name="Đồng thau"),
        material("titanium", "metal", "#8f9297", 1.0, 0.34, name="Titan"),
        material("copper", "metal", "#c46f3b", 1.0, 0.33, name="Đồng (cuộn dây)"),
        material("rubber", "rubber", "#1a1a1a", 0.0, 0.88, name="Cao su"),
        material("rubber_gray", "rubber", "#3b3d40", 0.0, 0.85, name="Cao su xám"),
        material("glass", "glass", "#9fb8c8", 0.0, 0.04, alpha=0.32, name="Kính"),
        material("glass_tinted", "glass", "#1c2a33", 0.0, 0.03, alpha=0.55, name="Kính màu khói"),
        material("lens", "glass", "#05070a", 0.0, 0.02, alpha=0.92, name="Thấu kính quang học"),
        material("sensor_black", "plastic", "#0b0c0e", 0.0, 0.18, name="Nhựa đen bóng (cảm biến)"),
        material("led_green", "emissive", "#0f3d1f", 0.0, 0.3, emissive="#22c55e", name="Đèn LED xanh"),
        material("led_red", "emissive", "#3d0f0f", 0.0, 0.3, emissive="#ef4444", name="Đèn LED đỏ"),
        material("led_white", "emissive", "#3a3a3a", 0.0, 0.3, emissive="#f8fafc", name="Đèn trắng"),
        material("pcb", "plastic", "#0f3b2a", 0.0, 0.45, name="Mạch in"),
        material("battery_wrap", "plastic", "#23262b", 0.0, 0.4, name="Vỏ pin"),
        material("label_yellow", "paint", "#f4c20d", 0.0, 0.4, name="Nhãn cảnh báo"),
        material("paint_red", "paint", "#c1121f", 0.0, 0.35, clearcoat=0.5, name="Sơn đỏ (nút dừng khẩn cấp)"),
        material("paint_yellow", "paint", "#ffc300", 0.0, 0.4, name="Sơn vàng an toàn"),
        material("steel_dark", "metal", "#4a4d52", 0.9, 0.45, name="Thép sơn tĩnh điện"),
    ]
    return apply_micro_textures({m.id: m for m in mats})


def object_library(primary: str = "#c4c8cc", secondary: str = "#2b2e33", accent: str = "#22d3ee") -> dict[str, Material]:
    """Bộ vật liệu cho vật thể tự do (CAD DSL): bộ chuẩn + vật liệu đồ dùng thường gặp (gỗ, gốm sứ, vải, da…)."""
    mats = library(primary, secondary, accent)
    for m in (
        material("wood", "wood", "#9a6a3c", 0.0, 0.62, name="Gỗ sáng"),
        material("wood_dark", "wood", "#5b3a22", 0.0, 0.58, name="Gỗ tối"),
        material("ceramic", "ceramic", "#f2f0ea", 0.0, 0.18, clearcoat=0.8, name="Gốm sứ tráng men"),
        material("fabric", "fabric", "#6b7280", 0.0, 0.92, name="Vải"),
        material("leather", "leather", "#5a3824", 0.0, 0.55, name="Da"),
        material("gold", "metal", "#d4af37", 1.0, 0.25, name="Vàng"),
        material("chrome", "metal", "#e8eaed", 1.0, 0.08, name="Crôm"),
        material("stone", "stone", "#8d8a84", 0.0, 0.8, name="Đá"),
        material("paper", "paper", "#f5f1e6", 0.0, 0.9, name="Giấy"),
        material("foam", "rubber", "#2e3136", 0.0, 0.95, name="Mút/xốp"),
    ):
        mats[m.id] = m
    return mats


def tinted(base: Material, color: str, new_id: str) -> Material:
    """Bản sao vật liệu với màu riêng (bộ phận DSL có 'color': '#rrggbb')."""
    import copy as _copy
    m = _copy.deepcopy(base)
    m.id = new_id
    m.base_color = hex_color(color, base.base_color[3] if len(base.base_color) > 3 else 1.0)
    m.name = f"{base.name} ({color})"
    return m


# ------------------------------------------------------------------ texture thủ tục
def _png_bytes(arr: np.ndarray) -> bytes:
    from PIL import Image
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _height_to_normal(h: np.ndarray, strength: float) -> np.ndarray:
    """Bản đồ độ cao (tuần hoàn) → normal map tiếp tuyến (OpenGL, +Y lên), 8 bit."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5 * strength
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5 * strength
    n = np.dstack([-dx, dy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return (n * 0.5 + 0.5) * 255


def carbon_weave(size: int = 512, tows: int = 8) -> tuple[bytes, bytes]:
    """Vân dệt carbon 2x2 twill, lặp liền mạch. Trả (base_color PNG, normal PNG)."""
    y, x = np.mgrid[0:size, 0:size] / size * tows
    cell_x, cell_y = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - cell_x, y - cell_y
    over = ((cell_x + cell_y) // 2) % 2 == 0                        # twill 2x2
    # sợi ngang: gợn theo fy; sợi dọc: gợn theo fx
    h_weft = np.sin(np.pi * fy) ** 0.6
    h_warp = np.sin(np.pi * fx) ** 0.6
    height = np.where(over, h_warp, h_weft)
    fiber = np.where(over, np.sin(fy * np.pi * 18), np.sin(fx * np.pi * 18)) * 0.08
    height = height + fiber
    shade = 0.55 + 0.45 * np.where(over, np.sin(np.pi * fx), np.sin(np.pi * fy))
    base = np.dstack([shade * 34 + 8, shade * 36 + 9, shade * 40 + 11])
    return _png_bytes(base), _png_bytes(_height_to_normal(height, 3.0))


def thread_normal_map(size: int = 256) -> bytes:
    """Normal map ren minh họa: u = θ/2π, v = z/P. Pha ren = (v − u) mod 1 (ren phải), lặp liền mạch."""
    v, u = np.mgrid[0:size, 0:size] / size
    phase = (v - u) % 1.0
    tri = 1 - np.abs(phase * 2 - 1)                                    # tam giác 0..1..0
    height = np.clip((tri - 0.1) / 0.8, 0, 1)
    return _png_bytes(_height_to_normal(height, 6.0))


def _tile_noise(size: int, cells: int, seed: int) -> np.ndarray:
    """Nhiễu giá trị mượt, lặp liền mạch (nội suy cosine trên lưới ô tuần hoàn)."""
    rng = np.random.default_rng(seed)
    g = rng.random((cells, cells))
    t = np.arange(size) / size * cells
    i0 = np.floor(t).astype(int) % cells
    i1 = (i0 + 1) % cells
    f = (1 - np.cos((t - np.floor(t)) * np.pi)) / 2
    rows = g[i0][:, :] * (1 - f)[:, None] + g[i1] * f[:, None]           # nội suy theo trục dọc
    return rows[:, i0] * (1 - f)[None, :] + rows[:, i1] * f[None, :]


def brushed_normal_map(size: int = 256) -> bytes:
    """Kim loại chải xước: vệt mảnh dọc một hướng (u) với độ dài/biên độ ngẫu nhiên, lặp liền mạch."""
    rng = np.random.default_rng(11)
    streak = rng.normal(0, 1, size)
    h = np.tile(streak[:, None], (1, size)) * 0.35                       # mỗi hàng một vệt chạy dọc trục u
    h += (_tile_noise(size, 64, 12) - 0.5) * 0.6 + (_tile_noise(size, 8, 13) - 0.5) * 0.3
    return _png_bytes(_height_to_normal(h, 1.2))


def paint_normal_map(size: int = 256) -> bytes:
    """Sơn phủ công nghiệp: vân vỏ cam rất nhẹ."""
    h = (_tile_noise(size, 24, 21) - 0.5) + (_tile_noise(size, 48, 22) - 0.5) * 0.5
    return _png_bytes(_height_to_normal(h, 0.9))


def rubber_normal_map(size: int = 256) -> bytes:
    """Cao su đúc: hạt nhám mịn."""
    rng = np.random.default_rng(31)
    h = (_tile_noise(size, 96, 32) - 0.5) + rng.normal(0, 0.25, (size, size))
    return _png_bytes(_height_to_normal(h, 1.6))


def plastic_normal_map(size: int = 256) -> bytes:
    """Nhựa ép khuôn vân nhám (texture VDI) mịn."""
    h = (_tile_noise(size, 64, 41) - 0.5) + (_tile_noise(size, 128, 42) - 0.5) * 0.6
    return _png_bytes(_height_to_normal(h, 1.1))


def tread_plate_normal_map(size: int = 256) -> bytes:
    """Tấm thép gân chống trượt (sàn, bậc lên xuống): gân kim cương so le."""
    y, x = np.mgrid[0:size, 0:size] / size * 6
    fx, fy = x - np.floor(x), y - np.floor(y)
    a = np.exp(-(((fx - 0.25) * 4) ** 2 + ((fy - 0.25) * 12) ** 2))      # gân nghiêng hai chiều so le
    b2 = np.exp(-(((fx - 0.75) * 12) ** 2 + ((fy - 0.75) * 4) ** 2))
    return _png_bytes(_height_to_normal(a + b2, 5.0))


# texture thủ tục vi mô: tên tệp → (hàm tạo, kích thước một lần lặp trên bề mặt thật, mm)
MICRO_TEXTURES: dict[str, tuple] = {
    "brushed_normal": (brushed_normal_map, 60.0),
    "paint_normal": (paint_normal_map, 140.0),
    "rubber_normal": (rubber_normal_map, 28.0),
    "plastic_normal": (plastic_normal_map, 40.0),
    "treadplate_normal": (tread_plate_normal_map, 120.0),
}
# vật liệu chuẩn → (texture vi mô, độ mạnh normal)
MICRO_BY_MATERIAL = {
    "aluminum": ("brushed_normal", 0.35), "aluminum_dark": ("brushed_normal", 0.3), "aluminum_anodized": ("brushed_normal", 0.3),
    "steel": ("brushed_normal", 0.35), "stainless": ("brushed_normal", 0.4), "titanium": ("brushed_normal", 0.35),
    "paint_primary": ("paint_normal", 0.25), "paint_secondary": ("paint_normal", 0.25), "paint_accent": ("paint_normal", 0.25),
    "paint_red": ("paint_normal", 0.25), "paint_yellow": ("paint_normal", 0.25), "steel_dark": ("brushed_normal", 0.3),
    "rubber": ("rubber_normal", 0.4), "rubber_gray": ("rubber_normal", 0.4),
    "plastic_black": ("plastic_normal", 0.45), "plastic_gray": ("plastic_normal", 0.45),
    "plastic_white": ("plastic_normal", 0.4), "battery_wrap": ("plastic_normal", 0.3),
}


def texture_tile_mm(material: Material) -> float:
    """Kích thước một lần lặp texture (mm) — dùng tạo UV chiếu hộp đúng tỷ lệ thật."""
    for rel in material.textures.values():
        stem = Path(rel).stem
        if stem in MICRO_TEXTURES:
            return float(MICRO_TEXTURES[stem][1])
        if "carbon" in stem:
            return 22.0
    return 50.0


def apply_micro_textures(mats: dict[str, Material]) -> dict[str, Material]:
    """Gắn normal map vi mô (kim loại chải, sơn, cao su, nhựa nhám) cho vật liệu chuẩn chưa có texture."""
    for mid, (tex, strength) in MICRO_BY_MATERIAL.items():
        m = mats.get(mid)
        if m is not None and "normal" not in m.textures:
            m.textures["normal"] = f"textures/{tex}.png"
            m.normal_scale = strength
    return mats


def write_textures(project_dir: Path, needed: set[str]) -> dict[str, str]:
    """Ghi các texture cần dùng vào <dự án>/textures. Trả map tên → đường dẫn tương đối.

    needed: "carbon", "thread" hoặc tên texture vi mô trong MICRO_TEXTURES (vd "brushed_normal")."""
    out: dict[str, str] = {}
    tex_dir = project_dir / "textures"
    tex_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(n for n in needed if n in MICRO_TEXTURES):
        f = tex_dir / f"{name}.png"
        if not f.exists():
            f.write_bytes(MICRO_TEXTURES[name][0]())
        out[name] = f"textures/{name}.png"
    if "carbon" in needed:
        base, normal = carbon_weave()
        (tex_dir / "carbon_basecolor.png").write_bytes(base)
        (tex_dir / "carbon_normal.png").write_bytes(normal)
        out["carbon_basecolor"] = "textures/carbon_basecolor.png"
        out["carbon_normal"] = "textures/carbon_normal.png"
    if "thread" in needed:
        (tex_dir / "thread_normal.png").write_bytes(thread_normal_map())
        out["thread_normal"] = "textures/thread_normal.png"
    return out


def expected_kinds(category: str) -> set[str]:
    """Loại vật liệu hợp lý theo loại bộ phận (kiểm tra vật liệu deterministic trong quality.py)."""
    table = {
        "propeller": {"plastic", "carbon", "metal"}, "rotor_blade": {"carbon", "paint", "metal", "plastic"},
        "tire": {"rubber"}, "wheel": {"rubber", "metal", "plastic"}, "fastener": {"metal"}, "screw": {"metal"},
        "bolt": {"metal"}, "nut": {"metal"}, "washer": {"metal"}, "gear": {"metal", "plastic"},
        "lens": {"glass"}, "canopy": {"glass"}, "motor": {"metal", "plastic", "paint"}, "shell": {"paint", "plastic", "carbon"},
        "frame": {"carbon", "metal", "plastic", "paint"}, "arm": {"carbon", "metal", "plastic", "paint"},
        "battery": {"plastic", "paint"}, "camera": {"plastic", "metal", "glass"}, "sensor": {"plastic", "glass", "metal"},
        "lidar": {"plastic", "glass", "metal"}, "joint": {"metal", "plastic", "paint"}, "foot": {"rubber", "plastic"},
        # mẫu kỹ thuật mở rộng
        "bearing_ring": {"metal"}, "ball": {"metal", "ceramic"}, "cage": {"metal", "plastic"}, "seal": {"rubber", "plastic", "metal"},
        "shaft": {"metal"}, "housing": {"metal", "paint", "plastic"}, "stator": {"metal"}, "connector": {"plastic", "rubber"},
        "cable": {"plastic", "rubber"}, "cover": {"metal", "paint", "plastic"}, "sight_glass": {"metal", "glass"},
        "plug": {"metal"}, "cylinder_barrel": {"metal"}, "piston": {"metal"}, "rod": {"metal"}, "tie_rod": {"metal"},
        "fitting": {"metal", "plastic"}, "valve_body": {"metal", "paint"}, "valve_ball": {"metal"},
        "handle": {"metal", "paint", "plastic", "rubber"}, "pipe": {"metal", "plastic"}, "flange": {"metal", "paint"},
        "belt": {"rubber"}, "pulley": {"metal", "plastic"}, "chain": {"metal"}, "sprocket": {"metal"},
        "coupling_hub": {"metal"}, "spider": {"rubber", "plastic"}, "carriage": {"metal"}, "rail": {"metal"},
        "spring": {"metal"}, "hook": {"metal"}, "leg": {"metal"}, "bearing": {"metal", "paint"},
        "base": {"metal", "paint", "plastic"}, "link": {"metal", "paint", "carbon"}, "tool_flange": {"metal"},
        "end_effector": {"metal", "plastic", "rubber"}, "chassis": {"plastic", "metal", "paint"}, "bumper": {"rubber", "plastic"},
        "brush": {"plastic", "rubber"}, "dustbin": {"plastic", "glass"}, "dock": {"plastic"}, "caster": {"rubber", "plastic", "metal"},
        "estop": {"paint", "plastic"}, "light": {"plastic", "emissive", "glass"}, "lift": {"metal"}, "cargo": {"paint", "plastic"},
        "button": {"plastic"},
        # phương tiện
        "battery_pack": {"metal", "paint"}, "car_body": {"paint", "metal", "carbon"}, "door": {"paint", "metal", "glass"},
        "hood": {"paint", "metal", "carbon"}, "trunk": {"paint", "metal", "glass"}, "interior": {"plastic", "rubber"},
        "subframe": {"metal", "paint"}, "suspension": {"metal", "paint"}, "fuselage": {"paint", "metal", "carbon"},
        "wing": {"paint", "metal", "carbon"}, "control_surface": {"paint", "metal", "carbon"}, "tail": {"paint", "metal", "carbon"},
        "landing_gear": {"metal", "rubber", "paint"}, "boom": {"carbon", "metal", "paint"}, "engine": {"paint", "metal"},
    }
    if category == "battery":                                  # pin xe điện: vỏ nhôm
        return {"plastic", "paint", "metal"}
    return table.get(category, set())


def luminance(rgba: list[float]) -> float:
    return 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]

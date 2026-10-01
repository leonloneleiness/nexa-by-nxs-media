"""Bo mạch phát triển: Arduino Uno R3 (68,58 × 53,34 × 1,6 mm) hoặc Raspberry Pi 4 B (85 × 56 × 1,4 mm).

Gốc tọa độ tại góc trái-dưới bo (x dọc cạnh dài, y dọc cạnh ngắn), mặt trên bo z = t. Lỗ bắt theo bản vẽ hãng
(standards.BOARDS), header bước 2,54 mm.
- Uno: ATmega328P DIP-28 trên đế, ATmega16U2, thạch anh 16 MHz, ổn áp, 2 tụ hóa, 4 LED, nút reset, header cái 10+8 (số) /
  8+6 (nguồn + analog), ICSP 2×3, cổng USB-B và giắc DC nhô khỏi mép trái.
- Pi 4: SoC có nắp tản nhiệt, RAM, chip USB, GPIO 2 × 20 chân đực mạ vàng dọc mép trên, 2 cổng USB 2.0 + 2 USB 3.0 xếp
  chồng + RJ45 ở mép phải, USB-C nguồn + 2 micro-HDMI + giắc âm thanh ở mép dưới, đầu FFC camera/màn hình, header PoE,
  khe thẻ microSD mặt dưới.
"""
from __future__ import annotations

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def female_header(x0: float, y: float, n: int, z0: float, pitch: float = 2.54) -> tuple[K.Solid, K.Solid, list]:
    """Header cái 1 hàng: thân nhựa 2,54 × n, cao 8,5, lỗ vuông 1 mm; chân hàn xuống dưới bo. Trả (thân, chân, tâm chân)."""
    L = n * pitch
    body = box_at(x0 - pitch / 2, x0 - pitch / 2 + L, y - 1.27, y + 1.27, z0, z0 + 8.5)
    centers = [(x0 + i * pitch, y) for i in range(n)]
    body = body - K.Solid.union_all([box_at(cx - 0.5, cx + 0.5, cy - 0.5, cy + 0.5, z0 + 2.0, z0 + 9.0) for cx, cy in centers])
    pins = K.Solid.union_all([box_at(cx - 0.3, cx + 0.3, cy - 0.3, cy + 0.3, z0 - 3.0 - 1.6, z0 + 1.0) for cx, cy in centers])
    return body, pins, centers


def male_header(x0: float, y0: float, nx: int, ny: int, z0: float, pitch: float = 2.54) -> tuple[K.Solid, K.Solid, list]:
    """Header đực nx × ny: đế nhựa 2,5 mm + chân vuông 0,64 cao 8,5 mm trên đế."""
    body = box_at(x0 - pitch / 2, x0 - pitch / 2 + nx * pitch, y0 - pitch / 2, y0 - pitch / 2 + ny * pitch, z0, z0 + 2.5)
    centers = [(x0 + i * pitch, y0 + j * pitch) for i in range(nx) for j in range(ny)]
    pins = K.Solid.union_all([box_at(cx - 0.32, cx + 0.32, cy - 0.32, cy + 0.32, z0 - 3.0, z0 + 2.5 + 6.0) for cx, cy in centers])
    return body, pins, centers


def dip(x: float, y: float, n: int, z0: float, width: float = 7.62) -> tuple[K.Solid, K.Solid]:
    """IC DIP-n dọc X (thân nhựa đen + chân thép)."""
    half = n // 2
    L = half * 2.54
    body = K.rounded_box(L, width - 1.0, 3.3, 0.4, segments=8).translate(x, y, z0 + 0.8 + 1.65)
    notch = K.cylinder(0.8, 1.0, segments=16).rotate(90, 0, 0).translate(x - L / 2, y + 0.5, z0 + 0.8 + 3.3 - 0.2)
    legs = []
    for i in range(half):
        cx = x - L / 2 + 1.27 + i * 2.54
        for sy in (1, -1):
            legs.append(box_at(cx - 0.25, cx + 0.25, y + sy * (width / 2 - 0.3), y + sy * (width / 2 + 0.3), z0 - 3.0, z0 + 2.5))
            legs.append(box_at(cx - 0.25, cx + 0.25, y + sy * (width / 2 - 1.0), y + sy * (width / 2 + 0.3), z0 + 1.8, z0 + 2.3))
    return body - notch, K.Solid.union_all(legs)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("board", "arduino_uno")
    B = S.BOARDS[kind]
    W, Hb, t = B["w"], B["h"], B["t"]
    mats = MC.tech_materials(spec, primary="#0b6e99" if kind == "arduino_uno" else "#1f7a3a", secondary="#1b1d21", accent="#e6c35a")
    mats["pcb_uno"] = M.material("pcb_uno", "plastic", "#0b6e99" if kind == "arduino_uno" else "#1f7a3a", 0.0, 0.45, name="PCB FR-4 phủ mặt nạ hàn")
    mats["gold"] = M.material("gold", "metal", "#d4af37", 1.0, 0.25, name="Mạ vàng")
    mats["silkscreen"] = M.material("silkscreen", "plastic", "#f4f4f4", 0.0, 0.6, name="In lụa trắng")
    mats["solder"] = M.material("solder", "metal", "#c9ccd0", 0.9, 0.3, name="Thiếc hàn")
    names = {"arduino_uno": "Arduino Uno R3", "raspberry_pi": "Raspberry Pi 4 Model B"}
    b = AssemblyBuilder(spec.name or names[kind], "dev_board", mats)
    z = t
    pcb = K.extrude(MC.P.rounded_rect(W, Hb, 1.0 if kind == "arduino_uno" else 3.0, 6), t).translate(W / 2, Hb / 2, 0)
    holes = K.Solid.union_all([K.cylinder(B["hole_d"] / 2, 3 * t, segments=24).translate(hx, hy, -t) for hx, hy in B["holes"]])
    rings = K.Solid.union_all([(K.cylinder(B["hole_d"] / 2 + 1.2, 0.05, segments=24) - K.cylinder(B["hole_d"] / 2, 1.0, segments=24).translate(0, 0, -0.5))
                               .translate(hx, hy, t) for hx, hy in B["holes"]])
    pcb = pcb - holes
    pins_all, headers, chips, conns, passives = [], [], [], [], []
    header_centers = {}
    if kind == "arduino_uno":
        # header cái: số 10 + 8 (mép trên), nguồn 8 + analog 6 (mép dưới) — tọa độ chân theo bản vẽ Uno R3
        for name_, x0, y, n in (("digital_hi", 17.78 + 1.27, 50.8, 10), ("digital_lo", 45.72 + 1.27, 50.8, 8), ("power", 27.94 + 1.27, 2.54, 8),
                                ("analog", 50.8 + 1.27, 2.54, 6)):
            body, pins, cen = female_header(x0, y, n, z)
            headers.append(body)
            pins_all.append(pins)
            header_centers[name_] = cen
        icsp_b, icsp_p, cen = male_header(64.1 - 1.27, 25.4 - 2.54, 2, 3, z)
        headers.append(icsp_b)
        pins_all.append(icsp_p)
        header_centers["icsp"] = cen
        sock = box_at(46.0 - 17.8 - 0.5, 46.0 + 17.8 + 0.5, 20.3 - 4.8, 20.3 + 4.8, z, z + 1.0)
        mcu, legs = dip(46.0, 20.3, 28, z + 1.0)
        chips += [mcu]
        dip_legs = legs
        headers.append(sock)
        chips.append(box_at(19.0, 24.0, 30.0, 35.0, z, z + 0.9))                        # ATmega16U2 QFN-32
        chips.append(box_at(17.0, 21.5, 11.5, 15.0, z, z + 1.8))                        # ổn áp SOT-223
        xtal = K.rounded_box(11.0, 4.6, 3.5, 1.5, segments=12).translate(36.0, 30.5, z + 1.75)
        passives.append(xtal)
        passives += [K.cylinder(3.15, 7.7, segments=24).translate(cx, cy, z) for cx, cy in ((12.5, 21.5), (19.5, 21.5))]
        leds = K.Solid.union_all([box_at(x - 0.8, x + 0.8, y - 0.4, y + 0.4, z, z + 0.6) for x, y in ((29.0, 42.5), (29.0, 39.0), (29.0, 36.5), (58.5, 39.5))])
        button = box_at(3.5, 9.5, 46.0, 52.0, z, z + 3.5) + K.cylinder(1.7, 1.5, segments=20).translate(6.5, 49.0, z + 3.5)   # trên cổng USB
        usb = box_at(-6.35, 9.65, 38.1 - 6.0, 38.1 + 6.0, z, z + 10.9) - box_at(-7.0, -1.0, 38.1 - 4.0, 38.1 + 4.0, z + 1.5, z + 9.4)
        jack = box_at(-1.9, 11.8, 3.3, 12.2, z, z + 11.0) - K.cylinder(3.2, 10.0, segments=24).rotate(0, 90, 0).translate(-3.0, 7.75, z + 6.5)
        conns += [usb, jack]
        conn_names = ("Cổng USB-B + giắc nguồn DC", "USB-B & DC jack", ["cổng usb", "usb", "giắc nguồn", "jack dc", "cổng nạp"])
        extra = {"pins_total": 32 + 6, "header_rows": {k: len(v) for k, v in header_centers.items()}}
    else:
        gp_b, gp_p, cen = male_header(7.1 + 0.0, 50.06, 20, 2, z)
        headers.append(gp_b)
        pins_all.append(gp_p)
        header_centers["gpio"] = cen
        poe_b, poe_p, cen2 = male_header(59.2, 48.5, 2, 2, z)               # PoE giữa GPIO và RJ45
        headers.append(poe_b)
        pins_all.append(poe_p)
        header_centers["poe"] = cen2
        soc = box_at(29.0 - 7.5, 29.0 + 7.5, 32.0 - 7.5, 32.0 + 7.5, z, z + 1.6)
        lid = box_at(29.0 - 7.0, 29.0 + 7.0, 32.0 - 7.0, 32.0 + 7.0, z + 1.6, z + 2.4)
        ram = box_at(42.0, 57.0, 26.5, 37.5, z, z + 1.0)
        usbc = box_at(49.5, 55.5, 17.0, 21.0, z, z + 1.0)                              # chip USB VL805
        wifi = box_at(5.0, 15.0, 32.0, 42.0, z, z + 1.2)
        chips += [soc, ram, usbc, wifi]
        passives.append(lid)
        # mép phải: RJ45 (mép trên) + 2 cặp USB xếp chồng
        eth = box_at(65.0, 87.3, 45.75 - 8.0, 45.75 + 8.0, z, z + 13.5) - box_at(84.0, 88.0, 45.75 - 5.0, 45.75 + 5.0, z + 3.0, z + 11.0)
        usbs = []
        for yc, col in ((27.0, "usb3"), (9.0, "usb2")):
            u = box_at(69.6, 87.1, yc - 7.35, yc + 7.35, z, z + 16.0)
            for zz in (z + 3.0, z + 10.5):
                u = u - box_at(84.0, 88.0, yc - 6.0, yc + 6.0, zz, zz + 5.0)
            usbs.append((u, col))
        blue =K.Solid.union_all([box_at(84.5, 87.0, 27.0 - 5.5, 27.0 + 5.5, zz + 1.8, zz + 3.2) for zz in (z + 3.0, z + 10.5)])
        # mép dưới: USB-C, 2 micro-HDMI, giắc âm thanh
        usbc_p = box_at(3.5 + 7.7 - 4.5, 3.5 + 7.7 + 4.5, -1.0, 6.5, z, z + 3.2)
        hdmi = K.Solid.union_all([box_at(x - 3.25, x + 3.25, -1.0, 6.5, z, z + 3.0) for x in (3.5 + 22.5, 3.5 + 35.9)])
        audio = box_at(3.5 + 50.5 - 3.5, 3.5 + 50.5 + 3.5, 0.0, 12.0, z, z + 6.0) + K.cylinder(3.0, 2.5, segments=24).rotate(90, 0, 0).translate(3.5 + 50.5, 0.0, z + 3.0)
        ffc = K.Solid.union_all([box_at(43.0, 45.5, 1.5, 23.0, z, z + 5.0), box_at(1.5, 4.0, 17.0, 39.0, z, z + 5.0)])
        sd = box_at(-2.0, 12.0, 22.0, 34.0, -1.4, 0.0)
        conns += [eth, usbs[0][0], usbs[1][0], usbc_p, hdmi, audio, ffc, sd]
        conn_names = ("Cổng mạng + USB + HDMI + nguồn + âm thanh", "Ports", ["cổng mạng", "rj45", "ethernet", "usb", "hdmi", "micro hdmi", "usb-c",
                                                                             "giắc âm thanh", "khe thẻ nhớ", "microsd"])
        extra = {"pins_total": 44, "header_rows": {k: len(v) for k, v in header_centers.items()}}
        conns_blue = blue
    b.add("pcb", f"PCB {W:g} × {Hb:g} × {t:g} mm", "Printed circuit board", "pcb", [Shape(pcb, "pcb_uno", 35.0), Shape(rings, "gold", 35.0)], required=True,
          aliases=["bo mạch", "mạch in", "pcb", "lỗ bắt vít", "board"], function=f"PCB FR-4 {t:g} mm, {len(B['holes'])} lỗ bắt Ø{B['hole_d']:g} theo bản vẽ hãng.",
          position_tag="center", dimensions={"width": W, "height": Hb, "thickness": t})
    b.add("chips", "Vi xử lý + chip + linh kiện thụ động", "ICs & passives", "chip",
          [Shape(K.Solid.union_all(chips), "plastic_black", 35.0)] + ([Shape(K.Solid.union_all(passives), "aluminum", 35.0)] if passives else [])
          + ([Shape(dip_legs, "steel", 35.0)] if kind == "arduino_uno" else []),
          parent_id="pcb", required=True, aliases=["chip", "vi xử lý", "vi điều khiển", "atmega", "soc", "ram", "thạch anh", "tụ", "ic"],
          function="Vi điều khiển ATmega328P + 16U2, thạch anh 16 MHz, ổn áp, tụ." if kind == "arduino_uno" else "SoC BCM2711 4 nhân + RAM LPDDR4, chip USB 3.0, WiFi/BT.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=15.0, explode_order=1)
    hdr_shapes = [Shape(K.Solid.union_all(headers), "plastic_black", 35.0), Shape(K.Solid.union_all(pins_all), "gold", 35.0)]
    b.add("headers", "Header chân cắm 2,54 mm", "Pin headers", "connector", hdr_shapes, parent_id="pcb", required=True,
          aliases=["header", "chân cắm", "chân gpio", "gpio", "hàng rào chân", "icsp"], function="Header bước 2,54 mm (chân mạ vàng xuyên lỗ).",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=25.0, explode_order=1)
    con_sh = [Shape(K.Solid.union_all(conns), "steel", 35.0)]
    if kind == "raspberry_pi":
        con_sh.append(Shape(conns_blue, "paint_blue", 35.0))
    b.add("connectors", conn_names[0], conn_names[1], "port", con_sh, parent_id="pcb", required=True, aliases=conn_names[2],
          function="Cổng ngoại vi ở mép bo theo bố trí hãng.", position_tag="side", explode_dir=(-1, 0, 0) if kind == "arduino_uno" else (1, 0, 0),
          explode_distance=20.0, explode_order=1)
    if kind == "arduino_uno":
        b.add("indicators", "LED + nút reset", "LEDs & reset button", "button", [Shape(button, "plastic_black", 35.0), Shape(leds, "led_green", 35.0)],
              parent_id="pcb", required=True, aliases=["led", "đèn báo", "nút reset", "reset"], function="LED ON/L/TX/RX, nút reset.", position_tag="top",
              explode_dir=(0, 0, 1), explode_distance=10.0, explode_order=1)
    b.note_stage(1, "Tháo linh kiện khỏi PCB")
    b.place_on_ground(center_xy=False)
    b.metadata.update({"board": kind, "width_mm": W, "height_mm": Hb, "pcb_t_mm": t, "holes": B["holes"], "pitch_mm": 2.54,
                       "header_centers": {k: [list(c) for c in v] for k, v in header_centers.items()}, **extra,
                       "standard": "Bản vẽ cơ khí Arduino Uno R3 / Raspberry Pi 4 B; header bước 2,54 mm (0,1\")",
                       "strict_overlap": True, "contacts": [["headers", "chips"]]})
    return b.build()



def mesh_components(mesh: Any) -> list[np.ndarray]:
    """Các thành phần liên thông của một lưới (theo đỉnh trùng vị trí) → danh sách mảng đỉnh."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    v = np.asarray(mesh.vertices)
    f = np.asarray(mesh.faces)
    if len(f) == 0:
        return []
    _, inv = np.unique(np.round(v, 5), axis=0, return_inverse=True)
    inv = inv.ravel()
    ff = inv[f]
    n = int(inv.max()) + 1
    rows = np.concatenate([ff[:, 0], ff[:, 1], ff[:, 2]])
    cols = np.concatenate([ff[:, 1], ff[:, 2], ff[:, 0]])
    g = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    k, lab = connected_components(g, directed=False)
    used = np.zeros(n, bool)
    used[ff.ravel()] = True
    vv = np.zeros((n, 3))
    vv[inv] = v
    return [vv[(lab == i) & used] for i in range(k) if np.any((lab == i) & used)]


def eng(v: np.ndarray) -> np.ndarray:
    return np.column_stack([v[:, 2], v[:, 0], v[:, 1]])


@register("belt_drive")
def _belt(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    belt = p.get("belt", "GT2")
    ids = by_id(parts)
    pa, pb = ids.get("pulley_driver"), ids.get("pulley_driven")
    if not (pa and pb and ids.get("belt")):
        return [Check("dimensions", "puly + đai", False, "thiếu", 2.0, True)]
    out: list[Check] = []
    centers = []
    for pd_ in (pa, pb):
        lo, hi = solid_bounds(pd_)
        cc = (lo + hi) / 2
        centers.append(cc)
    C = float(math.hypot(centers[1][0] - centers[0][0], centers[1][2] - centers[0][2]))
    want_c = float(p.get("center_distance_mm") or meta.get("center_distance_mm", C))
    if belt in S.BELTS:
        bt = S.BELTS[belt]
        out.append(Check("dimensions", "khoảng cách tâm (hiệu chỉnh ≤ ½ bước theo đai số răng nguyên)",
                         abs(C - want_c) <= bt["pitch"] / 2 + 1e-6, f"đo {C:.2f} mm / yêu cầu {want_c:g} mm", 2.0,
                         "center_distance_mm" in (spec.explicit or {})))
        teeth = []
        for pd_, zt, cc in ((pa, int(p.get("teeth_driver", 20)), centers[0]), (pb, int(p.get("teeth_driven", 40)), centers[1])):
            ro = zt * bt["pitch"] / (2 * math.pi) - bt["pld"]
            v = eng_vertices(pd_)
            r = radial(v, cc, "y")
            yc = float(np.median(v[np.abs(r - ro) < 0.02][:, 1])) if np.any(np.abs(r - ro) < 0.02) else float(cc[1])
            c2 = np.array([cc[0], yc, cc[2]])
            zone = v[np.abs(v[:, 1] - yc) < 1.0]
            out.append(dim(f"đường kính đỉnh puly {zt} răng (PD − 2·PLD)", float(2 * radial(zone, c2, "y").max()), 2 * ro, 0.004, 0.03))
            n = ring_count(pd_.solid, c2, "y", ro - 0.45 * bt["tooth_h"], -0.8, 0.8, thickness=0.02)
            out.append(count_check(f"số răng puly (đếm, yêu cầu {zt})", n, zt))
            teeth.append(n)
        if all(teeth):
            want_r = int(p.get("teeth_driven", 40)) / int(p.get("teeth_driver", 20))
            out.append(dim("tỷ số truyền z2/z1 (đếm)", teeth[1] / teeth[0], want_r, 0.001, 0.001, unit=""))
    else:
        out.append(dim("khoảng cách tâm", C, want_c, 0.002, 0.1))
        v_ = S.VBELTS[belt]
        for pd_, dd, cc in ((pa, float(p.get("pulley_d_mm") or 100), centers[0]), (pb, float(p.get("pulley2_d_mm") or 200), centers[1])):
            r = radial(eng_vertices(pd_), cc, "y")
            out.append(dim(f"đường kính ngoài puly (dp {dd:g} + 2·0,28h, ISO 4183)", float(2 * r.max()), dd + 2 * 0.28 * v_["height"],
                           0.004, 0.1))
    return out


@register("chain_drive")
def _chain(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    ch = S.CHAINS[p.get("chain", "08B")]
    pitch = ch["pitch"]
    ids = by_id(parts)
    sa, sb, chain = ids.get("sprocket_driver"), ids.get("sprocket_driven"), ids.get("chain")
    if not (sa and sb and chain):
        return [Check("dimensions", "đĩa xích + xích", False, "thiếu", 2.0, True)]
    out: list[Check] = []
    cen = []
    for sp, zt in ((sa, int(p.get("teeth_driver", 17))), (sb, int(p.get("teeth_driven", 34)))):
        lo, hi = solid_bounds(sp)
        v = eng_vertices(sp)
        R = pitch / (2 * math.sin(math.pi / zt))
        cc = (lo + hi) / 2
        rr = radial(v, cc, "y")
        ra = float(rr.max())
        band = v[rr > ra * 0.98]
        cc[1] = float(np.median(band[:, 1])) if len(band) else cc[1]
        n = ring_count(sp.solid, cc, "y", (R + ra) / 2, -1.5, 1.5, thickness=0.02)
        out.append(count_check(f"số răng đĩa xích (đếm, yêu cầu {zt})", n, zt))
        out.append(dim(f"đường kính đỉnh răng da ≈ p(0,54 + cot(180°/z)) — z = {zt}", 2 * ra,
                       pitch * (0.54 + 1 / math.tan(math.pi / zt)), 0.01, 0.1, critical=False))
        cen.append(cc)
    roll_mesh = next((m for m, mt in chain.meshes if getattr(mt, "id", "") == "steel"), None)
    if roll_mesh is not None:
        comps = mesh_components(roll_mesh)
        cs_ = np.array([eng(c).mean(axis=0) for c in comps])
        out.append(Check("dimensions", "số mắt xích chẵn (đếm con lăn)", len(cs_) % 2 == 0 and len(cs_) > 10, f"{len(cs_)} con lăn",
                         2.0, True))
        if len(cs_) > 3:
            from scipy.spatial import cKDTree
            dd, _ = cKDTree(cs_).query(cs_, k=2)
            out.append(dim("bước xích đo giữa tâm con lăn (ISO 606)", float(np.median(dd[:, 1])), pitch, 0.002, 0.01))
    C = float(math.hypot(cen[1][0] - cen[0][0], cen[1][2] - cen[0][2]))
    want = float(p.get("center_distance_mm") or meta.get("center_requested_mm", C))
    out.append(Check("dimensions", "khoảng cách tâm (hiệu chỉnh ≤ ½ bước theo số mắt nguyên)", abs(C - want) <= pitch / 2 + 1e-6,
                     f"đo {C:.2f} / yêu cầu {want:g} mm", 2.0, "center_distance_mm" in (spec.explicit or {})))
    return out


@register("shaft_coupling")
def _coupling(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    d1 = float(p.get("bore_mm", 14.0))
    d2 = float(p.get("bore2_mm") or d1)
    ids = by_id(parts)
    out: list[Check] = []
    for sid, want in (("shaft_1", d1), ("shaft_2", d2)):
        sh = ids.get(sid)
        if sh is None:
            out.append(Check("dimensions", sid, False, "thiếu", 2.0, True))
            continue
        lo, hi = solid_bounds(sh)
        out.append(dim(f"đường kính trục {sid[-1]} = lỗ khớp nối", float(hi[1] - lo[1]), want, 0.005, 0.03))
    h1 = ids.get("hub_1")
    if h1 is not None:
        lo, hi = solid_bounds(h1)
        if p.get("coupling_type", "jaw") == "jaw":
            size = next(k for k in sorted(S.JAW_COUPLINGS) if S.JAW_COUPLINGS[k][2] >= max(d1, d2))
            out.append(dim(f"đường kính ngoài khớp vấu (ROTEX cỡ {size})", float(hi[1] - lo[1]), S.JAW_COUPLINGS[size][0], 0.005, 0.05))
            out.append(shape("có đệm sao đàn hồi", "spider" in ids, ""))
        v = eng_vertices(h1)
        ctr = (lo + hi) / 2
        left = v[v[:, 0] < ctr[0] - 0.5]
        out.append(dim("lỗ moay-ơ phía trục 1", float(2 * radial(left, ctr, "x").min()) if len(left) else None, d1, 0.005, 0.03))
    return out


@register("ball_screw")
def _ball_screw(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    d, lead = float(p.get("diameter_mm", 16)), float(p.get("lead_mm", 5))
    t = S.BALL_SCREWS[f"{int(round(d)):02d}{int(round(lead)):02d}"]
    ids = by_id(parts)
    sh, nut = ids.get("screw_shaft"), ids.get("ball_nut")
    if not (sh and nut):
        return [Check("dimensions", "trục vít + đai ốc", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(sh)
    out = [dim("chiều dài trục vít", float(hi[0] - lo[0]), float(p.get("length_mm", 500)), 0.002, 0.1)]
    v = eng_vertices(sh)
    yc, zc = (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2
    x0, x1 = lo[0] + 0.3 * (hi[0] - lo[0]), lo[0] + 0.7 * (hi[0] - lo[0])
    mid = v[(v[:, 0] > x0) & (v[:, 0] < x1)]
    r = np.hypot(mid[:, 1] - yc, mid[:, 2] - zc)
    out.append(dim("đường kính danh nghĩa vít", float(2 * r.max()), d, 0.005, 0.03))
    iv = probe_intervals(sh.solid, "x", (0, yc + d / 2 - 0.05, zc), eps=0.02)
    iv = [q for q in iv if q[0] > x0 and q[1] < x1]
    cen = [(a + b) / 2 for a, b in iv]
    out.append(dim("bước vít (khoảng gờ ren liên tiếp, đo dọc đường sinh)", float(np.median(np.diff(cen))) if len(cen) > 3 else None,
                   lead, 0.01, 0.02))
    vn = eng_vertices(nut)
    out.append(dim("đường kính mặt bích đai ốc (TBI SFU)", float(2 * np.hypot(vn[:, 1] - yc, vn[:, 2] - zc).max()), float(t["flange_d"]),
                   0.01, 0.2, critical=False))
    return out


@register("linear_guide")
def _linear_guide(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    g = S.LINEAR_GUIDES[spec.params.get("series", "HGR20")]
    ids = by_id(parts)
    rail = ids.get("rail")
    if rail is None:
        return [Check("dimensions", "ray", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(rail)
    out = [dim("bề rộng ray (HIWIN)", float(hi[1] - lo[1]), g["rail_w"], 0.003, 0.02),
           dim("chiều cao ray", float(hi[2] - lo[2]), g["rail_h"], 0.003, 0.02),
           dim("chiều dài ray", float(hi[0] - lo[0]), float(spec.params.get("length_mm", 400)), 0.002, 0.1)]
    iv = probe_intervals(rail.solid, "x", (0, (lo[1] + hi[1]) / 2, hi[2] - g["cb_h"] / 2))
    gs = gaps_between(iv)
    if len(gs) >= 2:
        c = np.array([(a + b) / 2 for a, b in gs])
        out.append(dim("bước lỗ lắp ray P", float(np.median(np.diff(c))), g["pitch"], 0.002, 0.05))
    else:
        out.append(dim("bước lỗ lắp ray P", None, g["pitch"]))
    cars = by_cat(parts, "carriage")
    out.append(count_check("số con trượt", len(cars), int(spec.params.get("carriages", 2))))
    if cars:
        clo, chi = solid_bounds(cars[0])
        out.append(dim("bề rộng con trượt", float(chi[1] - clo[1]), g["car_w"], 0.003, 0.05))
        out.append(dim("chiều cao lắp H (đáy ray → mặt con trượt)", float(chi[2] - lo[2]), g["h"], 0.003, 0.05))
    return out


@register("spring")
def _spring(spec: Any, parts: Sequence[Any], meta: dict) -> list[Check]:
    p = spec.params
    kind = p.get("spring_type", "compression")
    d, OD = float(p.get("wire_d_mm", 2.0)), float(p.get("outer_d_mm", 20.0))
    ids = by_id(parts)
    sp = ids.get("spring")
    if sp is None:
        return [Check("dimensions", "lò xo", False, "thiếu", 2.0, True)]
    lo, hi = solid_bounds(sp)
    ctr = (lo + hi) / 2
    v = eng_vertices(sp)
    out = [dim("đường kính ngoài", float(2 * radial(v, ctr, "z").max()), OD, 0.005, 0.03)]
    # mặt cắt nửa phẳng x > 0, y ≈ 0: mỗi vòng dây cắt một lần → đếm vòng, đo bước và đường kính dây
    slab = K.box(OD, 0.02, (hi[2] - lo[2]) * 3 + 10).translate(ctr[0] + OD / 2, ctr[1], ctr[2])
    cut = sp.solid & slab
    comps = sorted(cut.split_components(), key=lambda s: s.bounds()[0][2]) if not cut.is_empty else []
    zs = [(c.bounds()[0][2] + c.bounds()[1][2]) / 2 for c in comps]
    wd = [c.bounds()[1][0] - c.bounds()[0][0] for c in comps]
    out.append(dim("đường kính dây (đo mặt cắt)", float(np.median(wd)) if wd else None, d, 0.01, 0.02))
    if kind == "compression":
        L0 = float(p.get("free_length_mm") or 50.0)
        out.append(dim("chiều dài tự do L0", float(hi[2] - lo[2]), L0, 0.003, 0.05))
        n = float(p.get("active_coils", 8.0))
        ends = p.get("ends", "ground")
        extra = {"ground": 2 * d, "closed": 3 * d, "open": d}[ends]
        pch = (L0 - extra) / n
        if len(zs) >= 4:
            dz = np.diff(zs)
            act = dz[dz > 1.2 * d] if ends != "open" else dz
            out.append(dim("bước vòng làm việc (đo)", float(np.median(act)) if len(act) else None, pch, 0.01, 0.03))
            want_total = n + (0 if ends == "open" else 2)
            out.append(Check("dimensions", "số vòng tổng (đếm vết cắt dây)", abs(len(zs) - want_total) <= 1.0,
                             f"đếm {len(zs)} / ≈ {want_total:g}", 2.0, True))
    elif kind == "extension":
        L0 = float(p.get("free_length_mm") or 50.0)
        tot_lo = min(solid_bounds(x)[0][2] for x in parts)
        tot_hi = max(solid_bounds(x)[1][2] for x in parts)
        out.append(dim("chiều dài tự do kể cả móc", float(tot_hi - tot_lo), L0, 0.005, 0.1))
        out.append(count_check("số móc", len(by_cat(parts, "hook")), 2))
        if len(zs) >= 4:
            out.append(dim("bước thân (quấn khít = d)", float(np.median(np.diff(zs))), d, 0.02, 0.02))
    else:
        out.append(count_check("số chân lò xo xoắn", len(by_cat(parts, "leg")), 2))
    return out

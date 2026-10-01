# Prompt: mở rộng hệ CAD tham số NEXA với ~30 mô hình kỹ thuật mới

Bạn là kỹ sư CAD + phần mềm cấp cao, làm việc trong repo NEXA (C:\Users\ASUS\Desktop\NEXA, Windows, Python 3.11 trong
.venv, PySide6/Qt Quick 3D). Nhiệm vụ: thêm TẤT CẢ các mô hình kỹ thuật dưới đây vào hệ CAD tham số cục bộ
(nexa/three_d), mỗi mô hình phải **chi tiết và sát thực tế** như thiết bị thật, dựng offline, có assembly tách/lắp đúng
logic, kích thước đo được, và qua quality gate. KHÔNG dùng Gemini/Hugging Face/Tripo để dựng các mô hình này.

## 0. Đọc trước khi code (bắt buộc)
- docs/three_d.md (kiến trúc, quy ước, mục "Chi tiết kỹ thuật", "Giới hạn").
- Mẫu tham khảo tốt nhất: nexa/three_d/generation/templates/boat.py, rover.py, humanoid.py, uav.py, helicopter.py.
- Hạ tầng dùng lại: templates/details.py (panel_lines, outline_groove, screws_at, button_screw, corner_points,
  vent_cutter, cable, handle_bar, estop_button, light_bar, ultrasonic_sensor, charge_port, label_plate, cooling_fins,
  rivet_row, shrink, **surface_at** — dò bề mặt thật, không đoán tọa độ), templates/components.py (motor_outrunner,
  propeller NACA, wheel, servo_actuator, battery_pack, camera_gimbal, lidar_puck, antenna, screw), geometry/kernel.py
  (loft, sweep, tube, revolve, extrude, hull, threaded_rod ISO, involute gear qua profiles), geometry/profiles.py,
  geometry/materials.py (library/object_library, material(), tinted, MICRO_TEXTURES, apply_micro_textures),
  generation/assembly.py (AssemblyBuilder.add/cut/note_stage, no_clash_with), spec.py, planner.py, checklist.py,
  quality.py, parametric.py (FIT_TARGETS), benchmark.py, intents.py.

## 1. Danh sách mô hình (mỗi dòng = ít nhất một category/template)
**A. Linh kiện cơ khí tiêu chuẩn** (đo kiểm chính xác theo tiêu chuẩn — ghi nguồn bảng số trong docstring):
1. Ổ bi rãnh sâu dãy 60xx/62xx/63xx (ISO 15; vd 6000 = 10×26×8, 6200 = 10×30×9, 6300 = 10×35×11 mm): vòng trong,
   vòng ngoài có rãnh lăn, bi (số bi + đường kính theo cỡ), vòng cách, phớt 2RS/nắp ZZ tùy chọn.
2. Động cơ bước NEMA 17/23/34 (NEMA ICS 16): mặt bích vuông, khoảng cách lỗ, gờ định tâm, trục (có mặt vát D), thân
   nhiều lớp lá thép, nắp sau, dây/đầu cắm; chiều dài thân tham số.
3. Hộp số bánh răng ăn khớp: ≥ 2 cấp, bánh răng thân khai ăn khớp đúng khoảng cách tâm a = m(z1+z2)/2, trục, ổ bi,
   vỏ hai nửa + bu-lông, phớt, nút thăm dầu; kiểm tra tỷ số truyền và khoảng cách tâm trong quality.
4. Xi lanh khí nén/thủy lực (ISO 15552 cho khí nén): nòng, nắp trước/sau, piston, cần piston, thanh giằng, cổng khí,
   đai ốc cần; hành trình tham số; trạng thái thu/duỗi.
5. Van bi (tay gạt), mặt bích đường ống, co 90°/45°, tê — theo cỡ DN15–DN200 (đường kính ngoài ống, bu-lông mặt bích
   theo EN 1092-1/ASME B16.5, ghi rõ chuẩn chọn).
6. Puly + dây đai (răng GT2/HTD hoặc thang), bánh xích + xích con lăn (ISO 606), khớp nối trục (mềm/cứng).
7. Vít me bi + đai ốc bi, ray trượt tuyến tính + con trượt (kiểu HGR/MGN).
8. Lò xo nén/kéo/xoắn: đường xoắn thật, đường kính dây, số vòng, bước, đầu mài phẳng/móc.

**B. Robot và tự động hóa**
9. Cánh tay robot công nghiệp 6 trục (kiểu KUKA/UR): đế, 6 khớp servo (dùng lại mẫu actuator của humanoid), khâu
   nối có vỏ đúc, cáp chạy dọc tay, mặt bích dụng cụ ISO 9409-1, tùy chọn kẹp/giác hút; tư thế tham số.
10. Robot hút bụi: thân tròn, cản trước, LiDAR đỉnh, 2 bánh chủ động + bánh xoay, chổi cạnh, chổi chính, khay bụi,
    cảm biến chống rơi, nút, đế sạc.
11. Robot giao hàng / AGV kho: khung, bánh mecanum hoặc vi sai, nâng kệ, LiDAR, cảm biến an toàn, đèn, nút E-stop.

**C. Phương tiện**
12. Máy bay cánh bằng / UAV cánh cố định VTOL: thân, cánh NACA có góc nhị diện, cánh lái (aileron, elevator, rudder
    tách được), động cơ + cánh quạt, càng, VTOL 4 rotor trên 2 cần.
13. Ô tô điện: thân loft (sedan/SUV/hatchback), 4 bánh + mâm + phanh đĩa + kẹp phanh, treo, pin sàn, motor cầu, kính,
    đèn, gương, tay nắm, cửa tách được.
14. Xe máy / xe đạp điện: khung, phuộc, bánh căm/mâm, phanh đĩa, xích/động cơ trong moay-ơ, yên, tay lái, đèn.
15. Máy xúc, xe nâng, xe cẩu: bánh xích/bánh lốp, cần + tay gầu có xi lanh thủy lực nối đúng khớp, cabin, đối trọng.
16. Đầu máy tàu hỏa + toa xe: thân, giá chuyển hướng (bogie) + bánh ray, khớp nối toa, cabin lái, cần lấy điện
    (tàu điện). Lưu ý: "tàu" đang thuộc nhóm thuyền — "tàu hỏa/tàu điện/đầu máy/toa" phải sang category mới.
17. Vệ tinh CubeSat 1U–12U (CubeSat Design Specification: 1U = 100 × 100 × 113,5 mm, ray góc): khung, tấm pin mở
    cánh, ăng-ten, bo mạch xếp chồng, camera.
18. Tên lửa nhiều tầng: các tầng, bồn nhiên liệu, động cơ + vòi phun, cánh ổn định, chóp mũi, vòng nối tầng; tách
    tầng theo thứ tự thật.

**D. Năng lượng và công trình**
19. Tua-bin gió trục ngang: tháp côn, vỏ nacelle (tách được để lộ trục chính, hộp số, máy phát, cơ cấu quay hướng),
    moay-ơ + 3 cánh NACA xoắn.
20. Hệ pin mặt trời: tấm pin (khung nhôm, ô cell, hộp đấu dây), giàn đỡ nghiêng, inverter, tủ điện.
21. Máy phát điện diesel, bơm ly tâm (vỏ xoắn ốc, cánh bơm, động cơ, bệ), bồn chứa (đứng/nằm, thang, van).
22. Cầu (giàn/dây văng/vòm), giàn thép, tháp (điện/viễn thông) — kết cấu thanh + bản mã + bu-lông.

**E. Máy chế tạo và điện tử**
23. Máy in 3D FDM: khung nhôm định hình 2020/2040, trục X/Y/Z (ray, vít me, đai), đầu in (quạt, tản nhiệt, vòi),
    bàn nhiệt, màn hình, cuộn nhựa.
24. Máy CNC 3 trục: khung, cổng trục, spindle, vít me bi, ray trượt, bàn máy rãnh T, động cơ bước NEMA (dùng lại mục 2).
25. Tủ rack 19" (482,6 mm, 1U = 44,45 mm), hộp điện, quạt (khung + cánh + lưới), tản nhiệt (lá + ống nhiệt), bo mạch
    kiểu Arduino/Raspberry Pi (PCB, chip, header, cổng USB/HDMI/Ethernet ở đúng vị trí tương đối).

## 2. Yêu cầu chất lượng cho MỖI mô hình
- **Sát thực tế**: tỷ lệ và kích thước theo sản phẩm/tiêu chuẩn thật; mỗi docstring ghi nguồn số liệu. Không để khối hộp
  trơn: dùng loft/sweep/revolve, fillet/chamfer, và chi tiết của thiết bị thật (rãnh ghép, ốc, khe gió, cáp, đèn, nhãn,
  cảm biến, gân tăng cứng, lỗ bắt vít…). Vật liệu PBR đúng loại (thép, nhôm chải, đồng, cao su, nhựa, sơn, kính, gỗ).
- **Assembly thật**: mỗi bộ phận có id, name_vi, aliases tiếng Việt, category, parent_id đúng chuỗi lắp ráp, joint_axis
  cho khớp, explode_dir/explode_distance/explode_order theo thứ tự tháo lắp thật; note_stage cho từng bước.
- **Không xuyên nhau / không lơ lửng**: đặt chi tiết bằng số đo thật (details.surface_at, bounds). Khai báo
  no_clash_with cho cặp quan trọng. Chạy quét giao khối mọi cặp bộ phận không cha–con (xem đoạn mã trong test
  tests/test_three_d_technical_detail.py) cho TỪNG biến thể; chỗ nối có chủ đích (ngàm, bắt ốc) được phép, còn lại = 0.
  Chỗ đi xuyên vỏ thật (trục, chân càng) thì khoét lỗ bằng AssemblyBuilder.cut.
- **Kích thước**: tham số người dùng nói rõ được giữ đúng (FIT_TARGETS hoặc dựng đúng mm); quality.py có kiểm tra
  deterministic riêng cho nhóm (vd ổ bi: d/D/B; NEMA: cạnh mặt bích, khoảng lỗ, Ø trục; hộp số: khoảng cách tâm, tỷ số
  truyền; CubeSat: kích thước U; rack: 482,6 mm & bội 44,45 mm; lò xo: bước, số vòng).
- **Hiệu năng**: mỗi mô hình ≤ 450 nghìn tam giác, dựng ≤ ~5 s, cả pipeline ≤ ~15 s trên máy này.
- **Kính/vỏ trong suốt**: làm vỏ mỏng, không để mặt trùng mặt (lỗi nhiễu sọc đã gặp ở trực thăng, robot).

## 3. Tích hợp đầy đủ (theo đúng cách nhóm "boat" đã làm)
1. spec.py: SUPPORTED_GROUPS, CATEGORY_GROUP, CATEGORY_VI, SAFETY_CRITICAL (phương tiện, robot, cần cẩu, tên lửa…),
   PARAM_SCHEMAS (enum/khoảng hợp lệ, mô tả tiếng Việt; tham số bắt buộc chỉ khi thật sự bắt buộc — vd cỡ ổ bi).
2. planner.py: CATEGORY_PATTERNS (thứ tự ưu tiên, không bắt nhầm), parse tham số tiếng Việt (có/không dấu, "hai/2",
   "dài 6 m", "M8", "NEMA 17", "6204", "DN50", "3U"…), `_default_name`, câu hỏi khi thiếu tham số bắt buộc.
   Xung đột cần xử lý: "tàu hỏa/tàu điện" (không phải thuyền), "máy bay" (khác "máy bay không người lái"/"máy bay lên
   thẳng"), "xe máy" vs "máy", "ổ bi" vs "bi", "cần cẩu" (alias tời trực thăng), "bơm", "quạt", "van", "tháp", "cầu".
   Không được làm hỏng lệnh cũ (tạo thư mục, file word, mở ứng dụng…) — xem tests/test_three_d_hf_intents.py.
3. templates/__init__.py (get_template), checklist.py (bộ phận bắt buộc theo tham số), quality.py (kiểm tra hình dáng +
   kích thước riêng), parametric.FIT_TARGETS, materials.expected_kinds (loại vật liệu hợp lệ cho category mới),
   pipeline.DEFAULT_SIZE_MM.
4. benchmark.py: GROUPS mới, ≥ 60 câu mỗi nhóm (≥ 5 câu mỗi category) với ground truth; spec_matches phải 100%.
5. Gemini prompt (ai/prompts.py, tools.py mô tả generate_3d_model) liệt kê nhóm mới.
6. scripts/smoke_3d_viewer.py: thêm PROMPTS cho vài mẫu tiêu biểu mỗi nhóm.
7. Tài liệu: docs/three_d.md (nhóm hỗ trợ + chi tiết từng mẫu + nguồn tiêu chuẩn), README.md (ví dụ câu lệnh),
   docs/manual_tests.md (bước kiểm tra tay), config/settings.example.yaml nếu thêm cấu hình.

## 4. Kiểm thử và xác minh (bằng chứng thật, không tuyên bố suông)
- Test mới cho mỗi nhóm: parse câu lệnh, kích thước tiêu chuẩn đo được, checklist, không xuyên nhau, mọi gate đạt,
  explosion plan hợp lệ, số tam giác. Giữ nguyên toàn bộ test cũ (hiện 991 test) và benchmark cũ (421/421).
- Chạy: `.venv\Scripts\python -m pytest -q`, `.venv\Scripts\python -m pyflakes nexa tests scripts`,
  `.venv\Scripts\python scripts\bench_3d_quality.py --workers 4 --out results\3d_benchmark_local.json`.
- **Xem tận mắt** từng mẫu: render 6 góc (`nexa.three_d.render.render_six` → contact_sheet → PNG) và viewer thật
  `scripts/smoke_3d_viewer.py <kind> <out.png> --window --assembled` (cửa sổ D3D11 ngoài màn hình; nền offscreen không vẽ
  được Qt Quick 3D). Mở PNG ra xem và sửa những gì trông sai (tỷ lệ, lơ lửng, xuyên, nhiễu sọc, thiếu chi tiết).

## 5. Quy tắc làm việc (bài học đã gặp — bắt buộc tuân thủ)
- KHÔNG sửa code có regex/dấu gạch ngược bằng heredoc Bash (`python - <<'EOF'`): trong môi trường này `\b` bị ghi thành
  ký tự backspace. Dùng công cụ Edit/Write. Test test_no_control_characters_in_sources chặn lỗi này.
- Hệ trục template: X trước, Y trái, Z lên, đơn vị mm; AssemblyBuilder tự đổi sang hệ glTF. Đáy mô hình tại z = 0.
- Không chụp màn hình máy người dùng; không mở camera/mic; không mở NEXA.exe. Không xóa code cũ, không git reset --hard.
- Không ghi API key vào file; không gọi Gemini/HF để dựng các mô hình này (chỉ CAD cục bộ).
- Không tuyên bố "chính xác 90%" hay "đủ an toàn để chế tạo"; nhóm phương tiện/robot/cần cẩu/tên lửa luôn có cảnh báo.
- Làm theo từng đợt, mỗi đợt xong phải xanh toàn bộ test trước khi sang đợt sau:
  Đợt 1: A (linh kiện chuẩn) → Đợt 2: B (robot) → Đợt 3: C (phương tiện) → Đợt 4: D (năng lượng/công trình)
  → Đợt 5: E (máy chế tạo/điện tử). Sau mỗi đợt báo cáo ngắn: mô hình đã thêm, ảnh đã xem, điểm, số test, benchmark.

## 6. Hoàn thành khi
- Tất cả mô hình mục 1 dựng được qua câu lệnh tiếng Việt tự nhiên, mở trong viewer, tách/lắp đúng thứ tự.
- Benchmark mọi nhóm (cũ + mới) 100% đạt gate và 100% hiểu đúng câu; toàn bộ test xanh; pyflakes sạch.
- Không cặp bộ phận nào xuyên nhau ngoài chỗ nối có chủ đích; không bộ phận lơ lửng; viewer không cảnh báo QML.
- Tài liệu cập nhật; báo cáo cuối liệt kê trung thực phần đã kiểm chứng và giới hạn còn lại.

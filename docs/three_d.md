# NEXA — Tạo và tương tác với mô hình 3D

Anh Sơn nói hoặc gõ yêu cầu ("Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm", "Tạo UAV mini bốn cánh, thân carbon màu đen,
camera phía trước"…). NEXA tự hiểu yêu cầu, hỏi lại thông số bắt buộc còn thiếu, dựng mô hình, kiểm tra chất lượng, lưu
cache và mở trình xem 3D. Không cần mở hay tải file CAD nào.

## Tạo mô hình từ ảnh tham chiếu

Trong **Không gian sáng tạo 3D**, chọn ảnh vào các ô **Trước, Sau, Trên, Dưới, Trái, Phải** rồi bấm **Tạo**.
Có thể dùng 1–6 góc của cùng một vật thể; chọn lại để thay ảnh, hoặc bấm **×** để xóa. Mô tả là tùy chọn;
nên ghi kích thước thật (mm) và chi tiết cần giữ. Các góc trái/phải được tính theo hướng của vật thể.

Luồng này cần Gemini API đã cấu hình để đối chiếu kết quả. Khi bấm Tạo, NEXA ưu tiên dịch vụ ảnh → 3D đang
cấu hình (Tripo/Meshy/Hugging Face); chỉ dùng CAD DSL ước lượng nếu chưa có dịch vụ ảnh → 3D sẵn sàng.
Nếu dịch vụ đã chọn gặp lỗi, NEXA báo lỗi thay vì âm thầm chuyển sang CAD đơn giản.
Mọi lần tạo lại đều dùng ảnh gốc, không dùng mẫu CAD hoặc cache chỉ dựa trên văn bản. Đây là dựng hình **best effort**,
không phải quét 3D chính xác; phần khuất và kích thước không được cung cấp sẽ được ước lượng.
Lựa chọn chế độ CAD/Cloud chỉ áp dụng khi không đính kèm ảnh.
Khi đính kèm ảnh, chọn **Ảnh → 3D** để dùng dịch vụ dựng từ ảnh hoặc **CAD từ ảnh gốc** để Gemini
thiết kế hình học trực tiếp từ các ảnh, không gọi tách nền. Cách CAD vẫn là ước lượng, khó giữ đủ hoa,
chữ và vật liệu. Nếu tách nền mất sa bàn, thông báo có nút **Thử CAD từ ảnh gốc** dùng bộ ảnh và mô tả
đang chọn. NEXA không tự đổi phương pháp; cả hai cách đều phải qua kiểm tra độ giống.
Mô hình từ ảnh ưu tiên chất lượng thị giác, không yêu cầu tách rời: không gọi segmentation, không yêu cầu
explosion plan và không bật thao tác tháo lắp. Kiểm tra lưới, vật liệu, manifest và độ giống ảnh vẫn giữ nguyên.

Gemini chấm riêng từng góc: hình dáng tổng thể cần ≥8/10, mỗi góc ≥7,5/10, màu/vật liệu ≥7/10 và không còn
lỗi lớn. Thiếu đánh giá hoặc chưa giống ảnh sẽ báo **chưa đạt**; có thể mở bản này để xem nhưng không tự mở như
kết quả hoàn tất. Điểm này là đánh giá AI, không phải phép đo độ chính xác của quét 3D.
Tripo/Meshy hiện nhận các góc trước/sau/trái/phải; ảnh trên/dưới vẫn dùng để đối chiếu và có thông báo giới hạn.
Bộ gọi TRELLIS nhận ảnh đa góc; không chuyển đa góc sang bộ gọi Hunyuan một ảnh và bỏ các ảnh còn lại.

TRELLIS được gọi theo đúng phiên giao diện: `/preprocess_image` cho từng ảnh → chọn tab Single/Multiple Images
qua cấu hình endpoint của phiên → dựng GLB. Gallery đa góc bao gồm cả ảnh chính. Lỗi tách nền/chuyển chế độ
sẽ dừng tác vụ, không tiếp tục dựng từ ảnh phòng chưa xử lý. Chất lượng cao dùng 24 bước lấy mẫu và texture
2048 px; mặc định 12 bước và 1024 px. Tách nền tự động vẫn có thể nhầm ở sa bàn nhiều thanh mảnh.
Đối chiếu phải kiểm tra riêng hậu cảnh dựng thừa, cấu trúc/khoảng gãy có chủ đích và chữ nhận diện trên biển;
các lỗi này không được bỏ qua chỉ vì điểm tổng cao. Ảnh cận cảnh không nên gán là ảnh toàn cảnh của một mặt.
Gemini còn so sánh từng ảnh trước/sau tách nền trước khi gọi dựng hình. Nếu chỉ còn biển tên hoặc lá cờ,
thiếu kết quả kiểm tra, hoặc còn hậu cảnh thì tác vụ dừng; không coi tách nền thành công là đã giữ đúng vật thể.

Nguồn giao thức: [mã ứng dụng TRELLIS](https://huggingface.co/spaces/trellis-community/TRELLIS/blob/main/app.py).

Hỗ trợ PNG/JPEG/WebP, tối đa 20 MB và 24 triệu điểm ảnh mỗi ảnh. NEXA tự xoay theo EXIF,
thu nhỏ tối đa 1536 px và lưu bản ảnh đã chuẩn hóa tại `source/reference_images/<góc>.jpg` trong dự án.
Ảnh có nền trong suốt được giữ alpha và lưu `.png`, để không làm mất mặt nạ tách nền người dùng đã chuẩn bị.
Các ảnh đã chọn được giữ trên giao diện để thử lại; xóa ảnh trước khi tạo vật thể khác.

## 1. Kiến trúc

```
Giọng nói / văn bản
  → IntentRouter (mẫu câu local)  ─┐
  → Gemini (function calling)     ─┴→ generate_3d_model (trả job_id NGAY, không chặn executor)
  → JobManager (luồng nền)
       planning: Planner = bộ phân tích tiếng Việt cục bộ + Gemini (JSON theo schema) → ModelSpec (kiểm tra nghiêm ngặt)
       └─ đường dựng:
          parametric  CAD tham số cục bộ (manifold3d + mặt tham số numpy) cho 6 nhóm hỗ trợ — có assembly, kích thước chính xác
          dsl         vật thể ngoài nhóm: Gemini mô tả bằng CAD DSL JSON (whitelist) → kernel (best effort)
          cloud       Tripo (mặc định) / Meshy: (ảnh tham chiếu nhiều góc) → N ứng viên → segmentation → chọn tốt nhất
       texturing → segmenting → validating (GLB + lưới + manifest) → rendering 6 góc → reviewing (Gemini chấm ảnh)
       → quality gate → refining (tối đa 1–2 vòng) → optimizing (LOD) → lưu cache
  → ViewerController (trạng thái viewer, nguồn sự thật)  ⇄ ThreeDBridge ⇄ ModelViewer.qml (Qt Quick 3D)
  → Cử chỉ: GestureEngine ở chế độ VIEWER_3D (độc quyền) → ViewerGestureStateMachine → ViewerController
```

Gemini chỉ trả JSON đúng schema (ModelSpec, CAD DSL, đánh giá ảnh). NEXA không bao giờ chạy mã do AI sinh.

### Mã nguồn (`nexa/three_d/`)

| Tệp | Vai trò |
|---|---|
| `models.py` | Model3DProject, Part3D, Material, trạng thái job, quy ước trục |
| `spec.py` | ModelSpec + schema nghiêm ngặt theo nhóm, bảng ISO (ren thô, lục giác, đai ốc, vòng đệm) |
| `planner.py` | Bộ phân tích local + Gemini planner, hỏi thông số thiếu, số người dùng nói luôn thắng |
| `checklist.py` | Danh sách bộ phận bắt buộc DO MÃ TÍNH từ spec (không tin AI) |
| `geometry/kernel.py` | Khối đặc manifold3d, revolve/extrude/loft/sweep (khung quay tối thiểu), ren helix ISO 68-1 |
| `geometry/profiles.py` | Fillet/chamfer profile, siêu elip, NACA 4 chữ số, bánh răng thân khai, B-spline |
| `geometry/dsl.py` | CAD DSL whitelist (box, cylinder, … fillet, chamfer) — giới hạn độ sâu/số nút/giá trị |
| `geometry/materials.py` | Thư viện PBR + texture thủ tục (vân carbon, normal map ren minh họa) |
| `geometry/gltf.py` | Đọc/ghi GLB tối giản, không URI ngoài |
| `generation/templates/*` | UAV, xe tự hành, robot người, robot chó, trực thăng, ốc vít, bánh răng/mặt bích/giá đỡ + linh kiện chuẩn |
| `generation/base.py, tripo_provider.py, meshy_provider.py, http.py` | ThreeDProvider + provider cloud thật |
| `postprocess/mesh.py` | Nhập GLB cloud, chuẩn hóa tỷ lệ, giảm lưới (LOD) |
| `validator.py`, `manifest.py`, `quality.py`, `render.py`, `review.py` | Kiểm tra deterministic, manifest, chấm điểm, render phần mềm 6 góc, Gemini chấm ảnh |
| `job_manager.py`, `pipeline.py`, `asset_store.py` | Job nền, pipeline, cache LRU + xuất GLB/STL/OBJ/3MF |
| `part_resolver.py`, `viewer_controller.py`, `gesture_controller.py` | Tìm bộ phận theo lời nói, trạng thái viewer, cử chỉ VIEWER_3D |
| `motion.py` | Suy luận chuyển động cơ khí từng bộ phận (quay/lắc/trượt, chuỗi khớp) cho mọi nhóm mô hình |
| `tools.py`, `intents.py`, `service.py`, `benchmark.py` | Công cụ cho executor/Gemini, mẫu câu tiếng Việt, mặt tiền, bộ benchmark |

UI: `nexa/ui/three_d_bridge.py` (context `nexa3d`, kiểu QML `NexaMesh`), `nexa/ui/qml/ModelViewer.qml`,
`ModelPartPanel.qml`, `ModelGenerationPanel.qml`.

## 2. Chế độ tạo mô hình

| Chế độ | Khi nào | Cần gì | Kết quả |
|---|---|---|---|
| CAD tham số (`parametric`) | Nhóm hỗ trợ (mặc định `auto`) | Không cần mạng | Assembly thật, kích thước đo được, exploded view theo logic lắp |
| Mức 2 — CAD DSL (`dsl`) | Vật thể ngoài nhóm (mặc định khi không có key trả phí) | GEMINI_API_KEY | Gemini thiết kế các bộ phận bằng DSL whitelist; tự sửa lỗi biên dịch; xem ảnh 6 góc rồi tinh chỉnh; có bộ phận để tách/xem |
| Mức 3 — Cloud (`cloud`) | Có key Tripo/Meshy; hoặc nói "chất lượng cao", "bằng hugging face/cloud"; hoặc mức 2 thất bại/điểm < `dsl_fallback_below` | TRIPO_API_KEY / MESHY_API_KEY, hoặc **miễn phí** qua Hugging Face Space (HF_TOKEN khuyến nghị) | Lưới AI hữu cơ (TRELLIS có texture, Hunyuan3D chỉ hình), được làm sạch và tách bộ phận theo thành phần liên thông |

Khi thiếu key cloud: CAD tham số vẫn chạy; yêu cầu cloud báo rõ "Chưa có TRIPO_API_KEY…" và **không giả vờ đã tạo**.

### Mức 2 — Gemini thiết kế CAD DSL (`generation/dsl_designer.py`)
1. **Thiết kế**: Gemini nhận yêu cầu + hướng dẫn DSL + quy tắc (kích thước thật mm, đặt trên mặt đất, bộ phận chạm nhau
   đúng chỗ nối, tự kiểm tra hộp bao) + 3 ví dụ mẫu đã kiểm (cốc, bàn, chuột) → JSON `{design_notes, overall_size_mm, parts}`.
   Mỗi bộ phận là một cây DSL (không phải mã) với vật liệu (gồm gỗ, gốm sứ, vải, da, crôm…) và màu `#rrggbb` tùy chọn.
2. **Biên dịch chịu lỗi** (`parametric.compile_dsl_parts`): bộ phận sai được cô lập; thông báo lỗi gửi lại Gemini sửa
   (`dsl_repair_rounds`); bộ phận vẫn lỗi bị bỏ kèm cảnh báo. Mô hình được căn giữa và đặt đáy tại z = 0.
3. **Xem ảnh – tinh chỉnh** (`dsl_refine_rounds`): render 6 góc + số đo thật (hộp bao từng bộ phận, bộ phận lơ lửng) +
   góp ý của người chấm → Gemini sửa cả mô hình; giữ phương án điểm cao nhất (`best_round`).
4. Gọi Gemini ở chế độ **tác vụ dài**: chuỗi model riêng `dsl_models` (mặc định gemini-3.8-flash → gemini-3.5-flash →
   GEMINI_MODEL), thời hạn `dsl_timeout_s`, không theo ngân sách 20 s của hội thoại giọng nói, không đổi model hội thoại.
   Model quá tải (503) hoặc hết quota → tự chuyển model kế tiếp.
- Phép DSL mới: `ellipsoid`, `hull` (bao lồi — khối hữu cơ), `tube` (ống dọc đường cong), `linear_array`.
- Lỗi đã sửa: schema cũ có `maxItems` trên mảng object bị Gemini từ chối (400) và `shape: {type: object}` rỗng khiến
  Gemini trả `{}` → mức 2 trước đây chưa từng chạy được với Gemini thật. Nay dùng MIME JSON không schema + kiểm tra phía NEXA.

### Mức 3 — Hugging Face Space miễn phí (`generation/hf_provider.py`)
Chữ → ảnh sản phẩm nền trắng (model ảnh Gemini nếu key có hạn mức; không thì Space `black-forest-labs/FLUX.1-schnell`) →
ảnh → 3D bằng `trellis-community/TRELLIS` (`/generate_and_extract_glb`, GLB có texture) → dự phòng `tencent/Hunyuan3D-2` /
`tencent/Hunyuan3D-2.1` (`/shape_generation`, chỉ hình). Endpoint/tham số lấy từ `view_api()` của chính Space. Có hủy, hạn
thời gian từng bước (`hf_image_timeout_s`, `hf_space_timeout_s`, `hf_timeout_s`), báo trạng thái hàng đợi. Lưới AI được
**làm sạch** (bỏ tam giác suy biến/trùng/mảnh vụn, giữ UV) rồi tách bộ phận theo thành phần liên thông; cỡ thật (mm) do
Gemini ước lượng. Space chạy ZeroGPU: người dùng **ẩn danh chỉ có vài phút GPU mỗi ngày** → đặt `HF_TOKEN` (token đọc miễn
phí của tài khoản Hugging Face) trong `.env`. Quyền riêng tư: mô tả tiếng Anh và ảnh sinh ra được gửi tới Space công khai;
tắt bằng `three_d.hf_enabled: false`.

**Có `HF_TOKEN`** (`hf_prefer_with_token: true`): vật thể tự do đi mức 3 (HF) TRƯỚC; Space lỗi/hết hạn mức/ngủ → tự
chuyển mức 2. Lượt thật 2026-09-25 (tài khoản HF miễn phí, token fine-grained): "Tạo bình hoa gốm men xanh" → FLUX →
TRELLIS, GLB có texture màu, 11 nghìn tam giác, 95/100. Renderer 6 góc (ảnh cho Gemini chấm, thumbnail) nay đọc texture
`baseColorTexture` theo UV; vật liệu mesh AI thiếu `metallicFactor` (glTF mặc định 1,0 = kim loại) được nhập là phi kim.
Ứng viên đầu đạt ngưỡng thì không tạo thêm (trước đây vật thể tự do luôn tạo thêm ứng viên vì trạng thái best effort).

### Nhóm hỗ trợ (mục tiêu chất lượng áp dụng)
UAV/drone (3/4/6/8 tay đòn) · xe tự hành (4/6/8 bánh, rocker-bogie/treo độc lập) · robot hình người · robot chó (2 hoặc 3
khớp mỗi chân) · trực thăng (rotor chính 2–7 lá, rotor đuôi, càng trượt/bánh, tời, đèn pha) · **thuyền/tàu** (ca nô cao
tốc, tàu cá, du thuyền, tàu tuần tra; 1,5–60 m; máy gắn ngoài 1–3 máy hoặc máy trong + trục + chân vịt + bánh lái) ·
bu-lông (đầu lục giác ISO 4017/4014, đầu trụ ISO 4762, đầu côn), đai ốc ISO 4032, vòng đệm ISO 7089, bánh răng trụ thân
khai, mặt bích, giá đỡ chữ L. Vật thể khác: ghi rõ **best effort**, mục tiêu 90% không áp dụng.

### Chi tiết kỹ thuật (2026-09-25, `generation/templates/details.py`)
Các mẫu có chi tiết như thiết bị thật, dựng bằng CSG và đặt theo số đo bề mặt thật (`surface_at` dò mặt khối, không đoán):
rãnh ghép tấm khắc vào vỏ, đường viền cửa, ốc đầu tròn ISO 7380, khe tản nhiệt, dây cáp có đầu nối, tay cầm, nút dừng khẩn
cấp, dải đèn, cảm biến siêu âm, cổng sạc, tấm nhãn, vây tản nhiệt, đinh tán.
- Xe tự hành: rãnh ghép vỏ 3 mảng + nắp, khe gió, 6 ốc nắp, tay cầm, E-stop, đèn hậu, cổng sạc, nhãn, 3 cảm biến siêu âm
  trên cản, ốc ray, móc kéo, vây tản nhiệt + cáp động cơ, cáp cột camera, ốc trục rocker-bogie.
- Robot hình người: khớp = cụm servo (vỏ + mặt bích màu + vòng ốc hai mặt), giáp ngực có rãnh + khe gió, rãnh ghép tay
  chân, ngón có đốt khớp, pin lưng có ốc/tay cầm/đèn, đế chân gai; kính mặt là vỏ mỏng phủ mặt nạ cảm biến có "mắt" đèn.
- Robot chó: servo có vòng ốc + moay-ơ, vỏ có rãnh + khe gió + ốc + E-stop + đèn trạng thái, dải đèn mặt, cảm biến độ sâu
  hai bên, cáp đùi, đệm chân có rãnh.
- UAV: cột GPS/la bàn (đặt theo vị trí pin), ESC + bó dây 3 pha trên tay đòn, ốc tấm khung, khe gió vỏ, đèn trạng thái,
  ăng-ten dưới tay đòn sau; vỏ dưới khoét lỗ cho chân càng/gimbal.
- Trực thăng: viền cửa trượt + cửa phi công, ray trượt, tay nắm, đường ghép tấm, lưới hút gió turbine, ống pitot, ăng-ten
  lưỡi, đèn chống va, đèn hàng hải đỏ/xanh + đèn đuôi; kính buồng lái là vỏ mỏng, nhìn thấy bảng điều khiển + ghế.
- Thuyền: thân loft đáy V (deadrise tăng về mũi, mép gãy có gờ, mũi cong lên), boong, giếng buồng lái hở, bàn lái + kính
  chắn gió + ghế (ca nô) / buồng lái có cửa sổ + cột đèn (tàu cá) / cabin thuôn + vòm radar (du thuyền, tuần tra), lan can
  mũi inox, gờ mạn, cọc buộc dây, đèn mạn đỏ trái / xanh phải + đèn đuôi (COLREG), sơn chống hà, biển số, máy gắn ngoài
  (nắp máy, trục đứng, tấm chống xoáy, chân vịt inox) hoặc trục + chân vịt đồng 4 lá + bánh lái NACA.

### Nhóm CAD kỹ thuật mở rộng (2026-09-26)

Mã nguồn: bảng tiêu chuẩn `standards.py` (mỗi bảng ghi nguồn), khối dựng dùng chung `generation/templates/machine.py`
(ổ bi, bánh răng, NEMA, ốc–đai ốc–vòng đệm, puly/đai, đĩa xích/xích, ray/con trượt, vít me bi, lò xo, ống/mặt bích),
schema tham số `spec_tech.py`, phân tích câu `parse_tech.py`, đo kiểm `measure.py`. Mọi mẫu mới dựng hoàn toàn cục bộ
(không Gemini/HF/Tripo), đáy ở z = 0, bật **quét giao khối mọi cặp** bộ phận không cha–con (`strict_overlap`, chỗ tiếp xúc
có chủ đích khai trong `contacts`) và **kiểm tra lơ lửng bằng khoảng hở thật** (`manifold3d.min_gap`, dung sai
max(0,05 mm; 1e-4 × đường chéo)) — cả hai là lỗi hình học (gate). Chỗ ốc/trục đi xuyên vỏ được khoét bằng chính thân
ốc/trục (`AssemblyBuilder.cut`), nên giao khối = 0 mà vẫn khít.

**Nhóm "components" — linh kiện cơ khí tiêu chuẩn** (đo trên khối, so với bảng):

| Mẫu | Chuẩn / nguồn số liệu | Chi tiết dựng | Kiểm tra đo trong quality |
|---|---|---|---|
| Ổ bi rãnh sâu 60xx/62xx/63xx | ISO 15:2017 (d × D × B); số bi/Ø bi **ước lượng** theo tỷ lệ Harris, làm tròn cỡ bi ISO 3290 | vòng trong/ngoài có rãnh lăn độ ôm 52 %, bi chạm đáy rãnh, vòng cách thép dập tán đinh hoặc PA66, phớt 2RS / nắp ZZ ngàm rãnh vòng ngoài | d, D, B, số bi, Ø bi, bi trên vòng tâm |
| Động cơ bước NEMA 17/23/34 | NEMA ICS 16 (cạnh bích, khoảng lỗ 31/47,14/69,6, gờ 22/38,1/73, trục 5/6,35/12,7) | nắp nhôm, khối lá thép có rãnh lá, rotor răng, trục mặt vát D, 4 vít xuyên, đầu cắm JST + 4 dây màu / ống luồn dây, nhãn | cạnh bích, khoảng tâm lỗ (dò tia qua lỗ), gờ định tâm, Ø trục, dài trục, dài thân |
| Hộp số 2–3 cấp | bánh răng thân khai α = 20° (ISO 53), module ISO 54, ổ bi ISO 15 | trục bậc có then, bánh răng ăn khớp pha đúng + khe hở 0,05m, 2 ổ/trục, vỏ tách đôi có gờ bích lùi quanh ụ ổ, bu-lông mặt ghép, nắp ổ + phớt, nắp thăm + thông hơi, mắt dầu, nút xả, tai cẩu, chân đế | số răng (đếm), module từ đỉnh răng, **a = m(z1+z2)/2**, **tỷ số truyền** (±3 %) |
| Xi lanh khí nén / thủy lực | ISO 15552 (TG, Ø cần, ren KK), thủy lực tỷ lệ ISO 6020-2 | nòng, nắp vát góc + gờ lồng + đệm cuối hành trình, 4 thanh giằng + 8 đai ốc, piston 2 vòng kín + nam châm, cần mạ crôm + đai ốc, cổng + đầu nối, vít giảm chấn | Ø nòng, Ø cần, TG, **hành trình** (khoảng piston chạy giữa hai đệm), vị trí theo trạng thái |
| Van bi DN15–200 | EN 1092-1 PN16 (mặt bích), ASME B16.10 Class 150 ngắn (mặt–mặt) | thân 2 mảnh + bu-lông, bi toàn lỗ + rãnh ngàm, 2 đệm PTFE ôm bi, trục + nắp ép gioăng, tay gạt bọc nhựa | mặt–mặt, lỗ = DN, D/K/số lỗ bích, tay gạt & lỗ bi đúng trạng thái |
| Co 90°/45°, tê đều, mối nối mặt bích | ASME B16.9 (tâm–mặt), EN 10220/ISO 4200 (OD, SCH 40), EN 1092-1 PN16 | ống hàn hai đầu + mối hàn, mặt bích cổ hàn + gờ nổi + gioăng + bu-lông/đai ốc/vòng đệm | OD, A/B/C, D/K/số lỗ |
| Bộ truyền đai GT2/HTD 5M, đai thang SPZ/SPA | Gates PowerGrip (bước, PLD, răng), ISO 4183/4184 | puly răng có gờ + vít hãm, đai có răng ăn đúng rãnh, động cơ NEMA + tấm đỡ chữ L + gối UCF | Ø đỉnh puly, số răng (đếm), tỷ số, khoảng cách tâm (±½ bước vì đai số răng nguyên) |
| Bộ truyền xích 06B–16B | ISO 606 dãy B (bước, Ø con lăn, rộng trong, chốt, má) | đĩa xích chỗ ngồi r_i,min = 0,505·d1, vát răng, mắt trong/ngoài, nhánh căng + nhánh chùng võng, số mắt chẵn | số răng (đếm), số mắt chẵn, bước đo giữa tâm con lăn, khoảng cách tâm (±½ bước) |
| Khớp nối vấu / cứng | KTR ROTEX (OD, dài, lỗ max); khớp cứng kiểu Ruland | 2 moay-ơ 3 vấu + đệm sao PU 6 cánh + vít hãm; ống kẹp xẻ rãnh + vít kẹp | Ø trục, lỗ moay-ơ, OD theo cỡ |
| Vít me bi SFU + gối BK/BF | TBI Motion SFU (DIN 69051 kiểu B), THK/HIWIN BK/BF | rãnh bi xoắn cung tròn, đầu trục gia công bậc + then + rãnh phanh, đai ốc mặt bích 6 lỗ + vát phẳng, ống hồi bi, phớt gạt, vú mỡ, đai ốc khóa | Ø vít, **bước vít** (dò gờ ren), dài trục, Ø bích đai ốc |
| Ray trượt HGR15–30 / MGN7–15 | catalogue HIWIN (HG, MG) | ray 4 rãnh bi + lỗ bậc bước P, vít, con trượt thép + nắp hồi bi + phớt + vú mỡ + lỗ ren | rộng/cao ray, bước lỗ P, rộng con trượt, cao lắp H |
| Lò xo nén/kéo/xoắn | EN 13906-1 / Shigley (L0 = n·p + 2d mài phẳng…) | dây quét theo xoắn ốc thật, đầu mài phẳng/khép kín/hở, móc tròn kiểu máy, chân thẳng | OD, Ø dây, L0, **bước**, **số vòng** (đếm vết cắt nửa mặt phẳng) |

**Nhóm "robotics" — robot và tự động hóa** (luôn kèm cảnh báo an toàn):

| Mẫu | Nguồn tỷ lệ | Chi tiết dựng | Kiểm tra đo trong quality |
|---|---|---|---|
| Cánh tay robot 6 trục (cobot kiểu UR / công nghiệp sơn cam kiểu KUKA) | DH của UR5 (d1 89,2; a2 425; a3 392; d4 109,3; d5 94,75; d6 82,5 mm @ tầm với 850) co giãn theo tầm với; mặt bích ISO 9409-1 chọn theo tải | động học thuận thật (J1…J6, tư thế ready/upright/reach/pick hoặc góc từng khớp), cụm servo = mẫu actuator của robot người, ống/khâu đúc, động cơ servo ngoài (kiểu công nghiệp), cáp dụng cụ có kẹp, đế 4 bu-lông + đầu nối + cáp nguồn, kẹp 2 ngón hoặc giác hút | a2, a3 (PCA ống), 6 khớp quay, ISO 9409-1: số lỗ trên vòng + lỗ định tâm |
| Robot hút bụi | Roborock S7 (Ø353 × 96,5 mm) | khung gầm + nắp trên vỏ mỏng, cản trước, tháp LDS, 2 bánh chủ động có tay treo lò xo, bánh xoay, chổi chính cao su + khung chắn, chổi cạnh, khay bụi + lọc, 6 cảm biến chống rơi, tiếp điểm sạc, nút + vòng đèn, tấm lau, đế sạc | Ø thân, chiều cao ≤ 0,31·D, bánh đối xứng, số cảm biến chống rơi (đếm), LiDAR cao nhất, bánh chạm đất |
| AGV kho / robot giao hàng | Kiva Drive Unit (760 × 640 × 300 mm), máy quét an toàn kiểu SICK nanoScan3 | khung thép hàn + giá động cơ, vỏ, vi sai (2 bánh PU + động cơ hộp số + 4 bánh xoay trong hốc) hoặc 4 bánh mecanum 10 con lăn 45°, đầu nâng kệ xoay hoặc thùng hàng có nắp + màn hình, 2 máy quét laser, camera 3D, camera mã sàn, dải đèn, 2 nút E-stop, cản cao su, pin tháo bên | dài/rộng, số bánh theo kiểu dẫn động, số con lăn mecanum (đếm), số nấm E-stop (đếm), 2 máy quét, đầu nâng/thùng ở trên cùng, bánh chạm đất |

"AGV/AMR" trước đây thuộc nhóm xe tự hành, nay là mẫu AGV riêng; "xe tự hành", "xe robot", "rover" vẫn là xe tự hành.

**Nhóm "vehicles" — phương tiện & hàng không vũ trụ** (luôn kèm cảnh báo an toàn; chỉ để hình dung, không dùng chế tạo):

| Mẫu | Nguồn tỷ lệ / chuẩn | Chi tiết dựng | Kiểm tra đo trong quality |
|---|---|---|---|
| Máy bay cánh bằng: hạng nhẹ 4 chỗ / UAV cánh cố định / VTOL (quadplane) | tỷ lệ PA-28/DA40; NACA 2412 (máy bay nhẹ), 4412 (UAV); FAR 23.925 | thân loft siêu elip, buồng lái khoét + kính bọt vỏ mỏng + ghế/bảng đồng hồ, cánh loft NACA thuôn + xoắn giảm góc 3° + nhị diện, aileron/elevator/rudder tách riêng có khe + chốt bản lề, đuôi thường / chữ T / chữ V (ruddervator), nắp động cơ + ống xả, cánh quạt loft xoắn, càng ba điểm (ốp bánh) hoặc càng trượt; VTOL: 2 dầm + 4 motor/cánh quạt nâng quay xen kẽ | sải cánh chiếu, góc nhị diện, t/c biên dạng (dò tia), số lá (đếm ở 0,7R), khoảng hở cánh quạt–đất ≥ 229 mm, đủ cánh lái, 4 rotor/2 dầm (VTOL) |
| Ô tô điện sedan / SUV / hatchback | tỷ lệ Model 3 / VF 6–8; lốp ISO 4000 (235/45R18 → Ø669) | thân unibody vỏ rỗng 22 mm (loft trong/ngoài giải tích, bo góc Chaikin), hốc bánh + ốp lòng dè, kính chắn gió/mái/hông/hậu và đèn LED là lớp mỏng trong hốc lõm (không mặt trùng), 4 cửa tách rời (khe 4 mm, bản lề, tay nắm, gương), capô, cốp/cửa hậu, nội thất, pin sàn + cáp cao áp, 1–2 motor + bán trục, hệ treo (cam lái, càng A, giảm chấn + lò xo lên tháp), đĩa + heo phanh | dài/rộng/cao, cơ sở, vệt bánh, Ø lốp, 4 cửa, 4 heo phanh (đếm), số motor, pin dưới sàn giữa hai trục |
| Xe hai bánh: mô tô côn tay / tay ga / xe đạp điện | lốp 110/70-17, 16", ETRTO 40-622; hình học lái caster/offset/trail | khung ống, phuộc song song trục lái + ghi-đông + đèn + gương, bánh + đĩa phanh / nan hoa + motor hub, càng sau + giảm xóc, động cơ xi lanh có cánh tản nhiệt + ống xả + xích (mô tô), động cơ liền càng + CVT + vỏ nhựa (tay ga), pin + đùi đĩa + xích + baga (xe đạp điện) | cơ sở, Ø lốp trước/sau, góc caster đo trên phuộc, trail > 0, chiều cao yên |
| Máy xúc bánh xích mini / 20 t / 45 t | tỷ lệ CAT 320 / PC200 | gầm xích (bánh dẫn, bánh sao răng, con lăn, xích guốc có vấu), thân trên quay swing, cabin kính, đối trọng đuôi tròn, cần cong + tay gầu + gầu răng + thanh nối, 4 xi lanh; tư thế đào / di chuyển / vươn xa, gầu luôn trên đất | khoảng cách tâm xích, bề rộng guốc, cần & tay gầu chốt–chốt, bán kính quay đuôi, **xi lanh đúng chốt + trong hành trình** |
| Xe nâng đối trọng 1–5 t điện/dầu | ISO 2331 (càng), ISO 2328 (giá càng cấp I–IV), ISO 6055 (khung bảo vệ) | khung + hốc bánh + đối trọng gang, ắc quy/động cơ, khung nâng 2 hoặc 3 tầng (tự thêm khi nâng cao) trụ C + con lăn, giá càng + tấm chắn tải + xích, 2 càng, xi lanh nâng + 2 xi lanh nghiêng, mái bảo vệ | tiết diện càng, chiều dài lưỡi, cao độ càng, chiều cao giá càng, số tầng khung nâng, xi lanh đúng chốt/hành trình |
| Xe cẩu cần ống lồng 2–4 trục | lốp 385/65R22.5; EN 13000 (thuật ngữ) | xe cơ sở + cabin kính, 4 chân chống + đế tì đất, bàn quay + đối trọng + tời + cabin điều khiển, cần ống lồng 4–6 đoạn rỗng (tự chọn để đoạn chồng ≥ 1 m) + tấm trượt PTFE + puly đầu cần, xi lanh nâng cần (vỏ cố định theo dải 0–80°), cáp 2 nhánh + cụm móc | chiều dài cần chốt → tâm puly, góc cần, đoạn chồng ≥ 1 m, 4 chân chống + bánh chạm đất, cáp thẳng đứng, xi lanh đúng chốt/hành trình |
| Tàu hỏa / tàu điện + 0–4 toa | khổ 1000/1435, ray P43/UIC 60, móc nối AAR, tỷ lệ D19E | đường ray + tà vẹt + ba lát, bộ trục bánh côn 1:20 + gờ, bogie 2 trục + lò xo + đệm khí, thân vỏ + kính chắn gió dốc, cần lấy điện + dây tiếp xúc (tàu điện) | khổ đường (dò tia nấm ray), số bộ trục bánh, bogie, móc nối |
| CubeSat 1U–12U | CubeSat Design Specification rev.14 (1U = 100 × 100 × 113,5) | khung 4 ray góc, tấm pin, cánh pin mở, ăng-ten, chồng bo PC/104, camera | X/Y/Z theo U, 4 ray, bề rộng ray |
| Tên lửa 2–3 tầng | tỷ lệ Falcon 9 | tầng + bồn + vòng gân, 9 động cơ tầng 1, vòng nối tầng + cánh lưới, động cơ chân không, chóp ogive 2 nửa, vệ tinh; tách theo đúng trình tự bay | chiều cao, Ø thân, số tầng, 9 vòi phun (đếm), 2 nửa chóp |

**Nhóm "energy" — năng lượng & công trình** (công trình/thiết bị năng lượng luôn kèm cảnh báo; chưa tính kết cấu, móng,
tải gió/động đất):

| Mẫu | Nguồn tỷ lệ / chuẩn | Chi tiết dựng | Kiểm tra đo trong quality |
|---|---|---|---|
| Giàn thép mái Pratt / Howe / Warren / Fink | thép góc đều cạnh TCVN 1656 / EN 10056-1, bu-lông 8.8 | **bộ dựng giàn dùng chung** (`structures.PlanarTruss`): thanh 2L kẹp bản mã, đầu thanh bụng tự cắt lùi bằng phép thử giao diện tích 2D tới khi không lấn thanh khác, bản mã = bao lồi vùng bu-lông (mép ≥ 1,5d) cắt theo gót thanh cánh, bu-lông xuyên lỗ khoan cục bộ, cách nhau ≥ 2,5d, không chạm cánh ngang; cột H + bản đế + bu-lông neo + móng | nhịp tâm cột, chiều cao giàn, cạnh/dày thép góc + khe bản mã (dò tia), số bản mã, ≥ 4 bu-lông mỗi bản mã, tổng bu-lông |
| Cầu giàn thép / dây văng / vòm | TCVN 11823 (chưa kiểm toán) | giàn Pratt chạy dưới 2 mặt (bộ dựng giàn, 2L200×20, M24) + thanh chống đỉnh (tĩnh không ≥ 4,75 m), dầm ngang I900 + dầm dọc + bản 250 + gờ + lan can, gối cao su, mố; dây văng: 2 tháp chữ H, dây bán rẻ quạt không cắt nhau, dầm hộp biên; vòm: sườn hộp parabol f = L/6, dây treo, giằng gió trên tĩnh không 6 m | nhịp (tâm gối / tâm tháp), bề rộng mặt đường, chiều cao giàn, tĩnh không, số dây văng + đối xứng, đường tên vòm, dây treo thẳng đứng |
| Tháp thép: cột điện mạch kép / tháp viễn thông 4 hoặc 3 chân | thép góc mạ kẽm, tỷ lệ tuyến 110 kV | chân thép góc loft (cánh nằm đúng mặt tháp nghiêng), giằng chữ X áp ngoài cánh chân + bản đệm, thanh ngang, bu-lông theo pháp tuyến thật của mặt nghiêng; xà dàn 3 tầng + chuỗi 10 bát thủy tinh + dây dẫn; viễn thông: sàn, 6 ăng-ten 3 hướng, 2 chảo viba, kim thu sét + đèn báo không; 3 chân: ống thép hàn | chiều cao, số chân + bề rộng chân tại móng, bát cách điện (đếm), ăng-ten/chảo (đếm), bu-lông (đếm) |
| Tuabin gió trục ngang | tỷ lệ Vestas V90-2 MW, IEC 61400-1 | móng, tháp côn 3 đoạn + cửa, ổ quay hướng răng trong + 4 động cơ, bệ máy, trục chính + ổ, hộp số hành tinh, máy phát + biến tần, vỏ nacelle mở nắp được, moay-ơ + ổ đổi bước + chóp, 3 cánh loft NACA 44xx xoắn 13° → 0°, ngẩng 5°, côn 2° | Ø rotor, chiều cao tâm rotor, độ xoắn cánh (đo tại trạm mặt cắt), Ø chân/đỉnh tháp, khe hở mũi cánh – tháp ≥ 0,1 R |
| Hệ điện mặt trời | tấm 400 Wp 1722 × 1134 × 30 (IEC 61215/61730) | tấm: khung nhôm, 108 cell nửa + khe, busbar, kính AR, hộp nối + MC4; giá C mạ kẽm (cột, xà nghiêng, xà gồ, chống), kẹp giữa/biên, móng; biến tần + tủ AC/DC + ống cáp | kích thước tấm, góc nghiêng (PCA), hướng Nam, mép dưới ≥ 500 mm, khoảng cách hàng tránh bóng (mặt trời 45°) |
| Máy phát điện diesel 10–1000 kVA | ISO 8528 | khung đế + bồn dầu, đệm chống rung, động cơ (nắp gân, tăng áp, lọc gió, két nước + quạt + lưới), đầu phát + chuông bánh đà đồng trục, tủ điều khiển + dừng khẩn, ắc quy, ống xả + bô; vỏ cách âm có cửa gió lá chớp + 4 cửa hông | chiều dài khung, đầu phát đồng trục chuông, đệm chống rung (đếm), két nước phía trước, ống xả lên trên mái |
| Máy bơm ly tâm EN 733 | EN 733 / DIN 24255, EN 1092-1 PN16, IEC 60072 | vỏ xoắn loft + buồng cánh rỗng, cánh bơm kín 6 lá, nắp + giá đỡ ổ, trục + phớt, khớp nối + chụp, động cơ IEC (cánh tản nhiệt, hộp đấu dây), đế + đệm căn | 2 mặt bích (D, K, số lỗ), trục bơm – động cơ đồng tâm, h1, chiều cao tâm trục IEC H, Ø cánh bơm |
| Bồn chứa đứng / nằm | kiểu API 650 (khoang 2 m, mái côn 1:6/vòm); đáy elip 2:1 + yên Zick | vỏ + đáy + thép góc, mái, vòi DN + mặt bích PN16 + van bi, cửa người chui DN600, thang có lồng (ISO 14122-4) + sàn đỉnh, ống thở, thước mức; bồn nằm: yên + bệ | **dung tích đo** (bán kính trong × chiều cao / trụ + 2 đáy), bậc thang, lồng khi leo > 3 m, van (đếm) |

Nhận dạng câu: "cầu" (cây cầu) / "cẩu" (xe cẩu) phân xử theo dấu; "cầu sau/cầu thang/cầu dao…" không phải cầu; "máy
phát điện gió" là tuabin gió, "máy phát điện năng lượng mặt trời" là hệ điện mặt trời; "tháp" chung là tháp thép.

Hiệu năng: `Solid.to_mesh` tính pháp tuyến theo từng mảnh rời khi khối có nhiều mảnh (bu-lông cả giàn: 19 s → < 1 s);
bu-lông kết cấu dùng mẫu nhẹ (`structures.light_bolt`) + nướng lưới mẫu một lần rồi tịnh tiến.

**Nhóm "fabrication" — máy chế tạo & điện tử** (2026-09-27; test `tests/test_three_d_fabrication.py`, 63 câu benchmark):

| Mẫu | Nguồn tỷ lệ / chuẩn | Chi tiết dựng | Kiểm tra đo trong quality |
|---|---|---|---|
| Máy in 3D FDM kiểu i3 (bàn trượt Y) / CoreXY | nhôm định hình 2020/2040, ray MGN, NEMA 17, đai GT2 | khung, ray + con trượt 3 trục, bàn nhiệt + tấm in, đai + puly + động cơ, vít me Z, hotend, nguồn, bo điều khiển; CoreXY: tấm góc + puly dẫn | tấm in phủ vùng in, khe mũi phun – tấm in ở gốc Z, mũi phun trên vùng in, bàn hạ đủ Z, chiều dài ray |
| Máy CNC router 3 trục (3040…1325) | vít me bi SFU1605/2005 + gối BK/BF, ray HGR, NEMA 23, khớp nối jaw | bàn rãnh T, gantry dẫn động kép trục Y, vít me + đai ốc bi + tai gá mỗi trục, spindle + đai ốc kẹp + dao phay rãnh xoắn, nút dừng khẩn | kích thước bàn, dao chạm được mặt bàn, khe dưới dầm > hành trình Z, Ø spindle/dao, chiều dài vít me X/Y/Z, ray đủ hành trình |
| Tủ rack 19" 6–48U | EIA-310 (1U = 44,45; lỗ vuông 9,5; tâm lỗ 465,1; mặt 482,6) | khung, 4 ray đục lỗ, cửa trước/sau, tấm hông, 2 quạt nóc, bánh xe, thiết bị 1–2U | số lỗ vuông, bước 1U, lọt lòng giữa ray, khoảng tâm lỗ, mặt thiết bị 482,6 |
| Tủ điện (vỏ thép) | ray DIN TH35 (EN 60715), mô-đun 17,5 (DIN 43880) | thân + cửa (có thể cửa kính), tấm lắp, ray DIN, aptomat tép, máng cáp (rộng ≥ 400), ốc siết cáp đáy | kích thước tủ, cửa ở mặt trước, TH35 35 × 7,5, bước mô-đun, ốc siết cáp ở đáy |
| Quạt hướng trục 40–140 mm | khoảng tâm lỗ vít theo cỡ quạt PC | khung + 4 lỗ, rotor + lá cánh cong, cáp, lưới bảo vệ | cạnh khung, bề dày, tâm lỗ vít, số lá, khe hở đầu lá |
| Tản nhiệt tháp ống đồng / nhôm đùn | — | đế đồng, ống dẫn nhiệt chữ U xuyên lá, chồng lá nhôm; nhôm đùn: đế + lá liền khối; quạt kẹp | số lá, bước lá, bề dày lá, số nhánh ống xuyên lá, Ø ống |
| Bo mạch Arduino Uno / Raspberry Pi | kích thước + tọa độ lỗ theo bản vẽ hãng | PCB, chip, header 2,54, cổng USB/HDMI/Ethernet | dài/rộng/dày bo, 4 lỗ đúng tọa độ, số chân + bước header |

Chuyển động: con trượt các trục máy in/CNC đi qua lại trên ray, không rời ray và mũi phun/dao không ăn xuống bàn (test quét
60 s); đai ốc bi đi theo con trượt còn vít me quay; dao quay theo đai ốc kẹp; cửa tủ rack/tủ điện mở ra ngoài quanh bản lề;
hai quạt nóc tủ rack quay quanh trục riêng. Nhận dạng câu: "tản nhiệt tháp" là tản nhiệt (không phải tháp thép), "thanh
răng rack" là bánh răng, "từ điển" không phải tủ điện; mã CNC 4 chữ số: "6040" → 600 × 400, "1325" → 1300 × 2500 (giới
hạn 1500). Vít me bi dài tự giảm độ chia lưới để giữ tổng ≤ 450k tam giác (CNC hành trình tối đa ≈ 340k).

Nhận dạng câu: "tàu hỏa/tàu điện/đầu máy/toa" là tàu hỏa (không phải thuyền); "máy bay không người lái" vẫn là UAV đa rotor,
"máy bay trực thăng" vẫn là trực thăng, "UAV cánh cố định/VTOL" và "máy bay" chung là máy bay cánh bằng; "xe máy" là xe hai
bánh (khác "máy xúc"); câu có dấu chỉ có "cầu" (cây cầu) không bị hiểu là "cẩu".

Tham số bắt buộc duy nhất của nhóm: **mã ổ bi** ("Tạo ổ bi" → hỏi "cỡ nào ạ (6204, 6000, 6305)?"). Thông số trái chuẩn bị
từ chối có lý do (xi lanh khí nén Ø45 không có trong ISO 15552; hộp 2 cấp tỷ số > 60; khoảng cách tâm đai nhỏ hơn chỗ lắp
động cơ). Nhận dạng câu dùng tầng ưu tiên + vị trí khớp sớm nhất ("hộp số có ổ bi" là hộp số; "bánh răng có 90 răng"
vẫn là bánh răng; "mặt bích Ø120" vẫn là mặt bích đơn, "mặt bích DN65" là mối nối ống). "dừng …" (có dấu), câu hỏi
("… như thế nào", "vẽ sơ đồ …") không bị hiểu là lệnh tạo mô hình.

**Vật liệu PBR có texture thật**: kim loại chải xước, sơn (vân vỏ cam), cao su hạt, nhựa nhám, tấm gân — normal map thủ
tục lặp liền mạch, UV chiếu hộp theo kích thước thật (mm/lần lặp); viewer gửi tangent/binormal nên normal map hiển thị đúng
(trước đây normal map, kể cả vân carbon, không có tangent).

**Không xuyên nhau / không lơ lửng**: quét giao khối mọi cặp bộ phận đã tìm và sửa lỗi có từ trước — pin UAV lấn vỏ trên
(1.138 mm³), bo mạch chạm vỏ, ăng-ten chạm pin/tay đòn, pin dưới đè camera dưới, pin trên/dưới lơ lửng, kính trực thăng
và kính mặt robot trùng mặt (nhiễu sọc). Các cặp quan trọng được khai báo `no_clash_with` để quality gate tự bắt.

### Ren
- **technical** (mặc định): hình học helix thật, biên dạng cơ bản ISO 68-1 (60°, đỉnh P/8, chân P/4), thoát ren, vát 45°
  đầu ren. Quality gate đo bước ren và lệch pha helix trên lưới thật.
- **illustrative** ("ren minh họa"): trụ + normal map ren — KHÔNG đánh dấu là mô hình kỹ thuật (`technical_thread = false`).
- Chân ren phẳng cơ bản, chưa bo R chân ren như ren thật cán/cắt.

## 3. Chất lượng

Thang 100: **30** hình dáng & tỷ lệ (70% kiểm tra hình học + 30% Gemini chấm ảnh 6 góc) · **25** đủ linh kiện (checklist do
mã tính) · **20** kích thước & vị trí lắp (đo trên lưới, va chạm bằng giao khối, tiếp đất, không lơ lửng) · **15**
lưới/topology (hữu hạn, pháp tuyến, suy biến, kín, lỗ từ render, faceting, ngân sách) · **10** vật liệu (30% AI).

Đạt khi: tổng ≥ `quality_threshold` (90), không thiếu bộ phận bắt buộc, không lỗi hình học nghiêm trọng, không lỗi
asset/đường dẫn, không sai kích thước bắt buộc, manifest hợp lệ. Không có AI chấm ảnh: mô hình tham số dùng điểm
deterministic; mô hình cloud/DSL bị trống 30% phần AI nên không thể đạt ngưỡng.

Mô hình không đạt: lưu với trạng thái "chưa đạt", job báo "Mô hình chưa đạt tiêu chuẩn …" kèm lý do, không mở như kết quả
hoàn chỉnh; nói "mở mô hình vừa tạo" để xem bản chưa đạt (có nhãn CHƯA ĐẠT).

Metadata mỗi dự án: `conceptual`, `dimensionally_specified`, `geometry_validated`, `manufacturing_unverified` (luôn true),
`assembly_confidence`, `segmentation_confidence`, `quality_score`, `technical_thread`, `ai_review_used`.

**Benchmark 2026-09-27 (thêm nhóm fabrication)**: 743 câu, 12 nhóm → spec khớp 743/743, điểm trung bình 100;
fabrication 63/63 đạt gate (p50 19 s, p95 62 s khi 6 luồng). 6 câu rover/humanoid báo timeout do máy ngủ giữa chừng
(≈ 10.450 s/câu); chạy lại riêng hai nhóm → 120/120.

**Benchmark trước (2026-09-25 23:48, sau nâng cấp chi tiết + nhóm thuyền)**: 421 câu, 7 nhóm (60–61 câu/nhóm) →
421/421 đạt gate, spec khớp 421/421, điểm trung bình 100. Thời gian một mô hình (chạy riêng, sau khi render 6 góc song
song): UAV 4,4 s · robot người 6,4 s · thuyền 6,5 s · xe tự hành 10,9 s.

**Benchmark**: `scripts/bench_3d_quality.py` chạy 361 câu (≥ 60 câu/nhóm, `nexa/three_d/benchmark.py`). Tỷ lệ đạt =
số mô hình vượt quality gate / tổng số yêu cầu. Kết quả đo được là tỷ lệ **đạt quality gate tự động**, KHÔNG phải tỷ lệ
"giống vật thể thật 90%" — việc đó cần người đánh giá; NEXA không tuyên bố con số đó.

Kết quả đo ngày 2026-09-25 (`results/3d_benchmark_local.json`, CAD cục bộ, không Gemini, không người chấm): 361/361
đạt gate, spec khớp 361/361, điểm trung bình 100, mỗi nhóm 60–61 câu; thời gian p50/p95 khi chạy 4 luồng song song:
cơ khí 3,0/6,9 s, UAV/robot/trực thăng ≈ 7/8 s. Bộ câu do nhóm phát triển tự viết, nên con số này cho thấy parser và mẫu
tham số ổn định; nó không đo được độ đẹp hay độ giống ý người dùng. Chạy thử với Gemini thật (planner + chấm 6 góc):
bu-lông M8×30 được 99/100; UAV 6 cánh «thân màu trắng» được 99,2/100 sau khi sửa lỗi Gemini chỉ ra (khung vẫn đen carbon).

**Mức 2, chạy thật với Gemini gói miễn phí** (2026-09-25, `scripts/run_3d_prompts.py`, `results/l2_v3/`): 10 vật thể
không có trong ví dụ mẫu (ghế, tai nghe, đèn bàn, chai nước, ấm siêu tốc, bàn phím, chậu xương rồng, ô dù, tạ tay, loa) →
9/10 tạo được, 18–182 s/vật. 7 vật được Gemini chấm ảnh: 94,6 · 88,2 · 95,9 · 95,9 · 94,6 · 80,6 · 92,8. Ba vật cuối đợt gặp
Gemini hết hạn mức/504: bàn phím 57,5 và ô dù 59,0 (không có người chấm → điểm thấp theo thiết kế); chậu cây thất bại (Gemini
504, chuyển sang HF nhưng hạn mức GPU ẩn danh đã cạn). Trước khi sửa, mức 2 là 0/5 (lỗi schema). Đây là thử nghiệm nhỏ do
nhóm phát triển tự chọn câu, không phải benchmark có người chấm.

**Hiệu năng** (RTX 4050 laptop, cửa sổ 1280×800, `scripts/smoke_3d_viewer.py <mẫu> --window --perf`): nạp UAV 25 bộ phận /
95,7k tam giác 266–282 ms, rover 152,8k tam giác 328 ms; 62,5 FPS (giới hạn vsync) cả khi đang xoay; CPU tiến trình 1–2 %
khi nhàn rỗi, ~2 % khi xoay bằng cử chỉ 30 Hz; RAM ≈ 240–250 MB (chưa gồm camera/ASR); xử lý một khung cử chỉ p50 0,3 ms,
p95 0,6 ms (chưa gồm thời gian chụp camera và MediaPipe — chưa đo trên camera thật).

## 4. Trình xem 3D

Qt Quick 3D: View3D, PerspectiveCamera orbit (nội suy mượt ở tốc độ khung hình), ánh sáng studio (3 đèn + light probe
`assets/3d/studio.hdr` sinh bằng `scripts/generate_studio_hdr.py`), PBR (metalness/roughness/normal/clearcoat), bóng đổ, sàn
và lưới, auto-frame theo bounds, chọn bộ phận bằng nhấp (pick), nhấp đúp = xem chi tiết, cây bộ phận (ẩn/hiện), thẻ thông
tin (tên, kích thước, vật liệu, chức năng), exploded view theo thứ tự tháo (animation có so le theo bước), X-quang, khung
dây, đặt lại góc nhìn, LOD khi vượt `viewer_triangle_budget`, cảnh báo asset lỗi. Lưới từng bộ phận nạp ở luồng nền.

Chuột: kéo = xoay, lăn = thu phóng, Esc = đóng. Mặt cắt chưa làm.

### Chuyển động (2026-09-26)

`motion.py` suy ra chuyển động cơ bản cho cả 44 nhóm từ tên/kích thước bộ phận: cánh quạt/rotor quay (hai cặp cánh UAV
ngược chiều), bánh xe lăn, bánh răng ăn khớp (quay ngược chiều, tốc độ theo tỷ số bán kính), cánh tay robot/máy xúc/cần cẩu
lắc theo chuỗi khớp (khớp sau mang theo chuyển động khớp trước), xi lanh/vít me/ray trượt tịnh tiến, robot người/chó bước
đi. Nhóm tĩnh (ốc vít, mặt bích, giá đỡ, cầu, giàn, bồn…) dùng chế độ **turntable** (xoay trưng bày). Chuỗi chuyển động
tính ở Python (`motion_mode` = `parts` | `turntable`), QML ghép chuỗi mỗi khung (`motionXf`), bật/tắt có tăng/giảm tốc
mượt. Nút "Chuyển động" trên viewer; kết hợp được với exploded view.

Bật/tắt: nút trên viewer, câu lệnh giọng nói, hoặc **búng tay** (mic và camera) — chỉ khi viewer đang mở; viewer đóng thì
búng tay không làm gì, vỗ tay đánh thức vẫn như cũ.

- Mic (`nexa/audio/snap_detector.py`): tiếng búng ngắn, năng lượng dồn ở dải cao (~2–4 kHz), khác tiếng vỗ tay (dải thấp
  hơn, tắt chậm hơn). Chạy song song ClapDetector; khi viewer mở, sự kiện vỗ tay được giữ 0,15 s và bị bỏ nếu nằm trong
  0,35 s quanh một tiếng búng → một cú búng không đánh thức nhầm. Bỏ qua nếu vừa gõ phím/nhấp chuột < 0,4 s.
- Camera (VIEWER_3D): dáng "chuẩn bị búng" (đầu ngón cái chạm đầu ngón giữa, ngón áp út/út co) giữ ≥ 90 ms rồi trong
  0,4 s chuyển sang dáng "vừa búng" (ngón giữa gập vào lòng, ngón cái bật ra) → bật/tắt một lần, cooldown 0,9 s. Là đặc
  trưng bàn tay riêng (`snap_ready`/`snap_released`), không phải tư thế mới nên sáu cử chỉ hệ thống không đổi.

## 5. Giọng nói

Tạo: "Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm", "Tạo robot hình chó, mỗi chân có ba khớp", "… bằng cloud",
"… chất lượng cao". Tiến độ: "mô hình tạo xong chưa". Hủy: "hủy tạo mô hình" (hoặc "hủy"/"dừng lại").
Mở: "mở mô hình vừa tạo". Khi viewer mở: "xem chi tiết cánh quạt trước trái", "phóng to motor phía sau bên phải",
"ẩn lớp vỏ", "tách riêng cụm camera", "xem khớp đầu gối chân phải", "cho tôi xem rotor chính", "quay bộ phận này 90 độ",
"đưa bộ phận này về vị trí lắp", "hiện lại toàn bộ", "tách các bộ phận ra", "lắp mô hình lại", "đặt lại góc nhìn",
"quay sang trái 30 độ", "chế độ x quang", "khung dây", "đóng trình xem 3D",
"cho mô hình chuyển động", "mô phỏng hoạt động", "chạy thử mô hình", "dừng chuyển động" (công cụ `set_3d_motion`). Câu phức tạp → Gemini gọi cùng công cụ.
Tên mơ hồ: "UAV có bốn cánh quạt. Anh muốn xem cánh quạt trước trái, sau trái, sau phải, trước phải hay xem cả cụm?" —
anh trả lời "trước trái" là đủ. Alias: cánh/cánh quạt/propeller/prop/rotor/chong chóng…

## 6. Cử chỉ (chế độ VIEWER_3D)

Khi viewer mở và camera cử chỉ bật: chuột bằng tay và sáu cử chỉ hệ thống **tạm ngưng**, cử chỉ chỉ điều khiển viewer.
Đóng viewer → về sáu cử chỉ, chuột bằng tay vẫn tắt (an toàn). Dừng khẩn cấp → khóa tương tác, hủy job.

| Động tác | Kết quả |
|---|---|
| Đưa bàn tay mở vào, giữ yên ~0,2 s | "Sẵn sàng xoay" (ghi điểm neo, bỏ qua chuyển động đưa tay vào) |
| Di chuyển bàn tay mở | Xoay yaw/pitch (One Euro, deadzone, clamp pitch ±85°, quán tính nhẹ) |
| Nắm tay giữ yên 0,5 s | "Đang chuẩn bị tách…" (thanh tiến trình) |
| … rồi mở tay giữ yên 0,35 s | Tách assembly đúng một lần; sau animation bàn tay mở xoay tiếp |
| Nắm tay giữ yên khi đang tách | Lắp lại |
| Hai ngón đưa lên/xuống | Phóng to/thu nhỏ |
| Búng tay (ngón cái – ngón giữa) | Bật/tắt chuyển động mô hình |

Mở tay nhưng di chuyển nhanh → không tách. Nắm tay ngắn → không gì. Mất tay → dừng ngay, xuất hiện lại lấy neo mới.
Có cooldown sau tách/lắp. Sự kiện xoay theo từng khung camera (~30 Hz), không qua gesture_status 10 Hz.

## 7. Cấu hình (`three_d` trong settings.yaml; Cài đặt > Mô hình 3D)

`enabled`, `default_mode`, `provider`, `cache_dir`, `cache_size_mb`, `keep_generated_assets`, `max_asset_mb`,
`max_triangles`, `max_texture_size`, `candidate_count`, `refinement_rounds`, `quality_threshold`, `generation_timeout_s`,
`max_cost_per_job`, `ai_review`, `use_gemini_planner`, `reference_images`, `reference_image_model`, `cloud_segmentation`,
`tripo_model_version`, `meshy_ai_model`, `dsl_models`, `dsl_thinking`, `dsl_timeout_s`, `dsl_max_tokens`,
`dsl_repair_rounds`, `dsl_refine_rounds`, `dsl_fallback_below`, `hf_enabled`, `hf_image_space`, `hf_3d_spaces`,
`hf_timeout_s`, `hf_image_timeout_s`, `hf_space_timeout_s`, `hf_expected_s`,
`open_viewer_when_ready`, `viewer_auto_camera`, `viewer_triangle_budget`,
`gesture.{rotate_sensitivity, rotate_deadzone, acquire_ms, fist_hold_ms, open_hold_ms, cooldown_ms, animation_ms,
arm_timeout_ms, explode_max_speed, inertia, pitch_limit_deg, zoom_two_fingers}`. Giá trị ngoài khoảng được kẹp lại
(`validate_three_d`). Búng tay: `audio.snap.{enabled, camera, sensitivity, min_level_dbfs, cooldown_ms,
calibration_seconds}` (Cài đặt > Âm thanh > Búng tay). API key chỉ trong `.env`:

```
NEXA_3D_PROVIDER=auto         # auto | tripo | meshy | hf_space | none
TRIPO_API_KEY=...
MESHY_API_KEY=...
HF_TOKEN=...                  # tùy chọn, miễn phí: tăng hạn mức GPU của Hugging Face Space
```

## 8. Dịch vụ cloud (đối chiếu tài liệu chính thức 2026-09-25)

- **Tripo API v3** (mặc định, `three_d.tripo_api: v3`): `https://openapi.tripo3d.ai/v3` — endpoint riêng `/generation/text-to-model`, `/generation/image-to-model`, `/generation/multiview-to-model`, `/mesh/segment`, `/files`, `/tasks/{id}`, `/account/balance`; mặc định texture HD + hình học Ultra + `auto_size` (kích thước thật); "chất lượng cao" → texture 8K. Khoảng 50 credit (0,5 USD)/mô hình theo bảng giá. Key hợp lệ đã kiểm (số dư 0 credit, chưa tạo thật). Tripo hết credit/sai key khi NEXA tự chọn → tự chuyển mức 2. Mã `tcli_…` trên trang key là mã định danh, secret là `tsk_…`.

- **Tripo** API v2 `https://api.tripo3d.ai/v2/openapi`: `POST /task` (text_to_model, image_to_model, multiview_to_model
  [front, left, back, right], mesh_segmentation, highpoly_to_lowpoly, texture_model), `GET /task/{id}`, `POST /upload`.
  Không có endpoint hủy → NEXA bỏ qua kết quả đến muộn. URL kết quả hết hạn ~5 phút → tải ngay. Credit (1 USD = 100):
  text 10–20 (+10 texture, +20 detailed), segmentation 40.
- **Meshy** `https://api.meshy.ai`: text-to-3d preview → refine, image/multi-image-to-3d, remesh, retexture; hủy bằng
  DELETE (chỉ task đang chờ được hoàn credit). Asset giữ 3 ngày.
- Chi phí được giới hạn bằng `candidate_count` (chỉ chất lượng cao), `refinement_rounds`, `max_cost_per_job`, và Gemini đề
  xuất dùng cloud phải được anh xác nhận (rủi ro MEDIUM).
- **Chưa kiểm chứng trực tiếp** với API thật vì máy chưa có TRIPO_API_KEY/MESHY_API_KEY — đã kiểm bằng HTTP giả lập theo
  đúng schema tài liệu.
- **Hugging Face Space** (2026-09-25): đã chạy thật FLUX.1-schnell (ảnh 1024², ~17 s) và Hunyuan3D-2 `/shape_generation`
  (GLB 1,13 triệu tam giác, ~208 s kể cả xếp hàng) → làm sạch còn 607 nghìn tam giác, lưới kín; phát lại GLB này qua
  toàn bộ pipeline với Gemini chấm thật: 94/100. TRELLIS báo hết hạn mức GPU ẩn danh; một lượt pipeline trực tiếp sau đó
  hết giờ vì hạn mức ẩn danh đã cạn → cần HF_TOKEN để dùng đều.

## 9. An toàn

Không chạy mã AI sinh. Không URI ngoài trong GLB, không path traversal. Không ghi API key vào settings/log. Không tạo
G-code. UAV/robot/xe/trực thăng luôn kèm cảnh báo chưa kiểm chứng độ bền, trọng tâm, khí động học, tải trọng, vật liệu, an
toàn vận hành. Xuất STL/3MF ghi chú "chưa kiểm chứng để chế tạo".

## 10. Giới hạn đã biết

- Kernel là CSG lưới (manifold3d), không phải B-rep: chưa xuất STEP; fillet/chamfer chỉ trên profile, hộp và trụ (chưa bo
  cạnh tùy chọn trên khối bất kỳ); B-spline dùng cho đường cong profile/đường quét, không có mặt NURBS.
- Template tham số tạo hình "sản phẩm ý tưởng" có tỷ lệ hợp lý, không phải thiết kế kỹ thuật của một mẫu thật cụ thể.
- Mô hình cloud: tên bộ phận sau segmentation không có ngữ nghĩa, hướng tách ước lượng xuyên tâm (có ghi rõ).
- Mức 2 là "mô hình ý tưởng" dựng từ khối cơ bản: nhận ra được vật thể nhưng thô hơn mô hình AI hữu cơ/thiết kế tay; chất
  lượng phụ thuộc model Gemini (key miễn phí hay gặp 503 ở model mạnh → dùng model nhẹ hơn). Điểm của vật thể tự do là
  "best effort": 70% điểm hình dáng và 50% điểm vật liệu do Gemini chấm ảnh, lỗi nghiêm trọng bị trừ điểm — không phải
  người thật chấm.
- Mức 3 miễn phí phụ thuộc Space công khai (có thể ngủ, đổi API, hết hạn mức); Hunyuan3D chỉ trả hình không texture; lưới AI
  có thể méo nhẹ và là một khối (tách bộ phận chỉ khi lưới có thành phần rời).
- Key Gemini gói miễn phí có hạn mức model ảnh = 0 → ảnh tham chiếu dùng FLUX thay Gemini.
- Render kiểm tra 6 góc là renderer phần mềm (không bóng đổ/phản xạ thật).
- Offscreen (QT_QPA_PLATFORM=offscreen) không vẽ được Qt Quick 3D — kiểm thử render dùng cửa sổ ngoài vùng màn hình.
- Blender/postprocess/blender.py chưa làm (không cần cho luồng hiện tại).
- Chuyển động là minh họa động học cơ bản (không mô phỏng lực, va chạm, ràng buộc ăn khớp chính xác); bộ phận nhận diện
  theo tên nên mô hình cloud/Mức 2–3 thường chỉ xoay trưng bày.
- Búng tay rất nhẹ (dưới khoảng −37 dBFS tại mic) hoặc ở phòng ồn có thể không nhận; tăng `audio.snap.sensitivity` hoặc
  hạ `min_level_dbfs`. Búng tay qua camera cần thấy rõ bàn tay (đủ sáng, không quá nhanh so với 30 khung/giây).
# Xuất ảnh và video sản phẩm

Hồ sơ linh kiện cho toàn thư viện: xem [Linh kiện & lắp ráp](build_dossier.md). Có bảng đối chiếu từng bộ phận,
lưu mã/nguồn linh kiện và xuất hồ sơ; chưa chứng nhận thiết kế đủ điều kiện chế tạo.

Trong trình xem mô hình, chọn **SẢN PHẨM → Ảnh & video**:

- Xuất ảnh PNG hoặc video MP4 xoay một vòng 360°, 24 hình/giây.
- Chọn kích thước vuông 512, 768 hoặc 1024 px; nền studio sáng/tối; góc 3/4, chính diện hoặc bên.
- Video dài 3, 6 hoặc 10 giây. Khung hình giữ nguyên tỷ lệ trong cả vòng xoay.
- Quá trình chạy nền, có tiến độ và **Hủy xuất**. Đóng bảng vẫn tiếp tục xuất; dừng khẩn cấp hủy xuất.
- Kết quả lưu tại `Documents/NEXA 3D/Media`, tên riêng cho mỗi lần xuất; nút **Mở thư mục** dẫn tới kết quả.
- File dở bị dọn khi hủy hoặc lỗi; video được mở lại kiểm tra trước khi công bố thành công.

Bản đầu dựng lại toàn bộ asset ở trạng thái lắp ráp, không chụp giao diện và không áp dụng trạng thái ẩn/tách/
chuyển động trong trình xem. Dùng ánh sáng phần mềm cố định và texture màu cơ bản; vật liệu có thể khác Qt 3D
(chưa có normal map, HDR hoặc chỉnh đèn). PNG hỗ trợ nền trong suốt theo vùng phủ hình học; vật liệu kính chưa có
alpha theo độ truyền sáng. MP4 chỉ có nền sáng/tối. Chưa hỗ trợ gắn logo hay âm thanh.
Xuất CPU có thể chậm với lưới lớn; nên thử 512 px / 3 giây trước. MP4 dùng MPEG-4 Part 2 (`mp4v`), không phải H.264.


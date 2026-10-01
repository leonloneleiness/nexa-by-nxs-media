# Sáu cử chỉ của NEXA và cách hiệu chuẩn

Toàn bộ nhận diện chạy **cục bộ** (MediaPipe Hand Landmarker trên CPU). Không gọi Gemini cho từng khung hình hay từng
cử chỉ. Camera chỉ bật khi anh bật chế độ cử chỉ.

## Bảng cử chỉ (v1.3 — giữ tư thế, không vuốt)

Mọi lệnh là **một tư thế tĩnh, giữ yên** trong khoảng ngắn. Mỗi tư thế khác nhau ở **tập ngón duỗi** và **hướng**, nên
không thể lẫn sang nhau:

| Tư thế (giữ yên) | Ngón duỗi | Thời gian giữ | Sự kiện | Kết quả |
| --- | --- | --- | --- | --- |
| 👉 Chỉ ngón trỏ **sang phải** (ngang, ±35°) | chỉ ngón trỏ (ngón cái tùy ý) | 0,65 s | `MOVE_WINDOW_TO_MONITOR_2` | Chuyển cửa sổ hiện tại sang màn hình 2 |
| 👎 Ngón cái **chỉ xuống** (dọc, ±40°) | chỉ ngón cái | 0,65 s | `MINIMIZE_ACTIVE_WINDOW` | Thu nhỏ cửa sổ hiện tại (như nút −) |
| 👍 Ngón cái **chỉ lên** (dọc, ±40°) | chỉ ngón cái | 0,65 s | `RESTORE_LAST_MINIMIZED_WINDOW` | Khôi phục đúng cửa sổ NEXA vừa thu nhỏ |
| ✊ Nắm tay, ngón cái áp lên các ngón | không ngón nào | 0,5 s | `YOUTUBE_PAUSE` | Tạm dừng video YouTube đang gắn |
| 🖐 Xòe cả bàn tay, **ngay sau** khi nắm tay tạm dừng | cả 5 ngón | 0,5 s | `YOUTUBE_RESUME` | Phát tiếp video vừa tạm dừng |
| ✌ Hai ngón trỏ + giữa (hướng tùy ý) | trỏ + giữa | 0,65 s rồi lặp | `SCROLL_UP` | Cuộn lên liên tục (2 nấc mỗi 180 ms) tới khi đổi tư thế |

Không gán hành động (để tránh nhầm): chỉ ngón trỏ sang trái, chỉ ngón trỏ lên, ngón cái nằm ngang, bàn tay mở khi chưa
nắm tay trước đó. Nắm tay **không** dùng để tạm dừng hệ thống cử chỉ — dùng nút, giọng nói hoặc Ctrl+Alt+Esc.

### Vì sao bỏ vuốt

Bộ cũ (v1.0–v1.2) dùng vuốt bàn tay mở. Trên webcam thật nó hay trượt và lộn lệnh vì:

- tay chuyển động nhanh bị nhòe → MediaPipe mất tư thế giữa chừng → cú vuốt không được tính;
- đưa tay lên / hạ tay xuống cũng là "vuốt lên / vuốt xuống" → khôi phục / thu nhỏ ngoài ý muốn;
- bàn tay mở vừa để vuốt vừa để phát tiếp YouTube → nắm tay xong vuốt dễ thành phát tiếp và ngược lại.

Giữ tư thế tĩnh thì landmarks rõ nét, và chỉ đếm giờ khi tay **đứng yên**, nên đưa tay vào/ra khung không kích hoạt gì.

### Mẹo để nhận diện tốt

- Đặt tay cách camera 40–80 cm, lòng bàn tay/mu bàn tay hướng về camera, đủ sáng, không ngược sáng.
- 👍/👎: nắm chặt 4 ngón, **ngón cái duỗi thẳng** hướng hẳn lên/xuống (không để nằm ngang).
- 👉: duỗi thẳng ngón trỏ **nằm ngang** sang phải *như anh thấy trong preview*; co hẳn ngón giữa, áp út, út.
- ✊: ngón cái **áp lên** các ngón đang co (không giơ ra), nếu không NEXA sẽ hiểu là like/dislike hoặc "chưa rõ".
- Bảng **Cử chỉ ▸** hiện tư thế đang thấy, độ tin cậy và thanh "Giữ yên" — thanh đầy là lệnh phát.

## Chuột bằng tay (v1.9, `nexa/vision/air_mouse.py`)

Bật bằng "**bật chuột bằng tay**" / "**bật chế độ chuột ảo**" hoặc nút **Chuột bằng tay** trong bảng Cử chỉ (tự bật
camera nếu chưa bật). Tắt bằng "tắt chuột bằng tay" / "dừng chuột bằng tay", nút, hoặc dừng khẩn cấp. Trong lúc bật,
**sáu cử chỉ lệnh tạm ngưng** để không lẫn (ví dụ chỉ ngón trỏ sang phải không chuyển cửa sổ).

| Động tác | Kết quả |
| --- | --- |
| Di chuyển tay (xòe hoặc chỉ ngón trỏ) | Con trỏ đi theo, kiểu touchpad: tương đối, có gia tốc; đi được qua cả hai màn hình |
| 🤏 Chụm ngón cái + ngón trỏ rồi nhả | Click trái (chụm hai lần nhanh = click đúp, do Windows tự nhận) |
| Chụm ngón cái + ngón trỏ, giữ, di chuyển | Kéo thả |
| Chụm ngón cái + ngón giữa | Click phải |
| ✌ Hai ngón (trỏ + giữa) đưa lên / xuống | Cuộn (con trỏ đứng yên) |
| ✊ Nắm tay | "Nhấc tay khỏi touchpad": con trỏ đứng yên, anh dời tay về giữa khung rồi xòe ra đi tiếp |

Thiết kế chống lỗi:

- **Bám tâm lòng bàn tay**, không bám đầu ngón trỏ: khi chụm, đầu ngón di chuyển nhưng lòng bàn tay gần như đứng yên,
  nên con trỏ không giật đúng lúc click.
- **Chụm** = khoảng cách đầu ngón cái tới đầu ngón trỏ/giữa chia cho kích thước tay: nhận khi < `pinch_on` trong
  `pinch_frames` khung liên tiếp, nhả khi > `pinch_off` (trễ bật/tắt). Đầu ngón đó phải cách xa tâm lòng bàn tay
  (`tip_reach`) nên **nắm tay không bao giờ thành click**. Ngón cái chạm giữa hai đầu ngón (không rõ trái/phải) thì
  bỏ qua.
- **Khóa con trỏ khi chụm**: sau khi nhấn, con trỏ đứng yên cho tới khi tay đi quá `drag_start` (× kích thước tay),
  nên click không bị trượt còn kéo thả vẫn chạy. Lúc nhấn, con trỏ được tua về vị trí `rewind_ms` trước (bù độ trễ
  nhận ra cú chụm), nhưng chỉ khi độ lệch ≤ `rewind_max_px`: không kéo lùi khi anh vừa lướt tay vừa chụm.
- **Dừng ngay, chạy lại mới bỏ phiếu**: nắm tay / hai ngón dừng con trỏ ngay từ khung đầu tiên; quay lại di chuyển cần
  đa số trong `pose_frames` khung.
- **Nhường chuột thật**: con trỏ bị dời khác chỗ NEXA đặt quá `yield_px` → NEXA nhường `yield_ms`.
- **Fail-safe**: chuột bằng tay không bao giờ tự đưa con trỏ vào góc màn hình chính. Nếu anh đưa chuột thật vào góc,
  NEXA dừng khẩn cấp như mọi thao tác khác.
- **Nhả nút an toàn**: mất tay quá `lost_hand_ms`, tắt chế độ, đổi tham số, khóa điều khiển (dừng khẩn cấp, tác vụ tự
  động đang giữ quyền) → nhả nút đang giữ. Dừng khẩn cấp tắt hẳn chuột bằng tay; bấm "Tiếp tục điều khiển" không tự
  bật lại.
- Chi phí thêm ~0,1 ms/khung (đo trên máy phát triển), không đáng kể so với MediaPipe (~10 ms).

Tham số (`config/gestures.yaml` → `mouse`): `mapping` (relative | absolute), `gain`, `accel`, `pinch_on`,
`pinch_off`, `drag_start`, `scroll_step`, `invert_scroll`, `yield_ms`. Các khóa khác xem `MouseParams` trong mã.
Hướng ngang theo `calibration.invert_x` như sáu cử chỉ.

## Luồng xử lý

```
camera (lật gương 1 lần) → MediaPipe 21 landmarks → gesture_features (tư thế + hướng, tâm lòng bàn tay, kích thước tay)
  → gesture_state_machine (bỏ phiếu tư thế, giữ yên, cooldown) → gesture_router
  → executor (cùng tool registry với lệnh giọng nói) → kiểm chứng kết quả → overlay / GesturePanel
```

## Nhận diện tư thế (`nexa/vision/gesture_features.py`)

- Mỗi ngón (trỏ, giữa, áp út, út) có **điểm duỗi 0..1** từ ba đặc trưng không phụ thuộc góc xoay: độ thẳng của ngón,
  tầm với (đầu ngón xa cổ tay hơn khớp giữa), khoảng cách đầu ngón tới tâm lòng bàn tay chia cho **kích thước bàn tay**.
  Duỗi ≥ 0,6, co ≤ 0,35; nằm giữa → "Chưa rõ".
- Bốn ngón co → phân biệt nắm tay và like/dislike bằng **khoảng cách đầu ngón cái tới đốt giữa/đốt xa của ngón trỏ và
  ngón giữa** (nắm tay: ngón cái vắt ngay trên các đốt này). Hướng ngón cái = vector khớp gốc → đầu ngón cái.
- Chỉ ngón trỏ → hướng = vector khớp gốc → đầu ngón trỏ: ngang phải / ngang trái / lên; chéo hoặc xuống → "Chưa rõ".
- Tư thế ổn định = bỏ phiếu trên 6 khung gần nhất (≥ 65%), bỏ khung có độ tin cậy < 0,6.

## Máy trạng thái (`nexa/vision/gesture_state_machine.py`)

- **Đơn vị:** khoảng cách = kích thước bàn tay, tốc độ = kích thước tay/giây — không phụ thuộc khoảng cách tới camera.
- **Giữ yên:** chỉ đếm khi tốc độ < `still_speed` và tâm tay không trôi quá `deadzone`. Tay di chuyển → hủy đếm.
- **Một lần mỗi lần giữ:** giữ tiếp không lặp lệnh; muốn làm lại phải đổi tư thế (hạ tay/xòe tay) rồi giữ lại.
  Riêng hai ngón thì cuộn lặp lại mỗi `scroll.repeat_ms` khi còn giữ.
- **Cooldown** `cooldown_ms` dùng chung cho ba lệnh cửa sổ. Nếu anh vẫn giữ tư thế khi hết cooldown, lệnh sẽ phát
  (không bị nuốt mất).
- **Nắm tay giữ yên** → YOUTUBE_PAUSE một lần cho tới khi nhả tay. **Xòe tay giữ yên** → YOUTUBE_RESUME **chỉ khi** vừa
  có một lần nắm tay đã phát PAUSE (nhả trong `resume_window_ms`).
- **Mất tay** quá `lost_hand_ms`, đổi tay điều khiển, tắt camera, dừng khẩn cấp → xóa mọi ứng viên.
- **Snapshot cửa sổ:** khi bắt đầu giữ một tư thế lệnh cửa sổ / cuộn, NEXA chụp HWND + PID + thời điểm tạo tiến trình của
  cửa sổ foreground. Trước khi chuyển/thu nhỏ/cuộn, NEXA kiểm tra lại; nếu anh đã đổi cửa sổ thì hủy.
- Khi một tác vụ tự động (Gemini hoặc chuỗi lệnh nhiều bước) đang giữ quyền điều khiển, cử chỉ bị từ chối với thông
  báo "đang có tác vụ tự động…"; anh có thể nói "hủy"/"dừng lại".

## Tham số (`config/gestures.yaml`) — giá trị khởi đầu, chỉnh theo webcam của anh

| Nhóm | Khóa | Mặc định | Gợi ý chỉnh |
| --- | --- | --- | --- |
| pose | `min_confidence` | 0.6 | giảm nhẹ (0.5) nếu tư thế hay rơi về "Chưa rõ" |
| pose | `vote_frames` / `vote_ratio` | 6 / 0.65 | tăng nếu tư thế nhấp nháy |
| hold | `hold_ms` | 500 | nắm tay / xòe tay |
| hold | `action_hold_ms` | 650 | chỉ tay, like/dislike, hai ngón; tăng nếu bị kích nhầm |
| hold | `still_speed` | 0.9 | tăng nếu tay run bị coi là đang di chuyển |
| hold | `deadzone` | 0.5 | xê dịch tối đa (× kích thước tay) vẫn coi là giữ yên |
| hold | `resume_window_ms` | 4000 | thời gian tối đa từ lúc nhả nắm tay tới lúc xòe tay |
| scroll | `repeat_ms` / `notch_size` | 180 / 2 | tốc độ cuộn khi giữ hai ngón |
| scroll | `invert_scroll` | false | true = giữ hai ngón cuộn nội dung xuống |
| timing | `cooldown_ms` | 900 | giữa hai lệnh cửa sổ |
| timing | `lost_hand_ms` | 250 | |
| calibration | `invert_x` / `invert_y` | false | do bước hiệu chuẩn tự đặt |

Các khóa của bộ vuốt cũ (`swipe.*`, `scroll.step_distance`, `timing.rearm_ms`…) được tự động bỏ khi nạp cấu hình.

## Hiệu chuẩn

1. Bật camera (nút **Bật cử chỉ**), mở **Cử chỉ ▸** để xem preview dạng gương, landmarks và thanh "Giữ yên".
2. Cài đặt → **Cử chỉ** → "Hiệu chuẩn: tôi sẽ CHỈ NGÓN TRỎ SANG PHẢI", rồi giữ ngón trỏ chỉ sang phải *thật* của anh.
   Nếu camera đã tự lật sẵn, NEXA đặt `invert_x`. Làm tương tự với "GIƠ NGÓN CÁI LÊN". Trong lúc hiệu chuẩn, cử chỉ
   không kích hoạt thao tác nào; tư thế không thuộc bước đang hiệu chuẩn bị bỏ qua.
3. Thử từng tư thế, quan sát "Tư thế" và độ tin cậy. Nếu tư thế nhấp nháy, cải thiện ánh sáng, đưa tay rõ hơn, hoặc
   tăng `vote_frames`.
4. Chỉnh ngưỡng trong Cài đặt → Cử chỉ rồi **Lưu** (ghi `config/gestures.yaml`).

## Nhận biết anh qua webcam (`nexa/core/attention.py`)

Chạy cùng luồng camera cử chỉ (MediaPipe FaceLandmarker, `models/face_landmarker.task` — tải bằng
`python scripts/download_models.py --faces`), mỗi 3 khung (~10 Hz), hoàn toàn cục bộ, không lưu ảnh. Cần camera đang
bật. Cấu hình ở `config/settings.yaml → attention`.

**Có ngồi ở máy không** (`nexa/vision/presence.py`, `presence_enabled`): không thấy mặt *và* không phím/chuột
`away_after_s − warning_s` giây → toast đếm ngược; tới `away_after_s` (45 s) → tạm dừng video đang phát rồi khóa Windows.
Mở khóa (PIN/Windows Hello — NEXA không bao giờ nhập mật khẩu) → phát tiếp video, *chỉ khi NEXA đã dừng nó*. Có
phím/chuột gần đây luôn tính là đang ngồi. Người thứ hai đủ gần (mặt ≥ 45 % mặt anh) nhìn màn hình ≥ 1,5 s → thu nhỏ
cửa sổ nhạy cảm (`sensitive_processes` / `sensitive_titles`: Zalo, ngân hàng, mật khẩu, `.env`…). Khi điều khiển đang
tạm khóa (dừng khẩn cấp / công cụ khác đang điều khiển) NEXA chỉ báo, không làm gì.

**Chọn màn hình theo hướng quay đầu** (`nexa/vision/head_monitor.py`, `head_target`): góc yaw/pitch từ ma trận biến đổi
khuôn mặt, so với "tâm" từng màn hình đã hiệu chuẩn (tâm gần nhất, có trễ + giữ 0,35 s để lướt mắt không đổi).
`commands`: lúc anh bắt đầu nói / bắt đầu cử chỉ, NEXA nhớ màn hình anh nhìn và đưa cửa sổ trên cùng của màn hình đó
lên trước khi chạy lệnh (con trỏ cũng sang đó để cuộn đúng chỗ). `auto`: focus tự theo hướng nhìn khi anh không gõ
phím/di chuột ≥ 1 s. Hiệu chuẩn: nói "hiệu chỉnh hướng nhìn" (hoặc nút trong bảng Cử chỉ) rồi nhìn vào giữa màn hình
đang sáng khung, mỗi màn hình ~2,5 s; kết quả lưu ở `attention.head_calibration`.

Giọng nói: "bật/tắt tự khóa máy", "bật chống nhìn trộm", "hiệu chỉnh hướng nhìn", "bật (tự động) chọn màn hình theo
hướng nhìn", "tắt chọn màn hình theo hướng nhìn". Kiểm thử: `tests/test_attention.py`.

## Kiểm thử

`tests/test_gestures.py` dùng landmarks tổng hợp (`tests/hand_synth.py`) ở nhiều góc xoay và kích thước, cùng chuỗi
khung mô phỏng 30 FPS: phân loại đủ 8 tư thế, hướng chéo → chưa rõ, nắm tay ≠ like, chỉ tay kiểu "khẩu súng", giữ đủ /
chưa đủ thời gian, tay di chuyển không phát lệnh, hạ bàn tay mở không thu nhỏ (lỗi cũ), phân loại nhấp nháy bị bỏ phiếu
loại, cooldown không nuốt lệnh, mất tay, đảo trục, cuộn lặp khi giữ, nắm tay → xòe tay phát tiếp đúng một lần, và hiệu
chuẩn (kể cả việc đảo trục không tự phát lệnh). Đây là mô phỏng; độ chính xác trên webcam thật cần anh kiểm tra theo
`docs/manual_tests.md`.

## Chế độ xem mô hình 3D (VIEWER_3D)

Khi trình xem 3D đang mở, cử chỉ tay CHỈ điều khiển mô hình: chuột bằng tay và sáu cử chỉ ở trên tạm ngưng (nắm tay
không tạm dừng YouTube). Đóng trình xem → sáu cử chỉ hoạt động lại, chuột bằng tay vẫn tắt.

| Động tác | Kết quả |
|---|---|
| 🖐 đưa bàn tay mở vào, giữ yên ~0,2 s rồi di chuyển | xoay mô hình (trái/phải = yaw, lên/xuống = pitch) |
| ✊ nắm tay giữ yên 0,5 s → 🖐 mở tay giữ yên 0,35 s | tách các bộ phận (đúng một lần) |
| ✊ nắm tay giữ yên khi đang tách | lắp lại |
| ✌ hai ngón đưa lên / xuống | phóng to / thu nhỏ |

Ngưỡng trong Cài đặt > Mô hình 3D (`three_d.gesture.*`). Chi tiết: docs/three_d.md §6.

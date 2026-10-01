# Kiểm tra thủ công NEXA trên máy thật

Chuẩn bị: đã chạy `setup_windows.bat`; `scripts\diagnose.py` không báo lỗi nghiêm trọng; (cho bước 13–15) đã đặt
`GEMINI_API_KEY` mới trong `.env`; (cho bước 16–19, 24) đã cắm hai màn hình ở chế độ *Extend*; (cho bước 20–22) đã cài
NEXA Bridge.

Ghi kết quả: ✓ đạt · ✗ lỗi (ghi lại hiện tượng + dòng liên quan trong `logs\nexa.log`).

## Checklist chính

| # | Bước | Kỳ vọng | Kết quả |
| --- | --- | --- | --- |
| 1 | Chạy `start_windows.bat` | Cửa sổ “NEXA — by NXS MEDIA”, quả cầu mờ chuyển động chậm, nhãn **Đang chờ tiếng vỗ tay**, chip Camera “tắt”, Mic “bật” | |
| 2 | Vỗ tay một lần (cách mic ~0,5–1 m) | Quả cầu sáng dần, vòng mở rộng, âm báo, câu “Chào anh Sơn, em là Nexa. Em sẵn sàng.” (hoặc chữ nếu không có TTS), rồi **Đang nghe** | |
| 3 | Nói “Mở Notepad” | Dòng “Em nghe: Mở Notepad”, Notepad mở và lên trước, viền sáng quanh cửa sổ | |
| 4 | “Gõ nội dung: Xin chào, tôi là Nguyễn Xuân Sơn” | Notepad nhận đúng chữ có dấu; không đụng clipboard | |
| 5 | “Đặt âm lượng 30 phần trăm” | Âm lượng Windows = 30%, NEXA báo “Đã đặt âm lượng 30%.” | |
| 6 | “Tìm trên web cách học Python” | Trình duyệt mặc định mở trang tìm kiếm | |
| 7 | “Chụp màn hình” | Tệp PNG mới trong `Pictures\NEXA`, thông báo đường dẫn | |
| 8 | Bật camera (nút **Bật cử chỉ**), mở **Cử chỉ ▸**, hiệu chuẩn hướng (Cài đặt → Cử chỉ), thử checklist cử chỉ bên dưới | Nhãn đỏ “CAMERA ĐANG BẬT”, preview gương + landmarks, tư thế đúng | |
| 9 | “Nexa, nghỉ đi”, rồi vỗ tay | Về STANDBY; vỗ tay đánh thức lại | |
| 10 | Nói một yêu cầu nhiều bước, trong lúc chạy bấm **DỪNG KHẨN CẤP** hoặc Ctrl+Alt+Esc | Tác vụ dừng, không bước nào chạy tiếp, thông báo “Điều khiển tạm khóa”, có nút **Tiếp tục điều khiển** | |
| 11 | Ngắt mạng; xóa key trong `.env`; rút mic; che/ngắt camera | NEXA không sập: chip AI “Cơ bản” + lý do; lệnh cơ bản vẫn chạy; mic/camera lỗi hiển thị thông báo | |
| 12 | Khi overlay hiện (nhấp chuột, thu nhỏ…), nhấp xuyên qua vùng overlay | Click tới ứng dụng bên dưới; overlay không lấy focus; cửa sổ NEXA vẫn tương tác được | |
| 13 | Với key Gemini: “Hôm nay em giúp anh được gì?”, “Mở Notepad và viết một đoạn giới thiệu ngắn về NXS MEDIA” | Trả lời tự nhiên, xưng “em”; Notepad mở, bản nháp được gõ, **không tự gửi/đăng** | |
| 14 | Bật “Đọc màn hình” (Cài đặt → AI), nói “Đọc màn hình và tóm tắt giúp anh” → xem trước, kéo chọn vùng, Đồng ý; sau đó tắt tính năng và thử lại | Có hộp xem trước + chỉ báo “Đang gửi ảnh”; khi tắt: NEXA từ chối, không chụp, không gửi | |
| 15 | Đổi `GEMINI_API_KEY` thành chuỗi sai hoặc ngắt mạng | “Chế độ lệnh cơ bản: …” với lý do đúng (key bị từ chối / mất mạng); lệnh cơ bản vẫn chạy | |
| 16 | Notepad ở màn hình 1; giữ 👉 ngón trỏ chỉ sang phải; tiếp tục giữ thêm vài giây | Notepad sang màn hình 2, hiệu ứng mũi tên trên màn hình nguồn, viền trên màn hình đích; **không** bị đẩy tiếp khi giữ tay (phải đổi tư thế mới làm lại) | |
| 17 | Lặp lại với cửa sổ phóng to; hai màn hình khác DPI/độ phân giải | Cửa sổ vẫn phóng to trên màn hình 2; cửa sổ thường nằm gọn trong work area, cỡ hợp lý | |
| 18 | Giữ 👎 ngón cái chỉ xuống, hạ tay, rồi giữ 👍 ngón cái chỉ lên | Thu nhỏ xuống taskbar (không đóng/không ẩn khay); 👍 khôi phục đúng cửa sổ và trạng thái | |
| 19 | Thu nhỏ A rồi B; 👍 hai lần (hạ tay giữa hai lần); thử đóng một cửa sổ trong lịch sử trước khi khôi phục | Khôi phục B rồi A; cửa sổ đã đóng bị bỏ qua; lịch sử rỗng → “Chưa có cửa sổ để khôi phục” | |
| 20 | Gắn một tab YouTube (popup NEXA Bridge); nắm tay giữ yên / mở tay giữ yên khi trình duyệt có và không có focus, ở cả hai màn hình; mở thêm tab YouTube khác và Spotify phát nhạc | Chỉ video đã gắn dừng/phát; biểu tượng ⏸/▶ theo kết quả thật; tab khác và Spotify không bị động tới | |
| 21 | Giữ nắm tay 5 giây; giữ mở tay 5 giây | Chỉ một lần pause, một lần resume; không pause/play liên tục | |
| 22 | Trang web dài: giữ ✌ hai ngón (trỏ + giữa) 3 giây rồi xòe tay; bật `invert_scroll` và thử lại | Cuộn liên tục khi giữ, dừng ngay khi đổi tư thế (không khôi phục cửa sổ, không phát YouTube); invert đổi chiều | |
| 23 | Đưa bàn tay mở vào khung, hạ xuống, vẫy qua lại; nắm tay rồi giơ 👍 thay vì xòe tay | Không có lệnh nào khi tay di chuyển (lỗi cũ: hạ tay → thu nhỏ); 👍 chỉ khôi phục cửa sổ, **không** phát tiếp video | |
| 24 | Rút màn hình 2 rồi giữ 👉; rút tay khỏi khung khi thanh "Giữ yên" chưa đầy; đổi cửa sổ trong lúc giữ; bấm dừng khẩn cấp rồi giữ 👉 | Báo chỉ còn một màn hình; không thao tác; hủy vì cửa sổ đổi; cử chỉ bị khóa tới khi Tiếp tục điều khiển | |

## Checklist mở rộng cho sáu cử chỉ

Thực hiện mỗi cử chỉ 10 lần, ghi số lần đúng / sai / nhầm sang cử chỉ khác (điều kiện ánh sáng, khoảng cách 0,5–1,5 m).

| Cử chỉ | Đúng | Không nhận | Nhận nhầm | Ghi chú |
| --- | --- | --- | --- | --- |
| 👉 Chỉ trỏ sang phải → màn hình 2 | | | | |
| 👎 Ngón cái xuống → thu nhỏ | | | | |
| 👍 Ngón cái lên → khôi phục | | | | |
| ✊ Nắm tay giữ → pause | | | | |
| 🖐 Xòe tay sau nắm tay → resume | | | | |
| ✌ Giữ hai ngón → cuộn lên | | | | |
| Tay đứng yên/cử động tự nhiên 60 s | — | — | | không được có sự kiện nào |

## Checklist chuột bằng tay (v1.9)

Nói "bật chuột bằng tay" hoặc bấm **Chuột bằng tay** trong bảng Cử chỉ. Mỗi dòng làm 10 lần.

| Thao tác | Đúng | Không nhận | Nhầm | Ghi chú |
| --- | --- | --- | --- | --- |
| Di tay chậm → con trỏ đi theo mượt, dừng tay → con trỏ đứng yên (không rung quá ~5 px) | | | | |
| Di tay nhanh → con trỏ đi xa hơn (gia tốc); đi được sang màn hình 2 | | | | |
| 🤏 Chụm cái + trỏ rồi nhả → click đúng chỗ đang trỏ (thử nút nhỏ ~20 px) | | | | |
| Chụm hai lần nhanh → click đúp (mở một thư mục) | | | | |
| Chụm giữ rồi kéo → kéo thả (kéo một tệp, kéo thanh cuộn) | | | | |
| Chụm cái + giữa → menu chuột phải | | | | |
| ✌ Hai ngón đưa lên/xuống → cuộn đúng chiều, con trỏ không chạy | | | | |
| ✊ Nắm tay rồi dời tay → con trỏ đứng yên; xòe lại → không nhảy | | | | |
| Nắm tay / tay thả lỏng 60 s → KHÔNG có click nào | — | — | | |
| Cầm chuột thật di chuyển → NEXA nhường ~1 s, không giành con trỏ | | | | |
| Đang kéo thì đưa tay ra khỏi khung → nút được nhả (không kẹt kéo) | | | | |
| Ctrl+Alt+Esc khi đang kéo → nhả nút, chuột bằng tay tắt hẳn | | | | |
| Đưa chuột thật vào góc trên-trái màn hình chính → dừng khẩn cấp | | | | |

Nếu con trỏ quá nhanh/chậm: chỉnh `mouse.gain` trong `config/gestures.yaml`. Nếu click hay thành kéo: tăng
`mouse.drag_start`. Nếu chụm khó nhận: tăng `mouse.pinch_on` (giữ `pinch_off` lớn hơn `pinch_on` khoảng 0,15).

---

## Kết quả kiểm tra (09/2026, máy phát triển Windows 11 Home x64, Python 3.11.9)

### Đã kiểm tra bằng công cụ, chạy thật trên máy phát triển

- Cài đặt: môi trường ảo Python 3.11.9 + các thư viện trong `requirements.txt`; `pip install --dry-run -r requirements.txt`
  phân giải 93 gói, đúng các phiên bản đã thử (PySide6 6.11.2, mediapipe 1.0.1, opencv-contrib-python 5.0.0.93,
  google-genai 2.25.0, faster-whisper 1.2.1, numpy 2.4.6), không có xung đột OpenCV.
- **181 kiểm thử tự động đạt** (`pytest -q`, ~6 s).
- Ứng dụng chạy từ mã nguồn và từ bản EXE: khởi động → STANDBY; mở mic Realtek ở 16 kHz mono; bridge named pipe sẵn sàng;
  faster-whisper `small` nạp trong 2,2–2,5 s; lệnh bàn phím “mấy giờ rồi” đi qua THINKING → EXECUTING → SPEAKING →
  LISTENING, đọc bằng edge-tts; tắt sạch (nhả phím/chuột, dừng luồng).
- Mic thật: ở lần chạy đầu NEXA đã phát hiện một xung âm (−17 dBFS) và đánh thức (WAKING → SPEAKING). Em không xác
  định được đó là tiếng vỗ tay hay tiếng khác trong phòng; vì vậy đã thêm lọc bỏ xung trùng thao tác bàn phím/chuột.
- Gemini: SDK dựng được cấu hình với 37 khai báo công cụ; một request thật tới Gemini API với **key giả** nhận lỗi
  “API key not valid”, được phân loại đúng `auth`, không thử lại, provider tự khóa key đó. **Chưa thử với key thật.**
- TTS: edge-tts tổng hợp 0,8–1,7 s mỗi câu; WinRT “Microsoft An” (offline) 0,09 s; SAPI5 trên máy này không có giọng Việt.
- STT (giọng tổng hợp → faster-whisper `small`, CPU ~1,4–1,8 s/câu):

  | Câu gốc | Giọng Edge | Giọng Windows An |
  | --- | --- | --- |
  | Mở Notepad | ✓ | ✓ |
  | Đặt âm lượng ba mươi phần trăm | ✓ (“30%”) | “Đã tâm lượng…” (đã thêm bảng sửa lỗi nghe nhầm) |
  | Tìm trên web cách học Python | “…học phí thông” | “Thìm… đi tùng” |
  | Chụp màn hình | ✓ | “Chúc màn hình” (đã thêm bảng sửa) |
  | Nexa, nghỉ đi / Dừng lại | ✓ | ✓ |
  | 3 giây im lặng có nhiễu | bị loại đúng | |

  Giọng tổng hợp không đại diện cho giọng thật; từ tiếng Anh (Python) thường bị nghe sai.
- MediaPipe: tải `hand_landmarker.task`, MD5 khớp với máy chủ; suy luận ~10 ms/khung trên CPU (khung trống).
- Win32: liệt kê màn hình, tên EDID và đường dẫn thiết bị qua `QueryDisplayConfig`; đọc foreground/placement; đăng ký
  được Ctrl+Alt+Esc và Ctrl+Alt+N; DPI Per-Monitor v2.
- Giao diện: render bằng `grabWindow()` (chỉ nội dung cửa sổ NEXA) ở STANDBY, SPEAKING, Cài đặt, bảng Cử chỉ; **FPS đo
  được 142–144** trên máy phát triển (chế độ hiệu ứng full).
- Bridge: `node --check` cho 3 tệp JS, manifest JSON hợp lệ, `install_bridge.ps1` parse được; kiểm thử IPC named pipe
  thật (xác thực HMAC, từ chối key sai, khung tin Native Messaging, từ chối origin lạ).
- Build EXE bằng PyInstaller 6.22.3 thành công (`dist\NEXA`, ~976 MB, không chứa `.env`) và chạy được.
- `scripts\diagnose.py --quick` chạy không lỗi nghiêm trọng.

### Kiểm tra mô phỏng (không dùng thiết bị thật)

- Vỗ tay: tín hiệu tổng hợp (vỗ tay, lời nói, tiếng gõ trầm, nhiễu kéo dài, hai tiếng, cooldown, debounce, chặn âm của NEXA).
- Sáu cử chỉ: landmarks tổng hợp xoay/co giãn + quỹ đạo 30 FPS (xem `docs/gestures.md`).
- Hai màn hình, thu nhỏ/khôi phục, lịch sử, snapshot: Win32 giả lập (tọa độ âm, 96/144 DPI, rút màn hình…).
- YouTube: backend giả (pause/resume xác định, đổi video, đóng tab, ứng dụng media khác không bị điều khiển).
- Gemini: client giả dùng kiểu dữ liệu thật của SDK (văn bản, tool call giữ ID, schema lỗi, công cụ lạ, trường nội bộ bị
  chặn, 401/400, 404, 429 có giới hạn, 503 không chạy trùng công cụ, timeout, mất mạng, hủy giữa chừng, giới hạn bước,
  cắt lịch sử, Screen Vision tắt không chụp, key không vào log, repo không chứa key).
- An toàn: xác nhận theo ID/hết hạn/đối tượng đổi, dừng khẩn cấp hủy hàng đợi và chặn token cũ, chống chạy trùng,
  khóa điều khiển, rủi ro phím tắt theo ngữ cảnh, tệp trong thư mục tạm (Thùng rác được mock).

### Cần anh xác nhận trên máy thật (em chưa làm / không thể làm)

- Máy phát triển chỉ có **một màn hình** → toàn bộ luồng hai màn hình (bước 16, 17, 24) chưa chạy trên phần cứng thật.
- **Webcam và độ chính xác sáu cử chỉ** chưa đo: em không bật camera của anh khi anh đang dùng máy (bước 8, 16–24).
- **YouTube bridge trong trình duyệt**: em không tự cài extension/ghi registry trình duyệt của anh (bước 20–22).
- **Gemini với key thật**: hội thoại, nhiều bước, soạn bản nháp, đọc màn hình (bước 13–15).
- **Giọng nói thật của anh** qua mic và **vỗ tay thật** trong phòng (bước 2, 3, 9).
- Các thao tác thay đổi máy (mở/gõ Notepad, đặt âm lượng, chụp màn hình, tìm web, overlay click-through) chỉ được kiểm
  thử tự động với lớp giả lập; em không chạy chúng trên máy vì anh đang sử dụng máy (bước 3–7, 10–12).
- Chưa đo độ chính xác nhận dạng/cử chỉ hay tốc độ trên máy khác; không có con số cam kết nào ngoài các số đo nêu trên.

## Mô hình 3D (docs/three_d.md)

1. Nói "Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm" → NEXA báo đang tạo, vài giây sau mở viewer; thẻ thông tin: đường
   kính 8, dài 30, bước ren 1,25 mm, "ren helix kỹ thuật", điểm ≥ 90.
2. "Tạo bu lông M8" → NEXA hỏi "Bu-lông M8 dài bao nhiêu mm ạ?" → trả lời "40" → tạo M8×40.
3. "Tạo UAV mini bốn cánh, thân carbon màu đen, camera phía trước" → cây bộ phận có khung, 4 tay đòn, 4 motor, 4 cánh quạt,
   camera; có cảnh báo chưa kiểm chứng chế tạo.
4. Bật cử chỉ trong viewer: bàn tay mở + vuốt → xoay mượt, không tách; nắm tay giữ ~0,5 s → mở tay giữ yên → tách một lần;
   vuốt tiếp → xoay mô hình đang tách; nắm tay giữ → lắp lại. Nắm tay lúc này KHÔNG được tạm dừng YouTube.
5. "Xem chi tiết cánh quạt" → NEXA hỏi trước trái/sau trái/…/cả cụm; "trước trái" → phóng to đúng cánh.
6. Trong lúc đang tạo, bấm DỪNG KHẨN CẤP → job hủy, viewer không tự mở kết quả đến muộn, cử chỉ viewer khóa.
7. Kéo chuột xoay, lăn thu phóng, nhấp chọn bộ phận, X-quang, khung dây, "hiện lại toàn bộ", Esc đóng — giao diện không đứng.
8. Mức 2: "Tạo ấm đun nước siêu tốc màu bạc" → thanh tiến độ qua "Gemini đang thiết kế…", có thể "đang sửa N bộ phận",
   "đang xem ảnh và sửa (vòng k)"; mở viewer với vài bộ phận (thân, nắp, tay cầm, đế) tách được; nhãn "best effort".
9. Mức 3: đặt HF_TOKEN trong .env, nói "Tạo bình hoa gốm bằng hugging face" → tiến độ hiện "xếp hàng #…"/"đang chạy …s";
   2–6 phút sau mở viewer với lưới AI. Bấm Hủy giữa chừng → job hủy, không mở kết quả đến muộn.

### Kết quả kiểm tra mô hình 3D (2026-09-25)

- Đã chạy bằng công cụ: 892 kiểm thử tự động đạt (174 kiểm thử 3D mới). Benchmark cục bộ 361/361 đạt gate. Viewer chạy
  trong cửa sổ D3D11 đặt ngoài màn hình (không chụp màn hình), không có cảnh báo QML, 62,5 FPS. Cử chỉ tổng hợp 30 Hz đi
  qua đúng `feed_gesture` → xoay 124° trong 3 s rồi tách. Gemini thật: planner (M10×45, UAV 6 cánh 550 mm, robot 1,6 m)
  cho đúng category và tham số; chấm 6 góc cho bu-lông M8×30 được 99/100.
- Bản PyInstaller kiểm thử (`build/pyi_dist/NEXA`) có đủ QtQuick3D, Helpers, AssetUtils, manifold3d, fast_simplification,
  các QML 3D và studio.hdr. **Chưa mở NEXA.exe** vì mở sẽ bật camera/mic.
- Chưa kiểm tra (cần anh làm trên máy thật): các bước 1–7 ở trên với giọng nói và camera thật; Tripo/Meshy (chưa có key,
  mới thử với HTTP giả lập).

### Mô hình kỹ thuật chi tiết + thuyền (2026-09-25)

10. "Tạo xe tự hành sáu bánh có lidar" → nhìn gần vỏ: có rãnh ghép tấm, khe tản nhiệt, ốc nắp, tay cầm, nút dừng khẩn cấp
    đỏ-vàng; cản trước có 3 cảm biến siêu âm; lốp có vân cao su, cột camera kim loại chải (xoay đèn để thấy vân).
11. "Tạo robot hình người" → khớp có mặt bích màu + vòng ốc; kính mặt tối bóng, sau kính có hai "mắt" đèn, không nhiễu sọc.
12. "Tạo ca nô cao tốc dài 6 m" / "tạo tàu cá dài 12 m" / "tạo du thuyền hai máy" / "tạo tàu tuần tra" → thân đáy chữ V,
    lan can mũi, đèn mạn đỏ (trái) xanh (phải); tách mô hình: boong, cabin, lan can nhấc lên, máy/chân vịt kéo ra sau.

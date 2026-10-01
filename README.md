# NEXA — by NXS MEDIA

Trợ lý máy tính của anh **Nguyễn Xuân Sơn** (CEO & Founder, Công ty TNHH Thương Mại và Dịch Vụ NXS MEDIA).
NEXA nghe lệnh tiếng Việt qua mic, nhận diện sáu cử chỉ tay qua webcam, thao tác trên Windows và hiển thị
một quả cầu năng lượng phản ứng theo trạng thái. Bộ AI chính là **Gemini** (Google Gen AI SDK); khi không
có key hoặc mất mạng, NEXA vẫn chạy **chế độ lệnh cơ bản** hoàn toàn cục bộ.

> **Giả định máy đích:** Windows 10/11 64-bit, Python 3.11 64-bit, chạy bằng CPU (không cần GPU).
> Đã chạy và kiểm thử trên Windows 11 x64 + Python 3.11.9 (xem [Kết quả kiểm tra](#kết-quả-kiểm-tra)).

---

## 1. Kiến trúc ngắn gọn

```
 Mic ──► AudioPipeline (1 luồng mic duy nhất, callback chỉ chép dữ liệu)
           ├─► ClapDetector ──(STANDBY)──► đánh thức
           └─► VAD tách câu ──► faster-whisper (vi, CPU) ──┐
 Bàn phím / nút "Nói" ─────────────────────────────────────┤
                                                           ▼
                          Controller ──► IntentRouter (lệnh cơ bản, offline)
                                │                └─► GeminiProvider (function calling thủ công)
                                ▼                                 │ tool call
                  Executor tuần tự + SafetyManager ◄──────────────┘
                  (schema, rủi ro, xác nhận, khóa điều khiển, dừng khẩn cấp, chống chạy trùng)
                                ▼
            Tool registry: cửa sổ · 2 màn hình · YouTube · bàn phím/chuột · âm lượng · tệp · ứng dụng
                                ▲
 Webcam ──► Camera ──► MediaPipe Hand Landmarker ──► đặc trưng/quỹ đạo ──► Gesture state machine ──► GestureRouter
                                                                            (không gọi Gemini)
 UI: PySide6 + Qt Quick/QML (luồng chính) ◄── UiBridge (signal queued) ── mọi luồng nền
     Overlay click-through trên từng màn hình · TTS (edge-tts online / WinRT offline)
```

**Lựa chọn kỹ thuật chính (đã đối chiếu tài liệu/phiên bản 09/2026):**

| Phần | Lựa chọn | Lý do |
| --- | --- | --- |
| Giao diện | PySide6 6.11 + Qt Quick/QML | Hiệu ứng GPU (Shapes, Particles, 3D Rotation), Python vẫn là lõi |
| Âm thanh | sounddevice + NumPy/SciPy | Một `InputStream` duy nhất; kiểm tra định dạng mic thật bằng `check_input_settings` |
| STT | faster-whisper 1.2.1, model đa ngôn ngữ `small`, `language="vi"`, CPU int8 | Chạy cục bộ; đổi `medium`/`large-v3-turbo` trong Cài đặt |
| TTS | edge-tts (online) → WinRT SpeechSynthesis (offline) → SAPI5 (chỉ khi có giọng Việt) | Máy anh có giọng "Microsoft An" (OneCore); SAPI5 không có giọng Việt |
| AI | `google-genai` 2.25, `client.models.generate_content`, `automatic_function_calling.disable=True` | Mọi tool call đi qua executor của NEXA; model mặc định `gemini-3.5-flash-lite` |
| Cử chỉ | MediaPipe Tasks Hand Landmarker 1.0.1 (VIDEO mode) + OpenCV | Cục bộ, ~10 ms/khung CPU đo trên máy này |
| Cửa sổ/màn hình | ctypes Win32 (EnumDisplayMonitors, QueryDisplayConfig, Get/SetWindowPlacement, SetWindowPos), Per-Monitor DPI Aware v2 | Tọa độ virtual desktop âm, DPI khác nhau |
| YouTube | Extension MV3 + Native Messaging + named pipe có xác thực; dự phòng Windows GSMTC | GSMTC chỉ biết ứng dụng+tiêu đề, không biết tab |
| UI Automation | pywinauto (backend uia) | Bấm control theo tên thay vì tọa độ |

---

## 2. Cài đặt

### Cách nhanh

1. Cài **Python 3.11 64-bit** từ <https://www.python.org/downloads/windows/> (tích *Add python.exe to PATH* và *py launcher*).
2. Mở thư mục NEXA, chạy **`setup_windows.bat`**. Script sẽ:
   - tạo `.venv`, cài `requirements.txt`;
   - tạo `.env` từ `.env.example` (key vẫn là giá trị mẫu → chế độ lệnh cơ bản);
   - tạo âm thanh hiệu ứng (`assets/sounds`);
   - tải model MediaPipe `hand_landmarker.task` (kiểm tra MD5 do máy chủ Google cung cấp) và faster-whisper `small` (~480 MB);
   - chạy chẩn đoán nhanh.
3. Chạy **`start_windows.bat`** (hoặc `.venv\Scripts\python main.py`).

### Cách thủ công

```bat
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python scripts\generate_sounds.py
.venv\Scripts\python scripts\download_models.py
.venv\Scripts\python scripts\diagnose.py
.venv\Scripts\python main.py
```

> Không cài thêm `opencv-python`: mediapipe đã kéo theo `opencv-contrib-python`; hai gói dùng chung thư mục `cv2`
> và gỡ một gói sẽ làm hỏng gói kia.

---

## 3. Cấu hình Gemini (key mới của anh)

1. Tạo key mới tại Google AI Studio (<https://ai.google.dev/gemini-api/docs/api-key>).
2. Mở `.env` trong thư mục NEXA và sửa **một dòng**:
   ```
   GEMINI_API_KEY=<dán key mới vào đây>
   ```
   Hoặc vào **Cài đặt → AI (Gemini)**, dán key vào ô che ký tự, chọn “Lưu vào .env cục bộ” rồi bấm **Đặt key**.
   Có thể đặt biến môi trường Windows `GEMINI_API_KEY` thay cho `.env` (biến môi trường được ưu tiên).
3. Bấm **Kiểm tra kết nối Gemini** (gửi một câu văn bản ngắn, không có công cụ điều khiển máy).

Các biến trong `.env`:

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `NEXA_AI_PROVIDER` | `gemini` | Bản này chỉ hỗ trợ `gemini`; giá trị khác → chế độ cơ bản |
| `GEMINI_API_KEY` | `YOUR_NEW_GEMINI_API_KEY` | Trống/giá trị mẫu → chế độ lệnh cơ bản |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Model ổn định, hỗ trợ function calling + ảnh, độ trễ/chi phí thấp (đối chiếu <https://ai.google.dev/gemini-api/docs/models>, 09/2026). Có thể đổi, ví dụ `gemini-3.8-flash`, nếu key của anh có quyền. |
| `GEMINI_REQUEST_TIMEOUT_SECONDS` | `30` | Timeout mỗi request |
| `NEXA_MAX_TOOL_STEPS` | `8` | Số bước công cụ tối đa mỗi yêu cầu |
| `NEXA_CLOUD_SCREEN_VISION` | `false` | Bật tính năng “Đọc màn hình” (gửi ảnh vùng anh chọn lên Gemini) |

**Nếu model không tồn tại hoặc key không có quyền**, NEXA báo đúng lỗi (404/403) và **không tự đổi sang model khác**.
Lỗi xác thực không được thử lại vô hạn: key bị từ chối sẽ bị tạm khóa trong phiên cho tới khi anh đổi key hoặc bấm Kiểm tra.

**Quota & chi phí:** NEXA không cam kết API miễn phí hay không giới hạn. Quota/giá thực tế theo tài khoản Google của
anh. NEXA có **giới hạn nội bộ** riêng (số lần gọi/phiên, số lượt lịch sử, token đầu ra, số bước công cụ) — khác với
quota tài khoản. Số lần gọi và token (vào/ra/suy nghĩ) hiển thị ở Cài đặt → AI.

**Dữ liệu gửi Gemini:** câu lệnh đã chuyển thành chữ, giờ hiện tại, tên cửa sổ đang làm việc, số màn hình, trạng thái
cử chỉ và kết quả của các công cụ trong yêu cầu đó. **Không** gửi audio, video camera, hay màn hình (trừ khi anh dùng
“Đọc màn hình”, xem trước, chọn vùng và bấm Đồng ý). STT, vỗ tay và cử chỉ luôn chạy cục bộ. Lịch sử hội thoại chỉ giữ
trong bộ nhớ của phiên (nút **Xóa** để xóa); NEXA dùng `generate_content` không lưu hội thoại phía máy chủ theo
tính năng của NEXA, còn việc Google xử lý/lưu dữ liệu tuân theo điều khoản gói API anh dùng.

**Bảo vệ key:** key chỉ đọc từ môi trường/`.env`, được lọc khỏi mọi log (`logs/nexa.log`), không hiển thị trên giao
diện, không nằm trong `settings.yaml`, không có trong ZIP bàn giao (`.env` bị loại, chỉ kèm `.env.example`).

---

## 4. Sử dụng

### Trò chuyện liên tục — chế độ Tâm sự

- Bấm **Tâm sự** trên thanh điều khiển hoặc nói **“Nexa, tôi muốn tâm sự với em”** / **“bật chế độ tâm sự”**.
- NEXA nghe tiếp sau mỗi câu trả lời, không cần gọi tên hay bấm mic lại. Cách trả lời ưu tiên lắng nghe,
  theo mạch câu chuyện và hỏi nhẹ nhàng khi phù hợp; cần kết nối Gemini hoạt động.
- Chờ khoảng lặng ít nhất **1,4 giây** trước khi chốt câu; mỗi lượt nói dài tối đa **60 giây**
  (hoặc dài hơn nếu cấu hình VAD đã đặt cao hơn). Mặc định im lặng **5 phút** thì về chế độ chờ.
  Đổi thời gian này tại **Cài đặt → Âm thanh & vỗ tay → Tâm sự**.
- Trong chế độ này, lời kể chỉ được dùng để trò chuyện, không chạy lệnh máy tính.
  Nói **“thoát chế độ tâm sự”** hoặc bấm lại nút để trở về điều khiển.
- **“Nexa nghỉ đi”** kết thúc chế độ và về chờ; **“xóa hội thoại”** xóa ngữ cảnh trong phiên.
- Ngữ cảnh dùng lịch sử Gemini hiện có, giới hạn bởi `ai.max_history_turns`; không phải bộ nhớ vĩnh viễn.
  Văn bản hội thoại được gửi đến Gemini. Chế độ này bỏ qua ghi corpus nghiên cứu và không ghi nội dung
  nhận dạng vào dòng log STT của controller; không phải cam kết không có dữ liệu trong mọi log/hệ thống bên ngoài.
- Mic vẫn được chặn trong lúc NEXA nói để tránh vọng loa. Muốn ngắt lời, bấm **Nói** rồi nói tiếp;
  phiên bản này chưa hỗ trợ vừa nói vừa nghe/ngắt lời bằng giọng nói.

### Đánh thức bằng vỗ tay

- Sau khi chạy, NEXA vào **STANDBY — “Đang chờ tiếng vỗ tay”**: quả cầu mờ, chuyển động chậm, camera tắt.
  Mic chỉ dùng để phát hiện tiếng vỗ tay, **không** chuyển hội thoại thành văn bản.
- **Một tiếng vỗ tay** (mặc định) → quả cầu sáng dần, các vòng mở rộng, âm báo ngắn, NEXA nói
  “Chào anh Sơn, em là Nexa. Em sẵn sàng.” rồi bắt đầu nghe lệnh.
- Chế độ **hai tiếng liên tiếp** (Cài đặt → Âm thanh & vỗ tay) để giảm kích hoạt nhầm; chỉnh khoảng cách hai tiếng.
- Dự phòng: nút **Đánh thức**, phím **Ctrl+Alt+N**, nhấp đúp vào quả cầu, hoặc gõ lệnh vào ô nhập.
- “**Nexa, nghỉ đi**” → về STANDBY. Không hoạt động quá `idle_timeout_s` (mặc định 60 s) cũng về STANDBY.
- Tiếng vỗ tay chỉ đánh thức khi **NEXA đang chạy**; nó không bật máy tính hay khởi chạy Python.

**Ngủ canh gác (vỗ tay bật lại máy)** — Cài đặt → Âm thanh & vỗ tay, mặc định BẬT (`power.clap_wake_guard`):

**Tùy chọn giữ thức và giữ màn hình sáng:** bật `power.keep_display_awake` trong Cài đặt.
NEXA đăng ký cả `SystemRequired` và `DisplayRequired`; nhấn ngắn nút nguồn/ngủ và gập nắp được đặt thành
“Không làm gì” cho cả cắm sạc và dùng pin. Tùy chọn này ưu tiên hơn các mục tắt màn hình bên dưới;
lệnh “cho máy ngủ” sẽ thông báo rằng chế độ giữ thức đang bật. Khi thoát NEXA hoặc tắt giữ thức,
yêu cầu được giải phóng và hành động nút được khôi phục. Nếu NEXA bị tắt cưỡng bức, hành động nút có thể
còn giữ nguyên đến khi mở lại NEXA để phục hồi từ bản sao lưu.

Đây không phải bảo đảm “không bao giờ tắt/ngủ”: Sleep/Shut down từ Windows, giữ nút nguồn cưỡng bức,
sự cố hệ thống, quá nhiệt và bảo vệ pin yếu vẫn có hiệu lực. Không sửa ngưỡng/hành động pin nguy cấp.
Máy Modern Standby chạy pin có thể hết hiệu lực yêu cầu `SystemRequired` sau thời gian chờ ngủ;
vì vậy chế độ chỉ giữ máy thức trong khi cho màn hình tắt có giới hạn. Xem
[tài liệu PowerSetRequest của Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powersetrequest).

Hành vi bên dưới mô tả chế độ canh gác thông thường, khi **không** bật giữ màn hình sáng:
- Máy này dùng Modern Standby: khi ngủ thật Windows đóng băng mọi ứng dụng, mic tắt, nên **không** gì nghe được
  tiếng vỗ tay. Vì vậy khi NEXA chạy, máy **không tự ngủ** (power request “SystemRequired”, xem `powercfg /requests`
  bằng quyền admin); màn hình vẫn tắt theo hẹn giờ của Windows.
- “**Cho máy ngủ**” / “**tắt màn hình**” → NEXA đọc xong câu trả lời, về STANDBY và tắt màn hình (không ngủ thật).
- Vỗ tay khi màn hình đã tắt hoặc sau `away_after_s` (5 phút) không thao tác → bật màn hình, đưa cửa sổ NEXA lên và
  chào theo buổi (“Chào buổi tối anh Sơn…”, đổi được ở `power.wake_greeting`).
- Nếu Windows đang **khóa**: NEXA nhắc “anh mở khóa giúp em nhé”, chờ anh mở khóa (PIN/Windows Hello) rồi mới chào.
  NEXA **không** lưu hay gõ mật khẩu: màn hình khóa là desktop bảo mật Winlogon, ứng dụng thường không nhập vào đó được.
- Gập nắp/nút nguồn vẫn có thể gây ngủ nếu chưa bật tùy chọn đổi hành động tương ứng; Start → Sleep vẫn làm máy ngủ thật. NEXA phát hiện lần ngủ đó khi máy thức lại và báo;
  nếu chính lệnh tắt màn hình làm máy ngủ thật, NEXA tự chuyển `power.screen_off: false`.

**Hiệu chuẩn:** Cài đặt → Âm thanh & vỗ tay → tích **Chế độ thử** (vỗ tay chỉ hiện trên màn hình, không đánh thức),
xem mức mic, nền ồn, ngưỡng và tiếng vỗ tay gần nhất; chỉnh **Độ nhạy**, **Mức tối thiểu tuyệt đối**, bấm
**Hiệu chuẩn lại tiếng ồn nền** khi phòng yên lặng. Bộ phát hiện dùng nền ồn thích nghi, sườn lên đột ngột, độ rộng
xung ≤ 40 ms, độ tắt nhanh và tỷ lệ năng lượng cao tần, cộng debounce và cooldown. Tiếng gõ phím/nhấp chuột ngay
sát mic rất giống tiếng vỗ tay, nên NEXA bỏ qua xung xảy ra trong 400 ms sau một thao tác bàn phím/chuột.

### Lệnh giọng nói / bàn phím (chạy được cả ở chế độ cơ bản)

| Lệnh mẫu | Việc NEXA làm |
| --- | --- |
| “Mở Notepad” · “Mở trình duyệt” · “Mở File Explorer” | Mở ứng dụng, chờ cửa sổ mới rồi đưa lên trước |
| “Gõ nội dung: Xin chào, tôi là Nguyễn Xuân Sơn” | Gõ Unicode tiếng Việt vào cửa sổ đang làm việc (kiểm tra cửa sổ đích trước mỗi đoạn) |
| “Đặt âm lượng 30 phần trăm” · “Giảm âm lượng 10 phần trăm” · “Tắt tiếng” | Core Audio, đọc lại giá trị để xác minh |
| “Tìm trên web cách học Python” · “Mở youtube” · “Mở trang vnexpress.net” | Mở trình duyệt mặc định |
| “Chụp màn hình” | Lưu PNG vào `Pictures\NEXA` (không gửi đi đâu) |
| “Mấy giờ rồi” · “Xem thông tin hệ thống” | Giờ/ngày, CPU/RAM/pin thật |
| “Thu nhỏ cửa sổ” · “Khôi phục cửa sổ” · “Phóng to cửa sổ” · “Chuyển sang màn hình 2” · “Đóng cửa sổ” | Quản lý cửa sổ (đóng cần xác nhận) |
| “Cuộn lên 5 nấc” · “Sao chép” · “Dán” · “Chọn tất cả” · “Bấm phím control shift T” | Phím tắt/chuột |
| “Tìm tệp báo cáo” · “Tạo thư mục Dự án trong tài liệu” · “Mở thư mục tải về” | Tệp trong phạm vi cho phép |
| “Tạm dừng video” · “Phát tiếp video” | YouTube đã gắn |
| “Nexa, bật điều khiển bằng tay” · “Tắt điều khiển bằng tay” | Bật/tắt camera cử chỉ |
| “Mở trình duyệt, tìm hướng dẫn Python rồi giảm âm lượng xuống 30 phần trăm” | Chuỗi 3 bước (mọi bước phải hiểu chắc chắn) |
| “Dừng lại” · “Hủy” · “Đồng ý” / “Không” | Dừng khẩn cấp · hủy tác vụ · trả lời xác nhận |

**Cần Gemini:** “Mở Notepad và viết một đoạn giới thiệu ngắn về NXS MEDIA” (soạn **bản nháp**, không tự gửi/đăng),
hội thoại tự nhiên, các cách nói linh hoạt, “Đọc màn hình và tóm tắt giúp anh” (khi bật Screen Vision).
Khi Gemini không khả dụng, NEXA báo “Chế độ lệnh cơ bản” kèm lý do, không đoán rồi làm yêu cầu phức tạp.

Câu thiếu thông tin → NEXA hỏi lại đúng phần thiếu (ví dụ “Mở” → “Anh muốn em mở ứng dụng nào ạ?”; câu trả lời
tiếp theo được ghép vào lệnh). Nhận dạng giọng nói **không** phải xác thực danh tính người nói.

### Sáu cử chỉ (v1.3: giữ tư thế thay cho vuốt — chi tiết [docs/gestures.md](docs/gestures.md))

Mọi cử chỉ là **một tư thế tĩnh giữ yên ~0,5–0,65 giây** — không cần vuốt, nên đưa tay vào/ra khung hình không
kích hoạt nhầm, và mỗi lệnh có một hình dạng bàn tay riêng (khác nhau ở số ngón duỗi và hướng).

| Tư thế (giữ yên) | Sự kiện | Kết quả |
| --- | --- | --- |
| 👉 Chỉ ngón trỏ sang phải (các ngón khác co) | `MOVE_WINDOW_TO_MONITOR_2` | Chuyển cửa sổ hiện tại từ màn hình 1 sang màn hình 2 |
| 👎 Ngón cái chỉ xuống (4 ngón nắm lại) | `MINIMIZE_ACTIVE_WINDOW` | Thu nhỏ xuống thanh tác vụ (như nút −) |
| 👍 Ngón cái chỉ lên (4 ngón nắm lại) | `RESTORE_LAST_MINIMIZED_WINDOW` | Khôi phục đúng cửa sổ NEXA vừa thu nhỏ |
| ✊ Nắm tay, ngón cái áp vào | `YOUTUBE_PAUSE` | Tạm dừng video YouTube đã gắn |
| 🖐 Xòe cả bàn tay ngay sau khi nắm tay | `YOUTUBE_RESUME` | Phát tiếp đúng video vừa tạm dừng |
| ✌ Hai ngón trỏ + giữa (giữ liên tục) | `SCROLL_UP` | Cuộn lên liên tục tới khi đổi tư thế |

Bật camera bằng nút **Bật cử chỉ** hoặc câu “Nexa, bật điều khiển bằng tay”. Chip **Camera: ĐANG DÙNG** và nhãn đỏ
trên bảng Cử chỉ báo camera đang bật. Nút **Cử chỉ ▸** mở bảng hiệu chuẩn (preview, tư thế, chuyển động, cooldown,
cửa sổ đích, màn hình nguồn/đích, mục tiêu YouTube, FPS đo được).

### Hai màn hình (xem [docs/dual_monitor.md](docs/dual_monitor.md))

Cài đặt → **Màn hình** → **Nhận diện màn hình** (hiện nhãn lớn trên từng màn hình) → chọn **nguồn (1)** và
**đích (2)** → **Lưu vai trò**. NEXA lưu đường dẫn thiết bị ổn định (không chỉ số thứ tự) và liệt kê lại màn hình trước
mỗi thao tác.

### YouTube (xem [browser_bridge/README.md](browser_bridge/README.md))

Khuyến nghị cài **NEXA Bridge** (Chrome/Edge): chạy `browser_bridge\install_bridge.ps1`, nạp thư mục
`browser_bridge\extension` bằng *Load unpacked*, mở video YouTube, bấm biểu tượng NEXA Bridge → **Gắn tab này**.
Không có bridge, NEXA có thể dùng Windows Media Controls (GSMTC) nhưng chỉ phân biệt được ứng dụng + tiêu đề.

### An toàn và dừng khẩn cấp

- Nút **DỪNG KHẨN CẤP** luôn hiển thị, phím **Ctrl+Alt+Esc**, hoặc nói “**Dừng lại**”: hủy hàng đợi và tác vụ,
  chặn kết quả Gemini đến muộn, nhả phím/chuột NEXA đang giữ, dừng giọng nói, **khóa điều khiển** cho tới khi anh bấm
  **Tiếp tục điều khiển**. Fail-safe PyAutoGUI (đưa chuột vào góc màn hình chính) vẫn bật.
- Hành động thường (mở ứng dụng, tìm web, âm lượng, sáu cử chỉ) chạy ngay. **Xóa (vào Thùng rác), ghi đè, đóng cửa sổ,
  phím tắt có thể gửi/đóng/chạy lệnh theo ngữ cảnh (Enter trong ứng dụng chat/trình duyệt/terminal, Alt+F4, Ctrl+W,
  Win+R, Shift+Delete…), mở tệp thực thi, tắt/khởi động lại máy, gửi ảnh lên Gemini** → hiện hộp xác nhận mô tả đúng
  đối tượng; xác nhận gắn với đúng hành động, hết hạn sau 30 s, và bị hủy nếu đối tượng thay đổi.
- Mức rủi ro do mã Python quyết định từ tham số + ngữ cảnh thật; không tin trường nào do model tự khai.
- Không cần quyền admin, không vượt UAC, không sửa cài đặt bảo mật, không thao tác màn hình khóa. Không lưu audio/video thô.

### Cập nhật v1.1 (tốc độ, nhấp chuột bằng giọng nói, toàn quyền, giọng robot nam)

- **Nhanh hơn:** Gemini dùng `thinking_level: minimal` (đo trên máy: ~2,6 s → ~1,4 s mỗi lượt; tự bỏ nếu model không
  hỗ trợ); câu trả lời được đọc **theo từng câu** — câu sau được tổng hợp trong lúc câu trước đang phát (đoạn dài bắt đầu
  nói sau ~3 s thay vì ~5,4 s); câu hay dùng được cache và tổng hợp sẵn khi khởi động; luồng loa luôn mở; STT
  `beam_size: 3`, kết thúc câu sau 600 ms im lặng.
- **Nhấp chuột bằng giọng nói** (lệnh cơ bản, không cần Gemini): “bấm vào nút Lưu”, “click Tải về”, “chọn tab Cài đặt”
  (UI Automation theo tên), “nhấp chuột tại 500 300”, “nhấp đúp tại 10 20”, “nhấp chuột phải tại 300 400”,
  “nhấp vào đây”, “nhấn enter”.
- **Toàn quyền** (Cài đặt → AI → Quyền điều khiển, hoặc `safety.autonomy: full`): NEXA thực hiện mọi lệnh **không hỏi
  xác nhận** (kể cả nhấp tọa độ, bấm Gửi/Xóa, Enter trong ứng dụng chat, đóng cửa sổ, xóa vào Thùng rác, tắt máy hẹn
  60 s). Mỗi lần tự duyệt được ghi trong bảng Tác vụ (chấm tím) và log. Vẫn giữ: **DỪNG KHẨN CẤP / Ctrl+Alt+Esc /
  “Dừng lại”**, xóa chỉ vào Thùng rác, và bước xem trước ảnh trước khi gửi màn hình lên Gemini. Lưu ý: nhận dạng giọng
  nói có thể nghe nhầm và lệnh nghe nhầm cũng được chạy ngay. Chip **Quyền: TOÀN QUYỀN** hiển thị trên thanh trạng thái.
- **Giọng robot nam:** Edge `vi-VN-NamMinhNeural` (cần Internet) hạ cao độ `edge_pitch_hz: -12` + hiệu ứng `robot`
  (ring modulation + vang kim loại, `effect_strength` 0..1). Mất mạng → giọng Windows (Microsoft An) hạ cao độ + hiệu
  ứng robot. Chỉnh ở Cài đặt → Giọng nói. Nghe mẫu: `release/giong_robot_nam_mau.wav`.

### Cập nhật v2.0 — AI tạo và xem mô hình 3D (chi tiết [docs/three_d.md](docs/three_d.md))

- Nói/gõ: “**tạo bu-lông M8 dài 30 mm bước ren 1,25**”, “**tạo UAV mini bốn cánh thân carbon đen, camera phía trước**”,
  “tạo xe tự hành 6 bánh có lidar”, “tạo robot hình người”, “tạo robot bốn chân”, “tạo trực thăng”, “**tạo ca nô cao tốc
  dài 6 m**”, “tạo tàu cá dài 12 m”, “tạo du thuyền hai máy”. Thiếu thông số bắt buộc thì NEXA hỏi lại (ví dụ chiều dài
  bu-lông). Gemini chỉ lập **ModelSpec JSON**; hình học do CAD tham số cục bộ (manifold3d, **không cần Internet**) dựng —
  bu-lông có ren helix ISO kỹ thuật, bánh răng thân khai, cánh quạt NACA, thân tàu đáy chữ V. Mô hình kỹ thuật có chi
  tiết như thiết bị thật (rãnh ghép tấm, ốc, khe tản nhiệt, cáp, khớp servo, đèn, cảm biến, lan can…) và vật liệu PBR có
  texture (kim loại chải, sơn, cao su, nhựa nhám), vẫn tách/lắp được theo đúng logic lắp ráp.
- Vật thể tự do (“tạo ghế gỗ có tựa lưng”, “tạo tai nghe màu đen”…):
  - **Mức 2** (mặc định, cần Gemini): Gemini thiết kế từng bộ phận bằng CAD DSL an toàn (không chạy mã), NEXA tự gửi lỗi
    lại cho Gemini sửa, rồi cho Gemini xem ảnh 6 góc để tinh chỉnh; có bộ phận để tách/xem chi tiết. ~20–100 s.
  - **Mức 3**: Tripo/Meshy nếu có key trả phí; hoặc **miễn phí** qua Hugging Face Space (ảnh FLUX → TRELLIS/Hunyuan3D) khi
    nói “chất lượng cao”/“bằng hugging face” hoặc khi mức 2 không đạt. Nên đặt `HF_TOKEN` (miễn phí) trong `.env` vì hạn
    mức GPU ẩn danh rất nhỏ. Không có dịch vụ nào dùng được thì NEXA nói rõ, không giả lập kết quả.
- Mỗi mô hình được chấm điểm 0–100 (kích thước 30, hình dạng 25, cấu trúc bộ phận 20, vật liệu 15, hình học 10) và chỉ
  đạt khi ≥ 90 và qua mọi cổng bắt buộc. Kết quả là mô hình minh họa, **chưa được kiểm chứng để chế tạo**.
- Trình xem Qt Quick 3D: xoay/thu phóng bằng chuột, chọn bộ phận, cây bộ phận, X-quang, khung dây, xuất GLB/STL/OBJ/3MF.
  Giọng nói: “tách mô hình ra”, “lắp lại”, “xem chi tiết cánh quạt trước trái”, “chỉ hiện động cơ”, “xoay trái 30 độ”.
- Khi viewer mở, cử chỉ tay dành riêng cho mô hình: 🖐 bàn tay mở + di chuyển = xoay; ✊ giữ 0,5 s → 🖐 mở tay = tách;
  ✊ giữ = lắp lại; ✌ hai ngón lên/xuống = thu phóng. Dừng khẩn cấp hủy job đang tạo và khóa cử chỉ viewer.

### Cập nhật v1.9 (chuột bằng tay, xem [docs/gestures.md](docs/gestures.md))

- Nói "**bật chuột bằng tay**" hoặc bấm **Chuột bằng tay** trong bảng Cử chỉ. Di tay để di con trỏ (kiểu touchpad, có
  gia tốc, đi qua cả hai màn hình). 🤏 Chụm ngón cái + ngón trỏ = click, chụm hai lần = click đúp, chụm giữ rồi kéo =
  kéo thả. Chụm ngón cái + ngón giữa = click phải. ✌ Hai ngón đưa lên/xuống = cuộn. ✊ Nắm tay = nhấc tay, đặt lại chỗ khác.
- Trong lúc bật, sáu cử chỉ lệnh tạm ngưng. Cầm chuột thật thì NEXA tự nhường. Mất tay, tắt chế độ hoặc dừng khẩn cấp
  thì nút đang giữ được nhả ngay. Góc fail-safe của màn hình chính vẫn là dừng khẩn cấp.

### Cập nhật v1.8 (gợi ý ngữ cảnh cho nhận dạng + công cụ nghiên cứu, xem [docs/research_asr.md](docs/research_asr.md))

- **Whisper được gợi ý theo ứng dụng đang mở** (`stt.bias_mode: context`, mặc định): khi anh bắt đầu nói, NEXA đọc tên
  tiến trình và tiêu đề các cửa sổ đang hiển thị ở luồng nền (~23 ms lần đầu), chỉ giữ tên nằm trong từ vựng đã biết
  (Zalo, ChatGPT, Photoshop, Telegram…), rồi đặt các tên đó lên đầu danh sách gợi ý. Tiêu đề tài liệu và tin nhắn
  không bao giờ vào gợi ý. `static` = chỉ danh sách cố định như trước; `none` = không gợi ý (dùng để đối chứng).
- **Thu dữ liệu nghiên cứu** (`research.record_corpus`, **tắt mặc định**): lưu mỗi câu nói (WAV 16 kHz) và kết quả nhận
  dạng vào `%LOCALAPPDATA%\NEXA\asr_corpus`. Gán nhãn bằng `scripts\asr_corpus.py export/import`.
- **Bộ đo chuẩn** `scripts\asr_benchmark.py`: đo WER, CER, lỗi tên riêng, tỷ lệ lệnh đúng và độ trễ theo model × chế độ
  gợi ý × nhiễu, kèm kiểm định ghép cặp (bootstrap, McNemar). `scripts\asr_synth.py` tạo bộ câu tổng hợp để thử nhanh.

### Cập nhật v1.7.1 (nghe rõ lệnh khi đang phát nhạc)

Log 24/09/2026: sau "mở nhạc", mỗi câu bị ghi đủ 12,5 s ("Bỏ qua quảng cáo Bỏ qua quảng cáo", "Đổi video Mở Antigravity"
dính hai lệnh rồi rơi sang Gemini). Nguyên nhân: sau lệnh mở nhạc NEXA thôi vặn nhỏ nhạc, và video bắt đầu phát SAU lúc
NEXA bắt đầu nghe thì không bị vặn nhỏ; bộ tách câu học nền ồn lúc còn yên lặng nên coi nhạc là tiếng nói.

- Luôn vặn nhỏ ứng dụng khác khi NEXA nghe (kể cả sau lệnh mở nhạc), quét lại mỗi 0,4 s để bắt cả video vừa bắt
  đầu phát (mỗi lần quét ~0,6 ms). Nói xong là trả âm lượng ngay.
- Sau lệnh mở nhạc: nếu một lượt chờ (8 s) không có lệnh, NEXA về chế độ chờ và trả nhạc về mức cũ — vỗ tay khi cần.
- Bộ tách câu có nền ồn động trong lúc ghi (mô phỏng: video bắt đầu phát khi đang nghe → chốt câu ở 3,9 s thay vì 13,2 s;
  câu dài 6 s, đuôi câu nhỏ 10 dB vẫn không bị cắt).
- Đang phát nhạc: câu không phải lệnh (thường là lời bài hát lọt mic) bị bỏ qua, không gửi Gemini; hai câu như vậy
  liên tiếp thì về chế độ chờ. Muốn hỏi Gemini lúc nhạc đang phát: gọi "Nexa, …" hoặc vỗ tay trước.
- Lệnh cơ bản mới: "đổi video", "bài khác", "bài tiếp theo", "chuyển bài" → video kế tiếp của lần tìm gần nhất.
- Nhớ kết quả tìm YouTube 10 phút: "đổi video"/"mở video thứ 2" không phải tìm lại (~1 s mỗi lần).

### Cập nhật v1.7 (thao tác tab nhanh hơn, bỏ quảng cáo tức thì, ngủ canh gác)

Đo trên máy anh ngày 24/09/2026 (trang YouTube ~1.160 phần tử giao diện; trang dùng lâu còn nặng hơn nhiều):

| Việc | Trước | Nay |
| --- | --- | --- |
| Một lượt kiểm tra quảng cáo (tìm nút + nhận quảng cáo) | ~450 ms | ~7 ms |
| "Bỏ qua quảng cáo" khi không có quảng cáo | ≥ 450 ms (tăng theo độ nặng trang) | ~10 ms |
| Đọc danh sách tab (sau lần đầu) | 64 ms/cửa sổ, lặp tới 22 lần khi đóng tab | ~2 ms |
| Đọc control để bấm theo tên (Edge) | 734 ms | 122 ms |

- **Bỏ quảng cáo**: chỉ đọc trình phát (`#movie_player`) thay vì cả trang; nhận quảng cáo bằng lớp `ad-showing` của
  YouTube (trước đây tìm chữ "quảng cáo" khắp trang nên nhầm khi tiêu đề/bình luận có chữ đó); bấm liền 2 quảng cáo
  liên tiếp; Invoke không ăn thì nhấp chuột thật; quét mỗi 0,25 s. Tự bỏ quảng cáo quét mỗi 1 s mà vẫn nhẹ.
- **Tab trình duyệt**: tìm thanh tab/trang/thanh địa chỉ trong khung trình duyệt (không đi vào trang web), nhớ theo cửa sổ.
- **Nghe nhầm**: "Bỏ quán cáo", "Bỏ quán cao" và câu bị Whisper lặp đôi giờ chạy thẳng lệnh cơ bản (trước rơi sang
  Gemini và chờ ~8 s).
- **Gemini**: nhớ model đang chạy được qua các lần mở NEXA (`%LOCALAPPDATA%\NEXA\gemini_state.json`) — không còn chờ
  ~7 s model chính quá tải ở câu đầu mỗi lần khởi động.
- Log ghi thời gian từng thao tác (`Công cụ skip_youtube_ad: OK trong 12 ms`) để lần sau tìm chỗ chậm/lỗi nhanh.
- **Ngủ canh gác**: xem mục *Đánh thức bằng vỗ tay*.

### Cập nhật v1.6 (tự động hóa công việc + quản trị máy)

| Anh nói | NEXA làm |
| --- | --- |
| "tạo file Word/Excel/PowerPoint mới" (kèm tên tùy ý) | Tạo tài liệu mới qua Office COM; có tên thì lưu vào Tài liệu, trùng tên thì thêm " (2)" — không ghi đè |
| "tạo file mới trong VS Code", "tạo file main.py trong VS Code" | Không tên: Ctrl+N trong VS Code. Có tên: tạo tệp thật rồi mở bằng `code -r` |
| "bỏ qua quảng cáo" | Bấm nút "Bỏ qua" của YouTube qua UI Automation; quảng cáo chưa cho bỏ thì chờ tới khi nút hiện (tối đa 12 giây) |
| "bật/tắt tự động bỏ qua quảng cáo" | Luồng nền tự bấm "Bỏ qua" mỗi khi hiện quảng cáo (`youtube.auto_skip_ads`) |
| "kiểm tra tin nhắn Zalo", "có ai nhắn tin cho tôi không" | Đọc danh sách trò chuyện Zalo, trả về **tên người/nhóm + số tin chưa đọc**; KHÔNG đọc nội dung, không ghi nội dung vào log |
| "chạy với quyền quản trị" | Mở lại NEXA qua hộp thoại UAC của Windows (anh bấm "Có"), rồi tự thoát bản cũ |
| "mở PowerShell quyền quản trị", "mở Task Manager / Device Manager / Services / Registry…" | Mở công cụ quản trị Windows |
| "ứng dụng nào đang ngốn RAM", "xem dung lượng ổ đĩa", "kiểm tra mạng" | Báo top CPU/RAM, dung lượng từng ổ, Wi-Fi + IP + có Internet không |
| "tắt Chrome đang treo", "buộc tắt Zalo" | Đóng lịch sự trước (ứng dụng còn kịp hỏi lưu), chỉ buộc dừng khi anh nói "buộc tắt"; tiến trình hệ thống thiết yếu luôn bị từ chối |

**Câu trả lời dài chỉ đọc phần chính:** "kiểm tra mạng" trước đây đọc to cả dãy IP mất 15,5 giây; nay loa chỉ đọc
"Máy đang có Internet qua Wi-Fi …" (5,2 giây), địa chỉ IP vẫn hiện trên màn hình. Tương tự với dung lượng ổ đĩa và
ứng dụng ngốn máy ("ngốn RAM" → đọc RAM trước, "ngốn CPU" → đọc CPU trước).

**Giới hạn an toàn:** NEXA không tắt UAC và không tự bỏ qua hộp thoại UAC — mỗi lần nâng quyền anh vẫn bấm xác nhận.
Không chặn quảng cáo bằng script, chỉ bấm nút "Bỏ qua" khi YouTube cho phép. Không đọc nội dung tin nhắn Zalo.

### Cập nhật v1.5 (hiểu từ tiếng Anh / viết tắt, không bị kẹt chờ Gemini)

- **Tìm/hỏi ngay trong trang được nêu tên** (`nexa/ai/site_search.py`, công cụ `site_search`): "tìm kiếm trong ChatGPT
  về Nguyễn Xuân Sơn", "hỏi ChatGPT về…", "mở ChatGPT rồi tìm…" mở chatgpt.com với câu hỏi tự gửi (bật tìm trên web);
  tương tự Claude, Perplexity, YouTube, Facebook, TikTok, Wikipedia, Google Maps/Hình ảnh/Tin tức/Dịch, Shopee, Lazada,
  Tiki, GitHub, Spotify, Gmail, Drive, Bing, bằng địa chỉ tìm kiếm chính thức của trang. Với ChatGPT/Claude/Perplexity
  NEXA kiểm tra câu hỏi đã gửi thật chưa (địa chỉ chuyển sang /c/…); nếu trang bỏ qua câu hỏi, NEXA gõ vào ô chat rồi
  Enter — chỉ khi con trỏ đang ở ô soạn thảo của đúng trang đó; không chắc thì báo anh bấm gửi.
  "tìm trên Google…" và "tìm <gì đó>" không nêu trang vẫn tìm Google như cũ.
- **"Đóng <tên>" chạy tại chỗ** (công cụ `close_named`): "đóng ChatGPT", "tắt YouTube", "đóng tab YouTube" đóng đúng
  TAB trình duyệt đó (chọn tab qua UI Automation rồi bấm nút "Đóng tab", không dùng chuột, không đóng cả trình duyệt);
  "đóng VS Code", "thoát Zalo", "tắt ứng dụng Antigravity" đóng cửa sổ ứng dụng (đóng thông thường, ứng dụng vẫn hỏi
  lưu). "đóng tab" / "đóng tab này" vẫn là Ctrl+W; "tắt tiếng / tắt máy / tắt wifi / tắt nhạc" không bị hiểu là đóng app.
- **Gemini tự đổi model khi Google quá tải** (`ai.fallback_models`): model chính lỗi 503/504/quá hạn thì chuyển ngay
  sang model dự phòng (3.6-flash, 3.1-flash-lite); model lỗi được "cho nghỉ" 5 phút; model vừa trả lời được dùng trước
  cho các câu sau. Nhóm luồng gọi Gemini 3 → 8 để yêu cầu bị treo không chặn câu hỏi mới. Lỗi phía Google được báo
  rõ ("Máy chủ Gemini của Google đang quá tải…") kèm nhắc lệnh điều khiển máy vẫn chạy.
- **Nhận dạng chạy trên GPU** (`stt.model: auto`, `stt.device: auto`): có GPU NVIDIA thì dùng **large-v3-turbo**
  trên GPU, không có thì small trên CPU như cũ; GPU lỗi thì tự về CPU. Đo trên máy này (RTX 4050): **1,63 s → 0,33 s
  mỗi câu** và nhận đúng lệnh tiếng Anh nhiều hơn. Cần gói `nvidia-cublas-cu12` (đã thêm vào requirements.txt).
- **Từ tiếng Anh nói kiểu Việt** (`nexa/ai/english_terms.py`): "phôn đơ" → folder, "phai" → file, "iu túp" → YouTube,
  "gu gồ" → Google, "oai phai" → Wi-Fi, "cóp pi" → copy, "pi đi ép" → PDF… ("phai màu", "rẽ phải" không bị đổi).
  Gợi ý của Whisper chuyển sang câu mẫu trộn tiếng Anh để ghi đúng chính tả ngay từ đầu.
- **"Mở file/folder <tên>"** chạy tại chỗ: tìm theo tên trong các thư mục được phép rồi mở; nhiều kết quả thì hỏi lại.
  "trong máy tôi" = tìm khắp nơi. "tạo folder…", "tìm file…" dùng chung mẫu với "thư mục", "tệp".
- **Sửa chữ "Mở" bị nghe nhầm** thành "Mà/Má/Mơ…" khi phía sau là ứng dụng/trang web đã biết ("Mà yêu đôi" → mở YouTube).
- **Lệnh mới thay lệnh cũ:** nói lệnh mới trong lúc Gemini còn đang nghĩ thì câu cũ bị hủy và câu mới chạy ngay
  (trước đây bị từ chối "em đang làm tác vụ trước").
- **Hỏi gì trả lời nấy:** "mấy giờ rồi" → "Bây giờ là 22 giờ 24."; "hôm nay ngày bao nhiêu" → chỉ đọc ngày.

### Cập nhật v1.4 (không cần gắn tab, phản hồi nhanh hơn)

- **Không cần gắn tab YouTube:** "tạm dừng" / ✊ tự tìm video **đang phát** trong trình duyệt; "phát tiếp" / 🖐 tìm
  video **đang dừng**, ưu tiên video NEXA vừa mở. Chỉ điều khiển trình duyệt (không đụng Spotify…). Không cần cài
  extension — dùng Windows Media Controls; extension NEXA Bridge vẫn dùng được để phân biệt chính xác từng tab.
- **Sửa lỗi** tạm dừng/phát tiếp qua Windows Media Controls (`TypeError: A coroutine object is required`).
- **Nói ngắn:** loa chỉ đọc "Đã mở video đầu tiên." — tên video đầy đủ hiện trên màn hình. Các lần đánh thức sau lần
  đầu chỉ nói "Dạ, em nghe.". Các câu xác nhận hay dùng được tạo sẵn lúc khởi động (phát ngay, không chờ mạng).
- **Vặn nhỏ nhạc/video khi nghe lệnh** (`audio.duck_media`, `audio.duck_level: 0.2`): âm thanh ứng dụng khác lọt
  vào mic làm Whisper nghe thành câu vô nghĩa. NEXA hạ các ứng dụng đang phát còn 20% trong lúc nghe, trả lại ngay khi
  anh nói xong; sau lệnh mở/phát nhạc thì không hạ nữa trong phiên đó. Không đụng âm lượng loa tổng.
- **Nghe không rõ thì hỏi lại:** câu Whisper kém chắc chắn (`stt.min_confidence_logprob: -0.9`) mà không khớp lệnh
  cơ bản nào thì NEXA nói "Em nghe chưa rõ, anh nói lại giúp em." thay vì gửi Gemini đoán. Log ghi độ tin cậy mỗi câu.
- **Gemini không làm treo:** mỗi lần hỏi có hạn tổng 20 giây kể cả thử lại (`ai.request_budget_s`; trước đây có thể
  tới ~100 giây), thời gian chờ mỗi request 30 → 15 giây. Sau 2 giây chưa có trả lời, NEXA nói "Dạ, anh chờ em chút.".
- **Câu có lời chào vẫn chạy tại chỗ:** "Xin chào, cho tôi hỏi hôm nay ngày bao nhiêu?" trả lời ngay trên máy thay vì
  gửi Gemini.
- **Cắt khoảng lặng** của giọng Edge (0,25 s đầu + 0,8–1,3 s cuối): "Dạ." 1,87 s → 0,44 s. Chờ im lặng cuối câu
  600 → 500 ms, chặn mic sau khi nói 400 → 300 ms.

### Cập nhật v1.3 (nhận đúng tên ứng dụng khi nói)

- **Whisper được gợi ý tên riêng** (`hotwords`): VS Code, ChatGPT, Claude, Zalo, Word, Excel… cùng các ứng dụng anh
  tự thêm trong Cài đặt → Ứng dụng. Thêm tên khác vào `stt.hotwords` trong `config/settings.yaml`.
- **`beam_size` 1 → 3**: đo trên máy chỉ chậm thêm ~0,1 giây/câu nhưng đúng hơn (5 không hơn 3).
- **Bảng tên nghe nhầm** (`nexa/desktop/app_aliases.py`): "VS Của", "video scop", "viết của" → Visual Studio Code;
  "chát dù bị tùy" → ChatGPT; "clout" → Claude… Dịch vụ web chưa cài (ChatGPT, Claude, Gemini…) mở bằng trình duyệt.
- **Khớp mờ có kiểm soát**: tên lệch nhẹ ("Zaloo", "Visual Answer Studio Code") vẫn ra đúng ứng dụng, nhưng chỉ khi
  ứng viên tốt nhất bỏ xa ứng viên thứ hai; tên mơ hồ ("Git") thì NEXA hỏi lại thay vì đoán.
- **"Mở Chrome" mở đúng Chrome** (trước đây mở trình duyệt mặc định, trên máy này là Edge).

### Cập nhật v1.2 (camera bật cùng NEXA, tối ưu cử chỉ và giọng nói)

- **Camera khởi động cùng NEXA** (`gestures.enabled_on_start: true`, Cài đặt → Cử chỉ): khoảng 4 giây sau khi mở app,
  camera bật và nhận diện cử chỉ ngay, kể cả khi NEXA đang chờ vỗ tay. Chip **Camera: ĐANG DÙNG** luôn hiển thị.
- **Cử chỉ:** bộ lọc One Euro thay EMA (giảm rung khi tay đứng yên, ít trễ khi vuốt nhanh; `timing.filter`,
  `euro_min_cutoff`, `euro_beta` trong `gestures.yaml`); theo dõi 1 tay (`gestures.num_hands: 1`); camera ưu tiên MJPG
  30 FPS; preview chỉ vẽ khi bảng Cử chỉ đang mở. Đo trên máy: 29,5 FPS xử lý ≈ 29,6 FPS camera (không dồn khung).
- **Giọng nói:** faster-whisper dùng số luồng = số nhân vật lý (đo: 1,97 s → 1,70 s mỗi câu); chặn mic sau khi NEXA
  nói giảm còn 300 ms.
- **Giao diện:** Canvas của quả cầu vẽ tối đa 45 hình/giây (24 khi chờ) thay vì theo tần số màn hình (~143) để nhường
  CPU cho nhận dạng giọng nói và cử chỉ; vòng quỹ đạo/hạt sáng vẫn chạy bằng GPU.

### Cập nhật v1.3 (mở video YouTube, không còn nhấp đoán mò)

- **Mở video bằng giọng nói:** “mở video đầu tiên”, “mở video thứ hai” (theo từ khóa vừa tìm), “phát nhạc Tíc Tắc”,
  “bật bài hát … trên YouTube”, “mở video hướng dẫn nấu phở”, “tìm trên YouTube …”. NEXA tìm trên YouTube, mở thẳng
  đúng video rồi **kiểm chứng** cửa sổ trình duyệt đã hiện tiêu đề video mới báo “Đã mở”.
- **Gemini không được nhấp tọa độ tự đoán** (nó không nhìn thấy màn hình): tọa độ chỉ được chấp nhận nếu nằm trong một
  control vừa đọc bằng `list_ui_controls`; nếu không, công cụ từ chối và Gemini phải đọc giao diện rồi bấm theo tên.
  `list_ui_controls` trả thêm vị trí, sắp theo thứ tự đọc; `click_ui_control` có `index` (“mục thứ mấy”).
- Gemini nhận ngữ cảnh các lệnh cơ bản vừa chạy (ví dụ vừa tìm “nhạc Tíc Tắc”).
- Sửa nghe nhầm: bỏ từ đệm đầu câu (“Nhất mở…”), “chương trình nghị” → “trình duyệt”, “tích tốc” → “Tíc Tắc”.

### Sinh code cho kỹ sư phần mềm (chi tiết [docs/code.md](docs/code.md))

- Bấm **“Sinh code ▸”** hoặc nói/gõ: “**viết code python đọc file CSV và tính tổng theo tháng**”, “tạo script
  PowerShell dọn thư mục Temp”, “sửa code thêm xử lý lỗi…”, “chạy thử code”, “hủy viết code”.
- Gemini viết code kèm kiểm thử. NEXA chuẩn hóa định dạng rồi kiểm tra: Python bằng compile và pyflakes, JS bằng
  node --check, cùng PowerShell, Go, JSON, YAML, TOML. Còn lỗi thì NEXA tự nhờ Gemini sửa, tối đa 2 lượt.
- Code hiện trên bảng xem, tô màu theme One Dark, có số dòng và danh sách lỗi. **Chỉ sao chép khi anh bấm nút**; ngoài
  ra có thể lưu ra `Documents\NEXA Code` hoặc bấm ▶ Chạy thử. Chạy thử dùng thư mục tạm, không mang biến bí mật, có giới
  hạn thời gian, nhưng **không phải sandbox**.

---

## 5. Bảng chức năng: offline / online / model / key / Windows

| Chức năng | Offline | Cần Internet | Cần model | Cần Gemini key | Phụ thuộc Windows |
| --- | :---: | :---: | :---: | :---: | :---: |
| Đánh thức bằng vỗ tay | ✓ | | | | |
| Nhận dạng tiếng Việt (faster-whisper) | ✓ | lần tải đầu | ✓ | | |
| Lệnh cơ bản (mở app, âm lượng, cửa sổ, tệp, phím…) | ✓ | | | | ✓ |
| TTS edge-tts | | ✓ | | | |
| TTS WinRT (giọng Windows vi-VN) | ✓ | | giọng Windows | | ✓ |
| Sáu cử chỉ tay (MediaPipe) | ✓ | lần tải đầu | ✓ | | ✓ (thao tác) |
| Hai màn hình, thu nhỏ/khôi phục | ✓ | | | | ✓ |
| YouTube qua NEXA Bridge | ✓ (cục bộ) | để xem YouTube | | | Chrome/Edge |
| YouTube qua GSMTC | ✓ | | | | ✓ |
| Hội thoại, lệnh linh hoạt, soạn nội dung, nhiều bước (Gemini) | | ✓ | | ✓ | |
| Đọc màn hình (Gemini Vision) | | ✓ | | ✓ + bật `NEXA_CLOUD_SCREEN_VISION` | ✓ |
| Mô hình 3D tham số (CAD cục bộ, viewer, cử chỉ) | ✓ | | | lập kế hoạch/đánh giá (tùy chọn) | |
| Mô hình 3D tự do mức 2 (Gemini thiết kế CAD DSL) | | ✓ | | ✓ | |
| Mô hình 3D tự do mức 3 (Tripo / Meshy / Hugging Face Space) | | ✓ | | Tripo/Meshy: key riêng; HF: miễn phí (`HF_TOKEN` khuyến nghị) | |

---

## 6. Cây thư mục thực tế và trách nhiệm

```
NEXA/
├─ main.py                     điểm chạy duy nhất (đặt DPI Per-Monitor v2 trước khi nạp Qt)
├─ requirements.txt / requirements-dev.txt
├─ .env.example · .gitignore · README.md
├─ setup_windows.bat · start_windows.bat
├─ config/  settings.example.yaml · gestures.yaml   (settings.yaml sinh cục bộ, không bàn giao)
├─ nexa/
│  ├─ app.py                   khởi tạo, nối module, QML, overlay, shutdown sạch, chống chạy 2 bản
│  ├─ core/  state_machine.py · events.py · controller.py · executor.py · safety.py · hotkeys.py
│  ├─ audio/ pipeline.py (mic duy nhất + VAD) · clap_detector.py · stt.py · context_bias.py · tts.py · sfx.py
│  ├─ ai/    gemini_provider.py · intent_router.py · tool_registry.py · prompts.py · screen_vision.py
│  ├─ vision/ camera.py · hand_tracker.py · gesture_features.py · gesture_state_machine.py · gesture_router.py · engine.py
│  │          air_mouse.py (chuột bằng tay)
│  ├─ desktop/ win32api.py · monitors.py · windows.py · window_history.py · media.py · bridge_server.py
│  │           input_control.py · apps_and_files.py · system.py · uia.py
│  ├─ ui/    bridge.py · overlay.py · qml/ Main.qml · Orb.qml · Settings.qml · GesturePanel.qml · Overlay.qml
│  ├─ research/ corpus.py (thu dữ liệu) · asr_metrics.py (WER, tên riêng, lệnh đúng, kiểm định) · templates.py
│  └─ utils/ config.py · logging.py · text.py
├─ assets/  sounds/ (wav tạo bằng scripts/generate_sounds.py) · fonts/ (không phân phối font; dùng Segoe UI của Windows)
├─ models/  cache model (không đưa vào Git/ZIP)
├─ scripts/ download_models.py · diagnose.py · build_exe.py · generate_sounds.py
│           asr_synth.py · asr_benchmark.py · asr_corpus.py (nghiên cứu nhận dạng)
├─ tests/   test_clap.py · test_gestures.py · test_windows.py · test_media.py · test_gemini.py · test_safety.py
│           test_intent_and_state.py · fake_win32.py · hand_synth.py · conftest.py
├─ docs/    gestures.md · dual_monitor.md · manual_tests.md · research_asr.md
└─ browser_bridge/ extension/(manifest.json · background.js · content.js · popup.html · popup.js)
                   native_host.py · native_host.bat · install_bridge.ps1 · README.md
```

Module thêm so với cây yêu cầu: `core/hotkeys.py` (Ctrl+Alt+Esc, Ctrl+Alt+N), `desktop/win32api.py` (lớp ctypes
dùng chung, thay được bằng bản giả khi kiểm thử), `desktop/bridge_server.py` (IPC bridge), `desktop/system.py`
(âm lượng, CPU/RAM, nguồn), `desktop/uia.py` (UI Automation), `vision/engine.py` (nối camera→router),
`ai/screen_vision.py`, `audio/sfx.py`, `utils/text.py`.

---

## 7. Kiểm thử

```bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

Kiểm thử tự động không điều khiển máy thật: Win32 được giả lập (`tests/fake_win32.py`), tệp dùng thư mục tạm,
Thùng rác được mock, Gemini dùng client giả với kiểu dữ liệu thật của SDK. Checklist kiểm tra thủ công trên máy thật:
[docs/manual_tests.md](docs/manual_tests.md).

### Kết quả kiểm tra

Xem mục “Kết quả kiểm tra” trong [docs/manual_tests.md](docs/manual_tests.md) — tách rõ phần đã kiểm tra bằng công cụ,
phần kiểm tra mô phỏng và phần cần anh xác nhận trên máy thật.

---

## 8. Build EXE (tùy chọn)

```bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python scripts\build_exe.py
```

Tạo `dist\NEXA\NEXA.exe` (one-folder, `--windowed`). Không đóng gói `.env`, `settings.yaml`, log hay model lớn; chép
`models\` vào cạnh `NEXA.exe` hoặc để NEXA tải ở lần chạy đầu. Bridge YouTube vẫn gọi `native_host.py` bằng Python của
`.venv`. **ZIP mã nguồn không phải là bản EXE đã kiểm chứng.**

---

## 9. Khắc phục lỗi

| Hiện tượng | Cách xử lý |
| --- | --- |
| Chip **Mic: lỗi** | Cài đặt → Âm thanh: chọn mic khác / Host API khác (MME ↔ WASAPI). Kiểm tra *Settings → Privacy → Microphone* cho ứng dụng desktop. |
| Vỗ tay không đánh thức | Bật *Chế độ thử*, xem ngưỡng; tăng độ nhạy hoặc giảm *mức tối thiểu tuyệt đối*; vỗ tay gần mic hơn. |
| Bị đánh thức nhầm | Chuyển sang **hai tiếng vỗ tay**, giảm độ nhạy, hiệu chuẩn lại nền ồn. |
| Nghe nhầm lệnh | Nói gần mic, rõ; đổi STT sang `medium` hoặc `large-v3-turbo` (chậm hơn trên CPU). Từ tiếng Anh (Python…) hay bị nghe sai. |
| Không có giọng nói | Cài đặt → Giọng nói xem backend nào khả dụng. Không Internet → cài giọng tiếng Việt: *Settings → Time & language → Speech → Add voices → Tiếng Việt*. NEXA vẫn trả lời bằng chữ. |
| Loa Bluetooth trễ | Tai nghe Bluetooth có độ trễ phát; mic của tai nghe Bluetooth làm giảm chất lượng âm thanh (chế độ gọi). |
| “Chế độ lệnh cơ bản” | Xem lý do trong chip AI/Cài đặt → AI; kiểm tra `.env`, mạng, bấm *Kiểm tra kết nối Gemini*. |
| Gemini báo 404 model | Đổi `GEMINI_MODEL` sang model key của anh truy cập được. |
| Gemini báo 429 | Hết quota/tốc độ của tài khoản; chờ hoặc xem hạn mức trong Google AI Studio. |
| Camera không mở | Đóng ứng dụng khác đang dùng camera; bật *Privacy → Camera → Let desktop apps access*; đổi chỉ số camera. |
| Thiếu `hand_landmarker.task` | `.venv\Scripts\python scripts\download_models.py --hands` |
| Không chuyển được cửa sổ | Ứng dụng chạy quyền admin (UIPI) hoặc cửa sổ đặc biệt/fullscreen độc quyền — NEXA báo giới hạn thay vì giả thành công. |
| YouTube không phản hồi | Xem bridge trong Cài đặt → YouTube; gắn lại tab; trình duyệt có thể chặn tự phát (autoplay) — bấm vào video một lần. |
| Xem log | `logs\nexa.log` (xoay vòng 5 × 1 MB, đã lọc API key). |

---

## 10. Giới hạn hiện tại (nói rõ)

- NEXA **không** điều khiển được mọi ứng dụng trong mọi tình huống: chỉ những gì các công cụ hỗ trợ và Windows cho
  phép; không điều khiển ứng dụng chạy quyền admin khi NEXA chạy quyền thường, không thao tác UAC/màn hình khóa.
- Game/ứng dụng **fullscreen độc quyền** có thể không chuyển được màn hình; NEXA báo lỗi đúng.
- Khi TTS đang nói, mic tạm chặn (nghe/nói luân phiên) — **chưa hỗ trợ ngắt lời bằng giọng nói**; dùng nút Dừng /
  Ctrl+Alt+Esc / nút “Nói”.
- Cuộn bằng cử chỉ gửi bánh xe chuột: Windows cuộn cửa sổ **dưới con trỏ chuột**.
- Ngưỡng cử chỉ và vỗ tay là giá trị khởi đầu; cần hiệu chuẩn theo webcam, ánh sáng và phòng của anh.
- Gemini Live (audio-to-audio) chưa tích hợp — là nâng cấp tùy chọn sau khi luồng mic → STT → Gemini → TTS ổn định.
- Chuột bằng tay (v1.9) cập nhật con trỏ theo tốc độ camera (~30 lần/giây), nên chưa mượt bằng chuột thật. Ngưỡng
  chụm là giá trị khởi đầu, cần chỉnh theo webcam và tay của anh (docs/manual_tests.md).
- Lịch sử hội thoại chỉ lưu trong phiên (chưa có lưu lâu dài).
- Mô hình 3D (v2.0): CAD cục bộ là lưới tam giác (manifold3d), **không có STEP/B-rep**; chỉ các nhóm có mẫu tham số
  (bu-lông/đai ốc/bánh răng/trục…, UAV, xe tự hành, robot hình người, robot bốn chân, trực thăng). Tripo/Meshy mới kiểm
  thử bằng HTTP giả lập (chưa có key để chạy thật). Điểm chất lượng là cổng tự động, chưa có người chấm — không tuyên bố
  “chính xác 90%”. Mô hình không dùng để chế tạo khi chưa kiểm chứng kỹ thuật. Xem docs/three_d.md §10.

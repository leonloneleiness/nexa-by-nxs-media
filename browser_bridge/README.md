# NEXA Bridge — điều khiển đúng tab YouTube

Windows Media Controls (GSMTC) chỉ cho NEXA biết **ứng dụng** (ví dụ `MSEdge`) và **tiêu đề** media, không xác định
được **tab** nào. Để nắm tay/mở tay tạm dừng/phát tiếp đúng video anh chọn — kể cả khi trình duyệt không có focus hay
nằm ở màn hình còn lại — NEXA dùng extension nhỏ cho Chrome/Edge.

## Thành phần

| Tệp | Vai trò |
| --- | --- |
| `extension/manifest.json` | Manifest V3. Quyền: `nativeMessaging`; host: chỉ `https://www.youtube.com/*`. Có `key` cố định nên ID extension luôn là `ghkmpnijfoceebnoolnbhedljpelgnhp`. |
| `extension/content.js` | Chạy trên tab YouTube: đọc `videoId`, tiêu đề, `video.paused`; thực hiện `video.pause()` / `video.play()` khi được yêu cầu và đọc lại trạng thái. Từ chối nếu `videoId` đã đổi. |
| `extension/background.js` | Service worker: kết nối Native Messaging, chuyển tiếp lệnh tới đúng tab, báo tab đóng/đổi video. |
| `extension/popup.html`, `popup.js` | Danh sách tab YouTube, nút **Gắn tab này cho NEXA**, trạng thái kết nối. |
| `native_host.py` + `native_host.bat` | Native Messaging host do trình duyệt khởi chạy: kiểm tra origin đúng ID extension, chuyển tiếp JSON tới NEXA. |
| `install_bridge.ps1` | Đăng ký host **cho người dùng hiện tại** (HKCU, không cần admin) với Chrome và Edge. |

## Bảo mật

- Không bật remote debugging, không mở cổng TCP.
- Extension ↔ host: Native Messaging (stdin/stdout, khung 4 byte độ dài + JSON). Manifest host chỉ cho phép đúng
  `chrome-extension://ghkmpnijfoceebnoolnbhedljpelgnhp/`; host kiểm tra lại origin.
- Host ↔ NEXA: named pipe `\\.\pipe\nexa-bridge-<tên người dùng>` với xác thực challenge-response HMAC bằng khóa ngẫu
  nhiên 32 byte ở `%LOCALAPPDATA%\NEXA\bridge.key`. Chỉ trao đổi JSON (không pickle).
- Extension chỉ gửi `videoId`, tiêu đề, trạng thái phát của tab YouTube; không đọc cookie hay nội dung khác.
- Lệnh chỉ gồm `pause`, `play`, `state`, và luôn kèm `videoId` phải khớp.

## Cài đặt (Chrome hoặc Edge)

1. Đã chạy `setup_windows.bat` (cần `.venv` vì host chạy bằng Python của NEXA).
2. Đăng ký native host (một lần, cho người dùng hiện tại):
   ```bat
   powershell -ExecutionPolicy Bypass -File browser_bridge\install_bridge.ps1
   ```
   Gỡ: thêm `-Uninstall`.
3. Mở `chrome://extensions` (hoặc `edge://extensions`), bật **Developer mode**, bấm **Load unpacked**, chọn thư mục
   `browser_bridge\extension`. Kiểm tra ID hiển thị là `ghkmpnijfoceebnoolnbhedljpelgnhp`.
4. Chạy NEXA, mở một video YouTube, bấm biểu tượng **NEXA Bridge** trên thanh công cụ → **Gắn tab này cho NEXA**.
   NEXA hiện thông báo “Đã gắn video…”. Hoặc chọn trong NEXA: Cài đặt → **YouTube** → **Gắn**.

## Hành vi

- **Nắm tay** → nếu video đang phát thì `pause()`, đọc lại `paused === true` rồi mới báo thành công; nếu đã dừng thì giữ nguyên.
- **Mở tay** (ngay sau nắm tay đã tạm dừng) → nếu video đang dừng thì `play()`, đọc lại; nếu đang phát thì giữ nguyên.
- Tab bị đóng, chuyển sang video khác, hoặc trình duyệt ngắt kết nối → NEXA bỏ gắn mục tiêu, không điều khiển video khác.
- Trình duyệt có thể từ chối `play()` theo chính sách autoplay (`NotAllowedError`) — NEXA báo đúng, anh bấm vào video một lần.
- Không gửi phím Space/K, không giành focus.

## Giới hạn

- Hỗ trợ `https://www.youtube.com/*` (watch, shorts, live); không hỗ trợ video YouTube nhúng trong trang khác.
- Trình duyệt Chromium khác (Brave, Cốc Cốc, Opera) có đường dẫn registry riêng — cần tự đăng ký tương tự nếu muốn dùng.
- Bản EXE vẫn dùng Python trong `.venv` để chạy `native_host.py`.
- Chưa kiểm thử trên trình duyệt thật trong môi trường phát triển (việc cài extension/registry cần anh tự làm); phần
  giao thức và kênh named pipe đã có kiểm thử tự động (`tests/test_media.py`).

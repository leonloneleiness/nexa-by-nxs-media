# Hai màn hình: chọn nguồn/đích, DPI, cắm/rút màn hình

## Chọn màn hình nguồn “1” và đích “2”

1. Cài đặt → **Màn hình** → **Nhận diện màn hình**: mỗi màn hình hiện một nhãn lớn gồm tên GDI (DISPLAY1, DISPLAY2…),
   tên EDID của màn hình, độ phân giải, tỷ lệ scaling và vai trò hiện tại.
2. Chọn **Màn hình nguồn (1)** và **Màn hình đích (2)** → **Lưu vai trò màn hình**.

Thứ tự liệt kê của Windows **không** được coi là số trong *Display Settings*. NEXA lưu định danh có thể xác minh lại:
`device_id` (đường dẫn thiết bị ổn định từ `QueryDisplayConfig`, ví dụ `\\?\DISPLAY#...#{e6f07b5f-...}`), kèm
`device_name` và `friendly_name`. Khi chưa chọn, NEXA dùng màn hình chính làm nguồn và màn hình còn lại làm đích.

## Chuyển cửa sổ (cử chỉ 👉 chỉ ngón trỏ sang phải hoặc lệnh “chuyển sang màn hình 2”)

- “Cửa sổ hiện tại” = cửa sổ top-level foreground của ứng dụng anh đang dùng. Bỏ qua desktop, taskbar, overlay, cửa sổ
  công cụ và cửa sổ của NEXA.
- Tiến trình NEXA ở chế độ **Per-Monitor DPI Aware v2** ngay từ `main.py`, nên mọi tọa độ là pixel vật lý trong
  *virtual desktop* (có thể âm khi màn hình 2 nằm bên trái/phía trên).
- Cửa sổ **thường**: dời bằng `SetWindowPos` (giữ kích thước) để Windows/ứng dụng tự xử lý `WM_DPICHANGED`, đọc lại
  kích thước thật, giữ vị trí tương đối và giới hạn trong **work area** của màn hình đích.
- Cửa sổ **phóng to**: đặt `rcNormalPosition` (tọa độ *workspace* — gốc là góc work area của màn hình chính) vào màn hình
  đích qua `SetWindowPlacement` với `SW_SHOWMAXIMIZED`, nên cửa sổ vẫn phóng to trên màn hình đích; có phương án dự phòng
  khôi phục → dời → phóng to lại.
- Chỉ báo “Đã chuyển sang màn hình 2” sau khi `MonitorFromWindow` xác nhận cửa sổ thuộc màn hình đích.
- Nếu cửa sổ **đã ở màn hình 2**: không làm gì (không đẩy ngược về 1, không trôi ra ngoài).
- Chỉ một màn hình / đang **Duplicate** / màn hình đích đã rút: bỏ qua và giải thích ngắn.
- Ứng dụng chạy quyền admin (UIPI), cửa sổ đặc biệt, game fullscreen độc quyền: báo không chuyển được thay vì giả thành công.

## Cắm/rút màn hình

NEXA liệt kê lại màn hình **trước mỗi thao tác** (không dùng HMONITOR cũ). Overlay tự tạo lại khi Qt báo thêm/bớt
màn hình. Định danh đã lưu được đối chiếu lại bằng `device_id`; nếu không còn thấy màn hình đích, NEXA yêu cầu chọn lại.

## Thu nhỏ và khôi phục

- 👎 Ngón cái chỉ xuống: kiểm tra cửa sổ đích (phải có nút −), đọc trạng thái/vị trí, gửi `WM_SYSCOMMAND/SC_MINIMIZE` (tương đương
  nút −; dự phòng `ShowWindowAsync(SW_MINIMIZE)`), **chỉ ghi lịch sử khi xác minh `IsIconic`**. Ứng dụng tự ẩn xuống
  khay hệ thống không được ghi.
- 👍 Ngón cái chỉ lên: lấy mục hợp lệ **gần nhất** trong lịch sử do NEXA thu nhỏ (LIFO: thu nhỏ A rồi B → khôi phục
  B rồi A), kiểm tra HWND còn tồn tại, cùng PID + thời điểm tạo tiến trình + lớp cửa sổ (phát hiện HWND bị tái sử dụng),
  vẫn đang thu nhỏ (anh chưa tự khôi phục). Khôi phục đúng trạng thái trước đó (phóng to/thường).
- Màn hình cũ đã rút → khôi phục vào work area của màn hình chính còn hoạt động.
- Lịch sử rỗng → “Chưa có cửa sổ để khôi phục”, không mở ứng dụng nào khác. Lịch sử chỉ tồn tại trong phiên chạy.
- Windows giới hạn việc đưa cửa sổ lên trước (foreground lock); NEXA không dùng mẹo lách — nếu Windows chỉ nháy biểu
  tượng trên taskbar, NEXA nói rõ.

## Kiểm thử

`tests/test_windows.py` (Win32 giả lập): tọa độ âm, DPI 96/144, độ phân giải khác nhau, phóng to, đã ở đích, một màn
hình, màn hình đích bị rút, ứng dụng từ chối di chuyển, cửa sổ không hợp lệ, lịch sử A/B, cửa sổ đã đóng, HWND tái sử
dụng, anh tự khôi phục, khay hệ thống, màn hình cũ bị rút, snapshot đổi giữa chừng. Máy phát triển chỉ có **một** màn
hình nên luồng hai màn hình thật cần anh kiểm tra theo `docs/manual_tests.md` (mục 16–19, 24).

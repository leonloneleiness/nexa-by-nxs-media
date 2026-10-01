# Sinh code — NEXA viết code cho công việc kỹ sư phần mềm

NEXA nhờ Gemini viết code theo yêu cầu, **tự kiểm tra và tự sửa lỗi**, rồi hiện code đã tô màu trên bảng
“Sinh code” để anh đọc trước. **Không có gì tự sao chép hay tự chạy**: clipboard chỉ được ghi khi anh bấm nút
“Sao chép”, và code chỉ chạy khi anh bấm “▶ Chạy thử”.

## 1. Cách dùng

- **Bàn phím:** bấm nút **“Sinh code ▸”** trên cửa sổ NEXA → gõ yêu cầu → chọn ngôn ngữ (hoặc “Tự chọn”) →
  **Viết code** (Ctrl+Enter).
- **Giọng nói / gõ lệnh:**
  - “viết code python đọc file CSV và tính tổng doanh thu theo tháng”
  - “tạo script PowerShell dọn thư mục Temp cũ hơn 7 ngày”
  - “viết hàm JavaScript kiểm tra email hợp lệ”, “giúp tôi viết API REST bằng FastAPI”
  - “sửa code thêm xử lý lỗi khi file không tồn tại” (chỉnh bản đang xem)
  - “chạy thử code”, “tiến độ viết code”, “hủy viết code”, “mở bảng sinh code”
- Những câu không phải yêu cầu viết code vẫn giữ lệnh cũ: “tạo thư mục code”, “tạo file python”,
  “tạo file main.py trong VS Code”, “viết email…”, “tạo mô hình 3D…”.

## 2. Quy trình bên trong

1. Gemini (`code.models`, JSON schema) trả về: tiêu đề, tóm tắt, danh sách tệp, cách chạy, thư viện và ghi chú.
   Nếu hợp lý, Gemini viết kèm kiểm thử (`code.with_tests`).
2. NEXA **chuẩn hóa định dạng**: bỏ CRLF và khoảng trắng cuối dòng, đổi tab thành 4 dấu cách (Python), rồi lọc đường
   dẫn tệp: không cho `..`, không cho đường dẫn tuyệt đối.
3. **Kiểm tra tĩnh** theo từng tệp:

   | Ngôn ngữ | Công cụ |
   |---|---|
   | Python | `compile` và pyflakes (lỗi tên chưa định nghĩa…) |
   | JS | `node --check` |
   | PowerShell | Parser của PowerShell |
   | Go | `gofmt -e` |
   | Java | `javac` (nếu máy có) |
   | JSON, YAML, TOML | Trình parse tương ứng |

4. Còn lỗi thì NEXA gửi lỗi lại cho Gemini sửa, tối đa `code.repair_rounds` lượt. Bản sửa nào không tốt hơn thì NEXA
   giữ bản cũ.
5. NEXA liệt kê thư viện chưa cài (`pip install …` / `npm install …`).
6. Mỗi kết quả được lưu vào lịch sử (`%LOCALAPPDATA%\NEXA\code_history`, giữ `code.history_limit` bản).

## 3. Bảng “Sinh code”

- **Bên trái:** lịch sử (bấm để mở lại, có nút xóa).
- **Bên phải:**
  - Tiêu đề, huy hiệu kiểm tra (Đạt / Cảnh báo / Lỗi), tóm tắt.
  - Thẻ tệp, mỗi thẻ có chấm trạng thái.
  - Code tô màu theo theme One Dark (Pygments), có số dòng, chọn và bôi đen được.
  - Danh sách lỗi kèm số dòng.
- **Nút:**
  - Sao chép tệp này / Sao chép tất cả (nhiều tệp thì có dòng tiêu đề `===== path =====`)
  - Lưu ra thư mục: `Documents\NEXA Code\<tên>-<giờ>`, không bao giờ ghi đè; NEXA mở thư mục sau khi lưu
  - ▶ Chạy thử
  - Sửa lỗi chạy thử
- **Thẻ dưới:** Cách chạy · Thư viện & ghi chú · Chạy thử. Ô “Yêu cầu chỉnh sửa” dùng để chỉnh tiếp bản code.

### Cử chỉ tay khi bảng Sinh code đang mở (camera bật)

| Cử chỉ | Tác dụng |
|---|---|
| ✊ Nắm tay, giữ yên ~0,7 s | Lưu code vào `Documents\NEXA Code` (không mở Explorer; nếu code không đổi thì không tạo bản trùng) |
| 🫰 Búng tay (camera hoặc mic) | Kiểu công tắc: đang ở màn hình code → chạy thử (hoặc chạy lại tệp vừa chạy); đang xem kết quả → dừng chương trình và về màn hình code. Hai lần búng cách nhau dưới 1,2 s chỉ tính một |
| ✌ Giơ ngón trỏ + ngón giữa | Cuộn kiểu joystick: tay cao hơn điểm bắt đầu thì cuộn lên, thấp hơn thì cuộn xuống; càng xa càng nhanh; đưa tay về chỗ cũ thì dừng |

- Cuộn áp dụng cho khung đang hiện: code, kết quả chạy, hoặc trang web xem trước.
- Khi bảng mở: chuột bằng tay tắt, 6 cử chỉ hệ thống tạm ngưng, và trình xem 3D nhường cử chỉ cho bảng code.
- Chip “✋ Cử chỉ” ở hàng tiêu đề hiện gợi ý và thanh tiến độ khi giữ nắm tay.
- Mục cấu hình `code.gesture`:
  - `auto_camera`: mặc định `false`, không tự bật camera;
  - `fist_hold_ms`;
  - `scroll_deadzone`, `scroll_gain`, `scroll_max`, `invert_scroll`.

## 4. Chạy thử — lưu ý an toàn

- Chạy thử **không phải sandbox**: code chạy thật trên máy anh với quyền của anh. Hãy đọc code trước khi bấm.
- Để giảm rủi ro, khi chạy thử NEXA:
  - chạy trong thư mục tạm, xong thì xóa;
  - bỏ các biến môi trường chứa KEY/TOKEN/SECRET/PASSWORD;
  - không mở cửa sổ console;
  - giới hạn thời gian `code.run_timeout_s` và kill cả cây tiến trình khi quá giờ;
  - cắt output ở 12 000 ký tự.
- Công cụ `run_code_tests` có mức rủi ro **MEDIUM**: khi Gemini tự đề xuất chạy thử, NEXA hỏi xác nhận trước.
- Python:
  - có tệp `test_*.py` → chạy `pytest -q` (máy không có pytest thì dùng bộ chạy mini có sẵn);
  - không có tệp kiểm thử → chạy tệp chính.
- JS: `node --test` hoặc tệp chính. Các ngôn ngữ khác: hiện hướng dẫn chạy tay.
- Dừng khẩn cấp (Ctrl+Alt+Esc) hủy việc code đang chạy và khóa tính năng cho tới khi anh nói “tiếp tục điều khiển”.

## 5. Cấu hình (`config/settings.yaml`, mục `code:`)

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `enabled` | `true` | Bật/tắt tính năng |
| `models` | `[gemini-3.8-flash, gemini-3.5-flash]` | Thứ tự model thử (cuối cùng là model chính của NEXA) |
| `thinking` | `medium` | Mức suy nghĩ của Gemini |
| `timeout_s` / `max_tokens` / `temperature` | `180` / `32000` / `0.2` | Tham số gọi Gemini |
| `repair_rounds` | `2` | Số lượt tự sửa lỗi kiểm tra |
| `with_tests` | `true` | Yêu cầu viết kèm kiểm thử |
| `comment_language` | `vi` | Ngôn ngữ chú thích trong code (`vi`/`en`) |
| `run_timeout_s` | `30` | Giới hạn thời gian chạy thử |
| `python_path` | `""` | Python dùng để chạy thử (trống = tự tìm; bản EXE dùng `py -3`/`python`) |
| `save_dir` | `""` | Thư mục lưu (trống = `Documents\NEXA Code`) |
| `history_limit` | `30` | Số bản giữ trong lịch sử |

## 6. Mã nguồn

- `nexa/code/`, gồm:
  - `models.py`: dữ liệu, ngôn ngữ, lọc đường dẫn
  - `checks.py`: chuẩn hóa, kiểm tra, tìm thư viện thiếu, chạy thử
  - `highlight.py`: tô màu
  - `generator.py`: prompt, schema, vòng sửa lỗi
  - `service.py`: việc nền, lịch sử, lưu
  - `tools.py`: công cụ cho Gemini
  - `intents.py`: lệnh nói
- `nexa/ui/code_bridge.py`, `nexa/ui/qml/CodePanel.qml`
- Kiểm thử: `tests/test_code.py` (Gemini giả lập, không gọi mạng).
- Xem bảng offscreen: `scripts/probe_code_panel.py`.

## 7. Giới hạn

- Chất lượng code phụ thuộc Gemini. Kiểm tra tĩnh và kiểm thử chỉ bắt được một phần lỗi. Hãy đọc code trước khi dùng
  cho việc thật.
- TypeScript, C#, C++, Rust… hiện chỉ được tô màu, chưa có trình kiểm tra cục bộ (trạng thái “Chưa kiểm tra”).
- Gemini miễn phí có hạn mức; mỗi lượt sửa lỗi là một lần gọi thêm.

# NEXA — IPA tải từ Drive, cài bằng Windows

Đây là đường phát hành dùng cá nhân. Google Drive chỉ chuyển file; Sideloadly
ký lại và cài ứng dụng. IPA chưa ký không thể mở trực tiếp trên iPhone và không
dùng để upload App Store.

## Tạo file bằng Codemagic

1. Đăng nhập https://codemagic.io/ bằng tài khoản của bạn và kết nối repository.
2. Nhánh được chọn phải có `codemagic.yaml` tại gốc, `mobile/` và lockfile.
   Không đưa `.env`, model, bản build PC hoặc dữ liệu cá nhân vào commit mobile.
3. Chọn workflow **nexa-ios-sideload**. Workflow này không yêu cầu tích hợp
   App Store Connect hay chứng chỉ Apple: ký sẽ thực hiện sau trên Windows.
4. Chạy build macOS. Workflow kiểm tra Dart, chạy test, biên dịch iPhone release,
   đóng gói `Payload/Runner.app` và tạo SHA-256.
5. Chỉ khi build thành công, tải ba artifact: `NEXA-unsigned.ipa`,
   `NEXA-unsigned.ipa.sha256`, `NEXA-unsigned.ipa.json`.
6. Bạn có thể tải ba file lên Drive rồi tải về laptop. Không cần domain/hosting.
   Dịch vụ build có quota/giá riêng; kiểm tra tài khoản trước khi chạy.

## Cài bằng laptop Windows

1. Tải Sideloadly tại https://sideloadly.io/ và làm theo hướng dẫn driver chính thức.
2. Kết nối iPhone bằng USB, mở khóa và chọn Tin cậy nếu được hỏi.
3. Kiểm tra file bằng PowerShell: `Get-FileHash .\NEXA-unsigned.ipa -Algorithm SHA256`.
   So sánh với checksum tải từ build.
4. Mở Sideloadly, chọn iPhone và file IPA, dùng chế độ Apple ID sideload.
   Chính bạn nhập tài khoản, mật khẩu và mã xác thực trong công cụ; không gửi vào chat.
5. Làm theo yêu cầu Trust Developer và Developer Mode trên iPhone. Không bỏ qua
   cảnh báo HTTPS hay dùng chứng chỉ không rõ nguồn gốc.
6. Mở NEXA. Trong Cài đặt nhập endpoint HTTPS chat-completions, model và token
   của dịch vụ AI bạn sử dụng. Không nhập localhost của PC: trên iPhone localhost
   trỏ về chính điện thoại. Ứng dụng chưa tự kết nối với NEXA Desktop.

Tài khoản Apple miễn phí thông thường có thời hạn 7 ngày cho ứng dụng đã ký;
cần ký lại/refresh. Giữ cùng Apple Account và bundle identifier khi cập nhật.
Tham khảo: https://sideloadly.io/faq.html

## Kiểm thử sau khi cài

- App khởi động, bàn phím không che ô nhập; thử cả xoay màn hình.
- Lưu cấu hình, đóng/mở lại để xác minh Keychain thực sự lưu được.
- Gửi câu ngắn với endpoint/token hợp lệ và kiểm tra phản hồi.
- Thử mất mạng/token sai: báo lỗi, giữ lại câu hỏi để gửi lại.
- Cuộc trò chuyện mới xóa phiên; ứng dụng hiện không đồng bộ lịch sử.
- Refresh/cài đè rồi kiểm tra cấu hình; ghi nhận lỗi nếu entitlements ký lại khác.

## Trạng thái

Đã chuẩn bị mã và workflow, chưa chạy macOS build từ phiên này. Không có IPA
thật, chưa upload Drive và chưa kiểm thử Sideloadly/Keychain trên iPhone.
Test đóng gói dùng bundle giả lập, không phải bằng chứng ứng dụng iOS chạy được.
Bản 0.1 là client chat văn bản; chưa có thoại, AI offline, điều khiển PC hoặc đồng bộ.

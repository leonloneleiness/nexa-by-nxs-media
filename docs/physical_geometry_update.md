# Sửa hình học lắp ghép, 2026-09-30

Yêu cầu: mô hình có cấu tạo thực tế, không chỉ vỏ minh họa hoặc hồ sơ linh kiện.
Hai ảnh người dùng cung cấp được dùng để hiểu mục tiêu (UAV với thiết bị lắp trên khung,
robot bốn chân có các cụm khớp và chân rõ ràng). Không suy ra kích thước hoặc cấu tạo bên trong từ ảnh.

Giữ nguyên ảnh tham chiếu do người dùng cung cấp tại `docs/reference_images/uav_user_reference.png`
và `docs/reference_images/quadruped_user_reference.png`; không dùng làm texture hay ảnh thay cho mô hình 3D.

## Thay đổi hình học đã thực hiện

- Hợp nhất vít đầu trụ trong hai thư viện `components` và `machine`. Kích thước đầu và lỗ lục giác
  của đường kính danh nghĩa dùng bảng ISO_METRIC hiện có thay vì hai công thức tỷ lệ khác nhau.
  Ví dụ M3: đầu Ø5,5 mm, cao 3 mm, lỗ lục giác 2,5 mm.
- Vòng đệm dùng đường kính lỗ có độ hở trong bảng, không dùng đúng đường kính thân vít.
- UAV: hai vít M3 ở mỗi tay đòn giữ nguyên đường kính khi thay wheelbase. Khoét lỗ đồng trục Ø3,4 mm
  xuyên cả khung trên/dưới và tay đòn; bổ sung phần vật liệu tựa quanh lỗ để không đặt vít vào khe giảm trọng.
  Thêm vòng đệm và đai ốc ở mặt dưới; chọn chiều dài vít theo chiều dày chồng tấm.
- Motor bước: lỗ xuyên thân có khoảng hở và lỗ bậc có vai tựa đầu vít, thay vì đầu vít lơ lửng
  trong hốc khoét quá sâu. Sửa này đã được kiểm tra va chạm ở NEMA 17/23/34.
- Tăng phiên bản bộ sinh để các yêu cầu mới không trả lại cache hình học cũ.
  Các file mô hình cũ không bị sửa tự động; phải tạo lại để nhận hình học mới.

## Giới hạn chưa giải quyết

Kiểm thử: 84 kiểm thử linh kiện cơ khí và 274 kiểm thử mối ghép/pipeline/máy chế tạo/robot/phương tiện/
năng lượng đã đạt. Các phép đo mới kiểm tra kích thước đầu vít, khoảng hở vòng đệm, lỗ đồng trục,
va chạm phần cứng và vật liệu tựa của UAV 3/4/6/8 tay đòn. Đây là kiểm thử phần mềm, không phải thử lắp vật lý.

Đây là đợt sửa cụ thể, **chưa hoàn thành việc thiết kế lại 51 loại mô hình**.
Các template dùng chung vít/vòng đệm nhận hình học mới; không có nghĩa mọi bộ phận đã khớp linh kiện mua được.
Thân vít/đai ốc trong assembly vẫn mô phỏng ren bằng mặt trơn; vít có đường kính ngoài bảng là chi tiết custom.
Chiều sâu lỗ lục giác và vát mép chưa phải bản vẽ sản xuất theo dung sai.

Chưa có đủ CAD/bản vẽ nguồn để tái tạo các motor, hộp số, khớp robot, hệ điện và các cụm khác
thành thiết kế chế tạo. Robot bốn chân chưa được thiết kế lại trong đợt này.
Không thể dùng hai ảnh làm chứng cứ về kích thước bên trong, khả năng chịu tải hoặc chức năng thực.

## Tham khảo

- [Bossard vít đầu trụ M3](https://nederland.bossard.com/en-us/standard-fastening-elements/screws/screws-and-bolts-with-internal-drive/912000a20030030).
- [Holybro tài liệu lắp ráp drone](https://docs.holybro.com/company/user-manuals/drone-dev-kit):
  ví dụ về mức tài liệu cần có, không tuyên bố UAV NEXA là bản sao X500.
- [Unitree Go2](https://www.unitree.com/go2/): tham khảo bố cục tổng thể, không dùng thông số bên ngoài
  để suy đoán cấu tạo khớp bên trong.

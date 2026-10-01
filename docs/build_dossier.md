# Linh kiện và lắp ráp cho toàn bộ thư viện NEXA

## Phạm vi đã bổ sung

51 loại mô hình cụ thể và loại `generic` có hồ sơ chuẩn bị chế tạo. Trong trình xem chọn
**SẢN PHẨM → Linh kiện & lắp ráp**. Mô hình cũ cũng dùng được ngay khi mở hồ sơ, không cần tạo lại
và không thay đổi manifest/hình học cũ.

Mỗi hồ sơ gồm yêu cầu kỹ thuật theo loại sản phẩm, một dòng cho toàn bộ sản phẩm, các dòng liên kết
với ID bộ phận thật, thông số mô hình, đề xuất cách cung ứng và những mục chưa hoàn thiện.
Chọn bộ phận trong hồ sơ rồi bấm **Xem bộ phận trên mô hình** để làm nổi bật nó.

## Ghi nhận linh kiện thực

1. Chọn toàn bộ sản phẩm hoặc bộ phận cần đối chiếu.
2. Chọn **Mua sẵn**, **Tự gia công** hoặc **Tham chiếu nội bộ**.
3. Nhập hãng, mã đầy đủ, địa chỉ nguồn mua/datasheet, số lượng vật lý và ghi chú.
4. Bấm **Lưu linh kiện**. NEXA ghi nhận thông tin do người dùng nhập, không tự xác minh trang web.
5. Bấm **Xuất hồ sơ đã lưu**, sau đó **Mở thư mục**. HTML đọc/in bằng trình duyệt; JSON giữ dữ liệu đầy đủ.
   Mỗi lần xuất có thư mục riêng trong `Documents/NEXA 3D/Build`.

Số lượng 0 nghĩa là chưa xác định. Không lấy số mesh làm số lượng mua: một mesh có thể gộp nhiều vít,
hoặc nhiều mesh chỉ mô tả một linh kiện mua nguyên cụm. Ví dụ ổ bi, động cơ bước, bo mạch nên tìm mua
nguyên cụm; bi, rotor, stator và linh kiện trên bo không tự trở thành BOM mua sắm.

Ghi chú được lưu ngoài cache tại `%LOCALAPPDATA%/NEXA/build_records`. Khi cấu trúc/thông số mô hình
thay đổi, từng ghi chú cũ được đánh dấu cần đối chiếu lại. Xóa cache không xóa ghi chú, nhưng để giữ
cả mô hình lẫn hồ sơ lâu dài cần xuất GLB và hồ sơ trước khi xóa dự án.

## Trạng thái kỹ thuật

**Đây chưa phải bộ thiết kế có thể mua đủ linh kiện và lắp chạy ngoài đời.** Chức năng hiện tại giúp
hoàn thiện hồ sơ cho toàn thư viện, không thiết kế lại các template thành máy đã kiểm chứng.
Điểm chất lượng mô hình/lưới không chứng nhận khả năng chế tạo.

- Kích thước mesh, vật liệu hiển thị và hướng tách cụm không thay thế bản vẽ dung sai, vật liệu thực,
  thông số mối ghép, mô-men siết và thứ tự lắp ráp.
- Co giãn toàn bộ mô hình có thể làm sai kích thước linh kiện tiêu chuẩn: hồ sơ đánh dấu cần kiểm tra.
- Mô hình cloud/DSL hoặc không tách bộ phận cần thiết kế kỹ thuật lại.
- Chưa tự tìm nhà cung cấp, đối chiếu datasheet, tạo STEP/B-rep, sơ đồ điện, firmware, tính tải hoặc thử lắp.
- Nhập đầy đủ hãng/mã/nguồn vẫn giữ trạng thái **chưa xác minh**. Không có nút tự chứng nhận “sẵn sàng chế tạo”.

Để hoàn thành mục tiêu lắp thật, từng cấu hình sản phẩm còn cần chọn linh kiện cụ thể, sửa hình học
theo linh kiện, lập bản vẽ và sơ đồ, kiểm tra giao diện cơ/điện, rồi thử lắp và ghi nhận kết quả.

## Nguồn tham khảo đã tra cứu

Các nguồn sau minh họa tài liệu hãng cần dùng, không tự gán sản phẩm đó cho mô hình:

- [SKF 6204](https://www.emarketplace.in.skf.com/deep-groove-ball-bearing/6204).
- [Pololu motor 2267](https://www.pololu.com/product/2267).
- [Arduino UNO R3 datasheet](https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf).

Các loại khác có yêu cầu đối chiếu riêng trong `nexa/three_d/build_profiles.py`; chưa có nguồn linh kiện được xác minh.

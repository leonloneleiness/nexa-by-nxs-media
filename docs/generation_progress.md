# Tiến độ tạo mô hình và code

Màn hình Trung tâm có hai thẻ tiến độ riêng cho mô hình 3D và code. Thẻ đọc trạng thái tác vụ nền thật,
không dùng trạng thái hoàn thành lệnh gửi yêu cầu. Danh sách lệnh cũ được đặt tên “Lệnh gần đây”.

Thẻ hiển thị phần trăm, bước hiện tại, thời gian đã chạy và nút Chi tiết/Xem kết quả.
Phần trăm là ước lượng theo bước, không phải tỷ lệ token hay thời gian đã hoàn thành. Chỉ khi tác vụ
báo ready/done mới hiện 100%. Chưa có dữ liệu ETA đáng tin cậy nên giao diện không dự đoán giờ xong.
Thời gian dừng đếm khi tác vụ kết thúc. Bản nháp chưa đạt, lỗi và hủy có nhãn riêng.

Khi mở code/trình xem hoặc thu hẹp cửa sổ khiến cột tiến độ bị ẩn, hai thẻ gọn xuất hiện dưới thanh đầu trang.
Cột bên phải cuộn được trên cửa sổ thấp. Với nhiều việc 3D, thẻ ưu tiên việc đang chạy trước việc đang chờ.

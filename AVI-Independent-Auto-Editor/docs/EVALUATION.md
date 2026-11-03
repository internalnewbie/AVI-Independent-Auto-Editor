# Đánh giá chất lượng audio–visual matching

## Baseline hiện tại

Người dùng đánh giá thủ công một dự án trên chủ đề tin tức Hoàng gia Anh và báo mức khớp khoảng **70%**. Không có dataset và tiêu chí gắn nhãn độc lập đi kèm source snapshot, vì vậy con số này là **user-reported**, không phải phép đo có khả năng tái lập bằng CI.

## Đề xuất đánh giá xuyên chủ đề

- Chuẩn bị 6 thể loại tối thiểu, mỗi thể loại ít nhất vài chục beat.
- Với mỗi beat, đánh dấu *đúng nhân vật*, *đúng hành động*, *đúng sự kiện/bối cảnh*, *phù hợp nhưng chỉ là hình minh họa*, *sai*.
- Tách độ chính xác theo **entity/event/visual relevance**, tránh gộp một điểm CLIP thành "độ chính xác".
- Tính top-1 precision, top-K recall, tỷ lệ cần duyệt, tỷ lệ sai người/sai sự kiện, hiệu năng index, tốc độ render; so sánh với bản v0.3.4.
- Khả năng sử dụng lại footage là tín hiệu phụ, không được đặt trên sự chính xác.

Model có thể tạo mô tả thiếu căn cứ: hình ảnh phải được kiểm chứng trước khi dùng làm tư liệu cho tuyên bố sự kiện thực. Phân biệt minh họa và cảnh sự kiện có nguồn.

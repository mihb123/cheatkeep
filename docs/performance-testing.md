# Kiểm thử hiệu năng

`make test` là cổng kiểm tra chung trước khi nhận thay đổi ảnh hưởng đến tốc độ. Lệnh chạy unit test và bài đo search với PostgreSQL, dữ liệu seed và Ollama thật. Cần chạy `make load` một lần sau khi thiết lập môi trường; nếu đổi dữ liệu hoặc model embedding, chạy lại `make load` trước khi đo.

## Ngưỡng search

- `tests/test_performance.py` có ít nhất 5 case cố định, gồm truy vấn có tiền tố sheet, alias, tiếng Việt, tiếng Anh, câu bắt đầu bằng từ dễ nhầm với tên sheet, tìm trên nhiều sheet và mở danh sách lệnh phổ biến.
- Mỗi case chạy 1 lần làm nóng, sau đó đo 5 lần bằng đồng hồ đơn điệu `perf_counter_ns`. Thời gian đo gồm `parse_query`, truy vấn PostgreSQL và đọc toàn bộ kết quả; case search còn gồm cả tạo embedding, case mở danh sách lệnh phổ biến bỏ qua bước này. Kết nối DB, khởi động Ollama và lần làm nóng không nằm trong số đo.
- Trung bình **từng case** và trung bình **toàn bộ lượt đo** đều phải **dưới `SEARCH_MAX_AVERAGE_MS`** trong `.env` (mặc định 200 ms). Test in kết quả từng case và thất bại khi vượt ngưỡng, thiếu dữ liệu/vector hoặc search không trả kết quả.
- Bài đo không dùng mock, không tự bỏ qua khi thiếu dịch vụ. Kết quả phản ánh máy chạy test với model đã ấm; độ trễ cold start, khởi tạo CLI và HTTP cần được đo riêng nếu đặt ngưỡng cho các luồng đó.

## Quy định khi thêm tính năng

Nếu thay đổi có thể ảnh hưởng đến tốc độ một luồng người dùng, thêm hoặc cập nhật case đại diện trong bài test hiệu năng của luồng đó và cho chạy qua `make test`. Dùng dữ liệu đủ để đi qua đường xử lý thật, làm nóng trước khi đo, lặp nhiều lần, ghi rõ phạm vi đo và đặt ngưỡng cụ thể. Test phải thất bại khi vượt ngưỡng hoặc khi thiếu điều kiện đo; không được coi thiếu dịch vụ là đạt. Với search, giữ tối thiểu 5 case và kiểm tra cả ngưỡng từng case lẫn toàn bộ từ `SEARCH_MAX_AVERAGE_MS`; nếu thay đổi quy mô dữ liệu hoặc phần cứng đo, ghi rõ điều kiện mới trước khi so sánh kết quả.

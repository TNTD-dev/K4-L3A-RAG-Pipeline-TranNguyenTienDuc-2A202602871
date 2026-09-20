# Individual contribution report

## Thông tin

- Họ và tên: Nguyễn Anh Dũng
- Mã học viên: 2A202602554
- Nhóm: L3A (K4)
- Repository/branch: `K4-L3A-RAG-Pipeline-TranNguyenTienDuc-2A202602871` / `main`

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Compass Assistant Service | Thiết kế và phát triển `DefaultCompassAssistant`, quản lý toàn bộ vòng đời sinh câu trả lời từ lúc nhận request đến khi trả về kết quả | `src/vinuni_compass/assistant/service.py` (Commit: `0849c8c`) | Done |
| Cơ chế Citation-Aware | Xây dựng prompt engineering ép buộc LLM phải trích dẫn nguồn theo ký hiệu `[n]` tương ứng với vị trí tài liệu trong context window, ngăn chặn trích dẫn nguồn ảo | `src/vinuni_compass/assistant/service.py`, `src/task10_generation.py` (Commit: `0849c8c`) | Done |
| Safe Refusal & PII Protection | Cài đặt bộ lọc từ chối an toàn khi không đủ dữ liệu chứng cứ (not_found); xây dựng regex phát hiện và làm sạch thông tin nhận dạng cá nhân PII (số điện thoại, CMND/CCCD, email) | `src/vinuni_compass/assistant/service.py` (Commit: `0849c8c`) | Done |
| Phát hiện xung đột chính sách | Phát triển logic `_has_conflicting_versions` tự động cảnh báo người dùng khi các tài liệu được trích xuất có phiên bản năm ban hành mâu thuẫn nhau | `src/vinuni_compass/assistant/service.py` (Commit: `0849c8c`) | Done |
| Kiểm thử Assistant & Contracts | Xây dựng bộ test suite kiểm tra hành vi trích dẫn, refusal và routing của assistant | `tests/test_assistant.py`, `src/contracts.py` (Commit: `0849c8c`) | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** Áp dụng cơ chế "Safe Refusal" từ chối trả lời ngay lập tức nếu không tìm thấy văn bản quy chế chứng minh hoặc điểm tương đồng vector quá thấp.  
   **Lý do/evidence:** Trong môi trường thông tin quy chế đại học và học phí (VinUni), trả lời sai hoặc bịa đặt (hallucination) có thể gây hậu quả nghiêm trọng cho sinh viên và phụ huynh. Tự động từ chối với thông điệp lịch sự an toàn hơn nhiều so với đoán mò.  
   **Trade-off:** Tỷ lệ trả lời chung của hệ thống có thể giảm trên các câu hỏi mở, nhưng đổi lại độ tin cậy và chỉ số Refusal Accuracy đạt tới 90.0%.

2. **Quyết định:** Định dạng trích dẫn theo thẻ số `[n]` đồng bộ với thứ tự của các nguồn `[Source 1]`, `[Source 2]` được cung cấp trong context prompt.  
   **Lý do/evidence:** Cú pháp `[n]` rất tự nhiên với LLM, ít tốn token hơn so với việc bắt LLM lặp lại toàn bộ URL hoặc tiêu đề văn bản dài, đồng thời giúp giao diện frontend dễ dàng phân tích và gắn thẻ link.  
   **Trade-off:** Cần bộ lọc regex ở đầu ra để kiểm tra nếu LLM vô tình trích dẫn số `[n]` nằm ngoài danh sách tài liệu thực tế được cung cấp.

## Kiểm thử và kết quả

- **Kiểm thử tự động:** Viết và chạy thành công 77 dòng test trong `tests/test_assistant.py`, kiểm thử trọn vẹn các kịch bản: trích dẫn nguồn đúng số, từ chối khi query rác, và định tuyến ngôn ngữ tiếng Anh/tiếng Việt.
- **Kết quả thực tế:** Hệ thống thể hiện khả năng trích dẫn rất trung thực: mọi khẳng định về mức học phí hay quy định ký túc xá đều kèm số nguồn cụ thể (ví dụ `[1]`, `[2]`), tạo sự minh bạch tuyệt đối cho người dùng.
- **Lỗi đã phát hiện và xử lý:** Phát hiện LLM đôi khi sinh ra các thẻ trích dẫn bị lệch khoảng trắng như `[ 1 ]`; đã cải tiến biểu thức chính quy để nhận diện và chuẩn hóa toàn bộ các biến thể trích dẫn này.

## Điều còn hạn chế

- **Một hạn chế cụ thể:** Hiện tại assistant mới chỉ cảnh báo văn bản mâu thuẫn năm ban hành chứ chưa tự động giải quyết mâu thuẫn bằng cách ưu tiên văn bản mới nhất tuyệt đối.
- **Nếu có thêm thời gian:** Tôi sẽ xây dựng thuật toán phân tích thứ tự thời gian (Temporal Resolution) để tự động ưu tiên quy chế có ngày hiệu lực mới nhất thay vì chỉ đưa ra cảnh báo.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 20/09/2026
- Tên thành viên: Nguyễn Anh Dũng

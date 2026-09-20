# Individual contribution report

## Thông tin

- Họ và tên: Lê Nguyễn Quốc Bảo
- Mã học viên: 2A202603011
- Nhóm: L3A (K4)
- Repository/branch: `K4-L3A-RAG-Pipeline-TranNguyenTienDuc-2A202602871` / `main`

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Golden Dataset Construction | Thiết kế và xây dựng bộ 30 golden test cases chuẩn hóa đa dạng (10 Admissions, 10 Student Life, 5 Keyword/Multi-source, 5 Refusal out-of-scope; 18 tiếng Anh, 12 tiếng Việt) kèm expected answer và expected source IDs | `group_project/evaluation/build_golden_dataset.py`, `golden_dataset.json` (Commit: `d2b4787`) | Done |
| A/B Evaluation Harness | Xây dựng khung đánh giá thực nghiệm A/B testing tự động, tính toán 7 metrics (Recall@5, Context Recall, Context Precision, Faithfulness, Relevance, Citation, Refusal) và đo độ trễ latency p50/p95 | `group_project/evaluation/harness.py` (Commit: `d2b4787`) | Done |
| Chat UI & Dashboard Explore | Thiết kế và phát triển giao diện Web SPA: chat tương tác, thẻ trích dẫn Public Sources và bảng Dashboard trực quan hóa chất lượng A/B testing bằng biểu đồ SVG động trên tab Explore | `app.py`, `web/app.js`, `web/index.html`, `web/styles.css`, `src/vinuni_compass/webapp.py` (Commit: `507913a`) | Done |
| Kiểm thử Evaluation & UI | Xây dựng bộ test suites kiểm thử tính toàn vẹn của harness đánh giá và giao diện web | `tests/test_evaluation.py`, `tests/test_ui_smoke.py` (Commit: `d2b4787`, `507913a`) | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** Sử dụng phương pháp đánh giá từ vựng tất định (`lexical-v1` token-overlap proxy) làm cơ chế chấm điểm mặc định thay vì phụ thuộc vào live LLM-as-a-judge.  
   **Lý do/evidence:** Đảm bảo tính nhất quán (reproducibility) 100% qua mọi lần chạy lại, không tốn chi phí API token của mô hình giám khảo bên ngoài và loại trừ được độ ngẫu nhiên không mong muốn khi chấm bài.  
   **Trade-off:** Điểm số token overlap (F1) bị thấp khi LLM sử dụng từ đồng nghĩa hoặc câu trả lời tự nhiên dài hơn câu mẫu. Do đó, harness cần ghi rõ trường `evaluator` là proxy overlap để phản ánh đúng bản chất kỹ thuật.

2. **Quyết định:** Trực quan hóa số liệu A/B testing trực tiếp bằng SVG nguyên bản trên giao diện web (không dùng thư viện ngoài nặng như Chart.js).  
   **Lý do/evidence:** Giúp ứng dụng nhẹ, tải tức thì, chạy mượt mà trên môi trường offline hoặc local demo và dễ dàng tùy biến tooltip hiển thị từng chỉ số theo thang đo $0.0 \rightarrow 1.0$.  
   **Trade-off:** Phải tự tính toán tỷ lệ tọa độ điểm SVG thủ công (viewBox, padding, bar-gap) nhưng đổi lại kiểm soát hoàn toàn DOM và giao diện tối ưu.

## Kiểm thử và kết quả

- **Kiểm thử tự động:** Viết và chạy thành công 366 dòng test trong `tests/test_evaluation.py` và 256 dòng test trong `tests/test_ui_smoke.py`, đảm bảo toàn bộ logic harness và UI endpoints đều hoạt động chuẩn xác.
- **Kết quả A/B evaluation:** Kết quả benchmark thể hiện rõ nét trên giao diện web với việc Hybrid + RRF vượt trội hơn Dense ở mọi khía cạnh truy xuất (Recall@5: 73.33% vs 66.67%, Context Recall: 70.00% vs 63.33%).
- **Lỗi đã phát hiện và cách xử lý:** Phát hiện lỗi các bar chart bị tràn nhãn khi thu nhỏ màn hình; đã xử lý bằng góc xoay `-28deg` cho label văn bản và tooltip tương tác thông minh.

## Điều còn hạn chế

- **Một hạn chế cụ thể:** Bộ harness hiện tại mới dừng ở mức so khớp từ khóa (Bag-of-Words / Token F1) có chuẩn hóa dấu tiếng Việt, chưa phân tích được tính tương đương ngữ nghĩa sâu (semantic embedding similarity).
- **Nếu có thêm thời gian:** Tôi sẽ tích hợp thêm cờ tùy chọn `--evaluator ragas` hoặc LLM judge chạy local (Ollama) để chấm điểm câu trả lời có tính ngữ nghĩa cao hơn.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 20/09/2026
- Tên thành viên: Lê Nguyễn Quốc Bảo

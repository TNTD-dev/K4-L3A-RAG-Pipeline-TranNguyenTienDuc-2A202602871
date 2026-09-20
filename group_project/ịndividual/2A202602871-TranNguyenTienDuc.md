# Individual contribution report

## Thông tin

- Họ và tên: Trần Nguyễn Tiến Đức
- Mã học viên: 2A202602871
- Nhóm: L3A (K4)
- Repository/branch: `K4-L3A-RAG-Pipeline-TranNguyenTienDuc-2A202602871` / `main`

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Thu thập & Chuẩn hóa dữ liệu | Thu thập 8 văn bản quy chế PDF VinUni và 10 bài viết tuyển sinh, chuyển đổi sang Markdown chuẩn có metadata provenance | `data/landing/`, `data/standardized/`, `src/task1_collect_legal_docs.py`, `src/task2_crawl_news.py`, `src/task3_convert_markdown.py` | Done |
| Chunking, Embedding & Vector DB | Triển khai chunking văn bản có overlap, tính toán embedding `text-embedding-3-small` theo batch (100 chunks/lần) và lưu trữ vào ChromaDB persistent | `src/task4_chunking_indexing.py`, `chroma_db/` | Done |
| Dense Search & BM25 | Xây dựng tìm kiếm ngữ nghĩa cosine similarity và tìm kiếm từ khóa BM25Okapi in-memory trên toàn bộ corpus | `src/task5_semantic_search.py`, `src/task6_lexical_search.py` | Done |
| RRF Fusion & Fallback | Cài đặt thuật toán Reciprocal Rank Fusion ($k=60$) để hợp nhất bảng xếp hạng; thiết lập cơ chế fallback khi dense cosine score < 0.30 | `src/task7_reranking.py`, `src/task8_reranking.py`, `src/task9_retrieval_pipeline.py`, `src/vinuni_compass/retrieval/` | Done |
| Generation & Citation | Tích hợp mô hình GPT-5.6-luna sinh câu trả lời bám sát ngữ cảnh, validate trích dẫn `[n]`, chống bịa đặt và xử lý safe refusal cho câu hỏi ngoài phạm vi | `src/task10_generation.py`, `src/vinuni_compass/assistant/service.py` | Done |
| Chatbot Web UI & Streaming | Phát triển giao diện web SPA với Server-Sent Events streaming, hiển thị thẻ Public Sources, render Markdown chuẩn (marked.js) và bộ câu hỏi gợi ý tiếng Việt | `web/app.js`, `web/index.html`, `web/styles.css`, `src/vinuni_compass/webapp.py` | Done |
| Đánh giá A/B & Báo cáo | Xây dựng 30 golden test cases (Admissions, Student Life, Refusal), chạy harness A/B testing 7 metrics, hoàn thiện báo cáo phân tích lỗi | `group_project/evaluation/harness.py`, `golden_dataset.json`, `group_project/evaluation/RESULT.md`, `reports/RESULT.md` | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** Sử dụng thuật toán Reciprocal Rank Fusion (RRF, $k=60$) thay vì cộng điểm số tuyến tính (Linear Combination) giữa Dense Cosine và BM25.  
   **Lý do/evidence:** Điểm Cosine Similarity nằm trong khoảng $[0, 1]$ trong khi điểm BM25 là số thực không chuẩn hóa $[0, 25+]$. Cộng trực tiếp sẽ bị lệch thang đo nghiêm trọng. RRF hợp nhất dựa trên thứ hạng (rank) độc lập với thang đo phân phối điểm của từng mô hình.  
   **Trade-off:** RRF score chỉ phản ánh thứ bậc tương đối ($\le 0.033$) chứ không phản ánh độ tương đồng tuyệt đối, nên quyết định fallback an toàn phải tách riêng và dựa trên Cosine score gốc của Dense.

2. **Quyết định:** Tách luồng xử lý phản hồi bằng Server-Sent Events (SSE) và render nguồn tham khảo ngay khi Retrieval hoàn tất.  
   **Lý do/evidence:** Khâu Retrieval chỉ mất ~100-150ms trong khi LLM Generation cần 1.5 - 2.5s. Bắn event `sources` sớm giúp người dùng nhìn thấy ngay căn cứ tài liệu và giảm cảm giác chờ đợi.  
   **Trade-off:** Cần xử lý cẩn thận trạng thái citation markers `[n]` trong streaming delta để không làm vỡ giao diện trước khi toàn bộ câu trả lời hoàn tất.

## Kiểm thử và kết quả

- **Kiểm thử tự động:** Chạy toàn bộ 109 test cases trong `tests/` (`test_contracts.py`, `test_acceptance.py`, `test_evaluation.py`, `test_ui_smoke.py`), kết quả: **109 passed**.
- **Kết quả A/B testing (30 golden cases):**
  - **Recall@5:** Hybrid + RRF đạt **73.33%** vs Dense only **66.67%** (+6.67%).
  - **Context Recall:** Hybrid + RRF đạt **70.00%** vs Dense only **63.33%** (+6.67%).
  - **Context Precision:** Hybrid + RRF đạt **52.22%** vs Dense only **50.11%** (+2.11%).
  - **Refusal Accuracy:** Cả 2 cấu hình đạt **90.00%** (xử lý an toàn các câu hỏi bẫy).
- **Lỗi đã phát hiện và xử lý:**
  - Lỗi `gpt-5.6-luna` không tương thích tham số `temperature` khi gọi API $\rightarrow$ Đã bỏ `temperature` khi gọi model này.
  - Lỗi hiển thị trùng lặp "Nguồn tham khảo" trên UI $\rightarrow$ Đã xử lý strip phần nguồn raw và hiển thị duy nhất qua thẻ Public Sources.
  - Render raw Markdown $\rightarrow$ Đã tích hợp `marked.min.js` và bổ sung CSS typography.

## Điều còn hạn chế

- **Một hạn chế cụ thể:** Bộ đánh giá mặc định dùng `lexical-v1` (Token-level F1 overlap) nên các câu trả lời của LLM dù diễn giải đúng ngữ nghĩa nhưng dùng từ đồng nghĩa hoặc câu dài hơn mẫu sẽ có điểm F1 ở mức ~0.34.
- **Thay đổi đầu tiên nếu có thêm thời gian:** Tích hợp mô hình LLM-as-a-judge (RAGAS với GPT-4/Luna) để chấm điểm ngữ nghĩa cho khâu Generation, đồng thời bổ sung OCR nâng cao cho các bảng biểu học phí phức tạp trong file PDF.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 20/09/2026
- Tên thành viên: Trần Nguyễn Tiến Đức

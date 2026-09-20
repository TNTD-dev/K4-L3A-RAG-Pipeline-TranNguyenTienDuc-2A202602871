# Individual contribution report

## Thông tin

- Họ và tên: Hoàng Anh Tài
- Mã học viên: 2A202602612
- Nhóm: L3A (K4)
- Repository/branch: `K4-L3A-RAG-Pipeline-TranNguyenTienDuc-2A202602871` / `main`

## Phần việc đã thực hiện

| Module/deliverable | Việc tôi trực tiếp làm | File/commit/PR | Trạng thái |
|---|---|---|---|
| Advanced Retrieval Engine | Thiết kế và phát triển `AdvancedRetrievalEngine`, điều phối đồng thời Dense Search, BM25 Search và RRF Fusion trong một seam duy nhất | `src/vinuni_compass/retrieval/advanced.py` (Commit: `a06f274`) | Done |
| BM25 Lexical Search & Fix | Cài đặt và khắc phục lỗi thuật toán BM25: tokenization, loại bỏ stopwords vô nghĩa, xử lý phân phối điểm số và tích hợp index `rank-bm25` | `src/task6_lexical_search.py` (Commit: `a06f274`) | Done |
| Chuẩn hóa tài liệu Markdown | Xử lý và chuẩn hóa toàn bộ văn bản quy chế và tin tức trong `data/standardized/` (8 legal policies, 10 news articles) đồng bộ theo cấu trúc Markdown có frontmatter | `data/standardized/legal/`, `data/standardized/news/` (Commit: `a06f274`) | Done |
| Vector Store & Reranker Adapters | Xây dựng các cổng adapter kết nối ChromaDB persistent vector store và Jina Reranker cho luồng nâng cao | `src/vinuni_compass/providers/adapters.py` (Commit: `a06f274`) | Done |
| Thử nghiệm & Test Retrieval | Viết bộ kiểm thử chuyên sâu cho retrieval nâng cao và các kịch bản thực nghiệm đối chứng | `tests/test_advanced_retrieval.py`, `tests/experiments/retrieval_experiments.py` (Commit: `a06f274`) | Done |

## Quyết định kỹ thuật quan trọng

1. **Quyết định:** Nạp toàn bộ chỉ mục BM25 trực tiếp vào RAM (In-memory) từ danh sách corpus ngay khi khởi động ứng dụng.  
   **Lý do/evidence:** Với quy mô 1.031 chunks của toàn trường VinUni, chỉ mục BM25 trên RAM chỉ chiếm vài MB nhưng cho tốc độ truy vấn cực nhanh (<1ms), loại bỏ hoàn toàn độ trễ I/O đọc ổ đĩa trong mỗi lượt hỏi đáp.  
   **Trade-off:** Thời gian khởi động server lâu hơn khoảng 100ms để build index, nhưng bù lại thời gian phản hồi cho từng câu hỏi đạt tốc độ gần như tức thì.

2. **Quyết định:** Thiết kế `AdvancedRetrievalEngine` có khả năng tự phục hồi (resilient) khi một trong hai phương thức tìm kiếm gặp sự cố.  
   **Lý do/evidence:** Nếu một trong hai provider (Dense hoặc BM25) bị lỗi hoặc trả về danh sách rỗng, engine vẫn tự động fallback sử dụng kết quả còn lại mà không làm sập luồng xử lý của người dùng.  
   **Trade-off:** Cần bổ sung logic chuẩn hóa schema `SearchResult` thống nhất ở đầu ra để đảm bảo tính toàn vẹn dữ liệu cho khâu reranking tiếp theo.

## Kiểm thử và kết quả

- **Kiểm thử tự động:** Hoàn thành và vượt qua 117 dòng test trong `tests/test_advanced_retrieval.py`, bao gồm kiểm tra tính đúng đắn của schema, deduplication và cơ chế fallback.
- **Kết quả thực nghiệm:** Thực nghiệm đối chứng trong `retrieval_experiments.py` cho thấy sự kết hợp giữa BM25 và Dense giúp giải quyết triệt để vấn đề "bỏ sót từ khóa chuyên biệt" mà mô hình Vector đơn thuần thường gặp phải.
- **Lỗi đã phát hiện và xử lý:** Phát hiện lỗi BM25 trả về điểm số âm đối với các từ xuất hiện trong quá nhiều văn bản; đã bổ sung bộ lọc `float(score) <= 0` để chỉ giữ lại những đoạn trích thực sự có ý nghĩa thống kê.

## Điều còn hạn chế

- **Một hạn chế cụ thể:** Thuật toán BM25 hiện tại tách từ cơ bản theo Regex chữ cái, chưa tích hợp mô hình phân tích từ vựng (Word Segmentation / PyVi) chuyên biệt cho tiếng Việt đa âm tiết.
- **Nếu có thêm thời gian:** Tôi sẽ tích hợp thư viện tách từ tiếng Việt chuyên dụng để BM25 nhận diện các từ ghép tiếng Việt chuẩn xác hơn nữa.

## Xác nhận đóng góp

Tôi xác nhận nội dung trên phản ánh đúng phần việc của mình và có thể giải thích hoặc chạy lại trong buổi demo.

- Ngày: 20/09/2026
- Tên thành viên: Hoàng Anh Tài

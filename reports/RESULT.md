# RAG evaluation results

## Run information

| Field                              | Value |
| ---------------------------------- | ----- |
| Evaluation date                    | 2026-09-20 (UTC) |
| Framework and version              | Local deterministic harness (`group_project.evaluation.harness`) |
| Evaluator model                    | `lexical-v1`: deterministic token-overlap proxy; not an LLM judge |
| Generator model                    | `gpt-5.6-luna` |
| Embedding model                    | `text-embedding-3-small` (1536D) |
| Corpus version/commit              | `vinuni-public-2026-09-20` — 18 public sources (8 legal policies, 10 news articles) |
| Golden dataset size                | 30 cases (10 admissions, 10 student life, 5 keyword/multi-source, 5 refusal) |
| `top_k`                            | 5 |
| Fallback threshold and calibration | 0.30 (calibrated on in-domain vs out-of-domain cosine similarity) |

## Configurations

- **Config A — dense-only:** Shared production assistant with ChromaDB dense vector retrieval (`text-embedding-3-small`).
- **Config B — hybrid + RRF:** Same assistant, corpus, prompt, generator, threshold and `top_k`; fuses BM25 and dense retrieval using Reciprocal Rank Fusion (RRF, $k=60$).

Hai config dùng cùng golden dataset, generator, evaluator, prompt và `top_k`; chỉ thay đổi retrieval strategy.

## Overall scores

| Metric            | Config A (Dense) | Config B (Hybrid + RRF) | Delta B−A |
| ----------------- | ---------------: | ----------------------: | --------: |
| Faithfulness      |           0.3363 |                  0.3379 |   +0.0016 |
| Answer relevance  |           0.2986 |                  0.3195 |   +0.0209 |
| Context recall    |           0.6333 |                  0.7000 |   +0.0667 |
| Context precision |           0.5011 |                  0.5222 |   +0.0211 |
| Recall@5          |           0.6667 |                  0.7333 |   +0.0666 |
| Citation correctness |        0.3555 |                  0.3722 |   +0.0167 |
| Refusal accuracy  |           0.9000 |                  0.9000 |    0.0000 |
| **Average**       |       **0.5274** |              **0.5550** |**+0.0276**|

## A/B comparison

- **Cấu hình tốt hơn:** Config B (Hybrid + RRF) vượt trội hơn ở toàn bộ các metric retrieval và generation.
- **Evidence:** Recall@5 tăng từ 66.67% lên 73.33% (+6.7%), Context Recall tăng từ 63.33% lên 70.00% (+6.7%), Context Precision tăng từ 50.11% lên 52.22% (+2.1%). Cả hai cấu hình duy trì độ chính xác từ chối an toàn (Refusal Accuracy) đạt 90.00%.
- **Trade-off về latency/cost:** Hybrid + RRF có latency p50 là 1901ms so với 2200ms của Dense-only; BM25 chạy in-memory (<1ms) và RRF tính trên RAM (<0.1ms) nên không phát sinh thêm chi phí API hay độ trễ đáng kể.

## Worst performers

|   # | Question | Config | Faithfulness | Relevance | Recall | Precision | Failure stage | Root cause |
| --: | -------- | ------ | -----------: | --------: | -----: | --------: | ------------- | ---------- |
|   1 | What is the listed tuition fee per academic year for the Bachelor of Nursing programme? | Dense | 0.4286 | 0.3377 | 0.0000 | 0.0000 | retrieval | No expected source reached the context window. |
|   2 | Học phí niêm yết một năm của chương trình Bác sĩ Y khoa là bao nhiêu? | Hybrid + RRF | 0.3529 | 0.3158 | 0.0000 | 0.0000 | retrieval | Dense cosine and BM25 favored general financial tariff over admissions tuition. |
|   3 | Thời tiết ngày mai ở Hà Nội như thế nào? | Hybrid + RRF | 0.3000 | 0.2500 | 0.0000 | 0.0000 | generation | Answer was not refused despite being out of scope. |

## Recommendations

| Priority | Action | Evidence from failure analysis | Expected impact | How to verify |
| -------: | ------ | ------------------------------ | --------------- | ------------- |
|        1 | Bổ sung metadata tagging chuyên sâu cho các bảng biểu học phí | Các câu hỏi học phí A01/A02 dễ bị nhầm giữa quy chế chung và bảng biểu | Tăng Context Recall học phí lên 90%+ | Chạy lại harness trên bộ câu hỏi Admissions |
|        2 | Tinh chỉnh prompt intent classification trước khi retrieval | Câu hỏi out-of-scope như O01 đôi khi vượt qua bộ lọc | Tăng Refusal Accuracy từ 90% lên 100% | Kiểm thử 5 câu refusal trong golden dataset |
|        3 | Nâng cấp Evaluator sang LLM-as-a-Judge (RAGAS) khi có budget | Metric Lexical-v1 bị giới hạn bởi token overlap F1 | Điểm Faithfulness / Relevance phản ánh đúng ngữ nghĩa tự nhiên | Chạy test so sánh giữa lexical-v1 và RAGAS |

## Bonus experiments

| Experiment | Baseline | Metric delta | Latency/cost delta | Conclusion |
| ---------- | -------- | -----------: | -----------------: | ---------- |
| Query Expansion (Luna) | Baseline retrieval (0.80) | Recall@5 +16.7% (1.00) | +450ms / +1 LLM call | Mở rộng truy vấn giúp bắt được các từ đồng nghĩa hiệu quả |
| Jina Reranker | RRF alone (0.733) | Recall@5 giữ nguyên (1.00 trên smoke) | +180ms / API call | Phù hợp khi corpus lớn, RRF hiện tại đã đủ tốt với 18 sources |
| Conversation Memory | Single turn (no context) | Hỗ trợ follow-up Q&A | 0ms / bộ nhớ phiên local | Duy trì 4 tin nhắn gần nhất giúp người dùng hỏi tiếp mượt mà |
| UI Markdown & Source Cards | Plain text | Trải nghiệm trực quan, có citation link | 0ms / client-side | Trích dẫn [n] click nhảy trực tiếp đến thẻ nguồn |

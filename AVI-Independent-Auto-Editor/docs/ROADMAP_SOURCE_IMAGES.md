# Nghiên cứu nâng cấp tiếp theo — Source Selection & Image Selection

**Trạng thái:** đề xuất nghiên cứu, CHƯA có trong v0.3.4. Mục tiêu: áp dụng cho mọi thể loại và mọi kho video/ảnh mà người dùng có quyền sử dụng, không cứng hóa tin tức Hoàng gia hoặc 320 clip.

## A. Chọn source video gốc — các hướng kỹ thuật

| Hướng | Pipeline đề xuất | Lợi ích | Chi phí/rủi ro |
|---|---|---|---|
| **A1. Kho local + indexing** (ưu tiên v0.4) | Người dùng chọn thư mục/ổ đĩa → ffprobe + hash → chia cảnh PySceneDetect → trích keyframes → CLIP/SigLIP2 embeddings + Qwen captions → cache SQLite/FAISS | Nhanh khi dựng lại, không phụ thuộc internet, hỗ trợ nhiều chủ đề | Tốn thời gian index đầu; metadata danh tính cần duyệt |
| **A2. Tiếp nhận source qua URL có quyền** | Người dùng tự cung cấp URL hợp lệ → công cụ tải nếu điều khoản/giấy phép cho phép (yt-dlp tùy chọn) → ghi nguồn và bản quyền → index | Ít thao tác nhập file; biết nguồn video | Chính sách website, bản quyền, link hỏng, DRM |
| **A3. Tìm source dựa trên script** | Tách entity/event/action/place/time → tạo truy vấn đa ngôn ngữ → nguồn được phép/có API → trả danh sách ứng viên để duyệt → nhập source | Kho hiện tại thiếu footage có thể mở rộng | Rất dễ chọn tư liệu sai sự kiện; cần đối chiếu tiêu đề/ngày/sự kiện |
| **A4. Reranking theo ngữ cảnh thời gian** | Matching 2 tầng: retrieval top-K qua embeddings, Qwen xác minh nhiều khung hình và mô tả, kiểm tra continuity/timestamp rồi chọn | Giảm những cảnh nhìn giống nhưng sai hành động | Compute VRAM/latency, Qwen có thể suy diễn |
| **A5. Hybrid kho liên dự án** | Cache nội dung bất biến theo hash, bổ sung nhãn chỉnh tay, nhóm theo entity/event và bộ lọc nguồn | Học từ corrections, mở rộng theo dự án | Quản lý cache/conflict, privacy |

**Điểm quyết định:** với mọi hướng, metadata phải có `source_id`, hash, đường dẫn gốc, `source_start/end`, mô tả cảnh, entity được xác minh, điểm tin cậy, loại quyền sử dụng và lịch sử chọn. Không được coi CLIP score hoặc Qwen caption là bằng chứng sự kiện thực xảy ra.

## B. Chọn ảnh minh họa — các hướng kỹ thuật

| Hướng | Pipeline đề xuất | Mục tiêu |
|---|---|---|
| **B1. Ảnh người dùng** (ưu tiên số 1) | Chỉ mục ảnh local → bỏ trùng pHash/embedding → OCR/caption → chấm matching theo narration | Nguồn kiểm soát được và chất lượng phù hợp |
| **B2. Wikimedia Commons** | API tìm ảnh → `imageinfo`/`extmetadata` → tác giả, URL, license → tải preview → duyệt ứng viên | Nguồn có metadata giấy phép và gốc hình; cần xác minh từng file |
| **B3. Openverse** | API tìm ảnh → lọc license/sources → lưu tác giả và trang gốc → thẩm định license | Mở rộng nguồn CC/PD, giảm thao tác tìm tay |
| **B4. Lấy frame từ source được phép** | Chọn keyframe có chất lượng cao/ít chữ/ít nhòe, kiểm tra quyền sử dụng → dùng làm still với pan/zoom | Tận dụng video đã duyệt, không tìm ngoài |
| **B5. Ảnh tạo bằng AI (tùy chọn)** | Sinh ảnh minh họa cho khái niệm trừu tượng → gắn nhãn generated illustration, KHÔNG mô tả là ảnh sự kiện thật | Lấp khoảng trống về hình tượng trừu tượng; hạn chế gây hiểu lầm |

## C. Thiết kế engine chọn cuối cùng

1. Narration → Whisper timestamp → semantic beats → trích entity/hành động/địa điểm/thời gian nếu có.
2. Tìm clip và ảnh local trước; khi thiếu mới tìm nguồn có giấy phép/nguồn được người dùng duyệt.
3. Retrieval embedding top-K → Qwen rerank nội dung hiển thị trong khung hình → confidence gate. Các thuộc tính danh tính/sự kiện cần bằng chứng metadata rõ ràng hoặc duyệt tay.
4. Xếp hạng với **hard constraint đúng nội dung**; sau đó ưu tiên **clip chưa dùng khi tương đương**. Cho phép tái sử dụng khi clip cũ phù hợp hơn.
5. Khi không đạt ngưỡng: đánh dấu `needs_review`, có thể dùng hình chung được mô tả là minh họa; không bịa việc có cảnh quay sự kiện.
6. `report.csv` nên có `narration`, `timecode`, `candidate_source`, `match_score`, `entity_verification`, `license`, `used_before`, `selection_reason`, `review_required`.

## D. Cách kiểm chứng trước khi phát hành

Lấy tập chuẩn có nhiều chủ đề độc lập: tin tức Hoàng gia, F1, công nghệ, kinh doanh, lịch sử, phóng sự. Gắn nhãn thủ công từng beat/video candidate: đúng người, hành động, sự kiện, thời điểm và tính phù hợp. Theo dõi top-1/top-5 relevance, tỷ lệ sai danh tính, tỷ lệ shot cần duyệt, số nguồn trùng và thời gian index/render. So với baseline v0.3.4 trên cùng tập; không lấy tỷ lệ 70% một dự án làm kết quả bảo đảm cho ngành khác.

## E. Tài liệu kỹ thuật tham khảo (2026-11)

- PySceneDetect (chia cảnh): https://www.scenedetect.com/docs/latest/
- Hugging Face SigLIP2 (image-text representation): https://huggingface.co/docs/transformers/model_doc/siglip2
- FAISS (vector similarity search): https://faiss.ai/
- Openverse API (image search/license filters): https://api.openverse.org/v1/
- MediaWiki Imageinfo + extmetadata: https://www.mediawiki.org/wiki/API:Imageinfo
- Creative Commons licenses: https://creativecommons.org/share-your-work/cclicenses/
- yt-dlp source metadata (cần kiểm tra điều khoản từng nguồn): https://github.com/yt-dlp/yt-dlp

**Khuyến nghị thứ tự:** v0.4 làm **A1 + A4 + B1** (index local vững, match chính xác hơn); tiếp theo bổ sung **B2/B3** với metadata license, rồi mới **A2/A3** nhận source URL/tìm online. Giữ B5 chỉ là minh họa có nhãn rõ ràng.

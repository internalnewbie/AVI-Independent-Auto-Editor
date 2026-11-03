# AVI Independent Auto Editor — v0.3.4 Consolidated

Đây là bản phát hành **hợp nhất**, không cần cài từng hotfix v0.3.3.

## Các bản vá đã tích hợp

1. **One-click / môi trường Python:** `CAI_MOT_LAN.bat` dùng đúng `.venv`, cập nhật pip cũ khi cần, dùng lại thư viện và model đã cài; PyTorch CUDA 12.6 cho NVIDIA (CPU trên máy không có CUDA).
2. **Whisper + PyAV:** cố định `av==18.1.0` trong `requirements-ai.txt`, thêm kiểm tra version vào installer và bài thử giải mã WAV thực tế để ngăn lỗi `open() got an unexpected keyword argument 'metadata_errors'`.
3. **Qwen JSON:** yêu cầu JSON schema, đọc JSON nằm trong Markdown/chuỗi thừa, thử lại nếu cấu trúc lỗi và lưu response lỗi vào `~/.avi_autoedit_cache/qwen_catalog/qwen_errors/`.
4. **Qwen trả response rỗng (`done_reason=length`):** dùng mặc định model `qwen3-vl:4b-instruct`, giới hạn token rộng hơn, tự thử lại với prompt ngắn và số frame ít hơn. Không khẳng định sẽ giải quyết được mọi lỗi VRAM/model.
5. **Model mặc định:** `qwen3-vl:4b-instruct` trong GUI, CLI, pipeline và bộ cài Ollama; ánh xạ alias `qwen3-vl:4b` cũ sang Instruct để giảm lỗi chọn nhầm.
6. **Giao diện cài:** chỉ còn 2 file BAT tại thư mục chính: `CAI_MOT_LAN.bat` và `CHAY_AUTO_EDIT.bat`.

## Những gì không thay đổi

- Whisper → timecoded narration; CLIP → tìm ứng viên hình; Qwen → mô tả ngữ nghĩa footage.
- Ưu tiên hình đúng narration, clip chưa sử dụng khi mức phù hợp tương đương, tái sử dụng khi clip cũ phù hợp hơn.
- Xuất timeline Premiere XML, MP4 (nếu bật render), JSON/CSV báo cáo.
- Cache Qwen, Hugging Face models. Không nhúng model nhiều GB vào ZIP.

## Trạng thái kiểm thử

- Python unit tests (mock Qwen/Ollama, không tải model); ffmpeg smoke test với nguồn tự tạo và WAV, xác minh H.264/AAC.
- **Chưa kiểm thử trực tiếp việc cài/cập nhật Windows, GPU RTX 3060, hoặc suy luận Qwen/Whisper/CLIP thực bằng trọng số model trong môi trường này.**

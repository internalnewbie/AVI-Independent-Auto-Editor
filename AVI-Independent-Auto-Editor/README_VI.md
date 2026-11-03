# AVI Independent Auto Editor v0.3.4 — Consolidated Windows Tester

Bản ZIP này **hợp nhất tất cả các hotfix** của v0.3.3 thành một mã nguồn. Không cần cài từng hotfix nữa. Đây là **mã nguồn chạy bằng Python trên Windows**, chưa phải file Setup.exe tự chứa toàn bộ mô hình AI.

## Cài đặt / nâng cấp

**Cài mới:** Giải nén ZIP → mở thư mục `AVI_Auto_Editor_v0.3.4` → chạy `CAI_MOT_LAN.bat` → khi thành công chạy `CHAY_AUTO_EDIT.bat`. Cần Internet lần đầu và ổ đĩa đủ trống để tải PyTorch/CUDA, Qwen và các model.

**Nâng cấp từ v0.3.x (khuyên dùng nếu máy đã cài thành công):** Đóng Auto Editor và sao lưu thư mục ứng dụng cũ. **Copy toàn bộ nội dung bên trong** thư mục `AVI_Auto_Editor_v0.3.4` của ZIP **vào chính thư mục Auto Editor đang sử dụng**, chọn Replace. **Không xóa thư mục `.venv`, không xóa thư mục output hoặc model/cache.** Chạy `CAI_MOT_LAN.bat` một lần để nó kiểm tra bản PyAV và model Instruct, sau đó `CHAY_AUTO_EDIT.bat`.

**Chú ý:** Nếu giải nén sang một thư mục mới, chương trình sẽ tạo `.venv` mới và phải cài lại các thư viện Python trong môi trường đó. Ollama/model Qwen của cùng tài khoản Windows và model cache Hugging Face thường được dùng lại. Các launcher cài đặt cũ có thể được `CAI_MOT_LAN.bat` chuyển vào `_legacy_installers` nếu thầy nâng cấp trực tiếp trong thư mục cũ.

## File chính

- `CAI_MOT_LAN.bat`: **một thao tác cài** Python/venv/requirements, CUDA hoặc CPU, Whisper, CLIP, FFmpeg, Ollama và model `qwen3-vl:4b-instruct`. Bỏ qua thành phần đã đạt yêu cầu. Không chủ động xóa/cài lại model đã có.
- `CHAY_AUTO_EDIT.bat`: mở giao diện. **Model mặc định luôn là `qwen3-vl:4b-instruct`**.

## Cách tester trước khi làm video dài

1. Chọn folder footage, một folder output trống. Quét 1–3 cảnh bằng Qwen, xem `footage_catalog.csv`.
2. Chọn narration 30–60 giây; bật Whisper + CLIP + Qwen; kiểm tra `match_report.csv` và bản dựng MP4 trước khi xử lý cả dự án.
3. Với narration dài, nhớ kiểm tra các đoạn có `review` vì CLIP/Qwen có thể mô tả và nhận định sai. Không xác nhận danh tính nhân vật chỉ từ mô tả AI.

## Các lỗi đã xử lý

- **`metadata_errors`**: pin PyAV 18.1.0, installer tự nhận diện version lệch và thử decode WAV.
- **Qwen JSON không hợp lệ**: parse JSON có Markdown, tự retry và lưu response vào `%USERPROFILE%\.avi_autoedit_cache\qwen_catalog\qwen_errors`.
- **Qwen response rỗng `done_reason=length`**: mặc định Qwen Instruct không thinking; tăng token và rút prompt khi retry. Nếu còn lỗi, gửi JSON mới và các lệnh `ollama list`, `ollama ps`.
- **Lỗi `torch`, `ctranslate2`, `faster-whisper` không tồn tại**: launcher installer luôn sử dụng `.venv` đúng thư mục, không cài qua IDLE/pythonw.

## Giới hạn

- RTX 3060 hỗ trợ CUDA nhưng PyTorch CUDA có sẵn **không bảo đảm** CTranslate2/Whisper CUDA hoạt động; khi khởi tạo CUDA lỗi chế độ Auto có thể chuyển phần đó về CPU.
- Nếu Qwen thiếu model, mạng lỗi hoặc hết VRAM, quá trình phân tích cảnh có thể thất bại. Lỗi mới sẽ có JSON diagnostics trong cache.
- Video dựng lại từ footage cần được kiểm tra bản quyền nếu nguồn không thuộc quyền sử dụng của thầy.
- XML Premiere tham chiếu đường dẫn footage/voice gốc. Không di chuyển source sau khi xuất.
- Chưa kiểm thử installer, model suy luận thật hoặc GUI Windows trên máy thầy từ môi trường tạo ZIP này.

## Log khi gặp lỗi

`logs\setup_all_latest.log` và `logs\install_latest.log` đối với cài đặt; thư mục `qwen_errors` đối với mô tả Qwen. Khi cần giúp sửa lỗi, gửi log **mới tạo** từ lần chạy thực tế.

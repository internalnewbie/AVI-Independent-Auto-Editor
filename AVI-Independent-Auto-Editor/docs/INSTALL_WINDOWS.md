# Cài đặt trên Windows (v0.3.4)

1. Tải repository về, giải nén/clone vào một đường dẫn cố định, ví dụ `D:\Projects\AVI-Independent-Auto-Editor`.
2. Cài trên Windows 64-bit. Bắt đầu với Python 3.11 (bản installer sẽ kiểm tra/yêu cầu), driver NVIDIA mới nếu muốn GPU; vẫn hỗ trợ CPU khi môi trường tương thích.
3. Chạy `CAI_MOT_LAN.bat` **bằng nhấp đúp**, không mở `install_auto.py` trong IDLE. Chương trình tạo/dùng lại `.venv` trong đúng thư mục repository.
4. Installer sẽ tìm ffmpeg/ffprobe, Ollama và model `qwen3-vl:4b-instruct`; nếu thiếu có thể cần WinGet/Internet. Kiểm tra log nếu cài tự động thất bại.
5. Chạy `CHAY_AUTO_EDIT.bat`. Kiểm tra thiết bị AI trong giao diện/log. Nếu PyTorch chạy CUDA nhưng Whisper CPU, kiểm tra thêm CTranslate2/cuBLAS/cuDNN thay vì cài lại cả hệ thống.
6. Test 1–3 cảnh và narration 30–60 giây. Chạy full project sau khi đã duyệt mô tả ảnh, matching và audio.

## Giữ lại thư viện khi nâng cấp

Nếu đang dùng bản cài ổn định, **sao lưu** ứng dụng trước. Chép mã nguồn mới vào **cùng thư mục** để giữ `.venv` và đường dẫn cũ, rồi chạy lại `CAI_MOT_LAN.bat` để kiểm tra dependency. Cài sang thư mục mới thường tạo `.venv` mới, nhưng Ollama/model trong hồ sơ Windows có thể được dùng lại.

## File quan trọng

- `CAI_MOT_LAN.bat` — cài/kiểm tra dependencies.
- `CHAY_AUTO_EDIT.bat` — khởi động giao diện.
- `requirements-ai.txt` — AI libraries, hiện pin `av==18.1.0` để tránh xung đột `metadata_errors` với faster-whisper đã thử nghiệm.
- `logs/setup_all_latest.log`, `logs/install_latest.log` — log lỗi cài đặt, **không upload công khai**.
- `%USERPROFILE%\.avi_autoedit_cache\qwen_catalog\qwen_errors` — response lỗi Qwen khi cần chẩn đoán.

Đây là source snapshot tester, không phải installer `.exe` phát hành chính thức.

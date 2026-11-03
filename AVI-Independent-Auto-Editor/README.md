# AVI Independent Auto Editor

**Phiên bản:** v0.3.4 (GitHub-ready source snapshot)  
**Nền tảng thử nghiệm chính:** Windows x64  
**AI:** faster-whisper + CLIP + Qwen3-VL (Ollama)  
**Hệ thống:** tự chọn CUDA/CPU khi các thư viện và driver tương thích

Một công cụ thử nghiệm dựng video từ **narration và kho footage**. Hệ thống phân tích narration theo mốc thời gian, lập chỉ mục cảnh quay, gợi ý footage phù hợp và xuất timeline/video. Hướng phát triển là **không gắn cứng một chủ đề hay số lượng footage**.

> **Độ chính xác:** Chủ dự án báo cáo khoảng **70%** độ khớp narration–hình trên một dự án tin tức Hoàng gia cụ thể. Đây là kết quả kiểm thử người dùng, **không phải benchmark chung**, và chưa được xác minh độc lập trên các thể loại khác. Không nên coi mô tả của Qwen/CLIP là bằng chứng xác minh nhân vật, nơi chốn hoặc sự kiện.

## Chạy trên Windows

1. Cài Git (nếu muốn clone/push); tải hoặc clone repository này.
2. Mở thư mục gốc, nhấp đúp **`CAI_MOT_LAN.bat`** để kiểm tra và cài Python/venv, FFmpeg, các thư viện AI, Ollama và model còn thiếu. Cần Internet và dung lượng ổ đĩa trống trong lần cài đầu.
3. Khi trình cài báo thành công, nhấp đúp **`CHAY_AUTO_EDIT.bat`** để mở giao diện.
4. Thử trên **1–3 footage** và một đoạn narration **30–60 giây** trước. Kiểm tra `footage_catalog.csv`, `match_report.csv` và preview; sau đó mới chạy dự án dài.

Cấu hình model Qwen mặc định: **`qwen3-vl:4b-instruct`**. Cài đặt thực tế trên Windows và tốc độ CUDA phụ thuộc phiên bản driver, PyTorch, CTranslate2/cuDNN và Ollama. Tool có thể sử dụng CPU dự phòng. Nếu cài đặt có lỗi, xem `logs/setup_all_latest.log` và `logs/install_latest.log` (các file này không được commit lên GitHub).

Hướng dẫn chi tiết và lưu ý khắc phục lỗi: **[README_VI.md](README_VI.md)** và **[docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md)**.

## Các khối chức năng

| Thành phần | Vai trò |
|---|---|
| Whisper | Nhận dạng narration, chia timestamp/beat |
| CLIP | Truy xuất footage theo tương đồng hình–văn bản |
| Qwen3-VL | Mô tả cảnh và hỗ trợ đánh giá lại ứng viên |
| Cache | Lưu mô tả, hạn chế phân tích lại file không thay đổi |
| Timeline / Exporter | Dựng theo lời thoại; xuất video MP4 và Premiere XML |
| Auto device selection | Tự kiểm tra GPU, chuyển CPU khi cần |

**Quy tắc lựa chọn:** độ chính xác so với narration được ưu tiên số một. Khi các ứng viên phù hợp tương đương, ưu tiên footage chưa dùng; có thể dùng lại clip cũ nếu phù hợp hơn. Không cố tránh lặp mà chọn sai người/sai sự kiện.

## Kiểm thử code (không tải AI)

```shell
python -m unittest discover -s tests -v
```

Các unit test chủ yếu mock model và dịch vụ; **không xác nhận chất lượng suy luận Qwen, Whisper, CLIP trên GPU thực**. Workflow CI thực hiện các bài kiểm tra này, không tự tải nhiều GB model AI.

## Bảo mật, dữ liệu và bản quyền

Repository **không chứa** venv, file nguồn cá nhân, log dự án, trọng số model, bộ cài bên thứ ba hay các module `.pyd` của AVI gốc. Công cụ có thể tải thành phần từ nhà cung cấp khi cài đặt. Chỉ xử lý/đăng tải footage và hình ảnh có quyền sử dụng; kiểm tra giấy phép và ghi công khi cần. Phần dựng minh họa không xác thực bản thân sự kiện, nên cần phân biệt nội dung hư cấu/giả định với tư liệu thật.

**Chưa cấp giấy phép nguồn mở cho repository này.** Nếu muốn phát hành public cho người khác sao chép/sửa đổi/phân phối, chủ dự án cần chọn license thích hợp trước. Xem [docs/REPOSITORY_POLICY.md](docs/REPOSITORY_POLICY.md).

## Sắp tới

Nghiên cứu **lựa chọn source gốc** theo chủ đề/kịch bản và **chọn/tìm ảnh minh họa**. Tổng hợp nhiều hướng kỹ thuật và thứ tự ưu tiên ở [docs/ROADMAP_SOURCE_IMAGES.md](docs/ROADMAP_SOURCE_IMAGES.md). Đây là nghiên cứu, **chưa tích hợp** vào v0.3.4.

**Cách đẩy lên GitHub:** [docs/GITHUB_UPLOAD.md](docs/GITHUB_UPLOAD.md).

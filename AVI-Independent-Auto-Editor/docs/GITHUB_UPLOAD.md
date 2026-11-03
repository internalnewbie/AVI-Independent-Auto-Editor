# Đẩy repository lên GitHub

## Qua GitHub Desktop (dễ nhất trên Windows)

1. Giải nén ZIP repo và mở GitHub Desktop.
2. Chọn **File → Add local repository**. Nếu thư mục chưa là Git repo, chọn **Create a repository** tại thư mục này.
3. Commit toàn bộ file source đã được lọc bởi `.gitignore`.
4. Chọn **Publish repository**; **để Private** trong giai đoạn thử nghiệm.

## Qua Git CLI

1. Tạo **repository trống** trên GitHub, không tick thêm README/license/gitignore vì bộ source đã có README và `.gitignore`.
2. Mở Git Bash / PowerShell trong thư mục source (không phải thư mục cha).
3. Thực hiện (thay địa chỉ repository thật):

```bash
git init -b main
git add .
git status
git commit -m "Initial source release v0.3.4"
git remote add origin https://github.com/USERNAME/AVI-Independent-Auto-Editor.git
git push -u origin main
```

**Trước khi push**, xem kỹ `git status` / `git diff --cached --name-only`. Không commit `.venv`, clip, narration, cache, model, log, key/token. Trường hợp đã add file bí mật vào lịch sử thì chỉ thêm `.gitignore` là **không đủ** để xóa khỏi lịch sử commit.

### Khuyến nghị phát hành

Dùng tag `v0.3.4` cho source snapshot, chưa nên gọi Stable. Chọn chế độ **Private** cho đến khi xác nhận quyền đối với mã, tài nguyên, nhãn hiệu và giấy phép phân phối. Chưa có `LICENSE` nên không mặc nhiên là mã nguồn mở.

Nguồn hướng dẫn: https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github

# 🗂 Librarian — dọn thư mục bằng luật cứng, model chỉ cho phần mù mờ

Sau mỗi đợt việc lớn (ScanReader chạy xong một tệp phiếu, ResearchTrail nhận
một zip mới, ai đó tải một installer về rồi quên) luôn có vài thư mục/file lạc
trôi ở gốc repo. Xếp lại chúng không cần Gemini, không cần một model to: 90%
ca đoán được bằng đuôi file + tên thư mục, phần còn lại (thư mục tên mù mờ,
nội dung trộn) mới cần một model đọc *tên* rồi đoán — `qwen3:14b` chạy local,
miễn phí, đủ dùng, không cần viết mã hay xem ảnh.

## Nguyên tắc an toàn

- `scan` **chỉ đọc đĩa và ghi một file kế hoạch** (`vault/processed/librarian_plan.json`)
  — không bao giờ tự xóa, tự di chuyển.
- `apply` in lại toàn bộ kế hoạch, hỏi `yes` trước khi làm gì (trừ khi
  `--yes`), và **luôn bỏ qua các mục action=delete** trừ khi có thêm
  `--allow-delete`.
- Không bao giờ gửi *nội dung* file đi đâu cả — model chỉ nhận tên file/thư
  mục và một vài tên file con để đoán chủ đề.

## Lệnh

```bash
cd Librarian

# 1. Quét gốc repo, xem đề xuất, không đụng file nào
python -m librarian scan

# Quét một thư mục khác (vd một chỗ tải về ngoài repo)
python -m librarian scan "G:\My Drive\Downloads"

# Chỉ dùng luật cứng, khỏi cần Ollama đang chạy
python -m librarian scan --no-llm

# 2. Xem lại vault/processed/librarian_plan.json, rồi thực thi phần MOVE
python -m librarian apply

# Cho phép xóa luôn phần rác (bytecode/cache) đã đề xuất
python -m librarian apply --allow-delete
```

## Luật cứng (rules.py) — áp trước, không tốn token

| Khớp | Đề xuất |
|---|---|
| `__pycache__`, `.pyc`, `Thumbs.db`, `.DS_Store`, `*.tmp`, `*.bak` | xóa |
| có `pyvenv.cfg` / `site-packages` bên trong | gắn cờ, không tự động đụng (có thể rất to) |
| có `.git` riêng bên trong | gắn cờ (có thể là clone ngoài, không phải nhánh của repo) |
| chỉ còn `.pyc`, hết `.py` nguồn | gắn cờ "husk" — kiểm tra source có nằm trên nhánh git khác |
| file lẻ `.jpg/.png/.heic/...` | → `vault/raw/photos/inbox` |
| file lẻ `.m4a/.mp3/.wav` | → `vault/raw/audio` |
| file lẻ `.pdf/.docx/.xlsx/.pptx` | → `vault/raw/documents` |
| `.exe/.msi/.msix/.zip/.7z` | → `_archive` |
| thư mục tên có ngày hoặc `[Chủ đề]` | → `vault/raw/research/<tên>` |

Cái gì không khớp dòng nào ở trên mới đi tiếp sang `qwen3:14b`
(`ollama_classify.py`) — model trả về bucket + lý do một câu; độ tin "thấp"
chỉ được gắn cờ để tự xem, không tự đề xuất di chuyển.

## Vì sao không dùng Gemini / qwen3.6

- Gemini free tier chỉ 20 request/ngày — dành cho ảnh mới + nhật ký, không
  phí vào việc phân loại thư mục.
- `qwen3.6` (vision, 36B) chậm hơn nhiều và là model dành cho backlog ảnh —
  việc này chỉ cần đọc tên file, `qwen3:14b` vừa đủ và nhanh hơn hẳn.

# 📠 ScanReader — bản scan giấy → Markdown nguyên văn

Nhánh đọc **PDF scan điền tay** (phiếu khảo sát, phiếu trả lời, biểu mẫu giấy)
thành file Markdown chép **nguyên văn từng trang** — cả chữ in sẵn lẫn chữ viết
tay, checkbox, thang điểm khoanh tròn, chữ gạch xóa. Không tóm tắt, không dịch,
không bịa: sản phẩm là tờ giấy dưới dạng text, để người (hoặc AI phiên sau) đọc
lại và đối chiếu được từng trang.

Sinh ra 2026-07-28 cho `KOI Recall Data.pdf` — 60 trang phiếu recall phỏng vấn
điện thoại (dự án KOI · Chinsu 30+5°N) viết tay hoàn toàn, không có lớp text.

## Chạy

```powershell
cd ScanReader

# soi cấu trúc file trước — 0 call
python -m scan_reader pages "G:\My Drive\...\KOI Recall Data.pdf"

# chép toàn bộ (mặc định gemini-3.6-flash, 6 trang/call)
python -m scan_reader scan "G:\My Drive\...\KOI Recall Data.pdf"

# chạy thử ít trang / để dành quota
python -m scan_reader scan "...pdf" --pages 1-2
python -m scan_reader scan "...pdf" --limit 5          # tối đa 5 call lần này

# local hoàn toàn (miễn phí, chậm, cần mở Ollama) — 1 trang/call
python -m scan_reader scan "...pdf" --model ollama:qwen3.6

python -m scan_reader list                 # đã chép những gì
python -m scan_reader show "KOI Recall"    # in nội dung Markdown
python -m scan_reader status               # quota hôm nay
```

## Output

- **Cạnh file PDF gốc**: `<tên file>.md` — nằm ngay trong thư mục dự án
  (tắt bằng `--no-beside`).
- **Bản chuẩn trong vault**: `vault/processed/scanreader/<tên file>.md`.
- **Store**: `vault/processed/scan_reader.json` — chép từng trang, lưu sau từng
  call; trang lỗi/thiếu tự retry lần chạy sau (fail-forward). File .md được
  dựng lại sau mỗi call nên dừng giữa chừng vẫn có bản đọc được, trang thiếu
  ghi rõ *(chưa trích xuất được)*.

## Quy ước trong file .md

| Ký hiệu | Nghĩa |
|---|---|
| `**đậm**` | chữ viết tay trên phiếu |
| ☑ / ☐ | ô tick được đánh / để trống |
| `(khoanh)` | phương án được khoanh tròn |
| `~~chữ~~` | chữ bị gạch xóa nhưng còn đọc được |
| `(?)` | ký tự/từ đọc không chắc |
| `[không đọc được]` | hoàn toàn không luận ra |
| `(bỏ trống)` | mục in sẵn nhưng không được điền |

## Cách nó tiết kiệm quota (và vì sao chunk 6 trang)

- Mỗi call Gemini gửi **6 trang** (≈ 3 phiếu 2-trang nguyên vẹn) → 60 trang ≈
  10-11 call trong trần 20/ngày của `gemini-3.6-flash`. Chỉnh bằng
  `--pages-per-call`; đừng tham to — output quá dài sẽ bị cắt, JSON hỏng,
  retry lại tốn thêm call.
- Trước **mỗi** call đều hỏi sổ quota (`second_brain.quota`); hết trần là dừng
  ngay, không đốt call chỉ để nhận 429.
- Chữ viết tay đi `gemini-3.6-flash` theo bảng đo PLAYBOOK; `ollama:qwen3.6`
  là đường lui riêng tư/miễn phí.

## Chi tiết kỹ thuật đáng nhớ

- **Ảnh đưa cho model là JPEG scan GỐC nhúng trong PDF** (không re-render) —
  bài học "+30% OCR khi ăn file gốc" của PhotoRecall. Nhưng scanner hay lưu
  ảnh nằm ngang + cờ `/Rotate` trong PDF: gửi ảnh thô là chữ nằm ngang, model
  đọc tệ hẳn — `pdf.py` tự xoay đứng lại (1 lần transpose q92) trước khi gửi.
  Trang không phải scan thuần (có lớp text, nhiều ảnh, ma trận đặt ảnh xoay/lật)
  thì fallback render 220 dpi.
- Trang do model tự đánh số lại từ 1 (thỉnh thoảng) được map về đúng số trang
  thật theo thứ tự gửi ảnh.

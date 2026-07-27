# Tools — tiện ích lẻ

Chỗ cho các tool một-file phục vụ việc cá nhân, không thuộc nhánh sub-project
nào. Mỗi tool tự chứa toàn bộ hướng dẫn trong chính nó.

## Nen_PDF_Google_Drive.ipynb

Notebook Colab nén hàng loạt PDF trong một thư mục Google Drive bằng
Ghostscript — file nén **cùng tên**, xuất sang thư mục khác, file gốc giữ
nguyên.

**Cách dùng:** mở [colab.research.google.com](https://colab.research.google.com)
→ Upload notebook này → sửa `SRC` / `DST` ở Cell 3 → chạy lần lượt 3 cell.

- Mức nén chỉnh bằng `QUALITY`: `/screen` (72 dpi, mạnh nhất) · `/ebook`
  (150 dpi, mặc định — chữ scan vẫn rõ) · `/printer` (300 dpi, nén nhẹ).
- Nén lỗi hoặc file nén to hơn bản gốc → tự copy nguyên bản, không bao giờ
  mất file.

Sinh ra để nén bộ hồ sơ Chứng Minh Tài Chính (12 PDF scan ~53 MB) cho đủ nhẹ
để upload cổng nộp hồ sơ.

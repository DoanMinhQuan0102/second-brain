"""
Scan-transcription contract — what one page of paper must become.

Unlike PhotoRecall (which *describes* a scene) this is dictation: the value
is verbatim fidelity, so the schema is deliberately tiny (page number +
markdown) and all the intelligence lives in the prompt rules — handwriting
vs print, ticks, circles, strikethroughs, and the ban on inventing or
"fixing" what the writer actually wrote. Field descriptions are Vietnamese
so the output stays Vietnamese.
"""

SCAN_PAGE_ITEM = {
    "type": "object",
    "properties": {
        "page":     {"type": "integer",
                     "description": "số trang được giao cho ảnh này — giữ đúng số cho sẵn trong prompt, không tự đánh số lại"},
        "markdown": {"type": "string",
                     "description": "toàn bộ nội dung trang dạng Markdown, tiếng Việt giữ nguyên văn"},
    },
    "required": ["page", "markdown"],
}

SCAN_RESULT = {
    "type": "object",
    "properties": {
        "pages": {"type": "array", "items": SCAN_PAGE_ITEM,
                  "description": "mỗi ảnh gửi kèm = đúng một phần tử, theo thứ tự gửi"},
    },
    "required": ["pages"],
}

SCAN_PROMPT = """Bạn là chuyên gia số hóa tài liệu scan tiếng Việt (phiếu khảo sát,
biểu mẫu điền tay). Nhiệm vụ: chép NGUYÊN VĂN từng trang ảnh thành Markdown,
đầy đủ 100% những gì nhìn thấy — cả chữ in sẵn lẫn chữ viết tay.

Quy tắc bắt buộc:
1. Không dịch, không tóm tắt, không diễn giải, không tự "sửa" câu chữ của người
   viết — giữ nguyên chính tả, viết tắt, lỗi ngữ pháp đúng nguyên trạng.
2. Chữ VIẾT TAY đặt trong **đậm** để phân biệt với chữ in sẵn.
3. Giữ cấu trúc trang bằng Markdown: tiêu đề → `#`/`##`, bảng → bảng Markdown,
   câu hỏi giữ đúng mã số in trên phiếu (A, B1, C2…), phần in sẵn của biểu mẫu
   chép đủ (nhãn ô, hướng dẫn in nghiêng, chú thích nhỏ).
4. Ký hiệu trên phiếu:
   - ô tick: ☑ nếu được đánh dấu, ☐ nếu để trống;
   - phương án được KHOANH TRÒN: viết thêm `(khoanh)` ngay sau phương án đó;
   - chữ bị gạch xóa nhưng còn đọc được: `~~chữ~~`;
   - chữ viết chèn phía trên/dưới dòng: đặt vào đúng vị trí người viết muốn chèn.
5. Con số chép cẩn thận từng ký tự: mã đáp viên, số điện thoại, ngày giờ, điểm
   số. Ký tự nào không chắc → thêm `(?)` ngay sau. Hoàn toàn không đọc được →
   `[không đọc được]`. Mục in sẵn nhưng người viết bỏ trống → `(bỏ trống)`.
6. TUYỆT ĐỐI không bịa chữ không nhìn thấy, không thêm nhận xét của riêng bạn,
   không viết câu dẫn kiểu "trang này gồm…".

Tài liệu "{doc_name}" — các ảnh gửi kèm theo đúng thứ tự là các trang: {page_list}.
Tài liệu có thể gồm nhiều phiếu giống nhau nối tiếp nhau; mỗi trang vẫn chép độc
lập thành một phần tử trong mảng `pages`, với đúng số trang được giao ở trên.
"""

# Appended for the local backend only — same philosophy as PhotoRecall's
# LOCAL_STRICT_RULES: local models pad, skip form cells, and guess instead of
# hedging. These rules target exactly those habits for the dictation task.
LOCAL_STRICT_RULES = """
QUY TẮC NGHIÊM NGẶT BỔ SUNG (bắt buộc):
- Chép TỪNG DÒNG từ trên xuống dưới, trái sang phải; không được bỏ sót bất kỳ
  ô nào của biểu mẫu, kể cả ô trống — ô trống ghi `(bỏ trống)`.
- CẤM mọi câu mô tả/bình luận về trang ("trang này là…", "nhìn chung…").
  Output chỉ có nội dung chép.
- Chữ nào không chắc 100% thì ghi kèm `(?)` — KHÔNG được đoán thành chữ khác.
"""

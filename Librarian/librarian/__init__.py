"""
Librarian — dọn thư mục Second Brain bằng luật cứng trước, model local sau.

Mỗi lần scan xong đợt việc lớn (ResearchTrail, ScanReader, một zip Takeout mới)
lại có vài thư mục lạc trôi ở gốc repo hoặc trong một chỗ tải về nào đó — cần
xếp vào đúng vault/raw/*, đưa vào _archive/, hoặc để yên vì đó là mã nguồn.
Việc này không cần Gemini: 90% ca là đuôi file + tên thư mục đã đủ đoán, phần
còn lại (thư mục tên mù mờ, nội dung hỗn hợp) mới cần một model đọc tên file
và đoán — qwen3:14b chạy local, miễn phí, đủ cho việc phân loại này (không
cần vision, không cần viết mã, chỉ cần hiểu ngữ cảnh ngắn).

Nguyên tắc: scan chỉ ĐỀ XUẤT, không bao giờ tự xóa hay tự di chuyển. apply
chỉ thực thi sau khi người dùng xem plan và gõ "yes".

Path bootstrap mirrors Journal's: repo root cho second_brain (dùng chung
OLLAMA_URL nếu second_brain có, và DRIVE_ROOT nếu cần).
"""

import sys
from pathlib import Path

_PARENT_ROOT = Path(__file__).resolve().parents[2]   # Second Brain Project/
if str(_PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PARENT_ROOT))

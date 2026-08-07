# Tools — tiện ích lẻ

Chỗ cho các tool một-file phục vụ việc cá nhân, không thuộc nhánh sub-project
nào. Mỗi tool tự chứa toàn bộ hướng dẫn trong chính nó.

## switch_model.py — đổi model đằng sau Claude Code

Claude Code đọc `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` lúc khởi động.
Trỏ hai biến đó sang endpoint Anthropic-compatible của nhà khác là chạy được
model khác trong đúng giao diện Claude Code — không sửa dòng code nào.

```powershell
cd Tools
python switch_model.py                     # xem đang dùng gì + model local đang có
python switch_model.py openrouter --test   # free tier, không cần thẻ — dùng để THỬ
python switch_model.py --list-free         # model ":free" đang sống (danh sách đổi liên tục)
python switch_model.py deepseek            # DeepSeek, trả theo token, không thuê bao
python switch_model.py glm                 # Z.ai GLM Coding Plan ($18/tháng)
python switch_model.py claude              # xoá override, về gói Claude
```

> Bản đầu viết bằng `.ps1` và **chạy không được**: Google Drive đóng dấu
> Mark of the Web (`Zone.Identifier` ZoneId=3) lên mọi file trong `G:`, mà
> execution policy của máy là `RemoteSigned` → PowerShell coi script là "tải
> từ Internet" và đòi chữ ký số. `Unblock-File` gỡ được một lần nhưng sync lại
> đóng dấu lại. Python không đụng execution policy nên miễn nhiễm — cùng họ
> với bài học "REST thắng SDK khi môi trường cứng đầu" (PLAYBOOK #7). **Đừng
> viết `.ps1` mới trong repo này.**

### Thử $0 trước khi trả tiền

Thứ tự leo thang, rẻ trước:

1. **Local** — `qwen3-coder:30b-a3b-q4_K_M` đã cài sẵn, miễn phí vĩnh viễn.
   Dùng để thử xem *quy trình ba tầng* có hợp tay không. Nếu quy trình không
   hợp thì trả $18 cũng không cứu được.
2. **OpenRouter free tier** — key không cần thẻ, ~50 request/ngày. Endpoint
   `https://openrouter.ai/api` nói đúng giao thức Anthropic nên cắm thẳng vào
   Claude Code. Tính tới 2026-08-07 **không còn model coding Trung Quốc nào
   free** (Qwen3-Coder / GLM / Kimi đều đã bỏ tag `:free`); thay vào đó có
   `nvidia/nemotron-3-ultra-550b-a55b:free` (550B MoE, 1M context) và
   `poolside/laguna-s-2.1:free` (chuyên code). Luôn chạy `-ListFree` để lấy
   danh sách sống.
3. **DeepSeek trả theo token** — không thuê bao, nạp bao nhiêu tiêu bấy nhiêu.
   $0.435/$0.87 mỗi triệu token, nên thử cả tuần hết chừng $1-3. Đây là cách
   duy nhất sờ được model Trung Quốc hạng nặng mà không cam kết tháng nào.
4. **GLM Coding Plan $18/tháng** — chỉ mua khi ba bước trên đã chứng minh
   tầng rẻ gánh được phần lớn việc.

Key đọc từ `.env` ở gốc repo (`GLM_API_KEY`, `DEEPSEEK_API_KEY`) — cùng chỗ
với `GEMINI_API_KEY`, đã gitignore. Chưa có key thì script in đúng dòng cần
thêm rồi thoát, không set gì bậy.

Script ghi biến vào **User env** nên **phải mở terminal mới** sau khi đổi;
Claude Code chỉ nạp biến lúc khởi động. Muốn chỉ đổi cho shell hiện tại thì
dot-source: `. .\switch-model.ps1 glm -Session`.

### Vì sao có nó — bài toán chi phí (chốt 2026-08-07)

Chênh Pro → Max 5x là **$80/tháng**. Thuê GPU online để tự host model
Trung Quốc **không** bù nổi khoản đó: model coding thật sự mạnh
(Qwen3-Coder-480B, DeepSeek V4, GLM-5.2 bản đầy) cần ~8×H100 ≈ $18.7/h —
khoảng $1.650/tháng nếu chạy 4h/ngày. Thuê 1×RTX 4090 ($0.34/h ≈ $30/tháng)
thì rẻ thật, nhưng model nhét vừa 24 GB VRAM cũng chính là model chạy được
miễn phí ngay trên laptop này. Trả tiền để có tốc độ, không phải trí tuệ.

Đường rẻ nhất là **mua token của họ, đừng thuê máy của họ**: GLM Coding Plan
$18/tháng phẳng, hoặc DeepSeek API ~$0.44/$0.87 mỗi triệu token.

| Phương án | $/tháng | Đổi lại |
|---|---|---|
| Max 5x | 100 | 5× quota Claude, một model, không cấu hình gì |
| Pro + thuê GPU | 50–226 | model yếu hơn, tự làm sysadmin, trả tiền cả lúc GPU rảnh |
| **Pro + GLM Coding Lite** | **38** | Claude cho việc khó + model mạnh gần Claude cho việc nhiều |

### Ba tầng — ai làm gì

| Tầng | Chạy ở đâu | Việc |
|---|---|---|
| Local (miễn phí) | `ollama:qwen3-coder:30b-a3b-q4_K_M` | đọc/tóm tắt file, boilerplate, refactor cơ học, phân loại — đúng kiểu `Librarian/` |
| Rẻ ($18–38) | GLM / DeepSeek qua script này | viết feature, sửa bug thường, viết test — 80% số token |
| Claude Pro | Claude Code gốc | kiến trúc, bug khó, review, quyết định đánh đổi |

Không có target `local` trong script: Ollama chỉ nói OpenAI-compatible, không
nói Anthropic. Tầng local của repo đi qua `second_brain/local_llm.py` trong
chính pipeline (PhotoRecall, Journal, Librarian) — đúng nguyên tắc #2 của
PLAYBOOK, một cổng LLM duy nhất.

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

# Nghiên cứu: Nhận dạng lệnh điều khiển máy tính nói lẫn Việt–Anh

**Tên đề tài (gợi ý):** *Gợi ý ngữ cảnh từ trạng thái máy tính để nhận dạng lệnh nói lẫn Việt–Anh trong trợ lý máy tính
chạy cục bộ* — *Desktop-state contextual biasing for Vietnamese–English code-switched voice commands.*

Tài liệu này mô tả câu hỏi nghiên cứu, dữ liệu, chỉ số, thiết kế thí nghiệm và cách chạy bằng công cụ có sẵn trong NEXA.

---

## 1. Vấn đề

Người Việt ra lệnh cho máy tính bằng câu tiếng Việt chen tên riêng/thuật ngữ tiếng Anh: "mở **VS Code**", "tạo
**folder** dự án", "đóng tab **ChatGPT**". Model nhận dạng đa ngôn ngữ (Whisper) chạy ở chế độ `language="vi"` thường
ghi các từ này theo **phiên âm** ("mở vi ét cốt", "phôn đơ", "chát gi pi ti") hoặc nghe nhầm hẳn ("VS Của"). Câu nghe
sai tên riêng chỉ sai một hai từ, nhưng **lệnh thì hỏng hoàn toàn**. Vì vậy WER thấp chưa có nghĩa là lệnh chạy đúng.

NEXA hiện có ba lớp xử lý độc lập, mỗi lớp là một biến thí nghiệm:

| Lớp | Nằm ở | Biến |
|---|---|---|
| Gợi ý tĩnh: câu mẫu (`initial_prompt`) + danh sách tên (`hotwords`) | `nexa/audio/stt.py` | `stt.bias_mode: static` |
| **Gợi ý ngữ cảnh**: tên ứng dụng/dịch vụ đang mở trên máy, đặt lên đầu `hotwords` | `nexa/audio/context_bias.py` | `stt.bias_mode: context` |
| Hậu xử lý: bảng phiên âm → từ gốc, sửa tên ứng dụng nghe nhầm | `nexa/ai/english_terms.py`, `app_aliases.py`, `intent_router.apply_stt_fixes` | raw / norm |

## 2. Câu hỏi nghiên cứu và giả thuyết

- **RQ1 — Gợi ý tĩnh.** Câu mẫu + danh sách tên riêng làm giảm lỗi tên riêng và tăng tỷ lệ lệnh đúng bao nhiêu so với
  không gợi ý? *H1: có, giảm rõ rệt, không làm hại câu tiếng Việt thuần.*
- **RQ2 — Gợi ý ngữ cảnh.** Thêm tên lấy từ trạng thái máy (cửa sổ đang mở) có cải thiện thêm không, và cải thiện ở
  đâu? *H2: có với tên **ngoài** danh sách tĩnh (tên hiếm, ứng dụng anh tự cài) khi tên đó đang mở (lệnh
  đóng/chuyển/tìm trong); gần như không đổi với tên đã có sẵn trong danh sách tĩnh.* Danh sách tĩnh bị giới hạn
  ~30 tên (ngân sách token của Whisper), nên không thể chỉ "thêm hết vào danh sách tĩnh".
- **RQ3 — Gợi ý và hậu xử lý.** Hai cách bổ trợ hay thay thế nhau? Hậu xử lý cứu được bao nhiêu lệnh mà gợi ý bỏ sót,
  và ngược lại?
- **RQ4 — Chi phí.** Đánh đổi độ chính xác và độ trễ theo model/thiết bị (small CPU, small GPU, large-v3-turbo GPU), và
  độ bền khi có nhiễu (SNR).
- **RQ5 (dài hạn) — Có cần huấn luyện không?** Fine-tune nhẹ (LoRA) Whisper trên dữ liệu thu được so với gợi ý
  không cần huấn luyện; kết hợp cả hai.

## 3. Đóng góp dự kiến

1. **Bộ dữ liệu** lệnh máy tính nói lẫn Việt–Anh (giọng người thật, nhiều người nói, nhiều loại mic), kèm ngữ cảnh máy
   lúc nói, công bố được sau khi ẩn danh.
2. **Phương pháp gợi ý ngữ cảnh từ trạng thái máy**, không cần huấn luyện lại, chạy dưới 25 ms (đo trên máy phát triển:
   đọc cửa sổ lần đầu 23 ms, lần sau 1 ms; chạy ở luồng nền nên không cộng vào độ trễ nhận dạng).
3. **Chỉ số lệnh đúng (command success)** bên cạnh WER, cùng quy trình đánh giá tái lập được (kiểm định ghép cặp).
4. Hệ thống mã nguồn đầy đủ (NEXA) để người khác chạy lại.

## 4. Dữ liệu

### 4.1 Bộ tổng hợp: chỉ để phát triển
`scripts/asr_synth.py` đọc câu mẫu trong `nexa/research/templates.py` bằng giọng TTS tiếng Việt (WinRT "Microsoft An"
offline; thêm `--edge` để có HoaiMy/NamMinh):
- mỗi câu có hai kiểu đọc: **orth** (đưa chính tả tiếng Anh cho TTS) và **viet** (đưa phiên âm kiểu Việt);
- câu chuẩn luôn viết đúng chính tả;
- ngữ cảnh được gán **thực tế**: "mở X" thì X chưa mở (ngữ cảnh không chứa X); "đóng X", "đóng tab X", "tìm trong X"
  thì X đang mở. Như vậy thí nghiệm không thổi phồng tác dụng của gợi ý ngữ cảnh;
- nhóm **longtail** (Photoshop, CapCut, Telegram, Notion…) gồm các tên *không* có trong danh sách tĩnh, để kiểm tra H2.

Giọng TTS sạch, đều và chỉ có 1–3 "người nói", nên **không dùng kết quả trên bộ tổng hợp làm kết luận**.

### 4.2 Bộ giọng thật: dùng để kết luận
Thu bằng chính NEXA khi dùng hằng ngày hoặc theo kịch bản:
1. Bật trong `config/settings.yaml`:
   ```yaml
   research:
     record_corpus: true
     speaker_id: S01        # mã ẩn danh của người nói, KHÔNG dùng tên thật
   ```
2. Dùng NEXA bình thường. Mỗi câu được lưu thành WAV 16 kHz + một dòng JSONL (chữ nghe được, loại lệnh, độ tin cậy,
   chế độ gợi ý, tên ngữ cảnh đã lọc) trong `%LOCALAPPDATA%\NEXA\asr_corpus`.
3. Gán nhãn: `scripts\asr_corpus.py export labels.csv`, mở bằng Excel, nghe file, sửa cột `reference`, đặt
   `checked=1` (`skip=1` để loại). Sau đó `scripts\asr_corpus.py import labels.csv` → `manifest.jsonl`.

Thiết kế đề xuất cho bộ kiểm tra:
- **≥ 20 người nói** (cân bằng giới và ba miền Bắc/Trung/Nam), mỗi người khoảng 80–120 lệnh: nửa đọc theo kịch bản
  (danh sách trong `templates.py`), nửa nói tự do theo tình huống ("anh muốn đóng ứng dụng chỉnh ảnh đang mở").
- **≥ 3 điều kiện mic**: tai nghe Bluetooth, mic laptop trong phòng yên tĩnh, mic laptop có nhạc hoặc quạt.
- Chia train/dev/test **theo người nói**, không để cùng một người xuất hiện ở hai tập.
- Ghi ngữ cảnh thật (NEXA tự ghi `context`), không tự dựng ngữ cảnh.

## 5. Chỉ số (`nexa/research/asr_metrics.py`)

| Chỉ số | Định nghĩa |
|---|---|
| WER / CER | Lỗi từ/ký tự sau chuẩn hóa nhẹ (chữ thường, NFC, bỏ dấu câu); **giữ dấu thanh** |
| Lỗi tên riêng | 1 − (số tên riêng của câu chuẩn xuất hiện đúng trong câu nhận dạng) / (tổng số tên riêng). "VS Code" = "Visual Studio Code"; "VS Của" là sai |
| **Lệnh đúng** | IntentRouter cho **cùng hành động** (loại + công cụ + tham số) với câu nhận dạng và với câu chuẩn. Câu chuẩn thuộc Gemini không chấm được cục bộ nên bị loại khỏi mẫu số |
| Độ trễ | Thời gian Whisper xử lý mỗi câu: trung bình và p90 |

Kiểm định: **bootstrap ghép cặp** theo câu cho ΔWER (khoảng tin cậy 95%, p hai phía) và **McNemar chính xác** cho tỷ
lệ lệnh đúng. Khi so sánh nhiều cặp, báo cáo kèm hiệu chỉnh Holm.

## 6. Chạy thí nghiệm

```bat
.venv\Scripts\python scripts\asr_synth.py
.venv\Scripts\python scripts\asr_benchmark.py --manifest data\asr_synth\manifest.jsonl ^
    --models large-v3-turbo,small --bias none,static,context --snr clean,15
```
Kết quả trong `results\asr\<thời điểm>\`:
- `report.md`: bảng tổng hợp, kiểm định ghép cặp, kết quả theo nhóm câu;
- `summary.json`: số liệu cùng phiên bản faster-whisper và SHA-1 của manifest, để tái lập;
- `utterances.csv`: từng câu, dùng để phân tích lỗi.

Tổng hợp giọng (WinRT) và chạy Whisper phải ở **hai tiến trình riêng**: chạy chung một tiến trình từng làm Python crash
trên máy phát triển.

## 7. Kết quả sơ bộ (bộ tổng hợp, 2026-09-24)

124 câu tổng hợp, giọng WinRT "An", GPU RTX 4050, beam 3, hậu xử lý raw. Bảng đầy đủ nằm ở
`results/asr/synth-v3/report.md`. **Chỉ là số liệu phát triển, không dùng làm kết luận.**

| Model | Gợi ý | WER | Lỗi tên riêng | Lệnh đúng | Trễ TB |
|---|---|---|---|---|---|
| large-v3-turbo | none | 53.5% | 68.7% | 28.6% | 0.29 s |
| large-v3-turbo | static | 41.8% | 56.0% | 37.8% | 0.30 s |
| large-v3-turbo | context | 40.4% | 54.5% | 37.8% | 0.29 s |
| small | none | 87.0% | 94.8% | 6.7% | 0.12 s |
| small | static | 68.6% | 73.1% | 23.5% | 0.13 s |
| small | context | 64.6% | 67.2% | 22.7% | 0.12 s |

- **H1 được ủng hộ mạnh.** Gợi ý tĩnh giảm WER 11,7 điểm (turbo) và 18,4 điểm (small), p < 0,001. Tỷ lệ lệnh đúng tăng:
  turbo có 11 câu chỉ đúng khi có gợi ý và 0 câu ngược lại; small là 21 và 1 (McNemar p ≤ 0,001). Khi có nhiễu 15 dB,
  tác dụng còn lớn hơn.
- **H2 mới có tín hiệu yếu.** So với gợi ý tĩnh, gợi ý ngữ cảnh giảm thêm 1,3 điểm WER với turbo (p = 0,23, không có ý
  nghĩa) và 4,0 điểm với small (p = 0,005), nhưng chưa làm tăng lệnh đúng. Tác dụng tập trung ở nhóm tên hiếm đọc kiểu
  phiên âm: lỗi tên riêng giảm từ 87,5% xuống 62,5% (8 câu, quá ít để kết luận). Với tên đã có trong danh sách tĩnh,
  ngữ cảnh gần như không đổi gì, đúng như dự đoán.
- **Phát hiện phụ:**
  - Bộ đo bắt được một câu Whisper tự bịa ("Các bạn hãy đăng kí cho kênh…") đã lọt qua bộ lọc ảo giác của NEXA; đã sửa
    trong `stt.py` và có test.
  - Whisper hay nghe "đóng" thành "đồng", làm hỏng nhiều lệnh đóng. Đây là ứng viên cho bảng hậu xử lý, nhưng phải cẩn
    thận vì "đồng" là từ tiếng Việt phổ biến.
- **Việc tiếp theo:** thu giọng thật với nhiều tên hiếm (ứng dụng mỗi người tự cài) để có đủ lực thống kê cho H2; mở
  rộng ngữ cảnh cho lệnh "mở X" bằng danh sách Start Menu.

## 8. Đạo đức và quyền riêng tư

- Thu âm người khác cần **phiếu đồng ý** ghi rõ mục đích, nơi lưu, thời hạn giữ, và quyền rút lại dữ liệu. Làm dưới
  trường/viện thì cần hội đồng đạo đức duyệt.
- `research.record_corpus` **tắt mặc định**. Dữ liệu nằm ngoài thư mục dự án nên không lọt vào git/ZIP. Không ghi
  tiêu đề cửa sổ, chỉ ghi tên ứng dụng đã lọc qua từ vựng biết trước.
- Trước khi công bố: bỏ câu có thông tin cá nhân (tên người, số điện thoại, nội dung tin nhắn), dùng mã người nói ẩn
  danh, và cân nhắc chỉ công bố đặc trưng âm học nếu người tham gia không đồng ý công bố giọng.
- Log hằng ngày của NEXA (`logs/nexa.log`) có câu nói thật: **không** đưa vào bộ dữ liệu.

## 9. Hạn chế cần nêu trong bài

- Ngữ cảnh chỉ giúp khi tên cần nói **đang mở**; lệnh "mở X" (X chưa chạy) cần nguồn khác, ví dụ Start Menu hoặc
  lịch sử dùng ứng dụng. Đây là hướng mở rộng.
- Chỉ số "lệnh đúng" phụ thuộc IntentRouter của NEXA. Cần báo cáo thêm WER và lỗi tên riêng để so với hệ thống khác.
- Nhiễu tổng hợp (nhiễu trắng) khác nhiễu thật: bộ giọng thật mới là căn cứ.
- Giọng TTS tiếng Việt đọc tên tiếng Anh hiếm theo chính tả rất sai ("Figma" → "vị ở mạng"): câu kiểu **orth** của
  nhóm longtail gần như không nhận ra được với mọi cấu hình, nên đo H2 trên bộ tổng hợp phải xem kiểu **viet**.
- Hậu xử lý đổi "folder" → "thư mục", "file" → "tệp" (dạng chuẩn cho IntentRouter): WER "norm" được chấm với câu chuẩn
  đã qua cùng phép đổi. Không so trực tiếp WER raw với WER norm; so bằng tỷ lệ lệnh đúng.
- Mẫu hiện tại nhỏ (124 câu tổng hợp); nhiều khác biệt theo nhóm chưa đủ ý nghĩa thống kê.

## 10. Lộ trình và nơi công bố

| Giai đoạn | Việc | Đầu ra |
|---|---|---|
| 1 (1 tháng) | Chạy bộ tổng hợp, sửa công cụ, viết phiếu đồng ý | Quy trình ổn định |
| 2 (3–4 tháng) | Thu và gán nhãn ≥ 20 người nói | Bộ dữ liệu v1; bài hội thảo trong nước (VLSP, RIVF, SoICT, KSE) |
| 3 (3–4 tháng) | RQ2–RQ4 trên giọng thật; mở rộng ngữ cảnh (Start Menu, lịch sử dùng) | Bài quốc tế (Interspeech, ICASSP, workshop ACL/EMNLP về code-switching) |
| 4 (3–6 tháng) | RQ5: fine-tune LoRA, so với gợi ý; công bố bộ dữ liệu | Bài tạp chí hoặc Datasets track |

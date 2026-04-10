# Math Tutoring Research Pipeline

Hệ thống này là một pipeline gia sư toán theo hướng nghiên cứu, được thiết kế để:

- chuẩn hóa đề bài thành biểu diễn có cấu trúc
- xây lời giải chuẩn có thể thực thi được
- chuẩn hóa bài làm học sinh thành biểu diễn có thể đối chiếu
- xây bằng chứng ở mức tiến trình
- chẩn đoán lỗi có căn cứ
- lập kế hoạch sư phạm
- sinh gợi ý theo flow `generate -> repair -> verify -> fallback`

Thay vì phụ thuộc hoàn toàn vào một lời giải tự do của mô hình, hệ thống kết hợp:

- LLM cho các bước cần hiểu ngữ nghĩa hoặc diễn đạt tự nhiên
- logic tất định cho các bước cần kiểm chứng, thực thi và đánh giá

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Tính năng hiện có](#tính-năng-hiện-có)
- [Cài đặt](#cài-đặt)
- [Cấu hình môi trường](#cấu-hình-môi-trường)
- [Cách chạy](#cách-chạy)
- [Các file debug](#các-file-debug)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Kiểm thử](#kiểm-thử)
- [Trạng thái hiện tại](#trạng-thái-hiện-tại)
- [Giới hạn hiện tại](#giới-hạn-hiện-tại)
- [Định hướng tiếp theo](#định-hướng-tiếp-theo)

---

## Tổng quan

Pipeline tổng thể hiện tại:

`Đề bài -> Chuẩn hóa đề bài -> Lời giải chuẩn thực thi được -> Chuẩn hóa bài làm học sinh -> Xây dựng bằng chứng -> Chẩn đoán -> Lập kế hoạch sư phạm -> Sinh/Sửa/Kiểm tra gợi ý`

Các ý tưởng cốt lõi của hệ thống:

- `Problem formalizer` sinh ra biểu diễn có cấu trúc và `problem graph`
- `Runtime` tạo `canonical reference` bằng cách biên dịch và thực thi kế hoạch giải
- `Student work formalizer` sinh `student graph` từ lời giải học sinh
- `Evidence builder` đối chiếu hai tiến trình thay vì chỉ so đáp án cuối
- `Diagnosis` dựa trên `hypothesis scoring`, không chỉ là một chuỗi if-else đơn giản
- `Hint` đi theo quy trình đầy đủ: sinh gợi ý, sửa gợi ý, kiểm tra, rồi mới dùng gợi ý dự phòng

Đây là một dự án theo hướng nghiên cứu vì:

- có bài toán nghiên cứu rõ ràng
- có artifact trung gian để benchmark từng mô-đun
- có thể làm ablation theo từng thành phần
- có thể mở rộng theo hướng verifier mạnh hơn, reranking, và RL/policy learning

---

## Kiến trúc hệ thống

### 1. Chuẩn hóa đề bài

Đề bài được biến thành object có cấu trúc gồm:

- các đại lượng
- thực thể
- mục tiêu câu hỏi
- quan hệ ứng viên
- `problem graph`

Module này hiện dùng kiến trúc:

- heuristic draft
- compact LLM skeleton
- local build
- validation
- retry/refine loop
- heuristic fallback

### 2. Lời giải chuẩn thực thi được

Từ `problem graph`, hệ thống:

- kiểm định đồ thị
- biên dịch thành kế hoạch thực thi
- chạy từng bước
- tạo `execution trace`
- tạo `canonical reference`

Phần này là deterministic và đóng vai trò nguồn chuẩn của toàn hệ thống.

### 3. Chuẩn hóa bài làm học sinh

Bài làm học sinh được biến thành:

- đáp án cuối đã chuẩn hóa
- danh sách bước
- mục tiêu học sinh đang nhắm tới
- `student graph`

Module này hiện cũng dùng pattern:

- heuristic draft
- compact LLM skeleton
- local build
- validation
- retry/refine loop
- fallback

### 4. Xây dựng bằng chứng

Hệ thống đối chiếu:

- `problem graph`
- `canonical plan / execution trace`
- `student graph`

và sinh ra:

- `evidence items`
- `alignment map`
- `first divergence step id`
- các cơ chế lỗi có khả năng cao

Phần này đã xử lý tốt hơn trường hợp:

- học sinh đúng nhưng khác thứ tự bước
- học sinh gộp hoặc tách bước khác lời giải chuẩn

### 5. Chẩn đoán

Chẩn đoán hiện dựa trên:

- structured evidence
- alignment
- divergence
- graph-aware signals

Đường chính là:

- deterministic hypothesis scoring

LLM nếu có chỉ đóng vai:

- critic / refiner

### 6. Lập kế hoạch sư phạm

Từ chẩn đoán, hệ thống chọn:

- mức gợi ý
- hành động sư phạm
- bước mục tiêu
- ngân sách tiết lộ thông tin
- các điểm cần tập trung
- các nội dung không được lộ

### 7. Gợi ý

Khối hint hiện hoạt động theo flow:

1. `generate`
2. `repair`
3. `verify`
4. `fallback`

Đây là trạng thái mới, không còn kiểu:

`generate -> fail -> fallback`

---

## Tính năng hiện có

- Chuẩn hóa đề bài bằng graph
- Xây lời giải chuẩn có thể thực thi
- Chuẩn hóa bài làm học sinh thành graph
- Đối chiếu tiến trình học sinh với lời giải chuẩn
- Chẩn đoán dựa trên bằng chứng có cấu trúc
- Kế hoạch gợi ý mang tính sư phạm
- Gợi ý có sửa, kiểm tra và dự phòng
- Pipeline end-to-end hoàn chỉnh
- Bộ debug riêng cho từng mô-đun chính
- Bộ test bao phủ các tầng chính của hệ thống

---

## Cài đặt

### Yêu cầu

- Python 3.11+ khuyến nghị
- Windows PowerShell hoặc môi trường Python tương đương

### Cài dependencies

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nếu bạn chưa có `venv`, có thể tạo mới:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

---

## Cấu hình môi trường

Tạo hoặc cập nhật file `.env` với các biến cần thiết cho OpenRouter:

```env
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL_ID=openai/gpt-5-nano
OPENROUTER_APP_NAME=problem-formalizer
```

Lưu ý:

- hệ thống vẫn chạy được ở nhiều phần mà không cần LLM
- nếu bật LLM, các module có thể gọi model gồm:
  - chuẩn hóa đề bài
  - chuẩn hóa bài làm học sinh
  - chẩn đoán
  - sinh gợi ý
  - sửa gợi ý

---

## Cách chạy

### Chạy pipeline end-to-end

```powershell
.\venv\Scripts\python.exe main.py
```

File `main.py` hiện:

- chạy toàn bộ pipeline
- in artifact của từng tầng
- ghi lại các lần gọi LLM đã xảy ra

### Chạy riêng một bài toán / một câu trả lời

Sửa trực tiếp các biến đầu vào trong `main.py` hoặc trong các file debug tương ứng rồi chạy lại.

---

## Các file debug

Repo hiện có các file debug chính sau:

### `debug_formalizer.py`

Dùng để xem riêng phần chuẩn hóa đề bài.

Xuất ra:

- `debug_formalizer_output.txt`
- `debug_formalizer_llm_raw.json`

Hiển thị:

- input
- heuristic problem
- final problem
- problem graph
- graph validation
- executable plan
- execution trace
- toàn bộ prompt gửi model
- phản hồi model

### `debug_student_work.py`

Dùng để xem riêng phần chuẩn hóa bài làm học sinh.

Xuất ra:

- `debug_student_work_output.txt`
- `debug_student_work_llm_raw.json`

Hiển thị:

- input
- problem
- reference nếu build được
- lỗi build reference nếu không build được
- heuristic student work
- final student work
- student graph
- toàn bộ prompt gửi model
- phản hồi model

### `debug_diagnosis.py`

Dùng để xem riêng phần chẩn đoán.

Xuất ra:

- `debug_diagnosis_output.txt`
- `debug_diagnosis_llm_raw.json`

Hiển thị:

- student work
- evidence
- deterministic diagnosis
- final diagnosis
- prompt gửi model
- phản hồi model

### `debug_hint.py`

Dùng để xem riêng phần hint.

Xuất ra:

- `debug_hint_output.txt`
- `debug_hint_llm_raw.json`

Hiển thị:

- diagnosis
- hint plan
- deterministic hint
- final hint
- prompt của `hint_generator`
- prompt của `hint_repair` nếu có
- phản hồi model

### `debug_llm_model.py`

Dùng để kiểm tra model OpenRouter đang được cấu hình và phản hồi thô từ API.

---

## Cấu trúc thư mục

```text
src/
  models/        # schema và artifact trung gian
  formalizer/    # chuẩn hóa đề bài và bài làm học sinh
  runtime/       # compile, execute, canonical reference
  evidence/      # alignment và bằng chứng process-level
  diagnosis/     # hypothesis scoring và diagnosis refinement
  pedagogy/      # lập kế hoạch sư phạm
  hint/          # generate, repair, verify, fallback
  pipeline/      # chạy end-to-end
  llm/           # client và tích hợp LLM

tests/
  models/
  formalizer/
  runtime/
  evidence/
  diagnosis/
  pedagogy/
  hint/
  pipeline/
  llm/
```

Tài liệu hỗ trợ:

- `PIPELINE_MECHANISM.md`: mô tả chi tiết cơ chế hoạt động từ đầu đến cuối

---

## Kiểm thử

Chạy toàn bộ test:

```powershell
.\venv\Scripts\python.exe -m pytest tests -q
```

Ở thời điểm cập nhật README này, trạng thái gần nhất là:

- `58 passed`
- `1 warning`

Warning còn lại là warning của `.pytest_cache` trên Windows, không phải lỗi logic của hệ thống.

---

## Trạng thái hiện tại

Hiện tại dự án đã có:

- formalizer cho đề bài theo hướng graph + compact LLM skeleton
- runtime tạo canonical reference thực thi được
- formalizer cho bài làm học sinh theo hướng graph
- evidence builder process-aware và graph-aware hơn
- diagnosis dùng hypothesis scoring
- pedagogy planner deterministic
- hint theo flow generate -> repair -> verify -> fallback
- debug script riêng cho từng tầng

Nói ngắn gọn, dự án đã vượt xa mức “chỉ có lõi”, và hiện là một pipeline hoàn chỉnh có thể chạy end-to-end.

---

## Giới hạn hiện tại

Dù đã khá đầy đủ, hệ thống vẫn còn các giới hạn sau:

- formalizer chưa bao phủ mọi dạng bài toán lời văn
- một số dạng graph reasoning khó vẫn chưa được formalize tốt
- diagnosis chưa phải mức research-grade hoàn chỉnh ở mọi trường hợp mơ hồ
- evidence graph matching đã mạnh hơn trước nhưng vẫn còn có thể nâng sâu
- quality của LLM path vẫn phụ thuộc model và prompt

Ví dụ:

- nếu đề bài quá khác các template quan hệ hiện có, canonical reference có thể không build được
- khi đó debug student vẫn chạy được, nhưng full workflow sẽ không hoàn chỉnh

---

## Định hướng tiếp theo

Các hướng tiếp tục phù hợp với trạng thái hiện tại của dự án:

### 1. Nâng formalizer

- hỗ trợ thêm nhiều loại bài toán
- semantic verifier mạnh hơn
- nhiều candidate graph hơn và reranking tốt hơn

### 2. Nâng evidence và diagnosis

- global graph alignment mạnh hơn nữa
- ambiguity modeling tốt hơn
- subtype phong phú hơn

### 3. Nâng hint

- evaluation kỹ hơn cho helpfulness
- tối ưu repair policy
- policy learning cho teacher move / disclosure control

### 4. Hướng RL

Nếu còn thời gian, đây là một hướng rất phù hợp để mở rộng:

- học policy chọn teacher move
- học policy chọn mức gợi ý
- học policy sửa hint
- tối ưu theo reward từ hành vi sửa lỗi của học sinh

---

## Ghi chú

README này phản ánh trạng thái hiện tại của dự án theo kiến trúc mới.  
Nếu bạn cần tài liệu giải thích cơ chế chi tiết hơn từng mô-đun, xem thêm:

- `PIPELINE_MECHANISM.md`

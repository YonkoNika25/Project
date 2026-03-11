Dưới đây là **tài liệu dự án để triển khai code** cho hướng hiện tại. Mình viết theo kiểu **technical design / project spec**, không phải báo cáo học thuật, để bạn dùng làm “bản đồ thi công” trước khi code.

---

# Tài liệu dự án

## Neuro-Symbolic Solver-Grounded Tutor for Math Word Problems

## 1. Mục tiêu tài liệu

Tài liệu này trả lời 7 câu hỏi thực dụng trước khi code:

1. Mình đang xây cái gì.
2. Nó giải quyết bài toán nào.
3. Vì sao chọn cách làm này.
4. Hệ thống gồm những module nào.
5. Input/output, dữ liệu, API nội bộ ra sao.
6. Giai đoạn nào làm trước, giai đoạn nào để sau.
7. Tiêu chí nào để biết bản đầu đã chạy đúng.

---

## 2. Tóm tắt dự án

Dự án xây một **solver-grounded tutor** cho bài toán lời văn nhiều bước, trước mắt dùng **GSM8K-style problems** làm testbed. GSM8K có khoảng **8.5K bài**, chia thành **7.5K train** và **1K test**, và được tạo ra để chẩn đoán thất bại của mô hình trong reasoning nhiều bước. ([GitHub][1])

Hệ thống nhận:

* `problem`: đề toán lời văn
* `student_answer`: đáp án cuối của người học hoặc của một model baseline

Hệ thống trả:

* `diagnosis`: câu trả lời sai/đúng theo kiểu gì
* `hint`: gợi ý sửa ngắn, đúng hướng, không lộ full solution

Điểm cốt lõi: hệ **không chỉ dùng LLM prompting thuần**, mà kết hợp:

* **LLM/model** để hiểu bài, giải tham chiếu, diễn đạt diagnosis/hint
* **symbolic/verifier layer** để kiểm chứng ràng buộc, đáp án, và tạo tín hiệu đáng tin hơn
* về sau có thể thêm **repair search / preference learning / RL-light**, nhưng không phải phần bắt buộc của bản đầu

Các công trình gần đây cho thấy đây là hướng hợp lý:
Qwen2.5-Math hỗ trợ cả Chain-of-Thought và **Tool-Integrated Reasoning** trên các benchmark như GSM8K, MATH, AMC, AIME. Trong khi đó, MathTutorBench cho thấy **giải đúng bài không tự động đồng nghĩa với tutor tốt**, và FoVer cho thấy **formal/symbolic verification** có thể tạo tín hiệu step-level verification chính xác hơn cho reasoning systems. ([arXiv][2])

---

## 3. Bài toán mà dự án giải quyết

### 3.1 Bài toán thực tế

Hầu hết hệ AI giải toán hiện nay giỏi ở việc:

* trả đáp án
* hoặc viết lời giải

Nhưng yếu ở việc:

* hiểu câu trả lời sai của học sinh sai kiểu gì
* chỉ ra đúng chỗ sai
* đưa gợi ý vừa đủ để học sinh tự sửa

MathTutorBench nhấn mạnh rằng **subject expertise và pedagogical ability là hai trục khác nhau**; solving ability không tự chuyển thành tutoring ability. ([arXiv][3])

### 3.2 Bài toán kỹ thuật

Cho:

* bài toán nhiều bước
* câu trả lời cuối của học sinh

Cần sinh:

* chẩn đoán lỗi
* gợi ý sửa

mà không hoàn toàn dựa vào “LLM tự đoán”, mà dựa trên:

* lời giải tham chiếu
* biểu diễn có cấu trúc
* kiểm chứng ký hiệu hoặc ràng buộc

---

## 4. Mục tiêu và ngoài phạm vi

### 4.1 Mục tiêu bản đầu

Bản đầu phải làm được 5 việc:

1. Đọc được một bài toán GSM8K-style.
2. Tạo được một lời giải tham chiếu đủ tin cậy.
3. Kiểm tra được `student_answer` đúng hay sai.
4. Gán được một `diagnosis` thuộc taxonomy lỗi cơ bản.
5. Sinh được một `hint` ngắn, đúng hướng, không spoil.

### 4.2 Ngoài phạm vi của bản đầu

Bản đầu **chưa cần**:

* nhận full lời giải từng bước của học sinh
* proof assistant như Lean/Isabelle
* RL/PPO/GRPO đầy đủ
* benchmark đa miền ngay từ đầu
* giao diện web đẹp
* tutor hội thoại nhiều lượt

---

## 5. Tư tưởng thiết kế

### 5.1 Tại sao không làm pure LLM prompting

Vì pure prompting có 3 nhược điểm lớn:

* dễ hallucinate diagnosis
* khó kiểm tra hint có thật sự bám vào lỗi hay không
* khó tạo tín hiệu huấn luyện/đánh giá đáng tin

### 5.2 Tại sao phải có solver-grounding

Solver giúp tạo:

* đáp án tham chiếu
* reasoning evidence
* mốc để so student answer với một lời giải đúng hơn

### 5.3 Tại sao phải có symbolic/verifier layer

Verifier giúp:

* kiểm tra consistency
* xác định loại sai ở tầng toán/ràng buộc
* cung cấp tín hiệu đáng tin hơn text-only judge

FoVer cho thấy formal verification tools có thể tạo nhãn step-level chính xác cho verifier training trong symbolic tasks. Với dự án này, mình áp dụng tinh thần đó ở mức thực dụng hơn: ưu tiên **SymPy/Python/constraint-style verification** trước khi nghĩ đến formal proof assistants. ([arXiv][4])

### 5.4 Tại sao không lấy RL làm lõi ngay

Vì bản đầu cần chứng minh được:

* state nào hữu ích
* verifier nào đáng tin
* diagnosis taxonomy nào dùng được
* hint policy nào không spoil

RL chỉ đáng thêm sau khi các phần trên đã rõ. Frontier math reasoning hiện nay là pipeline tổng hợp nhiều thành phần, không chỉ RL. Điều này thể hiện rõ trong technical report của Qwen2.5-Math. ([arXiv][2])

---

## 6. Kiến trúc tổng thể

Hệ thống gồm 6 module chính:

1. **Dataset & Example Builder**
2. **Reference Solver**
3. **Answer Checker**
4. **Structured Translator / Symbolic State Builder**
5. **Diagnosis Engine**
6. **Hint Generator + Hint Verifier**

Pipeline chạy như sau:

`problem + student_answer`
→ parse/chuẩn hóa
→ solver tạo reference
→ checker so sánh answer
→ symbolic state builder tạo state có cấu trúc
→ diagnosis engine suy ra lỗi
→ hint generator sinh gợi ý
→ hint verifier kiểm hint đúng hướng và không spoil

---

## 7. Module chi tiết

## 7.1 Dataset & Example Builder

### Nhiệm vụ

* đọc dữ liệu GSM8K
* chuẩn hóa format nội bộ
* tạo các sample dùng cho eval và phát triển
* về sau tạo synthetic `wrong_answer` nếu cần

### Input nguồn

* GSM8K train/test chính thức hoặc bản dùng qua huggingface/local mirror
  GSM8K gốc có 8.5K bài do người viết, đa dạng ngôn ngữ và nhiều bước. ([GitHub][1])

### Schema nội bộ đề xuất

```json
{
  "id": "gsm8k_000123",
  "problem": "Jan has 3 apples ...",
  "gold_answer_text": "#### 18",
  "gold_answer_value": 18,
  "metadata": {
    "source": "gsm8k",
    "split": "train"
  }
}
```

### Việc cần làm

* parser lấy `gold_answer_value` từ format đáp án gốc
* utility tạo `student_answer` giả:

  * đúng
  * sai số học nhẹ
  * sai do nhầm quantity
  * sai ngẫu nhiên

### Lý do cần module này

Nếu không chuẩn hóa dữ liệu từ đầu, toàn bộ pipeline sau sẽ rất khó debug, nhất là phần diagnosis taxonomy và eval.

---

## 7.2 Reference Solver

### Nhiệm vụ

Sinh lời giải tham chiếu đủ tốt để làm “cột mốc” cho tutor.

### Backbone đề xuất

* **Qwen2.5-Math** làm solver chính
* có thể chạy nhiều chế độ:

  * direct solve
  * CoT
  * tool-assisted solve

Qwen2.5-Math được thiết kế riêng cho reasoning toán và hỗ trợ Tool-Integrated Reasoning. ([arXiv][2])

### Output mong muốn

```json
{
  "final_answer": 18,
  "solution_text": "...",
  "structured_trace": {
    "quantities": [...],
    "relations": [...],
    "target": "...",
    "equations_or_steps": [...]
  },
  "confidence": 0.84
}
```

### Lý do cần structured_trace

Bản đầu có thể chưa cần trace rất hình thức, nhưng nếu không giữ ít nhất một trace cấu trúc nhẹ, diagnosis engine sẽ quá phụ thuộc vào text.

### Thiết kế runtime đề xuất

* gọi solver 1 lần ở chế độ chuẩn
* nếu confidence thấp hoặc parse fail, gọi thêm 2–3 samples và chọn best-of-N theo rule đơn giản
* chưa cần reranker học máy ở bản đầu

### Lý do không dùng symbolic solver thuần ngay

Với GSM8K-style word problems, “khó” nằm ở hiểu đề và thiết lập quan hệ, nên vẫn cần model để đi từ ngôn ngữ tự nhiên sang toán.

---

## 7.3 Answer Checker

### Nhiệm vụ

So sánh `student_answer` với `reference_answer`.

### Input

```json
{
  "problem": "...",
  "student_answer": "18",
  "reference_answer": 18
}
```

### Output

```json
{
  "is_correct": true,
  "normalized_student_value": 18,
  "comparison_type": "exact_match"
}
```

### Các kiểu kết quả nên hỗ trợ

* exact correct
* numeric incorrect
* parse failure
* correct value but malformed text
* ambiguous answer

### Lý do cần module riêng

Diagnosis nên dựa trên một primitive sạch là “answer-level status”, thay vì nhồi hết logic vào LLM.

---

## 7.4 Structured Translator / Symbolic State Builder

### Nhiệm vụ

Biến problem và student_answer thành một **state có cấu trúc** để:

* kiểm tra bằng symbolic/rule-based logic
* sinh diagnosis có căn cứ hơn

### Đây là phần AI rõ nhất

Model sẽ làm:

* parse quantities
* parse target
* suy ra quan hệ sơ bộ
* tạo structured state

### Dạng state đề xuất cho bản đầu

Không cần quá hàn lâm. Chỉ cần đủ để chẩn đoán.

```json
{
  "entities": ["Jan", "apples"],
  "quantities": [
    {"name": "initial_apples", "value": 3},
    {"name": "bought_more", "value": 5}
  ],
  "operations_hypothesis": [
    {"op": "add", "args": ["initial_apples", "bought_more"]}
  ],
  "target": "final_apples",
  "student_answer_value": 6
}
```

### Vì sao không dùng Lean/Isabelle ở đây

Với word problems, chi phí formalization quá cao so với lợi ích bản đầu. SymPy/Python/constraint representation thực dụng hơn nhiều.

### Cảnh báo thiết kế

**State builder không phải ground truth.**
Nó có thể dịch sai. Vì vậy toàn hệ phải lưu:

* state
* confidence
* nguồn của từng field nếu có thể

Để khi debug, bạn biết lỗi nằm ở parse hay diagnosis.

---

## 7.5 Symbolic / Constraint Verifier

### Nhiệm vụ

Kiểm tra:

* state có self-consistent không
* quan hệ suy đoán có hợp lý không
* student answer có phù hợp với một phép tính/quỹ đạo nào không
* chỗ nào có dấu hiệu sai loại “semantic bug”

### Dạng kiểm tra khả thi cho bản đầu

* numeric consistency
* operation consistency
* target consistency
* quantity coverage
* simple constraint satisfaction

### Ví dụ

Nếu problem nói “tổng”, nhưng translator hoặc student reasoning đang ám chỉ “hiệu”, verifier có thể gắn cờ:

* suspected relation mismatch

### Output

```json
{
  "flags": [
    "target_mismatch",
    "quantity_relation_inconsistent"
  ],
  "evidence": [
    "Expected additive composition from quantities A and B",
    "Student answer aligns with subtractive interpretation"
  ]
}
```

### Lý do cần verifier này

Đây là cây cầu nối giữa:

* solving
* diagnosis

Nếu không có nó, diagnosis sẽ chỉ là “LLM đoán đại”.

---

## 7.6 Diagnosis Engine

### Nhiệm vụ

Từ:

* answer checker output
* symbolic verifier flags
* solver trace/reference

suy ra `diagnosis` có cấu trúc.

### Taxonomy lỗi bản đầu đề xuất

Bản đầu chỉ nên dùng taxonomy nhỏ, rõ:

1. `correct_answer`
2. `arithmetic_error`
3. `quantity_relation_error`
4. `target_misunderstanding`
5. `unsupported_correct_answer`
6. `unparseable_answer`
7. `unknown_error`

### Output chuẩn

```json
{
  "label": "quantity_relation_error",
  "localization": "combining_quantities",
  "explanation_internal": "Student likely used subtraction instead of addition when combining the two known quantities."
}
```

### Vì sao diagnosis không nên chỉ là một câu text

Vì về sau bạn sẽ cần:

* đo diagnosis accuracy
* phân tích lỗi theo class
* sinh hint conditionally theo class

Không có nhãn cấu trúc thì rất khó mở rộng.

---

## 7.7 Hint Generator

### Nhiệm vụ

Sinh gợi ý ngắn, đúng hướng, không lộ lời giải.

### Chính sách hint bản đầu

Có 3 mức:

1. **Conceptual hint** – nhắc ý cần nghĩ
2. **Relational hint** – nhắc quan hệ giữa quantities
3. **Next-step hint** – nhắc bước nên làm tiếp

### Ví dụ

Nếu diagnosis là `target_misunderstanding`:

* “Hãy kiểm tra lại câu hỏi cuối cùng đang yêu cầu tổng số hay phần chênh lệch.”

Nếu diagnosis là `quantity_relation_error`:

* “Em thử xem hai đại lượng đã cho nên được cộng lại hay lấy hiệu.”

### Output

```json
{
  "hint_level": "relational",
  "hint_text": "Hãy kiểm tra lại xem hai số lượng trong đề nên được cộng lại hay lấy hiệu."
}
```

### Lý do cần policy “non-spoiler”

Tutor tốt không nên giải hộ ngay.
MathTutorBench cũng nhấn mạnh rằng dạy tốt không phải là “nói đáp án càng nhanh càng tốt”. ([arXiv][3])

---

## 7.8 Hint Verifier

### Nhiệm vụ

Kiểm tra hint có:

* đúng diagnosis không
* nhất quán với reference evidence không
* spoil quá mức không

### Rule-based bản đầu

Có thể làm rule đơn giản:

* không chứa trực tiếp final numeric answer
* không chứa full equation/reference chain hoàn chỉnh
* có nhắc đúng loại lỗi

### Output

```json
{
  "is_valid_hint": true,
  "violations": []
}
```

### Vì sao cần module này

Nếu không có hint verifier, hệ rất dễ “trông thông minh” nhưng thật ra là spoil lời giải hoặc nói sai hướng.

---

## 8. Dữ liệu nội bộ cần chuẩn hóa

Bạn nên thống nhất ngay một schema tổng cho toàn pipeline.

```json
{
  "id": "gsm8k_000123",
  "problem": "...",
  "student_answer": "...",
  "reference": {
    "final_answer": 18,
    "solution_text": "...",
    "structured_trace": {}
  },
  "answer_check": {
    "is_correct": false,
    "normalized_student_value": 16,
    "comparison_type": "numeric_incorrect"
  },
  "symbolic_state": {},
  "verification": {
    "flags": [],
    "evidence": []
  },
  "diagnosis": {
    "label": "quantity_relation_error",
    "localization": "combining_quantities",
    "explanation_internal": "..."
  },
  "hint": {
    "hint_level": "relational",
    "hint_text": "..."
  },
  "hint_verification": {
    "is_valid_hint": true,
    "violations": []
  }
}
```

Đây là thứ cực quan trọng trước khi code nhiều.

---

## 9. Thứ tự triển khai nên làm

## Giai đoạn 1: chạy được end-to-end tối thiểu

Làm trước:

* dataset loader
* answer parser
* reference solver wrapper
* answer checker
* diagnosis đơn giản rule/prompt-based
* hint generator cơ bản

Tiêu chí xong giai đoạn 1:

* đưa vào `problem + answer`
* hệ trả ra `diagnosis + hint`
* chạy được trên một subset nhỏ GSM8K

## Giai đoạn 2: thêm symbolic state và verifier

Làm tiếp:

* structured translator
* symbolic state schema
* rule-based / constraint-based verifier
* diagnosis dựa trên verifier evidence

Tiêu chí xong giai đoạn 2:

* diagnosis không còn thuần prompt
* có thể trace ngược vì sao gán nhãn lỗi

## Giai đoạn 3: chuẩn hóa đánh giá tutor

Làm tiếp:

* diagnosis accuracy
* hint correctness
* non-spoiler rate
* recovery rate

Tiêu chí xong giai đoạn 3:

* có bộ metric riêng cho tutor, không chỉ solve accuracy

## Giai đoạn 4: mở rộng

Sau cùng mới nghĩ tới:

* problem + student partial solution
* repair search
* DPO / RL-light
* cross-benchmark ngoài GSM8K

---

## 10. Metric cần theo dõi ngay từ đầu

### Metric lõi

* `solve_accuracy_reference`
  solver tham chiếu đúng bao nhiêu

* `answer_check_accuracy`
  checker xác định đúng/sai có chuẩn không

* `diagnosis_accuracy`
  diagnosis label có khớp nhãn kỳ vọng trên tập eval nhỏ không

* `hint_correctness`
  hint có đúng hướng không

* `non_spoiler_rate`
  hint có tránh lộ đáp án trực tiếp không

### Metric rất nên có

* `recovery_rate_after_hint`
  sau khi nhận hint, một student simulator hoặc model học sinh có sửa đúng được không

MathTutorBench cho thấy các metric tutoring cần vượt xa final correctness. ([arXiv][3])

---

## 11. Công nghệ đề xuất

### Model

* Qwen2.5-Math làm solver/reference backbone
* có thể dùng cùng model cho diagnosis/hint giai đoạn đầu

### Symbolic

* Python
* SymPy
* rule-based checker
* nếu cần thêm constraint solver sau

### Hạ tầng

* Python project chuẩn
* dataset cache local
* logging rõ từng stage
* config theo YAML/TOML

### Vì sao chọn vậy

Đủ mạnh để chạy thật, nhưng không quá nặng như formal proof stack.

---

## 12. Cấu trúc thư mục code đề xuất

```text
project/
  configs/
  data/
  notebooks/
  scripts/
  src/
    dataset/
    solver/
    checker/
    symbolic/
    diagnosis/
    hinting/
    evaluation/
    utils/
  tests/
  outputs/
  docs/
```

### Giải thích nhanh

* `dataset/`: loader GSM8K, builders
* `solver/`: model wrapper, prompting, best-of-N nếu có
* `checker/`: answer parsing, normalization, exact/approx compare
* `symbolic/`: state builder, verifier
* `diagnosis/`: taxonomy, diagnosis engine
* `hinting/`: hint generation + hint verifier
* `evaluation/`: metric scripts
* `docs/`: lưu chính tài liệu này và các design update

---

## 13. API nội bộ tối thiểu

### Solver

```python
solve_problem(problem_text: str) -> ReferenceSolution
```

### Checker

```python
check_answer(problem_text: str, student_answer: str, reference: ReferenceSolution) -> AnswerCheck
```

### State builder

```python
build_symbolic_state(problem_text: str, student_answer: str, reference: ReferenceSolution) -> SymbolicState
```

### Verifier

```python
verify_state(state: SymbolicState) -> VerificationResult
```

### Diagnosis

```python
diagnose(problem_text: str, student_answer: str, answer_check: AnswerCheck, verification: VerificationResult, reference: ReferenceSolution) -> Diagnosis
```

### Hint

```python
generate_hint(problem_text: str, diagnosis: Diagnosis, verification: VerificationResult) -> Hint
```

### Hint verifier

```python
verify_hint(problem_text: str, hint: Hint, diagnosis: Diagnosis, reference: ReferenceSolution) -> HintVerification
```

---

## 14. Những quyết định kỹ thuật đã chốt

1. **Không lấy tiếng Việt làm novelty.**
2. **Không khóa vào hàm số; dùng GSM8K-style trước.**
3. **Không lấy RL làm headline.**
4. **Có dùng model, và model là phần neural cốt lõi.**
5. **Solver + verifier mới là nền cho tutor.**
6. **Bản đầu chỉ cần problem + answer.**
7. **Output chính là diagnosis + hint.**
8. **Lean/Isabelle không phải ưu tiên của sprint đầu.**

---

## 15. Rủi ro và cách giảm rủi ro

### Rủi ro 1: solver tham chiếu sai

Nếu reference sai, cả tutor sẽ lệch.

Giảm rủi ro:

* dùng best-of-N nhỏ
* parse final answer cẩn thận
* log confidence
* test solver riêng trước

### Rủi ro 2: translator/state builder sai

State builder là chỗ dễ hỏng nhất.

Giảm:

* state đơn giản trước
* debug nhiều ví dụ tay
* log từng field và nguồn suy luận

### Rủi ro 3: diagnosis quá mơ hồ

Nếu taxonomy quá rộng, hint sẽ nhảm.

Giảm:

* taxonomy nhỏ, rõ
* label “unknown_error” cho ca chưa chắc

### Rủi ro 4: hint spoil

Giảm:

* hint levels
* rule filter không cho lộ final answer
* kiểm non-spoiler rate

### Rủi ro 5: làm thành một “prompt demo”

Giảm:

* phải có schema dữ liệu
* phải có module verifier
* phải có metric riêng cho diagnosis/hint

---

## 16. Bản đầu thế nào là “đạt”

Bản đầu không cần mới hoàn toàn. Nó chỉ cần đạt 4 điều:

1. Có pipeline end-to-end chạy được.
2. Dữ liệu, module, output đều có schema rõ.
3. Diagnosis và hint không còn hoàn toàn là free-form prompting.
4. Có metric riêng cho tutoring, không chỉ solve accuracy.

Nếu làm được 4 điều này, bạn đã có một nền kỹ thuật đúng để tiếp tục tăng novelty sau đó.

---

## 17. Tóm tắt một đoạn để bạn tự nhắc mình trước khi code

**Mình đang xây một tutor toán kiểu neuro-symbolic. Hệ nhận problem + answer, dùng model toán mạnh để tạo reference, dùng symbolic/verifier layer để kiểm chứng và định vị lỗi, rồi sinh diagnosis + hint theo nguyên tắc không spoil. Bản đầu chạy trên GSM8K-style, chưa cần RL hay formal proof assistants, nhưng phải có schema, verifier và tutor metrics ngay từ đầu.**

---

Nếu bạn muốn, bước tiếp theo mình sẽ biến tài liệu này thành **checklist triển khai 2 tuần đầu**, kiểu rất thực dụng: hôm nay code file nào, module nào trước, test gì trước.

[1]: https://github.com/openai/grade-school-math?utm_source=chatgpt.com "GitHub - openai/grade-school-math"
[2]: https://arxiv.org/abs/2409.12122?utm_source=chatgpt.com "Qwen2.5-Math Technical Report: Toward Mathematical Expert Model via ..."
[3]: https://arxiv.org/abs/2502.18940?utm_source=chatgpt.com "MathTutorBench: A Benchmark for Measuring Open-ended Pedagogical Capabilities of LLM Tutors"
[4]: https://arxiv.org/abs/2505.15960?utm_source=chatgpt.com "Training Step-Level Reasoning Verifiers with Formal Verification Tools"

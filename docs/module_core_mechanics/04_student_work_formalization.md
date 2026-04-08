# Cơ Chế Lõi Của Student Work Formalization

Tài liệu này mô tả đúng cơ chế hiện tại của tầng formalize bài làm học sinh, bám trực tiếp vào code trong:

- `src/formalizer/student_work.py`
- `src/formalizer/student_work_builder.py`
- `src/formalizer/student_work_llm.py`
- `src/formalizer/student_work_validation.py`
- `src/formalizer/student_work_graph.py`
- `src/formalizer/reference_trace.py`
- các schema student-side trong `src/models/formalizer_schemas.py`

Tầng này nhận đầu vào là:

1. `raw_answer`
2. `problem` tùy chọn
3. `reference` tùy chọn
4. `llm_client` tùy chọn

và đầu ra là:

- `StudentWorkState`

Trong kiến trúc hiện tại, student side đi theo đúng triết lý của problem side:

1. heuristic anchors
2. semantic sketch từ LLM
3. local compile
4. graph build
5. validation / retry / fallback

## 1. Contract dữ liệu của student side

Ba schema chính của tầng này là:

1. `StudentStepAttempt`
2. `StudentSemanticFact`
3. `StudentWorkState`

### 1.1 `StudentStepAttempt`

Có các field:

1. `step_id`
2. `raw_text`
3. `operation`
4. `input_values`
5. `extracted_value`
6. `referenced_ids`
7. `confidence`
8. `notes`

Invariant ở model:

1. `step_id` không được rỗng

### 1.2 `StudentSemanticFact`

Có các field:

1. `fact_id`
2. `label`
3. `value`
4. `grounding`
5. `confidence`
6. `notes`

Invariant:

1. `fact_id` không được rỗng
2. `label` không được rỗng

### 1.3 `StudentWorkState`

Có các field:

1. `raw_answer`
2. `normalized_final_answer`
3. `mode`
4. `semantic_facts`
5. `steps`
6. `student_graph`
7. `selected_target_ref`
8. `assumptions`
9. `confidence`
10. `notes`

Invariant ở model:

1. không được có `step_id` trùng trong `steps`
2. không được có `fact_id` trùng trong `semantic_facts`
3. nếu `student_graph` có mặt và bài làm có structure parse được, thì `student_graph.target_node_id` không được là `None`

## 2. Entry point công khai: `formalize_student_work`

Hàm công khai nằm trong `src/formalizer/student_work.py`:

- `formalize_student_work(raw_answer, problem=None, reference=None, llm_client=None)`

### 2.1 Trình tự thật sự

Hàm này luôn làm:

1. `heuristic_state = _heuristic_formalize_student_work(raw_answer, problem=problem, reference=reference)`

Sau đó:

2. nếu `llm_client is None` -> trả `heuristic_state`
3. nếu có `llm_client` -> gọi `_llm_formalize_student_work(...)`

### 2.2 Fallback cuối

Nếu `_llm_formalize_student_work(...)` ném:

1. `LLMGenerationError`
2. `ValueError`
3. `TypeError`

thì entrypoint:

1. copy `heuristic_state.notes`
2. append `llm_student_parse_failed_fallback`
3. trả về `heuristic_state`

Điều đó có nghĩa:

- heuristic state là fallback artifact cuối
- nhưng khi LLM path thành công, heuristic state chỉ đóng vai trò anchor

## 3. Heuristic formalization của student side bắt đầu ở đâu

Hàm:

- `_heuristic_formalize_student_work(raw_answer, problem=None, reference=None)`

nằm trong `student_work_builder.py`.

Đây là nơi student side tạo:

1. final answer heuristic
2. candidate step spans
3. heuristic step attempts
4. mode heuristic
5. target ref heuristic
6. student graph heuristic

Tuy nhiên sau refactor, heuristic side đã bị hạ xuống thành:

- anchor layer

không còn là nơi commit semantic mạnh như trước.

## 4. Final answer heuristic: `_extract_final_answer`

Hàm:

- `_extract_final_answer(raw_answer)`

trả:

1. `float | None`
2. `notes`

### 4.1 Trình tự dò final answer

Nó thử theo thứ tự:

1. `#### number`
2. answer cue regex
3. last numeric token

### 4.2 Regex `#### number`

`_HASH_PATTERN`:

```python
####\s*(-?\d[\d,]*\.?\d*)
```

Nếu match:

1. parse bằng `_parse_number(...)`
2. nếu parse được -> return ngay
3. note `hash_marker_match`
4. nếu parse không được -> note `hash_marker_unparseable`

### 4.3 Regex answer cue

`_ANSWER_PATTERN`:

```python
(?:answer|final answer|result|total)\s*(?:is|=|:)?\s*(-?\d[\d,]*\.?\d*)
```

Regex này không phân tích ngữ nghĩa, chỉ dò các cue surface như:

1. `answer is 117`
2. `final answer: 42`
3. `result = 9`

Nếu parse được:

- return ngay và note `answer_cue_match`

Nếu không parse được:

- note `answer_cue_unparseable`

### 4.4 Fallback last number

Nếu không bắt được hai case trên:

1. lấy tất cả `_NUMBER_PATTERN.findall(raw_answer)`
2. nếu có ít nhất một số:
   - parse số cuối

Nếu parse được:

1. nếu chỉ có một số trong toàn bài -> note `last_number_selected`
2. nếu có nhiều số -> note `multiple_numbers_found:<count>`

Nếu parse không được:

- note `last_number_unparseable`

### 4.5 Nếu không có số nào cả

Trả:

1. `None`
2. notes chứa `no_numeric_candidate`

### 4.6 `_parse_number` thực sự làm gì

Helper `_parse_number(text)`:

1. `strip()`
2. bỏ dấu `,`
3. nếu số kết thúc bằng `.` mà phần trước vẫn là numeric hợp lệ, bỏ dấu `.` cuối
4. `float(...)`

Điều này giải thích vì sao các text kiểu:

- `117.`

vẫn parse được ra `117.0`.

## 5. Heuristic step splitting: `_split_student_steps`

Hàm:

- `_split_student_steps(raw_answer)`

là nơi tạo candidate step spans.

### 5.1 Rule 1: split theo newline

`_STEP_SPLIT_PATTERN` là:

```python
(?:\r?\n)+
```

Code:

1. split theo cụm newline
2. `strip()` từng segment
3. bỏ segment rỗng

Nếu sau bước này có **hơn 1 dòng**:

- trả luôn `raw_lines`

Tức là nếu học sinh đã xuống dòng, code ưu tiên tin cấu trúc đó.

### 5.2 Rule 2: split theo dấu câu / ranh giới viết hoa

Nếu newline split không tạo được nhiều dòng, code thử:

```python
re.split(r"(?<=[.!?])(?:\s+|(?=[A-Z0-9]))", raw_answer)
```

Regex này nghĩa là:

1. sau một dấu `. ! ?`
2. nếu có:
   - khoảng trắng
   - hoặc ngay sau đó là chữ hoa / chữ số

thì cắt.

Đây là lý do code hiện tại tách được các chuỗi kiểu:

- `people.Then the next...`

thành hai span.

Nếu bước này tạo được hơn 1 segment:

- trả `sentence_lines`

### 5.3 Rule 3: giữ nguyên cả đoạn

Nếu cả hai cách trên đều không tạo được nhiều segment:

- trả `[raw_answer.strip()]`

### 5.4 Vai trò đúng của step splitting

Hàm này không “hiểu” step.

Nó chỉ tạo:

- candidate surface spans

cho heuristic step builder và LLM draft.

## 6. Heuristic trace helper: `reference_trace.py`

Heuristic step parsing của student side dựa trực tiếp vào:

- `build_student_partial_trace(student_solution_text, target_text="")`
- `parse_trace_step(line, step_index, final_value)`

trong `src/formalizer/reference_trace.py`.

Đây là lớp trung gian rất quan trọng nhưng dễ bị bỏ sót.

## 7. `parse_trace_step` hoạt động thế nào

Hàm:

- `parse_trace_step(line, step_index, final_value)`

trả về một `TraceStep`.

### 7.1 Pattern 1: `% of`

`_PERCENT_OF_PATTERN`:

```python
(-?\d[\d,]*\.?\d*)\s*% of\s*(-?\d[\d,]*\.?\d*)\s*=\s*(-?\d[\d,]*\.?\d*)
```

Nếu match:

1. parse `rate`
2. parse `base`
3. parse `output`
4. tạo `TraceStep` với:
   - `operation = PERCENT_OF`
   - `input_values = [rate, base]`
   - `output_value = output`
   - `output_label = step_<index>_output`
   - `is_final_target = abs(output - final_value) < 1e-9`
   - `confidence = 0.92`
   - `provenance = SOLVER_REFERENCE`

### 7.2 Pattern 2: binary equation

`_BINARY_EQUATION_PATTERN`:

```python
(-?\d[\d,]*\.?\d*)\s*([+\-*/xX])\s*(-?\d[\d,]*\.?\d*)\s*=\s*(-?\d[\d,]*\.?\d*)
```

Nếu match:

1. parse `left`
2. parse operator
3. parse `right`
4. parse `output`
5. map operator sang `TraceOperation`:
   - `+` -> `ADD`
   - `-` -> `SUBTRACT`
   - `*`, `x`, `X` -> `MULTIPLY`
   - `/` -> `DIVIDE`

Rồi tạo `TraceStep` với:

1. `input_values = [left, right]`
2. `output_value = output`
3. confidence `0.95`

### 7.3 Pattern 3: fallback số cuối

Nếu không match 2 pattern trên:

1. lấy mọi số trong line
2. parse số cuối cùng làm `output`

Rồi tạo `TraceStep`:

1. nếu `output is not None`
   - `operation = DERIVE`
   - `confidence = 0.45`
2. nếu không
   - `operation = UNKNOWN`
   - `confidence = 0.2`

### 7.4 Ý nghĩa

`parse_trace_step` là heuristic surface parser rất nông:

1. ưu tiên equation có pattern rõ
2. nếu không thì lấy số cuối như một output candidate

## 8. `build_student_partial_trace` làm gì

Hàm:

- `build_student_partial_trace(student_solution_text, target_text="")`

### 8.1 Cách nó tách lines

Nó dùng:

- `strip_reference_markers(...)`

để:

1. split theo dòng
2. bỏ dòng rỗng
3. nếu dòng bắt đầu bằng `####` thì bỏ marker

### 8.2 Cách nó lấy final value sơ bộ

Nó nhìn:

1. dòng cuối cùng
2. lấy số cuối cùng trong dòng đó
3. parse thành `final_value`

### 8.3 Cách nó build steps

Với mỗi dòng:

1. gọi `parse_trace_step(...)`
2. sau đó sửa provenance:
   - nếu operation là `UNKNOWN` -> `PROBLEM_TEXT`
   - ngược lại -> `HEURISTIC`
3. cap confidence ở `0.8`

### 8.4 Output trace

Trả `SymbolicTrace` gồm:

1. `steps`
2. `final_value`
3. `target_label`
4. `confidence`
5. `notes`
6. `provenance = HEURISTIC`

Note có thể gồm:

1. `student_trace_steps=<n>`
2. `student_trace_contains_unknown_steps`

## 9. Heuristic step attempts: `_build_step_attempts`

Hàm:

- `_build_step_attempts(raw_answer, problem)`

đây là nơi candidate spans được đổi thành `StudentStepAttempt`.

### 9.1 Chuỗi xử lý

1. `lines = _split_student_steps(raw_answer)`
2. `trace = build_student_partial_trace(raw_answer)`
3. `notes = list(trace.notes)`
4. nếu `len(lines) > 1` -> note `student_span_candidates=<count>`

### 9.2 Với mỗi line

Code gọi:

- `parsed_line = parse_trace_step(line, index, trace.final_value)`

Rồi lấy:

1. `extracted_value = parsed_line.output_value`
2. `operation = parsed_line.operation`
3. `input_values = list(parsed_line.input_values)`
4. `referenced_ids = _referenced_problem_quantity_ids(line, problem)`

### 9.3 `_referenced_problem_quantity_ids` làm gì

Nếu `problem is None`:

- trả `[]`

Nếu có `problem`, nó duyệt từng quantity trong problem và check:

```python
quantity.surface_text.lower() in lowered_line
or f"{quantity.value:g}" in lowered_line
```

Nếu match:

- append `quantity.quantity_id`

Tức là step heuristic hiện tại chỉ tham chiếu được đến problem quantities qua:

1. surface text
2. literal numeric value

### 9.4 `step_notes` được build thế nào

Cho mỗi step:

1. nếu `parsed_line.provenance != UNKNOWN`
   - note `trace_provenance=<...>`
2. nếu line chứa `=`
   - note `contains_equation`
3. nếu có `referenced_ids`
   - note `referenced_ids=<count>`
4. nếu có number matches
   - note `observed_numbers=<count>`

### 9.5 Confidence heuristic cho mỗi step

Qua `_step_confidence(operation, extracted_value, raw_text)`:

1. nếu operation rõ và extracted_value có:
   - `0.82`
2. nếu có extracted_value và line có `=`
   - `0.72`
3. nếu chỉ có extracted_value:
   - `0.58`
4. còn lại:
   - `0.25`

### 9.6 Kết quả

Mỗi line trở thành một `StudentStepAttempt` với:

1. `step_id = student_step_<index>`
2. `raw_text = line`
3. `operation`
4. `input_values`
5. `extracted_value`
6. `referenced_ids`
7. `confidence`
8. `notes`

## 10. Heuristic mode inference: `_infer_mode`

Hàm:

- `_infer_mode(raw_answer, steps, final_answer)`

### 10.1 Logic hiện tại

1. nếu `raw_answer` rỗng hoặc `(final_answer is None and not steps)`
   - `UNPARSEABLE`
2. nếu có ít nhất 2 step hoặc có bất kỳ step nào chứa `=`
   - `PARTIAL_TRACE`
3. nếu có đúng 1 step, step đó có `=`, và final_answer có mặt
   - `PARTIAL_TRACE`
4. còn lại:
   - `FINAL_ANSWER_ONLY` nếu final_answer có mặt
   - ngược lại `UNPARSEABLE`

### 10.2 Điều đáng chú ý

Heuristic mode hiện **không** tự sinh `FULL_TRACE`.

`FULL_TRACE` là mode thường chỉ xuất hiện khi LLM sketch yêu cầu.

## 11. Heuristic target ref hiện làm gì

Hàm:

- `_infer_selected_target_ref(final_answer, problem)`

hiện tại trả:

- `None`

Đây là thay đổi chủ đích.

Student heuristic layer **không còn** tự đoán target semantics từ va chạm số nữa.

## 12. Heuristic state được dựng ra sao

Trong `_heuristic_formalize_student_work(...)`, code làm:

1. `cleaned_answer = raw_answer.strip()`
2. `final_answer, final_answer_notes = _extract_final_answer(cleaned_answer)`
3. `steps, trace_notes = _build_step_attempts(cleaned_answer, problem)`
4. `mode = _infer_mode(cleaned_answer, steps, final_answer)`
5. `selected_target_ref = _infer_selected_target_ref(final_answer, problem)` -> hiện là `None`

### 12.1 Notes heuristic

`notes` được ghép từ:

1. `final_answer_notes`
2. `trace_notes`
3. thêm `selected_target_ref=...` nếu có
4. thêm `student_work_unparseable` nếu mode là `UNPARSEABLE`

### 12.2 Confidence heuristic toàn cục

Bắt đầu từ `0.0`, rồi:

1. `+0.35` nếu có final answer
2. `+min(0.4, 0.1 * len(steps))`
3. `+0.15` nếu có selected_target_ref
4. `+0.05` nếu mode là `PARTIAL_TRACE`

Cuối cùng cap ở `0.95`.

### 12.3 Attach graph heuristic

`StudentWorkState` heuristic vừa tạo ra sẽ đi qua:

- `_attach_student_graph(...)`

để build `student_graph`.

Tức là heuristic path cũng luôn cố có graph nếu có đủ structure.

## 13. Student graph builder: `build_student_work_graph`

Hàm:

- `build_student_work_graph(student_work, problem=None, provenance_override=None)`

nằm trong `student_work_graph.py`.

## 14. Khi nào graph không được tạo

Đầu hàm, code tính:

```python
has_structured_step = any(
    step.extracted_value is not None
    or (step.operation is not None and step.operation != TraceOperation.UNKNOWN)
    for step in student_work.steps
)
```

Nếu:

1. `student_work.normalized_final_answer is None`
2. và `not has_structured_step`

thì:

- trả `None`

Nghĩa là graph chỉ được tạo khi ít nhất có:

1. final answer parse được
2. hoặc có step structure đủ mạnh

## 15. Provenance của graph

Hàm `_graph_provenance(student_work)` quyết định:

1. nếu notes có `llm_student_parse_used` -> provenance `LLM`
2. ngược lại -> `HEURISTIC`

Tuy nhiên builder còn có `provenance_override`.

Trong path compile từ sketch, code gọi:

- `_attach_student_graph(..., provenance_override=ProvenanceSource.LLM)`

để tránh graph bị gắn provenance heuristic do thứ tự notes.

## 16. Các node mà student graph có thể tạo

### 16.1 Semantic fact nodes

Ngay đầu hàm, code duyệt mọi `student_work.semantic_facts` và gọi:

- `_ensure_reference_node(fact_id, ...)`

Nếu ref id trỏ vào semantic fact:

1. tạo node kiểu `INTERMEDIATE`
2. `label = semantic_fact.label`
3. `value = semantic_fact.value`
4. `semantic_role = INTERMEDIATE`
5. `confidence = semantic_fact.confidence`
6. `provenance = provenance`
7. notes gồm:
   - `semantic_fact.notes`
   - `grounding=<...>` nếu có grounding

### 16.2 Problem quantity nodes

Nếu ref id thuộc về quantity trong `problem`:

1. tạo node kiểu `QUANTITY`
2. mang:
   - `value`
   - `unit`
   - `entity_id`
   - `semantic_role`
   - `notes`

### 16.3 Placeholder reference nodes

Nếu ref id không phải semantic fact và không khớp problem quantity:

1. nếu `ref_id == target_variable(problem)` -> node kiểu `TARGET`
2. ngược lại -> node kiểu `INTERMEDIATE`

với note:

- `student_reference_placeholder`

Tức là graph builder có thể materialize ref placeholders nếu cần để giữ cấu trúc graph.

## 17. Operation nodes và output nodes của student graph

### 17.1 Tạo operation node cho từng step

Với mỗi `step` trong `student_work.steps`:

1. ensure các `referenced_ids` đã có node
2. nếu `step.operation is None` -> skip step
3. tạo `student_op_<step_id>` kiểu `OPERATION`

Node này mang:

1. `label = step.raw_text or step.step_id`
2. `operation = step.operation`
3. `expression = step.raw_text`
4. `step_id`
5. `step_index`
6. `confidence = step.confidence`
7. `provenance`
8. `notes = step.notes`

### 17.2 `step_index` được suy như thế nào

Nếu `step.step_id` kết thúc bằng số:

- dùng số đó

Nếu không:

- fallback sang `len(output_node_ids) + 1`

### 17.3 Input refs cho graph được chọn thế nào

Ban đầu:

- `input_refs_for_graph = list(step.referenced_ids)`

Sau đó, với mỗi `input_value` trong `step.input_values`, code thử match nó với `value_sources` đã có từ trước:

1. duyệt `value_sources` từ cuối về đầu
2. tìm source node có `abs(source_value - input_value) < 1e-9`
3. nếu tìm được và source chưa có trong input refs:
   - append source node id vào `input_refs_for_graph`

Điểm này cho phép graph tự tạo dependency giữa step hiện tại và output số học của step trước, ngay cả khi `referenced_ids` không ghi rõ.

### 17.4 Tạo input edges

Với mỗi `ref_id` trong `input_refs_for_graph`, code tạo edge:

- `INPUT_TO_OPERATION`

### 17.5 Khi nào tạo output node

Nếu `step.extracted_value is None`:

- không tạo output node

Nếu có:

1. tạo `student_output_<step_id>` kiểu `INTERMEDIATE`
2. `value = step.extracted_value`
3. `semantic_role = INTERMEDIATE`
4. `confidence = step.confidence`
5. notes = `step.notes`

Sau đó:

1. append vào `output_node_ids`
2. ghi map `output_node_to_step`
3. append `(output_node_id, extracted_value)` vào `value_sources`
4. tạo edge `OUTPUT_FROM_OPERATION`

## 18. Tạo target node cuối của student graph

Nếu `student_work.normalized_final_answer is not None`:

1. `target_node_id = "student_final_answer"`
2. tạo node kiểu `TARGET`

Node này có:

1. `label = "student_final_answer"`
2. `value = normalized_final_answer`
3. `target_variable = selected_target_ref or "student_final_answer"`
4. `confidence = clamp(student_work.confidence, 0.4, 0.99)`
5. `notes` có `selected_target_ref=...` nếu có

### 18.1 Nếu có `selected_target_ref`

Code còn ensure node cho `selected_target_ref`, rồi tạo edge:

- `TARGETS_VALUE`

từ `selected_target_ref` sang `student_final_answer`

note edge:

- `linked_from_selected_target_ref`

### 18.2 Chọn output nào link vào final target

Code tìm:

1. mọi output node có `value == normalized_final_answer`

Sau đó duyệt từ cuối về đầu và cố tránh chọn bước chỉ là restatement kiểu:

1. `step.raw_text` có chữ `answer`
2. và operation thuộc `{DERIVE, UNKNOWN}`

Nếu tìm được ứng viên “tốt hơn”:

- lấy output đó

Nếu không:

- fallback output matching cuối cùng

Rồi tạo edge:

- `TARGETS_VALUE`

từ output node đó sang `student_final_answer`

note edge:

- `linked_from_matching_final_value`

### 18.3 Nếu không có final answer nhưng có outputs

Nếu `normalized_final_answer is None` nhưng có `output_node_ids`:

- `target_node_id = output_node_ids[-1]`

Tức là graph vẫn có target node logic, nhưng khi không có đáp án cuối explicit thì target là output cuối có structure.

## 19. Notes của graph cuối

Graph notes hiện gồm:

1. `student_steps=<count>`
2. `student_graph_built`
3. nếu có semantic facts:
   - `student_semantic_facts=<count>`
4. nếu có selected target ref:
   - `selected_target_ref=<...>`

## 20. Compact draft gửi cho LLM: `_build_compact_student_draft`

Khi vào LLM path, system không gửi nguyên `StudentWorkState` làm truth.

Nó build một compact draft qua:

- `_build_compact_student_draft(heuristic_state, problem=None)`

Draft hiện gồm:

1. `raw_answer`
2. `observed_final_answer`
3. `candidate_step_spans`
4. `allowed_problem_refs`
5. `heuristic_notes`

### 20.1 `candidate_step_spans` chứa gì

Với mỗi span từ `_split_student_steps(...)`, code ghi:

1. `span_index`
2. `surface_text`
3. `observed_numbers`
4. `referenced_ids`

`observed_numbers` được lấy bằng regex số trên chính span đó.

## 21. Prompt student LLM được build thế nào

Hàm:

- `_build_llm_student_prompt(raw_answer, heuristic_state, problem, feedback_issues, attempt_index)`

### 21.1 Những field LLM phải trả

Prompt yêu cầu top-level JSON chỉ có:

1. `final_answer`
2. `mode`
3. `target`
4. `semantic_facts`
5. `trace_steps`
6. `assumptions`
7. `confidence`
8. `notes`

### 21.2 `allowed_refs`

Prompt còn truyền:

- `allowed_problem_refs = _allowed_student_refs(problem)`

`_allowed_student_refs(problem)` lấy:

1. mọi `problem.quantities[].quantity_id`
2. `problem.target.target_variable` nếu có

Tức là student sketch không được tùy tiện refer sang ref ngoài problem.

### 21.3 Hard constraints của prompt

Prompt hiện giữ các ràng buộc cốt lõi:

1. nếu học sinh nêu rõ đáp án số cuối -> copy vào `final_answer.value`
2. nếu không rõ -> dùng `null`, không dùng `0.0`
3. `trace_steps.surface_text` phải grounded trong bài làm
4. `target.selected_ref` chỉ được lấy từ allowed refs
5. `trace_steps.referenced_ids` chỉ được lấy từ allowed refs hoặc semantic fact ids
6. `semantic_facts` chỉ dùng cho hidden numeric claims học sinh thật sự dựa vào
7. nếu không chắc thì omit / null, không đoán
8. không thêm step không có trong bài học sinh
9. ưu tiên faithful step structure
10. chỉ dùng enum hợp lệ

## 22. LLM retry loop của student side

Hàm:

- `_llm_formalize_student_work(raw_answer, heuristic_state, problem, reference, llm_client)`

### 22.1 Số vòng retry

Code chạy:

```python
for attempt_index in range(1, 4):
```

### 22.2 Payload notes

Sau khi model trả JSON, code append:

- `llm_student_parse_attempt:<attempt_index>`

vào `payload["notes"]`.

### 22.3 Nếu compile sketch fail

Nếu `_build_student_work_from_sketch(...)` ném `ValueError` hoặc `TypeError`:

1. chuyển lỗi qua `_schema_validation_result(exc)`
2. build feedback payload
3. retry

### 22.4 Nếu compile pass

Code gọi:

- `_student_sanity_validation_result(refined, problem=problem, reference=reference)`

Nếu validation pass:

1. thêm notes diff với heuristic
2. đảm bảo có `llm_student_parse_used`
3. append `llm_student_semantic_sketch_used`
4. nếu attempt > 1 -> append `llm_student_parse_repaired_after:<attempt>`
5. return state

### 22.5 Nếu validation fail

1. build feedback từ issues
2. retry tiếp

### 22.6 Nếu hết 3 attempt vẫn fail

1. lấy `heuristic_state.notes`
2. append `student_graph_issue:<issue.code>` cho từng issue cuối
3. append `llm_student_parse_failed_fallback`
4. return heuristic state

## 23. Compile semantic facts từ sketch

Trong `_build_student_work_from_sketch(...)`, bước đầu tiên là:

- `_build_student_semantic_facts_from_sketch(sketch)`

### 23.1 Mỗi fact được validate thế nào

Với mỗi dict trong `semantic_facts`:

1. build `fact_payload`
2. validate thành `StudentSemanticFact`

### 23.2 Repair confidence của fact

Nếu `validated_fact.confidence <= 0.0`:

1. nếu có `grounding` -> set confidence `0.55`
2. nếu không có grounding -> set confidence `0.4`
3. note:
   - `local_semantic_fact_repair:recomputed_confidence`

## 24. Grounding numeric fields của step

Đây là chỗ quan trọng nhất của local compile student side.

### 24.1 `_is_grounded_numeric_value(...)`

Một số `value` được coi là grounded nếu:

1. nó xuất hiện như observed number trong `surface_text`
2. hoặc nó bằng giá trị của một `problem_ref` được step tham chiếu
3. hoặc nó bằng giá trị của một `semantic_fact` được step tham chiếu

Nếu không rơi vào ba case này:

- value bị coi là không grounded

### 24.2 `_sanitize_student_step_payload(...)`

Hàm này sanitize:

1. `extracted_value`
2. `input_values`
3. `confidence`

#### `extracted_value`

Nếu `extracted_value` là số:

1. check grounded bằng `_is_grounded_numeric_value(...)`
2. nếu không grounded -> set `None`
3. thêm note:
   - `local_step_repair:dropped_ungrounded_extracted_value`

#### `input_values`

Với từng input value:

1. nếu grounded -> giữ
2. nếu không -> drop
3. note:
   - `local_step_repair:dropped_ungrounded_input_value`

#### `confidence`

Nếu `confidence <= 0.0` hoặc parse lỗi:

1. recompute bằng `_step_confidence(...)`
2. note:
   - `local_step_repair:recomputed_step_confidence`

### 24.3 Ý nghĩa

Đây là lớp chặn placeholder số kiểu `0.0` hoặc số model tưởng tượng.

## 25. Resolve step text từ sketch

Hàm:

- `_resolve_step_surface_text(raw_answer, heuristic_state, step_payload, step_index)`

### 25.1 Logic

Nếu sketch có `surface_text`:

1. normalize candidate
2. normalize toàn bộ `raw_answer`
3. nếu candidate nằm trong raw answer -> chấp nhận
4. nếu không -> ném lỗi

Nếu sketch không có `surface_text`:

1. nếu `step_index < len(heuristic_state.steps)`
   - fallback sang `heuristic_state.steps[step_index].raw_text`
2. nếu không
   - ném lỗi

Điều này đảm bảo step trong sketch phải grounded ở text học sinh.

## 26. Build steps từ sketch: `_build_student_steps_from_sketch`

Hàm này là nơi `trace_steps` của model trở thành `StudentStepAttempt`.

### 26.1 Bước đầu

1. `requested_mode = StudentWorkMode(sketch.get("mode", heuristic_state.mode))`
2. `trace_steps = sketch.get("trace_steps", [])`

Nếu `trace_steps` không phải list:

- ném lỗi

Nếu `trace_steps` rỗng:

1. nếu mode là `FINAL_ANSWER_ONLY` hoặc `UNPARSEABLE` -> trả `[]`
2. nếu mode là trace mode -> ném lỗi

### 26.2 Với mỗi raw step

Code:

1. lọc `referenced_ids` sao cho chỉ giữ ref thuộc:
   - `allowed_problem_refs`
   - hoặc `semantic_fact_ids`
2. dedupe refs
3. resolve `surface_text`
4. sanitize numeric payload
5. build `StudentStepAttempt`

### 26.3 Điều quan trọng

Step compile hiện không merge lên step ids heuristic cũ.

Nó dựng lại list steps từ sketch, chỉ dùng heuristic state như:

1. source fallback cho surface text
2. source fallback cho confidence

## 27. Prune semantic facts: `_prune_student_semantic_facts`

Hàm này loại semantic facts không hữu dụng.

### 27.1 Nó giữ fact nào

Nó chỉ giữ fact nếu:

1. `fact.fact_id` xuất hiện trong ít nhất một `step.referenced_ids`

### 27.2 Nó loại fact nào

1. fact không được step nào tham chiếu
   - note `local_semantic_fact_pruned:unreferenced:<fact_id>`
2. fact trùng signature với fact khác
   - signature gồm:
     - normalized label
     - value
     - normalized grounding
   - note `local_semantic_fact_pruned:duplicate:<fact_id>`

Điểm này giữ semantic layer gọn và thực sự gắn với trace.

## 28. Repair target ref: `_repair_selected_target_ref`

Hàm:

- `_repair_selected_target_ref(selected_target_ref, normalized_final_answer, problem)`

### 28.1 Khi nào repair

Nếu:

1. `problem.target` có mặt
2. `selected_target_ref` không rỗng
3. `selected_target_ref` trỏ vào một visible problem quantity
4. `normalized_final_answer` có mặt
5. giá trị quantity đó **không bằng** final answer

thì:

1. repair sang `problem.target.target_variable`
2. note:
   - `local_target_repair:retargeted_selected_ref:<old>-><new>`

### 28.2 Ý nghĩa

Chỗ này chặn kiểu model chọn nhầm `quantity_1 = 847` làm selected target ref trong khi final answer thật là `117`.

## 29. Reconcile mode: `_reconcile_student_mode`

Hàm này đảm bảo `mode` không mâu thuẫn với `steps` và `normalized_final_answer`.

### 29.1 Nếu mode là `final_answer_only` hoặc `unparseable` nhưng vẫn có steps

Repair sang:

1. `FULL_TRACE` nếu `len(steps) >= 2`
2. ngược lại `PARTIAL_TRACE`

và note:

- `local_mode_repair:<old>-><new>`

### 29.2 Nếu mode là trace nhưng không có steps

1. nếu có `normalized_final_answer`
   - repair sang `FINAL_ANSWER_ONLY`
2. nếu không
   - repair sang `UNPARSEABLE`

### 29.3 Nếu mode là `UNPARSEABLE` nhưng lại có final answer

Repair sang:

1. mode suy từ `_infer_mode("", steps, normalized_final_answer)`
2. nếu mode suy ra vẫn là `UNPARSEABLE` thì dùng `FINAL_ANSWER_ONLY`

## 30. Compile toàn bộ sketch thành `StudentWorkState`

Hàm trung tâm:

- `_build_student_work_from_sketch(raw_answer, heuristic_state, sketch, problem=None)`

### 30.1 Thứ tự xử lý

1. lấy `allowed_problem_refs`
2. lấy `requested_mode`
3. build `all_semantic_facts`
4. lấy `semantic_fact_ids`
5. lấy `semantic_fact_values`
6. build `steps` từ sketch
7. prune semantic facts
8. compile `normalized_final_answer`
9. build `selected_target_ref`
10. repair `selected_target_ref`
11. reconcile `mode`
12. recompute `overall_confidence` nếu cần
13. merge payload
14. validate thành `StudentWorkState`
15. attach graph với provenance LLM

### 30.2 `normalized_final_answer` được lấy thế nào

Ban đầu:

- lấy từ `heuristic_state.normalized_final_answer`

Nếu sketch có `final_answer.value`:

- overwrite bằng value đó

Nếu là `int`:

- ép sang `float`

### 30.3 Confidence tổng được repair thế nào

Lấy:

- `overall_confidence = sketch.get("confidence", heuristic_state.confidence)`

Nếu parse lỗi hoặc `overall_confidence <= 0.0`:

1. dùng `heuristic_state.confidence`
2. nếu heuristic confidence cũng <= 0:
   - dùng `0.6` nếu có final answer
   - ngược lại `0.35`
3. note:
   - `local_student_repair:recomputed_confidence`

### 30.4 Merged payload cuối

Code lấy:

- `heuristic_state.model_dump(mode="json")`

rồi overwrite bằng:

1. `raw_answer`
2. `normalized_final_answer`
3. `mode`
4. `semantic_facts`
5. `steps`
6. `selected_target_ref`
7. `assumptions`
8. `confidence`
9. `notes`
10. `student_graph = None`

Sau đó append:

1. repair notes
2. mode repair notes
3. `llm_student_parse_used`

Rồi validate bằng:

- `StudentWorkState.model_validate(merged_payload)`

Cuối cùng attach graph với:

- `provenance_override = LLM`

## 31. Student sanity validation

Sau khi compile ra state, LLM loop gọi:

- `_student_sanity_validation_result(student_state, problem, reference)`

### 31.1 Allowed refs

Code build:

1. `allowed_problem_refs`
   - mọi problem quantity id
   - target variable nếu có
2. `allowed_step_refs = allowed_problem_refs + semantic_fact_ids`

### 31.2 Kiểm `selected_target_ref`

Nếu `selected_target_ref` không nằm trong `allowed_problem_refs`:

- issue `student_invalid_selected_target_ref`

### 31.3 Kiểm `referenced_ids`

Với mỗi step:

1. nếu có ref không nằm trong `allowed_step_refs`
   - issue `student_unknown_referenced_ids`

### 31.4 Kiểm `operation`

Nếu `step.operation is None`:

- issue `student_missing_operation`

### 31.5 Kiểm mode invariants

1. `FINAL_ANSWER_ONLY` mà không có final answer
   - `student_missing_final_answer`
2. `FINAL_ANSWER_ONLY` mà vẫn có steps
   - `student_final_answer_only_with_steps`
3. `UNPARSEABLE` mà lại có structure parse được
   - `student_unparseable_with_structure`
4. `PARTIAL_TRACE` hoặc `FULL_TRACE` mà không có steps
   - `student_trace_mode_missing_steps`

### 31.6 Kiểm graph

Nếu:

1. state có parseable final answer hoặc step structure
2. nhưng `student_graph is None`

-> issue:

- `student_missing_graph`

Nếu `student_graph` có mặt nhưng `target_node_id is None`:

- issue `student_graph_missing_target`

### 31.7 Output

Validator trả `GraphValidationResult` với:

1. `is_valid`
2. `issues`
3. `target_node_id`
4. `operation_node_count`
5. `notes = ["student_sanity_validation"]`

## 32. So sánh với heuristic để ghi notes diff

Nếu LLM path thành công, code gọi:

- `_compare_with_heuristic_student_notes(heuristic_state, refined_state)`

Nó ghi diff nếu có khác biệt ở:

1. `normalized_final_answer`
2. `mode`
3. `selected_target_ref`
4. `step_count`
5. từng step:
   - `operation`
   - `extracted_value`
   - `referenced_ids`

Mục đích là giữ trace giải thích nội bộ về việc LLM path đã thay đổi artifact ra sao.

## 33. Kết luận đúng với code hiện tại

Nếu mô tả thật ngắn nhưng chính xác:

- Student work formalization hiện bắt đầu bằng heuristic extraction rất nông để lấy final answer, step spans và anchor steps; sau đó LLM sinh semantic sketch grounded trong text học sinh; local compiler build lại `StudentWorkState`, lọc số không grounded, prune semantic facts, repair target/mode, dựng `student_graph`, rồi mới validate và chấp nhận hoặc fallback.

Nếu nén thành 5 khâu:

1. final-answer + span heuristics
2. semantic sketch from LLM
3. local grounded compile
4. graph build
5. sanity validation / retry / fallback

Đó là cơ chế lõi hiện tại của `04_student_work_formalization`.

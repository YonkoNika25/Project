# Cơ Chế Lõi Của Evidence

Tài liệu này mô tả đúng tầng `evidence` hiện tại, bám trực tiếp vào code trong:

- `src/evidence/alignment.py`
- `src/evidence/builder.py`
- các schema:
  - `EvidenceItem`
  - `DiagnosisEvidence`

Tầng này nhận đầu vào là:

1. `problem: FormalizedProblem`
2. `reference: CanonicalReference`
3. `student: StudentWorkState`

và đầu ra là:

- `DiagnosisEvidence`

Vai trò của tầng này là:

1. chiếu reference và student về cùng một dạng step-level comparable payload
2. làm global alignment
3. suy target misunderstanding bằng tín hiệu cấu trúc
4. sinh các `EvidenceItem`
5. tính `first_divergence_step_id`
6. tổng hợp `likely_error_mechanisms`

Tầng này **không** đưa ra diagnosis label cuối cùng.

Nó chỉ xây bằng chứng có cấu trúc cho diagnosis layer phía sau.

## 1. Contract dữ liệu đầu ra

### 1.1 `EvidenceItem`

Schema `EvidenceItem` có:

1. `evidence_type`
2. `description`
3. `confidence`
4. `reference_step_id`
5. `student_step_id`
6. `quantity_ids`
7. `metadata`

Invariant:

1. `evidence_type` không được rỗng

### 1.2 `DiagnosisEvidence`

Schema `DiagnosisEvidence` có:

1. `evidence_items`
2. `alignment_map`
3. `first_divergence_step_id`
4. `likely_error_mechanisms`
5. `confidence`
6. `notes`

Điểm cần nắm:

- `DiagnosisEvidence` không chỉ là list evidence items
- nó còn giữ:
  - full alignment map
  - first divergence
  - mechanism summary

## 2. Entry point công khai của tầng evidence

Hàm chính:

- `build_diagnosis_evidence(problem, reference, student)`

nằm trong `src/evidence/builder.py`.

Đây là nơi gom toàn bộ alignment và structural inference lại thành `DiagnosisEvidence`.

## 3. Case đặc biệt đầu tiên: unparseable

Ở đầu `build_diagnosis_evidence(...)`, code check:

1. `student.mode == StudentWorkMode.UNPARSEABLE`
2. hoặc `student.normalized_final_answer is None`

Nếu rơi vào một trong hai:

- return `_build_unparseable_evidence()`

### 3.1 `_build_unparseable_evidence()` trả gì

Nó trả một `DiagnosisEvidence` cố định:

1. `evidence_items` có đúng 1 item:
   - `evidence_type = "unparseable_answer"`
   - mô tả không normalize được thành target số
   - confidence `0.96`
2. `alignment_map = []`
3. `first_divergence_step_id = None`
4. `likely_error_mechanisms = ["unparseable_answer"]`
5. `confidence = 0.94`
6. notes:
   - `student_work_unparseable`

Điều này có nghĩa:

- nếu student side không formalize được bài làm, evidence layer dừng ở mức coarse-grained
- không cố bịa alignment

## 4. Hai dạng step payload nội bộ

Trong `alignment.py`, evidence layer làm việc với hai dataclass nội bộ:

1. `StepGraphPayload`
2. `StepAlignment`

### 4.1 `StepGraphPayload`

Có các field:

1. `step_id`
2. `output_ref`
3. `operation`
4. `input_refs`
5. `dependency_step_ids`
6. `output_value`

Đây là representation trung gian thống nhất giữa:

1. canonical reference steps
2. student steps

### 4.2 `StepAlignment`

Có các field:

1. `student_step_id`
2. `reference_step_id`
3. `matched_output_ref`
4. `score`
5. `reasons`
6. `relationship`
7. `dependency_overlap`
8. `missing_dependencies`
9. `extra_dependencies`

Đây là output trực tiếp của global alignment.

## 5. So khớp giá trị: `values_match`

Hàm:

- `values_match(left, right)`

chỉ làm:

```python
abs(left - right) < 1e-9
```

và nếu một trong hai là `None` thì trả `False`.

Điểm này rất quan trọng:

- mọi chỗ so final answer / step output trong evidence hiện đang dùng exact numeric match với tolerance rất nhỏ

## 6. Projection canonical reference thành step payloads

Hàm:

- `reference_steps(reference)`

đổi `CanonicalReference` sang `list[StepGraphPayload]`.

### 6.1 Dữ liệu đầu vào thật sự

Code dùng:

1. `reference.chosen_plan.steps`
2. `reference.execution_trace.step_results`

### 6.2 Cách build dependency của canonical step

Với mỗi `step` trong `reference.chosen_plan.steps`, code tạo:

```python
dependency_step_ids = [
    prior_step.step_id
    for prior_step in reference.chosen_plan.steps
    if prior_step.output_ref in step.input_refs
]
```

Nghĩa là dependency canonical được suy bằng cách:

1. nhìn input refs của step hiện tại
2. xem những input ref đó có phải output ref của step nào trước đó không

Đây là dependency step-level, không phải graph traversal tổng quát.

### 6.3 Cách gắn output value

Với mỗi cặp `(step, result)` trong:

```python
zip(reference.chosen_plan.steps, reference.execution_trace.step_results)
```

payload lấy:

1. `output_value = result.output_value if result.success else None`

Nghĩa là reference step payload luôn mang theo giá trị thực thi của step đó nếu execution step thành công.

### 6.4 Kết quả

Mỗi canonical step trở thành:

1. `step_id`
2. `output_ref`
3. `operation`
4. `input_refs`
5. `dependency_step_ids`
6. `output_value`

## 7. Projection student side thành step payloads

Hàm:

- `student_steps(student)`

đổi `StudentWorkState` thành `list[StepGraphPayload]`.

Đây là phần phức tạp hơn reference side.

## 8. Mục tiêu thật sự của `student_steps(student)`

Hàm này không dùng trực tiếp `student.steps` rồi dừng.

Nó cố dùng `student.student_graph` để suy:

1. output node nào do step nào sinh ra
2. dependency giữa các step
3. dependency thông qua semantic facts

Tức là student side payload được graph-enriched.

## 9. Bước 1 trong `student_steps`: build mapping từ graph

Code tạo trước:

1. `output_node_to_step_id`
2. `step_to_output_node`
3. `dependency_edges_to_step`
4. `step_order`
5. `semantic_fact_by_id`

### 9.1 `step_order`

Map:

```python
{step.step_id: index for index, step in enumerate(student.steps)}
```

được dùng để kiểm tra step nào “đứng trước” step nào trong bài học sinh.

### 9.2 `semantic_fact_by_id`

Map từ:

- `fact_id -> StudentSemanticFact`

được dùng để suy dependency từ semantic facts sang supporting steps.

## 10. Semantic fact support: `_semantic_fact_supporting_steps`

Đây là nested helper trong `student_steps(student)`.

Input:

1. `fact_id`
2. `target_step_id`

### 10.1 Cách nó tìm supporting steps

1. lấy semantic fact theo `fact_id`
2. lấy `target_index` từ `step_order`
3. duyệt mọi `candidate` trong `student.steps`
4. chỉ xét các step có `candidate_index < target_index`

Nghĩa là:

- chỉ step trước mới được coi là hỗ trợ cho fact mà step hiện tại dùng

### 10.2 Hai cách support được nhận

#### Cách 1: grounding text

Nếu:

1. `fact.grounding` có mặt
2. `fact.grounding.strip()` nằm trong `candidate.raw_text`

-> `candidate.step_id` được coi là supporting step

#### Cách 2: value match

Nếu:

1. `fact.value is not None`
2. `values_match(candidate.extracted_value, fact.value)`

-> `candidate.step_id` cũng được coi là supporting step

### 10.3 Ý nghĩa

Đây là fix quan trọng của semantic-fact dependency:

- semantic fact không có producing op node riêng
- nên alignment phải tự suy step support từ grounding hoặc value

## 11. Bước 2 trong `student_steps`: map output node sang step

Nếu `student.student_graph` có mặt, code duyệt tất cả edges.

### 11.1 Với mỗi `OUTPUT_FROM_OPERATION`

Code lấy:

1. `source_node` là operation node
2. `target_node` là output node

Nếu `source_node.step_id` có mặt:

1. `output_node_to_step_id[target_node.node_id] = source_node.step_id`
2. `step_to_output_node[source_node.step_id] = target_node.node_id`

Kết quả:

- biết output node nào được sinh bởi step nào
- biết step nào sinh ra output node nào

## 12. Bước 3 trong `student_steps`: suy dependency edges cho từng step

Code lại duyệt toàn bộ graph edges, nhưng chỉ lấy:

- `INPUT_TO_OPERATION`

### 12.1 Nếu source edge là output node của step trước

Nếu `edge.source_node_id` nằm trong `output_node_to_step_id`:

1. lấy `source_step_id`
2. append vào `dependency_edges_to_step[target_step_id]`

Đây là dependency direct từ output step trước sang step hiện tại.

### 12.2 Nếu source edge là semantic fact

Nếu `edge.source_node_id` nằm trong `semantic_fact_by_id`:

1. gọi `_semantic_fact_supporting_steps(edge.source_node_id, target_step_id)`
2. extend dependency list của step hiện tại bằng các supporting step đó

Đây là chỗ semantic fact được đưa vào dependency alignment.

## 13. Bước 4 trong `student_steps`: build payload cuối cho từng step

Sau khi có mapping và dependency info, code duyệt từng `step` trong `student.steps`.

Với mỗi step:

1. lấy `dependency_step_ids = dependency_edges_to_step.get(step.step_id, [])`
2. dedupe dependency ids theo thứ tự
3. tạo `StepGraphPayload` với:
   - `step_id = step.step_id`
   - `output_ref = step_to_output_node.get(step.step_id)`
   - `operation = step.operation or UNKNOWN`
   - `input_refs = list(step.referenced_ids)`
   - `dependency_step_ids = deduped_dependencies`
   - `output_value = step.extracted_value`

### 13.1 Điều quan trọng

Student step payload hiện:

1. dùng `step.referenced_ids` làm input refs semantic
2. nhưng dependency step ids lại đến từ graph edges và semantic-fact support

Tức là:

- `input_refs` và `dependency_step_ids` không phải cùng một tầng representation

## 14. Local match score: `_local_match_score`

Hàm:

- `_local_match_score(student_step, reference_step)`

trả:

1. `score`
2. `reasons`

### 14.1 Thành phần điểm

#### `output_value_match`

Nếu:

- `values_match(student_step.output_value, reference_step.output_value)`

thì:

1. `score += 6.0`
2. reason `output_value_match`

#### `operation_match`

Nếu:

1. `student_step.operation != UNKNOWN`
2. và `student_step.operation == reference_step.operation`

thì:

1. `score += 3.0`
2. reason `operation_match`

#### `input_overlap`

Nếu intersection giữa:

1. `student_step.input_refs`
2. `reference_step.input_refs`

không rỗng:

1. `score += min(2.0, len(overlap))`
2. reason `input_overlap:<...>`

#### Numeric disagreement penalty

Nếu cả student và reference đều có output_value:

```python
score -= min(abs(student - reference) / 50.0, 1.5)
```

### 14.2 Ý nghĩa

Điểm alignment hiện nghiêng mạnh về:

1. match giá trị
2. match operation
3. overlap input refs

Nó là heuristic score, nhưng được dùng trong global optimization chứ không greedy.

## 15. Global alignment: `global_align_student_steps`

Đây là lõi lớn nhất của tầng evidence.

Hàm:

- `global_align_student_steps(student, reference)`

### 15.1 Bước chuẩn bị

1. `student_payload = student_steps(student)`
2. `reference_payload = reference_steps(reference)`
3. build `score_matrix`

`score_matrix[i][j]` là điểm local giữa:

- student step `i`
- reference step `j`

### 15.2 Dynamic programming state

Code dùng memoized recursion:

- `_solve(student_index, used_mask)`

State gồm:

1. đang xét student step thứ mấy
2. những reference step nào đã dùng rồi

### 15.3 Nhánh unmatched

Ở mỗi student step, code luôn có option:

- bỏ unmatched

Cách tính:

1. gọi `_solve(student_index + 1, used_mask)`
2. trừ `1.25`

Đây là cost cố định cho việc không align được step học sinh này.

### 15.4 Nhánh match với từng reference step chưa dùng

Với mỗi `ref_index` chưa có trong `used_mask`:

1. lấy `local_score`
2. gọi tiếp `_solve(student_index + 1, used_mask | (1 << ref_index))`
3. cộng lại thành `candidate_score`
4. nếu tốt hơn best hiện tại -> cập nhật best

### 15.5 Kết quả của DP

Cuối cùng, `_solve(0, 0)` trả:

1. best score
2. tuple các cặp `(student_index, ref_index)`

Sau đó code build:

1. `student_to_reference`
2. `reverse_pair`
3. `inverse_reverse_pair`

Lưu ý:

- `inverse_reverse_pair` hiện được tạo nhưng không dùng tiếp

## 16. Gán relationship cho từng cặp align

Sau khi có pairing, code duyệt lại từng student step.

### 16.1 Nếu student step không được match

Tạo `StepAlignment` với:

1. `reference_step_id = None`
2. `matched_output_ref = None`
3. `score = 0.0`
4. `reasons = ["unmatched_in_global_alignment"]`
5. `relationship = "unsupported"`

### 16.2 Nếu có reference step match

Code tính lại:

1. `score, reasons = _local_match_score(...)`

Rồi tính dependency comparison.

## 17. Dependency comparison trong alignment

### 17.1 Map student dependencies sang canonical space

`mapped_student_deps` được tính bằng:

1. lấy từng `dep_step_id` trong `student_step.dependency_step_ids`
2. nếu `dep_step_id` có trong `reverse_pair`
   - map nó sang `reference_step_id`

Kết quả là một tập reference-step ids mà dependency học sinh “tương ứng” đến sau khi align.

### 17.2 So với dependency thật của canonical step

`reference_deps = set(reference_step.dependency_step_ids)`

Từ đó:

1. `dependency_overlap = mapped_student_deps ∩ reference_deps`
2. `missing_dependencies = reference_deps - mapped_student_deps`
3. `extra_dependencies = mapped_student_deps - reference_deps`

### 17.3 Gán `relationship`

Thứ tự rule:

1. mặc định `aligned`
2. nếu output value mismatch -> `value_mismatch`
3. else nếu operation mismatch và student op không UNKNOWN -> `value_match_operation_mismatch`
4. else nếu có missing/extra deps -> `dependency_mismatch`
5. nếu vẫn `aligned` nhưng `dependency_overlap` rỗng trong khi canonical có deps -> ép thành `dependency_mismatch`
6. nếu vẫn `aligned` nhưng `student_step.output_value is None` -> `ambiguous`

Kết quả là mỗi pair được gán một relationship label duy nhất.

## 18. Detect reorder-but-consistent

Hàm:

- `detect_reordered_but_consistent(student, reference, alignments)`

### 18.1 Điều kiện đầu

Nếu:

1. `student.normalized_final_answer` là `None`
2. hoặc final answer của student không match `reference.final_answer`

-> return `False`

### 18.2 Lọc các alignment “đủ tốt”

Chỉ giữ alignment có:

1. `reference_step_id is not None`
2. `relationship` thuộc:
   - `aligned`
   - `dependency_mismatch`

Nếu số lượng < 2:

- `False`

### 18.3 So thứ tự canonical indices

1. build `reference_index = {step.step_id: index}`
2. map các aligned items sang `aligned_order`

Nếu:

- `aligned_order != sorted(aligned_order)`

thì return `True`.

Ý nghĩa:

- student đang đi qua các canonical intermediate quantities đúng-ish nhưng theo thứ tự khác

## 19. Kiểm student graph có target path không

Hàm:

- `student_graph_has_target_path(student)`

### 19.1 Logic

Nếu:

1. `student.student_graph is None`
2. hoặc `graph.target_node_id is None`

-> `False`

Ngược lại:

1. duyệt edges
2. nếu có edge:
   - `edge.target_node_id == graph.target_node_id`
   - và `edge.edge_type == TARGETS_VALUE`

-> `True`

Tức là “target path present” hiện được định nghĩa rất hẹp:

- có ít nhất một edge `TARGETS_VALUE` đi vào target node

## 20. Suy student target ref: `infer_student_target_ref`

Hàm:

- `infer_student_target_ref(problem, reference, student)`

là nơi tầng evidence suy student đang “nhắm” quantity nào.

### 20.1 Rule 1: nếu student side đã có `selected_target_ref`

Nếu `student.selected_target_ref is not None`:

- trả luôn giá trị đó

### 20.2 Rule 2: nhìn target-link edges trong student graph

Nếu graph có target node:

1. lấy tất cả edges:
   - `edge.edge_type == TARGETS_VALUE`
   - `edge.target_node_id == graph.target_node_id`

2. build:
   - `visible_problem_refs`
   - `reference_output_refs`

3. với từng incoming edge:
   - nếu `source_ref == reference.chosen_plan.target_ref` -> return source_ref
   - nếu `source_ref in reference_output_refs` -> return source_ref
   - nếu `source_ref in visible_problem_refs` -> return source_ref

### 20.3 Nếu không infer được

- return `None`

### 20.4 Ý nghĩa

Numeric-collision fallback kiểu cũ đã bị bỏ.

Target inference ở evidence layer giờ dựa trên:

1. explicit selected target ref từ student formalizer
2. hoặc cấu trúc edge đi vào target node

## 21. Helper `_student_target_linked_output_step_id`

Builder còn có một helper riêng:

- `_student_target_linked_output_step_id(student)`

Mục đích:

1. tìm output node nào đang nối vào target node
2. lần ngược từ output node đó về operation node
3. lấy `step_id` của operation đó

### 21.1 Cơ chế

1. tìm edge `TARGETS_VALUE` vào target node mà source bắt đầu bằng `student_output_`
2. từ output node đó tìm edge `OUTPUT_FROM_OPERATION`
3. từ operation node lấy `step_id`

Kết quả:

- biết “step học sinh nào đang được graph target node trỏ vào”

Điều này dùng cho target misunderstanding evidence.

## 22. Helper `_unique_visible_problem_quantity`

Hàm:

- `_unique_visible_problem_quantity(problem, value)`

làm:

1. nếu `value is None` -> `None`
2. tìm mọi quantity trong `problem.quantities` có `values_match(quantity.value, value)`
3. nếu có đúng 1 match -> trả quantity đó
4. nếu 0 hoặc >1 -> `None`

Ý nghĩa:

- chỉ khi final answer đúng bằng **duy nhất một** visible problem quantity thì builder mới suy selected visible quantity

## 23. `alignment_map` trong `DiagnosisEvidence`

Builder không nhét raw dataclass `StepAlignment` trực tiếp.

Nó gọi:

- `_alignment_payload(alignments)`

để convert từng alignment thành dict JSON-like với:

1. `student_step_id`
2. `reference_step_id`
3. `matched_output_ref`
4. `score`
5. `relationship`
6. `reasons`
7. `dependency_overlap`
8. `missing_dependencies`
9. `extra_dependencies`

Đây là thứ được lưu vào `DiagnosisEvidence.alignment_map`.

## 24. Khởi tạo state trong `build_diagnosis_evidence`

Sau khi vượt qua unparseable gate, builder khởi tạo:

1. `evidence_items = []`
2. `mechanisms = []`
3. `notes = [f"student_mode={student.mode.value}"]`
4. `first_divergence_step_id = None`
5. `target_ref = reference.chosen_plan.target_ref`
6. `output_ref_to_step_id = _reference_output_to_step_id(reference)`
7. `inferred_target_ref = infer_student_target_ref(...)`
8. `alignments = global_align_student_steps(...)`
9. `alignment_map = _alignment_payload(alignments)`
10. `alignment_by_student_step_id`
11. `reordered_consistent`
12. `student_steps_by_id`
13. `edit_summary = graph_edit_summary(reference, alignments)`

Tức là mọi evidence item về sau đều được xây trên 3 trục:

1. final answer correctness
2. target inference
3. step alignment / graph edit summary

## 25. Graph target path evidence

Builder luôn xét graph target path trước.

### 25.1 Nếu có target path

Thêm `EvidenceItem`:

1. `evidence_type = "graph_target_path_present"`
2. mô tả có path vào student target node
3. confidence `0.72`

### 25.2 Nếu graph có mặt nhưng không có target path

Thêm:

1. `evidence_type = "graph_target_path_missing"`
2. confidence `0.78`

Điều đáng chú ý:

- nếu `student.student_graph is None`, builder không thêm hai loại item này

## 26. Final answer correctness evidence

Builder so:

- `student.normalized_final_answer`
- `reference.final_answer`

bằng `values_match(...)`.

### 26.1 Nếu match

Thêm item:

1. `evidence_type = "correct_final_answer"`
2. `reference_step_id = output_ref_to_step_id.get(target_ref)`
3. metadata có:
   - `student_final_answer`
4. confidence `0.98`

### 26.2 Nếu mismatch

Thêm item:

1. `evidence_type = "final_answer_mismatch"`
2. `reference_step_id = output_ref_to_step_id.get(target_ref)`
3. metadata có:
   - `student_final_answer`
   - `reference_final_answer`
4. confidence `0.9`

Và append mechanism:

- `final_answer_mismatch`

## 27. Target evidence khi `infer_student_target_ref(...)` suy ra được ref

Nếu `inferred_target_ref is not None`, builder vào nhánh explicit target inference.

### 27.1 Nếu inferred target đúng bằng canonical target

Thêm:

1. `evidence_type = "target_ref_match"`
2. `reference_step_id = output_ref_to_step_id.get(target_ref)`
3. metadata có `selected_target_ref`
4. confidence `0.88`

### 27.2 Nếu inferred target là canonical intermediate output

Nếu `inferred_target_ref in output_ref_to_step_id`:

1. `matched_step_id = output_ref_to_step_id[inferred_target_ref]`
2. thêm item:
   - `evidence_type = "selected_intermediate_reference"`
   - confidence `0.94`
   - `reference_step_id = matched_step_id`
   - metadata có `selected_target_ref`
3. append mechanism:
   - `selected_intermediate_target`
4. nếu `first_divergence_step_id is None`
   - set bằng `matched_step_id`

### 27.3 Nếu inferred target là visible problem quantity

Nếu `inferred_target_ref` khớp một quantity trong `problem.quantities`:

1. thêm item:
   - `evidence_type = "selected_visible_problem_quantity"`
   - confidence `0.9`
   - `quantity_ids = [quantity.quantity_id]`
   - metadata có:
     - `selected_target_ref`
     - `quantity_value`
2. append mechanism:
   - `selected_visible_quantity_as_answer`

## 28. Target evidence khi `infer_student_target_ref(...)` trả `None`

Đây là nhánh structural fallback.

### 28.1 Nếu target node nối từ student output step

Code lấy:

- `linked_output_step_id = _student_target_linked_output_step_id(student)`

Nếu có:

1. tìm `linked_alignment = alignment_by_student_step_id.get(linked_output_step_id)`
2. nếu alignment đó có `reference_step_id`
3. lấy `matched_reference_output = linked_alignment.matched_output_ref`

Nếu `matched_reference_output`:

1. khác `target_ref`
2. và không rỗng

thì builder tạo item:

1. `evidence_type = "selected_intermediate_reference"`
2. confidence `0.92`
3. `reference_step_id = linked_alignment.reference_step_id`
4. `student_step_id = linked_output_step_id`
5. metadata có `matched_output_ref`

Và append:

1. mechanism `selected_intermediate_target`
2. `first_divergence_step_id` nếu chưa có

### 28.2 Nếu không có linked output step

Builder thử:

- `_unique_visible_problem_quantity(problem, student.normalized_final_answer)`

Nếu match đúng một visible quantity:

1. thêm item:
   - `evidence_type = "selected_visible_problem_quantity"`
   - confidence `0.82`
   - metadata có:
     - `selected_target_ref`
     - `quantity_value`
2. append mechanism:
   - `selected_visible_quantity_as_answer`

## 29. Reorder-but-consistent evidence

Nếu `reordered_consistent` là `True`, builder thêm item:

1. `evidence_type = "reordered_but_consistent_steps"`
2. confidence `0.87`
3. metadata có `alignment_map_size`

Điều này không tự thêm mechanism riêng.

Nó là một structural signal bổ sung.

## 30. Graph edit summary evidence

Builder luôn thêm một item:

1. `evidence_type = "graph_edit_distance"`
2. confidence `0.76`
3. metadata chứa:
   - `node_substitutions`
   - `node_deletions`
   - `node_insertions`
   - `edge_substitutions`
   - `edge_deletions`
   - `edge_insertions`
   - `total_cost`

Điều này đúng ngay cả khi alignment còn yếu.

## 31. `graph_edit_summary(...)` tính gì

Hàm:

- `graph_edit_summary(reference, alignments)`

### 31.1 Các thành phần node

1. `node_substitutions`
   - số alignment mà:
     - có reference step
     - relationship thuộc:
       - `value_mismatch`
       - `value_match_operation_mismatch`
       - `dependency_mismatch`

2. `node_insertions`
   - số student step không match reference step nào

3. `node_deletions`
   - số reference step không được align bởi student step nào

### 31.2 Các thành phần edge

Với mỗi aligned item:

1. `edge_substitutions += len(missing_dependencies) + len(extra_dependencies)`
2. `edge_deletions += len(missing_dependencies)`
3. `edge_insertions += len(extra_dependencies)`

### 31.3 `total_cost`

```python
node_substitutions + node_insertions + node_deletions + edge_substitutions
```

Đây không phải graph edit distance tối ưu theo thuật toán GED tổng quát.

Nó là summary cost được suy từ alignment hiện có.

## 32. Step-level evidence từ alignment map

Sau khi builder đã có `alignment_map`, nó duyệt từng item trong map để sinh evidence items.

## 33. Case `reference_step_id is None`

Nếu student step không được align với canonical step nào:

### 33.1 Special-case `restated_final_answer`

Builder nhìn `student_step` thật từ `student_steps_by_id`.

Nếu:

1. step tồn tại
2. `step.operation == DERIVE`
3. `step.extracted_value` match `student.normalized_final_answer`

thì emit:

1. `evidence_type = "restated_final_answer"`
2. confidence `0.72`
3. metadata có:
   - `reasons`
   - `score`

và `continue`.

### 33.2 Nếu không phải restatement

Emit:

1. `evidence_type = "unsupported_student_step"`
2. confidence `0.7`
3. `student_step_id`
4. metadata có:
   - `reasons`
   - `score`

append mechanism:

- `unsupported_step`

## 34. Case `relationship == aligned`

Emit:

1. `evidence_type = "step_value_match"`
2. confidence `0.78`
3. `reference_step_id`
4. `student_step_id`
5. metadata có:
   - `matched_output_ref`
   - `reasons`

Nhánh này không thêm mechanism.

## 35. Case `relationship == dependency_mismatch`

Builder emit **hai** evidence items.

### 35.1 Item 1: dependency mismatch

1. `evidence_type = "dependency_mismatch"`
2. confidence `0.86`
3. metadata có:
   - `matched_output_ref`
   - `dependency_overlap`
   - `missing_dependencies`
   - `extra_dependencies`

### 35.2 Item 2: edge-level divergence

1. `evidence_type = "edge_level_divergence"`
2. confidence `0.84`
3. metadata có:
   - `missing_dependencies`
   - `extra_dependencies`

### 35.3 Side effects

1. append mechanism `dependency_mismatch` nếu chưa có
2. set `first_divergence_step_id` nếu chưa có

## 36. Case `relationship == value_match_operation_mismatch`

### 36.1 Special-case restated final answer

Nếu:

1. student step tồn tại
2. `student_step.operation == DERIVE`
3. `matched_output_ref == target_ref`
4. `student.normalized_final_answer` match `reference.final_answer`

thì emit:

1. `evidence_type = "restated_final_answer"`
2. confidence `0.72`
3. metadata có `reasons`

### 36.2 Nếu không phải restatement

Emit:

1. `evidence_type = "operation_mismatch"`
2. confidence `0.82`
3. metadata có:
   - `matched_output_ref`
   - `reasons`

append mechanism:

- `operation_mismatch`

và set `first_divergence_step_id` nếu chưa có.

## 37. Case `relationship == value_mismatch`

Emit:

1. `evidence_type = "step_value_mismatch"`
2. confidence `0.84`
3. metadata có:
   - `matched_output_ref`
   - `reasons`

append mechanism:

- `arithmetic_mismatch`

và set `first_divergence_step_id` nếu chưa có.

## 38. Missing reference steps evidence

Sau khi duyệt alignment map, builder tính:

1. `reference_step_ids`
2. `matched_reference_step_ids`

### 38.1 Nếu final answer đúng

Nếu student final answer đúng mà vẫn thiếu reference steps:

1. builder **không** emit `missing_reference_steps`
2. nếu không reorder-consistent thì chỉ append note:
   - `correct_final_answer_with_partial_process_coverage`

Điều này phản ánh:

- final answer đúng thì missing process coverage chưa chắc là lỗi cần phạt nặng

### 38.2 Nếu final answer sai

Nếu có `missing_reference_step_ids`:

emit:

1. `evidence_type = "missing_reference_steps"`
2. confidence `0.74`
3. metadata có `missing_reference_step_ids`

append mechanism:

- `missing_step`

và nếu chưa có divergence thì lấy step id đầu tiên bị thiếu làm `first_divergence_step_id`.

## 39. `graph_edit_distance_nonzero` mechanism

Nếu:

1. `edit_summary.total_cost > 0`
2. và `not reordered_consistent`
3. và mechanism này chưa có

thì append:

- `graph_edit_distance_nonzero`

Lưu ý:

- đây chỉ là mechanism summary
- không tạo `EvidenceItem` riêng

## 40. `target_correct_but_value_wrong`

Builder có một rule hậu kỳ rất quan trọng:

Nếu:

1. final answer của student **không** match reference
2. `inferred_target_ref == target_ref`
3. chưa có mechanism `arithmetic_mismatch`
4. chưa có mechanism `selected_intermediate_target`

thì emit:

1. `evidence_type = "target_correct_but_value_wrong"`
2. confidence `0.82`
3. `reference_step_id = output_ref_to_step_id.get(target_ref)`
4. metadata có `student_final_answer`

Và append:

- `arithmetic_mismatch`

Đồng thời set `first_divergence_step_id` nếu chưa có.

Ý nghĩa:

- student dường như nhắm đúng target cuối
- nhưng ra sai giá trị số

## 41. Fallback khi không có evidence items nào

Nếu toàn bộ logic ở trên không tạo được item nào:

builder thêm:

1. `evidence_type = "insufficient_alignment_signal"`
2. confidence `0.3`

và note:

- `insufficient_alignment_signal`

## 42. Confidence của `DiagnosisEvidence`

Builder tính:

```python
confidence = min(
    0.25 + sum(item.confidence for item in evidence_items) / max(len(evidence_items), 1) * 0.75,
    0.97,
)
```

Tức là:

1. lấy mean confidence của evidence items
2. scale bởi `0.75`
3. cộng base `0.25`
4. cap ở `0.97`

### 42.1 Ý nghĩa

Đây không phải Bayesian confidence hay calibrated score.

Nó là aggregate heuristic confidence của evidence bundle.

## 43. Kết cấu cuối của `DiagnosisEvidence`

Builder return:

1. `evidence_items`
2. `alignment_map`
3. `first_divergence_step_id`
4. `likely_error_mechanisms`
5. `confidence`
6. `notes`

`notes` hiện tối thiểu luôn có:

- `student_mode=<...>`

và có thể thêm các notes như:

1. `correct_final_answer_with_partial_process_coverage`
2. `insufficient_alignment_signal`

## 44. Cơ chế lõi thật sự của tầng evidence

Nếu nén đúng bản chất của code hiện tại:

1. reference được chiếu thành step payload có output value và dependencies
2. student được chiếu thành step payload có graph-enriched dependencies
3. DP global alignment gán 1-1 giữa student steps và reference steps
4. target misunderstanding được suy bằng selected target ref hoặc target-link edges
5. alignment map được convert thành evidence items và mechanism list
6. first divergence được lấy từ target/intermediate mismatch hoặc step mismatch đầu tiên

## 45. Kết luận đúng với code hiện tại

Nếu phải mô tả thật ngắn nhưng chính xác:

- Tầng evidence hiện là một lớp graph-aware alignment và evidence synthesis: nó chuẩn hóa canonical/student process về step payloads, giải bài toán global alignment, suy target misunderstanding từ cấu trúc graph, rồi tổng hợp thành `DiagnosisEvidence` có thể dùng cho diagnosis layer.

Nếu nén thành 5 khâu:

1. payload projection
2. global alignment
3. target inference
4. evidence item synthesis
5. divergence/mechanism aggregation

Đó là cơ chế lõi hiện tại của `05_evidence`.

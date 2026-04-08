# Cơ Chế Lõi Của Diagnosis

Tài liệu này mô tả đúng tầng diagnosis hiện tại, bám trực tiếp vào code trong:

- `src/diagnosis/scoring.py`
- `src/diagnosis/engine.py`
- các enum/schema liên quan trong:
  - `src/models/schemas.py`
  - `src/models/formalizer_schemas.py`

Tầng này nhận đầu vào là:

- `DiagnosisEvidence`

và đầu ra là:

- `DiagnosisResult`

Điểm rất quan trọng:

- diagnosis layer **không đọc raw student text**
- không đọc lại problem text
- không làm alignment
- không xây evidence mới

Nó chỉ:

1. đọc `DiagnosisEvidence`
2. chấm các diagnosis hypotheses
3. chọn hypothesis tốt nhất theo deterministic scoring
4. tùy chọn cho LLM critique / refine kết quả đó

## 1. Taxonomy của diagnosis

Diagnosis hiện dùng 2 enum nền:

### 1.1 `DiagnosisLabel`

Nằm trong `src/models/schemas.py`, gồm:

1. `correct_answer`
2. `arithmetic_error`
3. `quantity_relation_error`
4. `target_misunderstanding`
5. `unparseable_answer`
6. `unknown_error`

Đây là taxonomy chính mà engine được phép chọn.

### 1.2 `ErrorLocalization`

Gồm:

1. `none`
2. `final_computation`
3. `intermediate_step`
4. `combining_quantities`
5. `target_selection`
6. `unknown`

Enum này nói:

- lỗi đang được localize ở đâu trong tiến trình giải

## 2. Contract đầu ra: `DiagnosisResult`

Schema `DiagnosisResult` có:

1. `diagnosis_label`
2. `subtype`
3. `localization`
4. `target_step_id`
5. `summary`
6. `supporting_evidence_types`
7. `confidence`
8. `notes`

Invariant:

1. `summary` không được rỗng

Điểm cần nắm:

- diagnosis không chỉ là một label
- nó còn phải trả:
  - subtype cụ thể
  - localization
  - step divergence nếu có
  - evidence types nào đang support cho chẩn đoán
  - confidence

## 3. Entry point công khai của diagnosis

Trong `src/diagnosis/__init__.py`, package chỉ export:

- `diagnose`

Hàm thật nằm trong `src/diagnosis/engine.py`:

- `diagnose(evidence, llm_client=None)`

### 3.1 Trình tự tổng quát

Hàm này chạy theo đúng thứ tự:

1. `deterministic_result, hypotheses = _deterministic_diagnosis(evidence)`
2. nếu `llm_client is None` -> trả `deterministic_result`
3. nếu có `llm_client` -> thử `_llm_diagnose(...)`
4. nếu LLM fail hoặc output mâu thuẫn với guardrail -> fallback về deterministic result

Tức là diagnosis hiện là:

- deterministic-first
- LLM-second

## 4. Internal representation: `DiagnosisHypothesis`

Trong `scoring.py`, diagnosis engine không chấm trực tiếp ra `DiagnosisResult`.

Nó tạo một dataclass trung gian:

- `DiagnosisHypothesis`

gồm:

1. `label`
2. `subtype`
3. `localization`
4. `summary`
5. `score`
6. `supporting_evidence_types`
7. `rationale`

### 4.1 Vai trò của `DiagnosisHypothesis`

Hypothesis là representation nội bộ của tầng scoring.

Nó cho phép hệ:

1. chấm nhiều diagnosis label song song
2. so sánh score giữa các label
3. giữ rationale dạng machine-readable
4. chỉ đến cuối mới convert hypothesis thắng thành `DiagnosisResult`

## 5. Helper cơ bản trong `scoring.py`

Scoring dùng vài helper nhỏ:

### 5.1 `_evidence_types(evidence)`

Trả:

- `[item.evidence_type for item in evidence.evidence_items]`

Tức là flatten evidence items thành list type strings.

### 5.2 `_item_by_type(evidence, evidence_type)`

Trả item đầu tiên có đúng `evidence_type`, nếu có.

### 5.3 `_has_type(evidence, evidence_type)`

Check có ít nhất một item type đó không.

Lưu ý:

- trong code hiện tại `_has_type(...)` đang tồn tại nhưng không dùng ở phần scoring bên dưới

### 5.4 `_graph_edit_cost(evidence)`

Lấy `EvidenceItem` có type `graph_edit_distance`.

Nếu có:

- trả `int(item.metadata.get("total_cost", 0))`

Nếu không:

- `0`

### 5.5 `_alignment_relationship_counts(evidence)`

Duyệt `evidence.alignment_map` và đếm:

- mỗi `relationship` xuất hiện bao nhiêu lần

Kết quả là:

- `dict[str, int]`

Helper này chỉ được dùng cho `quantity_relation_error`.

## 6. Hypothesis 1: `_score_correct_answer`

Đây là hypothesis cho:

- `DiagnosisLabel.CORRECT_ANSWER`

### 6.1 Mục tiêu của scorer này

Scorer này không chỉ hỏi:

- final answer có đúng không

Nó còn hỏi:

- process có đủ sạch để vẫn coi là đúng không

Đó là điểm thay đổi quan trọng của version hiện tại.

### 6.2 Positive signals

Nếu `evidence_types` có:

#### `correct_final_answer`

1. `score += 6.5`
2. rationale append `correct_final_answer`

#### `target_ref_match`

1. `score += 1.5`
2. rationale append `target_ref_match`

#### `reordered_but_consistent_steps`

1. `score += 2.0`
2. rationale append `reordered_but_consistent_steps`

#### `graph_target_path_present`

1. `score += 0.5`
2. rationale append `graph_target_path_present`

#### `restated_final_answer`

1. `score += 0.4`
2. rationale append `restated_final_answer`

#### graph edit cost thấp

Nếu:

1. `edit_cost > 0`
2. và có `correct_final_answer`

thì:

```python
score += max(0.0, 1.0 - min(edit_cost / 10.0, 1.0))
```

và append rationale:

- `graph_edit_cost=<cost>`

Nghĩa là:

- final answer đúng và edit cost nhỏ thì hypothesis correct được thưởng thêm

### 6.3 Negative signals

Nếu có:

#### `final_answer_mismatch`

- `score -= 6.0`

#### target misunderstanding evidence

Nếu có:

1. `selected_intermediate_reference`
2. hoặc `selected_visible_problem_quantity`

thì:

- `score -= 8.0`

#### `operation_mismatch`

- nếu có `correct_final_answer`:
  - `score -= 5.0`
- nếu không:
  - `score -= 3.0`

#### `dependency_mismatch`

- nếu có `correct_final_answer`:
  - `score -= 4.0`
- nếu không:
  - `score -= 2.5`

#### `unsupported_student_step`

- nếu có `correct_final_answer`:
  - `score -= 2.5`
- nếu không:
  - `score -= 1.5`

#### `step_value_mismatch`

- nếu có `correct_final_answer`:
  - `score -= 3.5`
- nếu không:
  - `score -= 2.0`

#### edit cost lớn

Nếu `edit_cost > 2`:

```python
score -= min(edit_cost / 3.0, 3.0)
```

### 6.4 Subtype và summary

Nếu có `reordered_but_consistent_steps`:

1. `subtype = "equivalent_reordered_process"`
2. summary nói final answer đúng và process vẫn consistent dù thứ tự khác

Ngược lại:

1. `subtype = "matches_canonical_reference"`
2. summary nói final answer match reference

### 6.5 Điểm quan trọng

Version hiện tại **không còn** luật cứng:

- final answer đúng => bắt buộc diagnosis là `correct_answer`

`correct_answer` bây giờ chỉ là một hypothesis được chấm cao nếu evidence ủng hộ.

## 7. Hypothesis 2: `_score_unparseable_answer`

Scorer cho:

- `DiagnosisLabel.UNPARSEABLE_ANSWER`

### 7.1 Logic

Nếu `evidence_types` có `unparseable_answer`:

- `score = 10.0`

Ngược lại:

- `score = 0.0`

### 7.2 Output cố định

1. `subtype = "answer_not_numeric"`
2. `localization = UNKNOWN`
3. summary:
   - không normalize được thành target số usable

### 7.3 Ý nghĩa

Đây là hypothesis có scoring gần như hard gate.

Nếu evidence layer nói unparseable rõ ràng:

- diagnosis này gần như luôn thắng

## 8. Hypothesis 3: `_score_target_misunderstanding`

Scorer cho:

- `DiagnosisLabel.TARGET_MISUNDERSTANDING`

### 8.1 Default state

Ban đầu:

1. `score = 0.0`
2. `subtype = "target_selection_ambiguous"`
3. summary:
   - student dường như nhắm quantity khác target yêu cầu

### 8.2 `selected_intermediate_reference`

Nếu có evidence type này:

1. `score += 8.0`
2. rationale append `selected_intermediate_reference`
3. `subtype = "selected_intermediate_quantity"`
4. summary:
   - student dừng ở intermediate quantity thay vì target cuối

### 8.3 `selected_visible_problem_quantity`

Nếu có evidence type này:

1. `score += 8.0`
2. rationale append `selected_visible_problem_quantity`
3. `subtype = "selected_visible_problem_quantity"`
4. summary:
   - student trả về một quantity xuất hiện trong problem thay vì target yêu cầu

### 8.4 `final_answer_mismatch`

Nếu có:

1. `score += 1.0`
2. rationale append `final_answer_mismatch`

### 8.5 `target_ref_match`

Nếu có:

- `score -= 4.0`

Điều này phản ánh:

- nếu evidence đã nói student target đúng target canonical
- hypothesis target misunderstanding phải bị phạt mạnh

### 8.6 Supporting evidence types

Scorer set:

```python
[item for item in evidence_types if "target" in item or "selected_" in item]
```

Tức là mọi evidence type liên quan tới target / selected ref đều có thể được show như support.

## 9. Hypothesis 4: `_score_arithmetic_error`

Scorer cho:

- `DiagnosisLabel.ARITHMETIC_ERROR`

### 9.1 Positive signals

#### `step_value_mismatch`

1. `score += 5.0`
2. rationale append `step_value_mismatch`

#### `target_correct_but_value_wrong`

1. `score += 4.0`
2. rationale append `target_correct_but_value_wrong`

#### `final_answer_mismatch + target_ref_match`

Nếu có cả hai:

1. `score += 2.0`
2. rationale append `final_answer_mismatch+target_ref_match`

Ý nghĩa:

- nếu student nhắm đúng target nhưng final answer sai
- arithmetic error được boost

### 9.2 Negative signals

#### target misunderstanding evidence

Nếu có:

1. `selected_intermediate_reference`
2. hoặc `selected_visible_problem_quantity`

-> `score -= 4.0`

#### `operation_mismatch`

- `score -= 2.0`

#### `dependency_mismatch`

- `score -= 1.5`

#### `correct_final_answer`

- `score -= 6.0`

### 9.3 Subtype

Nếu có `step_value_mismatch`:

1. `subtype = "intermediate_calculation_error"`

Ngược lại:

1. `subtype = "final_computation_error"`

### 9.4 Localization

Nếu subtype là `intermediate_calculation_error` và:

- `evidence.first_divergence_step_id is not None`

thì:

- `localization = INTERMEDIATE_STEP`

Ngược lại:

- `localization = FINAL_COMPUTATION`

### 9.5 Summary

Hai variant summary:

1. intermediate calculation error
2. target đúng nhưng kết quả số cuối sai

## 10. Hypothesis 5: `_score_quantity_relation_error`

Scorer cho:

- `DiagnosisLabel.QUANTITY_RELATION_ERROR`

Đây là hypothesis quan trọng nhất cho các lỗi process/structure.

### 10.1 Default state

Ban đầu:

1. `score = 0.0`
2. `subtype = "wrong_operation_or_relationship"`
3. summary:
   - student kết hợp quantities bằng relation / operation sai

### 10.2 `operation_mismatch`

Nếu có:

1. `score += 5.0`
2. rationale append `operation_mismatch`

### 10.3 `dependency_mismatch`

Nếu có:

1. `score += 4.5`
2. rationale append `dependency_mismatch`
3. đổi:
   - `subtype = "missing_dependency_or_relationship"`
   - summary nói dependency structure bị sai

### 10.4 `edge_level_divergence`

Nếu có:

1. `score += 2.0`
2. rationale append `edge_level_divergence`

### 10.5 `unsupported_student_step`

Nếu có:

- nếu `correct_final_answer` cũng có:
  - `score += 2.0`
- nếu không:
  - `score += 1.5`

và append rationale `unsupported_student_step`

### 10.6 Alignment relationship count

Nếu `align_counts.get("dependency_mismatch", 0) > 0`:

1. `score += 0.5`
2. rationale append `alignment_dependency_mismatch`

### 10.7 Negative signals

#### target misunderstanding evidence

Nếu có:

1. `selected_intermediate_reference`
2. hoặc `selected_visible_problem_quantity`

-> `score -= 3.0`

#### correct final answer

Nếu có `correct_final_answer`, code phân biệt 2 nhánh:

##### Nhánh 1: reordered but consistent

Nếu có `reordered_but_consistent_steps`:

- `score -= 5.0`

Điều này chặn việc reorder lành tính bị chẩn đoán thành relation error.

##### Nhánh 2: final đúng nhưng process không consistent

Nếu có ít nhất một trong:

1. `operation_mismatch`
2. `dependency_mismatch`
3. `unsupported_student_step`

thì:

1. `score += 3.0`
2. `subtype = "process_inconsistent_but_final_correct"`
3. summary:
   - final answer đúng nhưng process recorded không consistent với canonical quantity relationships

### 10.8 Điểm rất quan trọng

Đây là chỗ code hiện tại cho phép biểu diễn:

- đúng đáp án nhưng sai process

Nó không còn ép các case final đúng phải rơi vào `correct_answer`.

## 11. Hypothesis 6: `_score_unknown_error`

Scorer cho:

- `DiagnosisLabel.UNKNOWN_ERROR`

### 11.1 Base score

Ban đầu:

1. `score = 1.0`
2. rationale = `["fallback_unknown"]`

### 11.2 Nếu có final answer mismatch

1. `score += 1.5`
2. rationale append `final_answer_mismatch`

### 11.3 Nếu graph edit cost > 0

Nếu:

1. có evidence type `graph_edit_distance`
2. và `_graph_edit_cost(evidence) > 0`

thì:

1. `score += 1.0`
2. rationale append `graph_edit_distance_nonzero`

### 11.4 Ý nghĩa

`unknown_error` là fallback hypothesis:

- mismatch có thật
- nhưng evidence chưa đủ sắc để đẩy một mechanism cụ thể lên cao hơn

## 12. Tạo toàn bộ hypothesis leaderboard

Hàm:

- `build_diagnosis_hypotheses(evidence)`

chỉ làm:

1. build 6 hypothesis bằng 6 scorer trên
2. `sorted(..., key=lambda item: item.score, reverse=True)`

Tức là engine deterministic hiện là:

- score tất cả
- sort theo score giảm dần

Không có threshold gating riêng theo label.

## 13. Convert hypothesis thắng thành `DiagnosisResult`

Hàm:

- `_build_result_from_hypothesis(hypothesis, evidence, extra_notes=None)`

đây là chỗ convert representation nội bộ sang schema public.

### 13.1 `notes`

Notes được build từ:

1. `list(evidence.notes)`
2. thêm:
   - `diagnosis_rationale:<reason>`
   cho mỗi reason trong `hypothesis.rationale`
3. thêm `extra_notes` nếu có

### 13.2 `confidence`

Code tính:

```python
confidence = min(max(evidence.confidence + min(hypothesis.score / 20.0, 0.12), 0.35), 0.98)
```

Nghĩa là:

1. lấy `evidence.confidence`
2. cộng một bonus theo `hypothesis.score / 20`
3. bonus bị cap ở `0.12`
4. confidence cuối được clamp vào `[0.35, 0.98]`

### 13.3 Các field còn lại

`DiagnosisResult` nhận:

1. `diagnosis_label = hypothesis.label`
2. `subtype`
3. `localization`
4. `target_step_id = evidence.first_divergence_step_id`
5. `summary = hypothesis.summary`
6. `supporting_evidence_types`
7. `confidence`
8. `notes`

Điểm đáng chú ý:

- `target_step_id` của diagnosis hiện luôn đến từ `evidence.first_divergence_step_id`
- diagnosis layer không tự locate lại divergence step

## 14. Deterministic selector: `_deterministic_diagnosis`

Hàm:

- `_deterministic_diagnosis(evidence)`

### 14.1 Trình tự

1. `hypotheses = build_diagnosis_hypotheses(evidence)`
2. `best = hypotheses[0]`
3. `runner_up = hypotheses[1]` nếu có

### 14.2 Ghi notes về leaderboard

`extra_notes` luôn có:

1. `diagnosis_top_hypothesis=<label>:<score>`

Nếu có runner-up:

1. `diagnosis_runner_up=<label>:<score>`
2. `diagnosis_margin=<margin>`

### 14.3 Ambiguity handling

Nếu:

1. `margin < 1.0`
2. và `best.label != CORRECT_ANSWER`

thì append:

1. `diagnosis_ambiguous_competing_hypotheses`

Ngoài ra, nếu:

1. `best.label == UNKNOWN_ERROR`

thì thêm:

1. `diagnosis_low_separation_unknown`

### 14.4 Kết quả

Hàm trả:

1. `DiagnosisResult` từ best hypothesis
2. toàn bộ `hypotheses` leaderboard

## 15. Vai trò của LLM trong diagnosis

LLM diagnosis không thay thế deterministic scoring.

Nó chỉ là tầng critique/refinement ở trên deterministic baseline.

Hàm:

- `_llm_diagnose(evidence, deterministic_result, hypotheses, llm_client)`

## 16. Prompt LLM diagnosis được build ra sao

### 16.1 System prompt

System prompt nói rõ:

1. model là `diagnosis critic`
2. phải trả `DiagnosisResult` JSON
3. phải grounded vào:
   - structured evidence
   - hypothesis leaderboard
4. không được invent evidence
5. nên ưu tiên một trong các hypothesis labels/subtypes đã có
   - trừ khi leaderboard rõ ràng inconsistent

### 16.2 Leaderboard đưa cho model gồm gì

Engine chỉ đưa top 4 hypotheses đầu tiên, mỗi hypothesis gồm:

1. `diagnosis_label`
2. `subtype`
3. `localization`
4. `score`
5. `summary`
6. `rationale`
7. `supporting_evidence_types`

### 16.3 User prompt chứa gì

1. allowed `diagnosis_label` values
2. allowed `localization` values
3. toàn bộ `DiagnosisEvidence` ở dạng JSON
4. deterministic baseline diagnosis ở dạng JSON
5. hypothesis leaderboard ở dạng JSON

Cuối prompt yêu cầu:

- trả refined `DiagnosisResult`
- `supporting_evidence_types` phải aligned với evidence

## 17. Cách engine gọi model

Code gọi:

```python
payload = llm_client.generate_json(
    task_name="diagnosis",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.1,
    max_tokens=1200,
)
```

Sau đó:

1. nếu payload chưa có `supporting_evidence_types`
   - set default bằng `_evidence_types(evidence)`
2. append note:
   - `llm_diagnosis_used`
3. validate bằng `DiagnosisResult.model_validate(payload)`

## 18. Guardrails của LLM diagnosis

Sau khi validate ra `llm_result`, engine chạy 2 guardrail logic.

### 18.1 Guardrail unparseable

Nếu `evidence_types` có `unparseable_answer`, nhưng:

- `llm_result.diagnosis_label != UNPARSEABLE_ANSWER`

thì:

- raise `ValueError("LLM diagnosis conflicts with unparseable_answer evidence")`

### 18.2 Guardrail target-selection evidence

Nếu evidence có:

1. `selected_intermediate_reference`
2. hoặc `selected_visible_problem_quantity`

nhưng:

- `llm_result.diagnosis_label != TARGET_MISUNDERSTANDING`

thì:

- raise `ValueError("LLM diagnosis conflicts with target-selection evidence")`

### 18.3 Điều đã bị bỏ

Version hiện tại **đã bỏ** guardrail cũ kiểu:

- `correct_final_answer => correct_answer`

Đó là lý do engine giờ cho phép:

- final answer đúng nhưng diagnosis vẫn là `quantity_relation_error`

nếu evidence process inconsistency đủ mạnh.

## 19. Fallback khi LLM diagnosis fail

Trong `diagnose(...)`, nếu `_llm_diagnose(...)` ném:

1. `LLMGenerationError`
2. `ValueError`
3. `TypeError`

thì engine:

1. copy `deterministic_result.notes`
2. append `llm_diagnosis_failed_fallback`
3. return deterministic result

Tức là deterministic diagnosis luôn là baseline an toàn.

## 20. Những gì diagnosis layer không làm

Diagnosis layer hiện **không**:

1. rebuild evidence
2. sửa alignment
3. suy target ref mới
4. đọc raw student text
5. chạy execution plan

Mọi thứ nó dùng đều đến từ:

- `DiagnosisEvidence`

Điều này làm diagnosis layer hiện khá “sạch vai trò”.

## 21. Chỗ nào logic lõi của diagnosis đang nằm

Nếu nhìn đúng vào code, lõi của diagnosis hiện nằm ở 3 chỗ:

### 21.1 `scoring.py`

Đây là nơi ontology diagnosis được encode thành logic chấm điểm.

Nó quyết định:

1. evidence type nào đẩy hypothesis nào
2. evidence type nào phạt hypothesis nào
3. subtype và localization của từng label

### 21.2 `_deterministic_diagnosis`

Đây là nơi:

1. sort leaderboard
2. chọn hypothesis thắng
3. ghi meta-information về margin / ambiguity

### 21.3 `_llm_diagnose`

Đây là nơi:

1. cho model xem evidence + baseline + leaderboard
2. nhưng vẫn đặt guardrails không được mâu thuẫn với evidence cứng

## 22. Diễn giải ngắn theo từng label

Nếu nén logic hiện tại thành intuition:

### `correct_answer`

Thắng khi:

1. final answer đúng
2. target đúng
3. process không có divergence mạnh

### `unparseable_answer`

Thắng gần như tuyệt đối khi evidence đã nói unparseable.

### `target_misunderstanding`

Thắng khi:

1. student rõ ràng chọn intermediate quantity
2. hoặc chọn visible problem quantity thay vì target

### `arithmetic_error`

Thắng khi:

1. target dường như đúng
2. nhưng value ở intermediate/final bị sai

### `quantity_relation_error`

Thắng khi:

1. operation/dependency structure lệch
2. kể cả trong case final answer đúng nhưng process sai

### `unknown_error`

Thắng khi:

1. mismatch có thật
2. nhưng evidence không đủ sắc để quy về một mechanism cụ thể

## 23. Kết luận đúng với code hiện tại

Nếu phải mô tả thật ngắn nhưng chính xác:

- Tầng diagnosis hiện là một hypothesis scorer trên `DiagnosisEvidence`: nó chấm 6 nhãn diagnosis song song, chọn hypothesis thắng theo deterministic margin-aware scoring, rồi tùy chọn cho LLM critique kết quả đó dưới các guardrail không được mâu thuẫn với evidence cứng.

Nếu nén thành 4 khâu:

1. hypothesis scoring
2. leaderboard ranking
3. deterministic result build
4. optional LLM critique with guardrails

Đó là cơ chế lõi hiện tại của `06_diagnosis`.

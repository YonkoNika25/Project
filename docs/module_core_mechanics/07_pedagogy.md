# Cơ Chế Lõi Của Pedagogy Planner

Tài liệu này mô tả đúng tầng pedagogy planner hiện tại, bám trực tiếp vào code trong:

- `src/pedagogy/planner.py`
- các enum/schema liên quan trong:
  - `src/models/schemas.py`
  - `src/models/formalizer_schemas.py`

Tầng này nhận đầu vào là:

1. `problem: FormalizedProblem`
2. `reference: CanonicalReference`
3. `diagnosis: DiagnosisResult`

và đầu ra là:

- `HintPlan`

Vai trò của tầng này là:

1. đọc diagnosis đã chốt
2. quyết định teacher move
3. chọn hint level
4. chọn target step
5. chọn disclosure budget
6. chọn focus points
7. tạo danh sách `must_not_reveal`

Điểm rất quan trọng:

- pedagogy planner hiện là **deterministic**
- không gọi model
- không generate hint text
- nó chỉ sinh ra **kế hoạch sư phạm có cấu trúc**

## 1. Contract của `HintPlan`

Schema `HintPlan` nằm trong `src/models/formalizer_schemas.py`.

Các field:

1. `diagnosis_label`
2. `hint_level`
3. `teacher_move`
4. `target_step_id`
5. `disclosure_budget`
6. `focus_points`
7. `must_not_reveal`
8. `rationale`
9. `confidence`

### 1.1 Invariant

Model validator hiện chỉ kiểm một rule:

Nếu:

- `disclosure_budget == 0`

thì:

- `focus_points` phải rỗng

Nghĩa là planner không được tạo “nội dung cần dạy” nếu budget disclosure bằng 0.

## 2. Taxonomy sư phạm mà planner dùng

### 2.1 `HintLevel`

Từ `src/models/schemas.py`, gồm:

1. `conceptual`
2. `relational`
3. `next_step`

Ý nghĩa hiện tại trong planner:

1. `conceptual`
   - định hướng lại mục tiêu / cách trình bày / cách nghĩ
2. `relational`
   - kiểm tra quan hệ giữa các quantity
3. `next_step`
   - gợi ý tính bước tiếp theo / tính lại phép tính

### 2.2 `TeacherMove`

Từ `src/models/formalizer_schemas.py`, gồm:

1. `refocus_target`
2. `check_relationship`
3. `recompute_step`
4. `continue_from_step`
5. `restate_result`
6. `metacognitive_prompt`

Planner không tự bịa teacher move mới.

Nó chỉ chọn một trong tập enum này.

## 3. Entry point của pedagogy planner

Hàm công khai:

- `build_hint_plan(problem, reference, diagnosis)`

nằm trong `src/pedagogy/planner.py`.

### 3.1 Dispatcher chính

Hàm này dispatch hoàn toàn theo `diagnosis.diagnosis_label`:

1. `CORRECT_ANSWER` -> `_plan_for_correct_answer`
2. `UNPARSEABLE_ANSWER` -> `_plan_for_unparseable`
3. `TARGET_MISUNDERSTANDING` -> `_plan_for_target_misunderstanding`
4. `QUANTITY_RELATION_ERROR` -> `_plan_for_quantity_relation_error`
5. `ARITHMETIC_ERROR` -> `_plan_for_arithmetic_error`
6. còn lại -> `_plan_for_unknown`

Điểm cần nắm:

- pedagogy planner hiện **không** nhìn raw evidence nữa
- nó tin `diagnosis` là đầu vào đã resolve xong

## 4. Shared helper: `_find_reference_step`

Hàm:

- `_find_reference_step(reference, step_id)`

### 4.1 Logic

1. nếu `step_id is None` -> `None`
2. ngược lại:
   - duyệt `reference.chosen_plan.steps`
   - lấy step đầu tiên có `step.step_id == step_id`

### 4.2 Vai trò

Planner dùng hàm này để:

1. lấy canonical step mà diagnosis đang localize tới
2. dùng `step.output_ref` hoặc `step.explanation` làm focus point

## 5. Shared helper: `_base_must_not_reveal`

Hàm:

- `_base_must_not_reveal(reference)`

trả đúng:

1. `"final answer"`
2. `f"{reference.final_answer:g}"`

Tức là mọi hint plan nghiêm túc đều mặc định cấm:

1. nói literal “final answer”
2. nói thẳng đáp án số cuối

## 6. Shared helper: `_step_specific_must_not_reveal`

Hàm:

- `_step_specific_must_not_reveal(reference, step_id)`

### 6.1 Nếu `step_id is None`

- trả `[]`

### 6.2 Nếu có `step_id`

Code duyệt:

```python
for step, result in zip(reference.chosen_plan.steps, reference.execution_trace.step_results):
```

Khi tìm được step có `step.step_id == step_id`, và:

1. `result.success`
2. `result.output_value is not None`

thì append vào hidden list:

1. `step.output_ref`
2. `f"{result.output_value:g}"`

rồi break.

### 6.3 Ý nghĩa

Planner không chỉ cấm lộ đáp án cuối.

Nó còn có thể cấm lộ:

1. output ref của step đang target
2. giá trị số ở step đó

Điều này giúp hint generator không vô tình spoil intermediate answer quan trọng.

## 7. Shared helper: `_dedupe`

Hàm:

- `_dedupe(values)`

### 7.1 Logic

1. duyệt list theo thứ tự
2. bỏ value rỗng
3. bỏ value đã thấy
4. giữ nguyên thứ tự xuất hiện đầu tiên

### 7.2 Vai trò

Planner dùng `_dedupe(...)` cho:

1. `focus_points`
2. `must_not_reveal`

để tránh lặp nội dung.

## 8. Plan cho `correct_answer`: `_plan_for_correct_answer`

Đây là plan đơn giản nhất.

### 8.1 Output cố định

Planner trả `HintPlan` với:

1. `diagnosis_label = diagnosis.diagnosis_label`
2. `hint_level = CONCEPTUAL`
3. `teacher_move = RESTATE_RESULT`
4. `target_step_id = diagnosis.target_step_id`
5. `disclosure_budget = 0`
6. `focus_points = []`
7. `must_not_reveal = []`
8. rationale:
   - học sinh đã đúng, không cần hint instruction
9. `confidence = min(diagnosis.confidence, 0.95)`

### 8.2 Ý nghĩa

Planner coi case đúng bài là:

- không nên dạy thêm
- cũng không nên có focus point nào

Do `disclosure_budget = 0`, điều này còn được schema validator bảo vệ.

## 9. Plan cho `unparseable_answer`: `_plan_for_unparseable`

### 9.1 `target_prompt` được dựng thế nào

Nếu `problem.target` có mặt:

```python
f"what quantity the question asks for: {problem.target.surface_text}"
```

Nếu không:

- `"state the answer as a single numeric result"`

### 9.2 HintPlan được tạo

1. `hint_level = CONCEPTUAL`
2. `teacher_move = METACOGNITIVE_PROMPT`
3. `target_step_id = None`
4. `disclosure_budget = 1`
5. `focus_points` gồm:
   - `target_prompt`
   - `"state the final answer clearly as one number"`
6. `must_not_reveal = _base_must_not_reveal(reference)`
7. rationale:
   - trước hết học sinh cần giúp về cách phát biểu/format đáp án
8. `confidence = min(diagnosis.confidence + 0.02, 0.96)`

### 9.3 Ý nghĩa

Trong case unparseable, planner không cố nhảy vào lỗi toán học.

Nó ưu tiên:

1. re-orient student vào target
2. buộc student nêu một số cuối rõ ràng

## 10. Plan cho `target_misunderstanding`: `_plan_for_target_misunderstanding`

### 10.1 Khởi tạo focus points

Bắt đầu với:

1. `"what quantity the question is actually asking for"`

Nếu `problem.target` có mặt:

2. append `problem.target.surface_text`

### 10.2 Dùng canonical step nếu có

Code lấy:

- `step = _find_reference_step(reference, diagnosis.target_step_id)`

Nếu step có mặt và có `step.explanation`:

append:

```python
f"why {step.output_ref} is only an intermediate result"
```

Điểm này rất quan trọng:

- nếu diagnosis đã localize nhầm-target tại một step canonical cụ thể
- planner sẽ nhấn vào việc output đó chỉ là intermediate, chưa phải target cuối

### 10.3 `must_not_reveal`

Planner ghép:

1. `_base_must_not_reveal(reference)`
2. `_step_specific_must_not_reveal(reference, diagnosis.target_step_id)`

rồi `_dedupe(...)`

### 10.4 HintPlan cuối

1. `hint_level = CONCEPTUAL`
2. `teacher_move = REFOCUS_TARGET`
3. `target_step_id = diagnosis.target_step_id`
4. `disclosure_budget = 1`
5. `focus_points = deduped`
6. `must_not_reveal = deduped`
7. rationale:
   - cần redirect học sinh về quantity đích
8. `confidence = min(diagnosis.confidence + 0.03, 0.97)`

### 10.5 Ý nghĩa

Plan này không dạy phép tính.

Nó dạy:

- “em đang nhắm sai thứ cần trả lời”

## 11. Plan cho `quantity_relation_error`: `_plan_for_quantity_relation_error`

Đây là plan cho lỗi cấu trúc / quan hệ giữa quantities.

### 11.1 Khởi tạo focus points

Bắt đầu với:

1. `"how the problem quantities should be combined"`

### 11.2 Bổ sung từ relation candidate

Code lấy:

- `relation = problem.relation_candidates[0] if problem.relation_candidates else None`

Nếu `relation` có mặt và `relation.rationale` không rỗng:

- append `relation.rationale`

Điều này có nghĩa:

- pedagogy planner tận dụng rationale của relation candidate như một semantic clue cho hint

### 11.3 Bổ sung target reminder

Nếu `problem.target` có mặt:

- append:
  - `f"target: {problem.target.surface_text}"`

### 11.4 Bổ sung explanation của canonical step được target

Nếu tìm được `step = _find_reference_step(reference, diagnosis.target_step_id)` và `step.explanation` có mặt:

- append `step.explanation`

### 11.5 HintPlan cuối

1. `hint_level = RELATIONAL`
2. `teacher_move = CHECK_RELATIONSHIP`
3. `target_step_id = diagnosis.target_step_id`
4. `disclosure_budget = 2`
5. `focus_points = _dedupe(focus_points)`
6. `must_not_reveal = _dedupe(base + step_specific)`
7. rationale:
   - học sinh cần giúp về quan hệ giữa các quantity trước khi tính lại
8. `confidence = min(diagnosis.confidence + 0.02, 0.97)`

### 11.6 Ý nghĩa

Đây là plan “sửa cách combine quantities”, không phải plan “tính lại số”.

## 12. Plan cho `arithmetic_error`: `_plan_for_arithmetic_error`

### 12.1 State khởi đầu

Code set:

1. `step = _find_reference_step(reference, diagnosis.target_step_id)`
2. `focus_points = ["recompute the arithmetic carefully"]`
3. `teacher_move = RECOMPUTE_STEP`
4. `disclosure_budget = 1`

### 12.2 Nếu localization là `INTERMEDIATE_STEP`

Nếu:

1. `diagnosis.localization == INTERMEDIATE_STEP`
2. và `step is not None`

thì:

1. append:
   - `f"check the calculation around {step.output_ref}"`
2. nếu `step.explanation` có:
   - append `step.explanation`

Điều này làm hint tập trung vào một intermediate computation cụ thể.

### 12.3 Nếu localization là `FINAL_COMPUTATION`

Nếu:

- `diagnosis.localization == FINAL_COMPUTATION`

thì:

1. `teacher_move = CONTINUE_FROM_STEP`
2. append:
   - `"revisit the final computation after setting up the right quantities"`

Điều này phản ánh:

- setup nhìn có vẻ đúng
- lỗi nằm ở phép tính cuối

### 12.4 Bổ sung target reminder

Nếu `problem.target` có mặt:

- append:
  - `f"target: {problem.target.surface_text}"`

### 12.5 HintPlan cuối

1. `hint_level = NEXT_STEP`
2. `teacher_move`:
   - `RECOMPUTE_STEP` hoặc `CONTINUE_FROM_STEP`
3. `target_step_id = diagnosis.target_step_id`
4. `disclosure_budget = 1`
5. `focus_points = _dedupe(focus_points)`
6. `must_not_reveal = _dedupe(base + step_specific)`
7. rationale:
   - học sinh đang nhắm đúng quantity, chủ yếu cần hỗ trợ kiểm tra computation
8. `confidence = min(diagnosis.confidence + 0.03, 0.97)`

## 13. Plan cho `unknown_error`: `_plan_for_unknown`

Đây là fallback pedagogy plan.

### 13.1 Focus points

Bắt đầu:

1. `"restate the question in your own words"`

Nếu `problem.target` có mặt:

- append `problem.target.surface_text`

### 13.2 HintPlan cuối

1. `hint_level = CONCEPTUAL`
2. `teacher_move = METACOGNITIVE_PROMPT`
3. `target_step_id = diagnosis.target_step_id`
4. `disclosure_budget = 1`
5. `focus_points = _dedupe(focus_points)`
6. `must_not_reveal = _base_must_not_reveal(reference)`
7. rationale:
   - diagnosis chưa đủ đặc hiệu, nên cách an toàn nhất là yêu cầu học sinh re-orient vào bài toán
8. `confidence = min(diagnosis.confidence, 0.9)`

### 13.3 Ý nghĩa

Planner không cố bịa chiến lược chi tiết khi diagnosis chưa rõ.

Nó lùi về một move metacognitive an toàn.

## 14. Kết cấu logic chung giữa các plan

Nhìn toàn bộ planner, có 4 trục quyết định lặp lại:

### 14.1 `teacher_move`

Đây là trục mạnh nhất.

Từ diagnosis label, planner map sang đúng loại can thiệp:

1. `restate_result`
2. `metacognitive_prompt`
3. `refocus_target`
4. `check_relationship`
5. `recompute_step`
6. `continue_from_step`

### 14.2 `hint_level`

Map khá ổn định:

1. `correct_answer` -> `conceptual`
2. `unparseable_answer` -> `conceptual`
3. `target_misunderstanding` -> `conceptual`
4. `quantity_relation_error` -> `relational`
5. `arithmetic_error` -> `next_step`
6. `unknown_error` -> `conceptual`

### 14.3 `disclosure_budget`

Hiện chỉ dùng 3 mức:

1. `0` cho correct answer
2. `1` cho hầu hết các case còn lại
3. `2` cho quantity relation error

Điều này phản ánh:

- relation error thường cần nhiều nội dung hơn một prompt đơn lẻ

### 14.4 `must_not_reveal`

Planner dùng 2 lớp hidden content:

1. base-level:
   - final answer
   - literal final numeric answer
2. step-specific:
   - output ref của step target
   - output value của step target

## 15. Chỗ nào planner dùng `diagnosis.target_step_id`

`diagnosis.target_step_id` đi vào planner ở 3 chỗ:

1. `_find_reference_step(...)`
2. `_step_specific_must_not_reveal(...)`
3. `HintPlan.target_step_id`

Điều này rất quan trọng:

- planner hiện không tự suy target step
- nó dùng localization từ diagnosis để:
  - biết nên focus vào step nào
  - biết nên cấm lộ intermediate nào

## 16. Planner hiện không làm gì

Tầng này hiện **không**:

1. generate ngôn ngữ hint
2. verify spoiler
3. sửa diagnosis
4. đọc raw evidence
5. đọc raw student text

Tất cả những gì nó làm là:

- diagnosis label -> pedagogical plan

## 17. Confidence của `HintPlan` được set thế nào

Không có một công thức chung cho tất cả.

Mỗi branch tự chỉnh confidence:

1. `correct_answer`
   - `min(diagnosis.confidence, 0.95)`
2. `unparseable`
   - `min(diagnosis.confidence + 0.02, 0.96)`
3. `target_misunderstanding`
   - `min(diagnosis.confidence + 0.03, 0.97)`
4. `quantity_relation_error`
   - `min(diagnosis.confidence + 0.02, 0.97)`
5. `arithmetic_error`
   - `min(diagnosis.confidence + 0.03, 0.97)`
6. `unknown`
   - `min(diagnosis.confidence, 0.9)`

Ý nghĩa:

- pedagogy confidence hiện là diagnosis confidence đã qua calibration nhẹ theo branch

## 18. Kết luận đúng với code hiện tại

Nếu phải mô tả thật ngắn nhưng chính xác:

- Pedagogy planner hiện là một bộ luật deterministic map `DiagnosisResult` sang `HintPlan`: nó chọn teacher move, hint level, disclosure budget, focus points và must-not-reveal dựa trên diagnosis label, localization step và canonical reference step tương ứng.

Nếu nén thành 4 khâu:

1. dispatch theo diagnosis label
2. chọn teacher move + hint level
3. lấy focus points từ target/relation/reference step
4. dựng must-not-reveal từ final answer và target step

Đó là cơ chế lõi hiện tại của `07_pedagogy`.

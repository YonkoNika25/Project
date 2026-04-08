# Cơ Chế Lõi Của Problem Formalization Và Problem Graph

Tài liệu này mô tả đúng **problem formalization** sau tầng parsing heuristic, bám trực tiếp vào code hiện tại trong:

- `src/formalizer/problem_formalizer.py`
- `src/formalizer/problem_formalizer_llm.py`
- `src/formalizer/problem_formalizer_builder.py`
- `src/formalizer/problem_formalizer_validation.py`
- `src/formalizer/problem_graph.py`

Tài liệu này **không** lặp lại phần `01_problem_parsing.md`.

Ở đây, trọng tâm là:

1. hệ đi từ `heuristic_problem + heuristic_evidence` sang `FormalizedProblem` như thế nào
2. khi nào dùng heuristic-only, khi nào gọi LLM
3. semantic sketch mà LLM trả về thực chất là gì
4. local compiler từ sketch hoạt động ra sao
5. validation và repair chặn những gì
6. graph được dựng như thế nào
7. heuristic graph builder hiện resolve candidate evidence đến mức nào

## 1. Vai trò của tầng này

Sau khi có `evidence_pack` từ parsing layer, problem formalization hiện không đi theo kiểu:

- heuristic parser kết luận gần hết
- rồi LLM chỉ “chỉnh nhẹ”

Mà đi theo pipeline:

1. heuristic parsing sinh `evidence_pack`
2. heuristic projection sinh một `FormalizedProblem` mỏng
3. nếu không có LLM thì dùng heuristic projection đó
4. nếu có LLM thì dùng heuristic projection + evidence pack làm anchor
5. LLM trả về một **semantic sketch**
6. local code compile sketch thành `FormalizedProblem` typed
7. validate graph, validate semantic sanity
8. nếu pass thì nhận
9. nếu fail thì feedback và retry
10. nếu vẫn fail thì fallback về heuristic problem

Điểm rất quan trọng:

- LLM **không** trả artifact cuối cùng
- local code mới là nơi compile, validate, repair và đóng artifact cuối

## 2. Điểm vào công khai: `formalize_problem`

Hàm công khai là:

- `formalize_problem(problem_text, llm_client=None)`

trong `src/formalizer/problem_formalizer.py`.

### 2.1 Trình tự thực tế

Hàm này làm đúng 3 bước:

1. `heuristic_problem, heuristic_evidence = _heuristic_formalize_problem(problem_text)`
2. nếu `llm_client is None` -> trả luôn `heuristic_problem`
3. nếu có `llm_client` -> gọi `_llm_formalize_problem(...)`

### 2.2 Nhánh fallback cuối

Nếu `_llm_formalize_problem(...)` ném:

1. `LLMGenerationError`
2. `ValueError`
3. `TypeError`

thì `formalize_problem(...)` không để lỗi đi ra ngoài.

Nó:

1. copy `heuristic_problem.notes`
2. append `llm_formalization_failed_fallback`
3. trả về heuristic problem

Nghĩa là:

- heuristic formalization là đường dự phòng cuối cùng
- không phải artifact chính khi LLM thành công

## 3. Heuristic problem đóng vai trò gì ở tầng này

`heuristic_problem` ở đây đến từ:

- `_heuristic_formalize_problem(problem_text)`

trong builder.

Artifact này đã được nói ở file 01:

- nó là projection mỏng từ `evidence_pack`
- không phải semantic truth đầy đủ

Ở tầng formalization hiện tại, `heuristic_problem` có 3 vai trò:

1. fallback nếu LLM fail
2. anchor cho prompt LLM
3. baseline để local compiler so sánh và ghi disagreement notes

Nói cách khác:

- heuristic problem bây giờ là **anchor object + fallback object**
- không phải semantic parser cuối cùng

## 4. LLM được gọi như thế nào

LLM loop nằm trong:

- `_llm_formalize_problem(problem_text, heuristic_problem, heuristic_evidence, llm_client)`

ở `src/formalizer/problem_formalizer_llm.py`.

### 4.1 Số vòng retry

Code dùng:

```python
for attempt_index in range(1, 4):
```

Tức là có tối đa **3 attempt**.

### 4.2 Trạng thái lặp

Trước vòng lặp, code khởi tạo:

1. `feedback_issues = []`
2. `last_validation_result = _missing_graph_validation_result()`

Tức là mọi attempt sau attempt 1 đều có thể nhận feedback từ lỗi attempt trước.

## 5. Prompt LLM được xây như thế nào

Prompt nằm trong:

- `_build_llm_graph_prompt(problem_text, heuristic_problem, heuristic_evidence, feedback_issues, attempt_index)`

### 5.1 Dữ liệu anchor được đưa vào prompt

Hàm này gọi:

- `_build_compact_draft(heuristic_problem, heuristic_evidence)`

trong builder.

Compact draft hiện chứa đồng thời:

1. `problem_text`
2. `sentence_spans`
3. `numeric_mentions`
4. `implicit_quantity_cues`
5. `lexical_cues`
6. `target_span_candidates`
7. `target_link_candidates`
8. `relation_candidates`
9. `entity_candidates`
10. `heuristic_projection`
11. `draft_notes`
12. `resolved_quantities`
13. `resolved_entities`
14. `resolved_target`
15. `graph_steps`
16. `graph_target_node_id`

Điểm cần nắm:

- prompt bây giờ không chỉ đưa một heuristic formalization nghèo
- nó đưa cả `evidence_pack` và một projection heuristic mỏng

### 5.2 System prompt đang định nghĩa vai trò của model như thế nào

System prompt nói rõ:

1. model là `math problem formalizer`
2. phải trả về **compact semantic sketch JSON object**
3. không được trả final `FormalizedProblem`
4. phải dùng heuristic draft chỉ như **lightweight anchors**
5. local code sẽ compile sketch thành typed graph cuối

Đây là contract kiến trúc cốt lõi của hệ hiện tại.

### 5.3 Top-level schema mà LLM phải trả

Prompt yêu cầu model trả đúng các field:

1. `quantity_annotations`
2. `semantic_facts`
3. `target`
4. `relation`
5. `plan_steps`
6. `graph_target_node_id`
7. `graph_confidence`
8. `graph_notes`
9. `assumptions`
10. `confidence`
11. `notes`

Điểm rất quan trọng:

- đây vẫn chưa phải `FormalizedProblem`
- đây là **semantic sketch schema**

### 5.4 Các enum contract được đóng trong prompt

Prompt nhúng trực tiếp các tập giá trị cho:

1. `QuantitySemanticRole`
2. `RelationType`
3. `OperationType`
4. `TraceOperation`

Mục đích:

- ép LLM sinh output nằm trong vocabulary mà local compiler hiểu được

### 5.5 Hard constraints cốt lõi trong prompt

Prompt hiện giữ một số ràng buộc tối thiểu:

1. draft chỉ là anchor
2. hidden numeric facts phải vào `semantic_facts`
3. không invent `quantity_2`, `quantity_3` bừa nếu draft không có
4. `plan_steps.expression` chỉ là RHS executable
5. `graph_target_node_id` phải khớp target
6. target cuối phải reachable từ sequence
7. ưu tiên intermediate structure faithful hơn nhảy thẳng ra đáp án
8. chỉ dùng enum hợp lệ

Đây là layer constraint để model không sinh sketch phá compiler.

### 5.6 Feedback từ attempt trước được đưa lại cho model thế nào

Prompt user luôn chứa:

- `Structured feedback from the previous failed attempt: ...`

với dữ liệu lấy từ:

- `_graph_feedback_payload(last_validation_result)`

Tức là retry loop hiện tại không phải “random retry”.

Nó là:

- validation-driven retry

## 6. Semantic sketch LLM được xử lý ra sao

Trong mỗi attempt, `_llm_formalize_problem(...)` gọi:

```python
payload = llm_client.generate_json(...)
```

sau đó:

1. thêm `payload["problem_text"] = problem_text.strip()`
2. lấy `notes` cũ của payload
3. append `llm_formalization_attempt:<attempt_index>`

Tức là ngay từ đầu, payload đã được local code bọc thêm metadata attempt.

## 7. Tầng compile từ semantic sketch sang `FormalizedProblem`

Tầng này nằm trong builder:

- `_build_formalized_problem_from_skeleton(problem_text, heuristic_problem, payload)`

Đây là nơi semantic sketch trở thành artifact typed thật.

Nó làm 6 việc lớn:

1. compile quantities
2. compile target
3. compile relation candidates
4. normalize plan steps
5. build typed graph từ plan steps
6. validate + repair + compare với heuristic

## 8. Compile quantities: `_compile_quantities_from_semantic_sketch`

Hàm:

- `_compile_quantities_from_semantic_sketch(heuristic_problem, payload, notes)`

### 8.1 Nguồn dữ liệu

Hàm này đọc 2 khối trong payload:

1. `quantity_annotations`
2. `semantic_facts`

### 8.2 `quantity_annotations` được xử lý thế nào

Code duyệt `raw_quantity_annotations` nếu nó là `list[dict]`.

Với mỗi `raw_update`:

1. lấy `quantity_id`
2. nếu thiếu thì bỏ qua
3. gọi `_sanitize_quantity_update(raw_update)`

`_sanitize_quantity_update(...)` hiện chỉ check mạnh một thứ:

1. `semantic_role`
   - nếu không nằm trong enum `QuantitySemanticRole` thì bỏ field đó
   - ghi note `ignored_invalid_semantic_role:...`

Sau đó mọi update hợp lệ được lưu vào:

- `quantity_updates_by_id[quantity_id] = sanitized`

### 8.3 Merge quantity update lên heuristic quantities

Sau khi có map update, code duyệt toàn bộ `heuristic_problem.quantities`.

Với mỗi quantity heuristic:

1. lấy `quantity_payload = quantity.model_dump(mode="json")`
2. overlay các field hợp lệ từ update:
   - `unit`
   - `entity_id`
   - `semantic_role`
   - `is_target_candidate`
3. validate lại bằng `QuantityAnnotation.model_validate(quantity_payload)`

Nếu `semantic_role` bị model đổi so với heuristic, code append note:

- `llm_quantity_role_update:<quantity_id>:<old_role>-><new_role>`

### 8.4 `semantic_facts` được compile thành gì

`semantic_facts` không được giữ như một list rời.

Nó được compile thành **các quantity mới**.

Với mỗi fact:

1. tạo `latent_payload`
2. map:
   - `fact_id` hoặc `quantity_id` -> `quantity_id`
   - `label` / `surface_text` / `value` -> `surface_text`
   - `value`
   - `unit`
   - `entity_id`
   - `semantic_role`
   - `is_target_candidate`
   - `notes`

3. nếu `grounding` có mặt thì thêm nó vào notes
4. gọi `_sanitize_latent_quantity_payload(...)`

### 8.5 `_sanitize_latent_quantity_payload` kiểm gì

Hàm này chặn các latent quantity sai kiểu:

1. thiếu `quantity_id`
2. trùng `quantity_id` đã tồn tại
3. thiếu `surface_text`
4. `value` không numeric
5. `semantic_role` không hợp lệ

Nếu role không hợp lệ:

- nó ép về `intermediate`
- ghi note coercion

Nếu payload hợp lệ:

1. thêm `provenance = LLM`
2. validate bằng `QuantityAnnotation.model_validate(...)`
3. append vào `quantities`
4. note:
   - `llm_semantic_fact_added:<quantity_id>`

### 8.6 Kết luận của pha quantity compile

Sau khi chạy xong hàm này:

1. các quantity heuristic cũ đã có thể được refine
2. các semantic fact mới đã được nâng thành quantity/intermediate typed thật

## 9. Compile target: `_build_target_payload_from_sketch`

Hàm:

- `_build_target_payload_from_sketch(heuristic_problem, payload)`

### 9.1 Cách nó khởi tạo

Nếu heuristic problem đã có target:

- `target_payload` bắt đầu bằng `heuristic_problem.target.model_dump(mode="json")`

Nếu không:

- bắt đầu bằng `{}`.

### 9.2 Overlay field nào từ LLM

Nếu `payload["target"]` là dict, code chỉ cho update các field:

1. `surface_text`
2. `normalized_question`
3. `target_variable`
4. `target_quantity_id`
5. `entity_id`
6. `unit`
7. `description`
8. `confidence`

### 9.3 Repair target quantity id

Trong `_build_formalized_problem_from_skeleton(...)`, sau khi compile quantities xong, code lấy:

1. `target_payload`
2. `target_variable`
3. `target_quantity_id`

Nếu `target_quantity_id` có mặt nhưng **không nằm trong** `existing_quantity_ids`:

1. append note:
   - `local_target_repair:cleared_unknown_target_quantity_id:<id>`
2. set `target_payload["target_quantity_id"] = None`

Sau đó:

- ép `provenance = LLM`
- validate thành `TargetSpec`

### 9.4 Ý nghĩa

Tầng compile target hiện không tin mù target của model.

Nó vẫn:

1. khởi đầu từ heuristic target
2. overlay phần model đưa
3. clear ref không tồn tại

## 10. Compile relation: `_build_relation_candidates_from_sketch`

Hàm:

- `_build_relation_candidates_from_sketch(heuristic_problem, payload, target_variable, quantities)`

### 10.1 Nếu model có `relation`

Khi `payload["relation"]` là dict:

1. nó được bọc thành một danh sách `raw_relations = [relation_block]`
2. với mỗi raw relation, code tạo `relation_payload`:
   - `relation_id`
   - `relation_type`
   - `operation_hint`
   - `source_quantity_ids`
   - `target_variable`
   - `expression`
   - `rationale`
   - `confidence`
   - `provenance = LLM`

3. `expression` được chuẩn hóa qua `_normalize_relation_expression(...)`
4. validate bằng `RelationCandidate.model_validate(...)`

### 10.2 Nếu model không có relation

Code không cố invent relation mới.

Nó:

- trả lại `list(heuristic_problem.relation_candidates)`

### 10.3 `_normalize_relation_expression` làm gì

Hàm này:

1. `strip()` expression
2. nếu không có gì -> `None`
3. nếu có `=`:
   - tách `lhs`, `rhs`
   - chuẩn hóa về `lhs = rhs`
4. nếu không có `=` thì giữ nguyên

Khác với `plan_steps.expression`, relation expression được phép có vế trái.

## 11. Tách `plan_steps` từ payload

Hàm:

- `_extract_graph_steps_from_payload(payload)`

rất mỏng:

1. lấy `payload["plan_steps"]`
2. nếu là `list`
3. giữ lại các phần tử là `dict`
4. nếu không thì trả `[]`

Tức là local code tin rằng:

- plan step normalization sẽ diễn ra ở hàm sau, không ở bước extract này

## 12. Chuẩn hóa `plan_steps`: `_normalize_graph_steps_for_builder`

Đây là một trong những hàm repair quan trọng nhất của builder.

Input:

1. `graph_steps`
2. `target_variable`
3. `target_quantity_id`

### 12.1 Chuẩn hóa từng step

Với mỗi step:

1. copy `normalized_step = dict(step)`
2. chuẩn hóa expression qua `_normalize_step_expression(...)`
3. chuẩn hóa `input_refs`:
   - cast sang string
   - `strip()`
   - bỏ ref rỗng
4. chuẩn hóa `output_ref`
5. nếu `target_variable` có mặt:
   - thay mọi `input_ref == "target"` thành `target_variable`
   - nếu `output_ref == "target"` thì đổi thành `target_variable`

### 12.2 `_normalize_step_expression` làm gì

Khác với relation expression, `plan_steps.expression` **phải là RHS**.

Hàm này:

1. `strip()`
2. nếu có `=`:
   - bỏ vế trái
   - chỉ giữ `rhs`

Ví dụ:

- `a = b + c`

sẽ thành:

- `b + c`

### 12.3 Retarget output cuối

Sau khi normalize từng step, hàm xét:

1. có `target_variable` không
2. graph có step nào output trực tiếp ra `target_variable` chưa

Nếu chưa có, nó nhìn `last_output_ref` của step cuối.

Biến `should_retarget` thành `True` khi:

1. `target_quantity_id` có mặt và `last_output_ref == target_quantity_id`
2. hoặc `last_output_ref` trông giống generated quantity id (`quantity_\\d+`)

Nếu `should_retarget`:

1. mọi step output đúng `last_output_ref` được đổi sang `target_variable`
2. mọi `input_ref` bằng `last_output_ref` cũng được đổi sang `target_variable`
3. expression cũng replace token đó
4. append note:
   - `local_graph_repair:retargeted_output_ref:<old>-><target_variable>`

### 12.4 Ý nghĩa

Đây là lớp hấp thụ một loại sai lệch phổ biến của model:

- model dựng plan đúng logic nhưng output cuối lại trỏ vào placeholder/generated quantity thay vì target thật

## 13. Dựng typed graph từ semantic sketch: `_build_problem_graph_from_skeleton`

Hàm:

- `_build_problem_graph_from_skeleton(problem, graph_steps, graph_target_node_id, graph_confidence, graph_notes)`

là nơi semantic sketch trở thành `ProblemGraph` typed.

### 13.1 Dựng entity nodes

Với mỗi `problem.entities`, code tạo:

- `ProblemGraphNode` kiểu `ENTITY`

với:

1. `node_id = entity.entity_id`
2. `label = entity.surface_text`
3. `entity_id`
4. `confidence = 0.95`
5. `provenance = PROBLEM_TEXT`

### 13.2 Dựng quantity nodes

Với mỗi `problem.quantities`, code tạo:

- `ProblemGraphNode` kiểu `QUANTITY`

với:

1. `node_id = quantity.quantity_id`
2. `label = quantity.surface_text`
3. `value`
4. `unit`
5. `quantity_id`
6. `entity_id`
7. `semantic_role`
8. `confidence = 0.95`
9. `provenance = quantity.provenance`
10. `notes = quantity.notes`

Nếu quantity có `entity_id`, code thêm edge:

- `ENTITY_HAS_QUANTITY`

### 13.3 Dựng target node

Nếu `problem.target` có mặt, code tạo:

- `ProblemGraphNode` kiểu `TARGET`

với:

1. `node_id = problem.target.target_variable`
2. `label = problem.target.surface_text`
3. `unit`
4. `entity_id`
5. `target_variable`
6. `confidence = problem.target.confidence`
7. `provenance = problem.target.provenance`

Nếu target có `entity_id`, code thêm edge:

- `DESCRIBES_ENTITY`

### 13.4 Dựng operation nodes từ `plan_steps`

Code sort `graph_steps` theo `step_index`.

Với mỗi step:

1. lấy `step_id`
2. lấy `operation_name`
3. lấy `output_ref`
4. tạo `op_node_id = "op_<step_id>"`
5. lấy `input_refs`
6. lấy `label`
7. lấy `expression`

Sau đó tạo:

- `ProblemGraphNode` kiểu `OPERATION`

với:

1. `node_id = op_node_id`
2. `label`
3. `operation = TraceOperation(operation_name)`
4. `expression`
5. `step_id`
6. `step_index`
7. `confidence`
8. `provenance = LLM`

### 13.5 Tạo input edges

Với mỗi `input_ref` đã tồn tại trong `existing_refs`, code tạo edge:

- `INPUT_TO_OPERATION`

với `position` tương ứng.

### 13.6 Tạo output node nếu chưa tồn tại

Nếu `output_ref` có mặt nhưng chưa có node tương ứng:

1. nếu `output_ref == problem.target.target_variable`
   - tạo node kiểu `TARGET`
2. ngược lại
   - tạo node kiểu `INTERMEDIATE`

### 13.7 Tạo output edge

Mỗi step có `output_ref` thì luôn có:

- `OUTPUT_FROM_OPERATION`

từ `op_node_id` sang `output_ref`.

### 13.8 Kết quả cuối

Hàm trả:

- `ProblemGraph(...)`

với:

1. `nodes`
2. `edges`
3. `target_node_id`
4. `confidence = graph_confidence`
5. `provenance = LLM`
6. `notes = graph_notes`

## 14. Validation tầng schema và fallback target/relation

Trước khi graph được build, `_build_formalized_problem_from_skeleton(...)` tạo `FormalizedProblem` và gọi:

- `validate_formalized_problem(problem)`

Hàm này nằm trong `problem_formalizer_validation.py`.

### 14.1 Entity dedupe

Code dedupe entity theo:

- `(entity.normalized_name or entity.surface_text).strip().lower()`

Entity trùng sẽ bị bỏ và ghi note:

- `deduped_entity:<key>`

### 14.2 Quantity dedupe

Code gọi `_dedupe_quantities(...)`.

Hàm dedupe quantity theo key:

1. `surface_text`
2. `char_start`
3. `char_end`

Nếu quantity trùng:

- ghi note `deduped_quantity:<surface>@<char_start>`

### 14.3 Fallback target

Nếu `problem.target is None`, code sinh fallback:

- `TargetSpec(...)`

với:

1. `surface_text = problem.problem_text.strip()`
2. `normalized_question = same`
3. `target_variable = "answer"`
4. `provenance = UNKNOWN`
5. `confidence = 0.1`

và thêm note:

- `target_missing_fallback`

### 14.4 Fallback relation candidate

Nếu `problem.relation_candidates` rỗng, code tạo:

- `RelationCandidate(...)`

với:

1. `relation_id = "relation_fallback"`
2. `relation_type = UNKNOWN`
3. `operation_hint = UNKNOWN`
4. `source_quantity_ids` lấy từ tất cả quantities
5. `target_variable = target.target_variable`
6. `confidence = 0.1`
7. `provenance = UNKNOWN`
8. rationale fallback

và thêm note:

- `relation_candidate_fallback`

### 14.5 Fallback unresolved expression

Với mỗi relation candidate, nếu:

1. `relation.target_variable == target.target_variable`
2. `expression` còn trống
3. có quantities

thì code điền:

```python
target = unresolved_relation(q1, q2, ...)
```

và thêm note:

- `filled_expression_for:<relation_id>`

Điểm này không phải executable expression để runtime chạy.

Nó là placeholder để artifact typed không bị thiếu expression hoàn toàn.

### 14.6 Confidence của `FormalizedProblem` được tính lại thế nào

Code bắt đầu từ:

- `confidence = 0.15`

Rồi cộng:

1. `+0.25` nếu có quantities
2. `+0.15` nếu có ít nhất 2 quantities
3. `+0.15` nếu target tồn tại và provenance của target khác `UNKNOWN`

Ngoài ra, nếu notes của quantities có:

1. `percent_like`
2. `threshold_like`

thì code chỉ append note:

- `contains_percent_like_evidence`
- `contains_threshold_like_evidence`

chứ không boost confidence trực tiếp bằng semantic projection cũ nữa.

### 14.7 Ý nghĩa kiến trúc

`validate_formalized_problem(...)` hiện:

1. không còn coi heuristic semantic role hay relation projection là truth cứng
2. chủ yếu đảm bảo artifact typed không bị rỗng / gãy

## 15. Semantic repair sau graph build: `_apply_local_semantic_repairs`

Sau khi graph được dựng từ semantic sketch, builder gọi:

- `_apply_local_semantic_repairs(problem)`

Đây là post-compile repair layer.

### 15.1 Repair 1: clear `target_quantity_id` cho derived target

Nếu:

1. có `graph_steps`
2. số bước > 1
3. `target.target_quantity_id` không rỗng

thì code clear `target_quantity_id` và thêm note:

- `local_semantic_repair:cleared_target_quantity_for_derived_target`

Ý nghĩa:

- một target multi-step không nên vẫn trỏ vào visible quantity input

### 15.2 Repair 2: clear answer-fact target quantity

Nếu:

1. có graph steps
2. `target.target_quantity_id` không rỗng
3. quantity đó tồn tại
4. quantity đó có provenance `LLM`
5. `target.target_quantity_id` không nằm trong graph input refs
6. nhưng `target.target_variable` nằm trong graph output refs

thì clear `target_quantity_id` và thêm note:

- `local_semantic_repair:cleared_answer_fact_target_quantity`

Ý nghĩa:

- nếu LLM tạo ra một answer-like quantity fact nhưng graph thật đã produce target, không giữ target trỏ vào answer fact đó nữa

### 15.3 Repair 3: clear stale target candidates trên input quantities

Code lấy:

- `lowered_target_text = target.surface_text.lower()`

Rồi duyệt mọi quantity.

Nếu:

1. graph có nhiều hơn 1 step
2. quantity đang có `is_target_candidate = True`
3. nhưng `quantity.surface_text.lower()` **không nằm** trong `target_text`

thì quantity đó bị đổi:

- `is_target_candidate = False`

và append note:

- `local_semantic_repair:cleared_input_target_candidates`

### 15.4 Ý nghĩa

Hàm này sửa các mâu thuẫn semantic còn sót lại sau khi graph typed đã tồn tại.

## 16. Semantic sanity validation

Trong LLM loop, sau khi graph validator pass, code còn gọi:

- `_semantic_sanity_validation_result(refined)`

### 16.1 Nó kiểm target

Nếu `problem.target is None`:

- issue `missing_target_spec`

### 16.2 Nó kiểm derived target

Nếu:

1. graph có hơn 1 operation step
2. `problem.target.target_quantity_id` vẫn còn

-> issue:

- `derived_target_still_points_to_quantity`

### 16.3 Nó kiểm rate relation

Nếu relation chính là `RATE_UNIT_RELATION`, code đòi:

1. phải có `BASE`
2. phải có `UNIT_RATE`
3. phải có `PERCENT`
4. phải có `THRESHOLD`

Nếu thiếu bất kỳ loại nào, tạo issue tương ứng:

1. `missing_base_quantity_for_rate_relation`
2. `missing_unit_rate_for_rate_relation`
3. `missing_percent_for_rate_relation`
4. `missing_threshold_for_rate_relation`

### 16.4 Ý nghĩa

Graph validator kiểm tính đúng của graph như một graph typed.

Semantic sanity validation kiểm:

- graph đó có đang encode một cấu trúc semantic hợp lệ tối thiểu không

## 17. LLM retry loop quyết định accept / reject như thế nào

Quay lại `_llm_formalize_problem(...)`.

### 17.1 Case 1: compile payload nổ ở schema

Nếu `_build_formalized_problem_from_skeleton(...)` ném `ValidationError`:

1. code gọi `_schema_validation_result(exc)`
2. chuyển lỗi thành `GraphValidationResult`
3. lấy `feedback_issues = _graph_feedback_payload(last_validation_result)`
4. `continue`

### 17.2 Case 2: compile payload nổ ở builder logic

Nếu ném `ValueError` hoặc `TypeError`:

1. code tạo `GraphValidationResult`
2. issue code = `skeleton_build_error`
3. feedback quay lại prompt

### 17.3 Case 3: graph bị thiếu

Nếu `refined.problem_graph is None`:

1. `last_validation_result = _missing_graph_validation_result()`
2. feedback quay lại prompt

### 17.4 Case 4: graph validator fail

Nếu `validate_problem_graph(refined)` trả invalid:

1. feedback được build từ validation issues
2. loop retry tiếp

### 17.5 Case 5: graph validator pass nhưng semantic sanity fail

Nếu graph typed pass nhưng `_semantic_sanity_validation_result(refined)` fail:

1. semantic validation result trở thành `last_validation_result`
2. feedback quay lại prompt

### 17.6 Case 6: hoàn toàn thành công

Nếu:

1. compile pass
2. graph tồn tại
3. `validate_problem_graph(refined)` pass
4. semantic sanity pass

thì code:

1. lấy `success_notes = list(refined.notes)`
2. append:
   - `llm_formalization_used`
   - `llm_semantic_sketch_used`
3. nếu `attempt_index > 1`:
   - append `llm_formalization_repaired_after:<attempt_index>`
4. return artifact

### 17.7 Case 7: thất bại sau 3 attempt

Nếu loop hết 3 vòng mà chưa pass:

1. lấy mọi issue code của `last_validation_result`
2. tạo notes:
   - `graph_issue:<issue.code>`
   - `llm_formalization_failed_fallback`
3. trả về heuristic problem với notes mới

## 18. Graph builder heuristic-only hoạt động ra sao

Nếu không có LLM, hoặc nếu fallback về heuristic path, system dùng:

- `build_problem_graph(problem)`

trong `src/formalizer/problem_graph.py`.

Đây là graph builder của **heuristic-only problem**.

### 18.1 Bước 1: dựng base graph

`_build_base_graph(problem)` tạo:

1. entity nodes
2. quantity nodes
3. target node
4. ownership edges
5. target description edge

Tức là base graph luôn có:

- data nodes cơ bản

chưa có operation subgraph.

### 18.2 `_resolved_relation(problem)` làm gì

Đây là gate quan trọng nhất cho heuristic graph builder.

Logic:

1. nếu không có relation candidates -> `None`
2. lấy relation đầu tiên làm `primary`
3. nếu `primary.provenance != HEURISTIC` -> tin nó, trả luôn
4. nếu `primary.relation_type == UNKNOWN` hoặc `primary.confidence < 0.55` -> `None`
5. nếu có runner-up và `runner_up.confidence >= primary.confidence - 0.1` -> `None`
6. ngược lại -> trả `primary`

Ý nghĩa:

- heuristic relation candidate chỉ được dùng để build executable subgraph nếu nó đủ rõ
- candidate yếu hoặc mơ hồ sẽ **không** bị cưỡng ép resolve

### 18.3 Khi heuristic graph builder thêm note gì

Nếu `problem.provenance == HEURISTIC`, builder append note:

- `graph_semantic_resolution_from_candidates`

Nghĩa là graph ở path này được dựng bằng cách resolve candidate evidence trong local code, không phải do LLM trả plan sẵn.

## 19. Heuristic rate subgraph: `_add_rate_subgraph`

Nếu relation resolve ra `RATE_UNIT_RELATION`, graph builder dùng một subgraph nhiều bước riêng.

### 19.1 Cách nó tìm thành phần

Nó gọi:

1. `_select_rate_unit_price_quantity(problem)`
2. tìm `percent`
3. tìm `threshold`
4. `_select_rate_unit_base_quantity(problem)`

#### `_select_rate_unit_price_quantity`

Nó chọn từ quantities dựa trên:

1. `semantic_role == UNIT_RATE`
2. hoặc note có `role_hints=rate_like`
3. hoặc `surface_text` có `$`

Nếu target có `unit`, nó ưu tiên quantity có unit khớp target unit.

Nếu không, nó ưu tiên quantity có `$`.

#### `_select_rate_unit_base_quantity`

Nó ưu tiên:

1. quantity có `semantic_role == BASE`
2. nếu không có, tìm quantity không phải percent / threshold / dollar / percent sign
3. nếu target có unit, tránh quantity có unit đúng bằng target unit
4. fallback cuối là first non-percent quantity

### 19.2 Nếu thiếu thành phần

Nếu không có đủ:

1. unit_rate
2. percent
3. threshold
4. base

thì builder không dựng subgraph rate, chỉ append note:

- `graph_rate_relation_missing_components`

### 19.3 Nếu đủ thành phần

Builder dựng 5 operation steps:

1. `step_1_excess_quantity`
   - subtract
   - `max(base - threshold, 0)`
2. `step_2_discount_per_unit`
   - percent_of
   - `(percent / 100) * unit_rate`
3. `step_3_total_discount`
   - multiply
   - `excess_quantity * discount_per_unit`
4. `step_4_gross_total`
   - multiply
   - `base * unit_rate`
5. `step_5_final_total`
   - subtract
   - `gross_total - total_discount`

Cuối cùng append note:

- `graph_built_from_rate_relation`

Điểm cần nhấn mạnh:

- với rate relation, heuristic graph builder không chỉ dựng 1 step
- nó có một decomposition cứng thành 5 bước

## 20. Heuristic single-step subgraph: `_add_single_step_subgraph`

Nếu relation resolve ra một trong các loại:

1. additive
2. subtractive
3. multiplicative
4. partition

thì builder dùng 1-step subgraph.

### 20.1 Additive

1. operation = `ADD`
2. expression = `q1 + q2 + ...`
3. output = target

### 20.2 Subtractive

1. operation = `SUBTRACT`
2. expression = `q1 - q2 - ...`
3. output = target

### 20.3 Multiplicative

1. operation = `MULTIPLY`
2. expression = `q1 * q2`
3. output = target

### 20.4 Partition

1. operation = `DIVIDE`
2. expression = `q1 / q2`
3. output = target

### 20.5 Notes tương ứng

Mỗi relation type sẽ append một note:

1. `graph_built_from_additive_relation`
2. `graph_built_from_subtractive_relation`
3. `graph_built_from_multiplicative_relation`
4. `graph_built_from_partition_relation`

## 21. Expression fallback subgraph

Nếu relation không resolve ra một family rõ ở `_resolved_relation(problem)`, builder thử:

- `_add_expression_fallback_subgraph(...)`

### 21.1 Khi nào fallback này bị chặn

Nếu relation đầu không có expression:

- note `graph_missing_relation_expression`

Nếu expression chứa:

1. `unresolved_relation(`
2. `rate_or_percent_relation(`

thì coi đó là placeholder, không dùng, và append:

- `graph_placeholder_relation_expression`

### 21.2 Khi nào expression fallback được dùng

Nếu relation đầu có expression “thật”, builder:

1. lấy RHS của relation expression
2. tạo một step `DERIVE`
3. output trực tiếp ra target
4. input refs = `relation.source_quantity_ids`
5. confidence = `max(relation.confidence - 0.1, 0.35)`
6. provenance = `relation.provenance`

và append note:

- `graph_built_from_relation_expression`

### 21.3 Ý nghĩa

Đây là đường cuối để tận dụng relation expression có sẵn nếu các family heuristic không đủ rõ.

## 22. Cách `build_problem_graph(problem)` quyết định path nào

Thứ tự hiện tại:

1. dựng base graph
2. thêm note `graph_semantic_resolution_from_candidates` nếu heuristic path
3. `relation = _resolved_relation(problem)`
4. lấy `relation_type`
5. nếu `RATE_UNIT_RELATION` -> `_add_rate_subgraph`
6. nếu additive / subtractive / multiplicative / partition -> `_add_single_step_subgraph`
7. ngược lại -> `_add_expression_fallback_subgraph`

### 22.1 Confidence của graph cuối

Code tính:

1. nếu graph không có operation node nào -> `confidence = 0.35`
2. nếu có operation -> `confidence = 0.9`

Sau đó:

```python
confidence = max(min(problem.confidence, 0.98), confidence)
```

Tức là graph confidence cuối lấy max giữa:

1. confidence sàn theo việc có operation hay không
2. problem confidence đã có, capped ở `0.98`

### 22.2 Provenance của graph cuối

Graph provenance được set:

1. nếu `problem.provenance != UNKNOWN` -> dùng provenance của problem
2. nếu `UNKNOWN` -> ép thành `HEURISTIC`

## 23. Chỗ nào semantic resolution thực sự xảy ra

Sau refactor, semantic resolution problem-side xảy ra ở 3 tầng khác nhau:

### 23.1 Tầng 1: LLM semantic sketch

Model được phép:

1. refine quantity annotations
2. thêm semantic facts
3. đề xuất target
4. đề xuất relation
5. đề xuất plan steps

Nhưng đây mới là **đề xuất semantic structure**, chưa phải artifact cuối.

### 23.2 Tầng 2: local compiler

Builder:

1. merge quantity updates
2. thêm latent quantities
3. sanitize target
4. sanitize relation
5. normalize steps
6. build typed graph

Đây là nơi semantic sketch được hạ xuống schema typed.

### 23.3 Tầng 3: local validation / repair / heuristic graph builder

Validation và graph builder:

1. reject / repair contradiction
2. chọn khi nào được phép resolve heuristic candidate thành graph structure

Đây là nơi semantic commitment cuối cùng diễn ra.

## 24. Kết luận đúng với code hiện tại

Nếu phải mô tả thật ngắn nhưng đúng lõi:

- Problem formalization hiện không cho heuristic parser quyết định ngữ nghĩa cuối.
- Nó dùng heuristic làm anchor, LLM sinh semantic sketch, local builder compile sketch thành `FormalizedProblem` typed, rồi validation + repair + graph builder quyết định artifact nào đủ chuẩn để được chấp nhận.

Nếu phải nén thành 5 khâu:

1. anchor evidence + heuristic projection
2. semantic sketch generation
3. local typed compile
4. validation / repair / retry
5. graph construction

Đó là cơ chế lõi hiện tại của `02_problem_formalization_and_graph`.

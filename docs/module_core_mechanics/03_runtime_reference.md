# Cơ Chế Lõi Của Runtime Và Canonical Reference

Tài liệu này mô tả đúng lớp runtime hiện tại, bám trực tiếp vào code trong:

- `src/runtime/__init__.py`
- `src/runtime/compiler.py`
- `src/runtime/graph_validator.py`
- `src/runtime/executor.py`
- `src/runtime/solver.py`
- các schema runtime trong `src/models/formalizer_schemas.py`

Tầng này bắt đầu **sau khi đã có** `FormalizedProblem`.

Nó không còn làm NLP hay semantic parsing nữa.

Vai trò của nó là:

1. biến `FormalizedProblem` thành `ExecutablePlan`
2. thực thi `ExecutablePlan` một cách quyết định
3. sinh `ExecutionTrace`
4. đóng gói thành `CanonicalReference`

Điểm quan trọng nhất:

- runtime là **deterministic**
- không gọi model
- không sửa nghĩa theo kiểu heuristic mềm ở phút cuối
- hoặc compile được, execute được
- hoặc fail và trả lỗi có cấu trúc

## 1. Contract dữ liệu của runtime là gì

Runtime chủ yếu làm việc với 5 kiểu dữ liệu:

1. `ExecutableStep`
2. `ExecutablePlan`
3. `ExecutionStepResult`
4. `ExecutionTrace`
5. `CanonicalReference`

Tất cả đều nằm trong `src/models/formalizer_schemas.py`.

### 1.1 `ExecutableStep`

`ExecutableStep` có các field:

1. `step_id`
2. `operation`
3. `expression`
4. `input_refs`
5. `output_ref`
6. `explanation`
7. `executable_code`
8. `confidence`
9. `provenance`

Invariant ở model:

1. `step_id` không được rỗng
2. `output_ref` không được rỗng

Tức là runtime không chấp nhận step vô danh hoặc step không tạo output.

### 1.2 `ExecutablePlan`

`ExecutablePlan` có:

1. `plan_id`
2. `target_ref`
3. `steps`
4. `assumptions`
5. `confidence`
6. `provenance`
7. `notes`

Invariant:

1. `plan_id` không được rỗng
2. `target_ref` không được rỗng
3. không được có `step_id` trùng nhau trong `steps`

### 1.3 `ExecutionStepResult`

`ExecutionStepResult` có:

1. `step_id`
2. `operation`
3. `resolved_inputs`
4. `output_value`
5. `success`
6. `error_message`
7. `notes`

Invariant:

1. nếu `success=True` thì `output_value` bắt buộc phải có
2. nếu `success=False` thì `error_message` bắt buộc phải có

### 1.4 `ExecutionTrace`

`ExecutionTrace` có:

1. `plan_id`
2. `step_results`
3. `final_value`
4. `success`
5. `error_message`
6. `confidence`
7. `notes`

Invariant:

1. nếu `success=True` thì `final_value` bắt buộc phải có

### 1.5 `CanonicalReference`

`CanonicalReference` có:

1. `final_answer`
2. `formalized_problem`
3. `chosen_plan`
4. `execution_trace`
5. `rendered_solution_text`
6. `source_model`
7. `confidence`
8. `notes`

Invariant quan trọng nhất:

1. nếu `execution_trace.success=True` và `execution_trace.final_value` có mặt
2. thì `final_answer` phải đúng bằng `execution_trace.final_value` trong sai số `1e-9`

Điều này có nghĩa:

- `CanonicalReference.final_answer` không phải field tự do
- nó bị khóa bởi trace thực thi

## 2. Entry points của runtime

Trong `src/runtime/__init__.py`, package export các hàm:

1. `compile_executable_plan`
2. `execute_plan`
3. `validate_problem_graph`
4. `build_canonical_reference`
5. `build_solver_candidate`
6. `solve_problem`

Trong đó:

### 2.1 `build_canonical_reference`

`__init__.py` chỉ làm lazy import sang:

- `src.runtime.solver.build_canonical_reference`

### 2.2 `solve_problem`

`solve_problem(...)` trong `solver.py` làm:

1. `formalized_problem = formalize_problem(problem_text)`
2. `return build_canonical_reference(formalized_problem)`

Nhưng ở tầng này, trọng tâm thực sự là:

- `compile_executable_plan`
- `execute_plan`
- `build_canonical_reference`

## 3. Bước đầu tiên của runtime: compile plan

Hàm công khai:

- `compile_executable_plan(problem)`

nằm trong `src/runtime/compiler.py`.

Đây là nơi `FormalizedProblem` được chuyển thành một chiến lược thực thi cụ thể.

### 3.1 Thứ tự quyết định path compile

`compile_executable_plan(problem)` chạy theo thứ tự:

1. thử `_compile_problem_graph_plan(problem)`
2. nếu graph plan compile được thì dùng luôn
3. nếu graph path fail thì resolve relation bằng `_resolved_relation(problem)`
4. dispatch sang compiler chuyên biệt theo `relation_type`

Tức là runtime hiện là:

- **graph-first**
- relation-family fallback second

## 4. Graph-first compilation: `_compile_problem_graph_plan`

Đây là path ưu tiên cao nhất.

Hàm:

- `_compile_problem_graph_plan(problem)`

### 4.1 Điều kiện đầu vào

1. `graph = problem.problem_graph`
2. nếu `graph is None` -> trả `None`

Tức là không có graph thì không compile theo graph path.

### 4.2 Validation trước khi compile

Ngay đầu hàm, code gọi:

- `validation = validate_problem_graph(problem)`

Nếu `validation.is_valid == False`:

- trả `None`

Nghĩa là compiler graph path **không** cố gắng chạy graph nửa hợp lệ.

Nó chỉ compile graph đã pass validation.

### 4.3 Chuẩn bị indexing

Code tạo:

1. `nodes_by_id = {node.node_id: node for node in graph.nodes}`
2. `operation_nodes = sorted(...)`

`operation_nodes` được lấy bằng cách:

1. chỉ giữ node có `node_type == OPERATION`
2. chỉ giữ node có `step_index is not None`
3. sort theo `step_index`

Nếu `operation_nodes` rỗng:

- trả `None`

### 4.4 Compile từng operation node thành `ExecutableStep`

Với mỗi operation node:

1. lấy tất cả `INPUT_TO_OPERATION` edges mà `target_node_id == node.node_id`
2. sort các input edge theo `edge.position`
3. lấy đúng một `OUTPUT_FROM_OPERATION` edge mà `source_node_id == node.node_id`

Nếu không có output edge:

- trả `None`

Compiler không chấp nhận operation node không có output.

### 4.5 Cách `input_refs` được tính

Với mỗi input edge:

1. lấy `source_node = nodes_by_id[edge.source_node_id]`
2. chuyển source node sang ref theo thứ tự ưu tiên:
   - `source_node.quantity_id`
   - hoặc `source_node.target_variable`
   - hoặc `source_node.node_id`

Tức là `input_refs` của executable step luôn là ref symbol mà executor có thể lookup trong environment.

### 4.6 Cách `output_ref` được tính

Với output edge:

1. lấy `output_node = nodes_by_id[output_edge.target_node_id]`
2. `output_ref = output_node.target_variable or output_node.node_id`

### 4.7 Tạo `ExecutableStep`

Mỗi operation node được compile thành:

1. `step_id = node.step_id or node.node_id`
2. `operation = node.operation or TraceOperation.UNKNOWN`
3. `expression = node.expression or node.label`
4. `input_refs`
5. `output_ref`
6. `explanation = node.label`
7. `confidence = node.confidence`
8. `provenance = node.provenance`

### 4.8 Tính confidence của plan graph

Sau khi compile hết steps:

1. lấy trung bình `step.confidence` của tất cả step
2. tạo `ExecutablePlan`

`plan.confidence` được set:

```python
min(max(confidence, graph.confidence), 0.98)
```

Nghĩa là:

1. nó lấy giá trị lớn hơn giữa:
   - mean step confidence
   - graph confidence
2. rồi cap ở `0.98`

### 4.9 Kết quả của graph path

Nếu thành công, `ExecutablePlan` có:

1. `plan_id = "plan_problem_graph"`
2. `target_ref = graph.target_node_id or _target_ref(problem)`
3. `steps`
4. `assumptions = problem.assumptions`
5. `confidence`
6. `provenance = graph.provenance` nếu khác UNKNOWN, ngược lại HEURISTIC
7. `notes = ["compiled_from_problem_graph"] + graph.notes`

Điểm rất quan trọng:

- nếu graph path compile được, runtime **không** dùng heuristic relation compiler nữa

## 5. `_target_ref(problem)` thật sự làm gì

Hàm:

- `_target_ref(problem)`

rất đơn giản:

1. nếu `problem.target` có mặt -> trả `problem.target.target_variable`
2. nếu không -> trả `"answer"`

Hàm này là fallback target symbol cho nhiều compiler path.

## 6. Relation resolution trong runtime: `_resolved_relation`

Nếu graph path không compile được, runtime phải nhìn sang `relation_candidates`.

Hàm:

- `_resolved_relation(problem)`

định nghĩa khi nào relation heuristic được phép nâng thành execution strategy.

### 6.1 Logic chính xác

1. nếu `problem.relation_candidates` rỗng -> `None`
2. lấy candidate đầu là `primary`
3. nếu `primary.provenance != HEURISTIC` -> trả luôn `primary`
4. nếu `primary.relation_type == UNKNOWN` -> `None`
5. nếu `primary.confidence < 0.55` -> `None`
6. nếu có runner-up và:

```python
runner_up.confidence >= primary.confidence - 0.1
```

-> `None`

7. ngược lại -> trả `primary`

### 6.2 Ý nghĩa

Runtime không coi heuristic relation candidate là truth tự động.

Nó chỉ chấp nhận heuristic candidate nếu:

1. không phải `UNKNOWN`
2. đủ confident
3. không quá mơ hồ so với runner-up

Đây là cổng semantic resolution quan trọng để tránh compile nhầm strategy từ candidate evidence yếu.

## 7. Placeholder expression được định nghĩa thế nào

Hàm:

- `_is_placeholder_expression(expression)`

coi expression là placeholder nếu:

1. expression trống
2. hoặc chứa:
   - `unresolved_relation(`
   - `rate_or_percent_relation(`

Điều này dùng để ngăn runtime compile một relation expression chưa được resolve thật.

## 8. Rate plan compiler: `_compile_rate_plan`

Đây là compiler phức tạp nhất trong runtime heuristic path.

### 8.1 Trước hết, nó tìm 4 thành phần

1. `unit_rate`
2. `percent`
3. `threshold`
4. `base`

#### `unit_rate` được chọn bằng `_select_rate_unit_price_quantity`

Hàm này lấy candidate từ `problem.quantities` nếu quantity thỏa một trong các điều kiện:

1. `semantic_role == UNIT_RATE`
2. hoặc note có `role_hints=rate_like`
3. hoặc `surface_text` chứa `$`

Nếu target có unit:

- nó ưu tiên candidate nào có `quantity.unit == target.unit`

Nếu không, nó ưu tiên candidate chứa `$`.

#### `percent` được chọn ra sao

Code lấy:

1. quantity đầu tiên có role `PERCENT`
2. nếu không có thì tìm quantity có:
   - note `percent_like`
   - hoặc `surface_text` chứa `%`

#### `threshold` được chọn ra sao

Code lấy:

1. quantity đầu tiên có role `THRESHOLD`
2. nếu không có thì tìm quantity có note `threshold_like`

#### `base` được chọn bằng `_select_rate_unit_base_quantity`

Logic:

1. nếu có quantity role `BASE` -> lấy cái đầu
2. nếu không:
   - duyệt tất cả quantity
   - bỏ qua quantity có role PERCENT / THRESHOLD
   - bỏ qua quantity có hint percent_like / threshold_like
   - bỏ qua quantity có `$` hoặc `%`
   - nếu target có unit, bỏ qua quantity có `quantity.unit == target.unit`
   - lấy quantity đầu tiên còn lại
3. nếu vẫn không có:
   - fallback sang quantity đầu tiên không phải `PERCENT`

### 8.2 Nếu đủ 4 thành phần

Code dựng một `ExecutablePlan` 5 bước:

1. `step_1_excess_quantity`
   - `SUBTRACT`
   - `max(base - threshold, 0)`
   - output: `excess_quantity`
2. `step_2_discount_per_unit`
   - `PERCENT_OF`
   - `(percent / 100) * unit_rate`
   - output: `discount_per_unit`
3. `step_3_total_discount`
   - `MULTIPLY`
   - `excess_quantity * discount_per_unit`
   - output: `total_discount`
4. `step_4_gross_total`
   - `MULTIPLY`
   - `base * unit_rate`
   - output: `gross_total`
5. `step_5_final_total`
   - `SUBTRACT`
   - `gross_total - total_discount`
   - output: target

Plan metadata:

1. `plan_id = "plan_rate_unit_relation"`
2. `confidence = 0.92`
3. `provenance = HEURISTIC`
4. notes có `compiled_from_rate_unit_relation`

### 8.3 Nếu thiếu thành phần nhưng relation có expression thật

Nếu không đủ 4 thành phần, nhưng:

1. `relation.expression` có mặt
2. và không phải placeholder

thì code fallback sang một step:

1. `DERIVE`
2. expression = RHS của relation expression
3. `input_refs = relation.source_quantity_ids`
4. output = target
5. confidence = `0.45`
6. note thêm:
   - `rate_relation_fallback_expression`

### 8.4 Nếu thiếu cả component lẫn expression thật

Plan vẫn được tạo, nhưng:

1. `steps = []`
2. `confidence = 0.2`
3. note:
   - `rate_relation_missing_components`

Điểm cần nắm:

- compiler không ném lỗi ở đây
- nó trả một plan “rỗng có ghi lý do”
- executor sau đó mới fail ở mức plan không có step

## 9. Additive / subtractive / multiplicative / partition plan compilers

Nếu relation resolve thành 4 family còn lại, runtime dùng compiler 1-step.

### 9.1 `_compile_additive_plan`

1. `terms = [quantity.quantity_id for quantity in quantities]`
2. `expression = " + ".join(terms)` nếu có terms, không thì `"0"`
3. tạo 1 step `ADD`
4. output = target

Confidence:

1. step confidence = `0.9` nếu có ít nhất 2 term, ngược lại `0.4`
2. plan confidence = `0.88` nếu có ít nhất 2 term, ngược lại `0.35`

### 9.2 `_compile_subtractive_plan`

1. lấy `refs`
2. nếu 0 ref -> `"0"`
3. nếu 1 ref -> chính ref đó
4. nếu >=2 ref -> `ref0 - ref1 - ref2 ...`
5. tạo 1 step `SUBTRACT`

Confidence:

1. step = `0.9` nếu >=2 ref, ngược lại `0.4`
2. plan = `0.88` nếu >=2 ref, ngược lại `0.35`

### 9.3 `_compile_multiplicative_plan`

1. lấy tối đa 2 quantity đầu
2. expression = `"q1 * q2"` nếu có đủ 2
3. nếu không đủ thì `"0"`
4. tạo 1 step `MULTIPLY`

Confidence:

1. step = `0.86` nếu đủ 2 ref, ngược lại `0.35`
2. plan = `0.84` nếu đủ 2 ref, ngược lại `0.3`

### 9.4 `_compile_partition_plan`

1. lấy tối đa 2 quantity đầu
2. expression = `"q1 / q2"` nếu đủ 2
3. nếu không đủ thì `"0"`
4. tạo 1 step `DIVIDE`

Confidence:

1. step = `0.84` nếu đủ 2 ref, ngược lại `0.3`
2. plan = `0.8` nếu đủ 2 ref, ngược lại `0.25`

## 10. Unknown plan compiler: `_compile_unknown_plan`

Nếu không resolve được relation family có ích, runtime dùng `_compile_unknown_plan(problem, relation)`.

### 10.1 Trường hợp chỉ có 1 quantity

Nếu `len(problem.quantities) == 1`:

1. tạo 1 step `DERIVE`
2. expression = chính `quantity_id`
3. input_refs = `[quantity_id]`
4. output = target
5. note:
   - `used_single_quantity_fallback`

Confidence:

1. step = `0.5`
2. plan = `0.45`

### 10.2 Trường hợp relation có expression thật

Nếu:

1. có `relation`
2. `relation.expression` có mặt
3. và không phải placeholder

thì tạo 1 step `DERIVE`:

1. expression = RHS của relation expression
2. input_refs = `relation.source_quantity_ids`
3. output = target
4. note:
   - `used_relation_expression`

Confidence:

1. step = `0.35`
2. plan = `0.3`

### 10.3 Trường hợp hoàn toàn unresolved

Nếu không rơi vào hai case trên:

1. trả `ExecutablePlan`
2. `steps = []`
3. `confidence = 0.0`
4. `provenance = UNKNOWN`
5. notes:
   - `compiled_from_unknown_relation`
   - `no_executable_strategy`

Đây là nguyên nhân trực tiếp của lỗi runtime kiểu:

- `Executable plan has no steps`

## 11. Graph validator thực sự kiểm gì

Hàm:

- `validate_problem_graph(problem)`

nằm trong `src/runtime/graph_validator.py`.

Đây là cổng cấu trúc trước graph-first compilation.

### 11.1 Kiểm graph có tồn tại không

Nếu `problem.problem_graph is None`:

- issue `missing_problem_graph`

và return invalid ngay.

### 11.2 Kiểm có operation nodes không

Lấy:

- `operation_nodes = sorted(node for node in graph.nodes if node.node_type == OPERATION, key=step_index)`

Nếu rỗng:

- issue `missing_operation_nodes`

### 11.3 Kiểm target node id

Nếu `graph.target_node_id is None`:

- issue `missing_target_node_id`

Nếu `graph.target_node_id` không nằm trong `nodes_by_id`:

- issue `unknown_target_node_id`

### 11.4 Kiểm uniqueness của step ids và step indexes

1. nếu có duplicate `step_id` -> issue `duplicate_step_id`
2. nếu có duplicate `step_index` -> issue `duplicate_step_index`

### 11.5 `available_refs` được khởi tạo như thế nào

Code set:

```python
available_refs = {quantity.quantity_id for quantity in problem.quantities}
```

và note:

- `initial_available_refs=<count>`

Điều này có nghĩa:

- trước khi execute operation nào, chỉ các `quantity_id` của problem mới được coi là available

### 11.6 Kiểm input edges của từng operation

Với mỗi operation node:

1. lấy tất cả `INPUT_TO_OPERATION` edges vào node
2. sort theo `position`

Nếu không có input edges:

- bình thường là invalid
- trừ case đặc biệt:
  - `node.operation == DERIVE`
  - và expression là constant zero-input expression

#### Constant zero-input expression được nhận thế nào

Qua `_is_zero_input_constant_expression(expression)`.

Hàm này parse AST expression và:

1. nếu parse lỗi -> False
2. nếu có bất kỳ `ast.Name` nào -> False
3. nếu không có `ast.Name` -> True

Tức là expression như:

- `7`
- `1 + 2`
- `max(3, 4)`

được coi là constant expression không cần input refs.

### 11.7 Kiểm output edges của từng operation

Nếu `len(output_edges) == 0`:

- issue `operation_missing_output`

Nếu `len(output_edges) > 1`:

- issue `operation_multiple_outputs`

Runtime hiện yêu cầu:

- mỗi operation node phải có **đúng một** output edge

### 11.8 Kiểm input ref có available trước khi dùng không

Với mỗi input edge:

1. lấy `source_node`
2. nếu `source_node.node_type == ENTITY`
   - issue `entity_used_as_numeric_input`
3. ngược lại:
   - tính `input_ref = source_node.quantity_id or source_node.target_variable or source_node.node_id`
   - nếu `input_ref not in available_refs`
     -> issue `input_not_available`

### 11.9 Cập nhật `available_refs`

Sau khi operation node pass qua phần input/output structural checks, code lấy output node:

1. `output_ref = output_node.target_variable or output_node.node_id`
2. add `output_ref` vào `available_refs`

Tức là validator đang mô phỏng đúng một execution order:

- step nào sinh output trước thì step sau mới được dùng output đó

### 11.10 Kiểm target có được produce không

Sau khi đi qua toàn bộ operation nodes:

Nếu `graph.target_node_id` không nằm trong `available_refs`:

- issue `target_not_produced`

### 11.11 Output của validator

Validator trả `GraphValidationResult` gồm:

1. `is_valid`
2. `issues`
3. `target_node_id`
4. `operation_node_count`
5. `notes`

## 12. Executor: `execute_plan`

Hàm:

- `execute_plan(plan, problem)`

nằm trong `src/runtime/executor.py`.

Đây là nơi plan thật sự được chạy.

## 13. Environment ban đầu được tạo thế nào

Code gọi:

- `_build_environment(problem)`

Hàm này tạo:

```python
{quantity.quantity_id: quantity.value for quantity in problem.quantities}
```

Tức là environment ban đầu chỉ bind:

1. `quantity_id`
2. sang `value`

Không bind entity, không bind target, không bind note-based aliases.

## 14. Expression evaluator hoạt động thế nào

Executor **không dùng `eval`**.

Nó parse AST và chỉ chấp nhận một tập node rất hẹp.

### 14.1 Hàm chính

- `_evaluate_expression(expression, environment)`

làm:

1. `parsed = ast.parse(expression, mode="eval")`
2. `return float(_eval_ast(parsed, environment))`

### 14.2 `_eval_ast` chấp nhận node gì

#### `ast.Expression`

- recurse vào `body`

#### `ast.Constant`

Chỉ nhận nếu `node.value` là `int` hoặc `float`

#### `ast.Name`

1. nếu `node.id` không có trong `environment` -> ném `KeyError`
2. nếu có -> trả `float(environment[node.id])`

#### `ast.BinOp`

Chỉ hỗ trợ:

1. `+`
2. `-`
3. `*`
4. `/`

Nếu operator khác:

- ném `ValueError`

#### `ast.UnaryOp` với `USub`

Hỗ trợ số âm unary.

#### `ast.Call`

Chỉ nhận nếu:

1. `node.func` là `ast.Name`
2. tên hàm nằm trong `_ALLOWED_FUNCTIONS`

Hiện `_ALLOWED_FUNCTIONS` chỉ có:

1. `max`
2. `min`
3. `abs`

Nếu hàm khác:

- ném `ValueError`

### 14.3 Điều gì bị cấm

Executor hiện không hỗ trợ:

1. attribute access
2. indexing
3. function lạ
4. boolean logic
5. comparison
6. assignment
7. statement blocks

Tức là executor hiện là:

- restricted symbolic arithmetic evaluator

## 15. Chu trình thực thi step-by-step trong `execute_plan`

### 15.1 Khởi tạo trace

Code tạo:

1. `environment`
2. `results = []`
3. `notes = [f"initial_bindings={len(environment)}"]`

### 15.2 Nếu plan không có steps

Nếu `not plan.steps`:

trả ngay `ExecutionTrace` với:

1. `step_results = []`
2. `final_value = None`
3. `success = False`
4. `error_message = "Executable plan has no steps"`
5. `confidence = 0.0`
6. note thêm:
   - `plan_has_no_steps`

Đây là lỗi runtime rất phổ biến khi compiler không tìm được chiến lược executable thật.

### 15.3 Với mỗi step trong plan

Code làm:

1. `resolved_inputs = []`
2. `missing_refs = [ref for ref in step.input_refs if ref not in environment]`

Nếu `missing_refs` không rỗng:

1. tạo một `ExecutionStepResult` failed
2. `notes = ["missing_input_refs"]`
3. trả luôn `ExecutionTrace` fail với note:
   - `execution_stopped_missing_refs`

### 15.4 Nếu input refs đầy đủ

Code lấy từng `ref` trong `step.input_refs`:

1. lookup `environment[ref]`
2. ép thành float
3. append vào `resolved_inputs`

### 15.5 Evaluate expression

Code gọi:

- `_evaluate_expression(step.expression, environment)`

Nếu bất kỳ exception nào xảy ra:

1. tạo `ExecutionStepResult` failed
2. note `expression_evaluation_failed`
3. trả trace fail với note:
   - `execution_stopped_exception`

### 15.6 Nếu evaluate thành công

1. `environment[step.output_ref] = output_value`
2. append `ExecutionStepResult` success với:
   - `resolved_inputs`
   - `output_value`
   - note `stored_as=<output_ref>`

### 15.7 Sau khi chạy hết các step

Nếu `plan.target_ref` **không có** trong `environment`:

1. trả trace fail
2. `error_message = "Target ref '<target_ref>' was not produced during execution"`
3. note thêm:
   - `target_ref_missing_after_execution`

Nếu target ref có trong environment:

1. `final_value = float(environment[plan.target_ref])`
2. tính `success_ratio = #successful_step_results / total_steps`
3. tính:

```python
confidence = min(plan.confidence * success_ratio + 0.08, 1.0)
```

4. trả `ExecutionTrace` success với note:
   - `target_ref=<plan.target_ref>`

## 16. Solver candidate được dựng thế nào

Trong `src/runtime/solver.py`, hàm:

- `build_solver_candidate(problem)`

làm rất ít việc:

1. `plan = compile_executable_plan(problem)`
2. trả `SolverCandidate(...)`

với:

1. `candidate_id = f"{plan.plan_id}_candidate"`
2. `executable_plan = plan`
3. `rendered_reasoning = None`
4. `selection_score = plan.confidence`
5. `selection_notes = plan.notes`

Điểm cần nắm:

- hệ hiện chỉ build **một** solver candidate deterministically
- chưa có search nhiều plan rồi chọn

## 17. Render solution text từ execution trace

Hàm:

- `_render_solution_text(plan, trace)`

trong `solver.py`

là cách canonical reference sinh ra lời giải text.

### 17.1 Cách nó map step -> result

1. tạo `outputs_by_step = {result.step_id: result for result in trace.step_results}`

### 17.2 Với mỗi step trong plan

Nếu step có result:

1. nếu result success và có `output_value`
   - append dòng:
     - `"{step.expression} = {result.output_value:g}"`
2. nếu fail
   - append dòng:
     - `"{step.expression} -> ERROR: {result.error_message}"`

### 17.3 Dòng cuối

Nếu trace success và `trace.final_value` có mặt:

- append:
  - `#### <final_value>`

Điểm quan trọng:

- `rendered_solution_text` hiện là **execution-derived text**
- không phải prose do model generate

## 18. Canonical reference được build như thế nào

Hàm:

- `build_canonical_reference(problem)`

là điểm cuối của runtime layer.

### 18.1 Trình tự

1. `candidate = build_solver_candidate(problem)`
2. `plan = candidate.executable_plan`
3. `trace = execute_plan(plan, problem)`

### 18.2 Nếu execution fail

Nếu:

1. `not trace.success`
2. hoặc `trace.final_value is None`

thì ném:

```python
ValueError(f"Unable to build canonical reference: {trace.error_message or 'execution failed'}")
```

Điểm này rất quan trọng:

- canonical reference chỉ tồn tại khi runtime thực thi thành công

### 18.3 Nếu execution thành công

Code tiếp tục:

1. `rendered_solution_text = _render_solution_text(plan, trace)`
2. tính `confidence`:

```python
min((problem.confidence + plan.confidence + trace.confidence) / 3, 0.98)
```

3. ghép `notes`:
   - `problem.notes`
   - `plan.notes`
   - `trace.notes`
   - thêm `canonical_reference_built`

4. trả `CanonicalReference(...)`

với:

1. `final_answer = trace.final_value`
2. `formalized_problem = problem`
3. `chosen_plan = plan`
4. `execution_trace = trace`
5. `rendered_solution_text`
6. `source_model = None`
7. `confidence`
8. `notes`

## 19. Quan hệ giữa compiler, validator, executor và solver

Đây là thứ dễ bị lẫn nếu chỉ nhìn bề ngoài.

### 19.1 Compiler

`compile_executable_plan(problem)` quyết định:

- chiến lược thực thi nào sẽ được dùng

Nó không tính ra kết quả số cuối.

### 19.2 Graph validator

`validate_problem_graph(problem)` kiểm:

- graph typed hiện tại có thể được compile/executed an toàn không

Nó không thực thi expression.

### 19.3 Executor

`execute_plan(plan, problem)`:

- thực thi expression thật sự theo environment

### 19.4 Solver

`build_canonical_reference(problem)`:

- ghép compiler + executor + render + packaging

Tức là:

1. compiler chọn plan
2. validator gác cổng graph path
3. executor tính ra số
4. solver đóng gói canonical artifact

## 20. Chỗ nào runtime hiện còn “semantic”

Runtime không hoàn toàn thuần execution engine.

Một phần semantic resolution vẫn còn trong:

1. `_resolved_relation(problem)`
2. `_select_rate_unit_price_quantity(problem)`
3. `_select_rate_unit_base_quantity(problem)`
4. lựa chọn compiler path theo relation type

Điều này có nghĩa:

- nếu graph path không compile được
- runtime vẫn phải dùng một lớp semantic fallback dựa trên relation candidates và note evidence

Tuy nhiên lớp này hiện đã bị siết lại:

- candidate yếu hoặc mơ hồ sẽ không tự động được nâng thành executable truth

## 21. Khi nào runtime sẽ cho ra lỗi `Executable plan has no steps`

Có 3 nguyên nhân logic chính:

1. graph path không compile được
2. relation fallback không tìm ra strategy executable
3. unknown plan cuối cùng trả `steps=[]`

Khi executor gặp plan rỗng:

- nó không cố suy tiếp
- nó trả trace fail ngay với:
  - `Executable plan has no steps`

## 22. Kết luận đúng với code hiện tại

Nếu phải mô tả thật ngắn nhưng chính xác runtime layer:

- Runtime hiện là một lớp deterministic chuyển `FormalizedProblem` thành một plan executable, kiểm graph nếu có, chạy plan bằng AST evaluator giới hạn, rồi đóng gói kết quả thành `CanonicalReference` chỉ khi trace thực thi thành công.

Nếu nén thành 4 khâu:

1. compile
2. validate
3. execute
4. package

Đó là cơ chế lõi hiện tại của `03_runtime_reference`.

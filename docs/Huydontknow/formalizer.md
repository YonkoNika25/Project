# Formalizer Pipeline (code-based)

Tài liệu này mô tả theo code hiện tại trong `src/formalizer` (không phải mô tả lý tưởng).
Mục tiêu: giúp bạn nhìn nhanh được pipeline, input/output của từng file và nhiệm vụ của từng khối chính.

## 1) Formalizer làm gì trong toàn hệ thống

`formalizer` có 2 nhánh chính:

1. `problem formalization`: biến `problem_text` thô thành `FormalizedProblem` (có quantity, target, relation, graph).
2. `student-work formalization`: biến `raw_answer` của học sinh thành `StudentWorkState` (có final answer, steps, semantic facts, student_graph).

Cả 2 nhánh dùng cùng pattern:

1. Heuristic draft (deterministic) để có anchor và fallback.
2. Nếu có `llm_client`: gọi LLM để sinh semantic sketch JSON.
3. Local compiler trong code compile sketch -> model typed.
4. Validate + repair.
5. Nếu LLM path fail: fallback về heuristic.

## 2) Contract dữ liệu chính (I/O cấp module)

Input thô:

1. `problem_text: str`
2. `raw_answer: str`
3. optional `llm_client`
4. optional `problem`, `reference`

Output chính:

1. `FormalizedProblem` (problem side)
2. `StudentWorkState` (student side)

Model nền quan trọng (trong `src/models/formalizer_schemas.py`):

1. `QuantityAnnotation`, `TargetSpec`, `RelationCandidate`
2. `ProblemGraph` + `ProblemGraphNode` + `ProblemGraphEdge`
3. `StudentStepAttempt`, `StudentSemanticFact`, `StudentWorkState`
4. `GraphValidationResult`, `GraphValidationIssue`

## 3) Call graph end-to-end

### 3.1 Problem side

`formalize_problem(...)` (`problem_formalizer.py`)

1. `_heuristic_formalize_problem(problem_text)` (`problem_formalizer_builder.py`)
2. nếu `llm_client is None` -> trả heuristic luôn
3. nếu có LLM -> `_llm_formalize_problem(...)` (`problem_formalizer_llm.py`)
4. `_llm_formalize_problem` retry tối đa 3 lần:
   1. build prompt từ heuristic anchor + feedback trước đó
   2. nhận semantic sketch JSON
   3. compile bằng `_build_formalized_problem_from_skeleton(...)`
   4. validate schema + graph runtime + semantic sanity
   5. pass -> trả refined
   6. fail -> feedback vào attempt tiếp theo
5. hết retry vẫn fail -> fallback heuristic + note lỗi

### 3.2 Student side

`formalize_student_work(...)` (`student_work.py`)

1. `_heuristic_formalize_student_work(raw_answer, problem, reference)` (`student_work_builder.py`)
2. nếu `llm_client is None` -> trả heuristic state
3. nếu có LLM -> `_llm_formalize_student_work(...)` (`student_work_llm.py`)
4. `_llm_formalize_student_work` retry tối đa 3 lần:
   1. build prompt từ heuristic anchor + feedback
   2. nhận semantic sketch JSON
   3. compile bằng `_build_student_work_from_sketch(...)`
   4. sanity validate bằng `_student_sanity_validation_result(...)`
   5. pass -> trả refined
   6. fail -> feedback vào attempt tiếp theo
5. hết retry vẫn fail -> fallback heuristic + note lỗi

## 4) Input/Output theo từng file trong `src/formalizer`

| File | Nhiệm vụ | Input chính | Output chính |
|---|---|---|---|
| `__init__.py` | Re-export public API | N/A | Hàm/public symbol để import tiện |
| `problem_formalizer.py` | Entry point public cho problem side | `problem_text`, `llm_client?` | `FormalizedProblem` |
| `problem_formalizer_extractors.py` | Extract evidence mức surface (regex/cues/entities) | `problem_text` | `evidence_pack` + projected quantities/target/relation |
| `problem_formalizer_builder.py` | Heuristic builder + compiler sketch -> typed problem | `problem_text`, `heuristic_problem`, `payload` | `FormalizedProblem` (+ `evidence_pack` ở heuristic path) |
| `problem_formalizer_llm.py` | Prompt + retry + accept policy cho problem sketch | `problem_text`, `heuristic_problem`, `heuristic_evidence`, `llm_client` | `FormalizedProblem` refined hoặc fallback |
| `problem_formalizer_validation.py` | Validate/repair local cho formalized problem | `FormalizedProblem` | `FormalizedProblem` repaired hoặc `GraphValidationResult` |
| `problem_graph.py` | Dựng `ProblemGraph` từ formalized problem | `FormalizedProblem` | `ProblemGraph` |
| `reference_trace.py` | Parse trace text (reference/student) thành symbolic trace | `solution_text` | `SymbolicTrace` + `TraceStep[]` |
| `student_work.py` | Entry point public cho student side | `raw_answer`, `problem?`, `reference?`, `llm_client?` | `StudentWorkState` |
| `student_work_builder.py` | Heuristic builder + compiler sketch -> typed student state | `raw_answer`, `heuristic_state`, `sketch`, `problem?` | `StudentWorkState` |
| `student_work_llm.py` | Prompt + retry + accept policy cho student sketch | `raw_answer`, `heuristic_state`, `problem?`, `reference?`, `llm_client` | `StudentWorkState` refined hoặc fallback |
| `student_work_validation.py` | Sanity validation cho student state | `StudentWorkState`, `problem?`, `reference?` | `GraphValidationResult` |
| `student_work_graph.py` | Build graph artifact cho bài làm học sinh | `StudentWorkState`, `problem?` | `ProblemGraph` hoặc `None` |

## 5) Block-level chi tiết theo file

## 5.1 `problem_formalizer.py`

Hàm chính: `formalize_problem(problem_text, llm_client=None)`

Input:

1. `problem_text` thô
2. optional `llm_client`

Output:

1. `FormalizedProblem`

Flow:

1. Luôn tạo `heuristic_problem` trước.
2. Không có LLM -> trả heuristic ngay.
3. Có LLM -> chạy nhánh LLM refine.
4. LLM lỗi (generation/build/type) -> fallback heuristic với note `llm_formalization_failed_fallback`.

## 5.2 `problem_formalizer_extractors.py`

Vai trò: tách evidence bề mặt từ đề, chưa phải semantic truth đầy đủ.

Block chính:

1. `_extract_target_span_candidates`: bắt candidate câu hỏi target.
2. `_extract_numeric_mentions`: bắt số + context + unit candidates + role hints.
3. `_extract_entities`: bắt entity dạng tên riêng.
4. `_extract_implicit_quantity_cues`: bắt verbal-number cues (`twice`, `hundred`, ...).
5. `_extract_lexical_cue_hits`: bắt cue family (`additive`, `subtractive`, `rate`, ...).
6. `_build_relation_candidates_from_cues`: map cue family -> relation candidates.
7. `_build_problem_anchor_evidence`: gói toàn bộ thành `evidence_pack`.
8. `_project_*_from_evidence`: convert evidence -> model typed (`QuantityAnnotation`, `TargetSpec`, `RelationCandidate`).

Input/Output block tiêu biểu:

1. `problem_text -> evidence_pack`
2. `evidence_pack -> quantities[]`
3. `evidence_pack -> target`
4. `evidence_pack + quantities + target -> relation_candidates`

## 5.3 `problem_formalizer_builder.py`

Đây là file orchestration quan trọng nhất của problem side.

### A. Heuristic path

Hàm: `_heuristic_formalize_problem(problem_text)`

Input:

1. `problem_text`

Output:

1. `(FormalizedProblem, evidence_pack)`

Flow:

1. build `evidence_pack` từ extractors
2. project quantities/entities/target/relation
3. tạo `FormalizedProblem` heuristic
4. `validate_formalized_problem(...)`
5. attach graph bằng `build_problem_graph(...)`

### B. LLM sketch compiler path

Hàm: `_build_formalized_problem_from_skeleton(problem_text, heuristic_problem, payload)`

Input:

1. `problem_text`
2. `heuristic_problem` (anchor)
3. `payload` (semantic sketch JSON từ LLM)

Output:

1. `FormalizedProblem` typed + graph

Các block con chính:

1. `_compile_quantities_from_semantic_sketch`: merge updates + semantic facts latent quantity.
2. `_build_target_payload_from_sketch`: compile target block.
3. `_build_relation_candidates_from_sketch`: compile relation block.
4. `_extract_graph_steps_from_payload` + `_normalize_graph_steps_for_builder`: chuẩn hóa skeleton step refs.
5. `validate_formalized_problem`: normalize/repair ở model level.
6. `_build_problem_graph_from_skeleton`: compile graph typed từ plan_steps.
7. `_apply_local_semantic_repairs`: dọn inconsistency local.
8. `_compare_with_heuristic_notes`: ghi note khác biệt so với heuristic.

## 5.4 `problem_formalizer_llm.py`

Vai trò: quản lý prompt + retry + acceptance.

Hàm chính: `_llm_formalize_problem(...)`

Input:

1. `problem_text`
2. `heuristic_problem`
3. `heuristic_evidence`
4. `llm_client`

Output:

1. refined `FormalizedProblem` hoặc heuristic fallback

Retry loop:

1. build prompt bằng `_build_llm_graph_prompt(...)`
2. gọi `llm_client.generate_json(...)`
3. compile sketch -> `_build_formalized_problem_from_skeleton(...)`
4. runtime validate graph (`validate_problem_graph` từ `src/runtime/graph_validator.py`)
5. semantic sanity validate (`_semantic_sanity_validation_result`)
6. fail -> convert issues thành `feedback_issues` cho attempt sau

## 5.5 `problem_formalizer_validation.py`

Vai trò: validator/repair local cho problem side.

Block chính:

1. `validate_formalized_problem`: dedupe entity/quantity, fallback target/relation, fill missing relation expression, recompute confidence.
2. `_apply_local_semantic_repairs`: sửa inconsistency target/quantity theo graph shape.
3. `_semantic_sanity_validation_result`: check domain-shape (ví dụ `RATE_UNIT_RELATION` phải có base/unit_rate/percent/threshold).
4. `_schema_validation_result`, `_missing_graph_validation_result`, `_graph_feedback_payload`: chuẩn hóa lỗi để feedback cho LLM retry.

Input/Output:

1. `FormalizedProblem -> FormalizedProblem` (repair path)
2. `ValidationError -> GraphValidationResult`
3. `GraphValidationResult -> feedback payload list[dict]`

## 5.6 `problem_graph.py`

Vai trò: dựng `ProblemGraph` typed từ `FormalizedProblem`.

Chiến lược build:

1. `_build_base_graph`: luôn add entity/quantity/target node trước.
2. resolve relation chính bằng `_resolved_relation`.
3. route theo relation type:
   1. `RATE_UNIT_RELATION` -> `_add_rate_subgraph` (multi-step template).
   2. additive/subtractive/multiplicative/partition -> `_add_single_step_subgraph`.
   3. còn lại -> `_add_expression_fallback_subgraph`.

Output:

1. `ProblemGraph` có node/edge/target_node_id/confidence/notes.

## 5.7 `reference_trace.py`

Vai trò: parser trace text dùng chung cho reference/student.

Hàm chính:

1. `strip_reference_markers`: chuẩn hóa line text.
2. `parse_trace_step`: parse 1 dòng thành `TraceStep`.
3. `build_reference_trace`: dựng `SymbolicTrace` cho lời giải chuẩn text.
4. `build_student_partial_trace`: dựng trace heuristic cho bài học sinh.

Input/Output:

1. `solution_text -> SymbolicTrace`
2. `line + step_index + final_value -> TraceStep`

## 5.8 `student_work.py`

Entry point public cho student side.

Hàm chính: `formalize_student_work(...)`

Input:

1. `raw_answer`
2. optional `problem`
3. optional `reference`
4. optional `llm_client`

Output:

1. `StudentWorkState`

Flow:

1. heuristic trước.
2. có LLM thì refine bằng sketch.
3. lỗi LLM path -> fallback heuristic + note.

## 5.9 `student_work_builder.py`

Đây là file orchestration quan trọng nhất của student side.

### A. Heuristic path

Hàm: `_heuristic_formalize_student_work(raw_answer, problem, reference)`

Input:

1. `raw_answer`
2. optional `problem`
3. optional `reference`

Output:

1. `StudentWorkState` heuristic + `student_graph`

Block con:

1. `_extract_final_answer`: lấy final answer từ cue regex.
2. `_build_step_attempts`: split step + parse trace từng dòng.
3. `_infer_mode`: suy mode parse (`final_answer_only`, `partial_trace`, ...).
4. `_attach_student_graph`: build graph artifact.

### B. LLM sketch compiler path

Hàm: `_build_student_work_from_sketch(raw_answer, heuristic_state, sketch, problem)`

Input:

1. raw text + heuristic anchor
2. sketch JSON từ LLM
3. optional `problem`

Output:

1. `StudentWorkState` typed + student graph

Block con chính:

1. compile semantic facts (`_build_student_semantic_facts_from_sketch`)
2. compile steps (`_build_student_steps_from_sketch`)
3. grounding/sanitize numeric claims (`_sanitize_student_step_payload`)
4. prune semantic facts không dùng (`_prune_student_semantic_facts`)
5. repair mode/target ref (`_reconcile_student_mode`, `_repair_selected_target_ref`)
6. validate bằng `StudentWorkState.model_validate`
7. attach graph LLM provenance

Điểm cần chú ý trong code hiện tại:

1. `_infer_selected_target_ref(...)` đang trả `None` cố định (chưa implement logic chọn target heuristic).

## 5.10 `student_work_llm.py`

Vai trò: prompt + retry loop cho student semantic sketch.

Hàm chính: `_llm_formalize_student_work(...)`

Input:

1. `raw_answer`
2. `heuristic_state`
3. optional `problem`
4. optional `reference`
5. `llm_client`

Output:

1. refined `StudentWorkState` hoặc heuristic fallback

Flow:

1. build prompt (`_build_llm_student_prompt`) với allowed refs/mode/operation.
2. gọi model.
3. compile sketch local.
4. sanity validate.
5. fail -> feedback cho retry.

## 5.11 `student_work_validation.py`

Vai trò: sanity validate student state sau compile.

Checks chính:

1. `selected_target_ref` phải nằm trong problem refs.
2. step `referenced_ids` chỉ được dùng allowed refs (problem refs + semantic fact ids).
3. mode consistency (`final_answer_only` không được có steps, trace mode phải có steps, ...).
4. parseable structure thì phải có `student_graph` + `target_node_id`.

Output:

1. `GraphValidationResult`
2. feedback payload qua `_student_feedback_payload`.

## 5.12 `student_work_graph.py`

Vai trò: dựng graph cho student để downstream alignment/evidence làm việc được.

Input:

1. `StudentWorkState`
2. optional `problem`
3. optional `provenance_override`

Output:

1. `ProblemGraph` hoặc `None` nếu không có cấu trúc parseable

Flow chính:

1. tạo node cho semantic facts/referenced refs.
2. với từng step: add operation node + input edges.
3. tạo output intermediate node khi có `extracted_value`.
4. nếu có final answer: tạo target node `student_final_answer` + target edges.

## 6) “Input/Output theo block” nhanh cho debug

### Problem side

1. `problem_text`
2. `_build_problem_anchor_evidence` -> `evidence_pack`
3. `_heuristic_formalize_problem` -> `(heuristic_problem, evidence_pack)`
4. `_build_llm_graph_prompt` -> `(system_prompt, user_prompt)`
5. `llm.generate_json` -> `semantic_sketch_payload`
6. `_build_formalized_problem_from_skeleton` -> `refined_formalized_problem`
7. `validate_problem_graph` + `_semantic_sanity_validation_result` -> `GraphValidationResult`
8. accept hoặc fallback

### Student side

1. `raw_answer`
2. `_heuristic_formalize_student_work` -> `heuristic_state`
3. `_build_llm_student_prompt` -> `(system_prompt, user_prompt)`
4. `llm.generate_json` -> `student_semantic_sketch`
5. `_build_student_work_from_sketch` -> `refined_state`
6. `_student_sanity_validation_result` -> `GraphValidationResult`
7. accept hoặc fallback

## 7) Checklist đọc code nhanh (gợi ý cho bạn)

1. Bắt đầu từ `problem_formalizer.py` + `student_work.py` để nắm entrypoint.
2. Qua `*_llm.py` để nắm retry/feedback.
3. Qua `*_builder.py` để nắm compiler local.
4. Qua `*_validation.py` để nắm guardrails.
5. Qua `problem_graph.py` và `student_work_graph.py` để nắm artifact graph cuối.


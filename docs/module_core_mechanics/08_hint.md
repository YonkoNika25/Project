# Cơ Chế Lõi Của Hint

Tài liệu này mô tả đúng tầng hint hiện tại, bám trực tiếp vào code trong:

- `src/hint/controller.py`
- `src/hint/generator.py`
- `src/hint/verifier.py`
- `src/hint/repair.py`
- `src/hint/__init__.py`
- các schema liên quan trong:
  - `src/models/schemas.py`
  - `src/models/formalizer_schemas.py`

Tầng này nhận đầu vào là:

1. `problem: FormalizedProblem`
2. `reference: CanonicalReference`
3. `diagnosis: DiagnosisResult`
4. `plan: HintPlan`
5. `hint_mode`
6. `llm_client` tùy chọn

và đầu ra là:

- `HintResult`

Điểm rất quan trọng:

- tầng hint không tự chẩn đoán lại
- không tự lập kế hoạch sư phạm lại
- nó nhận `HintPlan` như một contract phải tuân thủ
- rồi sinh hint text, verify, repair, fallback và đóng gói kết quả

## 1. Contract đầu ra: `HintResult`

Schema `HintResult` có:

1. `hint_text`
2. `hint_level`
3. `hint_mode`
4. `verification_passed`
5. `violated_rules`
6. `confidence`
7. `notes`

### 1.1 Invariant

Model validator chỉ kiểm một rule:

1. `hint_text` không được rỗng

Điều này có nghĩa:

- controller bắt buộc phải emit ra một chuỗi hint cuối cùng
- dù verification pass hay fail

## 2. Taxonomy hint dùng ở tầng này

### 2.1 `HintMode`

Từ `src/models/schemas.py`, gồm:

1. `normal`
2. `scaffolding`
3. `pedagogy_following`

Hiện tại mode này chủ yếu được:

1. truyền vào generator
2. truyền vào repair LLM
3. ghi lại trong `HintResult`

Code hiện chưa có branching sâu theo `HintMode` ở deterministic templates, nhưng vẫn giữ nó như một input contract.

### 2.2 `TeacherMove`

Hint layer đọc `plan.teacher_move` để quyết định:

1. deterministic hint template nào sẽ dùng
2. alignment verifier kỳ vọng loại semantic cue nào
3. repair layer nên rewrite theo kiểu nào
4. fallback hint sẽ là câu nào

Nghĩa là toàn bộ hint layer hiện bị chi phối mạnh bởi:

- `TeacherMove`

## 3. Entry point của hint layer

Hàm công khai chính:

- `build_hint_result(problem, reference, diagnosis, plan, hint_mode=HintMode.NORMAL, llm_client=None)`

nằm trong `src/hint/controller.py`.

Đây là controller của toàn bộ flow hint.

## 4. Controller flow tổng thể

`build_hint_result(...)` chạy đúng theo thứ tự:

1. gọi `generate_hint_text(...)`
2. gọi `verify_hint_text(hint_text, plan)`
3. nếu pass -> đóng `HintResult`
4. nếu fail -> gọi `repair_hint_text(...)`
5. verify lại repaired hint
6. nếu repaired hint pass -> dùng repaired hint
7. nếu repaired hint vẫn fail -> thử fallback hint
8. verify fallback hint
9. nếu fallback pass -> dùng fallback
10. nếu fallback vẫn fail -> giữ repaired hint và trả `verification_passed=False`

Điểm cần nắm:

- hint layer hiện là **generate -> verify -> repair -> verify -> fallback**
- không phải chỉ generate xong trả luôn

## 5. `_fallback_hint(plan)` làm gì

Đây là hint deterministic cực ngắn cuối cùng để cứu hệ khi generate và repair không ra được hint pass verifier.

Nó map theo `plan.teacher_move`:

### 5.1 `REFOCUS_TARGET`

Trả:

- `"Read the question again and decide what quantity you still need to find."`

### 5.2 `CHECK_RELATIONSHIP`

Trả:

- `"Think about how the quantities should be related before you calculate."`

### 5.3 `RECOMPUTE_STEP`

Trả:

- `"Check that arithmetic step carefully and try it again."`

### 5.4 `CONTINUE_FROM_STEP`

Trả:

- `"Use the quantities you already found and recompute the last step carefully."`

### 5.5 `METACOGNITIVE_PROMPT`

Trả:

- `"Restate what the problem is asking for and give one clear numeric answer."`

### 5.6 Default

Nếu không khớp teacher move nào:

- `"Your answer is correct."`

Fallback này không nhìn problem, reference hay diagnosis.

Nó chỉ nhìn:

- `TeacherMove`

## 6. Bước 1 của controller: `generate_hint_text`

Hàm:

- `generate_hint_text(problem, reference, diagnosis, plan, hint_mode, llm_client=None)`

nằm trong `src/hint/generator.py`.

### 6.1 Logic tổng quát

1. nếu `llm_client is None`
   - dùng `_deterministic_hint_text(problem, plan)`
2. nếu có `llm_client`
   - thử `_llm_hint_text(...)`
3. nếu `_llm_hint_text(...)` fail
   - fallback sang `_deterministic_hint_text(problem, plan)`

Tức là generator hiện là:

- deterministic baseline
- LLM optional
- deterministic fallback

## 7. `_target_prompt(problem)` làm gì

Helper này lấy:

1. nếu `problem.target` có mặt:
   - `problem.target.surface_text.rstrip("?")`
2. nếu không:
   - `"what quantity the problem is asking for"`

Hàm này là nguồn ngôn ngữ chung cho nhiều deterministic hint templates.

## 8. Deterministic hint generation: `_deterministic_hint_text`

Đây là lớp template-based hint generator.

Input:

1. `problem`
2. `plan`

Nó chỉ dùng:

1. `target_prompt`
2. `plan.teacher_move`

### 8.1 `RESTATE_RESULT`

Trả:

- `"Your answer is correct."`

### 8.2 `REFOCUS_TARGET`

Trả 2 câu:

1. `Look back at <target_prompt>.`
2. `Ask yourself whether your current result is the final quantity or only an intermediate value.`

### 8.3 `CHECK_RELATIONSHIP`

Trả 2 câu:

1. `Before calculating again, decide how the quantities should be related.`
2. `Ask whether this step should combine, compare, or apply a rate to the values in the problem.`

### 8.4 `RECOMPUTE_STEP`

Trả 2 câu:

1. `Recheck the arithmetic in the step you just computed.`
2. `Write that calculation again carefully before you move on.`

### 8.5 `CONTINUE_FROM_STEP`

Trả 2 câu:

1. `Your setup looks close, so pause before the last computation.`
2. `Use the quantities you already found and recompute the final step carefully.`

### 8.6 `METACOGNITIVE_PROMPT`

Trả 2 câu:

1. `Restate <target_prompt> in your own words.`
2. `Then give one clear numeric answer.`

### 8.7 Default

Nếu teacher move không khớp:

1. `Pause and think about <target_prompt>.`
2. `Check what the problem is asking for before you continue.`

### 8.8 Ý nghĩa

Deterministic generator hiện hoàn toàn template-based theo `TeacherMove`.

Nó không dùng:

1. `diagnosis.summary`
2. `plan.focus_points`
3. `plan.must_not_reveal`

ở tầng deterministic generation cơ bản.

Những thứ đó sẽ đi vào verifier/repair.

## 9. LLM hint generation: `_llm_hint_text`

Đây là nhánh generate bằng model.

### 9.1 System prompt

Prompt nói rõ:

1. model là math tutor
2. chỉ được trả JSON với đúng một field `hint_text`
3. tối đa 2 câu
4. phải follow pedagogy plan
5. không được reveal forbidden content

### 9.2 User prompt chứa gì

Prompt hiện truyền cho model:

1. `Problem target`
2. `Diagnosis` ở dạng JSON
3. `Pedagogy plan` ở dạng JSON
4. `Reference answer (must not be revealed): <value>`
5. `Hint mode`

Sau đó yêu cầu:

- return JSON như `{"hint_text": "..."}`

### 9.3 Cách engine gọi LLM

Code gọi:

```python
payload = llm_client.generate_json(
    task_name="hint_generator",
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    temperature=0.4,
    max_tokens=1000,
)
```

### 9.4 Validation cục bộ

Sau khi model trả payload:

1. lấy `hint_text = str(payload.get("hint_text", "")).strip()`
2. nếu rỗng:
   - raise `LLMGenerationError("LLM hint generator returned empty hint_text")`

### 9.5 Fallback

Nếu `_llm_hint_text(...)` ném:

1. `LLMGenerationError`
2. `ValueError`
3. `TypeError`

thì `generate_hint_text(...)` trả deterministic hint thay thế.

## 10. Bước 2 của controller: verify hint

Sau khi có `hint_text`, controller gọi:

- `verify_hint_text(hint_text, plan)`

Hàm này nằm trong `src/hint/verifier.py`.

`verify_hint_text(...)` chỉ làm:

1. `check_no_spoiler(...)`
2. `check_alignment(...)`
3. concatenate violations từ hai hàm

## 11. Normalization và tokenization trong verifier

Verifier có hai helper nền:

### 11.1 `_normalize(text)`

1. lower-case
2. collapse whitespace
3. strip

### 11.2 `_content_tokens(text)`

1. tokenize bằng regex `[a-z]+`
2. bỏ `_CONTENT_STOPWORDS`
3. chỉ giữ token có độ dài >= 3

Stopwords hiện gồm các từ chức năng như:

1. `a`
2. `an`
3. `and`
4. `before`
5. `for`
6. `the`
7. `use`
8. `what`
9. `your`

Mục đích:

- verifier nhìn semantic content tokens, không nhìn mọi token thô

## 12. Safe focus points trong verifier

Hàm:

- `_safe_focus_points(plan)`

### 12.1 Logic

1. lấy content tokens của toàn bộ `plan.must_not_reveal`
2. hợp chúng thành `hidden_tokens`
3. với mỗi `focus_point`:
   - lấy tokens của focus point
   - nếu token set rỗng -> bỏ
   - nếu toàn bộ token của focus point là subset của `hidden_tokens` -> bỏ
   - ngược lại giữ

### 12.2 Ý nghĩa

Planner có thể đưa focus points chứa nội dung nhạy cảm.

Verifier khi check alignment sẽ chỉ dùng:

- focus points đã được lọc là “safe”

để tránh ép hint lặp lại chính nội dung bị cấm.

## 13. Spoiler checking: `check_no_spoiler`

Hàm:

- `check_no_spoiler(hint_text, plan)`

đây là lớp chống lộ đáp án / lộ intermediate.

### 13.1 Chuẩn bị

1. `normalized_hint = _normalize(hint_text)`
2. `hint_numbers = {mọi số trong hint_text, bỏ dấu phẩy}`

### 13.2 Duyệt từng item trong `plan.must_not_reveal`

Với mỗi `hidden`:

1. normalize hidden
2. nếu hidden rỗng -> bỏ qua

### 13.3 Case 1: hidden là số

Nếu `_NUMBER_PATTERN.fullmatch(hidden.replace(",", ""))`:

1. nếu hidden number nằm trong `hint_numbers`
   - violation:
     - `reveals_hidden_number:<hidden>`

### 13.4 Case 2: hidden là text literal

Nếu `normalized_hidden in normalized_hint`:

- violation:
  - `reveals_hidden_text:<hidden>`

### 13.5 Case 3: hidden semantics qua token subset

Nếu:

1. `hidden_tokens = _content_tokens(hidden)`
2. `hint_tokens = _content_tokens(hint_text)`
3. `len(hidden_tokens) >= 2`
4. và `hidden_tokens.issubset(hint_tokens)`

thì:

- violation:
  - `reveals_hidden_semantics:<hidden>`

### 13.6 Ý nghĩa

Verifier hiện không chỉ bắt literal leak.

Nó còn bắt một dạng semantic overlap sơ bộ qua token set.

Tuy nhiên đây vẫn là heuristic token-based, không phải semantic entailment thật.

## 14. Alignment checking: `check_alignment`

Hàm:

- `check_alignment(hint_text, plan)`

kiểm hint có đang đi đúng teacher move và focus points không.

### 14.1 Chuẩn bị

1. `normalized_hint = _normalize(hint_text)`
2. `sentence_count` = số câu tách bằng `[.!?]+`

### 14.2 `semantic_cue_map`

Verifier map mỗi `TeacherMove` sang một set semantic tokens kỳ vọng:

#### `REFOCUS_TARGET`

1. `question`
2. `target`
3. `quantity`
4. `intermediate`
5. `final`
6. `find`

#### `CHECK_RELATIONSHIP`

1. `combine`
2. `compare`
3. `relationship`
4. `related`
5. `rate`
6. `setup`

#### `RECOMPUTE_STEP`

1. `recheck`
2. `recompute`
3. `calculation`
4. `arithmetic`
5. `carefully`

#### `CONTINUE_FROM_STEP`

1. `final`
2. `last`
3. `continue`
4. `next`
5. `step`
6. `recompute`

#### `RESTATE_RESULT`

1. `correct`

#### `METACOGNITIVE_PROMPT`

1. `restate`
2. `words`
3. `numeric`
4. `answer`
5. `asking`

### 14.3 Expected tokens và focus tokens

1. `hint_tokens = _content_tokens(hint_text)`
2. `expected_tokens = semantic_cue_map.get(plan.teacher_move, set())`
3. `focus_tokens` = union token của `_safe_focus_points(plan)`

### 14.4 Rule 1: teacher move alignment

Nếu:

1. `expected_tokens` không rỗng
2. và không có intersection giữa:
   - `expected_tokens` và `hint_tokens`
   - `focus_tokens` và `hint_tokens`

thì violation:

- `teacher_move_alignment_failed`

### 14.5 Rule 2: focus point alignment

Nếu:

1. `focus_tokens` không rỗng
2. và `focus_tokens` không intersect `hint_tokens`

thì violation:

- `focus_point_alignment_failed`

### 14.6 Rule 3: conceptual hint quá computational

Nếu:

1. `plan.hint_level.value == "conceptual"`
2. và `plan.disclosure_budget <= 1`
3. và `"calculate"` nằm trong `normalized_hint`

thì violation:

- `conceptual_hint_too_computational`

### 14.7 Rule 4: hint quá dài

Nếu `sentence_count > 2`:

- violation:
  - `hint_too_long`

### 14.8 Ý nghĩa

Alignment verifier hiện là:

- token-semantic checker theo teacher move và focus points

Nó đã vượt qua mức keyword literal rất đơn giản, nhưng vẫn chưa phải semantic verifier thực sự.

## 15. Bước 3 của controller: repair hint

Nếu verification fail, controller gọi:

- `repair_hint_text(problem, reference, diagnosis, plan, original_hint, hint_mode, llm_client=None)`

Repair layer nằm trong `src/hint/repair.py`.

## 16. Repair helper nền

### 16.1 `_normalize_whitespace(text)`

1. collapse whitespace
2. strip

### 16.2 `_split_sentences(text)`

1. normalize whitespace
2. split bằng `(?<=[.!?])\s+`
3. trả về danh sách câu không rỗng

### 16.3 `_join_sentences(sentences, limit=2)`

1. lấy tối đa `limit` câu đầu
2. strip từng câu
3. join bằng khoảng trắng

Mục đích:

- ép candidate hint về tối đa 2 câu

## 17. Xóa hidden content: `_remove_hidden_content`

Đây là repair primitive quan trọng nhất.

### 17.1 Với từng item trong `plan.must_not_reveal`

Code sort hidden items theo độ dài giảm dần.

### 17.2 Nếu hidden là số

Nếu `hidden_number` match `_NUMBER_PATTERN`:

Code replace literal đó bằng:

- `"that value"`

### 17.3 Nếu hidden là text

Code remove literal hidden text khỏi hint bằng regex ignore-case.

### 17.4 Cleanup hậu xử lý

Sau khi remove/replace:

1. xóa `() rỗng`
2. dọn whitespace trước punctuation
3. collapse multiple spaces
4. strip các ký tự thừa đầu/cuối

### 17.5 Ý nghĩa

Đây là literal content scrubber, không phải semantic rewrite đầy đủ.

## 18. Safe focus points trong repair

Hàm:

- `_safe_focus_points(plan)`

ở repair layer khác với verifier một chút về triển khai nhưng cùng mục tiêu:

1. normalize từng focus point
2. bỏ point rỗng
3. bỏ point chứa hidden content
4. giữ lại focus point an toàn

## 19. Teacher-move rewrite: `_teacher_move_rewrite`

Đây là deterministic rewrite an toàn từ scratch nếu original hint quá bẩn.

Input:

1. `problem`
2. `plan`

### 19.1 Chuẩn bị

1. lấy `target_prompt` từ `problem.target.surface_text` hoặc fallback
2. lấy `safe_focus = _safe_focus_points(plan)`
3. lấy `focus_fragment = safe_focus[0]` nếu có

### 19.2 Mapping theo `TeacherMove`

#### `RESTATE_RESULT`

- `"Your answer is correct."`

#### `REFOCUS_TARGET`

2 câu:

1. đọc lại câu hỏi
2. phân biệt current result là final hay intermediate

#### `CHECK_RELATIONSHIP`

1. câu đầu luôn: decide how quantities are related
2. câu hai:
   - nếu có `focus_fragment` -> `Focus on <focus_fragment>.`
   - nếu không -> generic combine/compare/rate sentence

#### `RECOMPUTE_STEP`

1. câu đầu: setup looks close, recheck arithmetic step
2. câu hai:
   - nếu có `focus_fragment` -> `Use <focus_fragment> as your checkpoint.`
   - nếu không -> generic rewrite-the-calculation sentence

#### `CONTINUE_FROM_STEP`

1. câu đầu: pause before final computation
2. câu hai:
   - nếu có `focus_fragment` -> `Use <focus_fragment> to guide the last step.`
   - nếu không -> generic recompute last step sentence

#### `METACOGNITIVE_PROMPT`

1. câu đầu: restate target prompt in your own words
2. câu hai:
   - nếu có `focus_fragment` -> `Keep your focus on <focus_fragment>.`
   - nếu không -> `Then give one clear numeric answer.`

#### Default

Generic target-oriented prompt.

### 19.3 Ý nghĩa

Đây là deterministic rewrite bám sát teacher move và focus points an toàn, không dùng original hint.

## 20. Minimal repair: `_minimal_repair_text`

Đây là nỗ lực repair “ít đụng nhất có thể”.

### 20.1 Các bước

1. `repaired = _remove_hidden_content(original_hint, plan)`
2. `sentences = _split_sentences(repaired)`
3. nếu không còn câu nào -> trả `""`
4. `candidate = _join_sentences(sentences, limit=2)`
5. `normalized_candidate = candidate.lower()`

### 20.2 Patching thiếu semantic cue theo teacher move

Sau đó, hàm kiểm từng `TeacherMove` xem candidate có thiếu cue cần thiết không.

#### Với `REFOCUS_TARGET`

Nếu candidate không chứa một trong:

1. `question`
2. `asking`
3. `quantity`
4. `intermediate`
5. `final`

thì append thêm câu:

- `Read the question again and decide what you still need to find.`

#### Với `CHECK_RELATIONSHIP`

Nếu candidate thiếu các cue như:

1. `combine`
2. `compare`
3. `rate`
4. `relationship`

thì append thêm câu:

- `Think about how the quantities should be related before you calculate.`

#### Với `RECOMPUTE_STEP`

Nếu candidate thiếu các cue:

1. `recheck`
2. `carefully`
3. `step`
4. `calculation`

thì append:

- `Recheck that calculation carefully before moving on.`

#### Với `CONTINUE_FROM_STEP`

Nếu candidate thiếu:

1. `final`
2. `step`
3. `recompute`
4. `setup`

thì append:

- `Use the values you already found and recompute the final step carefully.`

#### Với `METACOGNITIVE_PROMPT`

Nếu candidate thiếu:

1. `restate`
2. `own words`
3. `numeric answer`

thì append:

- `Restate the question in your own words, then give one clear numeric answer.`

### 20.3 Softening conceptual hints

Nếu:

1. `plan.hint_level.value == "conceptual"`
2. và `plan.disclosure_budget <= 1`

thì:

1. replace `calculate` -> `think`
2. replace `compute` -> `reason`

Điều này nhằm tránh conceptual hint trở nên quá computational.

### 20.4 Output cuối

`_normalize_whitespace(candidate)`

### 20.5 Ý nghĩa

Minimal repair cố giữ tối đa câu gốc, nhưng:

1. scrub spoiler
2. giới hạn 2 câu
3. vá semantic cue tối thiểu

## 21. LLM repair: `_llm_repair_text`

Nếu deterministic repair chưa đủ, repair layer có thể gọi model.

### 21.1 System prompt

Prompt nói:

1. model là hint repairer
2. chỉ được trả JSON có `hint_text`
3. tối đa 2 câu
4. phải preserve teacher move
5. phải remove spoilers và forbidden content
6. nếu original unusable thì rewrite từ scratch

### 21.2 User prompt chứa gì

1. problem target
2. original hint
3. violations
4. diagnosis JSON
5. pedagogy plan JSON
6. reference final answer
7. hint mode

### 21.3 Gọi model

Code gọi:

```python
llm_client.generate_json(
    task_name="hint_repair",
    system_prompt=...,
    user_prompt=...,
    temperature=0.2,
    max_tokens=1000,
)
```

### 21.4 Validation cục bộ

Nếu `hint_text` rỗng:

- raise `LLMGenerationError`

## 22. `repair_hint_text(...)` chạy theo thứ tự nào

Đây là controller con của repair layer.

Thứ tự:

### 22.1 Attempt 1: minimal candidate

1. `minimal_candidate = _minimal_repair_text(original_hint, plan)`
2. nếu candidate không rỗng:
   - verify lại bằng:
     - `check_no_spoiler(minimal_candidate, plan)`
     - `check_alignment(minimal_candidate, plan)`
3. nếu không có violation:
   - return `HintRepairResult`
   - notes:
     - `hint_repair_attempted`
     - `hint_repair:minimal_edit`

### 22.2 Attempt 2: guided rewrite

Nếu minimal candidate fail:

1. `rewrite_candidate = _teacher_move_rewrite(problem, plan)`
2. verify lại
3. nếu pass:
   - return notes:
     - `hint_repair_attempted`
     - `hint_repair:guided_rewrite`

### 22.3 Attempt 3: LLM rewrite

Nếu guided rewrite fail và có `llm_client`:

1. thử `_llm_repair_text(...)`
2. nếu LLM thành công:
   - return notes:
     - `hint_repair_attempted`
     - `hint_repair:llm_rewrite`
3. nếu LLM fail:
   - bỏ qua

### 22.4 Fallback cuối của repair layer

Nếu mọi thứ fail:

1. return `rewrite_candidate`
2. notes:
   - `hint_repair_attempted`
   - `hint_repair_unresolved`

Lưu ý:

- `repair_hint_text(...)` không tự đảm bảo candidate cuối của nó đã pass verifier
- việc verify lại được controller ngoài làm tiếp

## 23. Bước 4 của controller: sau repair thì làm gì

Quay lại `build_hint_result(...)`.

### 23.1 Nếu verification ban đầu fail

Code gọi:

- `repair_result = repair_hint_text(...)`

Sau đó verify lại:

- `repaired_violations = verify_hint_text(repair_result.hint_text, plan)`

### 23.2 Nếu repaired hint pass

Controller:

1. dùng `repair_result.hint_text`
2. `violated_rules = []`
3. `verification_passed = True`
4. `notes.extend(repair_result.notes)`
5. append:
   - `used_repaired_hint`

### 23.3 Nếu repaired hint vẫn fail

Controller thử fallback hint:

1. `fallback = _fallback_hint(plan)`
2. `fallback_violations = verify_hint_text(fallback, plan)`

#### Nếu fallback pass

1. dùng `fallback`
2. clear violations
3. `verification_passed = True`
4. notes append:
   - `used_fallback_hint`

#### Nếu fallback vẫn fail

1. giữ `repair_result.hint_text`
2. `violated_rules = repaired_violations`
3. `verification_passed = False`
4. notes append:
   - `fallback_hint_still_failed_verification`

Điểm này rất quan trọng:

- controller có thể trả ra một hint **không pass verification**
- nhưng khi đó `verification_passed=False` và violations được giữ lại

## 24. Confidence của `HintResult`

Cuối controller, code tính:

```python
confidence = min(plan.confidence + (0.04 if verification_passed else -0.1), 0.97)
confidence = max(confidence, 0.2)
```

Nghĩa là:

1. nếu pass verifier:
   - cộng `0.04`
2. nếu fail verifier:
   - trừ `0.1`
3. cap trên `0.97`
4. floor dưới `0.2`

### 24.1 Ý nghĩa

Hint confidence hiện là:

- pedagogy confidence đã được điều chỉnh theo trạng thái verification

## 25. Kết cấu cuối của `HintResult`

Controller return:

1. `hint_text`
2. `hint_level = plan.hint_level`
3. `hint_mode`
4. `verification_passed`
5. `violated_rules`
6. `confidence`
7. `notes`

Điểm cần nắm:

- `hint_level` ở result không được generator quyết định
- nó được propagate từ `HintPlan`

## 26. Chỗ nào là deterministic, chỗ nào là LLM trong hint layer

Đây là ranh giới vai trò rất rõ trong code hiện tại.

### 26.1 Deterministic

Deterministic hoàn toàn ở:

1. `_fallback_hint`
2. `_deterministic_hint_text`
3. `check_no_spoiler`
4. `check_alignment`
5. `_remove_hidden_content`
6. `_teacher_move_rewrite`
7. `_minimal_repair_text`
8. toàn bộ orchestration trong `build_hint_result`

### 26.2 LLM

LLM chỉ xuất hiện ở:

1. `_llm_hint_text`
2. `_llm_repair_text`

### 26.3 Vai trò thực sự của LLM

LLM hiện không được tin ngay.

Mọi output của nó đều phải đi qua:

1. verifier
2. và có thể bị repair / fallback

## 27. Chỗ nào là “lõi tận cùng” của tầng hint

Nếu nhìn đúng vào code, lõi của hint layer nằm ở 4 giao diện:

### 27.1 Generator

Sinh candidate hint text từ:

- `problem + diagnosis + plan + hint_mode`

### 27.2 Verifier

Check hai thứ:

1. spoiler
2. alignment với pedagogy plan

### 27.3 Repair

Nếu verifier fail:

1. scrub / patch / rewrite hint

### 27.4 Controller

Điều phối:

1. generate
2. verify
3. repair
4. verify
5. fallback
6. package

## 28. Kết luận đúng với code hiện tại

Nếu phải mô tả thật ngắn nhưng chính xác:

- Tầng hint hiện là một pipeline generate-then-verify: nó sinh hint từ `HintPlan`, kiểm spoiler và alignment, thử repair theo thứ tự deterministic rồi LLM nếu cần, sau đó fallback về một hint an toàn tối thiểu nếu vẫn chưa pass, và cuối cùng đóng gói kết quả thành `HintResult`.

Nếu nén thành 5 khâu:

1. hint generation
2. spoiler/alignment verification
3. deterministic repair
4. optional LLM rewrite
5. fallback and packaging

Đó là cơ chế lõi hiện tại của `08_hint`.

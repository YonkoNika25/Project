# Cơ Chế Lõi Của Problem Parsing

Tài liệu này chỉ mô tả **problem-side parsing heuristic** hiện tại, bám trực tiếp vào code đang chạy trong:

- `src/formalizer/problem_formalizer_extractors.py`
- `src/formalizer/problem_formalizer_builder.py`

Tài liệu này **không** đi sang:

- LLM semantic sketch
- compiler từ sketch sang `FormalizedProblem`
- runtime / canonical reference
- student side

Mục tiêu ở đây là bóc đúng **lõi tận cùng** của tầng parsing hiện tại: dữ liệu gì đi vào, từng hàm làm gì, commit điều gì, không commit điều gì, và artifact gốc thật sự của tầng này là gì.

## 1. Tầng này hiện đóng vai trò gì

Sau refactor, tầng này không còn được thiết kế như một “parser giải nghĩa gần xong”.

Nó đang làm 4 việc:

1. chia `problem_text` thành các span bề mặt có thể đánh chỉ mục được
2. phát hiện các tín hiệu bề mặt:
   - số
   - từ khóa quan hệ
   - verbal-number cues
   - candidate target question
3. đóng gói các tín hiệu này thành một `evidence_pack`
4. project một lớp `FormalizedProblem` heuristic rất mỏng chỉ để nối sang phần sau

Điểm rất quan trọng:

- **artifact gốc** của tầng parsing này là `evidence_pack`
- `FormalizedProblem` heuristic ở đây chỉ là **projection / adapter**, không phải “sự thật semantic đã được resolve”

## 2. Điểm vào thật sự nằm ở đâu

Trong [problem_formalizer_builder.py](C:/Users/linhn/Desktop/Dự án/src/formalizer/problem_formalizer_builder.py), hàm:

- `_heuristic_formalize_problem(problem_text)`

là nơi gọi parsing heuristic hiện tại.

Trình tự đầu hàm này là:

1. `cleaned_text = (problem_text or "").strip()`
2. `evidence_pack = _build_problem_anchor_evidence(cleaned_text)`

Điều này có nghĩa:

- parsing layer bây giờ không bắt đầu bằng “suy unit”, “suy relation”, “attach target”
- nó bắt đầu bằng **xây evidence pack**

Đó là thay đổi kiến trúc cốt lõi nhất của phần problem parsing.

## 3. `evidence_pack` gồm những gì

Hàm:

- `_build_problem_anchor_evidence(problem_text)`

trả về đúng một `dict` gồm các khóa:

1. `problem_text`
2. `sentence_spans`
3. `numeric_mentions`
4. `implicit_quantity_cues`
5. `lexical_cues`
6. `target_span_candidates`
7. `target_link_candidates`
8. `relation_candidates`
9. `entity_candidates`

Đây là thứ phải đọc trước nếu muốn hiểu parser thật sự đang làm gì.

Mỗi khóa này là kết quả của một extractor riêng, và các extractor đó đều đang hoạt động theo kiểu:

- lấy tín hiệu bề mặt
- tạo candidate
- gắn provenance / rule source

chứ không resolve ngữ nghĩa cuối cùng.

## 4. Tách câu: `_split_sentences`

Hàm:

- `_split_sentences(text)`

được định nghĩa trong [problem_formalizer_extractors.py](C:/Users/linhn/Desktop/Dự án/src/formalizer/problem_formalizer_extractors.py).

### 4.1 Regex đang dùng

```python
r"[^.!?]+[.!?]?"
```

### 4.2 Nó thực sự làm gì

Với toàn bộ chuỗi `text`, regex này sẽ:

1. lấy một đoạn liên tục không chứa `. ! ?`
2. nếu ngay sau đó có đúng một dấu `.`, `!`, hoặc `?` thì lấy kèm
3. lặp lại cho đến hết chuỗi

Sau đó code:

1. `strip()` từng đoạn
2. nếu đoạn không rỗng thì lưu lại

Mỗi phần tử kết quả có dạng:

1. `sentence`
2. `start`
3. `end`

### 4.3 Điều nó không làm

Hàm này không:

1. parse cú pháp
2. phân biệt mệnh đề chính / phụ
3. xử lý trích dẫn thông minh
4. hiểu abbreviation

Nó chỉ là utility để:

1. tạo `sentence_spans`
2. giúp các mention khác biết chúng nằm ở câu nào

Nói cách khác, đây là **indexing utility**, không phải parser cú pháp.

## 5. Trích target question candidates: `_extract_target_span_candidates`

Hàm:

- `_extract_target_span_candidates(problem_text)`

là nơi tạo danh sách các câu / span **có khả năng** là target question.

### 5.1 Điểm cần nắm trước

Hàm này **không** quyết định “đây là target duy nhất đúng”.

Nó chỉ sinh candidate.

### 5.2 Bước chuẩn bị

1. `text = (problem_text or "").strip()`
2. nếu `text` rỗng, trả `[]`
3. tạo:
   - `candidates = []`
   - `seen_spans = set()`
   - `sentences = _split_sentences(text)`

### 5.3 Internal helper `_append_candidate`

Mỗi candidate được thêm qua helper `_append_candidate(surface_text, start, end, rule_source)`.

Helper này làm:

1. tạo `span = (start, end)`
2. nếu span đã có trong `seen_spans` thì bỏ qua
3. nếu chưa có thì thêm vào `seen_spans`
4. suy `unit_candidate` rất nhẹ:
   - nếu có `how much` -> `dollars`
   - nếu có `how many` -> lấy token ngay sau `many`
5. tạo dict candidate gồm:
   - `surface_text`
   - `normalized_question`
   - `target_variable`
   - `unit_candidate`
   - `char_start`
   - `char_end`
   - `rule_source`
   - `confidence`

### 5.4 `_TARGET_QUESTION_PATTERN` đang là gì

Regex:

```python
r"((?:if\b.*?,\s*)?(?:how many|how much|what|which|who|where|when|why)[^?]*\?)"
```

Nghĩa thực tế:

1. cho phép một prefix kiểu `if ...,`
2. sau đó phải bắt đầu bằng một từ hỏi trong tập:
   - `how many`
   - `how much`
   - `what`
   - `which`
   - `who`
   - `where`
   - `when`
   - `why`
3. rồi lấy mọi thứ đến dấu `?`

### 5.5 Ba nguồn candidate thật sự

Hàm này lấy candidate từ 3 nguồn:

1. `matched_wh_question`
   - nếu regex trên match được
2. `question_sentence`
   - với mọi sentence có chứa `?`
3. `final_sentence_fallback`
   - luôn thêm câu cuối cùng của văn bản nếu có

### 5.6 `target_variable` được tạo như thế nào

Qua `_slugify(surface_text, fallback="answer")`.

Hàm `_slugify` làm:

1. lower-case toàn bộ
2. thay mọi cụm không phải `[a-z0-9]` bằng `_`
3. cắt `_` ở đầu / cuối
4. nếu rỗng thì dùng `fallback`

Ví dụ:

- `How many people were on the first ship?`

sẽ thành:

- `how_many_people_were_on_the_first_ship`

### 5.7 `unit_candidate` ở target candidate được suy như thế nào

Code hiện chỉ có 2 rule mỏng:

1. nếu câu hỏi có `how much`
   - `unit_candidate = "dollars"`
2. nếu có `how many`
   - tokenize bằng `[A-Za-z]+`
   - tìm token `many`
   - lấy token ngay sau nó làm `unit_candidate`

Điểm này vẫn còn heuristic, nhưng bây giờ nó chỉ là:

- target-side unit candidate

chứ không phải target semantic resolution cuối cùng.

## 6. Trích entity: `_extract_entities`

Hàm:

- `_extract_entities(problem_text)`

dùng regex `_ENTITY_PATTERN`:

```python
\b(?:(Mr|Mrs|Ms|Dr)\.\s+[A-Z][a-z]+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b
```

### 6.1 Nó bắt được kiểu gì

1. title + tên:
   - `Mr. Brown`
   - `Dr. Smith`
2. multi-word capitalized names:
   - `New York`
   - `Alice Johnson`

### 6.2 Nó làm gì sau khi match

1. lấy `surface = match.group(0).strip()`
2. dùng lowercase `surface` làm key để dedupe
3. nếu chưa thấy thì tạo `ProblemEntity` với:
   - `entity_id`
   - `surface_text`
   - `normalized_name`
   - `entity_type`
   - `metadata = {"char_start", "char_end"}`

### 6.3 Điều cần lưu ý

Đây không phải NER thật sự.

Nó là regex-based entity spotting.

## 7. Trích numeric mentions: `_extract_numeric_mentions`

Đây là lõi quan trọng nhất của parser bề mặt.

Hàm:

- `_extract_numeric_mentions(problem_text, target_candidates)`

### 7.1 Regex đang dùng

`_NUMBER_PATTERN`:

```python
-?\$?\d[\d,]*\.?\d*%?
```

### 7.2 Regex này bắt được gì

1. `847`
2. `$40`
3. `5%`
4. `1,200`
5. `-3.5`

### 7.3 Nó không bắt được gì

1. `three hundred`
2. `twice`
3. `half`
4. `triple`

Những cái này được xử lý ở nhánh khác là `implicit_quantity_cues`.

### 7.4 Trình tự xử lý cho từng match

Với mỗi số regex bắt được, code làm theo thứ tự:

1. `surface = match.group(0)`
2. bỏ `$`, `%`, `,`
3. convert sang `float`
4. tìm `sentence_index` bằng cách xem `match.start()` rơi vào span sentence nào
5. tạo 3 cửa sổ context:
   - `left_context`: 25 ký tự bên trái
   - `right_context`: 30 ký tự bên phải
   - `local_context`: 25 trái + 35 phải
6. gọi:
   - `_extract_unit_candidates(surface, left_context, right_context, target_candidates)`
   - `_extract_role_hints(surface, local_context, target_candidates)`
7. tạo mention dict

### 7.5 Artifact của mỗi numeric mention

Mỗi mention hiện có các trường:

1. `mention_id`
2. `surface_text`
3. `value`
4. `sentence_index`
5. `char_start`
6. `char_end`
7. `left_context`
8. `right_context`
9. `local_context`
10. `unit_candidates`
11. `role_hints`
12. `rule_source = "numeric_regex"`

Điểm quan trọng:

- numeric mention bây giờ giữ **candidate / hint**
- không giữ `unit` hay `semantic_role` như một truth đã resolve

## 8. Trích unit candidates: `_extract_unit_candidates`

Đây là nơi cần đọc rất kỹ để tránh hiểu sai.

Hàm:

- `_extract_unit_candidates(surface, left_context, right_context, target_candidates)`

### 8.1 Hai trường hợp special-case

Nếu `surface` chứa `$`:

- trả `["dollars"]`

Nếu `surface` chứa `%`:

- trả `["percent"]`

Ở hai chỗ này, code vẫn đang “commit” tương đối cứng, vì surface signal rất rõ.

### 8.2 Cấu trúc nội bộ của hàm

Hàm dùng:

1. `candidates = []`
2. `seen = set()`
3. helper `_push(candidate)`

`_push` làm:

1. `strip()`
2. lowercase
3. nếu rỗng hoặc đã thấy thì bỏ
4. nếu chưa thấy thì add vào `seen` và append vào `candidates`

### 8.3 Nhánh quét bên phải

Code tokenize `right_context` bằng:

```python
re.findall(r"[A-Za-z]+", right_context)
```

Sau đó:

1. duyệt từ trái sang phải
2. bỏ qua stopword nếu chưa collect gì
3. nếu đã collect rồi mà gặp stopword thì dừng
4. nếu không phải stopword thì collect
5. collect tối đa 3 từ

Sau khi collect xong, nó không trả nguyên danh sách collected ngay.

Nó push tất cả các prefix:

1. 1 từ đầu
2. 2 từ đầu
3. 3 từ đầu nếu có

Ví dụ:

- `847 beautiful red balloon`

nếu `right_context` bắt được:

- `beautiful`, `red`, `balloon`

thì candidates phía phải sẽ lần lượt là:

1. `beautiful`
2. `beautiful red`
3. `beautiful red balloon`

Điều này cực kỳ quan trọng:

- code hiện tại **không tìm noun head**
- nó chỉ đóng gói các candidate phrase gần số

### 8.4 Nhánh quét bên trái

Sau bên phải, code còn quét bên trái:

1. tokenize `left_context`
2. duyệt ngược từ phải qua trái
3. bỏ stopword theo cùng logic
4. collect tối đa 2 từ
5. đảo lại rồi push một candidate

Vai trò của nhánh này:

- bổ sung candidate từ bên trái nếu bên phải quá nghèo hoặc bị lệch

Nhưng nó vẫn không làm parse cú pháp.

### 8.5 Thêm unit candidate từ target question

Cuối hàm, code còn duyệt qua `target_candidates`.

Nếu target candidate nào có `unit_candidate` là string:

- push nó thêm vào danh sách unit candidates

Nghĩa là unit quanh quantity còn được bổ sung bởi unit suy ra từ câu hỏi đích.

### 8.6 Stopwords tham gia vào đâu

Code có `_UNIT_STOPWORDS` hard-code.

Các từ trong đó là các từ chức năng kiểu:

- `a`, `an`, `and`, `for`, `in`, `is`, `of`, `the`, `to`, `what`, `which`, ...

Vai trò:

1. đừng để parser lấy những từ này làm unit candidate
2. nếu đang collect một candidate phrase mà gặp stopword thì dừng phrase

### 8.7 Kết luận đúng về hàm này

Hàm này không trả lời:

- “đơn vị thật của số này là gì?”

Nó chỉ trả lời:

- “quanh số này đang có những cụm nào có vẻ có thể là đơn vị?”

Do đó output đúng của nó là:

- `unit_candidates`

không phải:

- `unit`

## 9. Trích role hints: `_extract_role_hints`

Hàm:

- `_extract_role_hints(surface, local_context, target_candidates)`

trả ra `list[str]`.

### 9.1 Tại sao đây là hint chứ không phải role

Phiên bản cũ cố ép quantity vào một role duy nhất quá sớm.

Phiên bản hiện tại:

- cho phép nhiều hint cùng tồn tại
- defer semantic resolution sang phần sau

### 9.2 Các hint hiện có

1. `percent_like`
2. `threshold_like`
3. `rate_like`
4. `target_overlap`

### 9.3 Rule cụ thể của từng hint

`percent_like`:

1. nếu `surface` có `%`
2. hoặc `local_context` có chữ `percent`

`threshold_like`:

1. nếu `local_context` chứa một cue trong `_THRESHOLD_CUES`
2. ví dụ:
   - `exceeds`
   - `over`
   - `after`
   - `first`
   - `at least`
   - `at most`

`rate_like`:

1. nếu `local_context` chứa cue trong `_RATE_CUES`
2. hoặc `surface` có `$`

`target_overlap`:

1. nếu `surface` của numeric mention xuất hiện trong `surface_text` của target candidate nào đó

### 9.4 Ý nghĩa kiến trúc

Điểm đúng của version hiện tại là:

- quantity có thể đồng thời `rate_like` và `target_overlap`
- parser không còn ép ngay về `UNIT_RATE`, `TARGET`, `BASE`, ...

## 10. Trích verbal / implicit quantity cues: `_extract_implicit_quantity_cues`

Hàm:

- `_extract_implicit_quantity_cues(problem_text)`

là lớp bù cho những thứ regex số không bắt được.

### 10.1 Lexicon đang dùng

`_VERBAL_NUMBER_CUES` gồm:

1. `one` -> `1.0`
2. `two` -> `2.0`
3. `three` -> `3.0`
4. `four` -> `4.0`
5. `five` -> `5.0`
6. `six` -> `6.0`
7. `seven` -> `7.0`
8. `eight` -> `8.0`
9. `nine` -> `9.0`
10. `ten` -> `10.0`
11. `hundred` -> `100.0`
12. `double` -> `2.0`
13. `twice` -> `2.0`
14. `triple` -> `3.0`
15. `half` -> `0.5`
16. `quarter` -> `0.25`

### 10.2 Cơ chế

1. lower-case toàn bộ text
2. với từng token trong lexicon:
   - compile regex `\btoken\b`
   - find all match
3. dedupe theo `(start, end)`
4. tạo cue dict

### 10.3 Artifact của mỗi implicit cue

1. `cue_id`
2. `surface_text`
3. `value_hint`
4. `char_start`
5. `char_end`
6. `cue_type`
7. `rule_source = "mini_lexicon"`

`cue_type` hiện được phân ra:

1. `multiplicative`
   - với `double`, `twice`, `triple`, `half`, `quarter`
2. `verbal_number`
   - với các token còn lại

### 10.4 Bản chất của lớp này

Đây không phải verbal-number parser đầy đủ.

Nó chỉ là:

- lexical cue collector cho các token có giá trị cao

## 11. Trích lexical cue hits: `_extract_lexical_cue_hits`

Hàm:

- `_extract_lexical_cue_hits(problem_text, target_text="")`

### 11.1 Nó quét trên chuỗi nào

Code ghép:

```python
combined_text = f"{problem_text} {target_text}".strip().lower()
```

Tức là lexical cue scanning nhìn cả:

1. thân đề bài
2. target question

### 11.2 Các cue families hiện có

1. additive
2. subtractive
3. multiplicative
4. partition
5. rate
6. threshold

Mỗi family dùng một tuple cue hard-code:

- `_ADDITIVE_CUES`
- `_SUBTRACTIVE_CUES`
- `_MULTIPLICATIVE_CUES`
- `_PARTITION_CUES`
- `_RATE_CUES`
- `_THRESHOLD_CUES`

### 11.3 Nó phát hiện như thế nào

Helper `_matching_cues(text, cues)` chỉ làm:

1. lower-case text
2. trả mọi cue mà `cue in lowered`

Nghĩa là:

- đây là substring cue lookup
- không phải token-level parser

### 11.4 Output của mỗi lexical hit

1. `family`
2. `cue`
3. `rule_source = "cue_lookup"`

Một lần nữa, đây là:

- evidence

chứ không phải:

- relation resolution

## 12. Dựng relation candidates từ lexical cues: `_build_relation_candidates_from_cues`

Hàm:

- `_build_relation_candidates_from_cues(problem_text, target_candidates, numeric_mentions, lexical_cues)`

### 12.1 Mapping family -> relation family

Code hiện map:

1. `additive` -> `RelationType.ADDITIVE_COMPOSITION`
2. `subtractive` -> `RelationType.SUBTRACTIVE_COMPARISON`
3. `multiplicative` -> `RelationType.MULTIPLICATIVE_SCALING`
4. `partition` -> `RelationType.PARTITION_GROUPING`
5. `rate` -> `RelationType.RATE_UNIT_RELATION`

Kèm theo mỗi relation family là một `OperationType` gợi ý:

1. additive -> `ADDITIVE`
2. subtractive -> `SUBTRACTIVE`
3. còn lại -> `UNKNOWN`

### 12.2 Bước group cue theo family

Từ `lexical_cues`, code gom thành:

- `family_hits: dict[str, list[str]]`

### 12.3 Tạo relation candidate

Với mỗi family đã có cue, code tạo một candidate dict gồm:

1. `relation_id`
2. `relation_type`
3. `operation_hint`
4. `source_quantity_ids`
5. `target_variable`
6. `expression = None`
7. `rationale`
8. `confidence`
9. `cue_family`
10. `matched_cues`

### 12.4 Confidence đang được tính như thế nào

```python
min(0.45 + (0.12 * len(cues)), 0.82)
```

Tức là:

1. có 1 cue -> `0.57`
2. có 2 cues -> `0.69`
3. có 3 cues -> `0.81`
4. cap ở `0.82`

### 12.5 Fallback khi không có cue

Nếu:

1. không có candidate nào
2. và chỉ có đúng 1 numeric mention

thì code tạo 1 candidate fallback:

1. `relation_type = unknown`
2. `operation_hint = unknown`
3. `expression = f"{target_variable} = {quantity_ids[0]}"`
4. `rationale = "Single visible numeric mention may itself answer the question."`
5. `confidence = 0.4`

### 12.6 Điểm cần chốt

Ở tầng parsing này:

- relation vẫn chỉ là **candidate family**
- chưa phải graph semantics hay executable relation

## 13. Dựng target link candidates: `_build_target_link_candidates`

Hàm:

- `_build_target_link_candidates(target_candidates, numeric_mentions)`

### 13.1 Logic thật sự

Với mỗi cặp:

1. một `target_candidate`
2. một `numeric_mention`

code xét hai loại evidence:

`surface_overlap`:

1. nếu `mention["surface_text"].lower()` nằm trong `target_text`

`unit_overlap`:

1. lấy `target_unit`
2. lower-case mọi `unit_candidates` của mention
3. nếu `target_unit` nằm trong bất kỳ unit candidate nào

Nếu không có reason nào:

- bỏ qua cặp này

Nếu có:

- tạo target-link candidate

### 13.2 Artifact của target-link candidate

1. `target_variable`
2. `quantity_id`
3. `reasons`
4. `confidence`

Confidence đang được tính:

```python
0.4 + (0.2 * len(reasons))
```

Tức là:

1. 1 reason -> `0.6`
2. 2 reasons -> `0.8`

### 13.3 Ý nghĩa kiến trúc

Đây là chỗ refactor quan trọng:

- parser **không attach target quantity**
- parser chỉ nói:
  - “có một candidate link, với những reason này”

## 14. Ghép toàn bộ evidence pack: `_build_problem_anchor_evidence`

Hàm:

- `_build_problem_anchor_evidence(problem_text)`

là chỗ ghép toàn bộ extractor lại với nhau.

### 14.1 Trình tự hiện tại

1. `cleaned_text = (problem_text or "").strip()`
2. `sentence_spans` từ `_split_sentences(cleaned_text)`
3. `target_candidates` từ `_extract_target_span_candidates(cleaned_text)`
4. `numeric_mentions` từ `_extract_numeric_mentions(cleaned_text, target_candidates)`
5. `implicit_quantity_cues` từ `_extract_implicit_quantity_cues(cleaned_text)`
6. `lexical_cues` từ `_extract_lexical_cue_hits(cleaned_text, first_target_surface_or_empty)`
7. `relation_candidates` từ `_build_relation_candidates_from_cues(...)`
8. `target_link_candidates` từ `_build_target_link_candidates(...)`
9. `entities` từ `_extract_entities(cleaned_text)`

Cuối cùng trả về dict.

### 14.2 Đây là “lõi tận cùng” của parsing layer

Nếu bỏ hết projection về sau, thì bản chất problem parsing hiện tại chính là hàm này cộng với các extractor mà nó gọi.

## 15. Projection sang `FormalizedProblem`: quantities

Sau khi có `evidence_pack`, builder vẫn cần project sang schema typed để phần sau chưa bị gãy.

Phần projection này bắt đầu ở:

- `_project_quantities_from_evidence(evidence_pack)`

### 15.1 Nó làm gì

Với mỗi `numeric_mention`, code tạo một `QuantityAnnotation`.

Nhưng khác rất lớn với logic cũ:

1. `unit = None`
2. `semantic_role = QuantitySemanticRole.UNKNOWN`
3. `is_target_candidate = False`

Nó không resolve các field semantic đó nữa.

### 15.2 Candidate evidence được giữ ở đâu

Trong `notes` của `QuantityAnnotation`, code ghi:

1. `unit_candidates=...`
2. `role_hints=...`
3. `rule_source=...`
4. `context=...` nếu có

Điểm cần nhấn mạnh:

- projection này chỉ là adapter vào schema typed cũ
- semantic evidence vẫn nằm trong `notes`, không bị nâng lên thành truth field

## 16. Projection sang `FormalizedProblem`: target

Hàm:

- `_project_target_from_evidence(evidence_pack)`

### 16.1 Nó làm gì

1. lấy candidate đầu tiên trong `target_span_candidates`
2. build một `TargetSpec`

### 16.2 Các field nó điền

1. `surface_text`
2. `normalized_question`
3. `target_variable`
4. `unit`
5. `description`
6. `provenance`
7. `confidence`

### 16.3 Điều rất quan trọng

Code cố định:

- `target_quantity_id = None`

Tức là parsing layer không còn được phép gắn:

- target này chính là `quantity_1`

theo rule heuristic nông như trước nữa.

## 17. Projection sang `FormalizedProblem`: relation candidates

Hàm:

- `_project_relation_candidates_from_evidence(evidence_pack, quantities, target)`

### 17.1 Nó làm gì

Với mỗi relation candidate dict trong `evidence_pack`, code tạo một `RelationCandidate` typed.

### 17.2 Những field nó giữ

1. `relation_id`
2. `relation_type`
3. `operation_hint`
4. `source_quantity_ids`
5. `target_variable`
6. `expression = None`
7. `rationale`
8. `confidence`
9. `provenance = HEURISTIC`

### 17.3 `rationale` được bổ sung như thế nào

Nếu candidate có `matched_cues`, code ghép thêm:

- `matched_cues=...`

vào `rationale`.

Ngoài ra nó còn thêm note tổng quát vào `notes` của problem dạng:

- `relation_candidate_hint:<relation_type>:matched_cues=...`

### 17.4 Ý nghĩa

Relation ở tầng parsing heuristic hiện chỉ là:

- candidate family được project vào schema typed

Nó không phải executable relation.

## 18. Entity linking: `_link_quantities_to_entities`

Hàm:

- `_link_quantities_to_entities(quantities, entities)`

### 18.1 Rule nội bộ

Với mỗi quantity:

1. nếu quantity đã có `entity_id` hoặc không có `char_start` -> giữ nguyên
2. nếu không:
   - duyệt mọi entity
   - lấy `entity.metadata["char_start"]`
   - tính khoảng cách tuyệt đối đến `quantity.char_start`
   - lấy entity gần nhất
3. update quantity với `entity_id` của entity gần nhất

### 18.2 Bản chất

Đây vẫn là:

- proximity heuristic bằng offset ký tự

không phải entity-quantity semantic linking.

## 19. Builder gom lại tất cả trong `_heuristic_formalize_problem`

Hàm này, trong [problem_formalizer_builder.py](C:/Users/linhn/Desktop/Dự án/src/formalizer/problem_formalizer_builder.py), đang làm đúng trình tự sau:

1. `cleaned_text = ...`
2. `evidence_pack = _build_problem_anchor_evidence(cleaned_text)`
3. `target_text = _extract_target_text(cleaned_text)`
4. `quantities = _project_quantities_from_evidence(evidence_pack)`
5. `entities = _extract_entities(cleaned_text)`
6. `quantities = _link_quantities_to_entities(quantities, entities)`
7. `target = _project_target_from_evidence(evidence_pack)`
8. `relation_candidates, relation_notes = _project_relation_candidates_from_evidence(...)`
9. tạo `notes` thống kê:
   - số `sentence_spans`
   - số `numeric_mentions`
   - số `implicit_quantity_cues`
   - số `lexical_cues`
   - số `target_candidates`
   - số `target_link_candidates`
   - số `relation_candidates`
   - số `entities` nếu có
   - marker `target_candidate_selected` nếu có `target_text`
10. tạo `FormalizedProblem`
11. `validated = validate_formalized_problem(problem)`
12. `return _attach_problem_graph(validated), evidence_pack`

### 19.1 Điểm rất quan trọng ở cuối hàm

Hàm này trả về **2 thứ**:

1. heuristic `FormalizedProblem`
2. `evidence_pack`

Điều đó xác nhận rất rõ kiến trúc hiện tại:

- `FormalizedProblem` heuristic không phải artifact duy nhất
- `evidence_pack` là output first-class của parsing layer

## 20. `target_text` convenience wrapper thực sự làm gì

Trong builder vẫn có:

- `_extract_target_text(problem_text)`

Hàm này hiện chỉ là wrapper tiện dụng:

1. gọi `_extract_target_span_candidates(problem_text)`
2. nếu có candidate thì lấy `candidates[0]["surface_text"]`
3. nếu không có thì trả `""`

Nó không có logic riêng ngoài việc “lấy candidate đầu”.

## 21. Những gì tầng này không còn làm

Theo code hiện tại, problem parsing heuristic **không còn**:

1. set `QuantityAnnotation.unit` từ candidate phrase gần số
2. set `QuantityAnnotation.semantic_role` từ cue nông
3. set `QuantityAnnotation.is_target_candidate = True`
4. set `TargetSpec.target_quantity_id` từ overlap nông
5. biến relation heuristic thành executable expression thật ngay ở parser

Những thứ đó đã bị hạ cấp thành:

1. `unit_candidates`
2. `role_hints`
3. `target_link_candidates`
4. `relation_candidates`
5. notes / provenance

## 22. Những gì tầng này vẫn còn làm theo rule cứng

Không phải mọi heuristic đều đã biến mất. Một số chỗ vẫn là rule cứng, nhưng vai trò đã hẹp hơn:

1. regex tách câu
2. regex bắt số
3. regex bắt WH-question
4. mini-lexicon cho verbal number / multiplicative cues
5. stopword list cho unit candidate collection
6. substring cue lookup cho relation family hints
7. char-distance entity linking

Điểm khác bây giờ là:

- các rule này chủ yếu dùng để **thu thập chứng cứ**
- chứ không còn được dùng để **đóng dấu semantic truth**

## 23. Kết luận đúng với code hiện tại

Nếu mô tả rất ngắn nhưng chính xác tầng `01_problem_parsing` hiện tại:

- Nó không còn là một heuristic formalizer kiểu cũ.
- Nó là một lớp **surface evidence extraction + candidate generation + evidence packaging**.
- Sau đó hệ mới project một `FormalizedProblem` heuristic rất mỏng để tương thích với schema typed và các tầng phía sau.

Nếu phải nén thành 4 cụm từ:

1. segmentation
2. mention extraction
3. candidate generation
4. evidence packaging

Đó là cơ chế lõi hiện tại của file `01_problem_parsing`.

# Cơ Chế Hoạt Động Của Hệ Thống Tutoring Toán Từng Bước

## 1. Mục tiêu tổng thể

Hệ thống được thiết kế để xử lý một bài toán lời văn và một câu trả lời của học sinh theo chuỗi bước:

1. Hiểu đề bài và chuẩn hóa đề thành biểu diễn có cấu trúc.
2. Tạo lời giải chuẩn có thể thực thi được, thay vì chỉ tạo lời giải bằng văn bản.
3. Chuẩn hóa bài làm của học sinh thành biểu diễn có thể đối chiếu.
4. So khớp bài làm của học sinh với lời giải chuẩn theo mức process, không chỉ theo đáp án cuối.
5. Chẩn đoán học sinh sai ở đâu, sai theo kiểu gì.
6. Lập kế hoạch gợi ý mang tính sư phạm.
7. Sinh gợi ý, sửa gợi ý nếu cần, kiểm tra gợi ý, rồi mới trả kết quả cuối.

Toàn bộ hệ thống đi theo tư tưởng:

- LLM được dùng ở những nơi cần hiểu ngữ nghĩa hoặc diễn đạt tự nhiên.
- Phần chuẩn hóa, kiểm tra, thực thi, so khớp, và kiểm chứng được giữ càng nhiều càng tốt ở phía cấu trúc và deterministic logic.
- Kết quả cuối không phụ thuộc hoàn toàn vào một lời giải tự do của model.

---

## 2. Luồng tổng thể của pipeline

Pipeline đầy đủ gồm các khối sau:

1. `Problem Formalization`
2. `Canonical Reference Construction`
3. `Student Work Formalization`
4. `Evidence Building`
5. `Diagnosis`
6. `Pedagogy Planning`
7. `Hint Generation`
8. `Hint Repair`
9. `Hint Verification`
10. `Fallback Hint`

Luồng dữ liệu tổng quát:

`problem_text`
-> formalize đề bài
-> tạo lời giải chuẩn thực thi được
-> formalize bài làm học sinh
-> build evidence
-> chẩn đoán
-> lập kế hoạch gợi ý
-> generate / repair / verify / fallback
-> `TutoringResult`

---

## 3. Module 1: Formalize đề bài

### 3.1. Mục tiêu

Biến đề bài tự nhiên thành một object có cấu trúc, đủ chặt để:

- biết các quantity nào có trong đề
- biết thực thể nào đang được nói đến
- biết mục tiêu câu hỏi là gì
- biết bài toán đang thuộc kiểu quan hệ nào
- biết graph giải bài toán nên có những bước nào

### 3.2. Đầu vào

- văn bản đề bài

### 3.3. Các bước nội bộ

#### Bước A. Heuristic parsing ban đầu

Hệ thống trước hết làm một lượt parsing deterministic để tạo draft:

- tách câu
- trích số
- trích entity
- suy unit
- suy semantic role sơ bộ
- suy target question
- suy relation type sơ bộ

Kết quả của bước này là một heuristic draft, dùng làm:

- baseline ban đầu
- fallback nếu LLM thất bại
- nguồn id ổn định cho quantities, entities, target

#### Bước B. Tạo compact draft gửi cho model

Thay vì gửi toàn bộ object rất dài cho model, hệ thống tạo một draft rút gọn chỉ gồm những gì cần thiết:

- problem text
- quantities dạng gọn
- entities dạng gọn
- target draft
- relation summary
- graph step summary

Mục tiêu là:

- giảm token
- giảm rủi ro sinh output rác
- giữ cho model làm đúng phần semantic khó

#### Bước C. Model trả compact skeleton

Model không còn trả full object hoàn chỉnh, mà trả skeleton gồm:

- cập nhật role/unit/entity cho quantities
- cập nhật target
- cập nhật relation
- graph steps
- graph target
- assumptions / notes / confidence

Ý nghĩa:

- model chỉ quyết định phần khó
- phần cơ học để hệ thống local build

#### Bước D. Local builder xây full formalized problem

Từ skeleton của model, hệ thống local build lại:

- danh sách quantities hoàn chỉnh
- entities hoàn chỉnh
- target hoàn chỉnh
- relation candidates hoàn chỉnh
- problem graph hoàn chỉnh

Ở đây hệ thống:

- giữ id ổn định từ draft heuristic
- chuẩn hóa cấu trúc theo schema
- điền provenance, notes, confidence mặc định nếu cần

#### Bước E. Validation

Sau khi build xong, formalization phải qua nhiều lớp kiểm tra:

- schema validation
- graph validation
- semantic sanity checks

Semantic sanity checks dùng để bắt những lỗi như:

- target trỏ sai kiểu quantity input
- bài rate nhưng thiếu percent
- bài threshold nhưng thiếu threshold
- graph không phù hợp với dạng bài

#### Bước F. Retry / refine loop

Nếu output của model:

- sai schema
- sai graph
- sai sanity constraints

thì hệ thống không bỏ ngay, mà:

1. trích lỗi có cấu trúc
2. đưa lỗi đó vào feedback
3. gọi model lại với feedback

Loop này chỉ dừng khi:

- output hợp lệ
- hoặc hết số lượt thử

#### Bước G. Fallback

Nếu loop thất bại, hệ thống quay về:

- heuristic formalization

### 3.4. Đầu ra

Đầu ra của module này là một biểu diễn đề bài chuẩn hóa, bao gồm:

- quantities
- entities
- target
- relation candidates
- problem graph

---

## 4. Module 2: Xây lời giải chuẩn thực thi được

### 4.1. Mục tiêu

Biến problem graph thành lời giải chuẩn có thể:

- compile
- execute
- trace

Thay vì tin vào một lời giải viết tay của model, hệ thống dùng:

- plan
- execution trace
- final answer

làm nguồn chuẩn.

### 4.2. Các bước nội bộ

#### Bước A. Validate graph ở mức executable

Kiểm tra:

- graph có target hay không
- operation nodes có đủ input/output không
- dependency có hợp lệ không
- target có được produce không

#### Bước B. Compile graph thành executable plan

Từ graph, hệ thống tạo plan dạng từng step:

- mỗi step có operation
- input refs
- output ref
- expression
- explanation

#### Bước C. Execute plan

Hệ thống lấy các quantity ban đầu làm bindings, rồi chạy từng step:

- resolve inputs
- tính output
- lưu vào bảng giá trị

#### Bước D. Tạo execution trace

Mỗi step execution được ghi lại:

- inputs resolved
- output value
- success/failure
- notes

#### Bước E. Tạo canonical reference

Kết quả cuối được đóng gói thành reference chuẩn gồm:

- final answer
- chosen plan
- execution trace
- rendered solution text

### 4.3. Tính chất

Module này hiện là deterministic, không phụ thuộc model.

---

## 5. Module 3: Formalize bài làm học sinh

### 5.1. Mục tiêu

Biến câu trả lời của học sinh thành artifact có thể đối chiếu với lời giải chuẩn.

Quan trọng:

- không chỉ lấy đáp án cuối
- còn phải cố gắng hiểu các bước trình bày
- và xây student graph

### 5.2. Đầu vào

- bài làm học sinh
- đề bài đã formalize

Lưu ý:

- student parser được giữ độc lập hơn với reference
- việc so với canonical reference được dời sang evidence layer

### 5.3. Các bước nội bộ

#### Bước A. Heuristic parse ban đầu

Hệ thống parse:

- đáp án cuối
- các dòng / bước trình bày
- phép toán sơ bộ
- các giá trị đầu vào của từng bước
- các ref tới quantities của đề

Kết quả là một heuristic draft của student work.

#### Bước B. Tạo compact student draft

Giống formalizer, hệ thống không nhờ model trả full object mà tạo một draft rút gọn gồm:

- normalized final answer draft
- mode
- selected target draft
- step summaries
- allowed refs

#### Bước C. Model trả compact student skeleton

Model chỉ được phép trả:

- normalized final answer
- mode
- selected target ref
- step updates
- assumptions / notes / confidence

Model không được tự ý:

- invent raw text
- invent step id mới
- invent refs ngoài contract

#### Bước D. Local builder tạo full student state

Từ skeleton đó, hệ thống local build:

- steps hoàn chỉnh
- selected target
- confidence / notes
- student graph

#### Bước E. Xây student graph

Student graph được build từ:

- các step học sinh
- input values
- refs tới quantities của đề
- output nodes của chính học sinh

Graph này cố gắng giữ dependency structure của bài làm:

- step nào sinh ra giá trị nào
- step nào dùng lại output trước
- target cuối của học sinh là gì

#### Bước F. Validation và refine loop

Nếu skeleton student:

- sai ref
- sai mode/step consistency
- graph invalid

thì hệ thống:

- tạo feedback issues
- gọi model lại

Nếu vẫn thất bại thì fallback về heuristic parse.

### 5.4. Đầu ra

- normalized final answer
- list steps
- selected target ref
- student graph

---

## 6. Module 4: Build evidence

### 6.1. Mục tiêu

Đây là tầng trung gian giữa:

- student work formalization
- diagnosis

Nó không chẩn đoán luôn.  
Nhiệm vụ của nó là:

- align
- compare
- emit structured evidence

### 6.2. Đầu vào

- problem graph
- canonical plan
- canonical execution trace
- student graph
- student steps
- student final answer

### 6.3. Các bước nội bộ

#### Bước A. Suy student target

Từ student graph, final answer, và context, hệ thống suy:

- học sinh đang trả lời final target
- hay đang dừng ở intermediate
- hay đang chọn visible quantity trong đề

#### Bước B. Global alignment giữa student steps và canonical steps

Thay vì so step theo index một cách cứng, hệ thống làm matching toàn cục một-một.

Việc align dựa trên nhiều tín hiệu:

- operation
- output value
- input refs overlap
- dependency shape
- target intent

Kết quả là:

- alignment map
- score cho từng cặp align

#### Bước C. So khớp process

Sau khi align, hệ thống đối chiếu:

- final answer
- target selection
- operation chain
- step values
- dependency chain
- graph path tới target

#### Bước D. Phát hiện divergence

Hệ thống tìm:

- step lệch đầu tiên
- lệch do target
- lệch do operation
- lệch do value
- lệch do dependency

#### Bước E. So sánh graph ở mức sâu hơn

Evidence layer hiện không chỉ so step rời rạc, mà còn:

- so dependency subgraph
- phát hiện edge-level divergence
- tính graph edit summary

#### Bước F. Xử lý case reorder hợp lệ

Một điểm quan trọng:

- nếu học sinh đúng nhưng thứ tự bước khác
- hoặc gộp/tách bước khác canonical

hệ thống cố gắng nhận diện đây là variation hợp lệ, không phải lỗi.

Nếu dependency vẫn hợp lý và target cuối đúng, evidence có thể ghi:

- reordered but consistent

thay vì mismatch oan.

### 6.4. Đầu ra

Module này trả structured evidence gồm:

- evidence items
- alignment map
- first divergence step id
- likely error mechanisms
- confidence

---

## 7. Module 5: Diagnosis

### 7.1. Mục tiêu

Biến structured evidence thành chẩn đoán:

- học sinh sai theo kiểu gì
- sai ở đâu
- bằng chứng nào hỗ trợ chẩn đoán đó

### 7.2. Cơ chế

Diagnosis hiện hoạt động theo hướng:

- deterministic hypothesis scoring là tầng chính
- LLM chỉ đóng vai critic / refiner

### 7.3. Các bước nội bộ

#### Bước A. Sinh các hypothesis ứng viên

Hệ thống tạo nhiều hypothesis như:

- correct answer
- unparseable answer
- target misunderstanding
- arithmetic error
- quantity relation error
- unknown error

#### Bước B. Chấm điểm từng hypothesis

Mỗi evidence sẽ tăng hoặc giảm điểm cho từng giả thuyết.

Ví dụ:

- final answer đúng và reordered but consistent
  -> tăng mạnh cho correct answer
- target inferred là intermediate
  -> tăng cho target misunderstanding
- divergence ở bước tính toán nhưng target đúng
  -> tăng cho arithmetic error

#### Bước C. Chọn hypothesis tốt nhất

Sau khi chấm điểm:

- hệ thống chọn top hypothesis
- ghi lại runner-up
- tính margin

Mục tiêu là tránh cách rule chain thô.

#### Bước D. Tạo diagnosis result

Diagnosis cuối gồm:

- diagnosis label
- subtype
- localization
- target step id
- summary
- supporting evidence types
- confidence

#### Bước E. LLM refinement nếu có

Nếu có model, hệ thống có thể đưa vào:

- evidence
- deterministic diagnosis baseline
- hypothesis leaderboard

để model refine summary hoặc subtype.

Model không còn là nguồn chẩn đoán chính.

### 7.4. Đầu ra

- diagnosis label
- subtype
- localization
- confidence
- summary

---

## 8. Module 6: Pedagogy planning

### 8.1. Mục tiêu

Biến diagnosis thành chiến lược gợi ý.

Diagnosis nói:

- học sinh sai gì

Pedagogy plan quyết định:

- nên can thiệp bằng kiểu gợi ý nào
- ở mức lộ thông tin nào
- nhắm tới bước nào

### 8.2. Các bước nội bộ

Tùy diagnosis label, hệ thống chọn:

- hint level
- teacher move
- target step
- disclosure budget
- focus points
- must not reveal
- rationale

Ví dụ:

- target misunderstanding
  -> refocus target
- arithmetic error
  -> recompute step hoặc continue from step
- unknown
  -> metacognitive prompt

### 8.3. Đầu ra

Pedagogy plan là contract trung gian giữa chẩn đoán và hint generation.

---

## 9. Module 7: Generate hint

### 9.1. Mục tiêu

Sinh ra câu gợi ý cụ thể từ pedagogy plan.

### 9.2. Hai đường sinh

#### Đường deterministic

Nếu không dùng model hoặc model thất bại:

- hệ thống sinh hint bằng template gắn với teacher move

#### Đường LLM

Nếu dùng model:

- hệ thống gửi target, diagnosis, pedagogy plan, hint mode
- yêu cầu model trả về một hint ngắn, đúng contract

Model ở bước này bị ép:

- tối đa số câu quy định
- không lộ forbidden content
- phải theo đúng teacher move

---

## 10. Module 8: Repair hint

### 10.1. Mục tiêu

Nếu hint sinh ra chưa đạt, hệ thống không fallback ngay mà cố sửa.

Đây là một bước rất quan trọng để tăng chất lượng hint mà vẫn giữ an toàn.

### 10.2. Các lớp repair

#### Repair mức 1: minimal edit

Hệ thống thử sửa nhẹ:

- xóa spoiler
- chuẩn hóa whitespace
- cắt còn số câu cho phép
- sửa một số lệch cue theo teacher move
- giảm tính computational nếu hint level là conceptual

#### Repair mức 2: guided rewrite

Nếu minimal edit không đủ:

- hệ thống dựng lại hint ngắn gọn từ pedagogy plan
- vẫn bám teacher move, focus points, disclosure budget

#### Repair mức 3: LLM repair

Nếu deterministic repair vẫn chưa đạt và có model:

- hệ thống gửi original hint
- violations
- diagnosis
- pedagogy plan
- forbidden content

cho model để model sửa lại hint.

### 10.3. Ý nghĩa

Nhờ có repair layer:

- các hint “gần đúng” không bị bỏ phí
- chất lượng hint tự nhiên hơn
- fallback chỉ còn là lưới an toàn cuối cùng

---

## 11. Module 9: Verify hint

### 11.1. Mục tiêu

Kiểm tra hint có an toàn và đúng chiến lược sư phạm hay không.

### 11.2. Hai nhóm kiểm tra chính

#### A. No-spoiler check

Kiểm tra hint có lộ:

- final answer
- intermediate bị cấm
- text bị cấm
- số bị cấm

#### B. Alignment check

Kiểm tra:

- hint có đúng teacher move không
- hint có quá dài không
- hint conceptual có quá computational không

### 11.3. Kết quả

Hint được gắn:

- passed / failed
- violated rules

---

## 12. Module 10: Fallback hint

### 12.1. Khi nào dùng

Fallback chỉ được dùng khi:

- generate không qua
- repair không cứu được
- verify vẫn fail

### 12.2. Cách hoạt động

Hệ thống dùng một hint ngắn, an toàn, rất bảo thủ, phụ thuộc vào teacher move.

Fallback không nhằm tối ưu độ tự nhiên, mà nhằm:

- an toàn
- không spoiler
- không sai sư phạm

---

## 13. Điều khiển LLM trong toàn hệ thống

LLM không phải lúc nào cũng là thành phần chính.  
Vai trò của LLM được đặt khác nhau theo từng module.

### 13.1. Nơi LLM được dùng

- formalize đề bài
- formalize bài làm học sinh
- diagnosis refinement
- hint generation
- hint repair

### 13.2. Nơi LLM không phải trung tâm

- graph validation
- runtime execution
- canonical reference building
- evidence alignment cốt lõi
- pedagogy planning
- hint verification

### 13.3. Quy tắc chung

Ở những nơi có LLM, hệ thống cố gắng giữ cấu trúc:

- heuristic or deterministic draft
- compact model output
- local build
- validation
- retry / refine
- fallback

Điều này giúp:

- giảm phụ thuộc vào một response duy nhất của model
- giảm lỗi schema
- giảm hallucination
- tăng khả năng benchmark

---


## 19. Đi sâu hơn nữa vào cơ chế bên trong module Formalize đề bài

### 19.1. Heuristic parsing ban đầu thực sự làm gì

Heuristic parsing không “hiểu” bài toán theo nghĩa sâu, mà thực hiện một chuỗi thao tác có tính pattern-based:

1. Quét toàn bộ đề để tìm các span có dạng số:
   - số nguyên
   - số thực
   - phần trăm
   - số có ký hiệu tiền tệ
2. Với mỗi số, lấy một cửa sổ ngữ cảnh xung quanh nó:
   - vài token trước
   - vài token sau
   - câu chứa nó
3. Từ cửa sổ ngữ cảnh đó, hệ thống suy:
   - unit
   - entity gần nhất
   - semantic role sơ bộ
4. Song song, hệ thống quét toàn bài để tìm:
   - câu hỏi mục tiêu
   - cue cho cộng/trừ/so sánh/rate/percent/threshold
   - cụm từ chỉ “in all”, “left”, “more than”, “every”, “costs”, “%”, ...

Về bản chất, đây là một pipeline:

`surface pattern -> local interpretation -> draft semantic slots`

Nó mô hình hóa được bài toán vì nhiều bài word problem có:

- regularity ở bề mặt câu chữ
- regularity ở vai trò của số
- regularity ở kiểu quan hệ

### 19.2. Compact draft được tạo như thế nào

Compact draft không phải một bản sao đầy đủ của formalized object, mà là một bản tóm lược có kiểm soát.

Quá trình tạo draft diễn ra như sau:

1. Giữ lại problem text nguyên bản.
2. Với mỗi quantity, chỉ giữ các field cần thiết cho model:
   - id
   - surface text
   - value
   - unit
   - entity id
   - semantic role draft
   - is_target_candidate
3. Với entity, chỉ giữ:
   - id
   - surface text
   - normalized name
   - entity type
4. Với target, chỉ giữ:
   - surface question
   - target variable
   - target quantity id draft
   - unit
5. Với relation và graph, chỉ giữ:
   - relation summary
   - graph step summary
   - graph target id

Điểm mấu chốt là:

- draft phải đủ để model hiểu semantic problem
- nhưng không dài đến mức model phải lặp lại toàn bộ object

### 19.3. Model sinh compact skeleton như thế nào trong cơ chế chung

Ở bước này, model được đặt vào một không gian output hẹp:

1. Model được cung cấp:
   - problem text
   - compact draft
   - ontology / enum được phép dùng
   - ràng buộc output
   - feedback issues nếu là retry
2. Model phải chọn:
   - quantity role nào cần sửa
   - target nào là đúng
   - relation type nào hợp lý
   - graph step chain nào có ý nghĩa
3. Model không được tạo tự do mọi field, mà chỉ điền các slot đã định trước.

Điều này làm giảm đáng kể:

- malformed JSON
- invented enum
- invented ref
- sự lệch pha giữa quantity ids và graph ids

### 19.4. Local builder ghép skeleton thành object đầy đủ như thế nào

Local builder hoạt động như một tầng hợp nhất:

1. Bắt đầu từ heuristic draft đã có.
2. Duyệt qua từng phần update trong skeleton:
   - quantity updates
   - target update
   - relation updates
   - graph steps
3. Với mỗi update:
   - nếu ref hợp lệ thì merge vào draft
   - nếu thiếu field không bắt buộc thì giữ field cũ
   - nếu field không có trong contract thì bỏ
4. Sau khi merge xong:
   - dựng lại graph nodes
   - dựng lại graph edges
   - điền provenance / notes / confidence

Local builder là nơi quyết định:

- object cuối có hợp lệ về cấu trúc hay không
- model được quyền sửa cái gì
- cái gì phải giữ ổn định theo draft

### 19.5. Validation hoạt động theo mấy lớp

Validation không chỉ có một lớp.

#### Lớp 1. Schema validation

Kiểm tra:

- field type
- required field
- enum hợp lệ
- id không rỗng
- duplicate id

#### Lớp 2. Internal reference validation

Kiểm tra:

- quantity id có tồn tại không
- entity id có tồn tại không
- target quantity id có trỏ đúng quantity không
- graph node có trỏ đúng quantity/entity không

#### Lớp 3. Graph validation

Kiểm tra:

- target node có tồn tại không
- operation node có đủ operation / expression / step id / step index không
- edge source/target có tồn tại không
- luồng input/output có hợp lệ để compile không

#### Lớp 4. Semantic sanity checks

Kiểm tra:

- dạng bài rate có thiếu unit rate không
- dạng bài percent có thiếu percent không
- dạng bài threshold có thiếu threshold không
- target có đang trỏ sai vào visible quantity đầu vào hay không
- graph step chain có hợp logic tối thiểu với relation type không

### 19.6. Retry/refine loop thực sự vận hành ra sao

Loop này vận hành theo cơ chế:

1. Attempt 1:
   - model nhận draft ban đầu
   - sinh skeleton
2. Local build + validate:
   - nếu pass -> accept
   - nếu fail -> trích issues
3. Attempt 2:
   - model nhận lại:
     - draft
     - feedback issues từ lần trước
   - model sửa skeleton
4. Lặp lại cho tới khi:
   - pass
   - hoặc hết số attempt

Feedback issues không phải một đoạn prose dài, mà là các tín hiệu có cấu trúc như:

- unknown quantity ref
- missing target node
- invalid operation chain
- semantic target mismatch

Điều này giúp loop có tính “sửa có hướng” hơn là chỉ generate lại từ đầu.

---

## 20. Đi sâu hơn nữa vào cơ chế bên trong module Canonical Reference

### 20.1. Compile graph thành plan diễn ra như thế nào

Khi đã có graph hợp lệ, hệ thống tạo plan qua các bước:

1. Lấy toàn bộ operation nodes.
2. Sắp xếp chúng theo `step_index`.
3. Với mỗi operation node:
   - tìm các edge input trỏ vào node
   - sắp input theo `position`
   - tìm edge output đi ra từ node
4. Từ đó dựng một executable step:
   - step id
   - operation
   - expression
   - input refs
   - output ref
   - explanation

Kết quả là graph được tuyến tính hóa thành một process thực thi được.

### 20.2. Runtime execute từng step như thế nào

Runtime giữ một bảng bindings:

- ban đầu chứa các quantity gốc

Ví dụ:

- `quantity_1 = 40`
- `quantity_2 = 12`

Sau đó với mỗi step:

1. Lấy `input_refs`
2. Resolve từng ref sang giá trị số trong bindings
3. Thực thi expression / operation
4. Sinh `output_value`
5. Ghi `output_ref = output_value` trở lại bindings

Nếu step nào fail:

- step result được đánh dấu fail
- trace giữ lại error message
- reference không được coi là successful execution

### 20.3. Execution trace giữ vai trò gì

Execution trace là cầu nối giữa:

- graph / plan
- final answer
- evidence / diagnosis

Nó không chỉ lưu final value, mà còn lưu toàn bộ process chuẩn:

- step nào cho ra intermediate nào
- output value ở từng bước là bao nhiêu
- đâu là bước cuối cùng tạo target

Nhờ đó, downstream có thể hỏi:

- học sinh đang dừng ở intermediate nào?
- giá trị học sinh nói có trùng một canonical output không?
- divergence xuất hiện ở bước nào?

---

## 21. Đi sâu hơn nữa vào cơ chế bên trong module Formalize bài làm học sinh

### 21.1. Heuristic parse student answer làm gì bên trong

Parser học sinh làm việc theo trục “tách câu trả lời thành các đơn vị xử lý nhỏ”.

1. Chuẩn hóa raw answer:
   - tách dòng
   - loại khoảng trắng thừa
   - giữ lại raw text cho từng step
2. Với từng dòng / từng cụm:
   - tìm phép tính có xuất hiện không
   - tìm output value có xuất hiện không
   - tìm các input values xuất hiện trong dòng
   - gán operation sơ bộ nếu nhận ra pattern
3. Với toàn bài:
   - tìm final answer cue như:
     - `Answer is`
     - `Final answer`
     - số cuối cùng trong pattern rõ ràng

Điểm quan trọng là parser không suy diễn quá mức.  
Nó ưu tiên:

- những gì có thể đọc trực tiếp từ bài làm
- rồi mới để model sửa

### 21.2. Student compact draft được dựng như thế nào

Student draft gồm:

- final answer draft
- work mode draft
- selected target draft
- step summaries
- allowed refs từ problem

Mỗi step summary chỉ giữ:

- step id ổn định
- raw text
- operation draft
- extracted value
- referenced ids
- input values

Mục tiêu là:

- cho model đủ context để chỉnh semantic parse
- nhưng không cho model quyền tái viết toàn bộ lời giải học sinh

### 21.3. Model student skeleton được constrained như thế nào

Trong bước này, model bị ép bởi các nguyên tắc:

1. Không invent step id mới.
2. Không invent raw text mới.
3. Chỉ được chọn refs từ tập allowed refs.
4. Nếu không chắc, để trống hoặc để unknown.

Điều này rất quan trọng vì bài làm học sinh nhiễu hơn đề bài, nên nếu thả tự do:

- model dễ suy luận hộ học sinh
- model dễ gắn nhầm canonical step từ quá sớm

### 21.4. Student graph được build ra sao

Student graph không chỉ là danh sách step.

Quy trình build:

1. Tạo node cho:
   - visible quantities từ problem mà học sinh đã dùng
   - từng step operation của học sinh
   - output của từng step
   - final answer target
2. Tạo edge input vào operation:
   - nếu step dùng quantity trong đề -> nối quantity node vào step node
   - nếu step dùng giá trị đã xuất hiện ở output trước đó -> nối output node trước vào step node
3. Tạo edge output:
   - từ step node sang output node tương ứng
4. Tạo target edge:
   - từ last supporting output sang target node của học sinh

Nhờ vậy, student graph biểu diễn được:

- process dependency nội tại của lời giải học sinh
- thay vì chỉ là một list step phẳng

### 21.5. Student refine loop hoạt động như thế nào

Khi skeleton student không hợp lệ:

- ref lạ
- selected target sai contract
- mode không khớp steps
- graph build fail

thì hệ thống:

1. đóng gói các lỗi này thành feedback issue
2. gửi lại model
3. yêu cầu model sửa đúng slot bị lỗi

Nếu vẫn không sửa được:

- quay về heuristic parse

---

## 22. Đi sâu hơn nữa vào cơ chế module xây Evidence

### 22.1. Suy student target không chỉ nhìn final answer

Student target inference dùng nhiều nguồn:

1. `selected_target_ref` nếu student formalization đã có
2. final answer value
3. target node của student graph
4. việc final answer có trùng:
   - canonical final answer
   - canonical intermediate output
   - visible quantity trong problem

Hệ thống gộp các tín hiệu đó để suy:

- học sinh đang nhắm final target
- intermediate canonical value
- visible quantity

### 22.2. Global alignment chấm điểm từng cặp step như thế nào

Hệ thống trước hết tạo một score matrix giữa:

- mỗi student step
- mỗi canonical step

Điểm của một cặp được tính từ nhiều thành phần:

- operation match
- extracted value có gần canonical output value không
- input refs overlap
- dependency compatibility
- vị trí tương đối trong chain

Sau đó hệ thống giải một bài toán matching toàn cục:

- mỗi student step match tối đa một canonical step
- mỗi canonical step match tối đa một student step
- tối đa hóa tổng score

Nhờ vậy alignment:

- không bị greedy cục bộ
- không quá phụ thuộc step index

### 22.3. Compare process diễn ra ở mấy lớp

Sau alignment, compare không làm một phát, mà đi qua nhiều lớp:

#### Lớp 1. Final answer compare

Kiểm tra:

- final answer đúng hay sai
- final answer có trùng visible quantity không
- final answer có trùng intermediate output không

#### Lớp 2. Target compare

Kiểm tra:

- student target inferred là gì
- có match canonical target không

#### Lớp 3. Step compare

Cho từng aligned pair:

- operation match hay mismatch
- value match hay mismatch
- step unsupported hay ambiguous

#### Lớp 4. Dependency compare

Cho từng aligned pair và các edge liên quan:

- dependency chain có tương ứng không
- input của student step có thực sự đến từ các output phù hợp không

### 22.4. Divergence được xác định như thế nào

Hệ thống không chỉ lấy “step sai đầu tiên theo index”, mà tìm step divergence đầu tiên theo alignment và dependency logic:

1. Bỏ qua các step reorder nhưng consistent
2. Bỏ qua restated final answer nếu chỉ là nhắc lại
3. Tìm step đầu tiên mà một trong các điều kiện đúng:
   - target lệch
   - operation lệch
   - value lệch
   - dependency lệch

Step này trở thành:

- `first_divergence_step_id`

### 22.5. Graph edit summary được tính ra sao

Hệ thống lấy:

- student aligned subgraph
- canonical aligned subgraph

rồi tóm tắt chênh lệch thành:

- node substitutions
- node insertions
- node deletions
- edge substitutions
- edge insertions
- edge deletions
- total edit cost

Đây không phải full academic graph edit distance cho mọi loại graph tùy ý, nhưng là một structural discrepancy summary đủ mạnh để diagnosis dùng.

---

## 23. Đi sâu hơn nữa vào cơ chế bên trong mudule Diagnosis

### 23.1. Hypothesis scoring thực sự vận hành ra sao

Diagnosis tạo một bảng ứng viên.  
Mỗi ứng viên gồm:

- label
- subtype
- localization
- score ban đầu
- rationale accumulator
- supporting evidence accumulator

Sau đó hệ thống duyệt qua evidence items và cập nhật score.

Ví dụ:

- `correct_final_answer`
  -> cộng điểm cho `correct_answer`
- `selected_intermediate_reference`
  -> cộng cho `target_misunderstanding`
- `operation_mismatch` hoặc `dependency_mismatch`
  -> cộng cho `quantity_relation_error`
- `step_value_mismatch` với target đúng
  -> cộng cho `arithmetic_error`

### 23.2. Localization được quyết định như thế nào

Localization không được đoán độc lập, mà phụ thuộc vào evidence:

- nếu divergence ở step intermediate -> `intermediate_step`
- nếu lỗi ở final computation -> `final_computation`
- nếu target chọn sai -> `target_selection`
- nếu không rõ -> `unknown`

### 23.3. LLM refinement ở diagnosis làm gì và không làm gì

LLM ở diagnosis không tự chẩn đoán từ raw answer.

Nó nhận:

- evidence đã cấu trúc
- deterministic diagnosis baseline
- hypothesis leaderboard

Nhiệm vụ của nó là:

- refine summary
- refine subtype
- chọn giữa các hypothesis gần nhau nếu cần

Nó không được phép bỏ qua grounding evidence.

---

## 24. Đi sâu vào cơ chế bên trong module Pedagogy planning

### 24.1. Teacher move được chọn theo logic nào

Teacher move không được chọn ngẫu nhiên mà theo mapping từ diagnosis:

- correct answer -> restate result
- target misunderstanding -> refocus target
- quantity relation error -> check relationship
- arithmetic error -> recompute step hoặc continue from step
- unknown / unparseable -> metacognitive prompt

### 24.2. Disclosure budget điều khiển gì

Disclosure budget quyết định hint được phép cụ thể đến đâu.

Ví dụ:

- budget thấp:
  - hint nên thiên về nhắc mục tiêu, không nói giá trị
- budget cao hơn:
  - hint có thể nhắm step cụ thể hơn
  - nhưng vẫn không được lộ output bị cấm

### 24.3. Focus points và must-not-reveal được tạo ra sao

Focus points được xây từ:

- target question
- relation rationale
- step explanation
- diagnosis localization

Must-not-reveal được xây từ:

- final answer
- output của step target
- text/number mà hint không được lộ

Đây là hai trục chính để:

- generator biết nên nói về cái gì
- verifier biết không được lộ cái gì

---

## 25. Đi sâu vào cơ chế bên trong module sinh Hint

### 25.1. Generate hint dùng plan như thế nào

Generator nhận:

- diagnosis
- pedagogy plan
- target prompt
- hint mode

Nếu đi đường deterministic:

- generator dùng template gắn với teacher move

Nếu đi đường LLM:

- model phải viết một hint ngắn
- theo teacher move
- không lộ forbidden content
- không vượt độ dài cho phép

### 25.2. Minimal repair sửa gì trước tiên

Minimal repair là cố giữ hint gốc càng nhiều càng tốt.  
Nó làm tuần tự:

1. chuẩn hóa whitespace
2. loại hoặc thay hidden number / hidden text
3. cắt bớt số câu
4. nếu thiếu cue teacher move thì thêm một câu cue ngắn
5. nếu hint conceptual quá computational thì thay các từ quá trực tiếp

Mục tiêu của minimal repair là:

- cứu những hint chỉ sai nhẹ
- không viết lại toàn bộ nếu chưa cần

### 25.3. Guided rewrite hoạt động ra sao

Nếu minimal repair vẫn chưa pass:

- hệ thống sinh lại một hint ngắn từ plan
- teacher move quyết định skeleton câu
- focus points quyết định nội dung nhắm tới
- must-not-reveal được dùng để tránh những từ/giá trị bị cấm

Guided rewrite là deterministic nhưng mang tính sư phạm hơn fallback.

### 25.4. LLM repair dùng thông tin gì

LLM repair nhận:

- original hint
- violated rules
- diagnosis
- pedagogy plan
- reference answer
- hint mode

Model được yêu cầu:

- giữ teacher move
- loại spoiler
- rút ngắn nếu cần
- viết lại an toàn nếu original hint không cứu được

### 25.5. Verify hint kết luận pass/fail như thế nào

Verifier không chấm kiểu cảm tính, mà gộp:

- no-spoiler violations
- alignment violations

Nếu cả hai rỗng:

- hint pass

Nếu còn vi phạm:

- controller không trả ngay
- mà còn có cơ hội repair hoặc fallback

### 25.6. Fallback được đặt cuối cùng để làm gì

Fallback tồn tại như một safety net:

- không nhằm tối ưu độ hay
- nhằm đảm bảo hệ không trả một hint nguy hiểm hoặc spoiler

Do đó, flow đúng là:

`generate -> verify -> repair -> verify -> fallback`

và không phải:

`generate -> fail -> fallback`

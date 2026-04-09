# Trực Quan Hóa Cách Hệ Thống Hoạt Động Bằng Neo4j

Có. Neo4j dùng **Cypher** làm ngôn ngữ truy vấn và thao tác đồ thị.

Nếu mục tiêu là trực quan hóa:

1. các module của hệ thống
2. các artifact (đầu vào, đầu ra trung gian, đầu ra cuối)
3. luồng dữ liệu giữa các module

thì Neo4j là một lựa chọn hợp lý vì pipeline hiện tại của dự án vốn đã có cấu trúc rất giống đồ thị:

- mỗi module nhận một số artifact
- tạo ra artifact mới
- artifact đó lại đi tiếp sang module sau

## 1. Vì sao bạn gặp lỗi bộ nhớ

Lỗi bạn gặp là:

- `Neo.TransientError.General.MemoryPoolOutOfMemoryError`

Đây là lỗi transaction memory (bộ nhớ của transaction), không phải lỗi cú pháp Cypher.

Nguyên nhân thực tế ở đây là:

- bạn chạy quá nhiều lệnh trong một lần
- Neo4j giữ toàn bộ thay đổi của transaction đó trong bộ nhớ
- đến giữa chừng thì transaction vượt ngưỡng `dbms.memory.transaction.total.max`

Vì vậy, với file Cypher này, cách chạy đúng là:

- **chạy từng block**
- **không chạy cả file một lần**

Tôi đã sửa file `.cypher` theo đúng hướng này.

## 2. File đã tạo

Tôi đã tạo file Cypher:

- [neo4j_pipeline_visualization.cypher](C:/Users/linhn/Desktop/Dự%20án/docs/neo4j_pipeline_visualization.cypher)

File này dựng hai lớp đồ thị:

1. **đồ thị kiến trúc tĩnh**
   - cho thấy pipeline tổng quát của hệ thống
   - module nào đứng trước, module nào đứng sau
   - artifact type nào đi vào và đi ra ở từng module

2. **đồ thị một run minh họa**
   - dùng ví dụ `847` trong các file debug problem/student
   - cho thấy dữ liệu đi qua các bước như thế nào
   - có các nút minh họa như:
     - `FormalizedProblem`
     - `CanonicalReference`
     - `StudentWorkState`
     - `DiagnosisEvidence`
     - `DiagnosisResult`
     - `HintPlan`
     - `HintResult`

## 3. Cách chạy đúng trong Neo4j Browser

Mở file:

- [neo4j_pipeline_visualization.cypher](C:/Users/linhn/Desktop/Dự%20án/docs/neo4j_pipeline_visualization.cypher)

Sau đó:

1. chỉ bôi đen **một block**
2. chạy block đó
3. chờ block chạy xong
4. mới chạy block tiếp theo

Trong file, các block đã được đánh số rõ:

- `BLOCK 1`
- `BLOCK 2`
- ...
- `BLOCK 12`

Thứ tự nên chạy là từ trên xuống dưới.

Không nên:

- mở file rồi bấm chạy toàn bộ
- bôi đen nhiều block cùng lúc

## 4. Mô hình trực quan hóa đang dùng

### 2.1 Các loại node chính

Trong đồ thị này có các nhóm node chính:

- `Pipeline`
  - biểu diễn toàn bộ hệ thống

- `Module`
  - biểu diễn từng bước lớn trong pipeline
  - ví dụ:
    - `formalize_problem`
    - `build_canonical_reference`
    - `formalize_student_work`
    - `build_diagnosis_evidence`
    - `diagnose`
    - `build_hint_plan`
    - `build_hint_result`

- `ArtifactType`
  - biểu diễn kiểu dữ liệu đi giữa các module
  - ví dụ:
    - `problem_text`
    - `student_answer`
    - `FormalizedProblem`
    - `CanonicalReference`
    - `StudentWorkState`
    - `DiagnosisEvidence`
    - `DiagnosisResult`
    - `HintPlan`
    - `HintResult`

- `PipelineRun`
  - biểu diễn một lần chạy cụ thể

- `Execution`
  - biểu diễn một bước thực thi cụ thể bên trong một run

- `Artifact`
  - biểu diễn artifact cụ thể được tạo ra trong run đó

- một số node chi tiết phụ cho ví dụ `847`
  - `Quantity`
  - `Target`
  - `ReferenceFinal`
  - `StudentFinal`

### 2.2 Các loại quan hệ chính

Đồ thị dùng các cạnh sau:

- `HAS_STAGE`
  - pipeline có module nào

- `NEXT_STAGE`
  - thứ tự logic giữa các module

- `INPUT_TO`
  - artifact đi vào module hoặc execution nào

- `OUTPUT_TYPE`
  - module loại gì sẽ tạo ra loại artifact gì

- `HAS_STEP`
  - một run có những bước thực thi nào

- `USES_MODULE`
  - execution đó là hiện thân của module nào

- `NEXT_EXECUTION`
  - thứ tự thực thi thực tế của các bước trong một run

- `OUTPUT`
  - execution tạo ra artifact nào

- `HAS_QUANTITY`, `HAS_TARGET`, `HAS_FINAL_ANSWER`, `TARGETS`
  - dùng để gắn vài chi tiết minh họa cho ví dụ `847`

## 5. Vì sao mô hình này phù hợp với code hiện tại

`src/pipeline/runner.py` cho thấy pipeline hiện tại chạy theo thứ tự rất rõ:

1. `formalize_problem(...)`
2. `build_canonical_reference(problem)`
3. `formalize_student_work(...)`
4. `build_diagnosis_evidence(problem, reference, student_work)`
5. `diagnose(evidence, llm_client=...)`
6. `build_hint_plan(problem, reference, diagnosis)`
7. `build_hint_result(problem, reference, diagnosis, hint_plan, ...)`

Vì vậy, nếu đưa lên Neo4j, cách tự nhiên nhất là biểu diễn:

- module như các node
- artifact như các node
- dữ liệu chảy từ artifact sang module rồi từ module sang artifact mới

Nói cách khác:

- đây không phải “vẽ sơ đồ minh họa cho đẹp”
- mà là đang chuyển đúng kiến trúc hiện tại của code sang một graph model

Lưu ý:

- script chỉ xóa các node mang label `Demo`
- nó không đụng vào dữ liệu khác ngoài demo graph này

## 6. Các câu Cypher nên chạy để xem đồ thị

### 5.1 Xem kiến trúc pipeline tổng quát

```cypher
MATCH (p:Demo:Pipeline {id: 'tutoring_pipeline'})-[r]-(n:Demo)
RETURN p, r, n
```

Query này cho bạn cái nhìn tổng quát:

- pipeline có những module nào
- mỗi module nối với artifact type nào

### 5.2 Xem riêng chuỗi module theo thứ tự

```cypher
MATCH p=(:Demo:Module {id: 'formalize_problem'})-[:NEXT_STAGE*]->(:Demo:Module {id: 'build_hint_result'})
RETURN p
```

Query này giúp bạn trình bày:

- hệ thống đi từ đâu đến đâu
- thứ tự các bước lớn

### 5.3 Xem run minh họa `847`

```cypher
MATCH (r:Demo:PipelineRun {run_id: 'demo_847'})-[rel]-(n:Demo)
RETURN r, rel, n
```

Query này cho thấy:

- input của run
- từng execution step
- artifact nào được sinh ở mỗi bước

### 5.4 Chỉ xem luồng artifact trong run `847`

```cypher
MATCH (r:Demo:PipelineRun {run_id: 'demo_847'})-[:HAS_STEP]->(e:Demo:Execution)
OPTIONAL MATCH (a_in:Demo:Artifact)-[:INPUT_TO]->(e)
OPTIONAL MATCH (e)-[:OUTPUT]->(a_out:Demo:Artifact)
RETURN r, e, a_in, a_out
ORDER BY e.order
```

Query này phù hợp nhất nếu bạn muốn giải thích “dữ liệu đi qua hệ thống như thế nào”.

### 5.5 Chỉ xem phần chênh lệch giữa reference và student trên ví dụ `847`

```cypher
MATCH (s:Demo:StudentFinal)-[r:DIFFERS_FROM]->(t:Demo:ReferenceFinal)
RETURN s, r, t
```

Query này rất hữu ích để nói ngắn gọn:

- reference của hệ là `121`
- bài làm học sinh kết thúc ở `117`
- toàn bộ các bước evidence, diagnosis và hint được xây tiếp từ chênh lệch đó

## 7. Ý nghĩa trực quan của đồ thị này khi trình bày

Nếu bạn dùng đồ thị này để trình bày với cô, tôi khuyên tách làm hai lượt:

### Lượt 1: nhìn ở mức kiến trúc

Cho thấy:

- hệ thống không phải chỉ có một model gọi một lần
- mà là một pipeline nhiều tầng
- mỗi tầng nhận đầu vào có cấu trúc và tạo ra đầu ra có cấu trúc

### Lượt 2: nhìn ở mức ví dụ `847`

Cho thấy:

- đề bài đi vào `formalize_problem`
- hệ thống dựng `FormalizedProblem`
- từ đó dựng `CanonicalReference` với đáp án `121`
- bài làm học sinh đi vào `formalize_student_work`
- hệ thống dựng `StudentWorkState` với đáp án cuối `117`
- phần sau của pipeline dùng hai artifact này để tiếp tục suy luận

Điểm mạnh của cách trình bày này là:

- người nghe thấy được cả kiến trúc tổng quát
- đồng thời vẫn thấy được một ví dụ cụ thể đang chảy qua từng bước

## 8. Giới hạn của bản trực quan hóa này

Tôi giữ bản Neo4j này ở mức:

- đúng với pipeline hiện tại
- đủ rõ để trình bày
- không nhồi quá nhiều chi tiết lõi

Do đó:

- phần module và luồng artifact là chính xác theo `src/pipeline/runner.py`
- phần ví dụ `847` bám theo các output debug problem/student hiện có
- các artifact sau diagnosis/hint trong demo graph được giữ ở mức “khung của pipeline”, không giả vờ là log đầy đủ của một run thật nếu repo hiện chưa có full run riêng cho chính ví dụ `847`

Nếu bạn muốn bước tiếp theo, tôi có thể làm tiếp một bản thứ hai:

- trực quan hóa theo kiểu **đồ thị kiến thức nội bộ** của riêng `FormalizedProblem`, `StudentWorkState`, `Evidence`
- tức là không chỉ vẽ “module nào nối module nào”, mà còn vẽ cả quantity, target, step, evidence item ở mức sâu hơn.

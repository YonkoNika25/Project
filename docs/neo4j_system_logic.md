# Graph Neo4j Để Hiểu Logic Hệ Thống

File đi kèm:

- [neo4j_system_logic.cypher](C:/Users/linhn/Desktop/Dự%20án/docs/neo4j_system_logic.cypher)

Graph này dùng cho mục tiêu:

- đọc logic nội bộ của hệ thống
- không chỉ xem pipeline tổng quát

## 1. Cách chạy

Mở file `.cypher` và chạy **từng block một** trong Neo4j Browser.

Không chạy cả file một lần.

Graph này dùng label:

- `Logic`

nên tách biệt với graph `Demo` của file trực quan hóa pipeline trước đó.

## 2. Graph này biểu diễn gì

Graph có 5 lớp:

1. `Stage`
   - Problem Side
   - Runtime Reference
   - Student Side
   - Evidence
   - Diagnosis
   - Pedagogy
   - Hint

2. `Module`
   - các file thật trong `src`

3. `Function`
   - các hàm lõi có vai trò cấu trúc trong pipeline

4. `Artifact`
   - các object dữ liệu trung gian như:
     - `problem evidence pack`
     - `heuristic FormalizedProblem`
     - `problem semantic sketch`
     - `FormalizedProblem`
     - `ExecutablePlan`
     - `CanonicalReference`
     - `heuristic StudentWorkState`
     - `student semantic sketch`
     - `StudentWorkState`
     - `DiagnosisEvidence`
     - `DiagnosisResult`
     - `HintPlan`
     - `HintResult`

5. `Concept`
   - các pattern kiến trúc đang dùng trong code:
     - `heuristic anchor`
     - `candidate generation`
     - `semantic sketch`
     - `local compile`
     - `validation and retry`
     - `fallback`
     - `global alignment`
     - `deterministic scoring`
     - `pedagogical planning`
     - `hint verification`

## 3. Các cạnh quan trọng

- `HAS_STAGE`
  - hệ có stage nào

- `HAS_MODULE`
  - stage nào chứa module nào

- `DEFINES`
  - module nào định nghĩa function nào

- `CALLS`
  - function nào gọi function nào

- `READS`
  - function nào đọc artifact nào

- `PRODUCES`
  - function nào tạo artifact nào

- `HAS_SUBARTIFACT`
  - artifact lớn chứa artifact con

- `IMPLEMENTS` / `USES`
  - function đó đang hiện thực pattern thiết kế nào

- `CAN_FALLBACK_TO`
  - function nào có đường fallback về artifact heuristic

## 4. Cách đọc graph

### 4.1 Muốn hiểu problem side

Chạy:

```cypher
MATCH p=(:Logic:Function {id:'formalize_problem'})-[:CALLS*1..4]->(n:Logic:Function)
RETURN p
```

Bạn sẽ thấy trục chính:

- `formalize_problem`
- `_heuristic_formalize_problem`
- `_build_problem_anchor_evidence`
- `_llm_formalize_problem`
- `_build_formalized_problem_from_skeleton`
- các hàm compile graph

### 4.2 Muốn hiểu student side

Chạy:

```cypher
MATCH p=(:Logic:Function {id:'formalize_student_work'})-[:CALLS*1..5]->(n:Logic:Function)
RETURN p
```

Bạn sẽ thấy:

- heuristic path
- LLM path
- build from sketch
- repair target ref
- reconcile mode
- attach student graph

### 4.3 Muốn hiểu evidence

Chạy:

```cypher
MATCH p=(:Logic:Function {id:'build_diagnosis_evidence'})-[:CALLS*1..3]->(n:Logic:Function)
RETURN p
```

Bạn sẽ thấy:

- `reference_steps`
- `student_steps`
- `global_align_student_steps`
- `infer_student_target_ref`
- `student_graph_has_target_path`
- `graph_edit_summary`

### 4.4 Muốn hiểu diagnosis có deterministic lõi thế nào

Chạy:

```cypher
MATCH p=(:Logic:Function {id:'diagnose'})-[:CALLS*1..3]->(n:Logic:Function)
RETURN p
```

Bạn sẽ thấy:

- `diagnose`
- `_deterministic_diagnosis`
- `_llm_diagnose`
- `build_diagnosis_hypotheses`
- các scorer cụ thể

### 4.5 Muốn hiểu hint được kiểm soát ra sao

Chạy:

```cypher
MATCH p=(:Logic:Function {id:'build_hint_result'})-[:CALLS*1..3]->(n:Logic:Function)
RETURN p
```

Bạn sẽ thấy:

- `generate_hint_text`
- `verify_hint_text`
- `repair_hint_text`

## 5. Query tổng quát nên dùng

Xem toàn bộ graph:

```cypher
MATCH (n:Logic)
OPTIONAL MATCH (n)-[r]->(m:Logic)
RETURN n,r,m
```

Xem stage -> module -> function:

```cypher
MATCH p=(s:Logic:Stage)-[:HAS_MODULE]->(m:Logic:Module)-[:DEFINES]->(f:Logic:Function)
RETURN p
```

Xem artifact flow:

```cypher
MATCH (f:Logic:Function)-[r:READS|PRODUCES|HAS_SUBARTIFACT]->(a:Logic:Artifact)
RETURN f,r,a
```

Xem design patterns:

```cypher
MATCH (f:Logic:Function)-[r:IMPLEMENTS|USES]->(c:Logic:Concept)
RETURN f,r,c
```

## 6. Cách dùng graph này cho mục tiêu của bạn

Nếu mục tiêu là “xem kỹ và hiểu kỹ logic của hệ thống”, cách tốt nhất là:

1. nhìn theo `Stage` để hiểu kiến trúc lớn
2. nhìn theo `Module` để biết logic nằm ở file nào
3. nhìn theo `Function` để hiểu call graph
4. nhìn theo `Artifact` để hiểu dữ liệu thay đổi thế nào
5. nhìn theo `Concept` để hiểu hệ đang dùng pattern kiến trúc gì

Graph này không thay thế việc đọc code, nhưng nó giúp bạn có một bản đồ logic rõ ràng hơn nhiều trước khi đi vào source.


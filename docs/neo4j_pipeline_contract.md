# Neo4j Pipeline Contract

File này biểu diễn pipeline ở mức:

- module nhận input gì
- đi qua các substep chính nào
- trả output gì

Graph này không đi sâu vào cơ chế lõi của từng hàm. Mục đích là nhìn ra:

- `formalize_problem`
  - nhận `problem_text`
  - heuristic parse tạo gì
  - LLM nhận gì và trả gì
  - local build tạo gì
  - validate/retry trả output cuối ra sao
- và tương tự cho toàn bộ pipeline

## Cách nạp

Chạy từng block trong [neo4j_pipeline_contract.cypher](/c:/Users/linhn/Desktop/Dự%20án/docs/neo4j_pipeline_contract.cypher), hoặc nạp bằng `cypher-shell` theo block.

## Các query nên dùng

### 1. Xem toàn bộ graph contract

```cypher
MATCH (n:Contract)
OPTIONAL MATCH (n)-[r]->(m:Contract)
RETURN n, r, m
```

### 2. Xem module và các substep

```cypher
MATCH p=(m:Contract:Module)-[:HAS_STEP]->(s:Contract:Step)
RETURN p
```

### 3. Xem input/output của từng substep

```cypher
MATCH (a:Contract:Artifact)-[:INPUT_TO]->(s:Contract:Step)
OPTIONAL MATCH (s)-[:OUTPUTS]->(b:Contract:Artifact)
RETURN a, s, b
```

### 4. Xem riêng `formalize_problem`

```cypher
MATCH p=(m:Contract:Module {id:'formalize_problem'})-[:HAS_STEP]->(s:Contract:Step)
OPTIONAL MATCH (a:Contract:Artifact)-[:INPUT_TO]->(s)
OPTIONAL MATCH (s)-[:OUTPUTS]->(b:Contract:Artifact)
RETURN p, a, b
```

### 5. Xem riêng `formalize_student_work`

```cypher
MATCH p=(m:Contract:Module {id:'formalize_student_work'})-[:HAS_STEP]->(s:Contract:Step)
OPTIONAL MATCH (a:Contract:Artifact)-[:INPUT_TO]->(s)
OPTIONAL MATCH (s)-[:OUTPUTS]->(b:Contract:Artifact)
RETURN p, a, b
```

### 6. Xem luồng output module này feed sang module nào

```cypher
MATCH (a:Contract:Artifact)-[:FEEDS_MODULE]->(m:Contract:Module)
RETURN a, m
```

# Báo Cáo Tổng Thể Dự Án Gia Sư Toán

## 1. Phát biểu vấn đề

### 1.1 Bối cảnh

Dự án này xây dựng một hệ thống gia sư toán có thể kiểm chứng từng bước. Thay vì để mô hình ngôn ngữ trả lời tự do từ văn bản đầu vào, hệ thống đi theo một chuỗi xử lý nhiều tầng (thường gọi là pipeline), trong đó mỗi tầng tạo ra dữ liệu có cấu trúc để tầng sau tiếp tục sử dụng.

Mục tiêu chính:

- chuẩn hóa đề bài thành dạng dữ liệu chặt chẽ,
- dựng lời giải chuẩn theo từng bước,
- chuẩn hóa bài làm học sinh để so sánh theo tiến trình,
- chẩn đoán lỗi dựa trên bằng chứng có cấu trúc,
- tạo gợi ý một cách chuẩn sư phạm và kiểm tra trước khi trả ra.

### 1.2 Bài toán kỹ thuật cốt lõi

Hệ thống phải xử lý đồng thời hai nguồn dữ liệu không ổn định:

- `problem_text`: đề bài tự nhiên, nhiều cách diễn đạt, có thông tin ẩn.
- `student_answer`: bài làm học sinh có thể thiếu bước, nhảy bước, sai phép tính, sai đại lượng cần tìm, hoặc chỉ có đáp án cuối.

Nếu chỉ làm việc với văn bản thuần, hệ thống sẽ khó:

- xác định sai ở bước nào,
- phân biệt sai phép tính với sai mục tiêu,
- đưa gợi ý đúng mức, không lộ kết quả cần giữ kín.

Vì vậy dự án đặt trọng tâm vào dữ liệu trung gian có cấu trúc: lược đồ dữ liệu, đồ thị, vết chạy thực thi, bằng chứng so khớp và kết luận chẩn đoán.

---

## 2. Phạm vi

### 2.1 Thành phần nằm trong phạm vi báo cáo

Báo cáo này bao quát toàn bộ luồng chính của dự án:

- Bộ điều phối và điểm chạy:
  - `main.py`
  - `src/pipeline/runner.py`
- Khối chuẩn hóa:
  - `src/formalizer/*`
- Khối dựng lời giải chuẩn:
  - `src/runtime/*`
- Khối tạo bằng chứng và chẩn đoán:
  - `src/evidence/*`
  - `src/diagnosis/*`
- Khối kế hoạch sư phạm và tạo gợi ý:
  - `src/pedagogy/*`
  - `src/hint/*`
- Hợp đồng dữ liệu:
  - `src/models/schemas.py`
  - `src/models/formalizer_schemas.py`
- Thành phần hỗ trợ:
  - `src/input_loader.py`
  - `src/llm/client.py`
  - `benchmarks/*`
  - `debug/*`


---

## 3. Chuỗi xử lý tổng thể và đầu vào/đầu ra từng khối

### 3.1 Luồng tổng quan

Hàm `run_tutoring_pipeline(...)` thực thi theo thứ tự:

1. Chuẩn hóa đề bài.
2. Dựng lời giải chuẩn có thể thực thi.
3. Chuẩn hóa bài làm học sinh.
4. Tạo bằng chứng chẩn đoán.
5. Chẩn đoán lỗi.
6. Lập kế hoạch sư phạm.
7. Tạo gợi ý và kiểm tra gợi ý (`generate -> verify -> repair -> verify -> fallback`).
8. Trả về `TutoringResult`.

### 3.2 Sơ đồ rút gọn

```text
problem_text + student_answer
  -> Chuẩn hóa đề bài
  -> Dựng lời giải chuẩn
  -> Chuẩn hóa bài làm học sinh
  -> Tạo bằng chứng
  -> Chẩn đoán lỗi sai
  -> Lập kế hoạch sư phạm
  -> Tạo và kiểm tra gợi ý
  -> TutoringResult
```

### 3.3 Bảng đầu vào/đầu ra theo khối

| Bước | Khối | Đầu vào chính | Tham số quan trọng | Đầu ra chính | Công dụng | Tệp mã chính |
|---|---|---|---|---|---|---|
| 1 | `load_problem_and_student_answer(..)` | Đường dẫn `problem_path`, `student_answer_path`; nội dung tệp `input/problem.txt`, `input/student_answer.txt` | `problem_path`: chỉ tới tệp đề cần đọc<br>`student_answer_path`: chỉ tới tệp bài học sinh cần đọc | `problem_text`, `student_answer` (2 chuỗi đã làm sạch) | Đọc đầu vào thô từ tệp | `src/input_loader.py` |
| 2 | `run_tutoring_pipeline(..)` | `problem_text`, `student_answer`, `hint_mode`, `llm_client`, `use_llm` | `problem_text`: đề gốc đưa vào luồng xử lý<br>`student_answer`: lời giải học sinh để phân tích<br>`hint_mode`: cách trình bày gợi ý đầu ra<br>`llm_client`: đối tượng gọi LLM dùng chung toàn luồng<br>`use_llm`: nếu bật thì cho phép tạo client mặc định khi chưa truyền vào | Cuối hàm trả `TutoringResult` gồm `problem`, `reference`, `student_work`, `evidence`, `diagnosis`, `hint_plan`, `hint_result` | Gọi tuần tự các bước 3 -> 13 và gom kết quả cuối | `src/pipeline/runner.py` |
| 3 | `formalize_problem(..)` | `problem_text`; tùy chọn `llm_client` | `problem_text`: nguồn thông tin chính để trích đại lượng/quan hệ<br>`llm_client`: dùng để tinh chỉnh ngữ nghĩa; nếu `None` thì dùng nhánh heuristic | `FormalizedProblem` gồm `problem_text`, `quantities`, `entities`, `target`, `relation_candidates`, `problem_graph`, `assumptions`, `confidence`, `notes` | Chuyển đề tự nhiên thành dữ liệu có cấu trúc | `src/formalizer/problem_formalizer.py` |
| 4 | `validate_problem_graph(..)` | `FormalizedProblem.problem_graph` (các `nodes`, `edges`, `target_node_id`) + `problem.quantities` | `problem_graph`: nguồn để kiểm tra liên kết và thứ tự phụ thuộc<br>`quantities`: dùng để đối chiếu tham chiếu đầu vào của các phép toán | `GraphValidationResult` gồm `is_valid`, `issues`, `target_node_id`, `operation_node_count`, `notes` | Chặn lỗi đồ thị trước khi biên dịch và chạy | `src/runtime/graph_validator.py` |
| 5 | `compile_executable_plan(..)` | `FormalizedProblem` (đặc biệt `target`, `relation_candidates`, `problem_graph`, `quantities`) | `problem_graph`: nếu hợp lệ thì ưu tiên biên dịch theo đồ thị<br>`relation_candidates`: dùng làm đường lùi chọn kiểu kế hoạch<br>`target`: xác định biến đích `target_ref` | `ExecutablePlan` gồm `plan_id`, `target_ref`, `steps` (`step_id`, `operation`, `expression`, `input_refs`, `output_ref`), `assumptions`, `confidence`, `notes` | Tạo kế hoạch tính toán | `src/runtime/compiler.py` |
| 6 | `execute_plan(..)` | `ExecutablePlan`; ràng buộc số ban đầu từ `problem.quantities` (`quantity_id -> value`) | `plan.steps`: xác định thứ tự phép tính phải chạy<br>`plan.target_ref`: biến đích bắt buộc phải tạo ra<br>`problem.quantities`: nguồn giá trị ban đầu cho môi trường tính toán | `ExecutionTrace` gồm `plan_id`, `step_results` (`resolved_inputs`, `output_value`, `success`), `final_value`, `success`, `error_message`, `notes` | Chạy từng bước và ghi vết thực thi | `src/runtime/executor.py` |
| 7 | `build_canonical_reference(..)` | `FormalizedProblem` + kết quả bước 5, 6 | `problem`: nguồn duy nhất để dựng plan và trace chuẩn<br>`trace.final_value`: giá trị dùng làm đáp án chuẩn cuối | `CanonicalReference` gồm `final_answer`, `chosen_plan`, `execution_trace`, `rendered_solution_text`, `confidence`, `notes` | Tạo mốc lời giải chuẩn để so sánh | `src/runtime/solver.py` |
| 8 | `formalize_student_work(..)` | `raw_answer`; ngữ cảnh `problem`, `reference`; tùy chọn `llm_client` | `raw_answer`: văn bản gốc của học sinh<br>`problem`: cung cấp ngữ cảnh đề để hiểu ý nghĩa bước làm<br>`reference`: cung cấp mốc chuẩn để chọn target và bước liên quan<br>`llm_client`: tinh chỉnh phân tích khi cần | `StudentWorkState` gồm `raw_answer`, `normalized_final_answer`, `mode`, `semantic_facts`, `steps`, `student_graph`, `selected_target_ref`, `confidence`, `notes` | Chuyển bài học sinh thành dữ liệu đối chiếu được | `src/formalizer/student_work.py` |
| 9 | `global_align_student_steps(..)` + `graph_edit_summary(..)` | `StudentWorkState` + `CanonicalReference` (bước, phụ thuộc, giá trị từng bước) | `student.steps`: dữ liệu tiến trình bên học sinh<br>`student.student_graph`: quan hệ phụ thuộc giữa bước học sinh<br>`reference.chosen_plan` + `reference.execution_trace`: chuẩn so khớp bước và giá trị | Bản đồ so khớp bước gồm `student_step_id`, `reference_step_id`, `matched_output_ref`, `relationship`, `score`; và tóm tắt chỉnh sửa đồ thị (`total_cost`, `node_*`, `edge_*`) | So sánh tiến trình học sinh với tiến trình chuẩn | `src/evidence/alignment.py` |
| 10 | `build_diagnosis_evidence(..)` | `problem`, `reference`, `student`; dữ liệu so khớp từ bước 9 | `reference.final_answer`: so đáp án cuối đúng/sai<br>`reference.chosen_plan.target_ref`: xác định đại lượng đích chuẩn<br>`student.normalized_final_answer`: tín hiệu đầu ra của học sinh<br>`student.mode`: phát hiện trường hợp không phân tích được (`UNPARSEABLE`) | `DiagnosisEvidence` gồm `evidence_items`, `alignment_map`, `first_divergence_step_id`, `likely_error_mechanisms`, `confidence`, `notes` | Gom tín hiệu sai khác thành bằng chứng có cấu trúc | `src/evidence/builder.py` |
| 11 | `diagnose(..)` | `DiagnosisEvidence`; tùy chọn `llm_client` | `evidence.evidence_items`: tín hiệu chính để chấm điểm giả thuyết<br>`evidence.alignment_map`: giúp định vị kiểu lệch tiến trình<br>`llm_client`: phản biện/tinh chỉnh kết luận tất định khi có | `DiagnosisResult` gồm `diagnosis_label`, `subtype`, `localization`, `target_step_id`, `summary`, `supporting_evidence_types`, `confidence`, `notes` | Chọn kết luận lỗi dựa trên bằng chứng | `src/diagnosis/engine.py` |
| 12 | `build_hint_plan(..)` | `problem`, `reference`, `diagnosis` | `diagnosis.diagnosis_label`: quyết định kiểu can thiệp<br>`diagnosis.target_step_id`: chọn bước cần tập trung<br>`reference.final_answer` và giá trị trung gian: đưa vào danh sách không được lộ | `HintPlan` gồm `hint_level`, `teacher_move`, `target_step_id`, `disclosure_budget`, `focus_points`, `must_not_reveal`, `rationale`, `confidence` | Xác định cách gợi ý phù hợp mục tiêu dạy học | `src/pedagogy/planner.py` |
| 13 | `build_hint_result(..)` | `problem`, `reference`, `diagnosis`, `plan`; `hint_mode`; tùy chọn `llm_client` | `plan.teacher_move`: định hướng nội dung gợi ý<br>`plan.must_not_reveal`: ràng buộc thông tin cấm lộ<br>`hint_mode`: điều khiển kiểu diễn đạt gợi ý<br>`llm_client`: dùng để sinh/sửa gợi ý trước khi kiểm tra | `HintResult` gồm `hint_text`, `hint_level`, `hint_mode`, `verification_passed`, `violated_rules`, `confidence`, `notes` | Sinh gợi ý, kiểm tra vi phạm, sửa gợi ý, dự phòng khi cần | `src/hint/controller.py` |

### 3.4 Các dữ liệu trung gian then chốt

Những kiểu dữ liệu quan trọng nối các khối:

- `FormalizedProblem`: đề bài đã chuẩn hóa.
- `CanonicalReference`: lời giải chuẩn có thể chạy.
- `StudentWorkState`: bài học sinh đã chuẩn hóa.
- `DiagnosisEvidence`: bằng chứng phục vụ chẩn đoán.
- `DiagnosisResult`: nhãn lỗi và vị trí lỗi.
- `HintPlan`: kế hoạch sư phạm trước khi tạo gợi ý.
- `HintResult`: gợi ý cuối cùng sau kiểm tra.
- `TutoringResult`: gói kết quả đầy đủ của toàn hệ thống.

### 3.5 Vai trò của kiến trúc lai

Hệ thống dùng cách kết hợp:

- LLM cho phần hiểu nghĩa và diễn đạt tự nhiên (khi có cấu hình).
- Logic tất định cho phần cần kiểm chứng:
  - kiểm tra hợp lệ,
  - biên dịch kế hoạch,
  - thực thi tính toán,
  - so khớp tiến trình,
  - chấm điểm chẩn đoán,
  - kiểm tra gợi ý.

Ưu điểm là khi LLM thất bại, hệ thống vẫn có đường lùi theo heuristic để duy trì luồng chạy.

---

## 4. Phương pháp đánh giá

### 4.1 Câu hỏi đánh giá trọng tâm

1. Hệ thống có chạy trọn vẹn từ đầu đến cuối không?
2. Dữ liệu trung gian ở từng tầng có hợp lệ và đủ dùng cho tầng sau không?
3. Kết luận chẩn đoán có bám theo bằng chứng đã xây không?
4. Gợi ý có đúng hướng sư phạm và không lộ thông tin cấm không?
5. Khi tắt LLM, chất lượng còn ở mức dùng được không?

### 4.2 Bộ chỉ số đề xuất

- **Tỷ lệ hoàn tất toàn luồng**:
  - tỷ lệ mẫu có `failing_stage = null`.
- **Độ hợp lệ từng tầng**:
  - tỷ lệ qua chuẩn hóa đề,
  - tỷ lệ dựng được lời giải chuẩn,
  - tỷ lệ chuẩn hóa được bài học sinh,
  - tỷ lệ qua tạo bằng chứng/chẩn đoán/tạo gợi ý.
- **Độ khớp đúng-sai cuối cùng**:
  - so sánh `pipeline_detected_final_correct` với nhãn kỳ vọng.
- **Phân bố nhãn chẩn đoán**:
  - kiểm tra xem hệ thống có dồn quá nhiều vào một nhãn hay không.
- **Số gợi ý không đạt kiểm tra**:
  - đếm `hint_verification_failures`.
- **Hiệu quả bộ nhớ đệm ngữ cảnh đề**:
  - theo dõi `problem_context_cache_hits`.

### 4.3 Quy trình đo thử hiện có trong dự án

1. Sinh dữ liệu đo thử bằng `benchmarks/generate_hint_diagnosis_stress_benchmark.py`.
2. Chạy đo thử bằng `benchmarks/run_hint_diagnosis_benchmark.py`:
   - `--use-llm` hoặc `--no-llm`,
   - có thể thêm `--limit` để chạy nhanh.
3. Lưu kết quả vào:
   - `benchmarks/results/*_results.jsonl`,
   - `benchmarks/results/*_summary.json`.
4. Xuất báo cáo HTML bằng `benchmarks/render_hint_diagnosis_benchmark_html.py`.

### 4.4 Quy trình gỡ lỗi phục vụ đánh giá

Thư mục `debug/` tách script theo từng mô-đun, giúp:

- xem rõ yêu cầu/phản hồi LLM,
- xác nhận đường lùi khi lỗi,
- ghi kết quả vào `debug/ouput/`,
- khoanh vùng sự cố theo từng khối thay vì chỉ thấy lỗi cuối.

### 4.5 Rủi ro khi đánh giá và cách xử lý

- Rủi ro 1: tập chạy quá nhỏ, chưa đại diện.
  - Cách xử lý: chạy đủ `200` mẫu và chia theo nhóm bài.
- Rủi ro 2: chỉ nhìn kết quả cuối, bỏ qua lỗi trung gian.
  - Cách xử lý: lưu đầy đủ dữ liệu trung gian ở từng tầng.
- Rủi ro 3: so sánh không công bằng giữa bật/tắt LLM.
  - Cách xử lý: chạy song song trên cùng dữ liệu, cùng cấu hình giới hạn.

---

## 5. Mốc đối chiếu (Baseline)

### 5.1 Baseline kỹ thuật hiện có

Dự án đang có hai mốc đối chiếu rõ ràng:

- **Không dùng LLM (chế độ tất định/heuristic)**:
  - chạy với `llm_client=None` hoặc cờ `--no-llm`,
  - các khối vẫn hoạt động nhờ quy tắc cục bộ, chấm điểm chẩn đoán và bộ kiểm tra gợi ý.
- **Có dùng LLM (chế độ tăng cường)**:
  - LLM hỗ trợ một số khối khó về ngữ nghĩa: chuẩn hóa, phản biện chẩn đoán, tạo/sửa gợi ý.

Ý nghĩa: baseline của dự án là “toàn bộ hệ thống nhưng không gọi LLM”, không phải một mô hình rút gọn mất chức năng.

### 5.2 Số liệu baseline đang có trong kho mã

Nguồn số liệu:

- `benchmarks/results/cache_check_summary.json` (`llm_enabled=false`)
- `benchmarks/results/hint_diagnosis_benchmark_summary.json` (`llm_enabled=true`)

Kết quả đang lưu (chạy nhanh `10` mẫu):

| Chỉ số | Không dùng LLM | Có dùng LLM |
|---|---:|---:|
| `sample_count` | 10 | 10 |
| `stage_counts.completed` | 10 | 10 |
| `hint_verification_failures` | 0 | 0 |
| `problem_context_cache_hits` | 7 | 7 |
| `final_correctness_agreement` | 10 | 9 |

Phân bố nhãn chẩn đoán:

- Không dùng LLM: chủ yếu `unknown_error` (8) và `arithmetic_error` (2).
- Có dùng LLM: `arithmetic_error` (8) và `target_misunderstanding` (2).

Nhận xét sơ bộ:

- Cả hai chế độ đều ổn định ở mức vận hành (hoàn tất 10/10, không có gợi ý vi phạm).
- Chế độ có LLM cho nhãn chẩn đoán cụ thể hơn (ít `unknown_error`), nhưng trên tập nhỏ này chưa cho thấy cải thiện rõ ở chỉ số đúng-sai cuối.

### 5.3 Giới hạn của baseline hiện tại

- Mới là tập chạy nhanh `10` mẫu, chưa đại diện cho tập thử tải `200` mẫu.
- Chưa có mốc đối chiếu với giáo viên thật hoặc thang đánh giá sư phạm độc lập.
- Chưa đo được tác động học tập sau gợi ý (ví dụ tỷ lệ học sinh sửa đúng ở lượt sau).

---

## 6. Kết luận

### 6.1 Tóm tắt

Dự án đã có đầy đủ các phần cốt lõi của một hệ thống gia sư toán có thể kiểm chứng:

- chuẩn hóa đề và bài học sinh bằng dữ liệu có cấu trúc,
- tạo lời giải chuẩn bằng biên dịch và thực thi,
- chẩn đoán dựa trên bằng chứng tiến trình,
- tạo gợi ý theo kế hoạch sư phạm và có khâu kiểm tra,
- có công cụ đo thử và gỡ lỗi theo từng khối.

### 6.2 Đánh giá hiện trạng

- Kiến trúc rõ ràng, tách mô-đun tốt.
- Có đường lùi khi LLM lỗi nên độ bền vận hành cao hơn cách phụ thuộc hoàn toàn vào LLM.
- Đã có nền đo thử đủ tốt để theo dõi chất lượng theo thời gian.

### 6.3 Hướng mở rộng gần nhất

1. Chạy đủ tập `200` mẫu cho cả hai chế độ bật/tắt LLM và so sánh theo từng nhóm bài.
2. Bổ sung chỉ số chất lượng chẩn đoán theo `variant_type`.
3. Bổ sung thang đánh giá chất lượng gợi ý ở mức sư phạm, không chỉ dựa vào quy tắc cứng.
4. Chuẩn hóa báo cáo định kỳ theo từng khối để phát hiện suy giảm chất lượng sớm.

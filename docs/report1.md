# Báo Cáo Chi Tiết: Phân Tích Formalizer Pipeline

## 1. Giới thiệu

Tài liệu này là báo cáo chi tiết cho module **formalizer** trong dự án, được xây dựng dựa trên phân tích mã nguồn hiện tại và tài liệu kỹ thuật nội bộ. Mục tiêu của báo cáo là chuyển phần mô tả kỹ thuật rời rạc thành một khung đánh giá có thể dùng cho cả kỹ sư phát triển, kiểm thử và quản lý chất lượng.

Báo cáo tập trung vào ba nội dung chính:

1. **Phát biểu vấn đề**: Bài toán hệ thống cần giải và vì sao cần formalizer.
2. **Phạm vi**: Ranh giới chức năng, giả định, giới hạn và các phần ngoài phạm vi.
3. **Phương pháp đánh giá**: Cách đo chất lượng module một cách định lượng và lặp lại được.

Ngữ cảnh của module formalizer trong pipeline tổng thể:

1. Nhận dữ liệu đầu vào dạng tự nhiên (đề toán, lời giải học sinh).
2. Chuyển về biểu diễn có cấu trúc (typed models, graph artifacts).
3. Cấp đầu vào chuẩn hóa cho các mô-đun downstream: runtime, evidence, diagnosis, hint.

Điểm quan trọng là formalizer không chỉ là parser văn bản. Formalizer đang đóng vai trò **hạ tầng chuẩn hóa tri thức**: mọi suy luận phía sau phụ thuộc mạnh vào chất lượng biểu diễn đầu ra của formalizer.

---

## 2. Phát biểu vấn đề

## 2.1 Bối cảnh nghiệp vụ

Hệ thống tutoring cần xử lý hai nguồn thông tin khác bản chất:

1. **Đề bài**: ngôn ngữ tự nhiên, chứa dữ kiện số, quan hệ toán, điều kiện ngầm, mục tiêu cần tìm.
2. **Bài làm học sinh**: văn bản tự do, mức độ chuẩn hóa thấp, có thể thiếu bước, sai phép toán, sai tham chiếu hoặc sai kết quả.

Nếu hệ thống giữ dữ liệu ở dạng text thuần, các mô-đun diagnosis và hint sẽ khó làm việc ổn định vì:

1. Không có định danh nhất quán cho quantity/step.
2. Không có graph để kiểm tra khả năng thực thi hoặc truy vết phụ thuộc.
3. Không có chuẩn hóa để so sánh reference vs student work một cách có hệ thống.

Vì vậy cần một lớp formalization trung gian để biến text thành cấu trúc có thể kiểm chứng bằng schema và validation.

## 2.2 Bài toán kỹ thuật cốt lõi

### A. Problem formalization

Cho đầu vào `problem_text`, hệ thống phải sinh `FormalizedProblem` gồm:

1. `quantities`: các đại lượng số có định danh và thuộc tính ngữ nghĩa.
2. `target`: đích cần giải (biến mục tiêu, câu hỏi chuẩn hóa).
3. `relation_candidates`: quan hệ toán học ứng viên.
4. `problem_graph`: graph thao tác có thể kiểm tra tính khả thi.

Khó khăn chính:

1. Mâu thuẫn giữa dữ kiện surface và cấu trúc suy luận thực.
2. Cần xử lý cả thông tin tường minh lẫn implicit cues.
3. Cần giữ được khả năng fallback khi LLM lỗi.

### B. Student-work formalization

Cho đầu vào `raw_answer` (và tùy chọn `problem`, `reference`), hệ thống phải sinh `StudentWorkState` gồm:

1. `normalized_final_answer` nếu trích được.
2. `mode` phản ánh mức độ parse được của bài làm.
3. `steps` + `semantic_facts` đã chuẩn hóa.
4. `student_graph` để đối sánh với graph chuẩn.

Khó khăn chính:

1. Text học sinh thiếu chuẩn (nhảy bước, viết tắt, sai cú pháp).
2. Khó phân biệt số “được nói ra” với số “model tự đoán”.
3. Cần ràng buộc groundedness để tránh hallucination trong nhánh LLM.

## 2.3 Mâu thuẫn thiết kế cần giải quyết

Formalizer hiện giải một mâu thuẫn trung tâm:

1. **Độ linh hoạt ngôn ngữ** (cần để hiểu được nhiều kiểu text)
2. **Độ chặt typed-graph** (cần để runtime/validator hoạt động ổn định)

Chiến lược hiện tại là mô hình hai tầng:

1. **Heuristic deterministic** tạo anchor + fallback.
2. **LLM semantic sketch** để tăng năng lực suy luận cấu trúc.
3. **Local compiler + validator** để kiểm soát đầu ra.

Nói cách khác, formalizer không để LLM trả artifact cuối, mà dùng LLM như bộ sinh proposal, sau đó local code chịu trách nhiệm đóng gói và kiểm định.

## 2.4 Tuyên bố vấn đề theo dạng đo lường được

Một tuyên bố vấn đề có thể kiểm thử:

> Với một tập đề toán và bài làm học sinh đa dạng, formalizer cần tạo ra biểu diễn cấu trúc đúng schema, có graph hợp lệ và đủ thông tin để downstream modules chạy ổn định; đồng thời khi nhánh LLM lỗi, hệ thống vẫn phải trả về artifact fallback hữu dụng và không làm vỡ pipeline.

Từ tuyên bố này, ta suy ra các yêu cầu chất lượng:

1. Tính đúng cấu trúc (schema validity).
2. Tính thực thi của graph (graph validity/executability).
3. Tính bền vững (fallback reliability).
4. Tính trung thực với đầu vào (groundedness).
5. Tính hỗ trợ downstream (diagnosis/hint utility).

---

## 3. Phạm vi

## 3.1 Phạm vi chức năng trong báo cáo

Báo cáo bao phủ các thành phần trong `src/formalizer`:

1. Entry points:
   1. `formalize_problem(...)`
   2. `formalize_student_work(...)`
2. Heuristic builders:
   1. `problem_formalizer_extractors.py`
   2. `problem_formalizer_builder.py`
   3. `student_work_builder.py`
3. LLM loops:
   1. `problem_formalizer_llm.py`
   2. `student_work_llm.py`
4. Validators/repairs:
   1. `problem_formalizer_validation.py`
   2. `student_work_validation.py`
5. Graph construction:
   1. `problem_graph.py`
   2. `student_work_graph.py`
6. Shared trace parsing:
   1. `reference_trace.py`

Đầu ra chính được đánh giá:

1. `FormalizedProblem`
2. `StudentWorkState`
3. `ProblemGraph` / `student_graph`
4. `GraphValidationResult` và các ghi chú fallback

## 3.2 Phạm vi tích hợp liên quan (liên đới)

Dù báo cáo tập trung formalizer, vẫn ghi nhận các điểm nối quan trọng:

1. `src/runtime/graph_validator.py` (validate executable graph của problem side).
2. Các mô-đun downstream (evidence/diagnosis/hint) dùng output của formalizer.

Các phần này chỉ được xem ở mức **điểm giao tiếp**, không đi sâu logic nội bộ trong báo cáo này.

## 3.3 Ngoài phạm vi

Các nội dung sau không nằm trong phạm vi báo cáo:

1. Benchmark hiệu năng hạ tầng (CPU/memory profiling sâu).
2. Tối ưu prompt engineering chi tiết theo từng model cụ thể.
3. Đánh giá UI/UX hoặc trải nghiệm người dùng cuối.
4. Thiết kế lại schema toàn dự án.
5. So sánh đa hệ thống (cross-project benchmark).

## 3.4 Giả định

Báo cáo giả định:

1. Schema Pydantic hiện tại là contract chính thức.
2. Các enum trong models là nguồn chân lý cho value hợp lệ.
3. Pipeline downstream kỳ vọng graph có thể kiểm chứng.
4. LLM client có thể trả lỗi bất kỳ lúc nào và phải có fallback.

## 3.5 Rủi ro trong phạm vi hiện tại

### A. Rủi ro do heuristic

1. Regex/cue rules có thể bỏ sót hoặc gán nhầm role.
2. Ambiguity cao trong relation candidate khi bài toán phức tạp.

### B. Rủi ro do LLM sketch

1. Sketch sai schema hoặc sai grounding.
2. Plan steps không tạo được target executable.

### C. Rủi ro do repair logic

1. Repair quá mạnh có thể che giấu lỗi thật.
2. Repair quá yếu có thể để lọt artifact không hữu dụng.

### D. Rủi ro tích hợp

1. Formalized output đúng schema nhưng không đủ thông tin cho diagnosis quality.
2. Student graph hợp lệ kỹ thuật nhưng không phản ánh đúng logic học sinh.

---

## 4. Phương pháp đánh giá

## 4.1 Nguyên tắc đánh giá

Phương pháp đánh giá đề xuất theo 5 lớp:

1. **Schema correctness**: output có hợp lệ model không.
2. **Graph correctness**: graph có hợp lệ và executable không.
3. **Semantic correctness**: target/relation/steps có hợp lý theo bài toán không.
4. **Robustness**: hệ thống có fallback tốt khi LLM hỏng không.
5. **Downstream utility**: output có giúp diagnosis/hint ổn định hơn không.

Cách làm này tránh tình trạng chỉ đo pass/fail schema mà bỏ qua chất lượng thực tế.

## 4.2 Thiết kế bộ dữ liệu đánh giá

Nên tổ chức test set thành các nhóm đại diện:

1. **Arithmetic đơn giản**: cộng/trừ/nhân/chia một bước.
2. **Rate/percent/threshold**: tương tự discount ticket, coupon, tax, overtime.
3. **Multi-step rõ ràng**: nhiều phép nối tiếp.
4. **Ngôn ngữ mơ hồ**: nhiều câu, từ chỉ dấu ít rõ.
5. **Student answer xấu**:
   1. thiếu bước
   2. nhảy bước
   3. ghi nhiều số nhiễu
   4. sai phép toán nhưng đúng số
   5. đúng phép toán nhưng sai số

Mỗi bài cần có:

1. ground truth tối thiểu cho target/ref chính
2. answer chuẩn
3. nhãn kỳ vọng lỗi học sinh (ở mức tổng quát)

## 4.3 Chỉ số đánh giá đề xuất

### A. Problem formalization

1. **Schema Pass Rate (SPR-problem)**
   1. Tỷ lệ `FormalizedProblem` validate thành công.
2. **Graph Valid Rate (GVR-problem)**
   1. Tỷ lệ pass `validate_problem_graph`.
3. **Target Resolution Accuracy (TRA)**
   1. Đúng target variable và target linkage.
4. **Relation Family Accuracy (RFA)**
   1. Đúng relation_type ở mức family.
5. **Fallback Success Rate (FSR-problem)**
   1. Khi LLM fail, fallback vẫn cho output usable.

### B. Student-work formalization

1. **Schema Pass Rate (SPR-student)**
2. **Graph Presence & Validity (GPV-student)**
   1. Trường hợp parseable thì student_graph phải tồn tại và hợp lệ tối thiểu.
3. **Final Answer Extraction Accuracy (FAE)**
4. **Mode Classification Accuracy (MCA)**
5. **Step Groundedness Precision (SGP)**
   1. Tỷ lệ step/value có grounding thật trong text hoặc refs hợp lệ.
6. **Fallback Success Rate (FSR-student)**

### C. Chỉ số tích hợp downstream

1. **Diagnosis Stability Delta (DSD)**
   1. So sánh độ ổn định diagnosis khi bật/tắt nhánh LLM formalizer.
2. **Hint Utility Proxy (HUP)**
   1. Tỷ lệ hint không vi phạm constraint cơ bản (không lộ đáp án, đúng target lỗi).

## 4.4 Quy trình đánh giá đề xuất

### Bước 1: Baseline heuristic-only

1. Chạy formalizer với `llm_client=None` trên toàn bộ test set.
2. Thu log artifacts và tính chỉ số baseline.

### Bước 2: Hybrid (heuristic + LLM sketch)

1. Chạy formalizer với LLM bật.
2. Thu chỉ số tương tự baseline.
3. So sánh theo từng nhóm bài toán.

### Bước 3: Stress test retry/fallback

Chủ động mô phỏng lỗi:

1. LLM timeout.
2. LLM trả JSON sai schema.
3. LLM trả graph thiếu target.
4. LLM trả step không grounded.

Mục tiêu: xác nhận retry loop + fallback hoạt động đúng và không làm vỡ pipeline.

### Bước 4: Error taxonomy review

Phân loại lỗi theo code trong `GraphValidationIssue`:

1. missing graph
2. schema validation
3. target mismatch
4. unknown refs
5. mode inconsistency

Sau đó lập bảng tần suất để tìm ưu tiên cải thiện.

## 4.5 Cơ chế chấm điểm tổng hợp (khuyến nghị)

Một công thức tổng hợp có thể dùng để theo dõi qua sprint:

`Overall = 0.25*Schema + 0.25*Graph + 0.2*Semantic + 0.15*Robustness + 0.15*Downstream`

Trong đó:

1. `Schema` = trung bình SPR-problem và SPR-student.
2. `Graph` = trung bình GVR-problem và GPV-student.
3. `Semantic` = trung bình TRA, RFA, FAE, MCA, SGP.
4. `Robustness` = trung bình FSR-problem và FSR-student.
5. `Downstream` = trung bình DSD và HUP (chuẩn hóa về cùng thang).

Mục đích của điểm tổng hợp không phải thay từng metric, mà để theo dõi xu hướng release-to-release.

## 4.6 Tiêu chí chấp nhận đề xuất (giai đoạn đầu)

Ví dụ ngưỡng kiểm soát chất lượng cho milestone gần nhất:

1. SPR-problem >= 99%
2. SPR-student >= 99%
3. GVR-problem >= 95%
4. GPV-student >= 92%
5. FAE >= 90%
6. MCA >= 88%
7. FSR-problem >= 99%
8. FSR-student >= 99%

Các ngưỡng này nên điều chỉnh theo domain dữ liệu thật của đội.

## 4.7 Mối đe dọa tới tính hợp lệ đánh giá

1. **Dataset bias**: test set không đại diện cho dữ liệu production.
2. **Label noise**: ground truth cho relation/target chưa nhất quán.
3. **Metric leakage**: một số metric có thể bị “làm đẹp” bằng repair mạnh tay.
4. **Model drift**: LLM đổi behavior theo thời gian làm metric dao động.

Giảm thiểu:

1. Chia tập theo domain và độ khó.
2. Có sample review thủ công định kỳ.
3. Lưu artifacts để audit.
4. Pin model/version cho benchmark định kỳ.

---

## 5. Kết luận và đề xuất thực thi

Formalizer hiện đã có nền kiến trúc tốt để vận hành production:

1. Có deterministic path làm anchor/fallback.
2. Có LLM path để tăng semantic coverage.
3. Có local compiler + validator để kiểm soát đầu ra.

Điểm mạnh lớn nhất là không phụ thuộc mù quáng vào output trực tiếp từ LLM.

Các ưu tiên triển khai tiếp theo nên là:

1. Chuẩn hóa bộ benchmark theo taxonomy lỗi formalizer.
2. Theo dõi metric tách riêng heuristic-only và hybrid.
3. Bổ sung regression suite cho các case rate/percent/threshold.
4. Tăng audit groundedness cho student trace steps.

Nếu thực hiện đúng quy trình đánh giá ở Mục 4, nhóm có thể kiểm soát chất lượng formalizer theo chu kỳ release một cách định lượng, thay vì chỉ dựa vào cảm nhận từ một vài ví dụ chạy tay.


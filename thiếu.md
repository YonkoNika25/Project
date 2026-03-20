

**Pipeline runtime của bạn hiện đã khá đầy đủ cho Phase 2, nhưng phần còn thiếu lớn nhất bây giờ nằm ở “độ chắc của grounding”, “độ đo được của evaluation”, và “khả năng bảo vệ claim nghiên cứu”, chứ không còn nằm ở việc thiếu một khối xử lý chính nữa.** Điều này rất hợp với bối cảnh hiện tại của lĩnh vực: benchmark như MathTutorBench nhấn mạnh rằng năng lực tutor phải được đánh giá bằng tiêu chí sư phạm riêng, chứ không thể suy ra từ solve accuracy; còn Qwen2.5-Math là một backbone hợp lý cho toán vì được thiết kế quanh CoT và Tool-Integrated Reasoning. ([arXiv][1])

---

# 1. Những gì đã **đủ khung** và không còn là thiếu sót lớn

Về luồng chính, bạn đã có đúng bộ xương mà một **solver-grounded tutor** cần có:

`problem + student_answer`
→ solver
→ parser
→ answer checker
→ symbolic state
→ symbolic verifier
→ diagnosis
→ hint generation
→ hint verification
→ response

Tức là về mặt kiến trúc, bạn **không còn thiếu một module runtime cốt lõi** nữa. Phần này đã rất khớp với mục tiêu nghiên cứu ban đầu của bạn: không làm một solver thuần, mà làm một tutor có grounding từ `reference_solution`, `answer_check_result`, `symbolic_state`, và `verification_result`.

Nói cách khác:

* **luồng chạy chính**: đã đúng,
* **schema tư duy**: đã đúng,
* **trọng tâm Phase 2**: đã đúng,
* **điểm yếu còn lại**: nằm ở độ sâu và chất lượng của từng khối.

---

# 2. Những gì còn thiếu hoặc cần nâng cấp trong **luồng runtime chính**

## 2.1. Reference Solver: chưa thiếu khối, nhưng còn thiếu **độ tin cậy vận hành**

Bạn đã có:

* gọi solver,
* parse output,
* tạo `ReferenceSolution`.

Nhưng tầng này vẫn còn 4 việc quan trọng.

### Thiếu / cần nâng cấp

**Thứ nhất, audit riêng cho reference solver.**
Bạn cần theo dõi riêng:

* `parse_success_rate`
* `reference_correctness`
* `provider/model failure rate`
* retry success rate

Lý do: nếu reference sai, toàn bộ grounding phía sau có thể grounded vào sai lầm.

**Thứ hai, structured trace còn mỏng.**
Hiện bạn chủ yếu lấy `final_answer`. Về sau nên lấy thêm:

* lời giải text sạch,
* answer span,
* reasoning snippet ngắn,
* confidence hoặc proxy confidence.

**Thứ ba, policy khi solver fail chưa đủ giàu.**
Bạn nên tách rõ:

* LLM/provider fail
* output format fail
* parse fail
* mathematically wrong but parseable

**Thứ tư, best-of-N / retry policy còn là hướng mở.**
Chưa cần làm mạnh ngay, nhưng đây là một trong các đòn bẩy rõ để giảm reference noise.

### Ý nghĩa

Đây là tầng không “hào nhoáng”, nhưng cực quan trọng, vì dự án của bạn là **solver-grounded**. Nếu tầng solver không được audit riêng, claim nghiên cứu sẽ yếu.

---

## 2.2. Answer Checker: đúng hướng nhưng vẫn còn “quá gọn”

Bạn đã tự chỉ ra rất đúng rằng `check_answer()` hiện còn mỏng. Mình đồng ý hoàn toàn.

### Thiếu / cần nâng cấp

**Thiếu rich status.**
Hiện checker mới chủ yếu trả đúng/sai và giá trị chuẩn hóa. Nên mở rộng thêm các trạng thái như:

* parse được một số duy nhất
* parse được nhiều số
* ambiguous extraction
* numerically correct but format-weird
* malformed but interpretable
* unparseable
* maybe-correct with low confidence

**Thiếu evidence detail cho symbolic layer.**
Checker không chỉ để kết luận “đúng/sai”, mà còn phải trả những tín hiệu giúp symbolic layer và diagnosis dùng tiếp, ví dụ:

* extracted numbers
* chosen number
* discarded spans
* formatting flags
* comparison mode

**Thiếu taxonomy con cho answer formatting.**
Điều này rất hữu ích nếu sau này bạn muốn tách `CorrectAnswer` nhưng localization là `answer_formatting`.

### Ý nghĩa

Checker hiện chưa sai, nhưng nó đang làm “ít hơn mức cần thiết”. Trong Phase 2, nó phải trở thành một **evidence producer** (bộ sinh tín hiệu bằng chứng), không chỉ là một comparator.

---

## 2.3. Symbolic Layer: đây vẫn là **trung tâm nâng cấp lớn nhất của Phase 2**

Đây là chỗ bạn cũng đã tự nhận ra đúng nhất.

## build_symbolic_state() và verify_symbolic_consistency()

### Thiếu / cần nâng cấp

**Thiếu quality gate khi symbolic evidence yếu.**
Hiện bạn đã có state builder và verifier, nhưng chưa có cơ chế “hạ độ mạnh” một cách bài bản khi:

* state thiếu trường quan trọng,
* quan hệ suy ra không chắc,
* quantities parse mâu thuẫn,
* target không rõ.

**Thiếu confidence propagation.**
Bạn cần truyền độ tin cậy đi tiếp từ:

* builder confidence
* verifier strength
* conflict severity

để diagnosis không overclaim.

**Thiếu provenance rõ hơn.**
Mỗi relation / quantity / target nên biết nó đến từ đâu:

* extracted from problem text
* inferred from solver
* inferred by heuristic
* inferred by LLM

**Thiếu ontology đủ rõ cho relations.**
Hiện representation quantity-relation là hợp lý, nhưng nên chốt rõ hơn:

* additive composition
* subtractive comparison
* multiplicative scaling
* partition / grouping
* rate / unit relation

**Thiếu failure modes có cấu trúc.**
Bạn nên có kiểu:

* incomplete_symbolic_state
* low_confidence_relation
* conflicting_relation_hypotheses
* unsupported_problem_structure

### Ý nghĩa

Đây chính là vùng sẽ tạo ra **novelty mạnh hơn** cho dự án. Nếu Phase 1 là “solver + checker + diagnosis + hint”, thì Phase 2 chỉ thực sự khác biệt khi vùng này đủ sâu.

---

## 2.4. Diagnosis Engine: vẫn là nơi cần nâng cấp nhiều nhất về “grounded diagnosis”

Bạn cũng tự nhìn ra điều này rất chính xác.

### Thiếu / cần nâng cấp

**Thiếu calibration nối thật vào eval.**
Bạn đã nói đến calibration/reporting, nhưng hiện nó mới là ý, chưa thành luồng đo thật.

**Thiếu localization sâu hơn.**
Hiện localization mới ở mức coarse, ví dụ:

* target selection
* combining quantities
* final computation

Về sau có thể tiến đến:

* step-like localization nhẹ
* operation-level localization
* relation-level localization

**Thiếu guardrail khi evidence yếu hoặc mâu thuẫn.**
Diagnosis không nên luôn “khẳng định mạnh”. Nó cần logic kiểu:

* nếu evidence mạnh → diagnosis confident
* nếu evidence yếu → diagnosis softer
* nếu evidence conflict → UnknownError hoặc low-confidence structured output

**Thiếu fusion giữa symbolic evidence và LLM fallback.**
Hiện bạn đã nói “chỉ dùng LLM khi cần”, nhưng nên formalize rõ hơn:

* rule-first
* evidence-first
* LLM-as-explainer
* LLM-as-tie-breaker
* LLM fallback only when verifier weak

**Thiếu chẩn đoán đa tầng.**
Về sau có thể tách:

* primary label
* localization
* short rationale
* confidence
* evidence summary

### Ý nghĩa

Đây là nơi câu chuyện “grounded diagnosis” của paper sống hay chết. Nếu chỗ này chỉ là prompt hay hơn thì paper sẽ yếu; nếu chỗ này có evidence fusion thật, paper sẽ mạnh hơn nhiều.

---

## 2.5. Hint Generation: chạy được rồi, nhưng còn thiếu chiều sâu sư phạm

Bạn đánh giá rất đúng: đây không còn là vùng “sửa lỗi nặng”, mà là vùng “tinh chỉnh chất lượng”.

### Thiếu / cần nâng cấp

**Thiếu điều khiển hint level bằng evidence strength.**
Hiện hint level còn đơn giản. Nên cho nó phụ thuộc vào:

* diagnosis label
* localization
* confidence
* verifier strength

Ví dụ:

* evidence mạnh → `Relational` hoặc `Next-step`
* evidence yếu → `Conceptual`
* conflict → safe fallback

**Thiếu tận dụng localization đủ sâu.**
Nếu biết lỗi nằm ở `combining_quantities`, hint nên rất khác với lỗi `target_selection`.

**Thiếu phân biệt hint policy theo trạng thái uncertainty.**
Khi hệ không chắc, hint nên an toàn hơn thay vì quá cụ thể.

**Thiếu đánh giá nội tại của hint trước khi verifier.**
Có thể thêm internal checks như:

* too generic
* too specific
* likely answer leakage
* inconsistent with diagnosis

### Ý nghĩa

Hint hiện ổn cho baseline, nhưng chưa đủ mạnh để tạo lợi thế sư phạm rõ ràng nếu mang đi so với baseline khác.

---

## 2.6. Hint Verifier: chạy được nhưng vẫn còn “thô”

Bạn cũng nhìn ra điểm này.

### Thiếu / cần nâng cấp

**Thiếu tách biệt rõ hai việc khác nhau:**

* `verify_hint_no_spoiler()`
* `verify_hint_alignment()`

Hai việc này không nên dùng chung một logic rule-based đơn giản.

**No-spoiler check còn quá keyword-based.**
Nên tiến tới logic phong phú hơn:

* final numeric answer leakage
* full equation chain leakage
* near-solution leakage
* step-complete leakage

**Alignment check chưa dùng đủ context.**
Hiện nó nên dần dùng:

* diagnosis label
* localization
* evidence strength
* hint level

**Thiếu lý do fail có cấu trúc.**
Thay vì chỉ fail/pass, nên có:

* `spoiler_final_answer`
* `spoiler_full_chain`
* `misaligned_with_diagnosis`
* `too_specific_for_low_confidence_case`
* `too_generic_for_high_confidence_case`

### Ý nghĩa

Đây là lý do bạn thấy có những hint “nghe hợp lý” nhưng verifier vẫn fail hoặc fail chưa thuyết phục. Tức là khối này đang hoạt động, nhưng còn thô so với mục tiêu paper.

---

# 3. Những gì còn thiếu ở **nhánh research support** — đây mới là khoảng trống lớn

Đây là phần bạn đã nhắc đến một phần, nhưng còn thiếu vài mảnh quan trọng.

## 3.1. Evaluation path: có rồi, nhưng chưa thành **paper-grade evaluation**

Bạn đã có:

* `run_eval.py`
* `diagnosis/evaluation.py`
* `eval/audit_io.py`

Đây là rất tốt.

Nhưng tầng này vẫn còn thiếu 6 thứ.

### Thiếu / cần nâng cấp

**Thiếu tích hợp thật giữa `run_eval.py` và `evaluation.py` / `audit_io.py`.**
Hiện chúng tồn tại, nhưng chưa nối thành một pipeline đánh giá hoàn chỉnh.

**Thiếu metric Phase 2 thật sự chạy được.**
Bạn đã nêu đúng:

* calibration
* ablation
* audit logging
* recovery after hint

Mình bổ sung thêm:

* confusion matrix cho diagnosis
* label-wise performance
* failure breakdown by evidence strength
* spoiler violation categories

**Thiếu benchmark subset có gold labels đủ rõ.**
Cần thật sự có:

* `gold_diagnosis`
* `gold_hint_reference`
* audited subset
* split rõ: `train_build`, `dev_audit`, `test_paper`

GSM8K là testbed tốt cho baseline vì nó là benchmark chuẩn cho multi-step arithmetic word problems, nhưng nó không tự cung cấp sẵn task `student_answer -> diagnosis + hint`; phần đó bạn phải xây thêm. ([Gitee][2])

**Thiếu judge protocol rõ.**
Bạn cần tách:

* metric nào human-rated
* metric nào LLM-judged
* rubric nào dùng cho hint correctness
* guideline nào dùng cho diagnosis labeling

MathTutorBench đặc biệt đáng chú ý ở chỗ nó không chỉ đo final correctness mà còn xây framework đánh giá năng lực tutor mở trên nhiều kỹ năng sư phạm. ([arXiv][1])

**Thiếu recovery evaluation thật sự.**
Bạn đã nhắc recovery, nhưng chưa có student simulator hoặc quy trình một bước thực sự ổn định.

**Thiếu audit artifacts chuẩn hóa.**
Bạn nên lưu:

* raw solver output
* parse status
* chosen reference
* symbolic confidence
* verifier flags
* diagnosis output
* hint output
* verifier result

### Ý nghĩa

Đây là phần quyết định project của bạn là “pipeline hay” hay là “paper có thể bảo vệ được”.

---

## 3.2. Baselines và ablations: hiện vẫn chưa được nhấn mạnh đủ

Bạn có nhắc `ablation`, nhưng nên đưa nó thành một hạng mục riêng, không chỉ là một metric “sau này thêm”.

### Thiếu / cần nâng cấp

Cần cố định các baseline tối thiểu:

* **Prompt-only tutor**
* **Reference-grounded tutor**
* **Reference + answer-check tutor**
* **Full grounded tutor**

và các ablation tối thiểu:

* bỏ `answer_check`
* bỏ `symbolic_state`
* bỏ `verification_evidence`
* bỏ `diagnosis-aware hint policy`

### Ý nghĩa

Nếu không có các baseline này, bạn khó chứng minh “grounding giúp ích” chứ không chỉ “thêm module thì hệ phức tạp hơn”.

---

## 3.3. Benchmark/data layer: vẫn còn thiếu phần “đủ chuẩn để viết paper”

### Thiếu / cần nâng cấp

**Thiếu synthetic error generator phong phú hơn.**
Không thể chỉ có `answer - 1`. Cần ít nhất 4 kiểu lỗi như document v2 đã chốt:

* `correct_answer`
* `arithmetic_error`
* `quantity_relation_error`
* `target_misunderstanding`

**Thiếu audited subset đủ sạch.**
Cần tập nhỏ được người xem lại để sửa những synthetic cases quá phi lý.

**Thiếu gold hint references.**
Nếu không có vài gợi ý tham chiếu chuẩn, rất khó chấm `hint_correctness` nhất quán.

**Thiếu protocol tạo dữ liệu rõ.**
Cần mô tả:

* sinh student answer thế nào
* lọc thế nào
* sửa tay ở đâu
* dùng tập nào cho design, tập nào cho reporting

### Ý nghĩa

Đây là phần giúp paper của bạn không bị xem là “prompt engineering trên dữ liệu tự bịa”.

---

## 3.4. Guideline và rubric: hiện mới có khung, chưa đủ operational

### Thiếu / cần nâng cấp

**Diagnosis guideline** cần operational hơn:

* ví dụ biên
* luật ưu tiên nhãn
* khi nào gán `UnknownError`
* khi nào tách `ArithmeticError` vs `QuantityRelationError`

**Hint rubric** cần operational hơn:

* đúng lỗi đến mức nào là đủ
* mức độ spoil nào là fail
* mơ hồ bao nhiêu là fail
* khác biệt giữa `Conceptual`, `Relational`, `Next-step`

### Ý nghĩa

Nếu thiếu guideline/rubric, metric sẽ không đáng tin dù bạn có pipeline rất đẹp.

---

# 4. Những gì còn thiếu ở tầng **schema / contracts**

Bạn nói rất đúng là `SymbolicState` và `VerificationResult` chưa được tận dụng đủ trong eval/audit. Mình đồng ý, và bổ sung thêm:

## Thiếu / cần nâng cấp

**Thiếu metadata audit xuyên suốt.**
Mỗi schema quan trọng nên có:

* `status`
* `confidence`
* `source`
* `provenance`
* `error_reason` nếu fail

**Thiếu schema cho evaluation artifacts.**
Không chỉ runtime outputs, bạn còn cần schema cho:

* `AuditRecord`
* `EvalExample`
* `AblationRecord`
* `JudgeScore`

**Thiếu consistency trong contract giữa runtime và eval.**
Hiện runtime và eval dễ bị tách đôi; trong khi paper-ready system nên dùng cùng một ngôn ngữ schema.

### Ý nghĩa

Schema đúng không chỉ để code sạch; nó còn giúp bạn làm error analysis, audit, và viết phần method/evaluation dễ hơn nhiều.

---

# 5. Những gì **chưa nên làm vội**, nhưng nên ghi rõ là “chưa làm”

Đây không phải thiếu sót theo nghĩa “quên”, nhưng cần được nói rõ để tránh trôi phạm vi.

## 5.1. Fine-tune / SFT / DPO / RL-light

Hiện chưa phải lúc. Trình tự hợp lý vẫn là:

* baseline ổn
* benchmark ổn
* verifier ổn
* eval ổn
* rồi mới đến SFT
* sau đó mới DPO / preference learning
* cuối cùng mới nghĩ tới RL-light

Điều này cũng phù hợp với Qwen2.5-Math technical report: hiệu năng mạnh đến từ cả một pipeline gồm pretraining, post-training, reward modeling, SFT iteration, rồi mới RL; không phải cứ thêm RL là xong. ([arXiv][3])

Nếu cần một điểm mốc học thuật cho giai đoạn sau, DPO là hướng hợp lý hơn RLHF nặng ở giai đoạn đầu learning extension, vì nó dùng dữ liệu preference pairs trực tiếp thay vì dựng reward model riêng phức tạp ngay từ đầu. ([arXiv][3])

## 5.2. Formal proof assistants / theorem proving nặng

Chưa cần ở giai đoạn này.

## 5.3. Multi-turn tutoring / partial solution tutoring

Đây là mở rộng hợp lý, nhưng nên để sau khi một-turn baseline của bạn đã được đo tử tế.

---

# 6. Bản tổng hợp cuối cùng: đầy đủ những gì đang còn thiếu, cần nâng cấp và tinh chỉnh

## A. Ở tầng solver

* audit riêng cho reference solver
* parse fail taxonomy rõ hơn
* confidence / trace tốt hơn
* retry / best-of-N nhỏ
* logging provider/model failures

## B. Ở tầng answer checker

* rich status đa dạng hơn
* extraction evidence giàu hơn
* phân biệt ambiguity / format / malformed cases
* output hữu ích hơn cho symbolic layer

## C. Ở tầng symbolic + verifier

* quality gate khi evidence yếu
* confidence propagation
* provenance rõ hơn
* relation ontology rõ hơn
* failure modes có cấu trúc
* verifier flags hữu ích hơn

## D. Ở tầng diagnosis

* calibration nối vào eval thật
* localization sâu hơn
* guardrail khi evidence conflict
* fusion rule giữa symbolic evidence và LLM fallback
* output diagnosis đa tầng hơn

## E. Ở tầng hint generation

* hint level phụ thuộc evidence strength
* tận dụng localization tốt hơn
* chính sách uncertainty-aware
* kiểm tra nội tại hint trước verifier

## F. Ở tầng hint verifier

* tách rõ no-spoiler và alignment
* giảm lệ thuộc keyword rules
* fail reasons có cấu trúc
* alignment dùng diagnosis + localization + confidence

## G. Ở tầng benchmark / evaluation

* benchmark subset có `gold_diagnosis` và `gold_hint_reference`
* audited subset
* judge protocol rõ
* confusion matrix / macro-F1 / calibration
* ablation matrix rõ
* recovery evaluation thật
* audit JSONL và structured logging

## H. Ở tầng research story

* baseline set rõ
* ablation set rõ
* guideline diagnosis rõ
* rubric hint rõ
* tách metric human-rated và LLM-judged
* bảo vệ claim “grounding helps” bằng số liệu chứ không chỉ bằng kiến trúc

## I. Ở tầng schema / contracts

* metadata audit xuyên suốt
* schema cho artifacts đánh giá
* thống nhất contract giữa runtime và eval

---

# 7. Ưu tiên thực hiện theo đúng thứ tự

Nếu phải xếp thứ tự từ quan trọng nhất xuống, mình sẽ xếp như sau:

**Ưu tiên 1**
benchmark subset + gold diagnosis + audit logging

**Ưu tiên 2**
nâng symbolic/verifier quality gate + diagnosis guardrail

**Ưu tiên 3**
làm evaluation thật sự: calibration, confusion matrix, ablation, recovery

**Ưu tiên 4**
nâng hint policy và hint verifier theo localization + evidence strength

**Ưu tiên 5**
sau tất cả những thứ trên mới tính đến SFT / DPO / RL-light




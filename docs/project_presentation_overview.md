

## 1. Bài toán mà hệ thống đang giải quyết

Dự án này hướng tới một bài toán hỗ trợ học tập cho bài toán lời văn.

Ở mức khái quát, hệ thống nhận:

1. `problem_text` là đề bài
2. `student_answer` là bài làm của học sinh

Từ đó, hệ thống cố gắng làm ba việc chính:

1. hiểu đề bài đang hỏi gì và cấu trúc toán học của đề là gì
2. hiểu học sinh đã làm gì, đang tính đại lượng nào, và trả ra đáp án nào
3. so sánh hai phía để đưa ra chẩn đoán lỗi và tạo gợi ý phù hợp

Mục tiêu của hệ thống không chỉ là kiểm tra đáp án cuối đúng hay sai.  
Hệ thống còn cố gắng:

- dựng một lời giải chuẩn cho đề bài
- đọc bài làm học sinh dưới dạng có cấu trúc
- phát hiện học sinh lệch ở đâu
- tạo hint (gợi ý) thay vì chỉ báo đúng hoặc sai

Nói ngắn gọn, đây là một tutoring pipeline (chuỗi xử lý hỗ trợ học tập), không phải chỉ là một bộ chấm đáp án cuối.

### Ví dụ minh họa sẽ dùng xuyên suốt trong tài liệu này

Để dễ hình dung, phần dưới sẽ minh họa bằng đúng ví dụ đang được dùng trong các file debug của problem side và student side:

`problem_text`:

> A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. Over three hundred years, it has consumed 847 people. Ships have been built larger over time, so each new ship has twice as many people as the last ship. How many people were on the ship the monster ate in the first hundred years?

`student_answer`:

> Let the first ship have x people. Then the next two ships had 2x and 4x people. x + 2x + 4x = 847. 7x = 847. x = 847/7. x = 117. Answer is 117.

Ý nghĩa của ví dụ này:

- tổng số người trong 3 lần là `847`
- số người trên các tàu theo tỉ lệ `1 : 2 : 4`
- đáp án đúng của bài là `121`
- học sinh lại kết luận `117`

Vì vậy, đây là một ví dụ tốt để nhìn rõ từng khối của hệ thống đang nhận gì và tạo ra gì.

## 2. Cách hệ thống vận hành

Điểm vào của toàn bộ hệ thống nằm ở:

- `src/pipeline/runner.py`
- hàm `run_tutoring_pipeline(...)`

Pipeline hiện tại chạy theo thứ tự:

1. `formalize_problem(...)`
2. `build_canonical_reference(problem)`
3. `formalize_student_work(...)`
4. `build_diagnosis_evidence(problem, reference, student_work)`
5. `diagnose(evidence, llm_client=...)`
6. `build_hint_plan(problem, reference, diagnosis)`
7. `build_hint_result(problem, reference, diagnosis, hint_plan, ...)`

Toàn bộ quá trình có thể hiểu theo các khối lớn sau.

### 2.1 Formalize problem

Khối đầu tiên nhận đề bài và cố gắng biến nó thành một biểu diễn có cấu trúc.

Ở bước này, hệ thống:

- tìm các đại lượng số xuất hiện trong đề
- tìm câu hỏi đích của bài toán
- thu thập các dấu hiệu ngôn ngữ gợi ý kiểu quan hệ toán học
- dùng mô hình kết hợp với code để dựng ra một `FormalizedProblem`

`FormalizedProblem` là cách hệ thống biểu diễn đề bài dưới dạng máy có thể xử lý tiếp, thay vì chỉ giữ nguyên văn bản thô.

Với ví dụ `847`, sau bước này hệ thống đi từ đề bài văn bản sang một biểu diễn có cấu trúc.  
Trong các lần debug gần đây, đầu ra của bước này thể hiện những ý chính sau:

- hệ thống nhận ra quantity (đại lượng số) chính là `847`
- target (đại lượng đích) là số người trên con tàu ở trăm năm đầu
- hệ thống không giữ nguyên cách hiểu heuristic ban đầu, mà sửa lại quan hệ bài toán theo hướng chia tổng `847` cho tổng hệ số `7`
- biểu diễn cuối cùng có thêm một quantity trung gian như `total_multiplier = 7`

Nói đơn giản hơn, sau bước này hệ thống đã đi từ:

- “đề bài có số 847 và có chữ twice”

sang:

- “đây là bài có cấu trúc tổng `847`, ba nhóm theo tỉ lệ `1, 2, 4`, nên muốn tìm nhóm đầu thì phải chia cho `7`”

### 2.2 Build canonical reference

Sau khi có `FormalizedProblem`, hệ thống dựng một `CanonicalReference`.

Đây có thể hiểu là lời giải chuẩn nội bộ của hệ thống, gồm:

- cấu trúc giải
- các bước tính
- đáp án cuối đúng

Khối này rất quan trọng vì nó tạo ra chuẩn tham chiếu để so với bài làm học sinh.  
Nếu bước này không dựng được reference (lời giải chuẩn nội bộ), các bước sau sẽ yếu đi rõ rệt.

Với ví dụ `847`, đầu ra quan trọng nhất của bước này là:

- `final_answer = 121.0`

Tức là hệ thống đã dựng được lời giải chuẩn nội bộ và thực thi được nó.  
Ở mức khái quát, lời giải chuẩn mà hệ thống dùng ở đây tương ứng với ý tưởng:

1. tổng hệ số là `1 + 2 + 4 = 7`
2. số người trên tàu đầu là `847 / 7`
3. kết quả là `121`

Điểm cần hiểu là:

- sau bước này, hệ thống đã có một “chuẩn tham chiếu” rõ ràng để so với bài làm học sinh
- chuẩn đó không còn là văn bản mơ hồ, mà là một reference (lời giải chuẩn nội bộ) có đáp án cuối cụ thể

### 2.3 Formalize student work

Khối tiếp theo nhận bài làm học sinh và biến nó thành một biểu diễn có cấu trúc.

Ở bước này, hệ thống cố gắng:

- lấy ra đáp án cuối mà học sinh nêu
- tách các bước giải trong bài làm
- hiểu học sinh đang nhắm tới đại lượng nào
- dựng `StudentWorkState`

`StudentWorkState` là phiên bản có cấu trúc của bài làm học sinh, để hệ thống không phải xử lý bài làm chỉ như một đoạn văn bản thuần túy.

Với ví dụ `847`, bước này đọc bài làm học sinh:

> x + 2x + 4x = 847  
> 7x = 847  
> x = 847/7  
> x = 117  
> Answer is 117

và chuyển nó thành dạng có cấu trúc.  
Những đầu ra quan trọng của bước này là:

- `normalized_final_answer = 117.0`
- `mode = full_trace`
- hệ thống tách được các bước giải chính của học sinh
- hệ thống hiểu rằng học sinh đang cố trả lời đúng target (đại lượng đích của bài), chứ không phải đang nhắm sang một số khác trong đề
- `student_graph` được dựng thành công

Nói ngắn gọn:

- sau bước này, hệ thống đã có một phiên bản “máy đọc được” của bài làm học sinh
- trong đó điều quan trọng nhất là học sinh đi đến kết quả `117`, khác với reference `121`

### 2.4 Build diagnosis evidence

Sau khi đã có:

- đề bài đã formalize
- lời giải chuẩn
- bài làm học sinh đã formalize

hệ thống chuyển sang bước so sánh.

Khối evidence (bằng chứng chẩn đoán) có nhiệm vụ:

- đối chiếu các bước giải chuẩn với các bước của học sinh
- tìm xem học sinh đang khớp với phần nào
- xác định điểm lệch đầu tiên nếu có
- tạo ra các evidence items (mục bằng chứng) để phục vụ diagnosis

Nói đơn giản, đây là bước “đem hai phía ra so” nhưng ở mức reasoning (lập luận), không chỉ ở mức đáp án cuối.

Với ví dụ `847`, bước này sẽ đem ra so:

- reference có đáp án cuối `121`
- student work có đáp án cuối `117`
- cùng với các bước giải ở mỗi phía

Ở mức khái quát, khối evidence sẽ cố trả lời:

- học sinh đang đi đúng hướng tổng quát hay không
- học sinh bắt đầu lệch từ bước nào
- sự lệch nằm ở việc chọn mục tiêu, ở quan hệ giữa các đại lượng, hay ở phép tính

Trong ví dụ này, trực giác tổng quát của pipeline là:

- học sinh hiểu rằng phải lập phương trình theo dạng `x + 2x + 4x = 847`
- nhưng kết quả cuối học sinh nêu là `117`, nên evidence chắc chắn sẽ ghi nhận có final answer mismatch (không khớp đáp án cuối)

Tài liệu này không đi sâu vào nội dung evidence item cụ thể, nhưng điều quan trọng là:

- sau bước này, hệ thống không còn chỉ biết “117 sai”
- mà có một gói bằng chứng để bước diagnosis dựa vào

### 2.5 Diagnose

Sau khi có evidence, hệ thống đưa ra diagnosis (chẩn đoán).

Diagnosis hiện tại chủ yếu trả lời các câu hỏi như:

- học sinh đúng hay sai
- nếu sai thì sai kiểu gì
- sai ở bước tính toán, sai ở quan hệ giữa các đại lượng, hay nhắm sai mục tiêu bài toán

Đầu ra của bước này là một `DiagnosisResult`.

Khối diagnosis là nền để bước sau quyết định nên gợi ý theo hướng nào.

Với ví dụ `847`, đầu vào của diagnosis lúc này là:

- đề bài đã formalize
- reference có đáp án đúng `121`
- student work có đáp án `117`
- evidence mô tả sự lệch giữa hai phía

Ở bước này, hệ thống sẽ chuyển từ:

- dữ liệu so sánh

sang:

- một kết luận ngắn gọn về kiểu lỗi mà học sinh đang mắc

Nói cách khác:

- evidence cho biết “học sinh khác reference ở đâu”
- diagnosis trả lời “vậy nên gọi lỗi này là gì”

### 2.6 Build hint plan

Sau khi có diagnosis, hệ thống chưa tạo hint ngay.

Nó tạo trước một `HintPlan`, tức là kế hoạch sư phạm cho hint.

Ở bước này, hệ thống quyết định:

- nên gợi ý ở mức độ nào
- nên hướng học sinh nhìn lại phần nào
- nên tránh tiết lộ phần nào của lời giải chuẩn

Nói cách khác, đây là bước chuyển từ:

- “hệ thống nghĩ học sinh sai ở đâu”

sang:

- “hệ thống nên can thiệp sư phạm theo cách nào”

Với ví dụ `847`, sau khi có diagnosis, hệ thống chưa viết hint ngay.  
Nó quyết định trước những câu hỏi như:

- nên nhắc học sinh kiểm tra lại phép tính hay kiểm tra lại quan hệ `1, 2, 4`
- nên gợi ý ở mức khái niệm hay mức bước tiếp theo
- có được lộ trực tiếp `121` hay không

Đó là vai trò của `HintPlan`:  
biến một diagnosis kỹ thuật thành một kế hoạch can thiệp sư phạm.

### 2.7 Build hint result

Khối cuối cùng tạo `HintResult`, tức là gợi ý thực tế trả cho học sinh.

Hint được tạo dựa trên:

- đề bài
- lời giải chuẩn
- diagnosis
- hint plan

Khối này còn có bước kiểm tra để hạn chế các trường hợp như:

- lộ đáp án quá trực tiếp
- gợi ý không đi đúng hướng đã chọn

Kết quả cuối cùng là một hint đủ ngắn gọn để hỗ trợ học sinh tiếp tục làm bài.

Với ví dụ `847`, đây là bước cuối mà hệ thống lấy:

- chẩn đoán lỗi
- kế hoạch gợi ý

để sinh ra một hint thực tế cho học sinh.

Ở mức mong muốn, hint trong ví dụ này sẽ không nên:

- lộ thẳng đáp án `121`

mà nên hướng học sinh nhìn lại phần then chốt, ví dụ:

- kiểm tra lại bước chia ở cuối
- hoặc kiểm tra lại xem từ `7x = 847` thì `x` phải bằng bao nhiêu

Tức là bước này không chỉ tạo ra câu chữ, mà còn phải giữ được ràng buộc sư phạm:  
gợi ý đủ hữu ích nhưng không giải bài thay cho học sinh.

## 3. Đặc điểm chung của kiến trúc hiện tại

Về mặt triển khai, hệ thống hiện là một kiến trúc hybrid (lai), nghĩa là kết hợp giữa:

- code deterministic (phần quyết định cứng theo code)
- LLM (mô hình ngôn ngữ lớn)

LLM được dùng ở các chỗ cần hiểu ngữ nghĩa khó bằng rule thuần, ví dụ:

- formalize đề bài
- formalize bài làm học sinh
- hỗ trợ diagnosis
- hỗ trợ tạo hint

Nhưng LLM không hoạt động một mình. Quanh nó luôn có:

- schema (lược đồ dữ liệu) rõ ràng
- compiler (bộ biên dịch cục bộ)
- validation (kiểm tra hợp lệ)
- retry (thử lại)
- fallback (đường dự phòng)

Điều này giúp hệ thống giữ được tính kiểm soát tốt hơn so với việc chỉ prompt mô hình rồi lấy thẳng kết quả.

## 4. Kết luận

Ở trạng thái hiện tại, hệ thống có thể được tóm tắt như sau:

- nhận đề bài và bài làm học sinh
- dựng lời giải chuẩn nội bộ cho đề bài
- dựng biểu diễn có cấu trúc cho bài làm học sinh
- so sánh hai phía ở mức reasoning
- chẩn đoán lỗi
- tạo gợi ý phù hợp

Điểm quan trọng nhất của dự án là:

- hệ thống không chỉ kiểm tra đáp án cuối
- mà cố gắng mô hình hóa cả quá trình giải và quá trình mắc lỗi của học sinh

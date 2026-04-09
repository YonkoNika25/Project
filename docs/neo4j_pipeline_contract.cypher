// Graph trực quan ở mức contract:
// mỗi module có input gì, đi qua các substep gì, và trả output gì.
// Chạy từng block một trong Neo4j Browser, hoặc nạp bằng cypher-shell theo block.

// BLOCK 1
MATCH (n:Contract)
DETACH DELETE n

// BLOCK 2
MERGE (sys:Contract:System {id:'tutoring_pipeline_contract'})
SET sys.name = 'Tutoring Pipeline Contract'
MERGE (m1:Contract:Module {id:'formalize_problem'})
SET m1.name = 'formalize_problem',
    m1.stage = 'problem',
    m1.summary = 'Nhận problem_text, tạo heuristic anchors, gọi LLM semantic sketch, local build, validate/retry, trả FormalizedProblem'
MERGE (m2:Contract:Module {id:'build_canonical_reference'})
SET m2.name = 'build_canonical_reference',
    m2.stage = 'runtime',
    m2.summary = 'Nhận FormalizedProblem, compile graph thành plan, execute, dựng CanonicalReference'
MERGE (m3:Contract:Module {id:'formalize_student_work'})
SET m3.name = 'formalize_student_work',
    m3.stage = 'student',
    m3.summary = 'Nhận student_answer cùng problem/reference, tạo heuristic state, gọi LLM semantic sketch, local build, validate/retry'
MERGE (m4:Contract:Module {id:'build_diagnosis_evidence'})
SET m4.name = 'build_diagnosis_evidence',
    m4.stage = 'evidence',
    m4.summary = 'Nhận problem, reference, student work; align và dựng DiagnosisEvidence'
MERGE (m5:Contract:Module {id:'diagnose'})
SET m5.name = 'diagnose',
    m5.stage = 'diagnosis',
    m5.summary = 'Nhận DiagnosisEvidence, chấm hypothesis và chọn DiagnosisResult'
MERGE (m6:Contract:Module {id:'build_hint_plan'})
SET m6.name = 'build_hint_plan',
    m6.stage = 'pedagogy',
    m6.summary = 'Nhận problem, reference, diagnosis; dựng HintPlan'
MERGE (m7:Contract:Module {id:'build_hint_result'})
SET m7.name = 'build_hint_result',
    m7.stage = 'hint',
    m7.summary = 'Nhận problem, reference, diagnosis, plan; sinh và verify hint cuối'
MERGE (sys)-[:HAS_MODULE]->(m1)
MERGE (sys)-[:HAS_MODULE]->(m2)
MERGE (sys)-[:HAS_MODULE]->(m3)
MERGE (sys)-[:HAS_MODULE]->(m4)
MERGE (sys)-[:HAS_MODULE]->(m5)
MERGE (sys)-[:HAS_MODULE]->(m6)
MERGE (sys)-[:HAS_MODULE]->(m7)
MERGE (m1)-[:NEXT_MODULE]->(m2)
MERGE (m2)-[:NEXT_MODULE]->(m3)
MERGE (m3)-[:NEXT_MODULE]->(m4)
MERGE (m4)-[:NEXT_MODULE]->(m5)
MERGE (m5)-[:NEXT_MODULE]->(m6)
MERGE (m6)-[:NEXT_MODULE]->(m7)

// BLOCK 3
MERGE (a1:Contract:Artifact {id:'problem_text'})
SET a1.name = 'problem_text',
    a1.kind = 'raw_input'
MERGE (a2:Contract:Artifact {id:'student_answer'})
SET a2.name = 'student_answer',
    a2.kind = 'raw_input'
MERGE (a3:Contract:Artifact {id:'problem_evidence_pack'})
SET a3.name = 'problem_evidence_pack',
    a3.kind = 'intermediate'
MERGE (a4:Contract:Artifact {id:'heuristic_problem'})
SET a4.name = 'heuristic_problem',
    a4.kind = 'intermediate'
MERGE (a5:Contract:Artifact {id:'problem_semantic_sketch'})
SET a5.name = 'problem_semantic_sketch',
    a5.kind = 'llm_output'
MERGE (a6:Contract:Artifact {id:'formalized_problem'})
SET a6.name = 'FormalizedProblem',
    a6.kind = 'module_output'
MERGE (a7:Contract:Artifact {id:'problem_graph'})
SET a7.name = 'problem_graph',
    a7.kind = 'subartifact'
MERGE (a8:Contract:Artifact {id:'executable_plan'})
SET a8.name = 'ExecutablePlan',
    a8.kind = 'intermediate'
MERGE (a9:Contract:Artifact {id:'execution_trace'})
SET a9.name = 'ExecutionTrace',
    a9.kind = 'intermediate'
MERGE (a10:Contract:Artifact {id:'canonical_reference'})
SET a10.name = 'CanonicalReference',
    a10.kind = 'module_output'
MERGE (a11:Contract:Artifact {id:'heuristic_student_state'})
SET a11.name = 'heuristic_student_state',
    a11.kind = 'intermediate'
MERGE (a12:Contract:Artifact {id:'student_semantic_sketch'})
SET a12.name = 'student_semantic_sketch',
    a12.kind = 'llm_output'
MERGE (a13:Contract:Artifact {id:'student_work'})
SET a13.name = 'StudentWorkState',
    a13.kind = 'module_output'
MERGE (a14:Contract:Artifact {id:'student_graph'})
SET a14.name = 'student_graph',
    a14.kind = 'subartifact'
MERGE (a15:Contract:Artifact {id:'diagnosis_evidence'})
SET a15.name = 'DiagnosisEvidence',
    a15.kind = 'module_output'
MERGE (a16:Contract:Artifact {id:'diagnosis_result'})
SET a16.name = 'DiagnosisResult',
    a16.kind = 'module_output'
MERGE (a17:Contract:Artifact {id:'hint_plan'})
SET a17.name = 'HintPlan',
    a17.kind = 'module_output'
MERGE (a18:Contract:Artifact {id:'hint_text'})
SET a18.name = 'hint_text',
    a18.kind = 'intermediate'
MERGE (a19:Contract:Artifact {id:'hint_result'})
SET a19.name = 'HintResult',
    a19.kind = 'module_output'

// BLOCK 4
MATCH (m1:Contract:Module {id:'formalize_problem'})
MATCH (a1:Contract:Artifact {id:'problem_text'})
MATCH (a3:Contract:Artifact {id:'problem_evidence_pack'})
MATCH (a4:Contract:Artifact {id:'heuristic_problem'})
MATCH (a5:Contract:Artifact {id:'problem_semantic_sketch'})
MATCH (a6:Contract:Artifact {id:'formalized_problem'})
MATCH (a7:Contract:Artifact {id:'problem_graph'})
MERGE (s11:Contract:Step {id:'formalize_problem.heuristic_parse'})
SET s11.name = 'heuristic_parse',
    s11.summary = 'Từ problem_text tạo evidence_pack và heuristic_problem'
MERGE (s12:Contract:Step {id:'formalize_problem.llm_semantic_sketch'})
SET s12.name = 'llm_semantic_sketch',
    s12.summary = 'LLM nhận problem_text + evidence_pack + heuristic_problem và trả semantic sketch'
MERGE (s13:Contract:Step {id:'formalize_problem.local_build'})
SET s13.name = 'local_build',
    s13.summary = 'Local builder compile sketch thành FormalizedProblem và problem_graph'
MERGE (s14:Contract:Step {id:'formalize_problem.validate_retry'})
SET s14.name = 'validate_retry',
    s14.summary = 'Validate graph/schema; nếu lỗi thì retry hoặc fallback heuristic'
MERGE (m1)-[:HAS_STEP]->(s11)
MERGE (m1)-[:HAS_STEP]->(s12)
MERGE (m1)-[:HAS_STEP]->(s13)
MERGE (m1)-[:HAS_STEP]->(s14)
MERGE (s11)-[:NEXT_STEP]->(s12)
MERGE (s12)-[:NEXT_STEP]->(s13)
MERGE (s13)-[:NEXT_STEP]->(s14)
MERGE (a1)-[:INPUT_TO]->(s11)
MERGE (s11)-[:OUTPUTS]->(a3)
MERGE (s11)-[:OUTPUTS]->(a4)
MERGE (a1)-[:INPUT_TO]->(s12)
MERGE (a3)-[:INPUT_TO]->(s12)
MERGE (a4)-[:INPUT_TO]->(s12)
MERGE (s12)-[:OUTPUTS]->(a5)
MERGE (a4)-[:INPUT_TO]->(s13)
MERGE (a5)-[:INPUT_TO]->(s13)
MERGE (s13)-[:OUTPUTS]->(a6)
MERGE (s13)-[:OUTPUTS]->(a7)
MERGE (a6)-[:INPUT_TO]->(s14)
MERGE (a7)-[:INPUT_TO]->(s14)
MERGE (s14)-[:OUTPUTS]->(a6)
MERGE (m1)-[:MODULE_INPUT]->(a1)
MERGE (m1)-[:MODULE_OUTPUT]->(a6)
MERGE (a6)-[:HAS_SUBARTIFACT]->(a7)

// BLOCK 5
MATCH (m2:Contract:Module {id:'build_canonical_reference'})
MATCH (a6:Contract:Artifact {id:'formalized_problem'})
MATCH (a8:Contract:Artifact {id:'executable_plan'})
MATCH (a9:Contract:Artifact {id:'execution_trace'})
MATCH (a10:Contract:Artifact {id:'canonical_reference'})
MERGE (s21:Contract:Step {id:'build_canonical_reference.build_solver_candidate'})
SET s21.name = 'build_solver_candidate',
    s21.summary = 'Từ FormalizedProblem chọn hướng solver và chuẩn bị runtime build'
MERGE (s22:Contract:Step {id:'build_canonical_reference.compile_plan'})
SET s22.name = 'compile_plan',
    s22.summary = 'Compile problem graph hoặc relation fallback thành ExecutablePlan'
MERGE (s23:Contract:Step {id:'build_canonical_reference.execute_plan'})
SET s23.name = 'execute_plan',
    s23.summary = 'Thực thi plan và sinh execution trace'
MERGE (s24:Contract:Step {id:'build_canonical_reference.package_reference'})
SET s24.name = 'package_reference',
    s24.summary = 'Đóng gói final answer, plan và trace vào CanonicalReference'
MERGE (m2)-[:HAS_STEP]->(s21)
MERGE (m2)-[:HAS_STEP]->(s22)
MERGE (m2)-[:HAS_STEP]->(s23)
MERGE (m2)-[:HAS_STEP]->(s24)
MERGE (s21)-[:NEXT_STEP]->(s22)
MERGE (s22)-[:NEXT_STEP]->(s23)
MERGE (s23)-[:NEXT_STEP]->(s24)
MERGE (a6)-[:INPUT_TO]->(s21)
MERGE (a6)-[:INPUT_TO]->(s22)
MERGE (s22)-[:OUTPUTS]->(a8)
MERGE (a8)-[:INPUT_TO]->(s23)
MERGE (s23)-[:OUTPUTS]->(a9)
MERGE (a6)-[:INPUT_TO]->(s24)
MERGE (a8)-[:INPUT_TO]->(s24)
MERGE (a9)-[:INPUT_TO]->(s24)
MERGE (s24)-[:OUTPUTS]->(a10)
MERGE (m2)-[:MODULE_INPUT]->(a6)
MERGE (m2)-[:MODULE_OUTPUT]->(a10)

// BLOCK 6
MATCH (m3:Contract:Module {id:'formalize_student_work'})
MATCH (a2:Contract:Artifact {id:'student_answer'})
MATCH (a6:Contract:Artifact {id:'formalized_problem'})
MATCH (a10:Contract:Artifact {id:'canonical_reference'})
MATCH (a11:Contract:Artifact {id:'heuristic_student_state'})
MATCH (a12:Contract:Artifact {id:'student_semantic_sketch'})
MATCH (a13:Contract:Artifact {id:'student_work'})
MATCH (a14:Contract:Artifact {id:'student_graph'})
MERGE (s31:Contract:Step {id:'formalize_student_work.heuristic_parse'})
SET s31.name = 'heuristic_parse',
    s31.summary = 'Từ student_answer tạo heuristic_student_state'
MERGE (s32:Contract:Step {id:'formalize_student_work.llm_semantic_sketch'})
SET s32.name = 'llm_semantic_sketch',
    s32.summary = 'LLM nhận student_answer + problem + reference + heuristic state và trả semantic sketch'
MERGE (s33:Contract:Step {id:'formalize_student_work.local_build'})
SET s33.name = 'local_build',
    s33.summary = 'Local builder compile sketch thành StudentWorkState và student_graph'
MERGE (s34:Contract:Step {id:'formalize_student_work.validate_retry'})
SET s34.name = 'validate_retry',
    s34.summary = 'Validate consistency/refs; nếu lỗi thì retry hoặc fallback heuristic'
MERGE (m3)-[:HAS_STEP]->(s31)
MERGE (m3)-[:HAS_STEP]->(s32)
MERGE (m3)-[:HAS_STEP]->(s33)
MERGE (m3)-[:HAS_STEP]->(s34)
MERGE (s31)-[:NEXT_STEP]->(s32)
MERGE (s32)-[:NEXT_STEP]->(s33)
MERGE (s33)-[:NEXT_STEP]->(s34)
MERGE (a2)-[:INPUT_TO]->(s31)
MERGE (s31)-[:OUTPUTS]->(a11)
MERGE (a2)-[:INPUT_TO]->(s32)
MERGE (a6)-[:INPUT_TO]->(s32)
MERGE (a10)-[:INPUT_TO]->(s32)
MERGE (a11)-[:INPUT_TO]->(s32)
MERGE (s32)-[:OUTPUTS]->(a12)
MERGE (a11)-[:INPUT_TO]->(s33)
MERGE (a12)-[:INPUT_TO]->(s33)
MERGE (a6)-[:INPUT_TO]->(s33)
MERGE (a10)-[:INPUT_TO]->(s33)
MERGE (s33)-[:OUTPUTS]->(a13)
MERGE (s33)-[:OUTPUTS]->(a14)
MERGE (a13)-[:INPUT_TO]->(s34)
MERGE (a14)-[:INPUT_TO]->(s34)
MERGE (s34)-[:OUTPUTS]->(a13)
MERGE (m3)-[:MODULE_INPUT]->(a2)
MERGE (m3)-[:MODULE_INPUT]->(a6)
MERGE (m3)-[:MODULE_INPUT]->(a10)
MERGE (m3)-[:MODULE_OUTPUT]->(a13)
MERGE (a13)-[:HAS_SUBARTIFACT]->(a14)

// BLOCK 7
MATCH (m4:Contract:Module {id:'build_diagnosis_evidence'})
MATCH (a6:Contract:Artifact {id:'formalized_problem'})
MATCH (a10:Contract:Artifact {id:'canonical_reference'})
MATCH (a13:Contract:Artifact {id:'student_work'})
MATCH (a15:Contract:Artifact {id:'diagnosis_evidence'})
MERGE (s41:Contract:Step {id:'build_diagnosis_evidence.project_payloads'})
SET s41.name = 'project_payloads',
    s41.summary = 'Chiếu reference và student sang payload alignment'
MERGE (s42:Contract:Step {id:'build_diagnosis_evidence.align_and_infer'})
SET s42.name = 'align_and_infer',
    s42.summary = 'Align step toàn cục, infer target path và graph edits'
MERGE (s43:Contract:Step {id:'build_diagnosis_evidence.package_evidence'})
SET s43.name = 'package_evidence',
    s43.summary = 'Đóng gói EvidenceItem và metadata thành DiagnosisEvidence'
MERGE (m4)-[:HAS_STEP]->(s41)
MERGE (m4)-[:HAS_STEP]->(s42)
MERGE (m4)-[:HAS_STEP]->(s43)
MERGE (s41)-[:NEXT_STEP]->(s42)
MERGE (s42)-[:NEXT_STEP]->(s43)
MERGE (a6)-[:INPUT_TO]->(s41)
MERGE (a10)-[:INPUT_TO]->(s41)
MERGE (a13)-[:INPUT_TO]->(s41)
MERGE (a10)-[:INPUT_TO]->(s42)
MERGE (a13)-[:INPUT_TO]->(s42)
MERGE (a6)-[:INPUT_TO]->(s43)
MERGE (a10)-[:INPUT_TO]->(s43)
MERGE (a13)-[:INPUT_TO]->(s43)
MERGE (s43)-[:OUTPUTS]->(a15)
MERGE (m4)-[:MODULE_INPUT]->(a6)
MERGE (m4)-[:MODULE_INPUT]->(a10)
MERGE (m4)-[:MODULE_INPUT]->(a13)
MERGE (m4)-[:MODULE_OUTPUT]->(a15)

// BLOCK 8
MATCH (m5:Contract:Module {id:'diagnose'})
MATCH (a15:Contract:Artifact {id:'diagnosis_evidence'})
MATCH (a16:Contract:Artifact {id:'diagnosis_result'})
MERGE (s51:Contract:Step {id:'diagnose.score_hypotheses'})
SET s51.name = 'score_hypotheses',
    s51.summary = 'Chấm các hypothesis từ evidence'
MERGE (s52:Contract:Step {id:'diagnose.optional_llm_review'})
SET s52.name = 'optional_llm_review',
    s52.summary = 'LLM có thể review nhưng không thay deterministic contract'
MERGE (s53:Contract:Step {id:'diagnose.select_result'})
SET s53.name = 'select_result',
    s53.summary = 'Chọn nhãn chẩn đoán cuối và localization'
MERGE (m5)-[:HAS_STEP]->(s51)
MERGE (m5)-[:HAS_STEP]->(s52)
MERGE (m5)-[:HAS_STEP]->(s53)
MERGE (s51)-[:NEXT_STEP]->(s52)
MERGE (s52)-[:NEXT_STEP]->(s53)
MERGE (a15)-[:INPUT_TO]->(s51)
MERGE (a15)-[:INPUT_TO]->(s52)
MERGE (a15)-[:INPUT_TO]->(s53)
MERGE (s53)-[:OUTPUTS]->(a16)
MERGE (m5)-[:MODULE_INPUT]->(a15)
MERGE (m5)-[:MODULE_OUTPUT]->(a16)

// BLOCK 9
MATCH (m6:Contract:Module {id:'build_hint_plan'})
MATCH (m7:Contract:Module {id:'build_hint_result'})
MATCH (a6:Contract:Artifact {id:'formalized_problem'})
MATCH (a10:Contract:Artifact {id:'canonical_reference'})
MATCH (a16:Contract:Artifact {id:'diagnosis_result'})
MATCH (a17:Contract:Artifact {id:'hint_plan'})
MATCH (a18:Contract:Artifact {id:'hint_text'})
MATCH (a19:Contract:Artifact {id:'hint_result'})
MERGE (s61:Contract:Step {id:'build_hint_plan.plan_from_diagnosis'})
SET s61.name = 'plan_from_diagnosis',
    s61.summary = 'Từ diagnosis và reference dựng HintPlan'
MERGE (s62:Contract:Step {id:'build_hint_plan.package_plan'})
SET s62.name = 'package_plan',
    s62.summary = 'Hoàn thiện disclosure budget, focus points và must_not_reveal'
MERGE (m6)-[:HAS_STEP]->(s61)
MERGE (m6)-[:HAS_STEP]->(s62)
MERGE (s61)-[:NEXT_STEP]->(s62)
MERGE (a6)-[:INPUT_TO]->(s61)
MERGE (a10)-[:INPUT_TO]->(s61)
MERGE (a16)-[:INPUT_TO]->(s61)
MERGE (a6)-[:INPUT_TO]->(s62)
MERGE (a10)-[:INPUT_TO]->(s62)
MERGE (a16)-[:INPUT_TO]->(s62)
MERGE (s62)-[:OUTPUTS]->(a17)
MERGE (m6)-[:MODULE_INPUT]->(a6)
MERGE (m6)-[:MODULE_INPUT]->(a10)
MERGE (m6)-[:MODULE_INPUT]->(a16)
MERGE (m6)-[:MODULE_OUTPUT]->(a17)
MERGE (s71:Contract:Step {id:'build_hint_result.generate_text'})
SET s71.name = 'generate_text',
    s71.summary = 'Sinh hint text bằng deterministic hoặc LLM generator'
MERGE (s72:Contract:Step {id:'build_hint_result.verify_text'})
SET s72.name = 'verify_text',
    s72.summary = 'Kiểm spoiler và alignment với hint plan'
MERGE (s73:Contract:Step {id:'build_hint_result.repair_or_fallback'})
SET s73.name = 'repair_or_fallback',
    s73.summary = 'Nếu verify fail thì repair hoặc fallback rồi trả HintResult'
MERGE (m7)-[:HAS_STEP]->(s71)
MERGE (m7)-[:HAS_STEP]->(s72)
MERGE (m7)-[:HAS_STEP]->(s73)
MERGE (s71)-[:NEXT_STEP]->(s72)
MERGE (s72)-[:NEXT_STEP]->(s73)
MERGE (a6)-[:INPUT_TO]->(s71)
MERGE (a10)-[:INPUT_TO]->(s71)
MERGE (a16)-[:INPUT_TO]->(s71)
MERGE (a17)-[:INPUT_TO]->(s71)
MERGE (s71)-[:OUTPUTS]->(a18)
MERGE (a18)-[:INPUT_TO]->(s72)
MERGE (a17)-[:INPUT_TO]->(s72)
MERGE (a18)-[:INPUT_TO]->(s73)
MERGE (a17)-[:INPUT_TO]->(s73)
MERGE (a6)-[:INPUT_TO]->(s73)
MERGE (a10)-[:INPUT_TO]->(s73)
MERGE (a16)-[:INPUT_TO]->(s73)
MERGE (s73)-[:OUTPUTS]->(a19)
MERGE (m7)-[:MODULE_INPUT]->(a6)
MERGE (m7)-[:MODULE_INPUT]->(a10)
MERGE (m7)-[:MODULE_INPUT]->(a16)
MERGE (m7)-[:MODULE_INPUT]->(a17)
MERGE (m7)-[:MODULE_OUTPUT]->(a19)

// BLOCK 10
MATCH (a6:Contract:Artifact {id:'formalized_problem'})
MATCH (a10:Contract:Artifact {id:'canonical_reference'})
MATCH (a13:Contract:Artifact {id:'student_work'})
MATCH (a15:Contract:Artifact {id:'diagnosis_evidence'})
MATCH (a16:Contract:Artifact {id:'diagnosis_result'})
MATCH (a17:Contract:Artifact {id:'hint_plan'})
MATCH (a19:Contract:Artifact {id:'hint_result'})
MERGE (a6)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_canonical_reference'})
MERGE (a6)-[:FEEDS_MODULE]->(:Contract:Module {id:'formalize_student_work'})
MERGE (a6)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_diagnosis_evidence'})
MERGE (a6)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_hint_plan'})
MERGE (a6)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_hint_result'})
MERGE (a10)-[:FEEDS_MODULE]->(:Contract:Module {id:'formalize_student_work'})
MERGE (a10)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_diagnosis_evidence'})
MERGE (a10)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_hint_plan'})
MERGE (a10)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_hint_result'})
MERGE (a13)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_diagnosis_evidence'})
MERGE (a15)-[:FEEDS_MODULE]->(:Contract:Module {id:'diagnose'})
MERGE (a16)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_hint_plan'})
MERGE (a16)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_hint_result'})
MERGE (a17)-[:FEEDS_MODULE]->(:Contract:Module {id:'build_hint_result'})

// BLOCK 11
MATCH (sys:Contract:System {id:'tutoring_pipeline_contract'})
OPTIONAL MATCH (sys)-[:HAS_MODULE]->(m:Contract:Module)
OPTIONAL MATCH (m)-[:HAS_STEP]->(s:Contract:Step)
OPTIONAL MATCH (a:Contract:Artifact)-[r:INPUT_TO|OUTPUTS]->(s)
RETURN sys, m, s, a, r

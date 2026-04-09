// Deep logic graph. Run one block at a time in Neo4j Browser.

// BLOCK 1
MATCH (n:Logic)
DETACH DELETE n;

// BLOCK 2
MERGE (sys:Logic:System {id:'tutoring_system'}) SET sys.name='Tutoring System';
MERGE (s1:Logic:Stage {id:'problem'}) SET s1.name='Problem Side';
MERGE (s2:Logic:Stage {id:'runtime'}) SET s2.name='Runtime Reference';
MERGE (s3:Logic:Stage {id:'student'}) SET s3.name='Student Side';
MERGE (s4:Logic:Stage {id:'evidence'}) SET s4.name='Evidence';
MERGE (s5:Logic:Stage {id:'diagnosis'}) SET s5.name='Diagnosis';
MERGE (s6:Logic:Stage {id:'pedagogy'}) SET s6.name='Pedagogy';
MERGE (s7:Logic:Stage {id:'hint'}) SET s7.name='Hint';
MERGE (sys)-[:HAS_STAGE]->(s1)
MERGE (sys)-[:HAS_STAGE]->(s2)
MERGE (sys)-[:HAS_STAGE]->(s3)
MERGE (sys)-[:HAS_STAGE]->(s4)
MERGE (sys)-[:HAS_STAGE]->(s5)
MERGE (sys)-[:HAS_STAGE]->(s6)
MERGE (sys)-[:HAS_STAGE]->(s7)
MERGE (s1)-[:NEXT_STAGE]->(s2)
MERGE (s2)-[:NEXT_STAGE]->(s3)
MERGE (s3)-[:NEXT_STAGE]->(s4)
MERGE (s4)-[:NEXT_STAGE]->(s5)
MERGE (s5)-[:NEXT_STAGE]->(s6)
MERGE (s6)-[:NEXT_STAGE]->(s7);

// BLOCK 3
MERGE (m0:Logic:Module {id:'pipeline.runner'}) SET m0.name='src/pipeline/runner.py';
MERGE (m1:Logic:Module {id:'formalizer.problem_entry'}) SET m1.name='src/formalizer/problem_formalizer.py';
MERGE (m2:Logic:Module {id:'formalizer.problem_builder'}) SET m2.name='src/formalizer/problem_formalizer_builder.py';
MERGE (m3:Logic:Module {id:'formalizer.problem_extractors'}) SET m3.name='src/formalizer/problem_formalizer_extractors.py';
MERGE (m4:Logic:Module {id:'formalizer.problem_llm'}) SET m4.name='src/formalizer/problem_formalizer_llm.py';
MERGE (m5:Logic:Module {id:'runtime.compiler'}) SET m5.name='src/runtime/compiler.py';
MERGE (m6:Logic:Module {id:'runtime.solver'}) SET m6.name='src/runtime/solver.py';
MERGE (m7:Logic:Module {id:'formalizer.student_entry'}) SET m7.name='src/formalizer/student_work.py';
MERGE (m8:Logic:Module {id:'formalizer.student_builder'}) SET m8.name='src/formalizer/student_work_builder.py';
MERGE (m9:Logic:Module {id:'formalizer.student_llm'}) SET m9.name='src/formalizer/student_work_llm.py';
MERGE (m10:Logic:Module {id:'evidence.builder'}) SET m10.name='src/evidence/builder.py';
MERGE (m11:Logic:Module {id:'evidence.alignment'}) SET m11.name='src/evidence/alignment.py';
MERGE (m12:Logic:Module {id:'diagnosis.engine'}) SET m12.name='src/diagnosis/engine.py';
MERGE (m13:Logic:Module {id:'diagnosis.scoring'}) SET m13.name='src/diagnosis/scoring.py';
MERGE (m14:Logic:Module {id:'pedagogy.planner'}) SET m14.name='src/pedagogy/planner.py';
MERGE (m15:Logic:Module {id:'hint.controller'}) SET m15.name='src/hint/controller.py';
MERGE (m16:Logic:Module {id:'hint.generator'}) SET m16.name='src/hint/generator.py';
MERGE (m17:Logic:Module {id:'hint.verifier'}) SET m17.name='src/hint/verifier.py';
MERGE (m18:Logic:Module {id:'hint.repair'}) SET m18.name='src/hint/repair.py';
MATCH (sys:Logic:System {id:'tutoring_system'})
MATCH (s1:Logic:Stage {id:'problem'})
MATCH (s2:Logic:Stage {id:'runtime'})
MATCH (s3:Logic:Stage {id:'student'})
MATCH (s4:Logic:Stage {id:'evidence'})
MATCH (s5:Logic:Stage {id:'diagnosis'})
MATCH (s6:Logic:Stage {id:'pedagogy'})
MATCH (s7:Logic:Stage {id:'hint'})
MERGE (sys)-[:HAS_MODULE]->(m0)
MERGE (s1)-[:HAS_MODULE]->(m1)
MERGE (s1)-[:HAS_MODULE]->(m2)
MERGE (s1)-[:HAS_MODULE]->(m3)
MERGE (s1)-[:HAS_MODULE]->(m4)
MERGE (s2)-[:HAS_MODULE]->(m5)
MERGE (s2)-[:HAS_MODULE]->(m6)
MERGE (s3)-[:HAS_MODULE]->(m7)
MERGE (s3)-[:HAS_MODULE]->(m8)
MERGE (s3)-[:HAS_MODULE]->(m9)
MERGE (s4)-[:HAS_MODULE]->(m10)
MERGE (s4)-[:HAS_MODULE]->(m11)
MERGE (s5)-[:HAS_MODULE]->(m12)
MERGE (s5)-[:HAS_MODULE]->(m13)
MERGE (s6)-[:HAS_MODULE]->(m14)
MERGE (s7)-[:HAS_MODULE]->(m15)
MERGE (s7)-[:HAS_MODULE]->(m16)
MERGE (s7)-[:HAS_MODULE]->(m17)
MERGE (s7)-[:HAS_MODULE]->(m18);

// BLOCK 4
MERGE (a1:Logic:Artifact {id:'problem_text'}) SET a1.name='problem_text';
MERGE (a2:Logic:Artifact {id:'student_answer'}) SET a2.name='student_answer';
MERGE (a3:Logic:Artifact {id:'problem_evidence_pack'}) SET a3.name='problem evidence pack';
MERGE (a4:Logic:Artifact {id:'heuristic_problem'}) SET a4.name='heuristic FormalizedProblem';
MERGE (a5:Logic:Artifact {id:'problem_semantic_sketch'}) SET a5.name='problem semantic sketch';
MERGE (a6:Logic:Artifact {id:'formalized_problem'}) SET a6.name='FormalizedProblem';
MERGE (a7:Logic:Artifact {id:'problem_graph'}) SET a7.name='ProblemGraph';
MERGE (a8:Logic:Artifact {id:'executable_plan'}) SET a8.name='ExecutablePlan';
MERGE (a9:Logic:Artifact {id:'execution_trace'}) SET a9.name='ExecutionTrace';
MERGE (a10:Logic:Artifact {id:'canonical_reference'}) SET a10.name='CanonicalReference';
MERGE (a11:Logic:Artifact {id:'heuristic_student_state'}) SET a11.name='heuristic StudentWorkState';
MERGE (a12:Logic:Artifact {id:'student_semantic_sketch'}) SET a12.name='student semantic sketch';
MERGE (a13:Logic:Artifact {id:'student_work'}) SET a13.name='StudentWorkState';
MERGE (a14:Logic:Artifact {id:'student_graph'}) SET a14.name='student graph';
MERGE (a15:Logic:Artifact {id:'diagnosis_evidence'}) SET a15.name='DiagnosisEvidence';
MERGE (a16:Logic:Artifact {id:'diagnosis_result'}) SET a16.name='DiagnosisResult';
MERGE (a17:Logic:Artifact {id:'hint_plan'}) SET a17.name='HintPlan';
MERGE (a18:Logic:Artifact {id:'hint_text'}) SET a18.name='generated hint text';
MERGE (a19:Logic:Artifact {id:'hint_result'}) SET a19.name='HintResult';

// BLOCK 5
MERGE (c1:Logic:Concept {id:'heuristic_anchor'}) SET c1.name='heuristic anchor';
MERGE (c2:Logic:Concept {id:'candidate_generation'}) SET c2.name='candidate generation';
MERGE (c3:Logic:Concept {id:'semantic_sketch'}) SET c3.name='semantic sketch';
MERGE (c4:Logic:Concept {id:'local_compile'}) SET c4.name='local compile';
MERGE (c5:Logic:Concept {id:'validation_retry'}) SET c5.name='validation and retry';
MERGE (c6:Logic:Concept {id:'fallback'}) SET c6.name='fallback';
MERGE (c7:Logic:Concept {id:'global_alignment'}) SET c7.name='global alignment';
MERGE (c8:Logic:Concept {id:'deterministic_scoring'}) SET c8.name='deterministic scoring';
MERGE (c9:Logic:Concept {id:'pedagogical_planning'}) SET c9.name='pedagogical planning';
MERGE (c10:Logic:Concept {id:'hint_verification'}) SET c10.name='hint verification';

// BLOCK 6
MERGE (f0:Logic:Function {id:'run_tutoring_pipeline'}) SET f0.name='run_tutoring_pipeline';
MATCH (m0:Logic:Module {id:'pipeline.runner'})
MATCH (a1:Logic:Artifact {id:'problem_text'})
MATCH (a2:Logic:Artifact {id:'student_answer'})
MERGE (m0)-[:DEFINES]->(f0)
MERGE (f0)-[:READS]->(a1)
MERGE (f0)-[:READS]->(a2)
MERGE (f0)-[:CALLS]->(:Logic:Function {id:'formalize_problem', name:'formalize_problem'})
MERGE (f0)-[:CALLS]->(:Logic:Function {id:'build_canonical_reference', name:'build_canonical_reference'})
MERGE (f0)-[:CALLS]->(:Logic:Function {id:'formalize_student_work', name:'formalize_student_work'})
MERGE (f0)-[:CALLS]->(:Logic:Function {id:'build_diagnosis_evidence', name:'build_diagnosis_evidence'})
MERGE (f0)-[:CALLS]->(:Logic:Function {id:'diagnose', name:'diagnose'})
MERGE (f0)-[:CALLS]->(:Logic:Function {id:'build_hint_plan', name:'build_hint_plan'})
MERGE (f0)-[:CALLS]->(:Logic:Function {id:'build_hint_result', name:'build_hint_result'});

// BLOCK 7
MERGE (f1:Logic:Function {id:'formalize_problem'}) SET f1.name='formalize_problem';
MERGE (f2:Logic:Function {id:'_heuristic_formalize_problem'}) SET f2.name='_heuristic_formalize_problem';
MERGE (f3:Logic:Function {id:'_build_problem_anchor_evidence'}) SET f3.name='_build_problem_anchor_evidence';
MERGE (f4:Logic:Function {id:'_project_quantities_from_evidence'}) SET f4.name='_project_quantities_from_evidence';
MERGE (f5:Logic:Function {id:'_project_target_from_evidence'}) SET f5.name='_project_target_from_evidence';
MERGE (f6:Logic:Function {id:'_project_relation_candidates_from_evidence'}) SET f6.name='_project_relation_candidates_from_evidence';
MERGE (f7:Logic:Function {id:'_attach_problem_graph'}) SET f7.name='_attach_problem_graph';
MERGE (f8:Logic:Function {id:'_llm_formalize_problem'}) SET f8.name='_llm_formalize_problem';
MERGE (f9:Logic:Function {id:'_build_llm_graph_prompt'}) SET f9.name='_build_llm_graph_prompt';
MERGE (f10:Logic:Function {id:'_build_formalized_problem_from_skeleton'}) SET f10.name='_build_formalized_problem_from_skeleton';
MERGE (f11:Logic:Function {id:'_compile_quantities_from_semantic_sketch'}) SET f11.name='_compile_quantities_from_semantic_sketch';
MERGE (f12:Logic:Function {id:'_build_target_payload_from_sketch'}) SET f12.name='_build_target_payload_from_sketch';
MERGE (f13:Logic:Function {id:'_build_relation_candidates_from_sketch'}) SET f13.name='_build_relation_candidates_from_sketch';
MERGE (f14:Logic:Function {id:'_normalize_graph_steps_for_builder'}) SET f14.name='_normalize_graph_steps_for_builder';
MERGE (f15:Logic:Function {id:'_build_problem_graph_from_skeleton'}) SET f15.name='_build_problem_graph_from_skeleton';
MATCH (m1:Logic:Module {id:'formalizer.problem_entry'})
MATCH (m2:Logic:Module {id:'formalizer.problem_builder'})
MATCH (m3:Logic:Module {id:'formalizer.problem_extractors'})
MATCH (m4:Logic:Module {id:'formalizer.problem_llm'})
MATCH (a1:Logic:Artifact {id:'problem_text'})
MATCH (a3:Logic:Artifact {id:'problem_evidence_pack'})
MATCH (a4:Logic:Artifact {id:'heuristic_problem'})
MATCH (a5:Logic:Artifact {id:'problem_semantic_sketch'})
MATCH (a6:Logic:Artifact {id:'formalized_problem'})
MATCH (a7:Logic:Artifact {id:'problem_graph'})
MATCH (c1:Logic:Concept {id:'heuristic_anchor'})
MATCH (c2:Logic:Concept {id:'candidate_generation'})
MATCH (c3:Logic:Concept {id:'semantic_sketch'})
MATCH (c4:Logic:Concept {id:'local_compile'})
MATCH (c5:Logic:Concept {id:'validation_retry'})
MATCH (c6:Logic:Concept {id:'fallback'})
MERGE (m1)-[:DEFINES]->(f1)
MERGE (m2)-[:DEFINES]->(f2)
MERGE (m3)-[:DEFINES]->(f3)
MERGE (m3)-[:DEFINES]->(f4)
MERGE (m3)-[:DEFINES]->(f5)
MERGE (m3)-[:DEFINES]->(f6)
MERGE (m2)-[:DEFINES]->(f7)
MERGE (m4)-[:DEFINES]->(f8)
MERGE (m4)-[:DEFINES]->(f9)
MERGE (m2)-[:DEFINES]->(f10)
MERGE (m2)-[:DEFINES]->(f11)
MERGE (m2)-[:DEFINES]->(f12)
MERGE (m2)-[:DEFINES]->(f13)
MERGE (m2)-[:DEFINES]->(f14)
MERGE (m2)-[:DEFINES]->(f15)
MERGE (f1)-[:READS]->(a1)
MERGE (f1)-[:CALLS]->(f2)
MERGE (f1)-[:CALLS]->(f8)
MERGE (f1)-[:CAN_FALLBACK_TO]->(a4)
MERGE (f2)-[:CALLS]->(f3)
MERGE (f2)-[:CALLS]->(f4)
MERGE (f2)-[:CALLS]->(f5)
MERGE (f2)-[:CALLS]->(f6)
MERGE (f2)-[:CALLS]->(f7)
MERGE (f2)-[:PRODUCES]->(a3)
MERGE (f2)-[:PRODUCES]->(a4)
MERGE (f2)-[:IMPLEMENTS]->(c1)
MERGE (f3)-[:IMPLEMENTS]->(c2)
MERGE (f8)-[:READS]->(a1)
MERGE (f8)-[:READS]->(a3)
MERGE (f8)-[:READS]->(a4)
MERGE (f8)-[:CALLS]->(f9)
MERGE (f8)-[:CALLS]->(f10)
MERGE (f8)-[:PRODUCES]->(a5)
MERGE (f8)-[:PRODUCES]->(a6)
MERGE (f8)-[:USES]->(c3)
MERGE (f8)-[:USES]->(c5)
MERGE (f8)-[:USES]->(c6)
MERGE (f10)-[:CALLS]->(f11)
MERGE (f10)-[:CALLS]->(f12)
MERGE (f10)-[:CALLS]->(f13)
MERGE (f10)-[:CALLS]->(f14)
MERGE (f10)-[:CALLS]->(f15)
MERGE (f10)-[:IMPLEMENTS]->(c4)
MERGE (f15)-[:PRODUCES]->(a7)
MERGE (a6)-[:HAS_SUBARTIFACT]->(a7);

// BLOCK 8
MERGE (f16:Logic:Function {id:'build_canonical_reference'}) SET f16.name='build_canonical_reference';
MERGE (f17:Logic:Function {id:'build_solver_candidate'}) SET f17.name='build_solver_candidate';
MERGE (f18:Logic:Function {id:'compile_executable_plan'}) SET f18.name='compile_executable_plan';
MERGE (f19:Logic:Function {id:'_compile_problem_graph_plan'}) SET f19.name='_compile_problem_graph_plan';
MERGE (f20:Logic:Function {id:'execute_plan'}) SET f20.name='execute_plan';
MERGE (f21:Logic:Function {id:'_render_solution_text'}) SET f21.name='_render_solution_text';
MATCH (m5:Logic:Module {id:'runtime.compiler'})
MATCH (m6:Logic:Module {id:'runtime.solver'})
MATCH (a6:Logic:Artifact {id:'formalized_problem'})
MATCH (a8:Logic:Artifact {id:'executable_plan'})
MATCH (a9:Logic:Artifact {id:'execution_trace'})
MATCH (a10:Logic:Artifact {id:'canonical_reference'})
MERGE (m6)-[:DEFINES]->(f16)
MERGE (m6)-[:DEFINES]->(f17)
MERGE (m5)-[:DEFINES]->(f18)
MERGE (m5)-[:DEFINES]->(f19)
MERGE (m6)-[:DEFINES]->(f21)
MERGE (f16)-[:READS]->(a6)
MERGE (f16)-[:CALLS]->(f17)
MERGE (f16)-[:CALLS]->(f18)
MERGE (f16)-[:CALLS]->(f20)
MERGE (f16)-[:CALLS]->(f21)
MERGE (f16)-[:PRODUCES]->(a10)
MERGE (f18)-[:READS]->(a6)
MERGE (f18)-[:CALLS]->(f19)
MERGE (f18)-[:PRODUCES]->(a8)
MERGE (f20)-[:READS]->(a8)
MERGE (f20)-[:PRODUCES]->(a9)
MERGE (a10)-[:HAS_SUBARTIFACT]->(a8)
MERGE (a10)-[:HAS_SUBARTIFACT]->(a9);

// BLOCK 9
MERGE (f22:Logic:Function {id:'formalize_student_work'}) SET f22.name='formalize_student_work';
MERGE (f23:Logic:Function {id:'_heuristic_formalize_student_work'}) SET f23.name='_heuristic_formalize_student_work';
MERGE (f24:Logic:Function {id:'_extract_final_answer'}) SET f24.name='_extract_final_answer';
MERGE (f25:Logic:Function {id:'_split_student_steps'}) SET f25.name='_split_student_steps';
MERGE (f26:Logic:Function {id:'_build_step_attempts'}) SET f26.name='_build_step_attempts';
MERGE (f27:Logic:Function {id:'_infer_mode'}) SET f27.name='_infer_mode';
MERGE (f28:Logic:Function {id:'_infer_selected_target_ref'}) SET f28.name='_infer_selected_target_ref';
MERGE (f29:Logic:Function {id:'_attach_student_graph'}) SET f29.name='_attach_student_graph';
MERGE (f30:Logic:Function {id:'_llm_formalize_student_work'}) SET f30.name='_llm_formalize_student_work';
MERGE (f31:Logic:Function {id:'_build_llm_student_prompt'}) SET f31.name='_build_llm_student_prompt';
MERGE (f32:Logic:Function {id:'_build_student_work_from_sketch'}) SET f32.name='_build_student_work_from_sketch';
MERGE (f33:Logic:Function {id:'_reconcile_student_mode'}) SET f33.name='_reconcile_student_mode';
MERGE (f34:Logic:Function {id:'_repair_selected_target_ref'}) SET f34.name='_repair_selected_target_ref';
MERGE (f35:Logic:Function {id:'_prune_student_semantic_facts'}) SET f35.name='_prune_student_semantic_facts';
MERGE (f36:Logic:Function {id:'_build_student_steps_from_sketch'}) SET f36.name='_build_student_steps_from_sketch';
MATCH (m7:Logic:Module {id:'formalizer.student_entry'})
MATCH (m8:Logic:Module {id:'formalizer.student_builder'})
MATCH (m9:Logic:Module {id:'formalizer.student_llm'})
MATCH (a2:Logic:Artifact {id:'student_answer'})
MATCH (a6:Logic:Artifact {id:'formalized_problem'})
MATCH (a10:Logic:Artifact {id:'canonical_reference'})
MATCH (a11:Logic:Artifact {id:'heuristic_student_state'})
MATCH (a12:Logic:Artifact {id:'student_semantic_sketch'})
MATCH (a13:Logic:Artifact {id:'student_work'})
MATCH (a14:Logic:Artifact {id:'student_graph'})
MATCH (c1:Logic:Concept {id:'heuristic_anchor'})
MATCH (c3:Logic:Concept {id:'semantic_sketch'})
MATCH (c4:Logic:Concept {id:'local_compile'})
MATCH (c5:Logic:Concept {id:'validation_retry'})
MATCH (c6:Logic:Concept {id:'fallback'})
MERGE (m7)-[:DEFINES]->(f22)
MERGE (m8)-[:DEFINES]->(f23)
MERGE (m8)-[:DEFINES]->(f24)
MERGE (m8)-[:DEFINES]->(f25)
MERGE (m8)-[:DEFINES]->(f26)
MERGE (m8)-[:DEFINES]->(f27)
MERGE (m8)-[:DEFINES]->(f28)
MERGE (m8)-[:DEFINES]->(f29)
MERGE (m9)-[:DEFINES]->(f30)
MERGE (m9)-[:DEFINES]->(f31)
MERGE (m8)-[:DEFINES]->(f32)
MERGE (m8)-[:DEFINES]->(f33)
MERGE (m8)-[:DEFINES]->(f34)
MERGE (m8)-[:DEFINES]->(f35)
MERGE (m8)-[:DEFINES]->(f36)
MERGE (f22)-[:READS]->(a2)
MERGE (f22)-[:READS]->(a6)
MERGE (f22)-[:READS]->(a10)
MERGE (f22)-[:CALLS]->(f23)
MERGE (f22)-[:CALLS]->(f30)
MERGE (f22)-[:CAN_FALLBACK_TO]->(a11)
MERGE (f23)-[:CALLS]->(f24)
MERGE (f23)-[:CALLS]->(f25)
MERGE (f23)-[:CALLS]->(f26)
MERGE (f23)-[:CALLS]->(f27)
MERGE (f23)-[:CALLS]->(f28)
MERGE (f23)-[:CALLS]->(f29)
MERGE (f23)-[:PRODUCES]->(a11)
MERGE (f23)-[:IMPLEMENTS]->(c1)
MERGE (f30)-[:READS]->(a2)
MERGE (f30)-[:READS]->(a6)
MERGE (f30)-[:READS]->(a10)
MERGE (f30)-[:READS]->(a11)
MERGE (f30)-[:CALLS]->(f31)
MERGE (f30)-[:CALLS]->(f32)
MERGE (f30)-[:PRODUCES]->(a12)
MERGE (f30)-[:PRODUCES]->(a13)
MERGE (f30)-[:USES]->(c3)
MERGE (f30)-[:USES]->(c5)
MERGE (f30)-[:USES]->(c6)
MERGE (f32)-[:CALLS]->(f36)
MERGE (f32)-[:CALLS]->(f35)
MERGE (f32)-[:CALLS]->(f34)
MERGE (f32)-[:CALLS]->(f33)
MERGE (f32)-[:CALLS]->(f29)
MERGE (f32)-[:IMPLEMENTS]->(c4)
MERGE (f29)-[:PRODUCES]->(a14)
MERGE (a13)-[:HAS_SUBARTIFACT]->(a14);

// BLOCK 10
MERGE (f37:Logic:Function {id:'build_diagnosis_evidence'}) SET f37.name='build_diagnosis_evidence';
MERGE (f38:Logic:Function {id:'reference_steps'}) SET f38.name='reference_steps';
MERGE (f39:Logic:Function {id:'student_steps'}) SET f39.name='student_steps';
MERGE (f40:Logic:Function {id:'global_align_student_steps'}) SET f40.name='global_align_student_steps';
MERGE (f41:Logic:Function {id:'infer_student_target_ref'}) SET f41.name='infer_student_target_ref';
MERGE (f42:Logic:Function {id:'student_graph_has_target_path'}) SET f42.name='student_graph_has_target_path';
MERGE (f43:Logic:Function {id:'graph_edit_summary'}) SET f43.name='graph_edit_summary';
MATCH (m10:Logic:Module {id:'evidence.builder'})
MATCH (m11:Logic:Module {id:'evidence.alignment'})
MATCH (a6:Logic:Artifact {id:'formalized_problem'})
MATCH (a10:Logic:Artifact {id:'canonical_reference'})
MATCH (a13:Logic:Artifact {id:'student_work'})
MATCH (a15:Logic:Artifact {id:'diagnosis_evidence'})
MATCH (c7:Logic:Concept {id:'global_alignment'})
MERGE (m10)-[:DEFINES]->(f37)
MERGE (m11)-[:DEFINES]->(f38)
MERGE (m11)-[:DEFINES]->(f39)
MERGE (m11)-[:DEFINES]->(f40)
MERGE (m11)-[:DEFINES]->(f41)
MERGE (m11)-[:DEFINES]->(f42)
MERGE (m11)-[:DEFINES]->(f43)
MERGE (f37)-[:READS]->(a6)
MERGE (f37)-[:READS]->(a10)
MERGE (f37)-[:READS]->(a13)
MERGE (f37)-[:CALLS]->(f38)
MERGE (f37)-[:CALLS]->(f39)
MERGE (f37)-[:CALLS]->(f40)
MERGE (f37)-[:CALLS]->(f41)
MERGE (f37)-[:CALLS]->(f42)
MERGE (f37)-[:CALLS]->(f43)
MERGE (f37)-[:IMPLEMENTS]->(c7)
MERGE (f37)-[:PRODUCES]->(a15);

// BLOCK 11
MERGE (f44:Logic:Function {id:'diagnose'}) SET f44.name='diagnose';
MERGE (f45:Logic:Function {id:'_deterministic_diagnosis'}) SET f45.name='_deterministic_diagnosis';
MERGE (f46:Logic:Function {id:'_llm_diagnose'}) SET f46.name='_llm_diagnose';
MERGE (f47:Logic:Function {id:'build_diagnosis_hypotheses'}) SET f47.name='build_diagnosis_hypotheses';
MERGE (f48:Logic:Function {id:'_score_correct_answer'}) SET f48.name='_score_correct_answer';
MERGE (f49:Logic:Function {id:'_score_unparseable_answer'}) SET f49.name='_score_unparseable_answer';
MERGE (f50:Logic:Function {id:'_score_target_misunderstanding'}) SET f50.name='_score_target_misunderstanding';
MERGE (f51:Logic:Function {id:'_score_arithmetic_error'}) SET f51.name='_score_arithmetic_error';
MERGE (f52:Logic:Function {id:'_score_quantity_relation_error'}) SET f52.name='_score_quantity_relation_error';
MERGE (f53:Logic:Function {id:'_score_unknown_error'}) SET f53.name='_score_unknown_error';
MATCH (m12:Logic:Module {id:'diagnosis.engine'})
MATCH (m13:Logic:Module {id:'diagnosis.scoring'})
MATCH (a15:Logic:Artifact {id:'diagnosis_evidence'})
MATCH (a16:Logic:Artifact {id:'diagnosis_result'})
MATCH (c8:Logic:Concept {id:'deterministic_scoring'})
MERGE (m12)-[:DEFINES]->(f44)
MERGE (m12)-[:DEFINES]->(f45)
MERGE (m12)-[:DEFINES]->(f46)
MERGE (m13)-[:DEFINES]->(f47)
MERGE (m13)-[:DEFINES]->(f48)
MERGE (m13)-[:DEFINES]->(f49)
MERGE (m13)-[:DEFINES]->(f50)
MERGE (m13)-[:DEFINES]->(f51)
MERGE (m13)-[:DEFINES]->(f52)
MERGE (m13)-[:DEFINES]->(f53)
MERGE (f44)-[:READS]->(a15)
MERGE (f44)-[:CALLS]->(f45)
MERGE (f44)-[:CALLS]->(f46)
MERGE (f44)-[:PRODUCES]->(a16)
MERGE (f45)-[:CALLS]->(f47)
MERGE (f45)-[:IMPLEMENTS]->(c8)
MERGE (f47)-[:CALLS]->(f48)
MERGE (f47)-[:CALLS]->(f49)
MERGE (f47)-[:CALLS]->(f50)
MERGE (f47)-[:CALLS]->(f51)
MERGE (f47)-[:CALLS]->(f52)
MERGE (f47)-[:CALLS]->(f53);

// BLOCK 12
MERGE (f54:Logic:Function {id:'build_hint_plan'}) SET f54.name='build_hint_plan';
MERGE (f55:Logic:Function {id:'_plan_for_correct_answer'}) SET f55.name='_plan_for_correct_answer';
MERGE (f56:Logic:Function {id:'_plan_for_unparseable'}) SET f56.name='_plan_for_unparseable';
MERGE (f57:Logic:Function {id:'_plan_for_target_misunderstanding'}) SET f57.name='_plan_for_target_misunderstanding';
MERGE (f58:Logic:Function {id:'_plan_for_quantity_relation_error'}) SET f58.name='_plan_for_quantity_relation_error';
MERGE (f59:Logic:Function {id:'_plan_for_arithmetic_error'}) SET f59.name='_plan_for_arithmetic_error';
MERGE (f60:Logic:Function {id:'_plan_for_unknown'}) SET f60.name='_plan_for_unknown';
MERGE (f61:Logic:Function {id:'build_hint_result'}) SET f61.name='build_hint_result';
MERGE (f62:Logic:Function {id:'generate_hint_text'}) SET f62.name='generate_hint_text';
MERGE (f63:Logic:Function {id:'_deterministic_hint_text'}) SET f63.name='_deterministic_hint_text';
MERGE (f64:Logic:Function {id:'_llm_hint_text'}) SET f64.name='_llm_hint_text';
MERGE (f65:Logic:Function {id:'verify_hint_text'}) SET f65.name='verify_hint_text';
MERGE (f66:Logic:Function {id:'check_no_spoiler'}) SET f66.name='check_no_spoiler';
MERGE (f67:Logic:Function {id:'check_alignment'}) SET f67.name='check_alignment';
MERGE (f68:Logic:Function {id:'repair_hint_text'}) SET f68.name='repair_hint_text';
MATCH (m14:Logic:Module {id:'pedagogy.planner'})
MATCH (m15:Logic:Module {id:'hint.controller'})
MATCH (m16:Logic:Module {id:'hint.generator'})
MATCH (m17:Logic:Module {id:'hint.verifier'})
MATCH (m18:Logic:Module {id:'hint.repair'})
MATCH (a6:Logic:Artifact {id:'formalized_problem'})
MATCH (a10:Logic:Artifact {id:'canonical_reference'})
MATCH (a16:Logic:Artifact {id:'diagnosis_result'})
MATCH (a17:Logic:Artifact {id:'hint_plan'})
MATCH (a18:Logic:Artifact {id:'hint_text'})
MATCH (a19:Logic:Artifact {id:'hint_result'})
MATCH (c9:Logic:Concept {id:'pedagogical_planning'})
MATCH (c10:Logic:Concept {id:'hint_verification'})
MERGE (m14)-[:DEFINES]->(f54)
MERGE (m14)-[:DEFINES]->(f55)
MERGE (m14)-[:DEFINES]->(f56)
MERGE (m14)-[:DEFINES]->(f57)
MERGE (m14)-[:DEFINES]->(f58)
MERGE (m14)-[:DEFINES]->(f59)
MERGE (m14)-[:DEFINES]->(f60)
MERGE (m15)-[:DEFINES]->(f61)
MERGE (m16)-[:DEFINES]->(f62)
MERGE (m16)-[:DEFINES]->(f63)
MERGE (m16)-[:DEFINES]->(f64)
MERGE (m17)-[:DEFINES]->(f65)
MERGE (m17)-[:DEFINES]->(f66)
MERGE (m17)-[:DEFINES]->(f67)
MERGE (m18)-[:DEFINES]->(f68)
MERGE (f54)-[:READS]->(a6)
MERGE (f54)-[:READS]->(a10)
MERGE (f54)-[:READS]->(a16)
MERGE (f54)-[:CALLS]->(f55)
MERGE (f54)-[:CALLS]->(f56)
MERGE (f54)-[:CALLS]->(f57)
MERGE (f54)-[:CALLS]->(f58)
MERGE (f54)-[:CALLS]->(f59)
MERGE (f54)-[:CALLS]->(f60)
MERGE (f54)-[:PRODUCES]->(a17)
MERGE (f54)-[:IMPLEMENTS]->(c9)
MERGE (f61)-[:READS]->(a6)
MERGE (f61)-[:READS]->(a10)
MERGE (f61)-[:READS]->(a16)
MERGE (f61)-[:READS]->(a17)
MERGE (f61)-[:CALLS]->(f62)
MERGE (f61)-[:CALLS]->(f65)
MERGE (f61)-[:CALLS]->(f68)
MERGE (f61)-[:PRODUCES]->(a19)
MERGE (f62)-[:CALLS]->(f63)
MERGE (f62)-[:CALLS]->(f64)
MERGE (f62)-[:PRODUCES]->(a18)
MERGE (f65)-[:CALLS]->(f66)
MERGE (f65)-[:CALLS]->(f67)
MERGE (f65)-[:IMPLEMENTS]->(c10);

// BLOCK 13
// Run these manually after loading:
// MATCH (n:Logic) OPTIONAL MATCH (n)-[r]->(m:Logic) RETURN n,r,m
// MATCH p=(:Logic:Function {id:'formalize_problem'})-[:CALLS*1..4]->(n:Logic:Function) RETURN p
// MATCH p=(:Logic:Function {id:'formalize_student_work'})-[:CALLS*1..5]->(n:Logic:Function) RETURN p
// MATCH p=(s:Logic:Stage)-[:HAS_MODULE]->(m:Logic:Module)-[:DEFINES]->(f:Logic:Function) RETURN p
// MATCH (f:Logic:Function)-[r:READS|PRODUCES|HAS_SUBARTIFACT]->(a:Logic:Artifact) RETURN f,r,a
// MATCH (f:Logic:Function)-[r:IMPLEMENTS|USES]->(c:Logic:Concept) RETURN f,r,c

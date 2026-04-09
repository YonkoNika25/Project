// Neo4j Browser-friendly script.
// Run ONE BLOCK AT A TIME, from top to bottom.
// Do not highlight and run the whole file at once.

// ===================================================================
// BLOCK 1. RESET ONLY THE DEMO GRAPH
// ===================================================================

MATCH (n:Demo)
DETACH DELETE n;


// ===================================================================
// BLOCK 2. STATIC PIPELINE MODULES
// ===================================================================

MERGE (pipeline:Demo:Pipeline {id: 'tutoring_pipeline'})
SET pipeline.name = 'Tutoring Pipeline';

MERGE (m1:Demo:Module {id: 'formalize_problem'})
SET m1.name = 'formalize_problem',
    m1.order = 1,
    m1.description = 'Turn problem_text into a structured FormalizedProblem';

MERGE (m2:Demo:Module {id: 'build_canonical_reference'})
SET m2.name = 'build_canonical_reference',
    m2.order = 2,
    m2.description = 'Compile and execute the problem structure to produce the internal reference solution';

MERGE (m3:Demo:Module {id: 'formalize_student_work'})
SET m3.name = 'formalize_student_work',
    m3.order = 3,
    m3.description = 'Turn the student answer into a structured StudentWorkState';

MERGE (m4:Demo:Module {id: 'build_diagnosis_evidence'})
SET m4.name = 'build_diagnosis_evidence',
    m4.order = 4,
    m4.description = 'Compare reference and student work to produce evidence';

MERGE (m5:Demo:Module {id: 'diagnose'})
SET m5.name = 'diagnose',
    m5.order = 5,
    m5.description = 'Turn evidence into a diagnosis label and localization';

MERGE (m6:Demo:Module {id: 'build_hint_plan'})
SET m6.name = 'build_hint_plan',
    m6.order = 6,
    m6.description = 'Convert diagnosis into a pedagogical plan';

MERGE (m7:Demo:Module {id: 'build_hint_result'})
SET m7.name = 'build_hint_result',
    m7.order = 7,
    m7.description = 'Generate and verify the final hint text';

MERGE (pipeline)-[:HAS_STAGE]->(m1)
MERGE (pipeline)-[:HAS_STAGE]->(m2)
MERGE (pipeline)-[:HAS_STAGE]->(m3)
MERGE (pipeline)-[:HAS_STAGE]->(m4)
MERGE (pipeline)-[:HAS_STAGE]->(m5)
MERGE (pipeline)-[:HAS_STAGE]->(m6)
MERGE (pipeline)-[:HAS_STAGE]->(m7);


// ===================================================================
// BLOCK 3. STATIC PIPELINE ORDER
// ===================================================================

MATCH (m1:Demo:Module {id: 'formalize_problem'})
MATCH (m2:Demo:Module {id: 'build_canonical_reference'})
MATCH (m3:Demo:Module {id: 'formalize_student_work'})
MATCH (m4:Demo:Module {id: 'build_diagnosis_evidence'})
MATCH (m5:Demo:Module {id: 'diagnose'})
MATCH (m6:Demo:Module {id: 'build_hint_plan'})
MATCH (m7:Demo:Module {id: 'build_hint_result'})
MERGE (m1)-[:NEXT_STAGE]->(m2)
MERGE (m2)-[:NEXT_STAGE]->(m3)
MERGE (m3)-[:NEXT_STAGE]->(m4)
MERGE (m4)-[:NEXT_STAGE]->(m5)
MERGE (m5)-[:NEXT_STAGE]->(m6)
MERGE (m6)-[:NEXT_STAGE]->(m7);


// ===================================================================
// BLOCK 4. STATIC ARTIFACT TYPES
// ===================================================================

MERGE (t_problem_text:Demo:ArtifactType {id: 'problem_text'})
SET t_problem_text.name = 'problem_text',
    t_problem_text.description = 'Raw problem statement';

MERGE (t_student_answer:Demo:ArtifactType {id: 'student_answer'})
SET t_student_answer.name = 'student_answer',
    t_student_answer.description = 'Raw student answer text';

MERGE (t_problem:Demo:ArtifactType {id: 'formalized_problem'})
SET t_problem.name = 'FormalizedProblem',
    t_problem.description = 'Structured representation of the problem';

MERGE (t_reference:Demo:ArtifactType {id: 'canonical_reference'})
SET t_reference.name = 'CanonicalReference',
    t_reference.description = 'Internal executable reference solution';

MERGE (t_student_work:Demo:ArtifactType {id: 'student_work'})
SET t_student_work.name = 'StudentWorkState',
    t_student_work.description = 'Structured representation of the student answer';

MERGE (t_evidence:Demo:ArtifactType {id: 'diagnosis_evidence'})
SET t_evidence.name = 'DiagnosisEvidence',
    t_evidence.description = 'Evidence produced by comparing reference and student work';

MERGE (t_diagnosis:Demo:ArtifactType {id: 'diagnosis_result'})
SET t_diagnosis.name = 'DiagnosisResult',
    t_diagnosis.description = 'Final diagnosis label and localization';

MERGE (t_hint_plan:Demo:ArtifactType {id: 'hint_plan'})
SET t_hint_plan.name = 'HintPlan',
    t_hint_plan.description = 'Pedagogical plan for hint generation';

MERGE (t_hint_result:Demo:ArtifactType {id: 'hint_result'})
SET t_hint_result.name = 'HintResult',
    t_hint_result.description = 'Final hint returned by the system';


// ===================================================================
// BLOCK 5. STATIC INPUT/OUTPUT RELATIONS
// ===================================================================

MATCH (m1:Demo:Module {id: 'formalize_problem'})
MATCH (m2:Demo:Module {id: 'build_canonical_reference'})
MATCH (m3:Demo:Module {id: 'formalize_student_work'})
MATCH (m4:Demo:Module {id: 'build_diagnosis_evidence'})
MATCH (m5:Demo:Module {id: 'diagnose'})
MATCH (m6:Demo:Module {id: 'build_hint_plan'})
MATCH (m7:Demo:Module {id: 'build_hint_result'})
MATCH (t_problem_text:Demo:ArtifactType {id: 'problem_text'})
MATCH (t_student_answer:Demo:ArtifactType {id: 'student_answer'})
MATCH (t_problem:Demo:ArtifactType {id: 'formalized_problem'})
MATCH (t_reference:Demo:ArtifactType {id: 'canonical_reference'})
MATCH (t_student_work:Demo:ArtifactType {id: 'student_work'})
MATCH (t_evidence:Demo:ArtifactType {id: 'diagnosis_evidence'})
MATCH (t_diagnosis:Demo:ArtifactType {id: 'diagnosis_result'})
MATCH (t_hint_plan:Demo:ArtifactType {id: 'hint_plan'})
MATCH (t_hint_result:Demo:ArtifactType {id: 'hint_result'})
MERGE (t_problem_text)-[:INPUT_TO]->(m1)
MERGE (m1)-[:OUTPUT_TYPE]->(t_problem)
MERGE (t_problem)-[:INPUT_TO]->(m2)
MERGE (m2)-[:OUTPUT_TYPE]->(t_reference)
MERGE (t_student_answer)-[:INPUT_TO]->(m3)
MERGE (t_problem)-[:INPUT_TO]->(m3)
MERGE (t_reference)-[:INPUT_TO]->(m3)
MERGE (m3)-[:OUTPUT_TYPE]->(t_student_work)
MERGE (t_problem)-[:INPUT_TO]->(m4)
MERGE (t_reference)-[:INPUT_TO]->(m4)
MERGE (t_student_work)-[:INPUT_TO]->(m4)
MERGE (m4)-[:OUTPUT_TYPE]->(t_evidence)
MERGE (t_evidence)-[:INPUT_TO]->(m5)
MERGE (m5)-[:OUTPUT_TYPE]->(t_diagnosis)
MERGE (t_problem)-[:INPUT_TO]->(m6)
MERGE (t_reference)-[:INPUT_TO]->(m6)
MERGE (t_diagnosis)-[:INPUT_TO]->(m6)
MERGE (m6)-[:OUTPUT_TYPE]->(t_hint_plan)
MERGE (t_problem)-[:INPUT_TO]->(m7)
MERGE (t_reference)-[:INPUT_TO]->(m7)
MERGE (t_diagnosis)-[:INPUT_TO]->(m7)
MERGE (t_hint_plan)-[:INPUT_TO]->(m7)
MERGE (m7)-[:OUTPUT_TYPE]->(t_hint_result);


// ===================================================================
// BLOCK 6. DEMO RUN HEADER (847 EXAMPLE)
// ===================================================================

MERGE (run:Demo:PipelineRun {run_id: 'demo_847'})
SET run.title = '847 monster example',
    run.source = 'debug_formalizer.py + debug_student_work.py';

MERGE (a_problem_text:Demo:Artifact {id: 'demo_847_problem_text'})
SET a_problem_text.kind = 'problem_text',
    a_problem_text.summary = 'Raw word problem about 847 total people across 3 ships with doubling sizes';

MERGE (a_student_answer:Demo:Artifact {id: 'demo_847_student_answer'})
SET a_student_answer.kind = 'student_answer',
    a_student_answer.summary = 'Student sets x, forms x + 2x + 4x = 847, then answers 117';

MERGE (run)-[:HAS_INPUT]->(a_problem_text)
MERGE (run)-[:HAS_INPUT]->(a_student_answer);


// ===================================================================
// BLOCK 7. DEMO RUN EXECUTION STEPS
// ===================================================================

MERGE (e1:Demo:Execution {id: 'demo_847_step_1'})
SET e1.order = 1, e1.name = 'formalize_problem';

MERGE (e2:Demo:Execution {id: 'demo_847_step_2'})
SET e2.order = 2, e2.name = 'build_canonical_reference';

MERGE (e3:Demo:Execution {id: 'demo_847_step_3'})
SET e3.order = 3, e3.name = 'formalize_student_work';

MERGE (e4:Demo:Execution {id: 'demo_847_step_4'})
SET e4.order = 4, e4.name = 'build_diagnosis_evidence';

MERGE (e5:Demo:Execution {id: 'demo_847_step_5'})
SET e5.order = 5, e5.name = 'diagnose';

MERGE (e6:Demo:Execution {id: 'demo_847_step_6'})
SET e6.order = 6, e6.name = 'build_hint_plan';

MERGE (e7:Demo:Execution {id: 'demo_847_step_7'})
SET e7.order = 7, e7.name = 'build_hint_result';

MERGE (run)-[:HAS_STEP]->(e1)
MERGE (run)-[:HAS_STEP]->(e2)
MERGE (run)-[:HAS_STEP]->(e3)
MERGE (run)-[:HAS_STEP]->(e4)
MERGE (run)-[:HAS_STEP]->(e5)
MERGE (run)-[:HAS_STEP]->(e6)
MERGE (run)-[:HAS_STEP]->(e7);


// ===================================================================
// BLOCK 8. DEMO RUN MODULE LINKS + ORDER
// ===================================================================

MATCH (e1:Demo:Execution {id: 'demo_847_step_1'})
MATCH (e2:Demo:Execution {id: 'demo_847_step_2'})
MATCH (e3:Demo:Execution {id: 'demo_847_step_3'})
MATCH (e4:Demo:Execution {id: 'demo_847_step_4'})
MATCH (e5:Demo:Execution {id: 'demo_847_step_5'})
MATCH (e6:Demo:Execution {id: 'demo_847_step_6'})
MATCH (e7:Demo:Execution {id: 'demo_847_step_7'})
MATCH (m1:Demo:Module {id: 'formalize_problem'})
MATCH (m2:Demo:Module {id: 'build_canonical_reference'})
MATCH (m3:Demo:Module {id: 'formalize_student_work'})
MATCH (m4:Demo:Module {id: 'build_diagnosis_evidence'})
MATCH (m5:Demo:Module {id: 'diagnose'})
MATCH (m6:Demo:Module {id: 'build_hint_plan'})
MATCH (m7:Demo:Module {id: 'build_hint_result'})
MERGE (e1)-[:USES_MODULE]->(m1)
MERGE (e2)-[:USES_MODULE]->(m2)
MERGE (e3)-[:USES_MODULE]->(m3)
MERGE (e4)-[:USES_MODULE]->(m4)
MERGE (e5)-[:USES_MODULE]->(m5)
MERGE (e6)-[:USES_MODULE]->(m6)
MERGE (e7)-[:USES_MODULE]->(m7)
MERGE (e1)-[:NEXT_EXECUTION]->(e2)
MERGE (e2)-[:NEXT_EXECUTION]->(e3)
MERGE (e3)-[:NEXT_EXECUTION]->(e4)
MERGE (e4)-[:NEXT_EXECUTION]->(e5)
MERGE (e5)-[:NEXT_EXECUTION]->(e6)
MERGE (e6)-[:NEXT_EXECUTION]->(e7);


// ===================================================================
// BLOCK 9. DEMO RUN OUTPUT ARTIFACTS
// ===================================================================

MERGE (a_problem:Demo:Artifact {id: 'demo_847_formalized_problem'})
SET a_problem.kind = 'FormalizedProblem',
    a_problem.summary = 'Problem formalized as total 847 with target = first ship size, relation total / 7',
    a_problem.provenance = 'llm',
    a_problem.key_outputs = 'quantity_1=847; total_multiplier=7; target=first hundred years';

MERGE (a_reference:Demo:Artifact {id: 'demo_847_reference'})
SET a_reference.kind = 'CanonicalReference',
    a_reference.summary = 'Executable internal reference built successfully',
    a_reference.final_answer = '121.0';

MERGE (a_student_work:Demo:Artifact {id: 'demo_847_student_work'})
SET a_student_work.kind = 'StudentWorkState',
    a_student_work.summary = 'Student trace parsed successfully; normalized final answer is 117.0',
    a_student_work.mode = 'full_trace',
    a_student_work.final_answer = '117.0',
    a_student_work.target_ref = 'how_many_people_were_on_the_ship_the_monster_ate_in_the_first_hundred_years';

MERGE (a_evidence:Demo:Artifact {id: 'demo_847_evidence'})
SET a_evidence.kind = 'DiagnosisEvidence',
    a_evidence.summary = 'Evidence compares reference final 121.0 with student final 117.0 and aligns trace structure';

MERGE (a_diagnosis:Demo:Artifact {id: 'demo_847_diagnosis'})
SET a_diagnosis.kind = 'DiagnosisResult',
    a_diagnosis.summary = 'Diagnosis stage consumes evidence and decides the error type for the 847 example';

MERGE (a_hint_plan:Demo:Artifact {id: 'demo_847_hint_plan'})
SET a_hint_plan.kind = 'HintPlan',
    a_hint_plan.summary = 'Pedagogical plan for how to hint without revealing the answer';

MERGE (a_hint_result:Demo:Artifact {id: 'demo_847_hint_result'})
SET a_hint_result.kind = 'HintResult',
    a_hint_result.summary = 'Final hint text returned to the learner';


// ===================================================================
// BLOCK 10. DEMO RUN DATA FLOW
// ===================================================================

MATCH (a_problem_text:Demo:Artifact {id: 'demo_847_problem_text'})
MATCH (a_student_answer:Demo:Artifact {id: 'demo_847_student_answer'})
MATCH (a_problem:Demo:Artifact {id: 'demo_847_formalized_problem'})
MATCH (a_reference:Demo:Artifact {id: 'demo_847_reference'})
MATCH (a_student_work:Demo:Artifact {id: 'demo_847_student_work'})
MATCH (a_evidence:Demo:Artifact {id: 'demo_847_evidence'})
MATCH (a_diagnosis:Demo:Artifact {id: 'demo_847_diagnosis'})
MATCH (a_hint_plan:Demo:Artifact {id: 'demo_847_hint_plan'})
MATCH (a_hint_result:Demo:Artifact {id: 'demo_847_hint_result'})
MATCH (e1:Demo:Execution {id: 'demo_847_step_1'})
MATCH (e2:Demo:Execution {id: 'demo_847_step_2'})
MATCH (e3:Demo:Execution {id: 'demo_847_step_3'})
MATCH (e4:Demo:Execution {id: 'demo_847_step_4'})
MATCH (e5:Demo:Execution {id: 'demo_847_step_5'})
MATCH (e6:Demo:Execution {id: 'demo_847_step_6'})
MATCH (e7:Demo:Execution {id: 'demo_847_step_7'})
MERGE (a_problem_text)-[:INPUT_TO]->(e1)
MERGE (e1)-[:OUTPUT]->(a_problem)
MERGE (a_problem)-[:INPUT_TO]->(e2)
MERGE (e2)-[:OUTPUT]->(a_reference)
MERGE (a_student_answer)-[:INPUT_TO]->(e3)
MERGE (a_problem)-[:INPUT_TO]->(e3)
MERGE (a_reference)-[:INPUT_TO]->(e3)
MERGE (e3)-[:OUTPUT]->(a_student_work)
MERGE (a_problem)-[:INPUT_TO]->(e4)
MERGE (a_reference)-[:INPUT_TO]->(e4)
MERGE (a_student_work)-[:INPUT_TO]->(e4)
MERGE (e4)-[:OUTPUT]->(a_evidence)
MERGE (a_evidence)-[:INPUT_TO]->(e5)
MERGE (e5)-[:OUTPUT]->(a_diagnosis)
MERGE (a_problem)-[:INPUT_TO]->(e6)
MERGE (a_reference)-[:INPUT_TO]->(e6)
MERGE (a_diagnosis)-[:INPUT_TO]->(e6)
MERGE (e6)-[:OUTPUT]->(a_hint_plan)
MERGE (a_problem)-[:INPUT_TO]->(e7)
MERGE (a_reference)-[:INPUT_TO]->(e7)
MERGE (a_diagnosis)-[:INPUT_TO]->(e7)
MERGE (a_hint_plan)-[:INPUT_TO]->(e7)
MERGE (e7)-[:OUTPUT]->(a_hint_result);


// ===================================================================
// BLOCK 11. SMALL DETAIL NODES FOR THE 847 EXAMPLE
// ===================================================================

MERGE (q1:Demo:Quantity {id: 'demo_847_q1'})
SET q1.quantity_id = 'quantity_1',
    q1.label = '847',
    q1.value = 847.0,
    q1.unit = 'people';

MERGE (q2:Demo:Quantity {id: 'demo_847_q2'})
SET q2.quantity_id = 'total_multiplier',
    q2.label = 'total_multiplier',
    q2.value = 7.0,
    q2.unit = 'dimensionless';

MERGE (target:Demo:Target {id: 'demo_847_target'})
SET target.target_variable = 'how_many_people_were_on_the_ship_the_monster_ate_in_the_first_hundred_years',
    target.unit = 'people';

MERGE (student_final:Demo:StudentFinal {id: 'demo_847_student_final'})
SET student_final.value = 117.0;

MERGE (reference_final:Demo:ReferenceFinal {id: 'demo_847_reference_final'})
SET reference_final.value = 121.0;

MATCH (a_problem:Demo:Artifact {id: 'demo_847_formalized_problem'})
MATCH (a_reference:Demo:Artifact {id: 'demo_847_reference'})
MATCH (a_student_work:Demo:Artifact {id: 'demo_847_student_work'})
MATCH (q1:Demo:Quantity {id: 'demo_847_q1'})
MATCH (q2:Demo:Quantity {id: 'demo_847_q2'})
MATCH (target:Demo:Target {id: 'demo_847_target'})
MATCH (student_final:Demo:StudentFinal {id: 'demo_847_student_final'})
MATCH (reference_final:Demo:ReferenceFinal {id: 'demo_847_reference_final'})
MERGE (a_problem)-[:HAS_QUANTITY]->(q1)
MERGE (a_problem)-[:HAS_QUANTITY]->(q2)
MERGE (a_problem)-[:HAS_TARGET]->(target)
MERGE (a_reference)-[:HAS_FINAL_ANSWER]->(reference_final)
MERGE (a_student_work)-[:HAS_FINAL_ANSWER]->(student_final)
MERGE (a_student_work)-[:TARGETS]->(target)
MERGE (student_final)-[:DIFFERS_FROM]->(reference_final);


// ===================================================================
// BLOCK 12. QUICK VIEW QUERY
// ===================================================================

MATCH (r:Demo:PipelineRun {run_id: 'demo_847'})-[rel]-(n:Demo)
RETURN r, rel, n;


import re
from copy import deepcopy

from src.diagnosis import diagnose
from src.evidence import build_diagnosis_context, build_diagnosis_evidence
from src.formalizer import formalize_problem, formalize_student_work
from src.hint import build_hint_result
from src.models import DiagnosisLabel, QuantitySemanticRole, StudentWorkMode, TraceOperation
from src.pedagogy import build_hint_plan
from src.pipeline import run_tutoring_pipeline
from src.runtime import build_canonical_reference, solve_problem


class FakeLLMClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self._pending_problem_commitment_payload = None
        self._pending_student_commitment_payload = None

    @staticmethod
    def _extract_block(user_prompt: str, marker: str, terminator: str) -> str:
        if marker not in user_prompt:
            return ""
        tail = user_prompt.split(marker, 1)[1]
        if terminator in tail:
            tail = tail.split(terminator, 1)[0]
        return tail.strip()

    @staticmethod
    def _parse_numeric_mentions(text: str) -> list[float]:
        values: list[float] = []
        for match in re.findall(r"-?\d[\d,]*\.?\d*", text):
            normalized = match.replace(",", "")
            try:
                values.append(float(normalized))
            except ValueError:
                continue
        return values

    def _consume(self, key: str):
        if key not in self.responses:
            raise KeyError(key)
        response = self.responses[key]
        if isinstance(response, list):
            if not response:
                raise AssertionError(f"No queued response left for task '{key}'")
            response = response.pop(0)
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)

    def _problem_payload_for_task(self, task_name: str, user_prompt: str):
        if task_name == "problem_formalizer_semantic_state":
            payload = self._consume("problem_formalizer")
            self._pending_problem_commitment_payload = deepcopy(payload)
        elif task_name == "problem_formalizer_executable_commitment":
            if self._pending_problem_commitment_payload is not None:
                payload = deepcopy(self._pending_problem_commitment_payload)
                self._pending_problem_commitment_payload = None
            else:
                payload = self._consume("problem_formalizer")
        else:
            raise KeyError(task_name)

        problem_text = self._extract_block(user_prompt, "Problem text:\n", "\n\nReturn one JSON object")
        numeric_mentions = self._parse_numeric_mentions(problem_text)
        default_observed_value = max(numeric_mentions) if numeric_mentions else 0.0

        target = deepcopy(payload.get("target", {}))
        relation = deepcopy(payload.get("relation", {}))
        plan_steps = [deepcopy(step) for step in payload.get("plan_steps", []) if isinstance(step, dict)]

        if task_name == "problem_formalizer_semantic_state":
            quantities = []
            seen_quantity_ids: set[str] = set()
            for raw_quantity in payload.get("quantity_annotations", []):
                quantity_id = raw_quantity.get("quantity_id")
                if not quantity_id or quantity_id in seen_quantity_ids:
                    continue
                seen_quantity_ids.add(quantity_id)
                quantities.append(
                    {
                        "quantity_id": quantity_id,
                        "surface_text": raw_quantity.get("surface_text") or str(quantity_id),
                        "value": float(raw_quantity.get("value", default_observed_value)),
                        "unit": raw_quantity.get("unit"),
                        "entity_id": raw_quantity.get("entity_id"),
                        "semantic_role": raw_quantity.get("semantic_role", "unknown"),
                        "is_target_candidate": bool(raw_quantity.get("is_target_candidate", False)),
                        "origin": raw_quantity.get("origin", "observed"),
                        "evidence_ref": quantity_id,
                        "grounding": raw_quantity.get("surface_text") or str(quantity_id),
                        "notes": list(raw_quantity.get("notes", [])),
                    }
                )
            for raw_fact in payload.get("semantic_facts", []):
                quantity_id = raw_fact.get("fact_id")
                if not quantity_id or quantity_id in seen_quantity_ids:
                    continue
                seen_quantity_ids.add(quantity_id)
                quantities.append(
                    {
                        "quantity_id": quantity_id,
                        "surface_text": raw_fact.get("surface_text") or raw_fact.get("label") or str(quantity_id),
                        "value": float(raw_fact.get("value", 0.0)),
                        "unit": raw_fact.get("unit"),
                        "entity_id": raw_fact.get("entity_id"),
                        "semantic_role": raw_fact.get("semantic_role", "intermediate"),
                        "is_target_candidate": bool(raw_fact.get("is_target_candidate", False)),
                        "origin": "latent" if str(quantity_id).startswith("latent_") else "derived",
                        "evidence_ref": None,
                        "grounding": raw_fact.get("grounding") or raw_fact.get("label") or str(quantity_id),
                        "notes": list(raw_fact.get("notes", [])),
                    }
                )
            for step in plan_steps:
                output_ref = step.get("output_ref")
                if (
                    isinstance(output_ref, str)
                    and output_ref
                    and output_ref not in seen_quantity_ids
                    and output_ref != target.get("target_variable")
                ):
                    seen_quantity_ids.add(output_ref)
                    quantities.append(
                        {
                            "quantity_id": output_ref,
                            "surface_text": output_ref,
                            "value": 0.0,
                            "unit": step.get("output_unit"),
                            "entity_id": None,
                            "semantic_role": "intermediate",
                            "is_target_candidate": output_ref == target.get("target_quantity_id"),
                            "origin": "derived",
                            "evidence_ref": None,
                            "grounding": step.get("label") or output_ref,
                            "notes": ["legacy_test_payload_derived_quantity"],
                        }
                    )

            return {
                "entities": [],
                "quantities": quantities,
                "semantic_structure": [],
                "target": {
                    "surface_text": target.get("surface_text", target.get("description", "target")),
                    "normalized_question": target.get("normalized_question"),
                    "target_variable": target.get("target_variable"),
                    "target_quantity_id": target.get("target_quantity_id"),
                    "entity_id": target.get("entity_id"),
                    "unit": target.get("unit"),
                    "description": target.get("description"),
                    "confidence": float(target.get("confidence", payload.get("confidence", 0.9))),
                },
                "relation": {
                    "relation_type": relation.get("relation_type", "unknown"),
                    "operation_hint": relation.get("operation_hint", "unknown"),
                    "source_quantity_ids": list(relation.get("source_quantity_ids", [])),
                    "target_variable": relation.get("target_variable") or target.get("target_variable"),
                    "rationale": relation.get("rationale"),
                    "confidence": float(relation.get("confidence", payload.get("confidence", 0.8))),
                },
                "confidence": float(payload.get("confidence", 0.9)),
                "notes": list(payload.get("notes", [])),
            }

        normalized_steps = []
        for step in plan_steps:
            normalized_step = deepcopy(step)
            expression = str(normalized_step.get("expression", "")).strip()
            if "=" in expression:
                normalized_step["expression"] = expression.split("=", 1)[1].strip()
            normalized_steps.append(normalized_step)
        return {
            "plan_steps": normalized_steps,
            "graph_target_node_id": payload.get("graph_target_node_id"),
            "graph_confidence": float(payload.get("graph_confidence", payload.get("confidence", 0.9))),
            "graph_notes": list(payload.get("graph_notes", [])),
            "assumptions": list(payload.get("assumptions", [])),
            "confidence": float(payload.get("confidence", 0.9)),
            "notes": list(payload.get("notes", [])),
        }

    def _student_payload_for_task(self, task_name: str):
        if task_name == "student_work_semantic_state":
            payload = self._consume("student_work_formalizer")
            self._pending_student_commitment_payload = deepcopy(payload)
        elif task_name == "student_work_trace_commitment":
            if self._pending_student_commitment_payload is not None:
                payload = deepcopy(self._pending_student_commitment_payload)
                self._pending_student_commitment_payload = None
            else:
                payload = self._consume("student_work_formalizer")
        else:
            raise KeyError(task_name)

        if task_name == "student_work_semantic_state":
            return {
                "final_answer": deepcopy(payload.get("final_answer", {})),
                "mode": payload.get("mode", "final_answer_only"),
                "target": deepcopy(payload.get("target", {})),
                "semantic_facts": deepcopy(payload.get("semantic_facts", [])),
                "confidence": float(payload.get("confidence", 0.9)),
                "notes": list(payload.get("notes", [])),
            }
        return {
            "trace_steps": deepcopy(payload.get("trace_steps", [])),
            "assumptions": list(payload.get("assumptions", [])),
            "confidence": float(payload.get("confidence", 0.9)),
            "notes": list(payload.get("notes", [])),
        }

    def _diagnosis_payload_for_task(self, task_name: str):
        if task_name == "diagnosis_state" and "diagnosis_state" in self.responses:
            return self._consume("diagnosis_state")
        if task_name == "diagnosis_state" and "diagnosis_interpretation" in self.responses:
            payload = self._consume("diagnosis_interpretation")
            label = payload.get("diagnosis_label")
            if label == "correct_answer":
                return {
                    "answer_acceptability": "acceptable",
                    "target_alignment": "aligned",
                    "process_equivalence": "canonical",
                    "intervention_required": False,
                    "verified_error_mechanisms": [],
                    "uncertain_concerns": [],
                    "candidate_localization": payload.get("localization", "none"),
                    "candidate_target_step_id": payload.get("candidate_target_step_id"),
                    "candidate_focus_step_ids": [],
                    "supporting_evidence_types": deepcopy(payload.get("supporting_evidence_types", [])),
                    "grounded_evidence": deepcopy(payload.get("grounded_evidence")),
                    "key_findings": deepcopy(payload.get("reasoning_points", [])),
                    "summary": payload.get("summary", ""),
                    "confidence": float(payload.get("confidence", 0.9)),
                    "notes": list(payload.get("notes", [])),
                }
            if label == "target_misunderstanding":
                return {
                    "answer_acceptability": "unacceptable",
                    "target_alignment": "misaligned",
                    "process_equivalence": "partial_or_noisy_but_acceptable",
                    "intervention_required": True,
                    "verified_error_mechanisms": ["wrong_target_selected"],
                    "uncertain_concerns": [],
                    "candidate_localization": payload.get("localization", "target_selection"),
                    "candidate_target_step_id": payload.get("candidate_target_step_id"),
                    "candidate_focus_step_ids": [],
                    "supporting_evidence_types": deepcopy(payload.get("supporting_evidence_types", [])),
                    "grounded_evidence": deepcopy(payload.get("grounded_evidence")),
                    "key_findings": deepcopy(payload.get("reasoning_points", [])),
                    "summary": payload.get("summary", ""),
                    "confidence": float(payload.get("confidence", 0.9)),
                    "notes": list(payload.get("notes", [])),
                }
            if label == "quantity_relation_error":
                return {
                    "answer_acceptability": "unacceptable",
                    "target_alignment": "aligned",
                    "process_equivalence": "inconsistent",
                    "intervention_required": True,
                    "verified_error_mechanisms": ["quantity_relationship_invalid"],
                    "uncertain_concerns": [],
                    "candidate_localization": payload.get("localization", "combining_quantities"),
                    "candidate_target_step_id": payload.get("candidate_target_step_id"),
                    "candidate_focus_step_ids": [],
                    "supporting_evidence_types": deepcopy(payload.get("supporting_evidence_types", [])),
                    "grounded_evidence": deepcopy(payload.get("grounded_evidence")),
                    "key_findings": deepcopy(payload.get("reasoning_points", [])),
                    "summary": payload.get("summary", ""),
                    "confidence": float(payload.get("confidence", 0.9)),
                    "notes": list(payload.get("notes", [])),
                }
            if label == "unparseable_answer":
                return {
                    "answer_acceptability": "unparseable",
                    "target_alignment": "unknown",
                    "process_equivalence": "unknown",
                    "intervention_required": True,
                    "verified_error_mechanisms": ["answer_not_numeric"],
                    "uncertain_concerns": [],
                    "candidate_localization": payload.get("localization", "unknown"),
                    "candidate_target_step_id": None,
                    "candidate_focus_step_ids": [],
                    "supporting_evidence_types": deepcopy(payload.get("supporting_evidence_types", [])),
                    "grounded_evidence": deepcopy(payload.get("grounded_evidence")),
                    "key_findings": deepcopy(payload.get("reasoning_points", [])),
                    "summary": payload.get("summary", ""),
                    "confidence": float(payload.get("confidence", 0.9)),
                    "notes": list(payload.get("notes", [])),
                }
            return {
                "answer_acceptability": "unacceptable",
                "target_alignment": "aligned",
                "process_equivalence": "inconsistent",
                "intervention_required": True,
                "verified_error_mechanisms": ["arithmetic_execution_invalid"],
                "uncertain_concerns": [],
                "candidate_localization": payload.get("localization", "final_computation"),
                "candidate_target_step_id": payload.get("candidate_target_step_id"),
                "candidate_focus_step_ids": [],
                "supporting_evidence_types": deepcopy(payload.get("supporting_evidence_types", [])),
                "grounded_evidence": deepcopy(payload.get("grounded_evidence")),
                "key_findings": deepcopy(payload.get("reasoning_points", [])),
                "summary": payload.get("summary", ""),
                "confidence": float(payload.get("confidence", 0.9)),
                "notes": list(payload.get("notes", [])),
            }
        raise KeyError(task_name)

    def _pedagogy_payload_for_task(self, task_name: str):
        if task_name == "pedagogy_state" and "pedagogy_state" in self.responses:
            return self._consume("pedagogy_state")
        if task_name == "pedagogy_state" and "hint_strategy" in self.responses:
            payload = self._consume("hint_strategy")
            teacher_move = payload.get("teacher_move")
            target_step_id = payload.get("target_step_id")
            disclosure_budget = int(payload.get("disclosure_budget", 1))
            if teacher_move == "restate_result":
                return {
                    "intervention_posture": "acknowledge_correct",
                    "primary_objective": "none",
                    "disclosure_policy": "none",
                    "step_grounding_requirement": "none",
                    "candidate_target_step_id": None,
                    "candidate_focus_step_ids": [],
                    "focus_semantics": [],
                    "uncertain_pedagogical_concerns": [],
                    "pedagogical_goal": payload.get("pedagogical_goal", ""),
                    "student_action": payload.get("student_action"),
                    "rationale": payload.get("rationale", ""),
                    "confidence": float(payload.get("confidence", 0.9)),
                    "notes": list(payload.get("notes", [])),
                }
            if teacher_move == "refocus_target":
                objective = "refocus_target"
            elif teacher_move == "check_relationship":
                objective = "repair_quantity_relationship"
            elif teacher_move in {"recompute_step", "continue_from_step"}:
                objective = "recompute_arithmetic"
            else:
                objective = "clarify_answer_format"
            disclosure_policy = "none" if disclosure_budget <= 0 else ("medium" if disclosure_budget >= 2 else "low")
            step_requirement = "required" if target_step_id else "none"
            return {
                "intervention_posture": "corrective",
                "primary_objective": objective,
                "disclosure_policy": disclosure_policy,
                "step_grounding_requirement": step_requirement,
                "candidate_target_step_id": target_step_id,
                "candidate_focus_step_ids": [target_step_id] if target_step_id else [],
                "focus_semantics": deepcopy(payload.get("focus_points", [])),
                "uncertain_pedagogical_concerns": [],
                "pedagogical_goal": payload.get("pedagogical_goal", ""),
                "student_action": payload.get("student_action"),
                "rationale": payload.get("rationale", ""),
                "confidence": float(payload.get("confidence", 0.9)),
                "notes": list(payload.get("notes", [])),
            }
        raise KeyError(task_name)

    def generate_json(
        self,
        task_name,
        system_prompt,
        user_prompt,
        temperature=0.0,
        max_tokens=1200,
    ):
        self.calls.append(task_name)
        if task_name in self.responses:
            return self._consume(task_name)
        if task_name == "diagnosis_state" and (
            "diagnosis_state" in self.responses or "diagnosis_interpretation" in self.responses
        ):
            return self._diagnosis_payload_for_task(task_name)
        if task_name == "pedagogy_state" and ("pedagogy_state" in self.responses or "hint_strategy" in self.responses):
            return self._pedagogy_payload_for_task(task_name)
        if task_name.startswith("problem_formalizer_") and "problem_formalizer" in self.responses:
            return self._problem_payload_for_task(task_name, user_prompt)
        if task_name.startswith("student_work_") and "student_work_formalizer" in self.responses:
            return self._student_payload_for_task(task_name)
        raise KeyError(task_name)


def _simple_problem_formalization():
    return {
        "quantity_annotations": [
            {
                "quantity_id": "quantity_1",
                "semantic_role": "base",
                "unit": "apples",
                "is_target_candidate": True,
            }
        ],
        "semantic_facts": [],
        "target": {
            "surface_text": "How many apples are there?",
            "normalized_question": "How many apples are there?",
            "target_variable": "how_many_apples_are_there",
            "target_quantity_id": "quantity_1",
            "unit": "apples",
            "description": "How many apples are there",
            "confidence": 0.95,
        },
        "relation": {
            "relation_type": "unknown",
            "operation_hint": "unknown",
            "source_quantity_ids": ["quantity_1"],
            "target_variable": "how_many_apples_are_there",
            "expression": "how_many_apples_are_there = quantity_1",
            "rationale": "Only one quantity is present, so it is also the answer.",
            "confidence": 0.8,
        },
        "plan_steps": [
            {
                "step_id": "step_1_single_quantity",
                "step_index": 1,
                "operation": "derive",
                "input_refs": ["quantity_1"],
                "output_ref": "how_many_apples_are_there",
                "expression": "quantity_1",
                "label": "Use the only quantity as the answer.",
                "output_unit": "apples",
                "confidence": 0.85,
            }
        ],
        "graph_target_node_id": "how_many_apples_are_there",
        "graph_confidence": 0.9,
        "graph_notes": ["llm_graph"],
        "assumptions": [],
        "confidence": 0.9,
        "notes": ["llm_refined"],
    }


def test_problem_formalizer_uses_llm_when_available():
    client = FakeLLMClient({"problem_formalizer": _simple_problem_formalization()})

    result = formalize_problem("There are 8 apples. How many apples are there?", llm_client=client)

    assert result.provenance.value == "llm"
    assert "llm_formalization_used" in result.notes
    assert "llm_semantic_state_used" in result.notes
    assert "llm_executable_commitment_used" in result.notes
    assert result.problem_graph is not None
    assert client.calls == ["problem_formalizer_semantic_state", "problem_formalizer_executable_commitment"]


def test_problem_formalizer_retries_after_invalid_graph_feedback():
    invalid_response = _simple_problem_formalization()
    invalid_response["plan_steps"] = [
        {
            "step_id": "step_1_single_quantity",
            "step_index": 1,
            "operation": "derive",
            "input_refs": ["missing_quantity_ref"],
            "output_ref": "how_many_apples_are_there",
            "expression": "missing_quantity_ref",
            "label": "Broken step",
            "output_unit": "apples",
            "confidence": 0.9,
        }
    ]
    client = FakeLLMClient(
        {
            "problem_formalizer": [invalid_response, _simple_problem_formalization()]
        }
    )

    result = formalize_problem("There are 8 apples. How many apples are there?", llm_client=client)

    assert result.provenance.value == "llm"
    assert "llm_formalization_used" in result.notes
    assert "llm_executable_commitment_repaired_after:2" in result.notes
    assert client.calls == [
        "problem_formalizer_semantic_state",
        "problem_formalizer_executable_commitment",
        "problem_formalizer_executable_commitment",
    ]


def test_problem_formalizer_applies_local_semantic_repairs_to_derived_target():
    payload = _simple_problem_formalization()
    payload["quantity_annotations"][0]["is_target_candidate"] = True
    payload["target"]["target_quantity_id"] = "quantity_1"
    payload["plan_steps"] = [
        {
            "step_id": "step_1_copy",
            "step_index": 1,
            "operation": "derive",
            "input_refs": ["quantity_1"],
            "output_ref": "intermediate_value",
            "expression": "quantity_1",
            "label": "Intermediate copy",
            "output_unit": "apples",
            "confidence": 0.85,
        },
        {
            "step_id": "step_2_answer",
            "step_index": 2,
            "operation": "derive",
            "input_refs": ["intermediate_value"],
            "output_ref": "how_many_apples_are_there",
            "expression": "intermediate_value",
            "label": "Final answer",
            "output_unit": "apples",
            "confidence": 0.85,
        },
    ]
    client = FakeLLMClient({"problem_formalizer": payload})

    result = formalize_problem("There are 8 apples. How many apples are there?", llm_client=client)

    assert result.target is not None
    assert result.target.target_quantity_id is None
    assert all(quantity.is_target_candidate is False for quantity in result.quantities)
    assert "local_semantic_repair:cleared_target_quantity_for_derived_target" in result.notes


def test_problem_formalizer_accepts_latent_quantities_for_model_led_structure():
    problem_text = (
        "A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. "
        "Over three hundred years, it has consumed 847 people. Ships have been built larger over time, so each new "
        "ship has twice as many people as the last ship. How many people were on the ship the monster ate in the first hundred years?"
    )
    payload = {
        "quantity_annotations": [
            {
                "quantity_id": "quantity_1",
                "semantic_role": "base",
                "unit": "people",
                "is_target_candidate": False,
            }
        ],
        "semantic_facts": [
            {
                "fact_id": "latent_quantity_1",
                "label": "doubling factor",
                "value": 2.0,
                "unit": "factor",
                "semantic_role": "rate",
                "notes": ["Derived from 'twice as many'."],
            }
        ],
        "target": {
            "surface_text": "How many people were on the ship the monster ate in the first hundred years?",
            "normalized_question": "How many people were on the ship the monster ate in the first hundred years?",
            "target_variable": "people_on_first_ship",
            "target_quantity_id": None,
            "unit": "people",
            "description": "Number of people on the first ship.",
            "confidence": 0.93,
        },
        "relation": {
            "relation_id": "relation_1",
            "relation_type": "multiplicative_scaling",
            "operation_hint": "unknown",
            "source_quantity_ids": ["quantity_1", "latent_quantity_1"],
            "target_variable": "people_on_first_ship",
            "expression": "quantity_1 / (1 + latent_quantity_1 + (latent_quantity_1 * latent_quantity_1))",
            "rationale": "Three ship visits form x + 2x + 4x = 847.",
            "confidence": 0.86,
        },
        "plan_steps": [
            {
                "step_id": "step_1_third_multiplier",
                "step_index": 1,
                "operation": "multiply",
                "input_refs": ["latent_quantity_1", "latent_quantity_1"],
                "output_ref": "third_multiplier",
                "expression": "latent_quantity_1 * latent_quantity_1",
                "label": "Compute the third ship multiplier.",
                "output_unit": "factor",
                "confidence": 0.88,
            },
            {
                "step_id": "step_2_total_multiplier",
                "step_index": 2,
                "operation": "add",
                "input_refs": ["latent_quantity_1", "third_multiplier"],
                "output_ref": "total_multiplier",
                "expression": "1 + latent_quantity_1 + third_multiplier",
                "label": "Add the three ship multipliers.",
                "output_unit": "factor",
                "confidence": 0.88,
            },
            {
                "step_id": "step_3_first_ship",
                "step_index": 3,
                "operation": "divide",
                "input_refs": ["quantity_1", "total_multiplier"],
                "output_ref": "people_on_first_ship",
                "expression": "quantity_1 / total_multiplier",
                "label": "Recover the first ship size.",
                "output_unit": "people",
                "confidence": 0.9,
            },
        ],
        "graph_target_node_id": "people_on_first_ship",
        "graph_confidence": 0.9,
        "graph_notes": ["llm_graph_with_latent_quantities"],
        "assumptions": ["One ship is eaten every hundred years for three hundred years."],
        "confidence": 0.9,
        "notes": ["llm_latent_quantity_test"],
    }
    client = FakeLLMClient({"problem_formalizer": payload})

    formalized = formalize_problem(problem_text, llm_client=client)
    reference = build_canonical_reference(formalized)

    assert any(quantity.quantity_id == "latent_quantity_1" for quantity in formalized.quantities)
    assert reference.final_answer == 121.0
    assert any(
        note in formalized.notes
        for note in {
            "llm_semantic_fact_added:latent_quantity_1",
        }
    )


def test_problem_formalizer_repairs_common_model_skeleton_shape_errors():
    problem_text = (
        "A deep-sea monster rises from the waters once every hundred years to feast on a ship and sate its hunger. "
        "Over three hundred years, it has consumed 847 people. Ships have been built larger over time, so each new "
        "ship has twice as many people as the last ship. How many people were on the ship the monster ate in the first hundred years?"
    )
    payload = {
        "quantity_annotations": [
            {
                "quantity_id": "quantity_1",
                "semantic_role": "base",
                "unit": "people",
                "entity_id": None,
                "is_target_candidate": False,
            },
        ],
        "semantic_facts": [
            {
                "fact_id": "latent_quantity_1",
                "label": "sum factor (1+2+4)",
                "value": 7.0,
                "unit": "dimensionless",
                "entity_id": None,
                "semantic_role": "intermediate",
                "is_target_candidate": False,
                "notes": ["used to divide total by 7"],
            }
        ],
        "target": {
            "surface_text": "How many people were on the ship the monster ate in the first hundred years?",
            "normalized_question": "How many people were on the ship the monster ate in the first hundred years?",
            "target_variable": "how_many_people_were_on_the_ship_the_monster_ate_in_the_first_hundred_years",
            "target_quantity_id": "quantity_2",
            "entity_id": None,
            "unit": "people",
            "description": "People on the first ship",
            "confidence": 0.0,
        },
        "relation": {
            "relation_id": "relation_1",
            "relation_type": "multiplicative_scaling",
            "operation_hint": "unknown",
            "source_quantity_ids": ["quantity_1", "latent_quantity_1"],
            "target_variable": "how_many_people_were_on_the_ship_the_monster_ate_in_the_first_hundred_years",
            "expression": "quantity_1 / latent_quantity_1",
            "rationale": "total divided by 7 gives the first ship size",
            "confidence": 0.0,
        },
        "plan_steps": [
            {
                "step_id": "step_1",
                "step_index": 1,
                "operation": "derive",
                "input_refs": [],
                "output_ref": "latent_quantity_1",
                "expression": "latent_quantity_1 = 7",
                "label": "define_sum_factor",
                "output_unit": "dimensionless",
                "confidence": 0.0,
            },
            {
                "step_id": "step_2",
                "step_index": 2,
                "operation": "divide",
                "input_refs": ["quantity_1", "latent_quantity_1"],
                "output_ref": "quantity_2",
                "expression": "quantity_2 = quantity_1 / latent_quantity_1",
                "label": "compute_first_ship_size",
                "output_unit": "people",
                "confidence": 0.0,
            },
        ],
        "graph_target_node_id": "how_many_people_were_on_the_ship_the_monster_ate_in_the_first_hundred_years",
        "graph_confidence": 0.0,
        "graph_notes": ["repairable_model_shape_errors"],
        "assumptions": ["Three ship sizes are x, 2x, and 4x."],
        "confidence": 0.0,
        "notes": ["model_used_quantity_2_and_assignment_syntax"],
    }
    client = FakeLLMClient({"problem_formalizer": payload})

    formalized = formalize_problem(problem_text, llm_client=client)
    reference = build_canonical_reference(formalized)

    assert formalized.provenance.value == "llm"
    assert formalized.target is not None
    assert formalized.target.target_quantity_id is None
    assert reference.final_answer == 121.0
    assert "local_target_repair:cleared_unknown_target_quantity_id:quantity_2" in formalized.notes
    assert any(
        "local_graph_repair:retargeted_output_ref:quantity_2->how_many_people_were_on_the_ship_the_monster_ate_in_the_first_hundred_years"
        == note
        for note in formalized.notes
    )


def test_student_work_formalizer_uses_llm_to_parse_word_number_answer():
    problem_text = "There are 8 apples. How many apples are there?"
    problem = formalize_problem(problem_text)
    reference = solve_problem(problem_text)
    client = FakeLLMClient(
        {
            "student_work_formalizer": {
                "final_answer": {"value": 8.0, "confidence": 0.95},
                "mode": "final_answer_only",
                "target": {
                    "selected_ref": "how_many_apples_are_there",
                    "confidence": 0.9,
                    "rationale": "The answer text points to the main target.",
                },
                "trace_steps": [],
                "assumptions": [],
                "confidence": 0.9,
                "notes": ["llm_parsed_word_number"],
            }
        }
    )

    result = formalize_student_work("The answer is eight.", problem=problem, reference=reference, llm_client=client)

    assert result.normalized_final_answer == 8.0
    assert "llm_student_parse_used" in result.notes
    assert "llm_student_semantic_state_used" in result.notes
    assert "llm_student_trace_commitment_used" in result.notes
    assert client.calls == ["student_work_semantic_state", "student_work_trace_commitment"]


def test_student_work_formalizer_retries_after_invalid_ref_feedback():
    problem_text = "There are 8 apples. How many apples are there?"
    problem = formalize_problem(problem_text)
    reference = solve_problem(problem_text)
    invalid_response = {
        "final_answer": {"value": 8.0, "confidence": 0.8},
        "mode": "final_answer_only",
        "target": {"selected_ref": "invented_ref", "confidence": 0.8, "rationale": "broken"},
        "trace_steps": [],
        "confidence": 0.85,
        "notes": ["broken_selected_ref"],
    }
    repaired_response = {
        "final_answer": {"value": 8.0, "confidence": 0.95},
        "mode": "final_answer_only",
            "target": {
                "selected_ref": "how_many_apples_are_there",
                "confidence": 0.92,
                "rationale": "repaired",
            },
        "trace_steps": [],
        "confidence": 0.92,
        "notes": ["repaired_selected_ref"],
    }
    client = FakeLLMClient({"student_work_formalizer": [invalid_response, repaired_response]})

    result = formalize_student_work("The answer is eight.", problem=problem, reference=reference, llm_client=client)

    assert result.normalized_final_answer == 8.0
    assert result.selected_target_ref == "how_many_apples_are_there"
    assert "llm_student_trace_commitment_used" in result.notes
    assert client.calls == [
        "student_work_semantic_state",
        "student_work_semantic_state",
        "student_work_trace_commitment",
    ]


def test_student_work_formalizer_rebuilds_trace_from_surface_text_sketch():
    problem_text = "Jan has 3 apples. She buys 5 more apples. How many apples does she have in total?"
    problem = formalize_problem(problem_text)
    reference = solve_problem(problem_text)
    raw_answer = "3 + 5 = 9. Answer is 9."
    assert problem.target is not None
    target_ref = problem.target.target_variable
    client = FakeLLMClient(
        {
            "student_work_formalizer": {
                "final_answer": {"value": 9.0, "confidence": 0.9},
                "mode": "partial_trace",
                "target": {
                    "selected_ref": target_ref,
                    "confidence": 0.85,
                    "rationale": "The student is answering the main question.",
                },
                "semantic_facts": [
                    {
                        "fact_id": "student_fact_1",
                        "label": "student_claimed_total",
                        "value": 9.0,
                        "grounding": "3 + 5 = 9.",
                        "confidence": 0.8,
                        "notes": ["Claim inferred from the student's equation."],
                    }
                ],
                "trace_steps": [
                    {
                        "surface_text": "3 + 5 = 9.",
                        "operation": "add",
                        "input_values": [3.0, 5.0],
                        "extracted_value": 9.0,
                        "referenced_ids": ["quantity_1", "quantity_2", "student_fact_1"],
                        "confidence": 0.82,
                        "notes": ["Student adds the two quantities and gets 9."],
                    }
                ],
                "assumptions": [],
                "confidence": 0.88,
                "notes": ["llm_trace_rebuilt_from_surface_text"],
            }
        }
    )

    result = formalize_student_work(raw_answer, problem=problem, reference=reference, llm_client=client)

    assert result.mode == StudentWorkMode.PARTIAL_TRACE
    assert result.selected_target_ref == target_ref
    assert len(result.semantic_facts) == 1
    assert result.semantic_facts[0].fact_id == "student_fact_1"
    assert len(result.steps) == 1
    assert result.steps[0].raw_text == "3 + 5 = 9."
    assert result.steps[0].operation == TraceOperation.ADD
    assert result.steps[0].extracted_value == 9.0
    assert "student_fact_1" in result.steps[0].referenced_ids
    assert any(node.node_id == "student_fact_1" for node in (result.student_graph.nodes if result.student_graph else []))
    assert "llm_student_semantic_state_used" in result.notes
    assert client.calls == ["student_work_semantic_state", "student_work_trace_commitment"]


def test_student_work_formalizer_repairs_target_ref_prunes_unused_facts_and_drops_placeholders():
    problem_text = "Jan has 3 apples. She buys 5 more apples. How many apples does she have in total?"
    problem = formalize_problem(problem_text)
    reference = solve_problem(problem_text)
    assert problem.target is not None
    target_ref = problem.target.target_variable
    client = FakeLLMClient(
        {
            "student_work_formalizer": {
                "final_answer": {"value": 8.0, "confidence": 0.0},
                "mode": "partial_trace",
                "target": {
                    "selected_ref": "quantity_1",
                    "confidence": 0.0,
                    "rationale": "broken_target_ref",
                },
                "semantic_facts": [
                    {
                        "fact_id": "student_fact_1",
                        "label": "student_claimed_total",
                        "value": 8.0,
                        "grounding": "3 + 5 = 8.",
                        "confidence": 0.0,
                        "notes": [],
                    },
                    {
                        "fact_id": "student_fact_2",
                        "label": "duplicate_unreferenced_total",
                        "value": 8.0,
                        "grounding": "Answer is 8.",
                        "confidence": 0.0,
                        "notes": [],
                    },
                ],
                "trace_steps": [
                    {
                        "surface_text": "3 + 5 = 8.",
                        "operation": "add",
                        "input_values": [0.0, 3.0, 5.0],
                        "extracted_value": 0.0,
                        "referenced_ids": ["quantity_1", "quantity_2", "student_fact_1"],
                        "confidence": 0.0,
                        "notes": [],
                    }
                ],
                "assumptions": [],
                "confidence": 0.0,
                "notes": ["repair_target_and_placeholders"],
            }
        }
    )

    result = formalize_student_work("3 + 5 = 8. Answer is 8.", problem=problem, reference=reference, llm_client=client)

    assert result.selected_target_ref == target_ref
    assert f"local_target_repair:retargeted_selected_ref:quantity_1->{target_ref}" in result.notes
    assert [fact.fact_id for fact in result.semantic_facts] == ["student_fact_1"]
    assert any(note == "local_semantic_fact_pruned:unreferenced:student_fact_2" for note in result.notes)
    assert result.steps[0].input_values == [3.0, 5.0]
    assert result.steps[0].extracted_value is None
    assert result.steps[0].confidence > 0.0
    assert any(note == "local_step_repair:dropped_ungrounded_input_value" for note in result.steps[0].notes)
    assert any(note == "local_step_repair:dropped_ungrounded_extracted_value" for note in result.steps[0].notes)
    assert result.confidence > 0.0
    assert client.calls == ["student_work_semantic_state", "student_work_trace_commitment"]


def test_diagnosis_uses_llm_refinement():
    problem_text = "Jan has 3 apples. She buys 5 more apples. How many apples does she have in total?"
    problem = formalize_problem(problem_text)
    reference = solve_problem(problem_text)
    student = formalize_student_work("3 + 5 = 9\nAnswer is 9.", problem=problem, reference=reference)
    evidence = build_diagnosis_evidence(problem, reference, student)
    context = build_diagnosis_context(problem, reference, student, evidence)
    client = FakeLLMClient(
        {
            "diagnosis_interpretation": {
                "diagnosis_label": "arithmetic_error",
                "subtype": "intermediate_calculation_error",
                "localization": "intermediate_step",
                "candidate_target_step_id": "step_1_add_all",
                "first_divergence_step_id": "step_1_add_all",
                "summary": "The student chooses the right setup but computes the sum incorrectly.",
                "supporting_evidence_types": ["final_answer_mismatch", "step_value_mismatch"],
                "grounded_evidence": ["final_answer_mismatch", "step_value_mismatch"],
                "reasoning_points": ["The target is correct, but the computed sum is wrong."],
                "confidence": 0.91,
                "notes": ["llm_refined_interpretation"],
            }
        }
    )

    result = diagnose(evidence, context=context, llm_client=client)

    assert result.summary == "The student chooses the right setup but computes the sum incorrectly."
    assert "llm_first_diagnosis_used" in result.notes
    assert client.calls == ["diagnosis_state"]


def test_hint_generator_uses_llm_text_when_verification_passes():
    problem_text = "Tom had 10 marbles and gave away 4. How many marbles are left?"
    problem = formalize_problem(problem_text)
    reference = solve_problem(problem_text)
    student = formalize_student_work("Answer is 6.", problem=problem, reference=reference)
    evidence = build_diagnosis_evidence(problem, reference, student)
    diagnosis = diagnose(evidence)
    plan = build_hint_plan(problem, reference, diagnosis)
    client = FakeLLMClient({"hint_generator": {"hint_text": "Your answer is correct."}})

    result = build_hint_result(problem, reference, diagnosis, plan, llm_client=client)

    assert diagnosis.diagnosis_label == DiagnosisLabel.CORRECT_ANSWER
    assert result.hint_text == "Your answer is correct."
    assert result.verification_passed is True
    assert client.calls == ["hint_generator"]


def test_pipeline_uses_llm_across_all_target_modules():
    client = FakeLLMClient(
        {
            "problem_formalizer": _simple_problem_formalization(),
            "student_work_formalizer": {
                "final_answer": {"value": 8.0, "confidence": 0.95},
                "mode": "final_answer_only",
                "target": {
                    "selected_ref": "how_many_apples_are_there",
                    "confidence": 0.92,
                    "rationale": "main target",
                },
                "trace_steps": [],
                "assumptions": [],
                "confidence": 0.92,
                "notes": ["llm_pipeline_student_parse"],
            },
            "diagnosis_interpretation": {
                "diagnosis_label": "correct_answer",
                "subtype": "matches_canonical_reference",
                "localization": "none",
                "candidate_target_step_id": None,
                "first_divergence_step_id": None,
                "summary": "The student's answer matches the canonical reference.",
                "supporting_evidence_types": ["correct_final_answer"],
                "grounded_evidence": ["correct_final_answer"],
                "reasoning_points": ["The student selected the correct target and final value."],
                "confidence": 0.93,
                "notes": ["llm_pipeline_diagnosis_interpretation"],
            },
            "hint_strategy": {
                "teacher_move": "restate_result",
                "hint_level": "conceptual",
                "pedagogical_goal": "Acknowledge that the student is already correct.",
                "student_action": None,
                "target_step_id": None,
                "disclosure_budget": 0,
                "focus_points": [],
                "must_not_reveal": [],
                "rationale": "No corrective hint is needed for a correct answer.",
                "confidence": 0.9,
                "notes": ["llm_pipeline_hint_strategy"],
            },
            "hint_generator": {"hint_text": "Your answer is correct."},
        }
    )

    result = run_tutoring_pipeline(
        "There are 8 apples. How many apples are there?",
        "The answer is 8.",
        llm_client=client,
        use_llm=True,
    )

    assert result.reference.final_answer == 8.0
    assert result.student_work.normalized_final_answer == 8.0
    assert result.diagnosis.diagnosis_label == DiagnosisLabel.CORRECT_ANSWER
    assert result.hint_result.hint_text == "Your answer is correct."
    assert client.calls == [
        "problem_formalizer_semantic_state",
        "problem_formalizer_executable_commitment",
        "student_work_semantic_state",
        "student_work_trace_commitment",
        "diagnosis_state",
        "pedagogy_state",
        "hint_generator",
    ]

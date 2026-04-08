"""Diagnosis engine with grounded hypothesis scoring and optional LLM critique."""
from __future__ import annotations

import json

from src.diagnosis.scoring import DiagnosisHypothesis, build_diagnosis_hypotheses
from src.llm import LLMClient, LLMGenerationError
from src.models import DiagnosisEvidence, DiagnosisLabel, DiagnosisResult, ErrorLocalization


def _evidence_types(evidence: DiagnosisEvidence) -> list[str]:
    return [item.evidence_type for item in evidence.evidence_items]


def _build_result_from_hypothesis(
    hypothesis: DiagnosisHypothesis,
    evidence: DiagnosisEvidence,
    extra_notes: list[str] | None = None,
) -> DiagnosisResult:
    notes = list(evidence.notes)
    notes.extend(f"diagnosis_rationale:{reason}" for reason in hypothesis.rationale)
    if extra_notes:
        notes.extend(extra_notes)

    confidence = min(max(evidence.confidence + min(hypothesis.score / 20.0, 0.12), 0.35), 0.98)
    return DiagnosisResult(
        diagnosis_label=hypothesis.label,
        subtype=hypothesis.subtype,
        localization=hypothesis.localization,
        target_step_id=evidence.first_divergence_step_id,
        summary=hypothesis.summary,
        supporting_evidence_types=hypothesis.supporting_evidence_types or _evidence_types(evidence),
        confidence=confidence,
        notes=notes,
    )


def _deterministic_diagnosis(evidence: DiagnosisEvidence) -> tuple[DiagnosisResult, list[DiagnosisHypothesis]]:
    hypotheses = build_diagnosis_hypotheses(evidence)
    best = hypotheses[0]
    runner_up = hypotheses[1] if len(hypotheses) > 1 else None

    extra_notes: list[str] = []
    extra_notes.append(f"diagnosis_top_hypothesis={best.label.value}:{best.score:.2f}")
    if runner_up is not None:
        margin = best.score - runner_up.score
        extra_notes.append(f"diagnosis_runner_up={runner_up.label.value}:{runner_up.score:.2f}")
        extra_notes.append(f"diagnosis_margin={margin:.2f}")
        if margin < 1.0 and best.label != DiagnosisLabel.CORRECT_ANSWER:
            extra_notes.append("diagnosis_ambiguous_competing_hypotheses")
            if best.label == DiagnosisLabel.UNKNOWN_ERROR:
                extra_notes.append("diagnosis_low_separation_unknown")

    return _build_result_from_hypothesis(best, evidence, extra_notes=extra_notes), hypotheses


def _llm_diagnose(
    evidence: DiagnosisEvidence,
    deterministic_result: DiagnosisResult,
    hypotheses: list[DiagnosisHypothesis],
    llm_client: LLMClient,
) -> DiagnosisResult:
    system_prompt = (
        "You are a diagnosis critic for a math tutoring system. Return only a JSON object matching DiagnosisResult. "
        "Stay grounded in the provided structured evidence and the candidate hypothesis leaderboard. "
        "Do not invent evidence. Prefer one of the provided hypothesis labels/subtypes unless the leaderboard is clearly inconsistent."
    )
    leaderboard = [
        {
            "diagnosis_label": hypothesis.label.value,
            "subtype": hypothesis.subtype,
            "localization": hypothesis.localization.value,
            "score": hypothesis.score,
            "summary": hypothesis.summary,
            "rationale": hypothesis.rationale,
            "supporting_evidence_types": hypothesis.supporting_evidence_types,
        }
        for hypothesis in hypotheses[:4]
    ]
    user_prompt = (
        "Allowed diagnosis_label values: "
        f"{[label.value for label in DiagnosisLabel]}\n"
        "Allowed localization values: "
        f"{[label.value for label in ErrorLocalization]}\n\n"
        f"Structured evidence:\n{json.dumps(evidence.model_dump(mode='json'), ensure_ascii=True)}\n\n"
        f"Deterministic baseline diagnosis:\n{json.dumps(deterministic_result.model_dump(mode='json'), ensure_ascii=True)}\n\n"
        f"Hypothesis leaderboard:\n{json.dumps(leaderboard, ensure_ascii=True)}\n\n"
        "Return a refined DiagnosisResult JSON object. Keep supporting_evidence_types aligned with the evidence."
    )
    payload = llm_client.generate_json(
        task_name="diagnosis",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=1200,
    )
    payload.setdefault("supporting_evidence_types", _evidence_types(evidence))
    notes = list(payload.get("notes", []))
    notes.append("llm_diagnosis_used")
    payload["notes"] = notes
    llm_result = DiagnosisResult.model_validate(payload)

    evidence_types = set(_evidence_types(evidence))
    if "unparseable_answer" in evidence_types and llm_result.diagnosis_label != DiagnosisLabel.UNPARSEABLE_ANSWER:
        raise ValueError("LLM diagnosis conflicts with unparseable_answer evidence")
    if (
        "selected_intermediate_reference" in evidence_types or "selected_visible_problem_quantity" in evidence_types
    ) and llm_result.diagnosis_label != DiagnosisLabel.TARGET_MISUNDERSTANDING:
        raise ValueError("LLM diagnosis conflicts with target-selection evidence")

    return llm_result


def diagnose(
    evidence: DiagnosisEvidence,
    llm_client: LLMClient | None = None,
) -> DiagnosisResult:
    """Map structured evidence into a diagnosis result."""
    deterministic_result, hypotheses = _deterministic_diagnosis(evidence)
    if llm_client is None:
        return deterministic_result

    try:
        return _llm_diagnose(evidence, deterministic_result, hypotheses, llm_client)
    except (LLMGenerationError, ValueError, TypeError):
        notes = list(deterministic_result.notes)
        notes.append("llm_diagnosis_failed_fallback")
        return deterministic_result.model_copy(update={"notes": notes})

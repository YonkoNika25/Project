"""Low-level surface evidence extraction helpers for problem formalization."""
from __future__ import annotations

import re
from typing import Iterable, Optional

from src.models import (
    OperationType,
    ProblemEntity,
    ProvenanceSource,
    QuantityAnnotation,
    QuantitySemanticRole,
    RelationCandidate,
    RelationType,
    TargetSpec,
)


_NUMBER_PATTERN = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")
_TARGET_QUESTION_PATTERN = re.compile(
    r"((?:if\b.*?,\s*)?(?:how many|how much|what|which|who|where|when|why)[^?]*\?)",
    re.IGNORECASE,
)
_ENTITY_PATTERN = re.compile(
    r"\b(?:(Mr|Mrs|Ms|Dr)\.\s+[A-Z][a-z]+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
)

_ADDITIVE_CUES = (
    "total",
    "altogether",
    "in all",
    "sum",
    "more",
    "added",
    "combined",
    "together",
    "buys",
)
_SUBTRACTIVE_CUES = (
    "left",
    "remain",
    "remaining",
    "still available",
    "difference",
    "less",
    "fewer",
    "exceeds",
    "exceed",
    "beyond",
    "over",
    "spent",
    "lost",
    "after",
)
_MULTIPLICATIVE_CUES = (
    "times",
    "twice",
    "double",
    "triple",
    "half",
    "quarter",
)
_PARTITION_CUES = (
    "split equally",
    "share equally",
    "group",
    "groups",
    "divide equally",
)
_RATE_CUES = (
    "each",
    "per",
    "%",
    "percent",
    "every",
    "costs",
    "price",
)
_THRESHOLD_CUES = (
    "exceeds",
    "exceed",
    "over",
    "beyond",
    "after",
    "first",
    "at least",
    "at most",
)

_UNIT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "if",
    "in",
    "is",
    "it",
    "much",
    "many",
    "of",
    "or",
    "that",
    "the",
    "their",
    "there",
    "they",
    "this",
    "to",
    "was",
    "were",
    "what",
    "which",
    "who",
    "why",
    "with",
}

_VERBAL_NUMBER_CUES = {
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "hundred": 100.0,
    "double": 2.0,
    "twice": 2.0,
    "triple": 3.0,
    "half": 0.5,
    "quarter": 0.25,
}


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    sentences: list[tuple[str, int, int]] = []
    if not text:
        return sentences
    for match in re.finditer(r"[^.!?]+[.!?]?", text):
        sentence = match.group().strip()
        if sentence:
            sentences.append((sentence, match.start(), match.end()))
    return sentences


def _slugify(text: str, fallback: str = "target") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return slug or fallback


def _matching_cues(text: str, cues: Iterable[str]) -> list[str]:
    lowered = text.lower()
    return [cue for cue in cues if cue in lowered]


def _extract_target_text(problem_text: str) -> str:
    candidates = _extract_target_span_candidates(problem_text)
    return candidates[0]["surface_text"] if candidates else ""


def _extract_target_span_candidates(problem_text: str) -> list[dict]:
    text = (problem_text or "").strip()
    if not text:
        return []

    candidates: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    sentences = _split_sentences(text)

    def _append_candidate(surface_text: str, start: int, end: int, rule_source: str) -> None:
        span = (start, end)
        if span in seen_spans:
            return
        seen_spans.add(span)
        unit_candidate = None
        lowered = surface_text.lower()
        if "how much" in lowered:
            unit_candidate = "dollars"
        elif "how many" in lowered:
            words = re.findall(r"[A-Za-z]+", surface_text)
            for index, word in enumerate(words):
                if word.lower() == "many" and index + 1 < len(words):
                    unit_candidate = words[index + 1].lower()
                    break
        candidates.append(
            {
                "surface_text": surface_text.strip(),
                "normalized_question": surface_text.strip(),
                "target_variable": _slugify(surface_text, fallback="answer"),
                "unit_candidate": unit_candidate,
                "char_start": start,
                "char_end": end,
                "rule_source": rule_source,
                "confidence": 0.9 if rule_source == "matched_wh_question" else 0.65,
            }
        )

    question_match = _TARGET_QUESTION_PATTERN.search(text)
    if question_match:
        _append_candidate(
            question_match.group(1).strip(),
            question_match.start(1),
            question_match.end(1),
            "matched_wh_question",
        )

    for sentence, start, end in sentences:
        if "?" in sentence:
            _append_candidate(sentence.strip(), start, end, "question_sentence")

    if sentences:
        sentence, start, end = sentences[-1]
        _append_candidate(sentence.strip(), start, end, "final_sentence_fallback")

    return candidates


def _extract_entities(problem_text: str) -> list[ProblemEntity]:
    seen: set[str] = set()
    entities: list[ProblemEntity] = []
    for idx, match in enumerate(_ENTITY_PATTERN.finditer(problem_text or ""), start=1):
        surface = match.group(0).strip()
        key = surface.lower()
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            ProblemEntity(
                entity_id=f"entity_{idx}",
                surface_text=surface,
                normalized_name=surface,
                entity_type="person" if surface.startswith(("Mr.", "Mrs.", "Ms.", "Dr.")) else "named_entity",
                metadata={"char_start": match.start(), "char_end": match.end()},
            )
        )
    return entities


def _extract_unit_candidates(surface: str, left_context: str, right_context: str, target_candidates: list[dict]) -> list[str]:
    if "$" in surface:
        return ["dollars"]
    if "%" in surface:
        return ["percent"]

    candidates: list[str] = []
    seen: set[str] = set()

    def _push(candidate: str) -> None:
        normalized = candidate.strip().lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    right_words = re.findall(r"[A-Za-z]+", right_context)
    collected: list[str] = []
    for word in right_words:
        lowered = word.lower()
        if lowered in _UNIT_STOPWORDS:
            if collected:
                break
            continue
        collected.append(lowered)
        if len(collected) >= 3:
            break
    if collected:
        for size in range(1, min(len(collected), 3) + 1):
            _push(" ".join(collected[:size]))

    left_words = re.findall(r"[A-Za-z]+", left_context)
    reversed_collected: list[str] = []
    for word in reversed(left_words):
        lowered = word.lower()
        if lowered in _UNIT_STOPWORDS:
            if reversed_collected:
                break
            continue
        reversed_collected.append(lowered)
        if len(reversed_collected) >= 2:
            break
    if reversed_collected:
        _push(" ".join(reversed(reversed_collected)))

    for target_candidate in target_candidates:
        unit_candidate = target_candidate.get("unit_candidate")
        if isinstance(unit_candidate, str):
            _push(unit_candidate)

    return candidates


def _extract_role_hints(surface: str, local_context: str, target_candidates: list[dict]) -> list[str]:
    hints: list[str] = []
    lowered_context = local_context.lower()

    def _add_hint(hint: str) -> None:
        if hint not in hints:
            hints.append(hint)

    if "%" in surface or "percent" in lowered_context:
        _add_hint("percent_like")
    if any(cue in lowered_context for cue in _THRESHOLD_CUES):
        _add_hint("threshold_like")
    if any(cue in lowered_context for cue in _RATE_CUES) or "$" in surface:
        _add_hint("rate_like")
    if any(surface in candidate["surface_text"] for candidate in target_candidates if candidate.get("surface_text")):
        _add_hint("target_overlap")

    return hints


def _extract_numeric_mentions(problem_text: str, target_candidates: list[dict]) -> list[dict]:
    mentions: list[dict] = []
    sentences = _split_sentences(problem_text)

    for idx, match in enumerate(_NUMBER_PATTERN.finditer(problem_text or ""), start=1):
        surface = match.group(0)
        normalized = surface.replace("$", "").replace("%", "").replace(",", "")
        try:
            value = float(normalized)
        except ValueError:
            continue

        sentence_index = None
        for s_idx, (_, start, end) in enumerate(sentences):
            if start <= match.start() < end:
                sentence_index = s_idx
                break

        left_context = (problem_text[max(0, match.start() - 25):match.start()] or "").strip()
        right_context = (problem_text[match.end():match.end() + 30] or "").strip()
        local_context = problem_text[max(0, match.start() - 25):match.end() + 35]

        mentions.append(
            {
                "mention_id": f"quantity_{idx}",
                "surface_text": surface,
                "value": value,
                "sentence_index": sentence_index,
                "char_start": match.start(),
                "char_end": match.end(),
                "left_context": left_context,
                "right_context": right_context,
                "local_context": local_context.strip(),
                "unit_candidates": _extract_unit_candidates(surface, left_context, right_context, target_candidates),
                "role_hints": _extract_role_hints(surface, local_context, target_candidates),
                "rule_source": "numeric_regex",
            }
        )

    return mentions


def _extract_implicit_quantity_cues(problem_text: str) -> list[dict]:
    lowered = (problem_text or "").lower()
    cues: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    for token, value in _VERBAL_NUMBER_CUES.items():
        pattern = re.compile(rf"\b{re.escape(token)}\b")
        for match in pattern.finditer(lowered):
            span = (match.start(), match.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            cues.append(
                {
                    "cue_id": f"implicit_cue_{len(cues) + 1}",
                    "surface_text": problem_text[match.start():match.end()],
                    "value_hint": value,
                    "char_start": match.start(),
                    "char_end": match.end(),
                    "cue_type": "verbal_number" if token not in {"double", "twice", "triple", "half", "quarter"} else "multiplicative",
                    "rule_source": "mini_lexicon",
                }
            )
    return cues


def _extract_lexical_cue_hits(problem_text: str, target_text: str = "") -> list[dict]:
    combined_text = f"{problem_text} {target_text}".strip().lower()
    cue_families = (
        ("additive", _ADDITIVE_CUES),
        ("subtractive", _SUBTRACTIVE_CUES),
        ("multiplicative", _MULTIPLICATIVE_CUES),
        ("partition", _PARTITION_CUES),
        ("rate", _RATE_CUES),
        ("threshold", _THRESHOLD_CUES),
    )

    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for family, cues in cue_families:
        for cue in _matching_cues(combined_text, cues):
            key = (family, cue)
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                {
                    "family": family,
                    "cue": cue,
                    "rule_source": "cue_lookup",
                }
            )
    return hits


def _build_relation_candidates_from_cues(
    problem_text: str,
    target_candidates: list[dict],
    numeric_mentions: list[dict],
    lexical_cues: list[dict],
) -> list[dict]:
    family_to_relation = {
        "additive": (RelationType.ADDITIVE_COMPOSITION, OperationType.ADDITIVE),
        "subtractive": (RelationType.SUBTRACTIVE_COMPARISON, OperationType.SUBTRACTIVE),
        "multiplicative": (RelationType.MULTIPLICATIVE_SCALING, OperationType.UNKNOWN),
        "partition": (RelationType.PARTITION_GROUPING, OperationType.UNKNOWN),
        "rate": (RelationType.RATE_UNIT_RELATION, OperationType.UNKNOWN),
    }
    family_hits: dict[str, list[str]] = {}
    for hit in lexical_cues:
        family = hit["family"]
        family_hits.setdefault(family, []).append(hit["cue"])

    target_variable = target_candidates[0]["target_variable"] if target_candidates else "answer"
    quantity_ids = [mention["mention_id"] for mention in numeric_mentions]
    candidates: list[dict] = []
    for family, cues in family_hits.items():
        if family not in family_to_relation:
            continue
        relation_type, operation_hint = family_to_relation[family]
        candidates.append(
            {
                "relation_id": f"relation_candidate_{len(candidates) + 1}",
                "relation_type": relation_type.value,
                "operation_hint": operation_hint.value,
                "source_quantity_ids": quantity_ids,
                "target_variable": target_variable,
                "expression": None,
                "rationale": f"Lexical cues suggest the {family} relation family.",
                "confidence": min(0.45 + (0.12 * len(cues)), 0.82),
                "cue_family": family,
                "matched_cues": cues,
            }
        )

    if not candidates and len(numeric_mentions) == 1:
        candidates.append(
            {
                "relation_id": "relation_candidate_1",
                "relation_type": RelationType.UNKNOWN.value,
                "operation_hint": OperationType.UNKNOWN.value,
                "source_quantity_ids": quantity_ids,
                "target_variable": target_variable,
                "expression": f"{target_variable} = {quantity_ids[0]}",
                "rationale": "Single visible numeric mention may itself answer the question.",
                "confidence": 0.4,
                "cue_family": "single_quantity_fallback",
                "matched_cues": [],
            }
        )

    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)


def _build_target_link_candidates(target_candidates: list[dict], numeric_mentions: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for target_candidate in target_candidates:
        target_text = target_candidate["surface_text"].lower()
        target_unit = str(target_candidate.get("unit_candidate") or "").lower()
        for mention in numeric_mentions:
            reasons: list[str] = []
            unit_candidates = [str(candidate).lower() for candidate in mention.get("unit_candidates", [])]
            if mention["surface_text"].lower() in target_text:
                reasons.append("surface_overlap")
            if target_unit and any(target_unit in candidate for candidate in unit_candidates):
                reasons.append("unit_overlap")
            if not reasons:
                continue
            candidates.append(
                {
                    "target_variable": target_candidate["target_variable"],
                    "quantity_id": mention["mention_id"],
                    "reasons": reasons,
                    "confidence": 0.4 + (0.2 * len(reasons)),
                }
            )
    return candidates


def _build_problem_anchor_evidence(problem_text: str) -> dict:
    cleaned_text = (problem_text or "").strip()
    sentence_spans = [
        {
            "sentence_index": index,
            "surface_text": sentence,
            "char_start": start,
            "char_end": end,
        }
        for index, (sentence, start, end) in enumerate(_split_sentences(cleaned_text))
    ]
    target_candidates = _extract_target_span_candidates(cleaned_text)
    numeric_mentions = _extract_numeric_mentions(cleaned_text, target_candidates)
    implicit_quantity_cues = _extract_implicit_quantity_cues(cleaned_text)
    lexical_cues = _extract_lexical_cue_hits(
        cleaned_text,
        target_candidates[0]["surface_text"] if target_candidates else "",
    )
    relation_candidates = _build_relation_candidates_from_cues(
        cleaned_text,
        target_candidates,
        numeric_mentions,
        lexical_cues,
    )
    target_link_candidates = _build_target_link_candidates(target_candidates, numeric_mentions)
    entities = _extract_entities(cleaned_text)

    return {
        "problem_text": cleaned_text,
        "sentence_spans": sentence_spans,
        "numeric_mentions": numeric_mentions,
        "implicit_quantity_cues": implicit_quantity_cues,
        "lexical_cues": lexical_cues,
        "target_span_candidates": target_candidates,
        "target_link_candidates": target_link_candidates,
        "relation_candidates": relation_candidates,
        "entity_candidates": [
            {
                "entity_id": entity.entity_id,
                "surface_text": entity.surface_text,
                "normalized_name": entity.normalized_name,
                "entity_type": entity.entity_type,
            }
            for entity in entities
        ],
    }


def _project_quantities_from_evidence(evidence_pack: dict) -> list[QuantityAnnotation]:
    quantities: list[QuantityAnnotation] = []
    for mention in evidence_pack.get("numeric_mentions", []):
        surface_text = str(mention.get("surface_text", ""))
        unit_candidates = [str(candidate) for candidate in mention.get("unit_candidates", []) if str(candidate).strip()]
        role_hints = [str(hint) for hint in mention.get("role_hints", []) if str(hint).strip()]

        quantity_notes = [
            f"unit_candidates={','.join(unit_candidates)}" if unit_candidates else "unit_candidates=",
            f"role_hints={','.join(role_hints)}" if role_hints else "role_hints=",
            f"rule_source={mention.get('rule_source', 'unknown')}",
        ]
        if mention.get("local_context"):
            quantity_notes.append(f"context={mention['local_context']}")

        quantities.append(
            QuantityAnnotation(
                quantity_id=str(mention["mention_id"]),
                surface_text=surface_text,
                value=float(mention["value"]),
                unit=None,
                semantic_role=QuantitySemanticRole.UNKNOWN,
                sentence_index=mention.get("sentence_index"),
                char_start=mention.get("char_start"),
                char_end=mention.get("char_end"),
                is_target_candidate=False,
                provenance=ProvenanceSource.PROBLEM_TEXT,
                notes=quantity_notes,
            )
        )
    return quantities


def _project_target_from_evidence(evidence_pack: dict) -> Optional[TargetSpec]:
    candidates = evidence_pack.get("target_span_candidates", [])
    if not candidates:
        return None
    target_candidate = candidates[0]
    return TargetSpec(
        surface_text=str(target_candidate["surface_text"]),
        normalized_question=str(target_candidate.get("normalized_question") or target_candidate["surface_text"]),
        target_variable=str(target_candidate["target_variable"]),
        target_quantity_id=None,
        unit=target_candidate.get("unit_candidate"),
        description=str(target_candidate["surface_text"]).strip("?"),
        provenance=ProvenanceSource.PROBLEM_TEXT,
        confidence=float(target_candidate.get("confidence", 0.7) or 0.7),
    )


def _candidate_expression(
    relation_type: RelationType,
    quantities: list[QuantityAnnotation],
    target_ref: str,
) -> Optional[str]:
    refs = [q.quantity_id for q in quantities]
    if not refs:
        return None
    if relation_type == RelationType.ADDITIVE_COMPOSITION and len(refs) >= 2:
        return f"{target_ref} = " + " + ".join(refs)
    if relation_type == RelationType.SUBTRACTIVE_COMPARISON and len(refs) >= 2:
        return f"{target_ref} = {refs[0]} - " + " - ".join(refs[1:])
    if relation_type == RelationType.MULTIPLICATIVE_SCALING and len(refs) >= 2:
        return f"{target_ref} = {refs[0]} * {refs[1]}"
    if relation_type == RelationType.PARTITION_GROUPING and len(refs) >= 2:
        return f"{target_ref} = {refs[0]} / {refs[1]}"
    if relation_type == RelationType.UNKNOWN and len(refs) == 1:
        return f"{target_ref} = {refs[0]}"
    return None


def _project_relation_candidates_from_evidence(
    evidence_pack: dict,
    quantities: list[QuantityAnnotation],
    target: Optional[TargetSpec],
) -> tuple[list[RelationCandidate], list[str]]:
    relation_candidates: list[RelationCandidate] = []
    notes: list[str] = []
    target_variable = target.target_variable if target is not None else "answer"

    for relation_candidate in evidence_pack.get("relation_candidates", []):
        relation_type = RelationType(str(relation_candidate.get("relation_type", RelationType.UNKNOWN.value)))
        operation_hint = OperationType(str(relation_candidate.get("operation_hint", OperationType.UNKNOWN.value)))
        matched_cues = [str(cue) for cue in relation_candidate.get("matched_cues", []) if str(cue).strip()]
        rationale = str(relation_candidate.get("rationale") or "Heuristic relation family candidate.")
        if matched_cues:
            rationale = f"{rationale} matched_cues={','.join(matched_cues)}"
        relation_candidates.append(
            RelationCandidate(
                relation_id=str(relation_candidate.get("relation_id") or f"relation_{len(relation_candidates) + 1}"),
                relation_type=relation_type,
                operation_hint=operation_hint,
                source_quantity_ids=[quantity.quantity_id for quantity in quantities],
                target_variable=target_variable,
                expression=None,
                rationale=rationale,
                confidence=float(relation_candidate.get("confidence", 0.35) or 0.35),
                provenance=ProvenanceSource.HEURISTIC,
            )
        )
        if matched_cues:
            notes.append(
                f"relation_candidate_hint:{relation_type.value}:matched_cues={','.join(matched_cues)}"
            )

    return relation_candidates, notes


def _link_quantities_to_entities(
    quantities: list[QuantityAnnotation],
    entities: list[ProblemEntity],
) -> list[QuantityAnnotation]:
    if not quantities or not entities:
        return quantities

    linked: list[QuantityAnnotation] = []
    for quantity in quantities:
        if quantity.entity_id is not None or quantity.char_start is None:
            linked.append(quantity)
            continue

        best_entity: ProblemEntity | None = None
        best_distance: int | None = None
        for entity in entities:
            char_start = entity.metadata.get("char_start")
            if not isinstance(char_start, int):
                continue
            distance = abs(char_start - quantity.char_start)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_entity = entity

        if best_entity is None:
            linked.append(quantity)
            continue

        linked.append(quantity.model_copy(update={"entity_id": best_entity.entity_id}))

    return linked


def _build_target_spec(problem_text: str, target_text: str) -> Optional[TargetSpec]:
    evidence_pack = _build_problem_anchor_evidence(problem_text)
    return _project_target_from_evidence(evidence_pack)


def _extract_quantities(problem_text: str, target_text: str) -> list[QuantityAnnotation]:
    evidence_pack = _build_problem_anchor_evidence(problem_text)
    return _project_quantities_from_evidence(evidence_pack)


def _build_relation_candidates(
    problem_text: str,
    target: Optional[TargetSpec],
    quantities: list[QuantityAnnotation],
) -> tuple[list[RelationCandidate], list[str]]:
    evidence_pack = _build_problem_anchor_evidence(problem_text)
    return _project_relation_candidates_from_evidence(evidence_pack, quantities, target)


def _dedupe_quantities(quantities: list[QuantityAnnotation]) -> tuple[list[QuantityAnnotation], list[str]]:
    deduped: list[QuantityAnnotation] = []
    notes: list[str] = []
    seen: set[tuple[str, int | None, int | None]] = set()

    for quantity in quantities:
        key = (quantity.surface_text, quantity.char_start, quantity.char_end)
        if key in seen:
            notes.append(f"deduped_quantity:{quantity.surface_text}@{quantity.char_start}")
            continue
        seen.add(key)
        deduped.append(quantity)

    return deduped, notes

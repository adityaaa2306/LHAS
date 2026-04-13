from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List

from app.models import ResearchClaim


HIGH_SIGNAL_SECTIONS = {"results", "abstract", "conclusion", "discussion"}


def _enum_value(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    return getattr(value, "value", value) or default


def _provenance(claim: ResearchClaim) -> Dict[str, Any]:
    return claim.provenance or {}


def claim_text(claim: ResearchClaim) -> str:
    return (claim.statement_normalized or claim.statement_raw or "").strip()


def claim_section(claim: ResearchClaim) -> str:
    return _enum_value(claim.section_source, "unknown").lower()


def claim_type_value(claim: ResearchClaim) -> str:
    return _enum_value(claim.claim_type, "correlational").lower()


def claim_direction_value(claim: ResearchClaim) -> str:
    return _enum_value(claim.direction, "unclear").lower()


def claim_validation_value(claim: ResearchClaim) -> str:
    return _enum_value(claim.validation_status, "UNKNOWN")


def claim_support_count(claim: ResearchClaim) -> int:
    try:
        count = int(_provenance(claim).get("supporting_evidence_count", 1) or 1)
    except (TypeError, ValueError):
        count = 1
    return max(1, count)


def claim_evidence_sections(claim: ResearchClaim) -> List[str]:
    sections = _provenance(claim).get("evidence_sections") or []
    normalized = [str(section).lower() for section in sections if section]
    return normalized or [claim_section(claim)]


def describe_evidence_source(
    primary_section: str,
    evidence_sections: List[str],
) -> Dict[str, str]:
    normalized_sections = [section.lower() for section in evidence_sections if section]
    unique_sections = sorted(set(normalized_sections))
    non_abstract_sections = [section for section in unique_sections if section != "abstract"]

    if not unique_sections:
        return {
            "evidence_source_type": "unknown",
            "evidence_source_label": "Source unclear",
            "evidence_source_detail": "The extractor could not determine whether this finding came from the abstract or the full paper.",
        }

    if unique_sections == ["abstract"]:
        return {
            "evidence_source_type": "abstract_only",
            "evidence_source_label": "Abstract only",
            "evidence_source_detail": "This finding is currently supported only by text from the paper abstract.",
        }

    if "abstract" in unique_sections and non_abstract_sections:
        section_list = ", ".join(section.replace("_", " ") for section in non_abstract_sections)
        return {
            "evidence_source_type": "mixed",
            "evidence_source_label": "Mixed: abstract + full text",
            "evidence_source_detail": f"This finding has support from the abstract and full-text sections ({section_list}).",
        }

    label_map = {
        "results": "Full text: results",
        "discussion": "Full text: discussion",
        "conclusion": "Full text: conclusion",
        "body": "Full text: body",
        "methods": "Full text: methods",
        "introduction": "Full text: introduction",
    }
    chosen = primary_section if primary_section in unique_sections else unique_sections[0]
    pretty_section = chosen.replace("_", " ")
    return {
        "evidence_source_type": "full_text_only",
        "evidence_source_label": label_map.get(chosen, f"Full text: {pretty_section}"),
        "evidence_source_detail": f"This finding is supported by full-text content from the paper's {pretty_section} section.",
    }


def claim_confidence(claim: ResearchClaim) -> float:
    try:
        return float(claim.composite_confidence or 0.0)
    except (TypeError, ValueError):
        return 0.0


def claim_presentation_score(claim: ResearchClaim) -> float:
    section_bonus = {
        "results": 0.22,
        "conclusion": 0.18,
        "abstract": 0.14,
        "discussion": 0.06,
    }.get(claim_section(claim), -0.08)
    support_bonus = min(0.15, 0.04 * max(0, claim_support_count(claim) - 1))
    canonical_bonus = 0.06 if claim.intervention_canonical and claim.outcome_canonical else 0.0
    relevance_bonus = 0.05 if _enum_value(claim.mission_relevance, "").lower() == "primary" else 0.0
    quantitative_bonus = 0.04 if _provenance(claim).get("quantitative_evidence") else 0.0
    return claim_confidence(claim) + section_bonus + support_bonus + canonical_bonus + relevance_bonus + quantitative_bonus


def is_high_signal_claim(claim: ResearchClaim) -> bool:
    text = claim_text(claim)
    section = claim_section(claim)
    confidence = claim_confidence(claim)
    validation = claim_validation_value(claim)
    lowered = text.lower()
    has_subject = any(
        [
            claim.intervention,
            claim.intervention_canonical,
            claim.outcome,
            claim.outcome_canonical,
        ]
    )

    if validation != "VALID":
        return False
    if section not in HIGH_SIGNAL_SECTIONS:
        return False
    if confidence < 0.55:
        return False
    if len(text) < 35 or len(text) > 280:
        return False

    if not has_subject:
        return False
    if lowered.startswith(("this study", "our findings", "we investigated", "the safety, pharmacokinetics")):
        return False
    if any(
        phrase in lowered
        for phrase in (
            "study selection",
            "data extraction",
            "risk of bias",
            "grade assessments",
            "editorial process",
            "publication of the studies",
            "conflict of interest",
            "funding source",
            "protocol for evaluation",
        )
    ):
        return False
    if "more research is needed" in lowered and confidence < 0.7:
        return False
    if claim_type_value(claim) == "correlational" and confidence < 0.65:
        return False
    return True


def _normalized_entity(value: Any) -> str:
    text = (str(value or "").strip().lower())
    return " ".join(text.split())


def _claim_signature(claim: ResearchClaim) -> str:
    base = claim_text(claim).lower()
    tokens = [token for token in base.replace("/", " ").replace("-", " ").split() if len(token) > 2]
    return " ".join(tokens[:24])


def claims_are_similar(left: ResearchClaim, right: ResearchClaim) -> bool:
    left_pair = (
        _normalized_entity(left.intervention_canonical or left.intervention),
        _normalized_entity(left.outcome_canonical or left.outcome),
    )
    right_pair = (
        _normalized_entity(right.intervention_canonical or right.intervention),
        _normalized_entity(right.outcome_canonical or right.outcome),
    )

    if all(left_pair) and all(right_pair) and left_pair != right_pair:
        return False

    left_direction = claim_direction_value(left)
    right_direction = claim_direction_value(right)
    if (
        left_direction != "unclear"
        and right_direction != "unclear"
        and left_direction != right_direction
    ):
        return False

    left_sig = _claim_signature(left)
    right_sig = _claim_signature(right)
    if not left_sig or not right_sig:
        return False

    left_tokens = set(left_sig.split())
    right_tokens = set(right_sig.split())
    if not left_tokens or not right_tokens:
        return False

    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, left_sig, right_sig).ratio()
    containment = left_sig in right_sig or right_sig in left_sig
    return containment or jaccard >= 0.56 or sequence >= 0.73


def confidence_label(score: float) -> str:
    if score >= 0.8:
        return "High"
    if score >= 0.65:
        return "Medium"
    if score >= 0.5:
        return "Low"
    return "Very Low"


def build_mission_findings(
    claims: List[ResearchClaim],
    max_findings: int = 30,
) -> List[Dict[str, Any]]:
    if not claims:
        return []

    curated = [claim for claim in claims if is_high_signal_claim(claim)]
    source_claims = curated or sorted(claims, key=claim_presentation_score, reverse=True)[:12]
    ordered = sorted(
        source_claims,
        key=lambda claim: (
            claim_support_count(claim),
            claim_presentation_score(claim),
            claim_confidence(claim),
        ),
        reverse=True,
    )

    groups: List[List[ResearchClaim]] = []
    for claim in ordered:
        placed = False
        for group in groups:
            if claims_are_similar(claim, group[0]):
                group.append(claim)
                placed = True
                break
        if not placed:
            groups.append([claim])

    findings: List[Dict[str, Any]] = []
    for group in groups:
        primary = max(group, key=claim_presentation_score)
        paper_titles: List[str] = []
        paper_ids = set()
        evidence_sections = set()
        total_support = 0

        for claim in group:
            paper_ids.add(str(claim.paper_id))
            if claim.paper_title and claim.paper_title not in paper_titles:
                paper_titles.append(claim.paper_title)
            evidence_sections.update(claim_evidence_sections(claim))
            total_support += claim_support_count(claim)

        finding = {
            "id": str(primary.id),
            "claim_text": claim_text(primary),
            "statement_raw": primary.statement_raw,
            "statement_normalized": primary.statement_normalized,
            "claim_type": claim_type_value(primary),
            "direction": claim_direction_value(primary),
            "confidence_score": round(max(claim_confidence(claim) for claim in group), 3),
            "composite_confidence": round(max(claim_confidence(claim) for claim in group), 3),
            "confidence_label": confidence_label(max(claim_confidence(claim) for claim in group)),
            "paper_title": primary.paper_title or "Unknown",
            "paper_count": len(paper_ids),
            "paper_titles": paper_titles[:5],
            "supporting_claim_count": len(group),
            "supporting_evidence_count": total_support,
            "intervention_canonical": primary.intervention_canonical,
            "outcome_canonical": primary.outcome_canonical,
            "section_source": claim_section(primary),
            "section_source_code": claim_section(primary),
            "validation_status": "VALID",
            "mission_relevance": _enum_value(primary.mission_relevance, "secondary").lower(),
            "evidence_sections": sorted(section for section in evidence_sections if section),
            "aggregation_scope": "mission_finding",
            "raw_claim_ids": [str(claim.id) for claim in group],
            "extracted_at": primary.extraction_timestamp.isoformat() if primary.extraction_timestamp else None,
        }
        finding.update(
            describe_evidence_source(
                primary_section=finding["section_source_code"],
                evidence_sections=finding["evidence_sections"],
            )
        )
        finding["section_source"] = finding["evidence_source_label"]
        findings.append(finding)

    findings.sort(
        key=lambda finding: (
            finding["paper_count"],
            finding["confidence_score"],
            finding["supporting_evidence_count"],
        ),
        reverse=True,
    )

    for rank, finding in enumerate(findings[:max_findings], 1):
        finding["rank"] = rank

    return findings[:max_findings]


def summarize_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(findings)
    confidences = [float(finding.get("confidence_score", 0.0) or 0.0) for finding in findings]
    by_type = Counter(finding.get("claim_type") for finding in findings if finding.get("claim_type"))
    by_direction = Counter(finding.get("direction") for finding in findings if finding.get("direction"))
    by_section = Counter(finding.get("section_source") for finding in findings if finding.get("section_source"))

    if confidences:
        sorted_conf = sorted(confidences)
        p25_idx = len(sorted_conf) // 4
        p50_idx = len(sorted_conf) // 2
        p75_idx = (3 * len(sorted_conf)) // 4
        confidence_stats = {
            "mean": round(sum(confidences) / len(confidences), 3),
            "min": round(min(confidences), 3),
            "max": round(max(confidences), 3),
            "p25": round(sorted_conf[p25_idx], 3),
            "median": round(sorted_conf[p50_idx], 3),
            "p75": round(sorted_conf[p75_idx], 3),
        }
    else:
        confidence_stats = {}

    return {
        "total_findings": total,
        "valid_findings": total,
        "percentage_valid": 100.0 if total else 0.0,
        "by_type": dict(by_type),
        "by_direction": dict(by_direction),
        "by_section": dict(by_section),
        "confidence_statistics": confidence_stats,
    }

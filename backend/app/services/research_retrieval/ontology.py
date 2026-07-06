"""Rule-based biomedical ontology expansions for common entities."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Brand → generic drug, class, MeSH-friendly terms
DRUG_ONTOLOGY: Dict[str, Dict[str, object]] = {
    "ozempic": {
        "canonical": "semaglutide",
        "drug_class": "GLP-1 receptor agonist",
        "synonyms": ["ozempic", "semaglutide", "wegovy", "rybelsus"],
        "mesh": ["Semaglutide", "Glucagon-Like Peptide-1 Receptor Agonists"],
    },
    "wegovy": {
        "canonical": "semaglutide",
        "drug_class": "GLP-1 receptor agonist",
        "synonyms": ["wegovy", "semaglutide", "ozempic"],
        "mesh": ["Semaglutide", "Anti-Obesity Agents"],
    },
    "mounjaro": {
        "canonical": "tirzepatide",
        "drug_class": "GLP-1/GIP dual agonist",
        "synonyms": ["mounjaro", "tirzepatide", "zepbound"],
        "mesh": ["Tirzepatide"],
    },
    "metformin": {
        "canonical": "metformin",
        "drug_class": "biguanide antidiabetic",
        "synonyms": ["metformin", "glucophage"],
        "mesh": ["Metformin", "Hypoglycemic Agents"],
    },
}

# Intent keywords → coverage dimensions for gap-fill
MEDICAL_SAFETY_DIMENSIONS = [
    "long-term safety",
    "adverse effects",
    "cardiovascular outcomes",
    "mortality",
    "kidney effects",
    "liver effects",
    "pancreatitis",
    "gastrointestinal effects",
    "thyroid cancer",
    "muscle loss",
    "chronic use",
    "efficacy",
]

STUDY_TYPE_PHRASES = {
    "systematic review": ["systematic review", "meta-analysis"],
    "meta-analysis": ["meta-analysis", "pooled analysis"],
    "rct": ["randomized controlled trial", "RCT", "clinical trial"],
    "observational": ["cohort study", "observational study", "real-world"],
    "guideline": ["clinical practice guideline", "consensus statement"],
}


def lookup_drug(term: str) -> Optional[Dict[str, object]]:
    key = (term or "").strip().lower()
    return DRUG_ONTOLOGY.get(key)


def expand_entity_from_text(text: str) -> List[Tuple[str, Dict[str, object]]]:
    """Return (matched_term, ontology_entry) for drugs found in text."""
    lower = (text or "").lower()
    found: List[Tuple[str, Dict[str, object]]] = []
    seen = set()
    for brand, entry in DRUG_ONTOLOGY.items():
        synonyms = entry.get("synonyms", [])
        for syn in synonyms:
            if syn.lower() in lower and brand not in seen:
                seen.add(brand)
                found.append((brand, entry))
                break
    return found


def default_medical_dimensions(query: str) -> List[str]:
    lower = (query or "").lower()
    dims = list(MEDICAL_SAFETY_DIMENSIONS)
    if "weight" in lower or "obesity" in lower:
        dims.extend(["weight loss", "body composition"])
    if "diabetes" in lower or "glycemic" in lower:
        dims.extend(["glycemic control", "HbA1c"])
    return list(dict.fromkeys(dims))

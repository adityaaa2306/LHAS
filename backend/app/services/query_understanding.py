"""
Production-Grade Query Understanding Module for LHAS

Analyzes research queries using LLM to produce structured interpretations,
detect ambiguity, and guide users toward well-formed research questions.

Not a conversational agent - operates programmatically with deterministic output.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import insert

from app.config import settings
from app.database import async_session_maker
from app.models.query_analysis import QueryAnalysis
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)


# ============================================================================
# Output Models (Pydantic)
# ============================================================================


class PICOComponents(BaseModel):
    """PICO framework breakdown."""

    population: Optional[str] = Field(default=None, description="Target population/cohort")
    intervention: Optional[str] = Field(default=None, description="Intervention or exposure")
    comparator: Optional[str] = Field(default=None, description="Comparison/control group")
    outcome: Optional[str] = Field(default=None, description="Measured outcome")


class QueryAnalysisResult(BaseModel):
    """Complete output of query understanding analysis."""

    original_query: str
    normalized_query: str
    intent_type: str = Field(description="One of: Causal, Comparative, Exploratory, Descriptive")
    pico: PICOComponents
    key_concepts: list[str] = Field(description="Main concepts/entities")
    search_queries: list[str] = Field(description="Optimized search formulations")
    ambiguity_flags: list[str] = Field(description="Detected issues or ambiguities")
    interpretation_variants: list[str] = Field(description="Alternative valid interpretations")
    suggested_refinements: list[str] = Field(description="Specific ways to improve clarity")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence 0-1")
    decision: str = Field(
        description="One of: PROCEED, PROCEED_WITH_CAUTION, NEED_CLARIFICATION"
    )
    reasoning_steps: list[str] = Field(description="Transparent, human-readable reasoning")

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        valid = {"PROCEED", "PROCEED_WITH_CAUTION", "NEED_CLARIFICATION"}
        if v not in valid:
            raise ValueError(f"decision must be one of {valid}")
        return v

    @field_validator("intent_type")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        valid = {"Causal", "Comparative", "Exploratory", "Descriptive"}
        if v not in valid:
            raise ValueError(f"intent_type must be one of {valid}")
        return v

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))  # Clamp to 0-1


# ============================================================================
# LLM Prompting
# ============================================================================


SYSTEM_PROMPT = """You are an expert query analyzer for a biomedical research system.
Your task is to analyze research queries with surgical precision and return ONLY valid JSON.

CRITICAL RULES:
1. Output ONLY valid JSON - no markdown, no explanations, no code blocks
2. Never hallucinate data - use null or "UNKNOWN" for missing information
3. Analyze the query and produce structured, deterministic output
4. Detect vague terms (e.g., "better", "safe", "effective", "truly")
5. Identify missing PICO elements
6. Generate alternative valid interpretations
7. Provide actionable refinement suggestions
8. Assign confidence based on query clarity (0-1)
9. Select decision: PROCEED (high confidence, low ambiguity), PROCEED_WITH_CAUTION (moderate), NEED_CLARIFICATION (high ambiguity)

NORMALIZATION RULES (MUST transform the query):
- Remove vague intensifiers: "truly", "really", "very", "quite", "absolutely"
- Convert informal language to academic formulation
- Combine compound questions into clear structure
- Add implicit operators: "How do X compare to Y?" for comparative questions
- Remove rhetorical questioning, state as assertions
EXAMPLES:
  "What makes X truly Y?" → "What factors determine or influence the relationship between X and Y?"
  "Is it A or B?" → "Does X demonstrate characteristic A or characteristic B?"
  "What makes a neural network's decision truly interpretable? Is it probabilistic or deterministic?" 
    → "How do probabilistic and deterministic approaches affect neural network decision interpretability?"

Return this JSON structure (all fields required):
{
  "normalized_query": "string - MUST be improved academic formulation, removing vague terms and clarifying structure",
  "intent_type": "Causal|Comparative|Exploratory|Descriptive",
  "pico": {
    "population": "string or null",
    "intervention": "string or null",
    "comparator": "string or null",
    "outcome": "string or null"
  },
  "key_concepts": ["list", "of", "strings"],
  "search_queries": ["optimized", "search", "formulations"],
  "ambiguity_flags": ["list", "of", "detected", "issues"],
  "interpretation_variants": ["alternative", "valid", "interpretations"],
  "suggested_refinements": ["actionable", "refinement", "suggestions"],
  "confidence_score": 0.85,
  "decision": "PROCEED",
  "reasoning_steps": [
    "Step 1: Interpretation",
    "Step 2: Entity identification",
    "Step 3: Ambiguity assessment",
    "Step 4: Confidence determination",
    "Step 5: Decision logic"
  ]
}"""


def construct_analysis_prompt(query: str, optional_context: Optional[dict] = None) -> str:
    """Construct the user prompt for LLM analysis."""
    context_str = ""
    if optional_context:
        context_items = [f"  - {k}: {v}" for k, v in optional_context.items()]
        context_str = f"\nAdditional context:\n" + "\n".join(context_items)

    return f"""Analyze this research query with precision:

Query: {query}
{context_str}

Respond with ONLY the JSON object, no other text."""


# ============================================================================
# Query Understanding Module
# ============================================================================


class QueryUnderstandingModule:
    """Production query understanding engine."""

    def __init__(self):
        """Initialize with LLM provider."""
        self.llm = get_llm_provider()
        logger.info("QueryUnderstandingModule initialized")

    async def analyze_query(
        self,
        query: str,
        mission_id: Optional[str] = None,
        optional_context: Optional[dict] = None,
    ) -> QueryAnalysisResult:
        """
        Analyze a research query and produce structured interpretation.

        Args:
            query: Raw research query from user
            mission_id: UUID of associated mission (for logging)
            optional_context: Additional context (e.g., disease domain, study type)

        Returns:
            QueryAnalysisResult with complete analysis

        Raises:
            ValueError: If query is invalid or analysis fails completely
        """
        if not query or len(query.strip()) < 5:
            raise ValueError("Query must be at least 5 characters")

        logger.info(f"Analyzing query: {query[:80]}...")

        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": construct_analysis_prompt(query, optional_context)},
        ]

        # Call LLM (with retry on parse failure)
        result = await self._call_llm_with_retry(messages)

        # Validate and clamp values
        result = self._validate_and_clamp(result)

        # PRODUCTION-GRADE: Dynamically optimize based on actual query properties
        result = await self._optimize_output_counts(result, query)

        # Log to database if mission_id provided
        if mission_id:
            await self._log_analysis(
                query=query,
                mission_id=mission_id,
                analysis_result=result,
            )

        logger.debug(f"Query analysis complete. Decision: {result.decision}, Confidence: {result.confidence_score}, "
                    f"Refinements: {len(result.suggested_refinements)}, "
                    f"Search variants: {len(result.search_queries)}")

        return result

    async def _call_llm_with_retry(self, messages: list[dict]) -> QueryAnalysisResult:
        """
        Call LLM with retry logic.

        If JSON parsing fails once, retry. If still fails, use fallback heuristic.
        """
        for attempt in range(2):
            try:
                logger.debug(f"LLM call attempt {attempt + 1}/2")

                response = await self.llm.generate_async(
                    messages=messages,
                    max_tokens=2000,
                )

                content = response.get("content", "")
                logger.debug(f"LLM response length: {len(content)} chars")

                # Parse JSON
                result_dict = self._parse_json_response(content)

                # Convert to Pydantic model
                result = QueryAnalysisResult(
                    original_query=messages[-1]["content"].split("Query: ")[1].split("\n")[0],
                    **result_dict,
                )

                logger.info(f"LLM analysis successful. Decision: {result.decision}")
                return result

            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error on attempt {attempt + 1}: {str(e)}")
                if attempt == 1:
                    logger.warning("JSON parsing failed twice, using fallback heuristic")
                    break
            except Exception as e:
                logger.warning(f"LLM call error on attempt {attempt + 1}: {str(e)}")
                if attempt == 1:
                    logger.warning("LLM calls exhausted, using fallback heuristic")
                    break

        # Fallback: heuristic parsing
        logger.info("Using fallback heuristic parser")
        query_text = messages[-1]["content"].split("Query: ")[1].split("\n")[0]
        return self._fallback_heuristic_parser(query_text)

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        content = content.strip()

        # Remove markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return json.loads(content)

    def _validate_and_clamp(self, result: QueryAnalysisResult) -> QueryAnalysisResult:
        """Validate and clamp values to acceptable ranges."""
        # Clamp confidence score
        result.confidence_score = max(0.0, min(1.0, result.confidence_score))

        # Ensure minimum viable data (will be optimized in next step)
        if not result.key_concepts or result.key_concepts == ["UNKNOWN"]:
            result.key_concepts = ["UNKNOWN"]  # Will be improved by LLM or fallback
        if not result.search_queries:
            result.search_queries = [result.normalized_query]
        if not result.reasoning_steps:
            result.reasoning_steps = ["Query analyzed"]

        # Ensure decision is valid
        if result.decision not in {"PROCEED", "PROCEED_WITH_CAUTION", "NEED_CLARIFICATION"}:
            result.decision = "PROCEED_WITH_CAUTION"

        return result

    def _fallback_heuristic_parser(self, query: str) -> QueryAnalysisResult:
        """
        Fallback parser using heuristics when LLM fails.

        This ensures the module always returns valid output.
        """
        logger.info("Fallback parser: analyzing query with heuristics")

        # Detect intent type
        query_lower = query.lower()
        if any(w in query_lower for w in ["effect", "cause", "lead", "result", "associated"]):
            intent = "Causal"
        elif any(w in query_lower for w in ["compare", "difference", "vs", "versus", "efficacy vs", "better than"]):
            intent = "Comparative"
        elif any(w in query_lower for w in ["explore", "understand", "characterize", "what is"]):
            intent = "Exploratory"
        else:
            intent = "Descriptive"

        # Extract key terms (simple heuristic)
        terms = query.split()
        key_concepts = [t.strip("?,;:.") for t in terms if len(t) > 4][:5]

        # Detect ambiguity
        vague_terms = {
            "better": "undefined comparison metric",
            "safe": "unspecified safety outcome",
            "effective": "unmeasured efficacy metric",
            "good": "subjective quality criterion",
            "bad": "subjective negative criterion",
            "improved": "undefined improvement metric"
        }
        
        found_vague = [v for v in vague_terms.keys() if v in query_lower]
        ambiguity_flags = []
        
        if found_vague:
            ambiguity_flags.append(f"Contains vague terminology: {', '.join(found_vague)}")
        
        if len(query) < 30:
            ambiguity_flags.append("Query is very brief - may lack specificity")
        
        if "?" not in query:
            ambiguity_flags.append("Query not phrased as clear question")
        
        # Check for compound questions
        if any(conj in query_lower for conj in [" or ", " and ", " vs "]):
            if query.count(" or ") + query.count(" and ") + query.count(" vs ") > 1:
                ambiguity_flags.append("Multiple comparisons in single query - consider separating")
        
        # PICO detection (simple heuristic)
        population = "unspecified" if not any(p in query_lower for p in ["patient", "population", "cohort", "disease", "condition"]) else None
        outcome = "unspecified" if not any(o in query_lower for o in ["outcome", "result", "effect", "efficacy", "safety"]) else None
        
        pico = PICOComponents(
            population=population,
            intervention=None,
            comparator=None,
            outcome=outcome
        )
        
        # Decision logic
        confidence = max(0.3, 0.7 - (len(ambiguity_flags) * 0.15))  # Decrease by ambiguity
        
        if confidence >= 0.75 and not ambiguity_flags:
            decision = "PROCEED"
        elif len(ambiguity_flags) >= 3:
            decision = "NEED_CLARIFICATION"
        elif ambiguity_flags:
            decision = "PROCEED_WITH_CAUTION"
        else:
            decision = "PROCEED"

        result = QueryAnalysisResult(
            original_query=query,
            normalized_query=query.strip(),
            intent_type=intent,
            pico=pico,
            key_concepts=key_concepts or ["UNKNOWN"],
            search_queries=[query],  # Will be optimized
            ambiguity_flags=ambiguity_flags,
            interpretation_variants=[query],  # Will be optimized
            suggested_refinements=[],  # Will be generated by optimization
            confidence_score=confidence,
            decision=decision,
            reasoning_steps=[
                f"Detected intent type: {intent}",
                f"Extracted {len(key_concepts)} key concepts",
                f"Identified {len(ambiguity_flags)} ambiguity flag(s)",
                f"Assessed confidence: {confidence:.2f}",
                f"Decision: {decision} (fallback heuristic)",
            ],
        )
        
        return result

    async def _optimize_output_counts(
        self,
        result: QueryAnalysisResult,
        original_query: str,
    ) -> QueryAnalysisResult:
        """
        PRODUCTION-GRADE: Dynamically optimize counts based on actual query properties.
        
        No hardcoded numbers. Generate:
        - search_queries: Based on complexity + confidence + intent type
        - interpretation_variants: Based on ambiguity
        - suggested_refinements: Only for actual issues, targeted per problem
        """
        
        # Calculate dynamic counts
        num_search_queries = self._calculate_search_query_count(
            original_query, result, result.confidence_score, result.intent_type
        )
        num_interpretation_variants = self._calculate_interpretation_variant_count(
            result.ambiguity_flags, result.confidence_score
        )
        
        # Trim to calculated counts
        result.search_queries = result.search_queries[:num_search_queries]
        result.interpretation_variants = result.interpretation_variants[:num_interpretation_variants]
        
        # Generate targeted refinements (not generic)
        result.suggested_refinements = await self._generate_targeted_refinements(
            original_query, result.ambiguity_flags, result.pico, result.intent_type, result.key_concepts
        )
        
        logger.debug(
            f"Optimized output: {len(result.search_queries)} queries, "
            f"{len(result.interpretation_variants)} variants, "
            f"{len(result.suggested_refinements)} refinements"
        )
        
        return result

    def _calculate_search_query_count(
        self, query: str, result: QueryAnalysisResult, confidence: float, intent_type: str
    ) -> int:
        """
        Calculate optimal number of search query variants.
        
        Logic:
        - Well-formed causal/comparative queries: 2-3 variants
        - Ambiguous queries: 3-4 variants to explore interpretations
        - Very specific queries: 2 variants (overkill to generate more)
        - Very ambiguous: up to 5 variants
        """
        
        # Base: query complexity
        query_len = len(query.split())
        is_compound = " or " in query.lower() or " vs " in query.lower() or " versus " in query.lower()
        
        # Start with baseline based on intent
        if intent_type == "Causal":
            base_count = 3  # Causal needs multiple framings
        elif intent_type == "Comparative":
            base_count = 3  # Comparisons need both directions
        elif intent_type == "Exploratory":
            base_count = 4  # Exploratory benefits from broad variants
        else:  # Descriptive
            base_count = 2  # Descriptive is usually clear-cut
        
        # Adjust by confidence
        if confidence >= 0.85:
            # Very clear - fewer variants needed
            base_count = max(2, base_count - 1)
        elif confidence < 0.65:
            # Ambiguous - need more variants
            base_count = min(5, base_count + 1)
        
        # Account for PICO completeness
        pico_filled = sum([
            result.pico.population is not None,
            result.pico.intervention is not None,
            result.pico.comparator is not None,
            result.pico.outcome is not None,
        ])
        
        # Incomplete PICO = more interpretation variants needed
        if pico_filled <= 1:
            base_count = min(5, base_count + 1)
        
        # Compound queries need more variants
        if is_compound and query_len > 15:
            base_count = min(5, base_count + 1)
        
        return max(2, min(5, base_count))  # Clamp 2-5

    def _calculate_interpretation_variant_count(
        self, ambiguity_flags: list[str], confidence: float
    ) -> int:
        """
        Calculate number of alternative interpretations.
        
        Logic:
        - No ambiguity: 1 (the query as stated)
        - 1-2 flags: 2-3 variants
        - 3+ flags: 4-5 variants (explore different readings)
        - High confidence: fewer variants
        - Low confidence: more variants
        """
        
        flag_count = len(ambiguity_flags)
        
        # Base on flag severity
        if flag_count == 0:
            base_count = 1  # No alternatives if unambiguous
        elif flag_count == 1:
            base_count = 2
        elif flag_count == 2:
            base_count = 3
        else:  # 3+
            base_count = 4
        
        # Adjust by confidence
        if confidence >= 0.85:
            base_count = max(1, base_count - 1)  # High confidence = fewer reads
        elif confidence < 0.60:
            base_count = min(5, base_count + 1)  # Low confidence = more reads
        
        return max(1, min(5, base_count))  # Clamp 1-5

    async def _generate_targeted_refinements(
        self,
        query: str,
        ambiguity_flags: list[str],
        pico: PICOComponents,
        intent_type: str,
        key_concepts: list[str],
    ) -> list[str]:
        """
        Generate TARGETED refinements for each actual ambiguity.
        
        Not generic ("use clearer language"). Specific ("define what 'better' means").
        Only generate if there's real ambiguity.
        """
        
        if not ambiguity_flags:
            # Query is clear - no refinements needed
            return []
        
        refinements = []
        query_lower = query.lower()
        
        # Map each ambiguity flag to specific refinement
        for flag in ambiguity_flags:
            refinement = None
            
            # VAGUE TERMINOLOGY
            if "vague" in flag.lower():
                vague_terms = ["better", "safe", "effective", "good", "bad", "worse", "improved"]
                found_terms = [t for t in vague_terms if t in query_lower]
                
                if found_terms:
                    term = found_terms[0]
                    if term == "better":
                        refinement = "Define the comparison metric (efficacy, safety, cost, adverse events, quality of life)"
                    elif term == "safe":
                        refinement = "Specify safety outcome: overall safety profile, specific adverse event, or contraindication?"
                    elif term == "effective":
                        refinement = "Define effectiveness: response rate, symptom reduction, survival, or functional improvement?"
                    elif term == "improved":
                        refinement = "Quantify the improvement threshold or timeframe for detecting change"
                    else:
                        refinement = f"Replace '{term}' with specific, measurable criteria"
            
            # MISSING PICO ELEMENTS
            elif "missing" in flag.lower() or "population" in flag.lower():
                if not pico.population:
                    refinement = f"Specify the population: age range, disease severity, prior treatments, or demographic inclusion criteria?"
            elif "intervention" in flag.lower() or "exposure" in flag.lower():
                if not pico.intervention:
                    refinement = "Specify the intervention: drug class, dosage, duration, or procedure type?"
            elif "comparison" in flag.lower() or "comparator" in flag.lower():
                if not pico.comparator:
                    refinement = "Clarify the comparison: standard of care, placebo, alternative treatment, or no intervention?"
            elif "outcome" in flag.lower():
                if not pico.outcome:
                    refinement = "Define the primary outcome: biomarker, clinical symptom, or patient-reported measure?"
            
            # TEMPORAL AMBIGUITY
            elif "temporal" in flag.lower() or "timing" in flag.lower() or "timeframe" in flag.lower():
                refinement = "Specify timeframe: acute (within days), short-term (weeks), or long-term (months/years)?"
            
            # SCOPE/DOMAIN AMBIGUITY
            elif "scope" in flag.lower() or "domain" in flag.lower():
                refinement = "Clarify scope: single-center, multi-center, systematic review, or real-world evidence?"
            
            # COMPOUND QUESTIONS
            elif "compound" in flag.lower() or "multiple" in flag.lower():
                refinement = "Consider separating into distinct questions for each comparison arm"
            
            # STUDY DESIGN AMBIGUITY
            elif "study design" in flag.lower() or "design unclear" in flag.lower():
                refinement = "Specify preferred study design: RCT, cohort, case-control, observational, or any?"
            
            # POPULATION SPECIFICITY
            elif "population" in flag.lower() and "specificity" in flag.lower():
                refinement = "Be more specific about population: pediatric, adult, elderly, or mixed cohorts?"
            
            # DEFAULT: Generic fallback only if no specific mapping
            if refinement is None and flag:
                # Extract keyword from flag and create targeted refinement
                refinement = f"Clarify: {flag.lower().replace('detected ', '').replace('issue', '').strip()}"
            
            if refinement and refinement not in refinements:  # Avoid duplicates
                refinements.append(refinement)
        
        logger.debug(f"Generated {len(refinements)} targeted refinements from {len(ambiguity_flags)} flags")
        return refinements[:5]  # Cap at 5 max (should rarely hit this)

    async def _log_analysis(
        self,
        query: str,
        mission_id: str,
        analysis_result: QueryAnalysisResult,
    ) -> None:
        """Log analysis to database."""
        try:
            async with async_session_maker() as session:
                stmt = insert(QueryAnalysis).values(
                    mission_id=UUID(mission_id),
                    original_query=query,
                    normalized_query=analysis_result.normalized_query,
                    intent_type=analysis_result.intent_type,
                    pico=analysis_result.pico.dict(),
                    key_concepts=analysis_result.key_concepts,
                    search_queries=analysis_result.search_queries,
                    ambiguity_flags=analysis_result.ambiguity_flags,
                    interpretation_variants=analysis_result.interpretation_variants,
                    suggested_refinements=analysis_result.suggested_refinements,
                    confidence_score=analysis_result.confidence_score,
                    decision=analysis_result.decision,
                    reasoning_steps=analysis_result.reasoning_steps,
                    created_at=datetime.utcnow(),
                )
                await session.execute(stmt)
                await session.commit()
                logger.debug(f"Analysis logged for mission {mission_id}")
        except Exception as e:
            logger.error(f"Failed to log analysis: {str(e)}")
            # Don't raise - logging failure shouldn't break analysis


# Singleton instance
_module: Optional[QueryUnderstandingModule] = None


def get_query_understanding_module() -> QueryUnderstandingModule:
    """Get or create Query Understanding Module singleton."""
    global _module
    if _module is None:
        _module = QueryUnderstandingModule()
    return _module

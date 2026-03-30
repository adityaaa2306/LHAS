"""
Query Refinement and Clarification Module (Module 2)

Analyzes research queries and generates contextual clarification questions
to transform vague queries into precise, structured search queries.

Steps:
1. Analyze query for clarity and specificity
2. Identify missing dimensions (domain, methodology, focus, population, etc.)
3. Generate targeted clarification questions if needed
4. Incorporate user responses to build refined query
5. Output final query optimized for semantic search/APIs
"""

import json
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)


# ============================================================================
# Output Models (Pydantic)
# ============================================================================


class ClarificationQuestion(BaseModel):
    """Single clarification question with options."""
    question: str
    options: list[str] = Field(min_items=4, description="3-5 options including 'Other'")


class ClarificationResponse(BaseModel):
    """User's response to a clarification question."""
    question: str
    selected_option: str
    user_input: Optional[str] = None


class QueryRefinementRequest(BaseModel):
    """Request for query refinement."""
    user_query: str
    previous_clarifications: Optional[list[ClarificationResponse]] = None


class QueryRefinementResponse(BaseModel):
    """Response from query refinement."""
    status: str = Field(description="'needs_clarification' or 'final'")
    clarification_questions: Optional[list[ClarificationQuestion]] = None
    refined_query: Optional[str] = None
    applied_filters: Optional[dict[str, Any]] = None


# ============================================================================
# LLM Prompts
# ============================================================================


CLARITY_ANALYSIS_PROMPT = """Analyze this research query for clarity and specificity:

Query: {query}

Respond with ONLY valid JSON:
{{
  "clarity_score": 0.0-1.0,
  "is_sufficiently_clear": boolean (true if >0.7 clarity or has strong specificity),
  "missing_dimensions": ["dimension1", "dimension2", ...],
  "identified_topics": ["topic1", "topic2", ...],
  "reasoning": "brief explanation"
}}"""


CLARIFICATION_QUESTIONS_PROMPT = """Generate 1-2 targeted clarification questions for this research query.

Query: {query}
Topics identified: {topics}
Missing dimensions: {missing_dimensions}

For EACH question, include 3-5 specific, diverse options relevant to the topic.
ALWAYS include "Other" as the last option.

Respond with ONLY valid JSON:
{{
  "clarification_questions": [
    {{
      "question": "specific question about the most important missing dimension",
      "options": ["specific_option_1", "specific_option_2", "specific_option_3", "Other"]
    }}
  ],
  "rationale": "why these questions"
}}"""


FINAL_QUERY_GENERATION_PROMPT = """Generate a final refined query for research retrieval.

Original query: {query}
User clarifications:
{clarifications}

Respond with ONLY valid JSON:
{{
  "refined_query": "specific, structured query optimized for semantic search",
  "applied_filters": {{
    "domain": "identified domain or null",
    "methodology": "identified methodology or null",
    "focus": "identified focus or null",
    "population": "identified population or null",
    "time_period": "identified time period or null",
    "other_filters": {{}}
  }},
  "reasoning": "how clarifications improved the query"
}}"""


# ============================================================================
# Query Refinement Module
# ============================================================================


class QueryRefinementModule:
    """Production query refinement and clarification engine."""

    def __init__(self):
        """Initialize with LLM provider."""
        self.llm = get_llm_provider()
        logger.info("QueryRefinementModule initialized")

    async def refine_query(
        self,
        user_query: str,
        previous_clarifications: Optional[list[ClarificationResponse]] = None,
    ) -> QueryRefinementResponse:
        """
        Refine a research query through intelligent clarification.

        Args:
            user_query: Raw user research query
            previous_clarifications: Prior responses to clarification questions

        Returns:
            QueryRefinementResponse with either clarification questions or final refined query
        """
        if not user_query or len(user_query.strip()) < 5:
            raise ValueError("Query must be at least 5 characters")

        logger.info(f"Refining query: {user_query[:80]}...")

        # If we have previous clarifications, go straight to final query generation
        if previous_clarifications and len(previous_clarifications) > 0:
            logger.info("Previous clarifications found, generating final query")
            return await self._generate_final_query(user_query, previous_clarifications)

        # Otherwise: analyze clarity and generate clarification questions if needed
        clarity_analysis = await self._analyze_clarity(user_query)

        if clarity_analysis["is_sufficiently_clear"]:
            logger.info("Query is sufficiently clear, generating final query")
            return QueryRefinementResponse(
                status="final",
                refined_query=user_query,
                applied_filters=self._extract_filters_from_analysis(clarity_analysis),
            )

        # Generate clarification questions
        logger.info("Query needs clarification, generating questions")
        questions = await self._generate_clarification_questions(
            user_query,
            clarity_analysis["identified_topics"],
            clarity_analysis["missing_dimensions"],
        )

        return QueryRefinementResponse(
            status="needs_clarification",
            clarification_questions=questions,
        )

    async def _analyze_clarity(self, query: str) -> dict[str, Any]:
        """Analyze query for clarity and identify missing dimensions."""
        prompt = CLARITY_ANALYSIS_PROMPT.format(query=query)

        response = await self.llm.generate_async(
            messages=[
                {
                    "role": "system",
                    "content": "You are a research query analyzer. Analyze queries for clarity, specificity, and missing information. Output ONLY valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
        )

        content = response.get("content", "")
        logger.debug(f"Clarity analysis response: {content[:200]}")

        try:
            # Handle markdown code blocks if present
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse clarity analysis: {str(e)}")
            # Fallback: assume query needs clarification
            return {
                "clarity_score": 0.5,
                "is_sufficiently_clear": False,
                "missing_dimensions": ["domain", "focus", "methodology"],
                "identified_topics": self._extract_topics_heuristic(query),
                "reasoning": "Fallback analysis due to parse error",
            }

    async def _generate_clarification_questions(
        self,
        query: str,
        topics: list[str],
        missing_dimensions: list[str],
    ) -> list[ClarificationQuestion]:
        """Generate contextual clarification questions."""
        topics_str = ", ".join(topics) if topics else "general research"
        dims_str = ", ".join(missing_dimensions) if missing_dimensions else "domain, methodology"

        prompt = CLARIFICATION_QUESTIONS_PROMPT.format(
            query=query,
            topics=topics_str,
            missing_dimensions=dims_str,
        )

        response = await self.llm.generate_async(
            messages=[
                {
                    "role": "system",
                    "content": "You generate specific, targeted clarification questions for research queries. Output ONLY valid JSON with 'clarification_questions' array.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
        )

        content = response.get("content", "")
        logger.debug(f"Clarification questions response: {content[:200]}")

        try:
            # Handle markdown code blocks
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            questions = result.get("clarification_questions", [])

            # Validate and construct ClarificationQuestion objects
            validated_questions = []
            for q in questions:
                if isinstance(q, dict) and "question" in q and "options" in q:
                    # Ensure "Other" is in options
                    options = q["options"]
                    if "Other" not in options:
                        options.append("Other")
                    validated_questions.append(
                        ClarificationQuestion(question=q["question"], options=options)
                    )

            return validated_questions if validated_questions else self._fallback_clarification_questions(query)

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse clarification questions: {str(e)}")
            return self._fallback_clarification_questions(query)

    async def _generate_final_query(
        self,
        original_query: str,
        clarifications: list[ClarificationResponse],
    ) -> QueryRefinementResponse:
        """Generate final refined query from clarifications."""
        # Format clarifications for LLM
        clarifications_str = "\n".join(
            [
                f"Q: {c.question}\nA: {c.selected_option}" + (f" ({c.user_input})" if c.user_input else "")
                for c in clarifications
            ]
        )

        prompt = FINAL_QUERY_GENERATION_PROMPT.format(
            query=original_query,
            clarifications=clarifications_str,
        )

        response = await self.llm.generate_async(
            messages=[
                {
                    "role": "system",
                    "content": "You are a research query refinement expert. Generate refined, structured queries optimized for semantic search. Output ONLY valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
        )

        content = response.get("content", "")
        logger.debug(f"Final query response: {content[:200]}")

        try:
            # Handle markdown code blocks
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            refined_query = result.get("refined_query", original_query)
            applied_filters = result.get("applied_filters", {})

            logger.info(f"Final query generated: {refined_query[:100]}")

            return QueryRefinementResponse(
                status="final",
                refined_query=refined_query,
                applied_filters=applied_filters,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse final query generation: {str(e)}")
            # Fallback: return original query with extracted filters
            return QueryRefinementResponse(
                status="final",
                refined_query=original_query,
                applied_filters=self._extract_filters_from_clarifications(clarifications),
            )

    def _extract_topics_heuristic(self, query: str) -> list[str]:
        """Extract likely topics from query using heuristics."""
        # Simple heuristic: split on common connectors and take significant terms
        terms = query.split()
        topics = [t.strip("?,;:.") for t in terms if len(t) > 4][:3]
        return topics or [query.split()[0]] if query.split() else ["research"]

    def _extract_filters_from_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Extract filters from clarity analysis."""
        return {
            "clarity_score": analysis.get("clarity_score", 0.5),
            "topics": analysis.get("identified_topics", []),
            "missing_dimensions": analysis.get("missing_dimensions", []),
        }

    def _extract_filters_from_clarifications(
        self,
        clarifications: list[ClarificationResponse],
    ) -> dict[str, Any]:
        """Extract applied filters from user's clarification responses."""
        filters = {}
        for c in clarifications:
            if c.selected_option != "Other":
                filters[c.question] = c.selected_option
            elif c.user_input:
                filters[c.question] = c.user_input

        return filters

    def _fallback_clarification_questions(self, query: str) -> list[ClarificationQuestion]:
        """Fallback clarification questions when LLM fails."""
        logger.info("Using fallback clarification questions")

        return [
            ClarificationQuestion(
                question="What is the primary domain or field for your research?",
                options=["biomedical/health", "technology/AI", "social sciences", "environmental", "Other"],
            ),
            ClarificationQuestion(
                question="What is your main research focus or outcome of interest?",
                options=["mechanism/causation", "comparison/effectiveness", "epidemiology/prevalence", "safety/risk", "Other"],
            ),
        ]


# ============================================================================
# Singleton Instance
# ============================================================================


_refinement_module_instance: Optional[QueryRefinementModule] = None


def get_query_refinement_module() -> QueryRefinementModule:
    """Get or create singleton instance of QueryRefinementModule."""
    global _refinement_module_instance
    if _refinement_module_instance is None:
        _refinement_module_instance = QueryRefinementModule()
    return _refinement_module_instance

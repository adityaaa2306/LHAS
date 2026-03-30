"""
Module 3: UI Clarification Generator

Converts Query Understanding analysis into conversational, user-friendly clarification questions.
Designed for seamless frontend integration with natural language interactions.
"""

import re
from typing import Optional
from pydantic import BaseModel


class ClarificationOption(BaseModel):
    """Single clarification option for user selection"""
    text: str
    value: Optional[str] = None  # Can store code/system value if needed


class ClarificationQuestion(BaseModel):
    """Single clarification question with options"""
    question: str
    options: list[str]  # List of option texts + "Other" as last


class ClarificationResponse(BaseModel):
    """API response with clarification questions"""
    message: str
    questions: list[ClarificationQuestion]
    requires_clarification: bool


class UIClarificationGenerator:
    """
    Converts technical query analysis into conversational UI questions.
    
    Rules:
    - Uses natural language (no technical terms)
    - Derives from interpretation_variants and key_concepts
    - Max 1-2 questions to avoid overwhelming users
    - Always includes "Other" option for user input
    """
    
    def __init__(self):
        self.base_message = "To give you a better answer, I need a bit more clarity:"
    
    def generate_from_analysis(self, analysis_data: dict) -> ClarificationResponse:
        """
        Convert Query Understanding output to user-friendly questions.
        
        Args:
            analysis_data: Output from QueryUnderstandingModule
                Expected keys:
                - decision (str): PROCEED, PROCEED_WITH_CAUTION, NEED_CLARIFICATION
                - ambiguity_flags (list): Technical issues found
                - interpretation_variants (list): Different ways to interpret query
                - key_concepts (list): Main terms in query
                - suggested_refinements (list): Suggested improvements
        
        Returns:
            ClarificationResponse with conversational questions
        """
        decision = analysis_data.get("decision", "PROCEED")
        
        # Only generate questions if clarification is needed
        if decision != "NEED_CLARIFICATION":
            return ClarificationResponse(
                message="Your query looks good!",
                questions=[],
                requires_clarification=False
            )
        
        questions = []
        
        # Extract ambiguous terms from flags
        ambiguity_flags = analysis_data.get("ambiguity_flags", [])
        interpretation_variants = analysis_data.get("interpretation_variants", [])
        key_concepts = analysis_data.get("key_concepts", [])
        
        # Strategy 1: If there are interpretation variants, convert to question
        if interpretation_variants and len(interpretation_variants) > 0:
            question = self._create_interpretation_question(
                analysis_data.get("original_query", ""),
                interpretation_variants,
                key_concepts
            )
            if question:
                questions.append(question)
        
        # Strategy 2: If there are ambiguous terms, create refinement question
        if len(questions) < 2 and ambiguity_flags:
            question = self._create_refinement_question(
                ambiguity_flags,
                analysis_data.get("suggested_refinements", [])
            )
            if question:
                questions.append(question)
        
        return ClarificationResponse(
            message=self.base_message,
            questions=questions,
            requires_clarification=len(questions) > 0
        )
    
    def _create_interpretation_question(
        self,
        original_query: str,
        interpretation_variants: list[str],
        key_concepts: list[str]
    ) -> Optional[ClarificationQuestion]:
        """
        Create a question from interpretation variants.
        
        Extracts vague terms and offers different interpretations as options.
        """
        if not interpretation_variants:
            return None
        
        # Find the vague term in original query
        vague_term = self._extract_vague_term(original_query, interpretation_variants)
        
        if vague_term:
            question_text = f"What do you mean by '{vague_term}'?"
        else:
            question_text = "How would you like me to interpret your query?"
        
        # Convert interpretation variants to natural options
        options = []
        for variant in interpretation_variants[:4]:  # Limit to 4 options
            # Clean up variant text
            cleaned = variant.strip()
            # Remove question marks if present
            if cleaned.endswith("?"):
                cleaned = cleaned[:-1].strip()
            options.append(cleaned)
        
        # Add "Other" as final option
        options.append("Other")
        
        return ClarificationQuestion(
            question=question_text,
            options=options
        )
    
    def _create_refinement_question(
        self,
        ambiguity_flags: list[str],
        suggested_refinements: list[str]
    ) -> Optional[ClarificationQuestion]:
        """
        Create a question from ambiguity flags and suggested refinements.
        
        Offers specific refinements as options to narrow down the query.
        """
        if not suggested_refinements:
            return None
        
        question_text = "Would you like to narrow down your query?"
        
        # Convert suggestions to options
        options = []
        for refinement in suggested_refinements[:4]:  # Limit to 4
            cleaned = refinement.strip()
            # Remove "Specify the " or similar prefixes
            cleaned = re.sub(r'^specify|define|clarify|add', '', cleaned, flags=re.IGNORECASE).strip()
            if cleaned:
                options.append(cleaned)
        
        if not options:
            return None
        
        options.append("Other")
        
        return ClarificationQuestion(
            question=question_text,
            options=options
        )
    
    def _extract_vague_term(
        self,
        original_query: str,
        interpretation_variants: list[str]
    ) -> Optional[str]:
        """
        Extract the vague term that caused ambiguity.
        
        Compares original query with variants to find what changed.
        """
        if not interpretation_variants:
            return None
        
        # Find words in original that might be vague
        # Compare original with first interpretation variant
        variant = interpretation_variants[0] if interpretation_variants else ""
        
        original_words = set(original_query.lower().split())
        variant_words = set(variant.lower().split())
        
        # Words in original but not in variant are likely the vague terms
        vague_words = original_words - variant_words
        
        if vague_words:
            # Return the longest vague word (usually more meaningful)
            return max(vague_words, key=len)
        
        # Fallback: try to extract quoted terms from query
        # Look for single words in quotes or emphasized words
        important_words = [w for w in original_query.split() if len(w) > 4]
        if important_words:
            return important_words[0].strip("'\"").strip(",.!?")
        
        return None
    
    def process_user_selection(
        self,
        clarification_answer: str,
        original_query: str,
        selected_index: int
    ) -> dict:
        """
        Process user's selection from clarification questions.
        
        Args:
            clarification_answer: The selected option (or custom input if "Other")
            original_query: Original user query
            selected_index: Index of question answered (if multiple)
        
        Returns:
            Dictionary with:
            - refined_context: Context about user's choice
            - should_refine: Whether to proceed to Module 2
        """
        return {
            "user_clarification": clarification_answer,
            "clarification_applied": True,
            "refined_context": f"The user clarified: {clarification_answer}",
            "should_refine": True
        }


# Singleton instance
_generator = UIClarificationGenerator()


def generate_clarification_questions(analysis_data: dict) -> ClarificationResponse:
    """
    Public function to generate UI clarification questions.
    
    Args:
        analysis_data: Output from QueryUnderstandingModule
    
    Returns:
        ClarificationResponse with user-friendly questions
    """
    return _generator.generate_from_analysis(analysis_data)


def process_clarification_answer(
    answer: str,
    original_query: str,
    question_index: int = 0
) -> dict:
    """
    Public function to process user's clarification answer.
    
    Args:
        answer: User's selected/entered answer
        original_query: Original query text
        question_index: Which clarification question was answered
    
    Returns:
        Processing result dict
    """
    return _generator.process_user_selection(answer, original_query, question_index)

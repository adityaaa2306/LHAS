"""
Query and Chat API Endpoints

Provides endpoints for:
- Query understanding (Module 1)
- Chat/dialogue with RAG support
- Direct LLM interaction
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.services.query_understanding import get_query_understanding_module, QueryAnalysisResult
from app.services.query_refinement import (
    get_query_refinement_module,
    QueryRefinementRequest,
    QueryRefinementResponse,
    ClarificationResponse,
)
from app.services.retrieval import get_retrieval_module
from app.services.llm import get_llm_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


# ============================================================================
# Request/Response Models
# ============================================================================


class QueryAnalysisRequest(BaseModel):
    """Request model for query analysis."""

    query: str = Field(..., description="Research query to analyze", min_length=5)


class QueryAnalysisResponse(BaseModel):
    """Response model for query analysis."""

    normalized_query: str
    intent_type: str
    pico: Dict[str, Optional[str]]
    key_concepts: List[str]
    ambiguity_flags: List[str]
    decision: str
    reasoning: Optional[str] = None
    needs_clarification: bool = Field(default=False)


class ChatMessage(BaseModel):
    """Single message in conversation."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    messages: List[ChatMessage] = Field(..., description="Conversation history")
    include_reasoning: bool = Field(
        default=False, description="Include LLM reasoning in response"
    )
    max_reasoning_tokens: Optional[int] = Field(default=None)


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    answer: str
    reasoning: Optional[str] = None
    model: Optional[str] = None
    usage: Dict[str, int] = Field(default_factory=dict)


class QueryUnderstandingRequest(BaseModel):
    """Request for analyzing query intent."""

    query: str = Field(..., description="Research question to understand", min_length=5)


class QueryUnderstandingResponse(BaseModel):
    """Response with query analysis."""

    original_query: str
    normalized_query: str
    intent_type: str
    pico: Dict[str, Optional[str]]
    key_concepts: List[str]
    search_queries: List[str] = []
    ambiguity_flags: List[str]
    interpretation_variants: List[str] = []
    suggested_refinements: List[str] = []
    confidence_score: float
    decision: str
    reasoning_steps: List[str] = []


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/query/understand", response_model=QueryUnderstandingResponse)
async def understand_query(request: QueryUnderstandingRequest) -> Dict[str, Any]:
    """
    Analyze a research query using Query Understanding Module (Module 1).

    This endpoint extracts:
    - Intent type (Causal, Comparative, Exploratory, Descriptive)
    - PICO framework breakdown
    - Key concepts
    - Ambiguity flags for clarification

    Args:
        request: Contains the research query to analyze

    Returns:
        Query analysis with structured breakdown

    Raises:
        HTTPException: If query analysis fails
    """
    try:
        logger.info(f"Analyzing query: {request.query[:100]}...")

        # Get query understanding module
        module = get_query_understanding_module()

        # Analyze query
        analysis: QueryAnalysisResult = await module.analyze_query(
            query=request.query,
            mission_id=None,
            optional_context=None,
        )

        return {
            "original_query": analysis.original_query,
            "normalized_query": analysis.normalized_query,
            "intent_type": analysis.intent_type,
            "pico": analysis.pico.dict() if hasattr(analysis.pico, 'dict') else analysis.pico,
            "key_concepts": analysis.key_concepts,
            "search_queries": getattr(analysis, 'search_queries', []),
            "ambiguity_flags": analysis.ambiguity_flags,
            "interpretation_variants": getattr(analysis, 'interpretation_variants', []),
            "suggested_refinements": getattr(analysis, 'suggested_refinements', []),
            "confidence_score": getattr(analysis, 'confidence_score', 0.7),
            "decision": analysis.decision,
            "reasoning_steps": getattr(analysis, 'reasoning_steps', []),
        }

    except ValueError as e:
        logger.warning(f"Invalid query: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Query understanding error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to analyze query")


class ClarificationGeneratorRequest(BaseModel):
    """Request for generating UI clarification questions."""
    analysis: Dict[str, Any] = Field(..., description="Query analysis from Module 1")


class UIQuestion(BaseModel):
    """Single clarification question."""
    question: str
    options: List[str]


class ClarificationGeneratorResponse(BaseModel):
    """Response with UI clarification questions."""
    message: str
    questions: List[UIQuestion]
    requires_clarification: bool


@router.post("/query/clarification", response_model=ClarificationGeneratorResponse)
async def generate_clarification_questions(
    request: ClarificationGeneratorRequest,
) -> Dict[str, Any]:
    """
    Generate user-friendly clarification questions from Query Understanding analysis.
    
    Module 3: UI Clarification Generator
    
    This endpoint converts technical analysis into conversational questions that:
    - Help users refine their query naturally
    - Feel like ChatGPT/Perplexity interactions
    - Are directly usable in the frontend UI
    
    Args:
        request: Contains the analysis output from /query/understand
    
    Returns:
        UI-ready clarification questions with options
    
    Raises:
        HTTPException: If question generation fails
    """
    try:
        from app.services.ui_clarification_generator import generate_clarification_questions
        
        logger.info("Generating UI clarification questions from analysis")
        
        # Generate clarification questions
        response = generate_clarification_questions(request.analysis)
        
        return {
            "message": response.message,
            "questions": [
                {"question": q.question, "options": q.options}
                for q in response.questions
            ],
            "requires_clarification": response.requires_clarification,
        }
    
    except Exception as e:
        logger.error(f"Clarification generation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate clarification questions")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> Dict[str, Any]:
    """
    Send a message and receive a response with optional RAG context.

    This endpoint:
    1. Accepts multi-turn conversation history
    2. Optionally retrieves relevant documents (RAG)
    3. Sends augmented context to NVIDIA NIM
    4. Returns answer and reasoning (if available)

    Args:
        request: Chat request with messages and options

    Returns:
        Chat response with answer and metadata

    Raises:
        HTTPException: If chat fails
    """
    try:
        logger.info(f"Processing chat request with {len(request.messages)} messages")

        if not request.messages:
            raise ValueError("At least one message is required")

        # Convert Pydantic models to dicts
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Get LLM provider
        llm = get_llm_provider()

        # Get retrieval module
        retrieval = get_retrieval_module()

        # If last message is from user, optionally retrieve context
        last_message = messages[-1]["content"] if messages else ""

        retrieved_results = await retrieval.retrieve_relevant_documents_async(
            query=last_message,
            top_k=5,
        )

        # If documents found, augment the context
        if retrieved_results.get("documents"):
            rag_context = retrieval.construct_rag_context(
                query=last_message,
                documents=retrieved_results.get("documents", []),
                metadata=retrieved_results.get("metadata", []),
            )

            # Modify the last user message to include RAG context
            if messages[-1]["role"] == "user":
                messages[-1]["content"] = f"{rag_context}\n\nUser Query: {messages[-1]['content']}"

        logger.debug("Sending messages to LLM provider")

        # Get response from LLM
        response = await llm.generate_async(
            messages=messages,
            max_tokens=request.max_reasoning_tokens
            or 4096,  # Use provided max_reasoning_tokens or default
        )

        return {
            "answer": response.get("content", ""),
            "reasoning": response.get("reasoning") if request.include_reasoning else None,
            "model": response.get("model"),
            "usage": response.get("usage", {}),
        }

    except ValueError as e:
        logger.warning(f"Invalid chat request: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process chat request")


@router.post("/query/chat", response_model=ChatResponse)
async def query_chat(request: ChatRequest) -> Dict[str, Any]:
    """
    Simplified endpoint: Direct chat without explicit RAG configuration.

    Equivalent to /chat endpoint - kept for backward compatibility.

    Args:
        request: Chat request

    Returns:
        Chat response
    """
    return await chat(request)


@router.get("/health/llm")
async def health_llm() -> Dict[str, Any]:
    """
    Check LLM provider health and configuration.

    Returns:
        Health status and configuration info
    """
    try:
        llm = get_llm_provider()
        return {
            "status": "healthy",
            "provider": llm.provider_name,
            "version": "1.0.0",
        }
    except Exception as e:
        logger.error(f"LLM health check failed: {str(e)}")
        raise HTTPException(status_code=503, detail="LLM provider unavailable")


@router.post("/query/refine")
async def refine_query(request: QueryRefinementRequest) -> Dict[str, Any]:
    """
    Refine a research query through intelligent clarification (Module 2).

    This endpoint:
    1. Analyzes query clarity and specificity
    2. Generates contextual clarification questions if needed
    3. Incorporates user responses to refine the query
    4. Produces final refined query optimized for semantic search

    Flow:
    - First call: user_query only → returns clarification questions if needed, or final refined query
    - Subsequent calls: user_query + previous_clarifications → returns final refined query

    Args:
        request: Contains user_query and optional previous clarification responses

    Returns:
        Either clarification questions or final refined query with applied filters

    Raises:
        HTTPException: If refinement fails
    """
    try:
        logger.info(f"Refining query: {request.user_query[:100]}...")

        module = get_query_refinement_module()
        result = await module.refine_query(
            user_query=request.user_query,
            previous_clarifications=request.previous_clarifications,
        )

        return {
            "status": result.status,
            "clarification_questions": [
                {"question": q.question, "options": q.options}
                for q in (result.clarification_questions or [])
            ],
            "refined_query": result.refined_query,
            "applied_filters": result.applied_filters,
        }

    except ValueError as e:
        logger.warning(f"Invalid refinement request: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Query refinement error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to refine query")

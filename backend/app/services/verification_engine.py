"""ADDED: Two-Tier Verification Engine with NLI and LLM verification

Implements grounding validation and evidence entailment checking
to ensure extracted claims are fully supported by their source chunks.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of claim verification"""
    claim_id: str
    is_supported: str  # true | false | partial | uncertain
    verification_confidence: float  # 0-1
    verification_tier: int  # 1 (NLI) | 2 (LLM) | 3 (skipped)
    error_type: Optional[str] = None  # hallucination, overgeneralization, unsupported, scope_drift
    note: Optional[str] = None
    grounding_valid: Optional[bool] = None


class VerificationEngine:
    """ADDED: Evidence-based verification layer for extracted claims"""
    
    def __init__(
        self,
        db: Any,
        llm_provider: Any,
        enable_nli: bool = True,
        enable_tier2: bool = True
    ):
        """
        Initialize verification engine.
        
        Args:
            db: AsyncSession database connection
            llm_provider: LLM service for Tier 2 verification
            enable_nli: Whether to use NLI model (Tier 1)
            enable_tier2: Whether to use LLM for uncertain cases (Tier 2)
        """
        self.db = db
        self.llm_provider = llm_provider
        self.enable_nli = enable_nli
        self.enable_tier2 = enable_tier2
        
        # Lazy load NLI model
        self._nli_model = None
        
        logger.info("VerificationEngine initialized")
    
    def _check_grounding_mechanical(
        self,
        evidence_span: str,
        source_chunks: List[Dict[str, Any]]
    ) -> bool:
        """ADDED: Mechanical check that evidence_span is in source chunks"""
        if not evidence_span or not source_chunks:
            return False
        
        # Check if evidence_span is a substring of any source chunk
        for chunk in source_chunks:
            chunk_text = chunk.get("raw_text", "")
            # Allow small whitespace differences
            normalized_span = " ".join(evidence_span.split())
            normalized_chunk = " ".join(chunk_text.split())
            
            if normalized_span in normalized_chunk:
                return True
        
        return False
    
    async def verify_nli(
        self,
        claim: Dict[str, Any],
        source_chunks: List[Dict[str, Any]]
    ) -> VerificationResult:
        """ADDED: Tier 1 verification using NLI model"""
        
        claim_id = claim.get("id", "unknown")
        evidence_span = claim.get("evidence_span", "")
        claim_statement = claim.get("statement_raw", "")
        
        # Check grounding first
        grounding_valid = self._check_grounding_mechanical(evidence_span, source_chunks)
        
        try:
            # Lazy load NLI model
            if self._nli_model is None and self.enable_nli:
                from sentence_transformers import CrossEncoder
                self._nli_model = CrossEncoder('cross-encoder/nli-deberta-v3-small')
                logger.info("Loaded NLI model")
            
            if not self.enable_nli or self._nli_model is None:
                # Skip NLI, return uncertain
                return VerificationResult(
                    claim_id=claim_id,
                    is_supported="uncertain",
                    verification_confidence=0.5,
                    verification_tier=3,
                    grounding_valid=grounding_valid
                )
            
            # NLI inference: (evidence_span, claim_statement)
            # NLI classes: 0=entailment, 1=neutral, 2=contradiction
            scores = self._nli_model.predict(
                [[evidence_span, claim_statement]],
                convert_to_numpy=True
            )[0]  # Get first (only) result
            
            entailment_score = scores[0]  # P(entailment)
            neutral_score = scores[1]      # P(neutral)
            contradiction_score = scores[2]  # P(contradiction)
            
            # Map to verification result
            if entailment_score > 0.70:
                return VerificationResult(
                    claim_id=claim_id,
                    is_supported="true",
                    verification_confidence=float(entailment_score),
                    verification_tier=1,
                    grounding_valid=grounding_valid
                )
            elif contradiction_score > 0.60:
                return VerificationResult(
                    claim_id=claim_id,
                    is_supported="false",
                    verification_confidence=1.0 - float(contradiction_score),
                    verification_tier=1,
                    error_type="contradiction",
                    grounding_valid=grounding_valid
                )
            else:
                # Uncertain — pass to Tier 2
                return VerificationResult(
                    claim_id=claim_id,
                    is_supported="uncertain",
                    verification_confidence=max(
                        entailment_score, neutral_score, contradiction_score
                    ),
                    verification_tier=1,
                    grounding_valid=grounding_valid
                )
        
        except Exception as e:
            logger.error(f"NLI verification failed for claim {claim_id}: {str(e)}")
            return VerificationResult(
                claim_id=claim_id,
                is_supported="uncertain",
                verification_confidence=0.5,
                verification_tier=1,
                grounding_valid=grounding_valid
            )
    
    async def verify_llm(
        self,
        claims: List[Dict[str, Any]],
        source_chunks_map: Dict[str, List[Dict[str, Any]]]
    ) -> List[VerificationResult]:
        """ADDED: Tier 2 LLM verification for uncertain claims"""
        
        if not self.enable_tier2 or not claims:
            return []
        
        try:
            # Batch up to 6 claims per LLM call
            batch_size = 6
            all_results = []
            
            for batch_start in range(0, len(claims), batch_size):
                batch_end = min(batch_start + batch_size, len(claims))
                batch = claims[batch_start:batch_end]
                
                # Build prompt
                claims_text = ""
                claim_ids = []
                
                for claim in batch:
                    claim_id = claim.get("id", "unknown")
                    source_chunk_ids = claim.get("source_chunk_ids", [])
                    evidence_span = claim.get("evidence_span", "")
                    statement = claim.get("statement_raw", "")
                    chunk_type = claim.get("chunk_type", "text")
                    
                    claim_ids.append(claim_id)
                    
                    # Get source chunks
                    chunks_text = ""
                    if claim_id in source_chunks_map:
                        for chunk in source_chunks_map[claim_id]:
                            chunks_text += f"[{chunk.get('section', '?')}] {chunk.get('raw_text', '')}\n\n"
                    
                    claims_text += f"""
Claim ID: {claim_id}
Type: {chunk_type}
Evidence span: "{evidence_span}"
Claim statement: "{statement}"
Source text: {chunks_text}

---
"""
                
                prompt = f"""Verify whether each claim is fully supported by its evidence span.

For each claim, determine if it is:
- SUPPORTED: The claim is a logical consequence of the evidence span
- PARTIALLY_SUPPORTED: The claim is mostly accurate but makes a small generalization or scope change the evidence doesn't fully cover
- UNSUPPORTED: The claim cannot be derived from the evidence

Also classify the error type if unsupported:
- "hallucination": Information added that is not in evidence
- "overgeneralization": Valid claim but applied too broadly
- "contradiction": Directly contradicts the evidence
- "scope_drift": Changes the scope/population/conditions

{claims_text}

Output JSON only (no markdown, no explanation):
[
    {{
        "claim_id": "...",
        "is_supported": "true" | "false" | "partial",
        "error_type": null | "hallucination" | "overgeneralization" | "contradiction" | "scope_drift",
        "confidence": 0.0-1.0,
        "note": "..."
    }},
    ...
]
"""
                
                # Call LLM
                response = await self.llm_provider.generate_async([
                    {
                        "role": "system",
                        "content": "You are a rigorous fact-checker. Verify claims against their evidence spans."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ], max_tokens=1000)
                
                # Parse response
                try:
                    content = response.get("content", "")
                    # Extract JSON
                    import re
                    json_match = re.search(r'\[.*\]', content, re.DOTALL)
                    if json_match:
                        results_data = json.loads(json_match.group())
                        
                        for result in results_data:
                            claim_id = result.get("claim_id")
                            is_supported = result.get("is_supported", "uncertain").lower()
                            
                            # Map partial to false with penalty
                            if is_supported == "partial":
                                is_supported = "false"
                                conf_penalty = 0.75
                            else:
                                conf_penalty = 1.0
                            
                            all_results.append(VerificationResult(
                                claim_id=claim_id,
                                is_supported=is_supported,
                                verification_confidence=float(
                                    result.get("confidence", 0.5)
                                ) * conf_penalty,
                                verification_tier=2,
                                error_type=result.get("error_type"),
                                note=result.get("note")
                            ))
                    else:
                        # Parse failed, mark uncertain
                        for claim_id in claim_ids:
                            all_results.append(VerificationResult(
                                claim_id=claim_id,
                                is_supported="uncertain",
                                verification_confidence=0.5,
                                verification_tier=2
                            ))
                
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse LLM response: {str(e)}")
                    for claim_id in claim_ids:
                        all_results.append(VerificationResult(
                            claim_id=claim_id,
                            is_supported="uncertain",
                            verification_confidence=0.5,
                            verification_tier=2
                        ))
            
            logger.info(f"Tier 2 LLM verified {len(all_results)} claims")
            return all_results
        
        except Exception as e:
            logger.error(f"Tier 2 LLM verification failed: {str(e)}")
            # Return uncertain for all
            return [
                VerificationResult(
                    claim_id=claim.get("id", "unknown"),
                    is_supported="uncertain",
                    verification_confidence=0.5,
                    verification_tier=2
                )
                for claim in claims
            ]
    
    async def verify_table_claim(
        self,
        claim: Dict[str, Any],
        table_data: Dict[str, Any]
    ) -> VerificationResult:
        """ADDED: Special verification for table-sourced claims (goes directly to Tier 2)"""
        
        claim_id = claim.get("id", "unknown")
        
        try:
            # Skip NLI for tables, go directly to LLM
            # Format table data for LLM
            table_text = self._format_table_for_llm(table_data)
            
            prompt = f"""Verify this claim against the table data provided.

Table data:
{table_text}

Claim: "{claim.get('statement_raw', '')}"
Evidence from table: {claim.get('evidence_span', '')}

Is this claim fully supported by the table data?
Answer: supported | partially_supported | unsupported
Confidence: 0.0-1.0

Output JSON only:
{{
    "is_supported": "true" | "false" | "partial",
    "confidence": 0.5,
    "error_type": null | "hallucination" | "overgeneralization" | "contradiction"
}}
"""
            
            response = await self.llm_provider.generate_async([
                {
                    "role": "system",
                    "content": "You are a fact-checker specialized in verifying claims against tabular data."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ], max_tokens=200)
            
            # Parse response
            content = response.get("content", "")
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group())
                is_supported = result.get("is_supported", "uncertain").lower()
                if is_supported == "partial":
                    is_supported = "false"
                
                return VerificationResult(
                    claim_id=claim_id,
                    is_supported=is_supported,
                    verification_confidence=float(result.get("confidence", 0.5)),
                    verification_tier=2,
                    error_type=result.get("error_type")
                )
            else:
                return VerificationResult(
                    claim_id=claim_id,
                    is_supported="uncertain",
                    verification_confidence=0.5,
                    verification_tier=2
                )
        
        except Exception as e:
            logger.error(f"Table verification failed for claim {claim_id}: {str(e)}")
            return VerificationResult(
                claim_id=claim_id,
                is_supported="uncertain",
                verification_confidence=0.5,
                verification_tier=2
            )
    
    def _format_table_for_llm(self, table_data: Dict[str, Any]) -> str:
        """ADDED: Format table data for LLM verification"""
        # Convert table structure to markdown
        markdown_table = "| Column | Values |\n|--------|--------|\n"
        for col, values in table_data.items():
            markdown_table += f"| {col} | {', '.join(str(v) for v in values[:3])} |\n"
        return markdown_table
    
    async def verify_batch(
        self,
        claims: List[Dict[str, Any]],
        source_chunks_map: Dict[str, List[Dict[str, Any]]]
    ) -> List[VerificationResult]:
        """ADDED: Verify batch of claims with two-tier approach"""
        
        if not claims:
            return []
        
        all_results = []
        tier2_candidates = []
        
        # Tier 1: NLI for text claims
        for claim in claims:
            chunk_type = claim.get("chunk_type", "text")
            
            if chunk_type == "table":
                # Tables go directly to Tier 2
                tier2_candidates.append(claim)
            elif chunk_type == "figure_caption":
                # Figure captions go directly to Tier 2
                tier2_candidates.append(claim)
            else:
                # Text claims: try Tier 1 NLI
                source_chunks = source_chunks_map.get(claim.get("id", ""), [])
                result = await self.verify_nli(claim, source_chunks)
                
                if result.is_supported == "uncertain":
                    # Uncertain, promote to Tier 2
                    tier2_candidates.append(claim)
                else:
                    # Resolved at Tier 1
                    all_results.append(result)
        
        # Tier 2: LLM for uncertain cases
        if tier2_candidates:
            tier2_results = await self.verify_llm(tier2_candidates, source_chunks_map)
            all_results.extend(tier2_results)
        
        logger.info(
            f"Verification complete: {len(all_results)} claims verified "
            f"({len(all_results) - len(tier2_candidates)} via Tier 1, "
            f"{len(tier2_candidates)} via Tier 2)"
        )
        
        return all_results

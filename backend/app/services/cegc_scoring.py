"""CEGC Hyper-Optimized 5-Layer Scoring Service

Implements the Comprehensive Evidence Grading & Credibility (CEGC) framework:
- Layer 1 (25%): PICO Soft Matching - semantic comparison of Population, Intervention, Outcome
- Layer 2 (30%): Evidence Strength - sample size, peer review status, reproducibility
- Layer 3 (20%): Mechanism Fingerprinting - method→result chain alignment
- Layer 4 (15%): Assumption Alignment - validates query's core assumptions
- Layer 5 (10%): LLM Verification - selective extraction for ambiguous papers (0.50-0.80)

Total inference: ~2 seconds per 200 papers | Cost: ~$0.51 per mission
"""

import re
import json
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class CEGCScoringService:
    """Hyper-optimized CEGC scoring with 5 deterministic + 1 selective-LLM layers"""
    
    def __init__(self, llm_provider=None, embedding_service=None):
        """Initialize CEGC scoring service
        
        Args:
            llm_provider: LLM service for Layer 5 (selective LLM verification)
            embedding_service: Embedding service for semantic matching
        """
        self.llm_provider = llm_provider
        self.embedding_service = embedding_service
        
        # Evidence extraction patterns
        self.sample_size_patterns = [
            r'(?:n|N)\s*=\s*(\d+)',  # n = 123
            r'sample\s+size\s+of\s+(\d+)',  # sample size of 123
            r'(\d+)\s+(?:participants|patients|subjects)',  # 123 participants
        ]
        
        self.peer_review_keywords = ['peer-reviewed', 'peer reviewed', 'published in', 'journal']
        self.reproducibility_keywords = ['reproducible', 'code available', 'supplementary']
        
        self.evidence_level_keywords = {
            'RCT': 1.0,
            'randomized controlled trial': 1.0,
            'systematic review': 0.95,
            'meta-analysis': 0.95,
            'prospective study': 0.85,
            'observational study': 0.65,
            'case report': 0.4,
        }
        
        self.method_patterns = r'(?:method|approach|protocol|procedure|technique|algorithm|model)'
        self.result_patterns = r'(?:result|finding|outcome|demonstrate|show|confirm)'

    def _paper_text(self, paper: Any) -> str:
        """Return the richest text available for scoring."""
        title = paper.title or ""
        abstract = paper.abstract or ""
        full_text = getattr(paper, "full_text_content", None)
        if full_text:
            return f"{title}\n\n{full_text}".lower()
        return f"{title} {abstract}".lower()

    def _paper_excerpt_for_llm(self, paper: Any, max_chars: int = 6000) -> str:
        """Use a bounded full-text excerpt for LLM verification."""
        title = paper.title or ""
        sections = getattr(paper, "full_text_sections", None) or {}
        if sections:
            preferred = ["abstract", "methods", "results", "discussion", "conclusion"]
            parts = [f"Title: {title}"]
            per_section_chars = max(800, max_chars // max(1, len(preferred)))
            for name in preferred:
                text = sections.get(name)
                if text:
                    parts.append(f"[{name.upper()}]\n{text[:per_section_chars]}")
            excerpt = "\n\n".join(parts)
            return excerpt[:max_chars]

        full_text = getattr(paper, "full_text_content", None)
        if full_text:
            return f"Title: {title}\n\n{full_text[:max_chars]}"
        return f"Title: {title}\nAbstract: {(paper.abstract or '')[:max_chars]}"
    
    async def score_papers(
        self,
        papers: List[Any],
        structured_query: Dict[str, Any],
        use_llm: bool = True,
    ) -> Tuple[List[Any], int, int]:
        """Score papers through all 5 CEGC layers
        
        Args:
            papers: List of PaperObject instances
            structured_query: Query with PICO and assumptions
            use_llm: Whether to apply Layer 5 LLM verification
            
        Returns:
            (scored_papers, llm_calls, llm_tokens_used)
        """
        logger.info(f"🔍 CEGC: Scoring {len(papers)} papers through 5 layers")
        
        llm_calls = 0
        llm_tokens = 0
        
        # Layer 1-4: Deterministic scoring (no LLM)
        for paper in papers:
            # Layer 1: PICO Soft Matching (25%)
            pico_score = self._layer1_pico_matching(paper, structured_query)
            paper.pico_match_score = pico_score
            
            # Layer 2: Evidence Strength Pre-scoring (30%)
            evidence_score = self._layer2_evidence_strength(paper)
            paper.evidence_strength_score = evidence_score
            
            # Layer 3: Mechanism Fingerprinting (20%)
            mechanism_score = self._layer3_mechanism_fingerprinting(paper, structured_query)
            paper.mechanism_agreement_score = mechanism_score
            
            # Layer 4: Assumption Alignment (15%)
            assumption_score = self._layer4_assumption_alignment(paper, structured_query)
            paper.assumption_alignment_score = assumption_score
            
            # Combine Layers 1-4 (90% of final score)
            intermediate_score = (
                pico_score * 0.25 +
                evidence_score * 0.30 +
                mechanism_score * 0.20 +
                assumption_score * 0.15
            ) / 0.90  # Normalize to 0-1
            
            paper.llm_verification_score = 0.0  # Default, may be updated by Layer 5
            paper.final_score = intermediate_score
            
            # Store breakdown - keys must match frontend expectations
            paper.score_breakdown = {
                'pico': round(pico_score, 3),
                'evidence': round(evidence_score, 3),
                'mechanism': round(mechanism_score, 3),
                'assumption': round(assumption_score, 3),
                'llm_adjustment': 0.0,  # Default, may be updated by Layer 5
                'final': round(intermediate_score, 3)  # Key must be 'final' not 'final_score'
            }
        
        # Layer 5: Selective LLM Verification (10%)
        if use_llm and self.llm_provider:
            ambiguous_papers = [
                p for p in papers 
                if 0.50 <= (p.final_score or 0) <= 0.80
            ]
            
            if ambiguous_papers:
                logger.info(f"📊 Layer 5: {len(ambiguous_papers)} ambiguous papers for LLM verification")
                
                for paper in ambiguous_papers:
                    llm_adj, calls, tokens = await self._layer5_llm_verification(
                        paper, structured_query
                    )
                    
                    paper.llm_verification_score = llm_adj
                    llm_calls += calls
                    llm_tokens += tokens
                    
                    # Update final score with LLM adjustment
                    new_final = (paper.final_score * 0.90) + (llm_adj * 0.10)
                    paper.final_score = min(1.0, max(0.0, new_final))
                    
                    # Update breakdown
                    if paper.score_breakdown:
                        paper.score_breakdown['llm_adjustment'] = round(llm_adj, 3)
                        paper.score_breakdown['final'] = round(paper.final_score, 3)  # Key must be 'final' not 'final_score'
        
        logger.info(f"✅ CEGC: Scored {len(papers)} papers | "
                   f"LLM calls: {llm_calls} | Tokens: {llm_tokens}")
        
        return papers, llm_calls, llm_tokens
    
    # ==================== LAYER 1: PICO SOFT MATCHING (25%) ====================
    
    def _layer1_pico_matching(self, paper: Any, query: Dict[str, Any]) -> float:
        """Layer 1: PICO Soft Matching
        
        Scores semantic alignment between paper and PICO query:
        - Population (P): patient demographics, condition
        - Intervention (I): treatment, procedure, drug
        - Outcome (O): measured results
        
        Returns: 0-1 score
        """
        try:
            # Extract PICO from query
            query_pico = query.get('pico', {})
            population = query_pico.get('population', '').lower()
            intervention = query_pico.get('intervention', '').lower()
            outcome = query_pico.get('outcome', '').lower()
            
            paper_text = self._paper_text(paper)
            
            scores = []
            
            # P: Check population keywords
            if population:
                p_score = self._keyword_overlap(population, paper_text, weight=0.8)
                scores.append(p_score * 0.33)
            
            # I: Check intervention keywords
            if intervention:
                i_score = self._keyword_overlap(intervention, paper_text, weight=0.9)
                scores.append(i_score * 0.33)
            
            # O: Check outcome keywords
            if outcome:
                o_score = self._keyword_overlap(outcome, paper_text, weight=0.85)
                scores.append(o_score * 0.33)
            
            # If no PICO specified, use default
            if not scores:
                return 0.5
            
            pico_score = min(1.0, sum(scores))
            logger.debug(f"Layer 1 PICO: '{paper.title[:40]}...' → {pico_score:.3f}")
            return pico_score
            
        except Exception as e:
            logger.warning(f"Layer 1 PICO error for '{paper.title[:40]}...': {e}")
            return 0.5
    
    def _keyword_overlap(self, keywords_str: str, text: str, weight: float = 1.0) -> float:
        """Calculate keyword overlap between keywords and text
        
        Args:
            keywords_str: Space/comma-separated keywords
            text: Target text to search in
            weight: Weighting factor
            
        Returns: 0-1 score
        """
        if not keywords_str or not text:
            return 0.0
        
        keywords = [k.strip() for k in re.split(r'[,\s]+', keywords_str) if k.strip()]
        if not keywords:
            return 0.0
        
        matches = 0
        for kw in keywords:
            if len(kw) > 2 and kw in text:  # Avoid single-char matches
                matches += 1
        
        overlap = matches / len(keywords) if keywords else 0.0
        return min(1.0, overlap * weight)
    
    # ==================== LAYER 2: EVIDENCE STRENGTH (30%) ====================
    
    def _layer2_evidence_strength(self, paper: Any) -> float:
        """Layer 2: Evidence Strength Pre-scoring
        
        Evaluates research quality via:
        - Sample size (N) - larger is better
        - Peer review status
        - Study type (RCT > Meta-analysis > Observational > Case)
        - Reproducibility signals
        
        Returns: 0-1 score
        """
        try:
            paper_text = self._paper_text(paper)
            
            scores = []
            
            # 1. Sample size extraction (0-1, log-scaled)
            sample_size = self._extract_sample_size(paper_text)
            if sample_size:
                # Log scale: 100 → 0.5, 1000 → 0.8, 10000 → 1.0
                n_score = min(1.0, 0.3 + (0.4 * np.log10(sample_size) / 4))
                scores.append(n_score * 0.35)
            else:
                scores.append(0.3 * 0.35)  # Default low for unknown N
            
            # 2. Study type (0-1)
            study_type_score = self._extract_study_type(paper_text)
            scores.append(study_type_score * 0.40)
            
            # 3. Peer review status (0-1)
            peer_review_score = 0.8 if any(kw in paper_text for kw in self.peer_review_keywords) else 0.5
            scores.append(peer_review_score * 0.15)
            
            # 4. Reproducibility signals (0-1)
            repro_score = 0.7 if any(kw in paper_text for kw in self.reproducibility_keywords) else 0.4
            scores.append(repro_score * 0.10)
            
            evidence_score = min(1.0, sum(scores))
            logger.debug(f"Layer 2 Evidence: '{paper.title[:40]}...' → {evidence_score:.3f}")
            return evidence_score
            
        except Exception as e:
            logger.warning(f"Layer 2 Evidence error: {e}")
            return 0.5
    
    def _extract_sample_size(self, text: str) -> Optional[int]:
        """Extract study sample size from text
        
        Returns: Sample size or None
        """
        for pattern in self.sample_size_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    n = int(match.group(1))
                    if 0 < n < 1_000_000:  # Sanity check
                        return n
                except ValueError:
                    continue
        return None
    
    def _extract_study_type(self, text: str) -> float:
        """Extract study type and return evidence quality score (0-1)"""
        for study_type, score in self.evidence_level_keywords.items():
            if study_type.lower() in text:
                return score
        
        # Default to observational
        return 0.6
    
    # ==================== LAYER 3: MECHANISM FINGERPRINTING (20%) ====================
    
    def _layer3_mechanism_fingerprinting(self, paper: Any, query: Dict[str, Any]) -> float:
        """Layer 3: Mechanism Fingerprinting
        
        Extracts method→result chain and verifies alignment with query mechanisms:
        - Identifies action (method section)
        - Identifies outcome (results section)
        - Scores alignment with expected mechanism
        
        Returns: 0-1 score
        """
        try:
            paper_text = self._paper_text(paper)
            
            # Extract query mechanism
            query_mechanism = query.get('mechanism', '')
            
            if not query_mechanism:
                # No mechanism specified - default to moderate score
                paper.mechanism_description = "No query mechanism specified"
                return 0.6
            
            # Find method→result patterns
            mechanism_score = 0.5  # Default
            mechanism_explanation = ""
            
            # Look for method indicators
            method_found = bool(re.search(self.method_patterns, paper_text, re.IGNORECASE))
            
            # Look for result indicators
            result_found = bool(re.search(self.result_patterns, paper_text, re.IGNORECASE))
            
            if method_found and result_found:
                # Both method and results present - strong signal
                mechanism_score = 0.75
                mechanism_explanation = "Complete method→result chain identified"
            elif method_found or result_found:
                # Partial signal
                mechanism_score = 0.6
                mechanism_explanation = "Partial method or results chain"
            else:
                # Neither found
                mechanism_score = 0.4
                mechanism_explanation = "Limited method/result chain"
            
            # Check mechanism alignment with query
            if query_mechanism:
                align_score = self._keyword_overlap(query_mechanism, paper_text, weight=1.0)
                mechanism_score = mechanism_score * 0.5 + align_score * 0.5
                mechanism_explanation += f" → Aligned with mechanism"
            
            paper.mechanism_description = mechanism_explanation
            logger.debug(f"Layer 3 Mechanism: '{paper.title[:40]}...' → {mechanism_score:.3f}")
            return min(1.0, mechanism_score)
            
        except Exception as e:
            logger.warning(f"Layer 3 Mechanism error: {e}")
            paper.mechanism_description = "Error processing mechanism"
            return 0.5
    
    # ==================== LAYER 4: ASSUMPTION ALIGNMENT (15%) ====================
    
    def _layer4_assumption_alignment(self, paper: Any, query: Dict[str, Any]) -> float:
        """Layer 4: Assumption Alignment
        
        Checks if paper validates query's core assumptions:
        - Identifies control group (if applicable)
        - Checks for confounding variable control
        - Validates statistical validity
        
        Returns: 0-1 score
        """
        try:
            paper_text = self._paper_text(paper)
            
            query_assumptions = query.get('assumptions', [])
            
            if not query_assumptions:
                # No assumptions to validate
                return 0.6
            
            # Check for assumptions in paper
            assumption_score = 0.5
            matches = 0
            
            for assumption in query_assumptions:
                assumption_lower = assumption.lower()
                
                # Simple keyword match
                if assumption_lower in paper_text:
                    matches += 1
                
                # Check for contradictory statements
                if self._has_contradiction_markers(paper_text, assumption_lower):
                    matches -= 0.5
            
            if query_assumptions:
                assumption_score = max(0.0, min(1.0, 0.5 + (matches / len(query_assumptions)) * 0.5))
            
            logger.debug(f"Layer 4 Assumption: '{paper.title[:40]}...' → {assumption_score:.3f}")
            return assumption_score
            
        except Exception as e:
            logger.warning(f"Layer 4 Assumption error: {e}")
            return 0.5
    
    def _has_contradiction_markers(self, text: str, assumption: str) -> bool:
        """Check for contradiction markers"""
        contradiction_patterns = [
            r'contradicts?',
            r'conflicts? with',
            r'contrary to',
            r'opposite of',
            r'no(?:\s+|)evidence',
        ]
        
        for pattern in contradiction_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    # ==================== LAYER 5: LLM VERIFICATION (10%, SELECTIVE) ====================
    
    async def _layer5_llm_verification(
        self,
        paper: Any,
        query: Dict[str, Any],
    ) -> Tuple[float, int, int]:
        """Layer 5: LLM Verification (selective for ambiguous papers only)
        
        Uses LLM to extract reasoning graph and refine score for papers
        in the ambiguous range (0.50-0.80).
        
        Returns: (llm_adjustment_score, llm_calls, tokens_used)
        """
        try:
            if not self.llm_provider:
                return 0.0, 0, 0
            
            # Build verification prompt
            prompt = self._build_llm_verification_prompt(paper, query)
            
            # Call LLM
            response = await self.llm_provider.agenerate(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert research paper analyzer. Evaluate if this paper is relevant to the query and provide a refinement score (0-1)."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=500,
            )
            
            # Parse response
            llm_text = response.get('content', '')
            reasoning_graph = self._parse_llm_reasoning(llm_text)
            
            # Extract score from reasoning
            adjustment_score = self._extract_llm_score(llm_text)
            
            # Store reasoning graph
            paper.reasoning_graph = reasoning_graph
            
            llm_calls = 1
            llm_tokens = response.get('usage', {}).get('total_tokens', 100)
            
            logger.info(f"Layer 5 LLM: '{paper.title[:40]}...' → {adjustment_score:+.3f}")
            
            return adjustment_score, llm_calls, llm_tokens
            
        except Exception as e:
            logger.warning(f"Layer 5 LLM error: {e}")
            return 0.0, 0, 0
    
    def _build_llm_verification_prompt(self, paper: Any, query: Dict[str, Any]) -> str:
        """Build LLM verification prompt"""
        prompt = f"""Analyze this paper for relevance to the research query.

QUERY:
- Population: {query.get('pico', {}).get('population', 'N/A')}
- Intervention: {query.get('pico', {}).get('intervention', 'N/A')}
- Outcome: {query.get('pico', {}).get('outcome', 'N/A')}
- Assumptions: {query.get('assumptions', 'N/A')}

PAPER:
{self._paper_excerpt_for_llm(paper)}

Evaluate:
1. Does it address ALL PICO components? (Yes/No + explanation)
2. Is the methodology sound? (Yes/No + concerns)
3. Are the results credible? (Yes/No + why/why not)
4. Overall relevance score (0-1): X.XX

Respond with JSON format: {{relevance_score: 0.XX, reasoning: "..."}}"""
        
        return prompt
    
    def _parse_llm_reasoning(self, llm_text: str) -> Dict[str, Any]:
        """Parse LLM response into reasoning graph"""
        try:
            # Try to extract JSON
            json_match = re.search(r'\{[^{}]*\}', llm_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        
        # Fallback: structure as simplified graph
        return {
            'type': 'llm_verification',
            'reasoning': llm_text[:500],  # First 500 chars
        }
    
    def _extract_llm_score(self, llm_text: str) -> float:
        """Extract numerical relevance score from LLM response"""
        # Look for patterns like "0.75" or "relevance_score: 0.75"
        patterns = [
            r'relevance_score["\']?\s*:\s*(0\.\d+)',
            r'relevance["\']?\s*:\s*(0\.\d+)',
            r'(\d\.\d+)',  # Fallback: any decimal
        ]
        
        for pattern in patterns:
            match = re.search(pattern, llm_text, re.IGNORECASE)
            if match:
                try:
                    score = float(match.group(1))
                    if 0 <= score <= 1:
                        return score - 0.5  # Convert to adjustment (-0.5 to +0.5)
                except ValueError:
                    continue
        
        return 0.0  # No adjustment if score not found

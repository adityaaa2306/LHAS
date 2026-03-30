"""ADDED: Quantitative Data Extraction from Tables and Figures

Extracts structured quantitative data from table and figure chunks
in parallel with Pass 2, providing evidence-grounded numeric support.
"""

import logging
import json
import re
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QuantitativeEvidence:
    """Structured quantitative data extracted from tables/figures"""
    effect_size: Optional[float] = None
    effect_size_unit: Optional[str] = None
    p_value: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    comparison_groups: List[str] = None
    outcome_metric: Optional[str] = None
    n_sample: Optional[int] = None
    n_groups: Optional[int] = None
    
    # For figures
    figure_type: Optional[str] = None  # forest plot, bar chart, survival curve, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "effect_size": self.effect_size,
            "effect_size_unit": self.effect_size_unit,
            "p_value": self.p_value,
            "confidence_interval": self.confidence_interval,
            "comparison_groups": self.comparison_groups or [],
            "outcome_metric": self.outcome_metric,
            "n_sample": self.n_sample,
            "n_groups": self.n_groups,
            "figure_type": self.figure_type
        }


class QuantitativeExtractor:
    """ADDED: Extract quantitative data from structured sources"""
    
    def __init__(self, llm_provider: Any):
        """
        Initialize quantitative extractor.
        
        Args:
            llm_provider: LLM service for extraction
        """
        self.llm_provider = llm_provider
        logger.info("QuantitativeExtractor initialized")
    
    async def extract_table_data(
        self,
        table_chunk_id: str,
        table_markdown: str
    ) -> Optional[QuantitativeEvidence]:
        """ADDED: Extract quantitative data from table markdown"""
        
        try:
            # Parse table markdown
            evidence = QuantitativeEvidence(comparison_groups=[])
            
            # Look for common table patterns
            lines = table_markdown.split('\n')
            
            # Parse effect size
            for line in lines:
                # Match patterns like "Effect Size: 0.45" or "0.45 (CI: 0.30-0.60)"
                es_match = re.search(r'(?:effect\s*size|coefficient)[\s:]*(-?\d+\.?\d*)', line, re.IGNORECASE)
                if es_match:
                    evidence.effect_size = float(es_match.group(1))
                
                # Match p-values: p = 0.001, p < 0.05, etc.
                p_match = re.search(r'p[\s=<>]*(\d+\.?\d{0,4})', line, re.IGNORECASE)
                if p_match:
                    evidence.p_value = float(p_match.group(1))
                
                # Match confidence intervals: CI: [0.30, 0.60] or (0.30-0.60)
                ci_match = re.search(r'(?:CI|95%\s*CI)[\s:]*\[?(\d+\.?\d*)\D+(\d+\.?\d*)\]?', line, re.IGNORECASE)
                if ci_match:
                    lower = float(ci_match.group(1))
                    upper = float(ci_match.group(2))
                    evidence.confidence_interval = (lower, upper)
                
                # Match sample size: N=345, n: 345, etc.
                n_match = re.search(r'[Nn][\s=:]*(\d+)', line)
                if n_match:
                    n_val = int(n_match.group(1))
                    if evidence.n_sample is None or n_val > evidence.n_sample:
                        evidence.n_sample = n_val
                
                # Extract group comparisons
                if 'vs' in line.lower() or 'vs.' in line.lower():
                    # Extract groups from "Group A vs Group B"
                    parts = re.split(r'\s+vs\.?\s+', line, flags=re.IGNORECASE)
                    if len(parts) >= 2:
                        group1 = parts[0].strip()
                        group2 = parts[1].strip()
                        if group1 not in evidence.comparison_groups:
                            evidence.comparison_groups.append(group1)
                        if group2 not in evidence.comparison_groups:
                            evidence.comparison_groups.append(group2)
            
            # If we extracted something, return it
            if (evidence.effect_size is not None or 
                evidence.p_value is not None or 
                evidence.confidence_interval is not None or
                evidence.n_sample is not None):
                logger.info(f"Extracted quantitative data from table {table_chunk_id}")
                return evidence
            
            # If extraction didn't work, try LLM
            return await self._extract_table_with_llm(table_chunk_id, table_markdown)
        
        except Exception as e:
            logger.error(f"Table extraction failed for {table_chunk_id}: {str(e)}")
            return None
    
    async def _extract_table_with_llm(
        self,
        table_chunk_id: str,
        table_markdown: str
    ) -> Optional[QuantitativeEvidence]:
        """ADDED: Use LLM to extract quantitative data from complex tables"""
        
        try:
            prompt = f"""Extract quantitative data from this research table.

Table:
{table_markdown}

Extract and return JSON:
{{
    "effect_size": null | number,
    "effect_size_unit": null | "cohen_d" | "odds_ratio" | "hazard_ratio" | "correlation" | "other",
    "p_value": null | number (0-1),
    "confidence_interval": null | [lower, upper],
    "comparison_groups": [],
    "outcome_metric": null | string (what was measured),
    "n_sample": null | number,
    "n_groups": null | number
}}

Output JSON only, no explanation.
"""
            
            response = await self.llm_provider.generate_async([
                {
                    "role": "system",
                    "content": "You are a data extraction specialist for research tables."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ], max_tokens=500)
            
            content = response.get("content", "")
            
            # Extract JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                evidence = QuantitativeEvidence(
                    effect_size=data.get("effect_size"),
                    effect_size_unit=data.get("effect_size_unit"),
                    p_value=data.get("p_value"),
                    confidence_interval=tuple(data.get("confidence_interval", [])) if data.get("confidence_interval") else None,
                    comparison_groups=data.get("comparison_groups", []),
                    outcome_metric=data.get("outcome_metric"),
                    n_sample=data.get("n_sample"),
                    n_groups=data.get("n_groups")
                )
                
                logger.info(f"LLM extracted data from table {table_chunk_id}")
                return evidence
            
            return None
        
        except Exception as e:
            logger.error(f"LLM table extraction failed: {str(e)}")
            return None
    
    async def extract_figure_data(
        self,
        figure_chunk_id: str,
        figure_caption: str
    ) -> Optional[QuantitativeEvidence]:
        """ADDED: Extract quantitative data from figure captions"""
        
        try:
            evidence = QuantitativeEvidence(comparison_groups=[])
            
            # Extract from caption text
            # Look for figure type
            types = ["forest plot", "bar chart", "line graph", "survival curve", 
                    "scatter plot", "histogram", "box plot", "heatmap"]
            for ftype in types:
                if ftype.lower() in figure_caption.lower():
                    evidence.figure_type = ftype
                    break
            
            # Extract numeric values
            numbers = re.findall(r'-?\d+\.?\d{0,4}', figure_caption)
            p_matches = re.findall(r'p\s*=?\s*(\d+\.?\d{0,4})', figure_caption, re.IGNORECASE)
            
            if p_matches:
                evidence.p_value = float(p_matches[0])
            
            # Extract effect size if mentioned
            es_pattern = r'(?:effect\s*size|coefficient|OR|RR|HR)\s*=?\s*(\d+\.?\d{0,4})'
            es_matches = re.findall(es_pattern, figure_caption, re.IGNORECASE)
            if es_matches:
                evidence.effect_size = float(es_matches[0])
            
            # If we found something, return
            if (evidence.figure_type or evidence.p_value is not None or 
                evidence.effect_size is not None):
                logger.info(f"Extracted figure data from {figure_chunk_id}")
                return evidence
            
            # Try LLM
            return await self._extract_figure_with_llm(figure_chunk_id, figure_caption)
        
        except Exception as e:
            logger.error(f"Figure extraction failed: {str(e)}")
            return None
    
    async def _extract_figure_with_llm(
        self,
        figure_chunk_id: str,
        figure_caption: str
    ) -> Optional[QuantitativeEvidence]:
        """ADDED: Use LLM to extract quantitative data from figure captions"""
        
        try:
            prompt = f"""Extract quantitative data from this figure caption.

Figure caption:
{figure_caption}

Extract and return JSON:
{{
    "figure_type": null | "forest_plot" | "bar_chart" | "line_graph" | "survival_curve" | "other",
    "reported_finding": "one sentence summary of the finding",
    "effect_size": null | number,
    "p_value": null | number (0-1),
    "confidence_interval": null | [lower, upper],
    "comparison_groups": [],
    "outcome_metric": null | string
}}

Output JSON only, no explanation.
"""
            
            response = await self.llm_provider.generate_async([
                {
                    "role": "system",
                    "content": "You are a data extraction specialist for research figures."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ], max_tokens=400)
            
            content = response.get("content", "")
            
            # Extract JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                evidence = QuantitativeEvidence(
                    figure_type=data.get("figure_type"),
                    effect_size=data.get("effect_size"),
                    p_value=data.get("p_value"),
                    confidence_interval=tuple(data.get("confidence_interval", [])) if data.get("confidence_interval") else None,
                    comparison_groups=data.get("comparison_groups", []),
                    outcome_metric=data.get("outcome_metric")
                )
                
                logger.info(f"LLM extracted figure data from {figure_chunk_id}")
                return evidence
            
            return None
        
        except Exception as e:
            logger.error(f"LLM figure extraction failed: {str(e)}")
            return None
    
    async def extract_for_chunks(
        self,
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, Optional[QuantitativeEvidence]]:
        """ADDED: Extract quantitative data from all table/figure chunks in parallel"""
        
        results = {}
        tasks = []
        
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            chunk_type = chunk.get("chunk_type", "text")
            
            if chunk_type == "table":
                task = self.extract_table_data(chunk_id, chunk.get("raw_text", ""))
                tasks.append((chunk_id, task))
            elif chunk_type == "figure_caption":
                task = self.extract_figure_data(chunk_id, chunk.get("raw_text", ""))
                tasks.append((chunk_id, task))
        
        # Run all extractions in parallel
        if tasks:
            completed = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
            
            for (chunk_id, _), result in zip(tasks, completed):
                if isinstance(result, Exception):
                    logger.error(f"Extraction exception for {chunk_id}: {str(result)}")
                    results[chunk_id] = None
                else:
                    results[chunk_id] = result
        
        logger.info(f"Quantitative extraction complete: {len(results)} chunks processed")
        return results

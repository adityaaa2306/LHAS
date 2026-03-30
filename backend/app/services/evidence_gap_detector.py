"""CAPABILITY 1: Evidence Gap Detection and Feedback Signal

Analyzes claim clusters to identify missing evidence categories.
Runs async after ClaimGraphManager, emits targeted retrieval signals.
No LLM, no external calls — deterministic analysis only.
Target: <500ms per paper.
"""

import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

Logger = logging.getLogger(__name__)


class GapType(str, Enum):
    """Types of evidence gaps detected"""
    NULL_RESULT_UNDERREPRESENTED = "NULL_RESULT_UNDERREPRESENTED"
    MECHANISM_ABSENT = "MECHANISM_ABSENT"
    HIGH_QUALITY_STUDY_ABSENT = "HIGH_QUALITY_STUDY_ABSENT"
    CONTRADICTING_EVIDENCE_ABSENT = "CONTRADICTING_EVIDENCE_ABSENT"
    SUBGROUP_EVIDENCE_ABSENT = "SUBGROUP_EVIDENCE_ABSENT"


@dataclass
class EvidenceGap:
    """Detected gap in an evidence cluster"""
    cluster_id: str
    gap_type: GapType
    mission_id: str
    paper_id_just_processed: str
    cluster_claim_count: int
    suggestion: str
    supporting_claims: int
    contradicting_claims: int
    null_claims: int
    high_quality_claims: int
    mechanistic_claims: int
    populated_subgroups: Set[str]
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "cluster_id": self.cluster_id,
            "gap_type": self.gap_type.value,
            "mission_id": self.mission_id,
            "paper_id_just_processed": self.paper_id_just_processed,
            "cluster_claim_count": self.cluster_claim_count,
            "suggestion": self.suggestion,
            "supporting_claims": self.supporting_claims,
            "contradicting_claims": self.contradicting_claims,
            "null_claims": self.null_claims,
            "high_quality_claims": self.high_quality_claims,
            "mechanistic_claims": self.mechanistic_claims,
            "populated_subgroups": list(self.populated_subgroups),
            "timestamp": self.timestamp
        }


class EvidenceGapDetector:
    """Analyzes evidence clusters for missing evidence categories"""
    
    def __init__(self):
        self.detected_gaps: List[EvidenceGap] = []
    
    async def detect_gaps(
        self,
        mission_id: str,
        paper_id_just_processed: str,
        clusters: Dict[str, List[Dict]]
    ) -> List[EvidenceGap]:
        """
        Analyze clusters for evidence gaps.
        
        Args:
            mission_id: Mission identifier
            paper_id_just_processed: Paper that just updated graph
            clusters: Dict mapping cluster_id → List[claims]
                where each claim has: direction, claim_type, 
                study_design_score, population
        
        Returns:
            List of detected EvidenceGap objects
        """
        
        self.detected_gaps = []
        
        for cluster_id, claims in clusters.items():
            if not claims:
                continue
            
            gaps = self._analyze_cluster(
                cluster_id=cluster_id,
                claims=claims,
                mission_id=mission_id,
                paper_id_just_processed=paper_id_just_processed
            )
            
            self.detected_gaps.extend(gaps)
        
        Logger.info(f"[GAPS] Detected {len(self.detected_gaps)} gaps across {len(clusters)} clusters")
        return self.detected_gaps
    
    def _analyze_cluster(
        self,
        cluster_id: str,
        claims: List[Dict],
        mission_id: str,
        paper_id_just_processed: str
    ) -> List[EvidenceGap]:
        """Analyze single cluster for all gap types"""
        
        gaps = []
        
        # Statistics
        total_claims = len(claims)
        supporting = sum(1 for c in claims if c.get("direction") in ["positive", "negative"])
        contradicting = sum(1 for c in claims if c.get("direction") == "null")
        null_result = sum(1 for c in claims if c.get("direction") == "null")
        mechanistic = sum(1 for c in claims if c.get("claim_type") == "mechanistic")
        high_quality = sum(1 for c in claims if c.get("study_design_score", 0) >= 0.85)
        
        populations = set()
        for claim in claims:
            pop = claim.get("population", "")
            if pop:
                populations.add(pop)
        
        # Gap 1: Null result underrepresented
        if supporting >= 3 and null_result == 0:
            gap = EvidenceGap(
                cluster_id=cluster_id,
                gap_type=GapType.NULL_RESULT_UNDERREPRESENTED,
                mission_id=mission_id,
                paper_id_just_processed=paper_id_just_processed,
                cluster_claim_count=total_claims,
                suggestion=self._generate_null_result_query(cluster_id),
                supporting_claims=supporting,
                contradicting_claims=contradicting,
                null_claims=null_result,
                high_quality_claims=high_quality,
                mechanistic_claims=mechanistic,
                populated_subgroups=populations
            )
            gaps.append(gap)
            Logger.debug(f"[GAPS] Cluster {cluster_id}: null result underrepresented")
        
        # Gap 2: Mechanism absent
        outcome_level_claims = sum(
            1 for c in claims 
            if c.get("claim_type") in ["causal", "correlational"]
        )
        if outcome_level_claims > 0 and mechanistic == 0:
            gap = EvidenceGap(
                cluster_id=cluster_id,
                gap_type=GapType.MECHANISM_ABSENT,
                mission_id=mission_id,
                paper_id_just_processed=paper_id_just_processed,
                cluster_claim_count=total_claims,
                suggestion=self._generate_mechanism_query(cluster_id),
                supporting_claims=supporting,
                contradicting_claims=contradicting,
                null_claims=null_result,
                high_quality_claims=high_quality,
                mechanistic_claims=mechanistic,
                populated_subgroups=populations
            )
            gaps.append(gap)
            Logger.debug(f"[GAPS] Cluster {cluster_id}: mechanism absent")
        
        # Gap 3: High quality study absent
        if high_quality == 0 and total_claims >= 2:
            gap = EvidenceGap(
                cluster_id=cluster_id,
                gap_type=GapType.HIGH_QUALITY_STUDY_ABSENT,
                mission_id=mission_id,
                paper_id_just_processed=paper_id_just_processed,
                cluster_claim_count=total_claims,
                suggestion=self._generate_high_quality_query(cluster_id),
                supporting_claims=supporting,
                contradicting_claims=contradicting,
                null_claims=null_result,
                high_quality_claims=high_quality,
                mechanistic_claims=mechanistic,
                populated_subgroups=populations
            )
            gaps.append(gap)
            Logger.debug(f"[GAPS] Cluster {cluster_id}: high quality study absent")
        
        # Gap 4: Contradicting evidence absent (potential retrieval bias)
        support_ratio = supporting / total_claims if total_claims > 0 else 0
        if support_ratio > 0.90 and total_claims >= 5:
            gap = EvidenceGap(
                cluster_id=cluster_id,
                gap_type=GapType.CONTRADICTING_EVIDENCE_ABSENT,
                mission_id=mission_id,
                paper_id_just_processed=paper_id_just_processed,
                cluster_claim_count=total_claims,
                suggestion=self._generate_contradicting_query(cluster_id),
                supporting_claims=supporting,
                contradicting_claims=contradicting,
                null_claims=null_result,
                high_quality_claims=high_quality,
                mechanistic_claims=mechanistic,
                populated_subgroups=populations
            )
            gaps.append(gap)
            Logger.warning(f"[GAPS] Cluster {cluster_id}: potential retrieval bias (99%+ consensus)")
        
        # Gap 5: Subgroup evidence absent
        if len(populations) <= 1 and total_claims >= 3:
            gap = EvidenceGap(
                cluster_id=cluster_id,
                gap_type=GapType.SUBGROUP_EVIDENCE_ABSENT,
                mission_id=mission_id,
                paper_id_just_processed=paper_id_just_processed,
                cluster_claim_count=total_claims,
                suggestion=self._generate_subgroup_query(cluster_id),
                supporting_claims=supporting,
                contradicting_claims=contradicting,
                null_claims=null_result,
                high_quality_claims=high_quality,
                mechanistic_claims=mechanistic,
                populated_subgroups=populations
            )
            gaps.append(gap)
            Logger.debug(f"[GAPS] Cluster {cluster_id}: subgroup evidence absent")
        
        return gaps
    
    def _generate_null_result_query(self, cluster_id: str) -> str:
        """Generate retrieval query for null result evidence"""
        # In real implementation, extract intervention/outcome from cluster_id
        intervention, outcome = cluster_id.split("|")
        return f'"{intervention}" "no significant effect" "null result" "{outcome}"'
    
    def _generate_mechanism_query(self, cluster_id: str) -> str:
        """Generate retrieval query for mechanistic evidence"""
        intervention, outcome = cluster_id.split("|")
        return f'"{intervention}" mechanism pathway mediates "{outcome}"'
    
    def _generate_high_quality_query(self, cluster_id: str) -> str:
        """Generate retrieval query for high-quality studies"""
        intervention, outcome = cluster_id.split("|")
        return f'"{intervention}" randomized controlled trial meta-analysis "{outcome}"'
    
    def _generate_contradicting_query(self, cluster_id: str) -> str:
        """Generate retrieval query to find contradicting evidence"""
        intervention, outcome = cluster_id.split("|")
        return f'NOT "{intervention}" -"{outcome}" alternative treatment comparison rigor'
    
    def _generate_subgroup_query(self, cluster_id: str) -> str:
        """Generate retrieval query for subgroup analysis"""
        intervention, outcome = cluster_id.split("|")
        return f'"{intervention}" subgroup analysis "{outcome}" age sex race ethnicity'
    
    async def emit_gap_events(
        self,
        gaps: List[EvidenceGap],
        event_emitter
    ):
        """Emit evidence_gap.detected events for ingestion module"""
        
        for gap in gaps:
            event_data = gap.to_dict()
            
            Logger.info(f"[GAPS] Emitting gap event: {gap.gap_type.value} in cluster {gap.cluster_id}")
            
            await event_emitter.emit("evidence_gap.detected", event_data)
    
    def get_detected_gaps(self) -> List[EvidenceGap]:
        """Return list of detected gaps from last analysis"""
        return self.detected_gaps
    
    def get_gaps_by_type(self, gap_type: GapType) -> List[EvidenceGap]:
        """Filter gaps by type"""
        return [g for g in self.detected_gaps if g.gap_type == gap_type]
    
    def get_suggestion_queries(self) -> List[str]:
        """Extract all suggestion queries for retrieval module"""
        return [gap.suggestion for gap in self.detected_gaps]

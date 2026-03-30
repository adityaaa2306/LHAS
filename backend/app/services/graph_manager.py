"""ADDED: Claim Graph Management with Cross-Paper Deduplication and Feedback

Builds knowledge graph of claims with entity-level clustering,
contradiction detection, replication tracking, and feedback loops
for improving subsequent extractions.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime
import numpy as np
from sqlalchemy import insert, select, and_, or_
import uuid

logger = logging.getLogger(__name__)


@dataclass
class ClaimGraphEvent:
    """Events emitted by graph manager"""
    event_type: str  # "graph.updated", "contradiction.detected", "cluster.updated"
    mission_id: str
    timestamp: datetime
    data: Dict[str, Any]


class ClaimGraphManager:
    """ADDED: Manages claim graph and entity-level reasoning"""
    
    def __init__(self, db: Any, embedding_service: Any):
        """
        Initialize graph manager.
        
        Args:
            db: AsyncSession database connection
            embedding_service: Service for embedding similarity
        """
        self.db = db
        self.embedding_service = embedding_service
        self.events: List[ClaimGraphEvent] = []
        
        logger.info("ClaimGraphManager initialized")
    
    async def add_claims_to_graph(
        self,
        mission_id: str,
        claims: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """ADDED: Add newly extracted claims to knowledge graph"""
        
        try:
            # Group claims by (intervention_canonical, outcome_canonical)
            clusters = self._cluster_by_entity(claims)
            
            logger.info(f"Organizing {len(claims)} claims into {len(clusters)} clusters")
            
            # For each cluster, detect relationships
            for entity_pair, cluster_claims in clusters.items():
                await self._process_cluster(mission_id, entity_pair, cluster_claims)
            
            # Emit graph.updated event
            self.events.append(ClaimGraphEvent(
                event_type="graph.updated",
                mission_id=mission_id,
                timestamp=datetime.utcnow(),
                data={
                    "claims_added": len(claims),
                    "clusters_created": len(clusters),
                    "contradictions_detected": len([e for e in self.events if e.event_type == "contradiction.detected"])
                }
            ))
            
            return {
                "success": True,
                "claims_added": len(claims),
                "clusters_updated": len(clusters),
                "events": len(self.events)
            }
        
        except Exception as e:
            logger.error(f"Failed to add claims to graph: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _cluster_by_entity(
        self,
        claims: List[Dict[str, Any]]
    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """ADDED: Group claims by (intervention, outcome) entity pair"""
        
        clusters: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        
        for claim in claims:
            intervention = claim.get("intervention_canonical", "unknown")
            outcome = claim.get("outcome_canonical", "unknown")
            
            pair = (intervention, outcome)
            if pair not in clusters:
                clusters[pair] = []
            clusters[pair].append(claim)
        
        return clusters
    
    async def _process_cluster(
        self,
        mission_id: str,
        entity_pair: Tuple[str, str],
        cluster_claims: List[Dict[str, Any]]
    ) -> None:
        """ADDED: Process single cluster for contradictions and replicates"""
        
        intervention, outcome = entity_pair
        
        logger.info(f"Processing cluster: {intervention} -> {outcome} ({len(cluster_claims)} claims)")
        
        # Get embeddings for all claims in cluster
        embeddings = []
        for claim in cluster_claims:
            # Use statement embedding
            stmt = claim.get("statement_raw", "")
            if stmt:
                emb = await self.embedding_service.embed_async(stmt)
                embeddings.append(emb)
            else:
                embeddings.append(None)
        
        # Pairwise comparison within cluster
        for i in range(len(cluster_claims)):
            for j in range(i + 1, len(cluster_claims)):
                claim_i = cluster_claims[i]
                claim_j = cluster_claims[j]
                
                # Skip if no embeddings
                if embeddings[i] is None or embeddings[j] is None:
                    continue
                
                # Compute similarity
                similarity = np.dot(
                    embeddings[i],
                    embeddings[j]
                ) / (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]) + 1e-8)
                
                direction_i = claim_i.get("direction", "").upper()
                direction_j = claim_j.get("direction", "").upper()
                
                # Check for contradictions (opposite directions, high similarity)
                if direction_i != direction_j and similarity > 0.80:
                    # Found contradiction
                    self.events.append(ClaimGraphEvent(
                        event_type="contradiction.detected",
                        mission_id=mission_id,
                        timestamp=datetime.utcnow(),
                        data={
                            "claim_1_id": claim_i.get("id"),
                            "claim_2_id": claim_j.get("id"),
                            "similarity": float(similarity),
                            "intervention": intervention,
                            "outcome": outcome,
                            "direction_1": direction_i,
                            "direction_2": direction_j
                        }
                    ))
                    logger.warning(f"Contradiction detected: {direction_i} vs {direction_j} (sim={similarity:.2f})")
                
                # Check for replication (same direction, high similarity)
                elif direction_i == direction_j and similarity > 0.88:
                    # Found replication
                    conf_i = claim_i.get("composite_confidence", 0.5)
                    conf_j = claim_j.get("composite_confidence", 0.5)
                    
                    # Mark lower confidence as replicated by higher
                    if conf_i > conf_j:
                        replicated_claim_id = claim_j.get("id")
                        replicating_claim_id = claim_i.get("id")
                    else:
                        replicated_claim_id = claim_i.get("id")
                        replicating_claim_id = claim_j.get("id")
                    
                    logger.info(f"Replication detected: {replicated_claim_id} replicated by {replicating_claim_id}")
    
    async def build_entity_boost_index(
        self,
        mission_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """ADDED: Build index of entities for query feedback"""
        
        try:
            # Query all canonical entities in mission with >2 claims
            # This is a simplified version - in production would query database
            
            entity_index = {}
            
            # For each entity, store:
            # - canonical form
            # - surface forms / aliases
            # - claim count
            # - embedding
            
            logger.info(f"Built entity boost index for mission {mission_id}")
            return entity_index
        
        except Exception as e:
            logger.error(f"Failed to build entity boost index: {str(e)}")
            return {}
    
    async def export_retrieval_feedback(
        self,
        mission_id: str
    ) -> Dict[str, Any]:
        """ADDED: Export feedback for improving next paper's retrieval"""
        
        try:
            # Get entity boost index
            entity_index = await self.build_entity_boost_index(mission_id)
            
            # Generate Query 6 candidates for next retrieval
            query6_terms = []
            for entity_id, entity_data in entity_index.items():
                surface_forms = entity_data.get("surface_forms", [])
                canonical = entity_data.get("canonical", "")
                
                if surface_forms:
                    query6_terms.extend(surface_forms)
            
            return {
                "entity_index": entity_index,
                "query6_candidates": query6_terms,
                "boost_thresholds": {
                    "similarity_threshold": 0.80,
                    "min_claim_count": 2
                }
            }
        
        except Exception as e:
            logger.error(f"Failed to export retrieval feedback: {str(e)}")
            return {}
    
    async def apply_entity_boost_in_normalization(
        self,
        extracted_entity: str,
        mission_id: str
    ) -> Optional[str]:
        """ADDED: Check entity boost index before Pass 2b LLM call"""
        
        try:
            # Query entity index for fuzzy match
            # If found with high confidence, return canonical form directly
            # This avoids redundant LLM calls
            
            # Simplified: just check if entity exactly matches any known form
            entity_boost_index = await self.build_entity_boost_index(mission_id)
            
            for entity_id, entity_data in entity_boost_index.items():
                canonical = entity_data.get("canonical", "")
                surface_forms = entity_data.get("surface_forms", [])
                
                # Exact match
                if extracted_entity.lower() == canonical.lower():
                    logger.info(f"Entity boost hit: {extracted_entity} -> {canonical} (exact)")
                    return canonical
                
                # Fuzzy match
                for surface in surface_forms:
                    if self._fuzzy_match(extracted_entity, surface, threshold=0.92):
                        logger.info(f"Entity boost hit: {extracted_entity} -> {canonical} (fuzzy)")
                        return canonical
            
            return None
        
        except Exception as e:
            logger.error(f"Entity boost lookup failed: {str(e)}")
            return None
    
    def _fuzzy_match(self, str1: str, str2: str, threshold: float = 0.8) -> bool:
        """ADDED: Simple fuzzy matching for entity aliases"""
        
        # Simple character-based similarity
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
        return ratio >= threshold
    
    async def get_events(self) -> List[Dict[str, Any]]:
        """ADDED: Get all emitted events"""
        return [
            {
                "event_type": e.event_type,
                "mission_id": e.mission_id,
                "timestamp": e.timestamp.isoformat(),
                "data": e.data
            }
            for e in self.events
        ]
    
    async def clear_events(self) -> None:
        """ADDED: Clear emitted events"""
        self.events = []


class EntityBoostIndex:
    """ADDED: Persistent index of known entities for feedback loop"""
    
    def __init__(self, db: Any):
        self.db = db
    
    async def register_canonical_entity(
        self,
        mission_id: str,
        canonical_form: str,
        surface_forms: List[str],
        entity_type: str = "intervention"
    ) -> bool:
        """ADDED: Register canonical entity to boost index"""
        
        try:
            # In production, store in database
            logger.info(f"Registered entity: {canonical_form} ({entity_type}) with {len(surface_forms)} surface forms")
            return True
        except Exception as e:
            logger.error(f"Failed to register entity: {str(e)}")
            return False
    
    async def lookup_entity(
        self,
        query: str,
        mission_id: str,
        entity_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """ADDED: Look up entity by surface form"""
        
        try:
            # In production, query database with fuzzy matching
            logger.debug(f"Looking up entity: {query}")
            return None
        except Exception as e:
            logger.error(f"Entity lookup failed: {str(e)}")
            return None

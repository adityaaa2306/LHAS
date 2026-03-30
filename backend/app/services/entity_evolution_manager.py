"""CAPABILITY 4: Entity Evolution and Vocabulary Growth

Manages dynamic controlled vocabulary that grows with feedback.
Tracks provisional entities, operator decisions, and auto-promotion.
Re-runs normalization when glossary updates.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import difflib

Logger = logging.getLogger(__name__)


class EntityStatus(str, Enum):
    """Status of an entity in the vocabulary"""
    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    MERGE_CANDIDATE = "merge_candidate"
    REJECTED = "rejected"


@dataclass
class EntityNode:
    """Managed entity in controlled vocabulary"""
    entity_id: str
    canonical_form: str
    surface_forms: Set[str]
    status: EntityStatus
    context: Optional[str]
    paper_ids: Set[str]
    mission_ids: Set[str]
    normalization_confidence: float
    created_at: str
    updated_at: str
    glossary_version: int
    
    def to_dict(self) -> Dict:
        return {
            "entity_id": self.entity_id,
            "canonical_form": self.canonical_form,
            "surface_forms": list(self.surface_forms),
            "status": self.status.value,
            "context": self.context,
            "paper_count": len(self.paper_ids),
            "mission_count": len(self.mission_ids),
            "normalization_confidence": self.normalization_confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "glossary_version": self.glossary_version
        }


class GlossaryVersion:
    """Tracks glossary version history"""
    
    def __init__(self):
        self.version = 0
        self.history: List[Dict] = []
    
    def increment(self, description: str):
        self.version += 1
        self.history.append({
            "version": self.version,
            "timestamp": datetime.utcnow().isoformat(),
            "description": description
        })


class EntityEvolutionManager:
    """Manages entity vocabulary evolution"""
    
    def __init__(self):
        self.entities: Dict[str, EntityNode] = {}
        self.glossary_version = GlossaryVersion()
        self.merge_candidates: List[Dict] = []
        self.new_candidates: List[Dict] = []
        self.auto_promotions: List[str] = []
    
    async def propose_normalization(
        self,
        surface_form: str,
        context_sentence: str,
        normalization_confidence: float,
        paper_id: str,
        mission_id: str,
        claim_id: str
    ) -> Tuple[str, EntityStatus]:
        """
        Handle entity normalization with dynamic vocabulary.
        
        Returns:
            (canonical_form, status) where status indicates if confirmed/pending
        """
        
        # Try to find existing canonical match (high confidence)
        exact_match = self._find_exact_match(surface_form)
        if exact_match:
            Logger.debug(f"[ENTITY] Exact match found: {surface_form} → {exact_match.canonical_form}")
            self._add_surface_form_to_entity(exact_match.entity_id, surface_form)
            return exact_match.canonical_form, EntityStatus.CONFIRMED
        
        # Try fuzzy match to existing confirmed entity
        fuzzy_match = self._find_fuzzy_match(surface_form, threshold=0.88)
        if fuzzy_match:
            Logger.debug(f"[ENTITY] Fuzzy match: {surface_form} → {fuzzy_match.canonical_form}")
            self._add_surface_form_to_entity(fuzzy_match.entity_id, surface_form)
            return fuzzy_match.canonical_form, EntityStatus.CONFIRMED
        
        # Try to find merge candidate (moderate similarity)
        merge_candidate = self._find_fuzzy_match(surface_form, threshold=0.65, max_threshold=0.88)
        if merge_candidate:
            Logger.warning(f"[ENTITY] Merge candidate: {surface_form} vs {merge_candidate.canonical_form}")
            
            candidate_event = {
                "new_surface_form": surface_form,
                "nearest_canonical": merge_candidate.canonical_form,
                "similarity_score": self._compute_similarity(surface_form, merge_candidate.canonical_form),
                "paper_id": paper_id,
                "mission_id": mission_id,
                "claim_id": claim_id,
                "status": "pending_operator_review",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.merge_candidates.append(candidate_event)
            
            # Create provisional entity
            provisional = self._create_provisional_entity(
                surface_form=surface_form,
                context=context_sentence,
                confidence=normalization_confidence,
                paper_id=paper_id,
                mission_id=mission_id
            )
            
            return surface_form, EntityStatus.MERGE_CANDIDATE
        
        # No match — create new entity candidate
        Logger.info(f"[ENTITY] New entity candidate: {surface_form}")
        
        new_event = {
            "surface_form": surface_form,
            "context_sentence": context_sentence,
            "paper_id": paper_id,
            "mission_id": mission_id,
            "claim_id": claim_id,
            "normalization_confidence": normalization_confidence,
            "status": "pending_operator_review",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.new_candidates.append(new_event)
        
        # Create provisional entity
        provisional = self._create_provisional_entity(
            surface_form=surface_form,
            context=context_sentence,
            confidence=normalization_confidence,
            paper_id=paper_id,
            mission_id=mission_id
        )
        
        return surface_form, EntityStatus.PROVISIONAL
    
    def _find_exact_match(self, surface_form: str) -> Optional[EntityNode]:
        """Find exact match in confirmed entities"""
        
        for entity in self.entities.values():
            if entity.status == EntityStatus.CONFIRMED:
                norm_form = surface_form.lower().strip()
                for candidate in entity.surface_forms:
                    if candidate.lower().strip() == norm_form:
                        return entity
        
        return None
    
    def _find_fuzzy_match(
        self,
        surface_form: str,
        threshold: float = 0.88,
        max_threshold: float = 1.0
    ) -> Optional[EntityNode]:
        """Find fuzzy match in entities"""
        
        best_match = None
        best_score = 0
        
        for entity in self.entities.values():
            if entity.status == EntityStatus.CONFIRMED:
                for candidate_form in entity.surface_forms:
                    similarity = self._compute_similarity(surface_form, candidate_form)
                    
                    if threshold <= similarity <= max_threshold and similarity > best_score:
                        best_match = entity
                        best_score = similarity
        
        return best_match
    
    def _compute_similarity(self, str1: str, str2: str) -> float:
        """Compute string similarity using SequenceMatcher"""
        
        return difflib.SequenceMatcher(
            None,
            str1.lower().strip(),
            str2.lower().strip()
        ).ratio()
    
    def _create_provisional_entity(
        self,
        surface_form: str,
        context: str,
        confidence: float,
        paper_id: str,
        mission_id: str
    ) -> EntityNode:
        """Create a new provisional entity"""
        
        entity_id = f"entity_{len(self.entities)}"
        
        entity = EntityNode(
            entity_id=entity_id,
            canonical_form=surface_form,  # Use surface form as provisional canonical
            surface_forms={surface_form},
            status=EntityStatus.PROVISIONAL,
            context=context,
            paper_ids={paper_id},
            mission_ids={mission_id},
            normalization_confidence=confidence,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            glossary_version=self.glossary_version.version
        )
        
        self.entities[entity_id] = entity
        return entity
    
    def _add_surface_form_to_entity(self, entity_id: str, surface_form: str):
        """Add surface form to existing entity"""
        
        if entity_id in self.entities:
            self.entities[entity_id].surface_forms.add(surface_form)
            self.entities[entity_id].updated_at = datetime.utcnow().isoformat()
    
    async def operator_merge_decision(
        self,
        new_surface_form: str,
        canonical_form: str
    ):
        """Operator confirmed merge"""
        
        Logger.info(f"[ENTITY] Operator merge: {new_surface_form} → {canonical_form}")
        
        # Find the canonical entity
        target = None
        for entity in self.entities.values():
            if entity.canonical_form == canonical_form:
                target = entity
                break
        
        if target:
            target.surface_forms.add(new_surface_form)
            target.updated_at = datetime.utcnow().isoformat()
        
        self.glossary_version.increment(f"Merged {new_surface_form} into {canonical_form}")
    
    async def operator_new_entity_decision(
        self,
        surface_form: str,
        canonical_form: str,
        context: str
    ):
        """Operator confirmed new entity"""
        
        Logger.info(f"[ENTITY] Operator confirmed new entity: {canonical_form}")
        
        entity = EntityNode(
            entity_id=f"entity_{len(self.entities)}",
            canonical_form=canonical_form,
            surface_forms={surface_form},
            status=EntityStatus.CONFIRMED,
            context=context,
            paper_ids=set(),
            mission_ids=set(),
            normalization_confidence=0.95,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            glossary_version=self.glossary_version.version
        )
        
        self.entities[entity.entity_id] = entity
        self.glossary_version.increment(f"Confirmed new entity: {canonical_form}")
    
    async def operator_reject_entity(
        self,
        surface_form: str
    ):
        """Operator rejected entity as out-of-scope"""
        
        Logger.info(f"[ENTITY] Operator rejected: {surface_form}")
        
        # Mark any provisional entities matching this surface form as rejected
        for entity in self.entities.values():
            if entity.canonical_form == surface_form:
                entity.status = EntityStatus.REJECTED
        
        self.glossary_version.increment(f"Rejected: {surface_form}")
    
    async def auto_promote_provisional(
        self,
        surface_form: str,
        mission_id: str,
        paper_count_threshold: int = 3
    ):
        """Auto-promote provisional entity if seen in many papers"""
        
        Logger.info(f"[ENTITY] Auto-promoting provisional: {surface_form}")
        
        # Find provisional entity
        for entity in self.entities.values():
            if (entity.canonical_form == surface_form and
                entity.status == EntityStatus.PROVISIONAL and
                len(entity.paper_ids) >= paper_count_threshold):
                
                entity.status = EntityStatus.CONFIRMED
                entity.updated_at = datetime.utcnow().isoformat()
                self.auto_promotions.append(surface_form)
                self.glossary_version.increment(f"Auto-promoted: {surface_form}")
                
                Logger.info(f"[ENTITY] Auto-promotion complete: {surface_form}")
    
    async def retrospective_normalization_pass(
        self,
        mission_id: str,
        uncertain_claims: List[Dict]
    ) -> List[Dict]:
        """
        Re-run normalization on claims marked uncertain.
        Called after glossary update.
        """
        
        Logger.info(f"[ENTITY] Starting retrospective normalization pass for {len(uncertain_claims)} claims")
        
        updated_claims = []
        
        for claim in uncertain_claims:
            old_canonical = claim.get("intervention_canonical", "unknown")
            
            # Try normalization again with updated glossary
            new_canonical, status = await self.propose_normalization(
                surface_form=claim.get("intervention", ""),
                context_sentence=claim.get("statement_raw", ""),
                normalization_confidence=claim.get("normalization_confidence", 0.5),
                paper_id=claim.get("paper_id", ""),
                mission_id=mission_id,
                claim_id=claim.get("id", "")
            )
            
            if new_canonical != old_canonical:
                Logger.info(f"[ENTITY] Retrospective update: {claim.get('id')} {old_canonical} → {new_canonical}")
                claim["intervention_canonical"] = new_canonical
                claim["normalization_source"] = "retrospective"
                updated_claims.append(claim)
        
        return updated_claims
    
    async def emit_entity_events(self, event_emitter):
        """Emit entity-related events"""
        
        # Emit merge candidates
        for candidate in self.merge_candidates:
            await event_emitter.emit("entity.merge_candidate", candidate)
        
        # Emit new candidates
        for candidate in self.new_candidates:
            await event_emitter.emit("entity.new_candidate", candidate)
        
        # Emit auto-promotions
        for surface_form in self.auto_promotions:
            await event_emitter.emit("entity.auto_promoted", {
                "surface_form": surface_form,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    def get_glossary_status(self) -> Dict:
        """Return glossary statistics"""
        
        confirmed = sum(1 for e in self.entities.values() if e.status == EntityStatus.CONFIRMED)
        provisional = sum(1 for e in self.entities.values() if e.status == EntityStatus.PROVISIONAL)
        rejected = sum(1 for e in self.entities.values() if e.status == EntityStatus.REJECTED)
        
        return {
            "glossary_version": self.glossary_version.version,
            "confirmed_entities": confirmed,
            "provisional_entities": provisional,
            "rejected_entities": rejected,
            "merge_candidates_pending": len(self.merge_candidates),
            "new_candidates_pending": len(self.new_candidates),
            "auto_promotions": len(self.auto_promotions)
        }

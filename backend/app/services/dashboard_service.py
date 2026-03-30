from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Dict, Any
from app.models import Mission, Alert, MissionStatus, HealthStatus, AlertSeverity, IntentType, QueryAnalysis
from datetime import datetime
from uuid import UUID
import uuid
import json
from app.services.query_understanding import get_query_understanding_module


class DashboardService:
    """Service layer for dashboard data aggregation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard_stats(self) -> Dict[str, int]:
        """
        Get dashboard statistics efficiently in a single query batch.
        Avoids N+1 queries by using aggregations.
        
        Returns:
            Dict with: total_missions, active_missions, missions_needing_attention, total_alerts
        """
        # Count total missions
        total_missions_stmt = select(func.count(Mission.id))
        total_missions = await self.db.scalar(total_missions_stmt)

        # Count active missions
        active_missions_stmt = select(func.count(Mission.id)).where(
            Mission.status == MissionStatus.ACTIVE
        )
        active_missions = await self.db.scalar(active_missions_stmt)

        # Count missions needing attention (non-healthy health status)
        needing_attention_stmt = select(func.count(Mission.id)).where(
            Mission.health.in_([HealthStatus.WATCH, HealthStatus.DEGRADED, HealthStatus.CRITICAL])
        )
        missions_needing_attention = await self.db.scalar(needing_attention_stmt)

        # Sum active alerts across all missions
        total_alerts_stmt = select(func.sum(Mission.active_alerts))
        total_alerts = await self.db.scalar(total_alerts_stmt) or 0

        return {
            "total_missions": total_missions or 0,
            "active_missions": active_missions or 0,
            "missions_needing_attention": missions_needing_attention or 0,
            "total_alerts": int(total_alerts),
        }

    async def get_recent_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent alerts with mission context.
        
        Args:
            limit: Maximum number of alerts to return
            
        Returns:
            List of alerts with mission names and severity info
        """
        stmt = (
            select(
                Alert.id,
                Alert.mission_id,
                Alert.alert_type,
                Alert.severity,
                Alert.cycle_number,
                Alert.lifecycle_status,
                Alert.message,
                Alert.created_at,
                Mission.name.label("mission_name"),
            )
            .join(Mission, Alert.mission_id == Mission.id)
            .where(Alert.lifecycle_status.in_(["firing", "active"]))
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        alerts = result.fetchall()

        return [
            {
                "id": alert.id,
                "mission_id": alert.mission_id,
                "mission_name": alert.mission_name,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "cycle_number": alert.cycle_number,
                "lifecycle_status": alert.lifecycle_status,
                "message": alert.message,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            }
            for alert in alerts
        ]

    async def get_all_missions(self) -> List[Dict[str, Any]]:
        """
        Get all missions with full details for dashboard.
        Single efficient query with all necessary joins.
        
        Returns:
            List of missions with all dashboard-required fields
        """
        stmt = select(Mission).order_by(Mission.last_run.desc().nullslast())
        result = await self.db.execute(stmt)
        missions = result.scalars().all()

        return [
            {
                "id": mission.id,
                "name": mission.name,
                "query": mission.normalized_query,
                "intent_type": mission.intent_type.value if mission.intent_type else None,
                "status": mission.status.value if mission.status else None,
                "health": mission.health.value if mission.health else None,
                "last_run": mission.last_run.isoformat() if mission.last_run else None,
                "papers": mission.total_papers,
                "claims": mission.total_claims,
                "confidence": round(mission.confidence_score, 2),
                "sessions": mission.session_count,
                "active_alerts": mission.active_alerts,
                "created_at": mission.created_at.isoformat() if mission.created_at else None,
                "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
            }
            for mission in missions
        ]

    async def get_mission_by_id(self, mission_id: str) -> Dict[str, Any] | None:
        """
        Get a specific mission with full details.
        
        Args:
            mission_id: Mission ID to retrieve
            
        Returns:
            Mission details or None if not found
        """
        stmt = select(Mission).where(Mission.id == mission_id)
        result = await self.db.execute(stmt)
        mission = result.scalar_one_or_none()

        if not mission:
            return None

        return {
            "id": mission.id,
            "name": mission.name,
            "query": mission.normalized_query,
            "intent_type": mission.intent_type.value if mission.intent_type else None,
            "status": mission.status.value if mission.status else None,
            "health": mission.health.value if mission.health else None,
            "pico": {
                "population": mission.pico_population,
                "intervention": mission.pico_intervention,
                "comparator": mission.pico_comparator,
                "outcome": mission.pico_outcome,
            } if any([mission.pico_population, mission.pico_intervention, mission.pico_comparator, mission.pico_outcome]) else None,
            "decision": mission.decision,
            "key_concepts": mission.key_concepts.split(",") if mission.key_concepts else [],
            "ambiguity_flags": mission.ambiguity_flags.split(",") if mission.ambiguity_flags else [],
            "last_run": mission.last_run.isoformat() if mission.last_run else None,
            "papers": mission.total_papers,
            "claims": mission.total_claims,
            "confidence": round(mission.confidence_score, 2),
            "confidence_initial": round(mission.confidence_from_module1, 2) if mission.confidence_from_module1 else None,
            "sessions": mission.session_count,
            "active_alerts": mission.active_alerts,
            "created_at": mission.created_at.isoformat() if mission.created_at else None,
            "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
        }

    async def get_mission_alerts(self, mission_id: str) -> List[Dict[str, Any]]:
        """
        Get all alerts for a specific mission.
        
        Args:
            mission_id: Mission ID to get alerts for
            
        Returns:
            List of alerts for the mission
        """
        stmt = (
            select(Alert)
            .where(Alert.mission_id == mission_id)
            .order_by(Alert.created_at.desc())
        )
        result = await self.db.execute(stmt)
        alerts = result.scalars().all()

        return [
            {
                "id": alert.id,
                "alert_type": alert.alert_type,
                "severity": alert.severity.value if alert.severity else None,
                "cycle_number": alert.cycle_number,
                "lifecycle_status": alert.lifecycle_status,
                "message": alert.message,
                "resolution_record": alert.resolution_record,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }
            for alert in alerts
        ]

    async def create_mission(
        self,
        name: str,
        query: str,
        intent_type: str,
        pico_population: str | None = None,
        pico_intervention: str | None = None,
        pico_comparator: str | None = None,
        pico_outcome: str | None = None,
        key_concepts: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Create a new mission from scratch.
        
        This method:
        1. Creates the mission record
        2. Calls Query Understanding Module to analyze the query
        3. Stores the analysis in query_analysis table
        
        Args:
            name: Mission name
            query: Research query/question
            intent_type: Type of research intent (Causal, Comparative, Exploratory, Descriptive)
            pico_population: PICO population element
            pico_intervention: PICO intervention element
            pico_comparator: PICO comparator element
            pico_outcome: PICO outcome element
            key_concepts: List of key concepts/keywords
            
        Returns:
            Created mission details
        """
        mission_id = str(uuid.uuid4())
        
        # Convert intent_type string to enum
        try:
            intent_enum = IntentType(intent_type)
        except ValueError:
            intent_enum = IntentType.EXPLORATORY

        key_concepts_str = ",".join(key_concepts) if key_concepts else None

        mission = Mission(
            id=mission_id,
            name=name,
            normalized_query=query,
            intent_type=intent_enum,
            status=MissionStatus.IDLE,
            health=HealthStatus.HEALTHY,
            pico_population=pico_population,
            pico_intervention=pico_intervention,
            pico_comparator=pico_comparator,
            pico_outcome=pico_outcome,
            key_concepts=key_concepts_str,
            total_papers=0,
            total_claims=0,
            confidence_score=0.0,
            active_alerts=0,
            session_count=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.db.add(mission)
        await self.db.commit()
        await self.db.refresh(mission)

        # Analyze query and store analysis in database
        try:
            module = get_query_understanding_module()
            analysis = await module.analyze_query(
                query=query,
                mission_id=mission_id,
                optional_context=None,
            )
            # Analysis is automatically logged to DB via _log_analysis method
        except Exception as e:
            # Log error but don't fail mission creation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to store query analysis for mission {mission_id}: {str(e)}")

        return {
            "id": mission.id,
            "name": mission.name,
            "query": mission.normalized_query,
            "intent_type": mission.intent_type.value if mission.intent_type else None,
            "status": mission.status.value if mission.status else None,
            "health": mission.health.value if mission.health else None,
            "pico": {
                "population": mission.pico_population,
                "intervention": mission.pico_intervention,
                "comparator": mission.pico_comparator,
                "outcome": mission.pico_outcome,
            } if any([mission.pico_population, mission.pico_intervention, mission.pico_comparator, mission.pico_outcome]) else None,
            "key_concepts": mission.key_concepts.split(",") if mission.key_concepts else [],
            "papers": mission.total_papers,
            "claims": mission.total_claims,
            "confidence": mission.confidence_score,
            "sessions": mission.session_count,
            "active_alerts": mission.active_alerts,
            "created_at": mission.created_at.isoformat() if mission.created_at else None,
            "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
        }

    async def delete_mission(self, mission_id: str) -> bool:
        """
        Delete a mission and all its associated alerts and data.
        
        Args:
            mission_id: Mission ID to delete
            
        Returns:
            True if mission was deleted, False if not found
        """
        # Find mission
        stmt = select(Mission).where(Mission.id == mission_id)
        result = await self.db.execute(stmt)
        mission = result.scalar_one_or_none()
        
        if not mission:
            return False
        
        # Delete associated alerts first
        alert_stmt = select(Alert).where(Alert.mission_id == mission_id)
        result = await self.db.execute(alert_stmt)
        alerts = result.scalars().all()
        for alert in alerts:
            await self.db.delete(alert)
        
        # Delete mission
        await self.db.delete(mission)
        await self.db.commit()
        
        return True

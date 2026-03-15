#!/usr/bin/env python3
"""
Trust Model for Mnemosyne Knowledge Vault.

Manages agent autonomy based on demonstrated reliability:
  - Tracks successful vs. failed actions per area
  - Calculates trust scores (0.0 to 1.0)
  - Auto-adjusts autonomy levels based on trust
  - Provides trust-aware authorization

Trust is earned through:
  - Successful task completion
  - Accurate research citations
  - User approval of suggestions
  - Consistent quality over time

Trust is lost through:
  - Failed actions
  - Incorrect information
  - User corrections
  - Missed deadlines

Usage:
    from trust import TrustModel

    trust = TrustModel(vault_path="~/.hermes/memory")
    
    # Record an outcome
    trust.record_outcome("eeg", "research", success=True, quality=0.9)
    
    # Get recommended autonomy level
    level = trust.get_recommended_autonomy("eeg", "research")
    
    # Get trust report
    report = trust.get_trust_report("eeg")
"""

import os
import json
import math
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from intent import AutonomyLevel


# ─── Constants ────────────────────────────────────────────────────

# Trust thresholds for autonomy levels
TRUST_THRESHOLDS = {
    AutonomyLevel.AUTONOMOUS: 0.8,
    AutonomyLevel.NOTIFY: 0.5,
    AutonomyLevel.APPROVE: 0.2,
    AutonomyLevel.FORBIDDEN: 0.0,
}

# Decay: trust decays 5% per week without activity
TRUST_DECAY_RATE = 0.05  # per week
TRUST_DECAY_INTERVAL = 7  # days

# Weights for trust calculation
WEIGHT_SUCCESS_RATE = 0.4
WEIGHT_QUALITY = 0.3
WEIGHT_RECENCY = 0.2
WEIGHT_VOLUME = 0.1


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class TrustOutcome:
    """A single recorded outcome."""
    project: str
    area: str
    success: bool
    quality: float  # 0.0 to 1.0
    timestamp: str
    details: str = ""
    user_rating: Optional[float] = None  # 0.0 to 1.0 if user provided


@dataclass
class AreaTrust:
    """Trust data for a specific area."""
    area: str
    total_actions: int
    successful_actions: int
    success_rate: float
    avg_quality: float
    trust_score: float
    recommended_autonomy: AutonomyLevel
    last_action: Optional[str]
    days_since_action: Optional[int]
    trend: str  # "improving", "stable", "declining"


@dataclass
class TrustReport:
    """Complete trust report for a project."""
    project: str
    overall_trust: float
    recommended_global_autonomy: AutonomyLevel
    area_trust: Dict[str, AreaTrust]
    total_actions: int
    total_successful: int
    overall_success_rate: float
    trust_history: List[Dict]  # Recent trust score snapshots
    strengths: List[str]  # Areas with high trust
    concerns: List[str]  # Areas with low trust or declining


# ─── Trust Model ──────────────────────────────────────────────────

class TrustModel:
    """
    Manages agent trust and autonomy based on demonstrated reliability.

    Trust scores are calculated from:
    - Success rate (40%): How often actions succeed
    - Quality (30%): How good the outcomes are
    - Recency (20%): More recent actions weighted higher
    - Volume (10%): More data points = more confidence
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.trust_dir = Path(vault_path) / "trust"
        self._outcomes: List[TrustOutcome] = []

    def record_outcome(
        self,
        project: str,
        area: str,
        success: bool,
        quality: float = 0.5,
        details: str = "",
        user_rating: Optional[float] = None,
    ) -> TrustOutcome:
        """
        Record an action outcome to update trust.

        Args:
            project: Project name
            area: Action area (research, implementation, etc.)
            success: Whether the action succeeded
            quality: Quality of the outcome (0.0 to 1.0)
            details: Description of what happened
            user_rating: Optional user-provided rating (0.0 to 1.0)

        Returns:
            TrustOutcome that was recorded
        """
        outcome = TrustOutcome(
            project=project,
            area=area,
            success=success,
            quality=quality,
            timestamp=datetime.now().isoformat(),
            details=details,
            user_rating=user_rating,
        )

        self._write_outcome(outcome)
        return outcome

    def get_trust_score(
        self,
        project: str,
        area: str,
    ) -> float:
        """
        Calculate current trust score for an area.

        Returns 0.0 to 1.0.
        """
        outcomes = self._get_outcomes(project, area)

        if not outcomes:
            return 0.3  # Default moderate-low trust for new areas

        # Success rate
        successes = sum(1 for o in outcomes if o.success)
        success_rate = successes / len(outcomes)

        # Average quality
        avg_quality = sum(o.quality for o in outcomes) / len(outcomes)

        # Recency score (more recent = higher weight)
        now = datetime.now()
        recency_scores = []
        for o in outcomes:
            try:
                age = (now - datetime.fromisoformat(o.timestamp)).days
                recency = math.exp(-0.1 * age)  # Exponential decay
                recency_scores.append(recency)
            except Exception:
                recency_scores.append(0.5)
        avg_recency = sum(recency_scores) / len(recency_scores) if recency_scores else 0.5

        # Volume confidence (more data = more confident)
        volume = min(1.0, len(outcomes) / 20)  # Caps at 20 actions

        # Weighted score
        score = (
            success_rate * WEIGHT_SUCCESS_RATE +
            avg_quality * WEIGHT_QUALITY +
            avg_recency * WEIGHT_RECENCY +
            volume * WEIGHT_VOLUME
        )

        # Apply decay if no recent activity
        last_outcome = max(outcomes, key=lambda o: o.timestamp)
        try:
            days_since = (now - datetime.fromisoformat(last_outcome.timestamp)).days
            decay_periods = days_since // TRUST_DECAY_INTERVAL
            if decay_periods > 0:
                score *= (1 - TRUST_DECAY_RATE) ** decay_periods
        except Exception:
            pass

        # User rating override (strong signal)
        user_ratings = [o.user_rating for o in outcomes if o.user_rating is not None]
        if user_ratings:
            avg_user_rating = sum(user_ratings) / len(user_ratings)
            score = score * 0.7 + avg_user_rating * 0.3

        return max(0.0, min(1.0, score))

    def get_recommended_autonomy(
        self,
        project: str,
        area: str,
    ) -> AutonomyLevel:
        """
        Get recommended autonomy level based on trust score.

        Maps trust score to autonomy level:
        - >= 0.8: AUTONOMOUS
        - >= 0.5: NOTIFY
        - >= 0.2: APPROVE
        - < 0.2: FORBIDDEN
        """
        score = self.get_trust_score(project, area)

        for level in [AutonomyLevel.AUTONOMOUS, AutonomyLevel.NOTIFY,
                      AutonomyLevel.APPROVE, AutonomyLevel.FORBIDDEN]:
            if score >= TRUST_THRESHOLDS[level]:
                return level

        return AutonomyLevel.FORBIDDEN

    def get_area_trust(self, project: str, area: str) -> AreaTrust:
        """Get detailed trust data for an area."""
        outcomes = self._get_outcomes(project, area)
        score = self.get_trust_score(project, area)
        recommended = self.get_recommended_autonomy(project, area)

        successes = sum(1 for o in outcomes if o.success)
        success_rate = successes / max(1, len(outcomes))
        avg_quality = sum(o.quality for o in outcomes) / max(1, len(outcomes))

        # Last action
        last_action = None
        days_since = None
        if outcomes:
            last = max(outcomes, key=lambda o: o.timestamp)
            last_action = last.timestamp
            try:
                days_since = (datetime.now() - datetime.fromisoformat(last.timestamp)).days
            except Exception:
                pass

        # Trend
        trend = self._calculate_trend(outcomes)

        return AreaTrust(
            area=area,
            total_actions=len(outcomes),
            successful_actions=successes,
            success_rate=success_rate,
            avg_quality=avg_quality,
            trust_score=score,
            recommended_autonomy=recommended,
            last_action=last_action,
            days_since_action=days_since,
            trend=trend,
        )

    def get_trust_report(self, project: str) -> TrustReport:
        """Get complete trust report for a project."""
        # Get all areas with outcomes
        areas = self._get_areas(project)

        area_trust = {}
        for area in areas:
            area_trust[area] = self.get_area_trust(project, area)

        # Overall trust (average of areas)
        if area_trust:
            overall_trust = sum(at.trust_score for at in area_trust.values()) / len(area_trust)
        else:
            overall_trust = 0.3

        # Recommended global autonomy
        global_autonomy = AutonomyLevel.FORBIDDEN
        for level in [AutonomyLevel.AUTONOMOUS, AutonomyLevel.NOTIFY,
                      AutonomyLevel.APPROVE, AutonomyLevel.FORBIDDEN]:
            if overall_trust >= TRUST_THRESHOLDS[level]:
                global_autonomy = level
                break

        # Totals
        total_actions = sum(at.total_actions for at in area_trust.values())
        total_successful = sum(at.successful_actions for at in area_trust.values())
        overall_success_rate = total_successful / max(1, total_actions)

        # Strengths and concerns
        strengths = [at.area for at in area_trust.values() if at.trust_score >= 0.7]
        concerns = [
            f"{at.area} (trust: {at.trust_score:.2f}, trend: {at.trend})"
            for at in area_trust.values()
            if at.trust_score < 0.4 or at.trend == "declining"
        ]

        return TrustReport(
            project=project,
            overall_trust=overall_trust,
            recommended_global_autonomy=global_autonomy,
            area_trust=area_trust,
            total_actions=total_actions,
            total_successful=total_successful,
            overall_success_rate=overall_success_rate,
            trust_history=[],  # Would need persistent snapshots
            strengths=strengths,
            concerns=concerns,
        )

    # ─── Internal ─────────────────────────────────────────────────

    def _get_outcomes(self, project: str, area: Optional[str] = None) -> List[TrustOutcome]:
        """Load outcomes for a project/area."""
        outcomes = []
        outcomes_file = self.trust_dir / f"{project}_outcomes.jsonl"

        if not outcomes_file.exists():
            return outcomes

        try:
            for line in outcomes_file.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                data = json.loads(line)
                if area and data.get("area") != area:
                    continue
                outcomes.append(TrustOutcome(
                    project=data.get("project", project),
                    area=data.get("area", ""),
                    success=data.get("success", False),
                    quality=data.get("quality", 0.5),
                    timestamp=data.get("timestamp", ""),
                    details=data.get("details", ""),
                    user_rating=data.get("user_rating"),
                ))
        except Exception:
            pass

        return outcomes

    def _get_areas(self, project: str) -> List[str]:
        """Get all areas with outcomes for a project."""
        areas = set()
        outcomes = self._get_outcomes(project)
        for o in outcomes:
            areas.add(o.area)
        return list(areas)

    def _calculate_trend(self, outcomes: List[TrustOutcome]) -> str:
        """Calculate trust trend from recent outcomes."""
        if len(outcomes) < 4:
            return "stable"

        # Compare recent half vs older half
        sorted_outcomes = sorted(outcomes, key=lambda o: o.timestamp)
        mid = len(sorted_outcomes) // 2
        older = sorted_outcomes[:mid]
        recent = sorted_outcomes[mid:]

        older_success = sum(1 for o in older if o.success) / len(older)
        recent_success = sum(1 for o in recent if o.success) / len(recent)

        diff = recent_success - older_success
        if diff > 0.15:
            return "improving"
        elif diff < -0.15:
            return "declining"
        return "stable"

    def _write_outcome(self, outcome: TrustOutcome) -> None:
        """Persist an outcome."""
        self.trust_dir.mkdir(parents=True, exist_ok=True)
        outcomes_file = self.trust_dir / f"{outcome.project}_outcomes.jsonl"

        entry = {
            "project": outcome.project,
            "area": outcome.area,
            "success": outcome.success,
            "quality": outcome.quality,
            "timestamp": outcome.timestamp,
            "details": outcome.details,
            "user_rating": outcome.user_rating,
        }

        with open(outcomes_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    trust = TrustModel(vault)

    if cmd == "score":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        area = sys.argv[3] if len(sys.argv) > 3 else None
        if not project or not area:
            print("Usage: trust.py score <project> <area>")
            sys.exit(1)
        score = trust.get_trust_score(project, area)
        autonomy = trust.get_recommended_autonomy(project, area)
        print(f"Trust for {project}/{area}:")
        print(f"  Score: {score:.2f}")
        print(f"  Recommended autonomy: {autonomy.value}")

    elif cmd == "report":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: trust.py report <project>")
            sys.exit(1)
        report = trust.get_trust_report(project)
        print(f"Trust Report: {report.project}")
        print(f"  Overall trust: {report.overall_trust:.2f}")
        print(f"  Recommended autonomy: {report.recommended_global_autonomy.value}")
        print(f"  Total actions: {report.total_actions}")
        print(f"  Success rate: {report.overall_success_rate:.0%}")
        if report.area_trust:
            print(f"  By area:")
            for area, at in report.area_trust.items():
                print(f"    {area}: {at.trust_score:.2f} ({at.total_actions} actions, {at.trend})")
        if report.strengths:
            print(f"  Strengths: {', '.join(report.strengths)}")
        if report.concerns:
            print(f"  Concerns: {', '.join(report.concerns)}")

    elif cmd == "record":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        area = sys.argv[3] if len(sys.argv) > 3 else None
        success_str = sys.argv[4] if len(sys.argv) > 4 else "true"
        quality = float(sys.argv[5]) if len(sys.argv) > 5 else 0.7
        if not project or not area:
            print("Usage: trust.py record <project> <area> <true|false> [quality]")
            sys.exit(1)
        success = success_str.lower() in ("true", "1", "yes")
        outcome = trust.record_outcome(project, area, success=success, quality=quality)
        print(f"Recorded: {project}/{area} success={success} quality={quality}")

    else:
        print("Commands: score <project> <area>, report <project>, record <project> <area> <true|false> [quality]")

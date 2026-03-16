#!/usr/bin/env python3
"""
Relevance Scoring Engine for Mnemosyne Knowledge Vault.

Scores vault files based on:
  - Recency (30%): How recently the file was updated
      - Layer-aware halflife: L1=14d, L2=30d, L3=90d, L4=180d
      - Floor of 0.1 — research files never fully age out
  - Topic match (50%): How well the file matches the current topic
      - Basic stemming: electrode≈electrodes, test≈testing
      - Searches id, tags, filename, summary/body (not type field)
  - User priority (20%): Explicit priority signals (tags, status, project)
  - Layer bonus: Applied to all files regardless of project match
      - L1=1.1, L2=1.05, L3=1.0, L4=0.95, cross=1.0

Formula: score = min(1.0, (recency×0.3 + topic×0.5 + priority×0.2) × layer_bonus)

Usage:
    from relevance import RelevanceScorer

    scorer = RelevanceScorer()
    score = scorer.score(metadata, topic="gold electrodes", project="eeg")
    print(f"Total: {score.total_score}, Breakdown: {score.breakdown}")
"""

import os
import re
import math
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from vault_utils import read_vault_file


# ─── Constants ────────────────────────────────────────────────────

# Weights for scoring formula
WEIGHT_RECENCY = 0.3
WEIGHT_TOPIC = 0.5
WEIGHT_PRIORITY = 0.2

# Recency decay: layer-aware halflife (days)
RECENCY_HALFLIFE_BY_LAYER = {
    "L1": 14,     # Decisions change fast
    "L2": 30,     # Components evolve
    "L3": 90,     # Rules are stable
    "L4": 180,    # Research persists
    "cross": 60,
}

# Minimum recency floor — never fully zero out a file
RECENCY_FLOOR = 0.1

# Status priority multipliers
STATUS_PRIORITY = {
    "active": 1.0,
    "reference": 0.6,
    "archived": 0.2,
}

# Confidence multipliers
CONFIDENCE_PRIORITY = {
    "high": 1.0,
    "moderate": 0.7,
    "low": 0.4,
}

# Layer relevance bonus — applied to all files (not gated on project match)
LAYER_BONUS = {
    "L1": 1.1,
    "L2": 1.05,
    "L3": 1.0,
    "L4": 0.95,
    "cross": 1.0,
}


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class ScoreBreakdown:
    """Detailed breakdown of relevance scoring."""
    recency_raw: float = 0.0
    recency_weighted: float = 0.0
    topic_raw: float = 0.0
    topic_weighted: float = 0.0
    priority_raw: float = 0.0
    priority_weighted: float = 0.0
    layer_bonus: float = 1.0
    matched_terms: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


@dataclass
class ScoredFile:
    """A file with its relevance score."""
    path: str
    filename: str
    metadata: Dict
    total_score: float
    breakdown: ScoreBreakdown

    def explain(self) -> str:
        """Human-readable explanation of the score."""
        lines = [
            f"File: {self.filename}",
            f"Total Score: {self.total_score:.3f}",
            f"  Recency:   {self.breakdown.recency_raw:.2f} × {WEIGHT_RECENCY} = {self.breakdown.recency_weighted:.3f}",
            f"  Topic:     {self.breakdown.topic_raw:.2f} × {WEIGHT_TOPIC} = {self.breakdown.topic_weighted:.3f}",
            f"  Priority:  {self.breakdown.priority_raw:.2f} × {WEIGHT_PRIORITY} = {self.breakdown.priority_weighted:.3f}",
            f"  Layer Bonus: ×{self.breakdown.layer_bonus:.1f}",
        ]
        if self.breakdown.matched_terms:
            lines.append(f"  Matched: {', '.join(self.breakdown.matched_terms)}")
        if self.breakdown.reasons:
            lines.append(f"  Reasons: {'; '.join(self.breakdown.reasons)}")
        return "\n".join(lines)


# ─── Topic Extraction ─────────────────────────────────────────────

# Common stop words to ignore in topic matching
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "up", "about", "into", "through", "during", "before", "after",
    "above", "below", "between", "out", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "because", "but",
    "and", "or", "if", "while", "what", "which", "who", "whom",
    "this", "that", "these", "those", "i", "me", "my", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their",
}


def extract_topic_terms(topic: str) -> Set[str]:
    """Extract meaningful terms from a topic string with basic stemming."""
    # Lowercase and split on non-alphanumeric
    words = re.findall(r'[a-z0-9]+', topic.lower())
    # Remove stop words and very short words (keep 2+ for AI, IoT, EEG)
    terms = {w for w in words if w not in STOP_WORDS and len(w) >= 2}

    # Add stemmed variants so "electrode" matches "electrodes"
    stemmed = set()
    for w in terms:
        stemmed.add(w)
        if w.endswith("es") and len(w) > 3:
            stemmed.add(w[:-2])   # electrodes -> electrode
        elif w.endswith("s") and len(w) > 2:
            stemmed.add(w[:-1])   # sensors -> sensor
        if w.endswith("ing") and len(w) > 4:
            stemmed.add(w[:-3])   # testing -> test
        if w.endswith("ed") and len(w) > 3:
            stemmed.add(w[:-2])   # oxidized -> oxidiz (partial, better than nothing)
        if w.endswith("tion") and len(w) > 4:
            stemmed.add(w[:-4] + "t")  # oxidation -> oxidat (partial)

    return stemmed


# ─── Relevance Scorer ─────────────────────────────────────────────

class RelevanceScorer:
    """
    Scores vault files for relevance to a given topic/context.

    Uses the formula: score = recency×0.3 + topic_match×0.5 + priority×0.2
    """

    def __init__(
        self,
        weight_recency: float = WEIGHT_RECENCY,
        weight_topic: float = WEIGHT_TOPIC,
        weight_priority: float = WEIGHT_PRIORITY,
    ):
        self.weight_recency = weight_recency
        self.weight_topic = weight_topic
        self.weight_priority = weight_priority

    def score(
        self,
        metadata: Dict,
        topic: Optional[str] = None,
        project: Optional[str] = None,
        vault_path: Optional[str] = None,
    ) -> ScoredFile:
        """
        Score a single file's relevance.

        Args:
            metadata: File metadata dict (from scan_vault or read_vault_file)
            topic: Current topic/query for matching
            project: Current project context
            vault_path: Vault path (for loading file content if needed)

        Returns:
            ScoredFile with total score and breakdown
        """
        breakdown = ScoreBreakdown()
        path = metadata.get("_path", "")
        filename = metadata.get("_filename", metadata.get("id", "unknown"))

        # ─── Recency Score ────────────────────────────────────────
        breakdown.recency_raw = self._score_recency(metadata)
        breakdown.recency_weighted = breakdown.recency_raw * self.weight_recency

        # ─── Topic Match Score ────────────────────────────────────
        topic_result = self._score_topic(metadata, topic, vault_path)
        breakdown.topic_raw = topic_result["score"]
        breakdown.topic_weighted = breakdown.topic_raw * self.weight_topic
        breakdown.matched_terms = topic_result["matched"]

        # ─── Priority Score ───────────────────────────────────────
        priority_result = self._score_priority(metadata, project)
        breakdown.priority_raw = priority_result["score"]
        breakdown.priority_weighted = breakdown.priority_raw * self.weight_priority
        breakdown.reasons = priority_result["reasons"]

        # ─── Layer Bonus ──────────────────────────────────────────
        # Always applied (not gated on project match)
        layer = metadata.get("layer", "cross")
        breakdown.layer_bonus = LAYER_BONUS.get(layer, 1.0)

        # ─── Total Score ──────────────────────────────────────────
        base_score = (
            breakdown.recency_weighted +
            breakdown.topic_weighted +
            breakdown.priority_weighted
        )
        total_score = min(1.0, base_score * breakdown.layer_bonus)

        return ScoredFile(
            path=path,
            filename=filename,
            metadata=metadata,
            total_score=total_score,
            breakdown=breakdown,
        )

    def score_batch(
        self,
        metadata_list: List[Dict],
        topic: Optional[str] = None,
        project: Optional[str] = None,
        vault_path: Optional[str] = None,
    ) -> List[ScoredFile]:
        """Score a batch of files and return sorted by relevance."""
        scored = [
            self.score(m, topic, project, vault_path)
            for m in metadata_list
        ]
        scored.sort(key=lambda s: s.total_score, reverse=True)
        return scored

    # ─── Scoring Components ───────────────────────────────────────

    def _score_recency(self, metadata: Dict) -> float:
        """Score based on how recently the file was updated.
        
        Uses layer-aware halflife: research files persist longer than decisions.
        Never returns zero — applies RECENCY_FLOOR minimum.
        """
        updated_str = metadata.get("updated", metadata.get("created", ""))
        if not updated_str:
            return 0.5  # Default for unknown date

        try:
            updated = datetime.strptime(str(updated_str), "%Y-%m-%d")
            now = datetime.now()
            days_old = (now - updated).days

            # Layer-aware halflife
            layer = metadata.get("layer", "cross")
            halflife = RECENCY_HALFLIFE_BY_LAYER.get(layer, 60)

            # Exponential decay with halflife, floor never goes to zero
            score = math.exp(-0.693 * days_old / halflife)
            return max(RECENCY_FLOOR, min(1.0, score))

        except (ValueError, TypeError):
            return 0.5

    def _score_topic(
        self,
        metadata: Dict,
        topic: Optional[str],
        vault_path: Optional[str],
    ) -> Dict:
        """Score based on topic matching."""
        if not topic:
            return {"score": 0.5, "matched": []}  # Neutral if no topic

        topic_terms = extract_topic_terms(topic)
        if not topic_terms:
            return {"score": 0.5, "matched": []}

        # Build searchable text from metadata
        # NOTE: "type" excluded — too generic (pollutes with "research", "component", etc.)
        searchable = " ".join([
            str(metadata.get("id", "")),
            " ".join(metadata.get("tags", [])),
            metadata.get("_filename", ""),
        ]).lower()

        # If we have a vault path, also check file content (first 500 chars)
        path = metadata.get("_path", "")
        if vault_path and path and os.path.exists(path):
            try:
                _, body = read_vault_file(path)
                # Add summary and first paragraph
                summary_match = re.search(r'## Summary\s*\n(.*?)(?=\n## )', body, re.DOTALL)
                if summary_match:
                    searchable += " " + summary_match.group(1).lower()[:300]
                else:
                    searchable += " " + body[:500].lower()
            except Exception:
                pass

        # Count term matches
        matched = []
        match_count = 0
        for term in topic_terms:
            if term in searchable:
                matched.append(term)
                # Count occurrences for weighting
                match_count += searchable.count(term)

        # Score: ratio of matched terms, boosted by multiple occurrences
        if not topic_terms:
            return {"score": 0.5, "matched": []}

        term_ratio = len(matched) / len(topic_terms)
        occurrence_boost = min(1.0, match_count / (len(topic_terms) * 2))
        score = (term_ratio * 0.7) + (occurrence_boost * 0.3)

        return {"score": min(1.0, score), "matched": matched}

    def _score_priority(self, metadata: Dict, project: Optional[str]) -> Dict:
        """Score based on priority signals (status, confidence, project)."""
        reasons = []
        score = 0.5  # Base score
        factors = 0

        # Status factor
        status = metadata.get("status", "active")
        status_score = STATUS_PRIORITY.get(status, 0.5)
        score += status_score
        factors += 1
        if status == "active":
            reasons.append("active status")

        # Confidence factor
        confidence = metadata.get("confidence", "moderate")
        conf_score = CONFIDENCE_PRIORITY.get(confidence, 0.7)
        score += conf_score
        factors += 1
        if confidence == "high":
            reasons.append("high confidence")

        # Project match bonus
        if project and metadata.get("project") == project:
            score += 1.0
            factors += 1
            reasons.append(f"project match ({project})")

        # Tag-based priority
        tags = metadata.get("tags", [])
        priority_tags = {"important", "critical", "active", "core"}
        if any(t in priority_tags for t in tags):
            score += 0.8
            factors += 1
            reasons.append("priority tag")

        # Average the factors
        if factors > 0:
            score = score / (factors + 1)  # +1 to keep below 1.0

        return {"score": min(1.0, score), "reasons": reasons}


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    scorer = RelevanceScorer()

    if cmd == "score":
        topic = sys.argv[2] if len(sys.argv) > 2 else None
        project = sys.argv[3] if len(sys.argv) > 3 else None

        from vault_utils import scan_vault
        files = scan_vault(vault)
        scored = scorer.score_batch(files, topic=topic, project=project, vault_path=vault)

        print(f"Top files for topic='{topic}', project='{project}':")
        print()
        for s in scored[:10]:
            print(f"  {s.total_score:.3f}  {s.filename:30}  [{s.metadata.get('layer', '??')}]")
            if s.breakdown.matched_terms:
                print(f"         matched: {', '.join(s.breakdown.matched_terms)}")

    elif cmd == "explain":
        filename = sys.argv[2] if len(sys.argv) > 2 else None
        topic = sys.argv[3] if len(sys.argv) > 3 else None

        if not filename:
            print("Usage: relevance.py explain <filename> [topic]")
            sys.exit(1)

        from vault_utils import scan_vault
        files = scan_vault(vault)
        for f in files:
            if f.get("_filename") == filename or f.get("id") == filename:
                scored = scorer.score(f, topic=topic, vault_path=vault)
                print(scored.explain())
                break
        else:
            print(f"File '{filename}' not found")

    else:
        print("Commands: score [topic] [project], explain <filename> [topic]")

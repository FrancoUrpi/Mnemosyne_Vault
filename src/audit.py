#!/usr/bin/env python3
"""
Decision Audit Trail Logger for Mnemosyne Knowledge Vault.

Records every significant agent decision with full reasoning chain:
  - Decision context and alternatives considered
  - L4→L3→L2→L1 reasoning trace
  - Confidence level and assumptions
  - Reversal conditions
  - Outcome tracking

Usage:
    from audit import AuditLogger

    logger = AuditLogger(vault_path="~/.hermes/memory")
    
    # Log a decision
    entry = logger.log_decision(
        project="eeg",
        decision="Use gold electrodes",
        reasoning_chain=[...],
        alternatives=[...],
        confidence="high",
    )
    
    # Query decisions
    decisions = logger.get_decisions(project="eeg", limit=5)
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from vault_utils import read_vault_file, write_frontmatter, parse_frontmatter


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class ReasoningStep:
    """A single step in the reasoning chain."""
    layer: str
    file_id: str
    finding: str  # What this source tells us
    confidence: str = "moderate"


@dataclass
class Alternative:
    """An alternative that was considered."""
    description: str
    reason_rejected: str
    trade_off: str = ""


@dataclass
class Assumption:
    """An assumption underlying the decision."""
    statement: str
    risk_if_wrong: str = "Decision may need revision"


@dataclass
class ReversalCondition:
    """Condition under which to revisit the decision."""
    condition: str
    action: str = "Reconsider alternatives"


@dataclass
class DecisionEntry:
    """A complete decision audit entry."""
    id: str
    project: str
    decision: str
    timestamp: str
    reasoning_chain: List[ReasoningStep]
    alternatives: List[Alternative]
    confidence: str
    assumptions: List[Assumption]
    reversal_conditions: List[ReversalCondition]
    status: str  # "active", "reversed", "superseded"
    outcome: Optional[str] = None
    reversed_by: Optional[str] = None
    reversed_date: Optional[str] = None

    def to_markdown(self) -> str:
        """Convert to markdown for vault file."""
        lines = []

        lines.append(f"# Decision: {self.decision}")
        lines.append("")
        lines.append(f"**ID:** {self.id}")
        lines.append(f"**Project:** {self.project}")
        lines.append(f"**Date:** {self.timestamp}")
        lines.append(f"**Confidence:** {self.confidence}")
        lines.append(f"**Status:** {self.status}")
        lines.append("")

        # Decision
        lines.append("## Decision")
        lines.append(self.decision)
        lines.append("")

        # Reasoning Chain
        lines.append("## Reasoning Chain")
        for i, step in enumerate(self.reasoning_chain, 1):
            lines.append(f"{i}. **{step.layer}**: [[{step.file_id}]] — {step.finding} "
                        f"(_{step.confidence}_)")
        lines.append("")

        # Alternatives
        if self.alternatives:
            lines.append("## Alternatives Considered")
            for alt in self.alternatives:
                lines.append(f"- **{alt.description}**: Rejected — {alt.reason_rejected}")
                if alt.trade_off:
                    lines.append(f"  - Trade-off: {alt.trade_off}")
            lines.append("")

        # Confidence
        lines.append("## Confidence")
        lines.append(f"**Level:** {self.confidence}")
        lines.append("")

        # Assumptions
        if self.assumptions:
            lines.append("## Assumptions")
            for a in self.assumptions:
                lines.append(f"- {a.statement}")
                if a.risk_if_wrong:
                    lines.append(f"  - Risk: {a.risk_if_wrong}")
            lines.append("")

        # Reversal Conditions
        if self.reversal_conditions:
            lines.append("## Reversal Conditions")
            for r in self.reversal_conditions:
                lines.append(f"- If {r.condition} → {r.action}")
            lines.append("")

        # Outcome (if recorded)
        if self.outcome:
            lines.append("## Outcome")
            lines.append(self.outcome)
            lines.append("")

        # Reversal info
        if self.status == "reversed" and self.reversed_by:
            lines.append(f"## Reversed By")
            lines.append(f"[[{self.reversed_by}]] on {self.reversed_date}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class AuditStats:
    """Statistics about the audit trail."""
    total_decisions: int
    active_decisions: int
    reversed_decisions: int
    by_project: Dict[str, int]
    by_confidence: Dict[str, int]
    avg_reasoning_steps: float


# ─── Audit Logger ─────────────────────────────────────────────────

class AuditLogger:
    """
    Decision audit trail logger.

    Creates and manages decision records in the vault's decisions/ directory.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.decisions_dir = Path(self.vault_path) / "decisions"

    def log_decision(
        self,
        project: str,
        decision: str,
        reasoning_chain: List[Dict],
        alternatives: Optional[List[Dict]] = None,
        confidence: str = "moderate",
        assumptions: Optional[List[Dict]] = None,
        reversal_conditions: Optional[List[Dict]] = None,
    ) -> DecisionEntry:
        """
        Log a new decision to the audit trail.

        Args:
            project: Project name
            decision: Decision text
            reasoning_chain: List of {layer, file_id, finding, confidence}
            alternatives: List of {description, reason_rejected, trade_off}
            confidence: Overall confidence (high/moderate/low)
            assumptions: List of {statement, risk_if_wrong}
            reversal_conditions: List of {condition, action}

        Returns:
            DecisionEntry that was created
        """
        # Generate ID
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Count existing decisions today for unique ID
        existing = list(self.decisions_dir.glob(f"{today}-*.md"))
        seq = len(existing) + 1
        decision_id = f"{today}-{project}-{seq:03d}"

        # Build entry
        chain = [
            ReasoningStep(
                layer=s.get("layer", "L1"),
                file_id=s.get("file_id", ""),
                finding=s.get("finding", ""),
                confidence=s.get("confidence", "moderate"),
            )
            for s in (reasoning_chain or [])
        ]

        alts = [
            Alternative(
                description=a.get("description", ""),
                reason_rejected=a.get("reason_rejected", ""),
                trade_off=a.get("trade_off", ""),
            )
            for a in (alternatives or [])
        ]

        asms = [
            Assumption(
                statement=a.get("statement", ""),
                risk_if_wrong=a.get("risk_if_wrong", "Decision may need revision"),
            )
            for a in (assumptions or [])
        ]

        revs = [
            ReversalCondition(
                condition=r.get("condition", ""),
                action=r.get("action", "Reconsider alternatives"),
            )
            for r in (reversal_conditions or [])
        ]

        entry = DecisionEntry(
            id=decision_id,
            project=project,
            decision=decision,
            timestamp=timestamp,
            reasoning_chain=chain,
            alternatives=alts,
            confidence=confidence,
            assumptions=asms,
            reversal_conditions=revs,
            status="active",
        )

        # Write to vault
        self._write_decision(entry)

        return entry

    def get_decisions(
        self,
        project: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[str] = None,
        limit: int = 20,
    ) -> List[DecisionEntry]:
        """
        Query decisions from the audit trail.

        Args:
            project: Filter by project
            status: Filter by status (active/reversed/superseded)
            confidence: Filter by confidence level
            limit: Max results

        Returns:
            List of DecisionEntry sorted by date (newest first)
        """
        entries = []

        if not self.decisions_dir.exists():
            return entries

        for md_file in sorted(self.decisions_dir.glob("*.md"), reverse=True):
            if len(entries) >= limit:
                break

            try:
                meta, body = read_vault_file(str(md_file))
            except Exception:
                continue

            # Parse entry from file
            entry = self._parse_decision_file(md_file, meta, body)
            if not entry:
                continue

            # Apply filters
            if project and entry.project != project:
                continue
            if status and entry.status != status:
                continue
            if confidence and entry.confidence != confidence:
                continue

            entries.append(entry)

        return entries

    def get_decision(self, decision_id: str) -> Optional[DecisionEntry]:
        """Get a specific decision by ID."""
        if not self.decisions_dir.exists():
            return None

        for md_file in self.decisions_dir.glob("*.md"):
            try:
                meta, body = read_vault_file(str(md_file))
                if meta.get("id") == decision_id or md_file.stem == decision_id:
                    return self._parse_decision_file(md_file, meta, body)
            except Exception:
                continue

        return None

    def reverse_decision(
        self,
        decision_id: str,
        reversed_by: str,
        reason: str,
    ) -> bool:
        """
        Mark a decision as reversed.

        Args:
            decision_id: ID of the decision to reverse
            reversed_by: ID of the new decision that supersedes this one
            reason: Why the decision was reversed

        Returns:
            True if successful
        """
        entry = self.get_decision(decision_id)
        if not entry:
            return False

        entry.status = "reversed"
        entry.reversed_by = reversed_by
        entry.reversed_date = datetime.now().strftime("%Y-%m-%d")
        entry.outcome = f"Reversed: {reason}"

        self._write_decision(entry)
        return True

    def record_outcome(
        self,
        decision_id: str,
        outcome: str,
    ) -> bool:
        """Record the outcome of a decision."""
        entry = self.get_decision(decision_id)
        if not entry:
            return False

        entry.outcome = outcome
        self._write_decision(entry)
        return True

    def get_reasoning_for_decision(
        self,
        decision_id: str,
    ) -> List[Dict]:
        """
        Get the full reasoning chain for a decision.

        Returns list of steps with layer, file_id, finding, confidence.
        """
        entry = self.get_decision(decision_id)
        if not entry:
            return []

        return [
            {
                "layer": step.layer,
                "file_id": step.file_id,
                "finding": step.finding,
                "confidence": step.confidence,
            }
            for step in entry.reasoning_chain
        ]

    def get_stats(
        self,
        project: Optional[str] = None,
    ) -> AuditStats:
        """Get audit trail statistics."""
        decisions = self.get_decisions(project=project, limit=1000)

        by_project: Dict[str, int] = {}
        by_confidence: Dict[str, int] = {}
        total_steps = 0

        for d in decisions:
            by_project[d.project] = by_project.get(d.project, 0) + 1
            by_confidence[d.confidence] = by_confidence.get(d.confidence, 0) + 1
            total_steps += len(d.reasoning_chain)

        active = sum(1 for d in decisions if d.status == "active")
        reversed_count = sum(1 for d in decisions if d.status == "reversed")

        return AuditStats(
            total_decisions=len(decisions),
            active_decisions=active,
            reversed_decisions=reversed_count,
            by_project=by_project,
            by_confidence=by_confidence,
            avg_reasoning_steps=total_steps / max(1, len(decisions)),
        )

    def search_decisions(
        self,
        query: str,
        project: Optional[str] = None,
    ) -> List[DecisionEntry]:
        """Search decisions by text content."""
        results = []
        decisions = self.get_decisions(project=project, limit=1000)
        query_lower = query.lower()

        for d in decisions:
            if (query_lower in d.decision.lower() or
                any(query_lower in s.finding.lower() for s in d.reasoning_chain)):
                results.append(d)

        return results

    # ─── File I/O ─────────────────────────────────────────────────

    def _write_decision(self, entry: DecisionEntry) -> None:
        """Write a decision entry to a vault file."""
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

        # Filename: date-project-seq.md
        filename = f"{entry.id}.md"
        filepath = self.decisions_dir / filename

        # Build frontmatter
        meta = {
            "id": entry.id,
            "type": "decision",
            "layer": "L1",
            "project": entry.project,
            "created": entry.timestamp[:10],
            "updated": datetime.now().strftime("%Y-%m-%d"),
            "confidence": entry.confidence,
            "status": entry.status,
        }

        body = entry.to_markdown()
        content = write_frontmatter(meta, body)
        filepath.write_text(content, encoding="utf-8")

    def _parse_decision_file(
        self,
        path: Path,
        meta: Dict,
        body: str,
    ) -> Optional[DecisionEntry]:
        """Parse a decision file back into a DecisionEntry."""
        decision_id = meta.get("id", path.stem)
        project = meta.get("project", "unknown")
        confidence = meta.get("confidence", "moderate")
        status = meta.get("status", "active")
        created = meta.get("created", "")

        # Extract decision text
        decision_text = ""
        dec_match = re.search(r'## Decision\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if dec_match:
            decision_text = dec_match.group(1).strip()

        # Extract reasoning chain
        chain = []
        chain_section = re.search(
            r'## Reasoning Chain\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
        )
        if chain_section:
            steps = re.findall(
                r'\d+\.\s+\*\*(\w+)\*\*:\s+\[\[(\w+)\]\]\s*[—-]\s*(.+?)\s*\(_(\w+)_\)',
                chain_section.group(1)
            )
            for layer, file_id, finding, conf in steps:
                chain.append(ReasoningStep(
                    layer=layer,
                    file_id=file_id,
                    finding=finding.strip(),
                    confidence=conf,
                ))

        # Extract alternatives
        alternatives = []
        alt_section = re.search(
            r'## Alternatives Considered\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
        )
        if alt_section:
            alts = re.findall(
                r'-\s+\*\*(.+?)\*\*:\s+Rejected\s*[—-]\s*(.+?)(?:\n|$)',
                alt_section.group(1)
            )
            for desc, reason in alts:
                alternatives.append(Alternative(
                    description=desc.strip(),
                    reason_rejected=reason.strip(),
                ))

        # Extract assumptions
        assumptions = []
        asm_section = re.search(
            r'## Assumptions\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
        )
        if asm_section:
            asms = re.findall(r'-\s+(.+?)(?:\n|$)', asm_section.group(1))
            for asm in asms:
                assumptions.append(Assumption(statement=asm.strip()))

        # Extract reversal conditions
        reversals = []
        rev_section = re.search(
            r'## Reversal Conditions\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
        )
        if rev_section:
            revs = re.findall(
                r'-\s+(?:If\s+)?(.+?)\s*(?:→|->)\s*(.+?)(?:\n|$)',
                rev_section.group(1)
            )
            for cond, action in revs:
                reversals.append(ReversalCondition(
                    condition=cond.strip(),
                    action=action.strip(),
                ))

        # Extract outcome
        outcome = None
        out_match = re.search(r'## Outcome\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if out_match:
            outcome = out_match.group(1).strip()

        return DecisionEntry(
            id=decision_id,
            project=project,
            decision=decision_text,
            timestamp=created,
            reasoning_chain=chain,
            alternatives=alternatives,
            confidence=confidence,
            assumptions=assumptions,
            reversal_conditions=reversals,
            status=status,
            outcome=outcome,
        )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    logger = AuditLogger(vault)

    if cmd == "list":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        decisions = logger.get_decisions(project=project)
        print(f"Decisions{f' for {project}' if project else ''}: {len(decisions)}")
        for d in decisions[:10]:
            marker = "*" if d.status == "active" else "x"
            print(f"  [{marker}] {d.id}: {d.decision[:60]} ({d.confidence})")

    elif cmd == "show":
        decision_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not decision_id:
            print("Usage: audit.py show <decision_id>")
            sys.exit(1)
        entry = logger.get_decision(decision_id)
        if entry:
            print(f"Decision: {entry.decision}")
            print(f"Project: {entry.project}, Status: {entry.status}")
            print(f"Confidence: {entry.confidence}")
            print(f"Reasoning chain ({len(entry.reasoning_chain)} steps):")
            for step in entry.reasoning_chain:
                print(f"  [{step.layer}] {step.file_id}: {step.finding[:60]}")
        else:
            print(f"Decision '{decision_id}' not found")

    elif cmd == "stats":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        stats = logger.get_stats(project=project)
        print(f"Audit Statistics:")
        print(f"  Total: {stats.total_decisions}")
        print(f"  Active: {stats.active_decisions}")
        print(f"  Reversed: {stats.reversed_decisions}")
        print(f"  Avg reasoning steps: {stats.avg_reasoning_steps:.1f}")
        if stats.by_confidence:
            print(f"  By confidence: {stats.by_confidence}")

    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("Usage: audit.py search <query>")
            sys.exit(1)
        results = logger.search_decisions(query)
        print(f"Found {len(results)} decisions matching '{query}':")
        for d in results[:10]:
            print(f"  {d.id}: {d.decision[:60]}")

    else:
        print("Commands: list [project], show <id>, stats [project], search <query>")

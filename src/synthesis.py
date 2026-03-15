#!/usr/bin/env python3
"""
Synthesis Engine for Mnemosyne Knowledge Vault.

Generates L4→L3→L2→L1 summaries by aggregating lower-layer content:
  - Collect research findings (L4)
  - Derive rules/constraints (L3)
  - Update component specs (L2)
  - Produce project decisions (L1)

The synthesis pipeline creates or updates _synthesis.md files
that provide a condensed view of all lower-layer knowledge.

Usage:
    from synthesis import SynthesisEngine

    engine = SynthesisEngine(vault_path="~/.hermes/memory")
    
    # Generate full synthesis for a project
    result = engine.synthesize_project("eeg")
    
    # Generate layer-specific synthesis
    l3_summary = engine.synthesize_layer("eeg", "L3")
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from vault_utils import (
    read_vault_file, write_frontmatter, parse_frontmatter,
    extract_links, scan_vault, find_by_layer, find_by_project
)
from on_demand import OnDemandRetriever
from link_navigator import LinkNavigator


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class LayerSummary:
    """Summary of a single layer's content."""
    layer: str
    file_count: int
    key_points: List[str]
    decisions: List[str]
    constraints: List[str]
    open_questions: List[str]
    files: List[Dict]  # file_id, type, summary


@dataclass
class SynthesisResult:
    """Result of a synthesis operation."""
    project: str
    timestamp: datetime
    layer_summaries: Dict[str, LayerSummary]
    key_decisions: List[str]
    active_rules: List[str]
    component_map: Dict[str, List[str]]  # component -> [dependencies]
    open_questions: List[str]
    confidence: str
    synthesis_text: str
    files_updated: List[str]


@dataclass
class ConfidenceChain:
    """Tracks confidence inheritance through layers."""
    source_file: str
    source_layer: str
    source_confidence: str
    inherited_confidence: str
    reason: str


# ─── Confidence Levels ────────────────────────────────────────────

CONFIDENCE_ORDER = {"low": 0, "moderate": 1, "high": 2}
CONFIDENCE_REVERSE = {0: "low", 1: "moderate", 2: "high"}


def min_confidence(confidences: List[str]) -> str:
    """Get the minimum confidence from a list (L1 inherits lowest)."""
    if not confidences:
        return "moderate"
    min_val = min(CONFIDENCE_ORDER.get(c, 1) for c in confidences)
    return CONFIDENCE_REVERSE[min_val]


# ─── Synthesis Engine ─────────────────────────────────────────────

class SynthesisEngine:
    """
    Generates synthesized summaries from lower layers up.

    Pipeline:
    1. Collect all files at each layer
    2. Extract key points from each file
    3. Derive higher-layer summaries from lower-layer content
    4. Track confidence inheritance
    5. Generate/update _synthesis.md
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.retriever = OnDemandRetriever(vault_path)
        self.navigator = LinkNavigator(vault_path)

    def synthesize_project(self, project: str) -> SynthesisResult:
        """
        Generate full synthesis for a project (L4→L3→L2→L1).

        Creates/updates _synthesis.md in the project directory.
        """
        layer_summaries = {}

        # Collect from each layer bottom-up
        for layer in ["L4", "L3", "L2", "L1"]:
            summary = self._synthesize_layer(project, layer, layer_summaries)
            layer_summaries[layer] = summary

        # Aggregate results
        all_decisions = []
        all_rules = []
        all_questions = []
        component_map = {}

        for layer, summary in layer_summaries.items():
            all_decisions.extend(summary.decisions)
            all_rules.extend(summary.constraints)
            all_questions.extend(summary.open_questions)

            # Build component map from L2
            if layer == "L2":
                for f in summary.files:
                    deps = self._get_file_dependencies(f.get("file_id", ""), project)
                    component_map[f.get("file_id", "")] = deps

        # Determine overall confidence
        all_confidences = []
        for layer, summary in layer_summaries.items():
            for f in summary.files:
                all_confidences.append(f.get("confidence", "moderate"))
        overall_confidence = min_confidence(all_confidences)

        # Generate synthesis text
        synthesis_text = self._generate_synthesis_text(
            project, layer_summaries, all_decisions, all_rules,
            component_map, all_questions, overall_confidence
        )

        # Write to _synthesis.md
        updated_files = self._write_synthesis_file(
            project, synthesis_text, overall_confidence
        )

        return SynthesisResult(
            project=project,
            timestamp=datetime.now(),
            layer_summaries=layer_summaries,
            key_decisions=all_decisions,
            active_rules=all_rules,
            component_map=component_map,
            open_questions=all_questions,
            confidence=overall_confidence,
            synthesis_text=synthesis_text,
            files_updated=updated_files,
        )

    def synthesize_layer(
        self,
        project: str,
        target_layer: str,
    ) -> LayerSummary:
        """Generate summary for a specific layer."""
        return self._synthesize_layer(project, target_layer, {})

    def get_confidence_chain(
        self,
        file_id: str,
        project: str,
    ) -> List[ConfidenceChain]:
        """
        Trace confidence inheritance from L4 up to L1 for a file.

        L1 decisions inherit the LOWEST confidence in the chain.
        """
        chain = []
        current_id = file_id

        for _ in range(10):  # Max 10 hops
            f = self.retriever.get(current_id, reason="confidence_trace")
            if not f:
                break

            conf = f.frontmatter.get("confidence", "moderate")
            layer = f.layer

            chain.append(ConfidenceChain(
                source_file=current_id,
                source_layer=layer,
                source_confidence=conf,
                inherited_confidence=conf,
                reason=f"Direct confidence from {layer}",
            ))

            # Find files that reference this one (going up)
            backs = self.navigator.get_backlinks(current_id)
            if not backs:
                break

            # Follow to higher layer
            found_higher = False
            for back in backs:
                back_layer = back.layer
                layer_order = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
                current_order = layer_order.get(layer, 0)
                back_order = layer_order.get(back_layer, 0)

                if back_order < current_order:  # Higher layer (lower number)
                    current_id = back.file_id
                    found_higher = True
                    break

            if not found_higher:
                break

        # Calculate inherited confidence (minimum in chain)
        if chain:
            all_confs = [c.source_confidence for c in chain]
            inherited = min_confidence(all_confs)
            for c in chain:
                c.inherited_confidence = inherited

        return chain

    # ─── Layer Synthesis ──────────────────────────────────────────

    def _synthesize_layer(
        self,
        project: str,
        layer: str,
        lower_summaries: Dict[str, LayerSummary],
    ) -> LayerSummary:
        """Synthesize a single layer's content."""
        files = find_by_layer(layer, self.vault_path, project)
        key_points = []
        decisions = []
        constraints = []
        open_questions = []
        file_summaries = []

        for meta in files:
            path = meta.get("_path", "")
            if not path or not os.path.exists(path):
                continue

            try:
                fm, body = read_vault_file(path)
            except Exception:
                continue

            file_id = fm.get("id", meta.get("_filename", ""))
            file_type = fm.get("type", "unknown")
            confidence = fm.get("confidence", "moderate")

            # Extract key content based on layer
            points = self._extract_key_points(body, layer, file_type)

            # Extract decisions (L1) — skip test decisions
            if layer == "L1" or file_type == "decision":
                if not self._is_test_decision(fm, body):
                    decs = self._extract_decisions(body)
                    decisions.extend(decs)

            # Extract constraints (L3)
            if layer == "L3" or file_type == "rule":
                consts = self._extract_constraints(body)
                constraints.extend(consts)

            # Extract open questions
            questions = self._extract_questions(body)
            open_questions.extend(questions)

            key_points.extend(points)
            file_summaries.append({
                "file_id": file_id,
                "type": file_type,
                "layer": layer,
                "confidence": confidence,
                "summary": points[0] if points else "",
                "path": path,
            })

        return LayerSummary(
            layer=layer,
            file_count=len(files),
            key_points=key_points[:10],  # Top 10
            decisions=decisions,
            constraints=constraints,
            open_questions=open_questions,
            files=file_summaries,
        )

    def _extract_key_points(
        self, body: str, layer: str, file_type: str
    ) -> List[str]:
        """Extract key points from file body."""
        points = []

        # Try to extract from Summary section
        summary_match = re.search(
            r'## Summary\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
        )
        if summary_match:
            summary = summary_match.group(1).strip()
            # First sentence
            first_sentence = summary.split('.')[0] + '.' if '.' in summary else summary
            points.append(first_sentence)

        # Extract from Key Findings (L4)
        if layer == "L4":
            findings = re.findall(r'^\d+\.\s+(.+)$', body, re.MULTILINE)
            points.extend(findings[:3])

        # Extract from Rule Statement (L3)
        if layer == "L3" or file_type == "rule":
            rule_match = re.search(
                r'## Rule Statement\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
            )
            if rule_match:
                points.append(rule_match.group(1).strip()[:200])

        # Extract from Specification (L2)
        if layer == "L2" or file_type == "component":
            spec_match = re.search(
                r'## Specification\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
            )
            if spec_match:
                points.append(spec_match.group(1).strip()[:200])

        return points

    def _is_test_decision(self, frontmatter: Dict, body: str) -> bool:
        """Check if a decision file is a test artifact (should be excluded from synthesis)."""
        # Check tags
        tags = frontmatter.get("tags", [])
        if isinstance(tags, list) and "test" in tags:
            return True

        # Check file ID for test patterns
        file_id = frontmatter.get("id", "")
        if any(p in file_id.lower() for p in ["test-", "test_", "_test"]):
            return True

        # Check decision text for test markers (standalone word "test" or "verification")
        dec_match = re.search(r'## Decision\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
        if dec_match:
            dec_text = dec_match.group(1).strip().lower()
            if (dec_text.startswith("test") or
                "test decision" in dec_text or
                re.search(r'\btest\b', dec_text) or
                re.search(r'\bverification\b', dec_text)):
                return True

        # Check title for test markers
        title_match = re.search(r'^#\s+Decision:\s*(.+)$', body, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip().lower()
            if (title.startswith("test") or
                "test decision" in title or
                re.search(r'\btest\b', title) or
                re.search(r'\bverification\b', title)):
                return True

        return False

    def _extract_decisions(self, body: str) -> List[str]:
        """Extract decision statements."""
        decisions = []

        # From Decision section
        dec_match = re.search(
            r'## Decision\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL
        )
        if dec_match:
            decisions.append(dec_match.group(1).strip()[:200])

        # From Key Decisions list
        dec_items = re.findall(r'- \[\[(\w+)\]\]\s*[—-]\s*(.+)', body)
        for link, desc in dec_items:
            decisions.append(f"[[{link}]] — {desc}")

        return decisions

    def _extract_constraints(self, body: str) -> List[str]:
        """Extract constraint statements."""
        constraints = []

        # From Parameters table
        params = re.findall(
            r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|',
            body
        )
        for name, value, unit in params:
            name = name.strip()
            value = value.strip()
            unit = unit.strip()
            if name and name not in ('Parameter', '-----------'):
                constraints.append(f"{name}: {value} {unit}".strip())

        return constraints

    def _extract_questions(self, body: str) -> List[str]:
        """Extract open questions from file content.

        Looks for:
        1. Explicit question marks (?)
        2. 'Open Questions' / 'Knowledge Gaps' / 'Unresolved' sections
        3. TODO/TBD/FIXME/UNCERTAIN markers
        4. 'Not yet' / 'Unknown' / 'Needs investigation' phrases
        """
        questions = []

        # 1. Look for explicit question marks
        q_matches = re.findall(r'([^.!?\\n]*\?)', body)
        for q in q_matches:
            q = q.strip()
            if len(q) > 10 and len(q) < 200:
                questions.append(q)

        # 2. Extract from "Open Questions" / "Knowledge Gaps" sections (all occurrences)
        section_matches = re.findall(
            r'##\s*(?:Open Questions|Knowledge Gaps|Unresolved|Gaps Found|Assumptions Found)\s*\n(.*?)(?=\n## |\Z)',
            body, re.DOTALL | re.IGNORECASE
        )
        for section in section_matches:
            items = re.findall(r'^[-*]\s+(.+)$', section, re.MULTILINE)
            for item in items:
                item = item.strip()
                if len(item) > 5 and len(item) < 200:
                    questions.append(item)

        # 3. Look for TODO/TBD/UNCERTAIN markers
        todo_matches = re.findall(r'(?:TODO|TBD|FIXME|UNCERTAIN|NOT YET|UNKNOWN):\s*(.+?)(?:\.|$)', body, re.IGNORECASE)
        for t in todo_matches:
            t = t.strip()
            if len(t) > 5 and len(t) < 200:
                questions.append(f"[uncertain] {t}")

        # 4. Look for "needs investigation" / "not validated" phrases
        gap_phrases = re.findall(
            r'((?:no .{0,30}(?:validation|testing|verification|prototype|confirmed)|'
            r'(?:not yet|needs?|requires?)\s+\w+(?:ed|ing|ation)\w*|'
            r'(?:unclear|unknown|unvalidated|unconfirmed)\s+\w+)[^.]*\.)',
            body, re.IGNORECASE
        )
        for g in gap_phrases:
            g = g.strip()
            if len(g) > 10 and len(g) < 200 and g not in questions:
                questions.append(f"[gap] {g}")

        # 5. Look for "implementation gap" or similar explicit gap mentions
        gap_mentions = re.findall(
            r'([^.\n]*(?:gap|incomplete|pending|unfinished|placeholder)[^.\n]*\.)',
            body, re.IGNORECASE
        )
        for g in gap_mentions:
            g = g.strip()
            if len(g) > 10 and len(g) < 200 and g not in questions:
                questions.append(f"[gap] {g}")

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for q in questions:
            normalized = q.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(q)

        return unique[:10]

    def _get_file_dependencies(self, file_id: str, project: str) -> List[str]:
        """Get files this file depends on (via outgoing links)."""
        f = self.retriever.get(file_id, reason="deps")
        if not f:
            return []
        return [link for link in f.links if link != file_id]

    # ─── Text Generation ──────────────────────────────────────────

    def _generate_synthesis_text(
        self,
        project: str,
        layer_summaries: Dict[str, LayerSummary],
        decisions: List[str],
        rules: List[str],
        component_map: Dict[str, List[str]],
        questions: List[str],
        confidence: str,
    ) -> str:
        """Generate the synthesis markdown text."""
        lines = []
        today = datetime.now().strftime("%Y-%m-%d")

        lines.append(f"# Synthesis: {project.upper()}")
        lines.append("")
        lines.append(f"## Summary")
        lines.append(f"Auto-generated synthesis for {project} project. "
                     f"Aggregates knowledge from L4 research through L1 decisions. "
                     f"Overall confidence: {confidence}.")
        lines.append("")

        # Key Decisions
        lines.append("## Key Decisions")
        if decisions:
            for d in decisions[:10]:
                lines.append(f"- {d}")
        else:
            lines.append("_(none recorded)_")
        lines.append("")

        # Active Rules
        lines.append("## Active Rules")
        if rules:
            for r in rules[:10]:
                lines.append(f"- {r}")
        else:
            lines.append("_(none recorded)_")
        lines.append("")

        # Component Map
        lines.append("## Component Map")
        if component_map:
            for comp, deps in component_map.items():
                deps_str = ", ".join(f"[[{d}]]" for d in deps[:5])
                lines.append(f"- **{comp}** → {deps_str}" if deps_str else f"- **{comp}**")
        else:
            lines.append("_(none recorded)_")
        lines.append("")

        # Layer Breakdown
        lines.append("## Layer Breakdown")
        for layer in ["L1", "L2", "L3", "L4"]:
            summary = layer_summaries.get(layer)
            if summary:
                layer_name = {"L1": "Surface", "L2": "Components", "L3": "Rules", "L4": "Research"}
                lines.append(f"### {layer}: {layer_name.get(layer, '')} ({summary.file_count} files)")
                for point in summary.key_points[:3]:
                    lines.append(f"- {point[:150]}")
                lines.append("")

        # Current Status
        lines.append("## Current Status")
        for layer in ["L1", "L2", "L3", "L4"]:
            summary = layer_summaries.get(layer)
            if summary:
                lines.append(f"- **{layer}**: {summary.file_count} files")
        lines.append("")

        # Open Questions
        lines.append("## Open Questions")
        if questions:
            for q in questions[:10]:
                lines.append(f"- {q}")
        else:
            lines.append("_(none)_")
        lines.append("")

        # Links
        lines.append("## Links")
        lines.append("")
        lines.append("### Derived From")
        for layer in ["L4", "L3", "L2"]:
            summary = layer_summaries.get(layer)
            if summary:
                for f in summary.files[:3]:
                    lines.append(f"- [[{f['file_id']}]] — {layer}/{f['type']}")
        lines.append("")
        lines.append("### Related")
        lines.append("- [[_overview]] — Project overview")
        lines.append("")

        lines.append(f"_Generated: {today}_")

        return "\n".join(lines)

    def _write_synthesis_file(
        self,
        project: str,
        synthesis_text: str,
        confidence: str,
    ) -> List[str]:
        """Write the synthesis file to the project directory."""
        project_dir = Path(self.vault_path) / "projects" / project
        synthesis_path = project_dir / "_synthesis.md"

        today = datetime.now().strftime("%Y-%m-%d")

        # Build frontmatter
        metadata = {
            "id": "_synthesis",
            "type": "overview",
            "layer": "cross",
            "project": project,
            "created": today,
            "updated": today,
            "confidence": confidence,
            "status": "active",
            "tags": ["synthesis"],
        }

        content = write_frontmatter(metadata, synthesis_text)

        # Write file
        synthesis_path.parent.mkdir(parents=True, exist_ok=True)
        synthesis_path.write_text(content, encoding="utf-8")

        return [str(synthesis_path)]


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    engine = SynthesisEngine(vault)

    if cmd == "synthesize":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: synthesis.py synthesize <project>")
            sys.exit(1)
        result = engine.synthesize_project(project)
        print(f"Synthesis complete for '{result.project}'")
        print(f"Confidence: {result.confidence}")
        print(f"Files updated: {len(result.files_updated)}")
        print(f"Decisions: {len(result.key_decisions)}")
        print(f"Rules: {len(result.active_rules)}")
        print(f"Components: {len(result.component_map)}")
        print(f"Open questions: {len(result.open_questions)}")

    elif cmd == "layer":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        layer = sys.argv[3] if len(sys.argv) > 3 else "L4"
        if not project:
            print("Usage: synthesis.py layer <project> <layer>")
            sys.exit(1)
        summary = engine.synthesize_layer(project, layer)
        print(f"{layer} Summary ({summary.file_count} files):")
        for p in summary.key_points:
            print(f"  - {p[:100]}")

    elif cmd == "confidence":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        project = sys.argv[3] if len(sys.argv) > 3 else "eeg"
        if not file_id:
            print("Usage: synthesis.py confidence <file_id> [project]")
            sys.exit(1)
        chain = engine.get_confidence_chain(file_id, project)
        print(f"Confidence chain for [[{file_id}]]:")
        for c in chain:
            print(f"  [{c.source_layer}] {c.source_file}: {c.source_confidence} -> {c.inherited_confidence}")

    else:
        print("Commands: synthesize <project>, layer <project> <layer>, confidence <file_id> [project]")

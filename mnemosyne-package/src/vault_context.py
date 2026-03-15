#!/usr/bin/env python3
"""
Vault Context Integration for Hermes Agent.

This module bridges Mnemosyne vault with Hermes agent loop:
  - Builds vault context for system prompt injection
  - Provides agent-facing CLI commands
  - Manages vault state across conversation turns
  - Handles context refresh and navigation

Integration Points:
  1. System prompt: Call build_vault_prompt() to get vault section
  2. Agent tools: vault_* CLI commands for in-conversation use
  3. Memory: Vault files persist across sessions like memory files

Usage from agent code:
    from vault_context import VaultContextManager

    vcm = VaultContextManager()
    
    # Get context for system prompt
    vault_section = vcm.build_prompt_section(project="eeg")
    
    # Agent navigates during conversation
    result = vcm.drill_down("gold_oxidation")
    
    # Agent logs a decision
    vcm.log_decision("Use gold electrodes", reasoning_chain=[...])
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Add mnemosyne src to path
MNEMOSYNE_SRC = str(Path(__file__).parent)
if MNEMOSYNE_SRC not in sys.path:
    sys.path.insert(0, MNEMOSYNE_SRC)

from vault_utils import scan_vault, read_vault_file
from layer_state import LayerState
from context_loader import ContextLoader
from vault_search import VaultSearch
from link_navigator import LinkNavigator
from on_demand import OnDemandRetriever
from traversal import VaultNavigator
from synthesis import SynthesisEngine
from intent import IntentManager
from audit import AuditLogger
from governance import GovernanceEngine
from attribution import AttributionTracker
from context_audit import ContextAuditor
from status import StatusTracker
from trust import TrustModel
from maintenance import VaultMaintainer
from cross_project import CrossProjectAnalyzer


# ─── Vault Context Manager ────────────────────────────────────────

@dataclass
class VaultSessionState:
    """State maintained across conversation turns."""
    project: Optional[str] = None
    current_layer: str = "L1"
    current_file: Optional[str] = None
    context_loaded: bool = False
    last_topic: Optional[str] = None
    files_in_context: List[str] = field(default_factory=list)
    turn_count: int = 0


class VaultContextManager:
    """
    Manages vault context for the Hermes agent.

    Provides a single interface to all vault functionality,
    maintaining state across conversation turns.

    Public API (all return str for display unless noted):
        enter_project(project) -> str
        drill_down(target=None) -> str
        synthesize_up() -> str
        search_vault(query, limit=5) -> str
        get_file(file_id) -> str
        log_decision(decision, reasoning_chain, ...) -> str
        check_authority(area, action) -> str
        get_status() -> str
        synthesize() -> str
        get_state() -> Dict              # structured data
        build_prompt_section(...) -> str
        vault_exists() -> bool           # check if vault is accessible

    Usage:
        from vault_context import VaultContextManager

        vcm = VaultContextManager()
        if not vcm.vault_exists():
            print("Vault not found")

        vcm.enter_project("eeg")
        print(vcm.get_status())
        print(vcm.search_vault("gold"))
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.state = VaultSessionState()
        self._vault_valid = False

        # Only initialize components if vault directory exists
        if not Path(self.vault_path).is_dir():
            self._init_error = f"Vault directory not found: {self.vault_path}"
            return

        try:
            # Initialize all components
            self.navigator = VaultNavigator(vault_path)
            self.loader = ContextLoader(vault_path)
            self.search = VaultSearch(vault_path)
            self.retriever = OnDemandRetriever(vault_path)
            self.synthesis = SynthesisEngine(vault_path)
            self.intent = IntentManager(vault_path)
            self.audit = AuditLogger(vault_path)
            self.governance = GovernanceEngine(vault_path)
            self.attribution = AttributionTracker(vault_path)
            self.context_audit = ContextAuditor(vault_path)
            self.status = StatusTracker(vault_path)
            self.trust = TrustModel(vault_path)
            self.maintenance = VaultMaintainer(vault_path)
            self.cross_project = CrossProjectAnalyzer(vault_path)
            self._vault_valid = True
            self._init_error = None
        except Exception as e:
            self._init_error = f"Failed to initialize vault components: {type(e).__name__}: {e}"

    def vault_exists(self) -> bool:
        """Check if vault is accessible and properly initialized."""
        return self._vault_valid

    def get_error(self) -> Optional[str]:
        """Get initialization error message, or None if vault is OK."""
        return self._init_error

    def _check_vault(self) -> Optional[str]:
        """Check vault is valid. Returns error string or None."""
        if not self._vault_valid:
            return self._init_error or "Vault not initialized"
        return None

    def build_prompt_section(
        self,
        project: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> str:
        """
        Build vault context section for system prompt.

        This is the main integration point — call this when building
        the system prompt to inject vault context.

        Returns formatted text ready for prompt injection.
        """
        # Use provided project or fall back to session state
        proj = project or self.state.project

        if not proj:
            # No project — return minimal vault overview
            return self._build_minimal_context()

        # Load context
        ctx = self.loader.load_context(
            project=proj,
            topic=topic or self.state.last_topic,
            budget_tokens=4000,
        )

        # Update state
        self.state.project = proj
        self.state.last_topic = topic
        self.state.context_loaded = True
        self.state.files_in_context = [f.file_id for f in ctx.files]
        self.state.turn_count += 1

        # Log context load
        self.context_audit.log_load(
            project=proj,
            topic=topic,
            loaded_files=[
                {
                    "file_id": f.file_id,
                    "layer": f.layer,
                    "file_type": f.file_type,
                    "relevance_score": f.relevance_score,
                    "token_estimate": f.token_estimate,
                    "load_reason": f.load_reason,
                }
                for f in ctx.files
            ],
            budget_used=ctx.total_tokens,
            budget_limit=ctx.budget_tokens,
            stage1_scanned=ctx.stage1_scanned,
            stage2_loaded=ctx.stage2_loaded,
        )

        # Format for prompt
        return ctx.to_prompt_section()

    def enter_project(self, project: str) -> str:
        """Enter a project context."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        self.state.project = project
        self.state.current_layer = "L1"
        result = self.navigator.enter_project(project)

        summary = f"Entered project: {project}\n"

        overview = result.get("overview")
        if overview and hasattr(overview, 'frontmatter'):
            phase = overview.frontmatter.get("phase", "unknown")
        elif overview and isinstance(overview, dict):
            phase = overview.get("frontmatter", {}).get("phase", "unknown")
        else:
            phase = "unknown"
        summary += f"Phase: {phase}\n"

        layers = result.get("layers", [])
        for layer in layers:
            summary += f"  {layer['layer']} ({layer['name']}): {layer['file_count']} files\n"

        return summary

    def drill_down(self, target: Optional[str] = None) -> str:
        """
        Drill down to deeper layer or specific file.

        Args:
            target: Optional file ID to drill into

        Returns: Summary of new context
        """
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        if target:
            result = self.navigator.drill_to(target)
            if result:
                self.state.current_layer = result.target_file.layer
                self.state.current_file = target
                summary = f"Now viewing: {target} [{result.target_file.layer}]\n"
                summary += f"Context: {len(result.context_above)} above, {len(result.context_below)} below\n"
                if result.reasoning_chain:
                    summary += f"Reasoning chain: {' → '.join(n.file_id for n in result.reasoning_chain)}\n"
                return summary
            return f"File '{target}' not found"

        # Just go deeper
        result = self.navigator.drill_down()
        if result:
            self.state.current_layer = result["layer"]
            summary = f"Now at {result['layer']} ({result['layer_name']}): {result['file_count']} files\n"
            for f in result.get("files", [])[:5]:
                summary += f"  - {f.file_id}\n"
            return summary
        return "Cannot drill deeper (already at L4)"

    def synthesize_up(self) -> str:
        """Move to higher layer."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        result = self.navigator.synthesize_up()
        if result:
            self.state.current_layer = result["layer"]
            return f"Now at {result['layer']} ({result['layer_name']}): {result['file_count']} files"
        return "Cannot go higher (already at L1)"

    def search_vault(self, query: str, limit: int = 5) -> str:
        """Search the vault."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        results = self.search.search(query, project=self.state.project, limit=limit)
        if not results:
            return f"No results for '{query}'"

        summary = f"Found {len(results)} results for '{query}':\n"
        for r in results:
            summary += f"  {r.score:.2f} [{r.layer}] {r.file_id}: {r.snippet[:60]}\n"
        return summary

    def get_file(self, file_id: str) -> str:
        """Get a file's content."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        f = self.retriever.get(file_id)
        if not f:
            return f"File '{file_id}' not found"

        self.state.current_file = file_id
        self.state.current_layer = f.layer

        summary = f"[{f.layer}/{f.file_type}] {f.file_id}\n"
        summary += f"Confidence: {f.frontmatter.get('confidence', 'moderate')}\n"
        summary += f"Updated: {f.frontmatter.get('updated', 'unknown')}\n"
        summary += f"Links: {', '.join(f.links[:10])}\n"
        summary += f"\n{f.body[:1000]}"
        if len(f.body) > 1000:
            summary += "\n...[truncated]"
        return summary

    def log_decision(
        self,
        decision: str,
        reasoning_chain: List[Dict],
        confidence: str = "moderate",
        alternatives: Optional[List[Dict]] = None,
    ) -> str:
        """Log a decision to the audit trail."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        entry = self.audit.log_decision(
            project=self.state.project or "general",
            decision=decision,
            reasoning_chain=reasoning_chain,
            confidence=confidence,
            alternatives=alternatives,
        )
        return f"Decision logged: {entry.id}\n{entry.decision}"

    def check_authority(self, area: str, action: str) -> str:
        """Check if an action is authorized."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        if not self.state.project:
            return "No active project"

        decision = self.governance.authorize(self.state.project, area, action)
        return f"Allowed: {decision.allowed}\nLevel: {decision.autonomy_level.value}\n{decision.message}"

    def get_status(self) -> str:
        """Get current project status."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        if not self.state.project:
            return "No active project"

        status = self.status.get_status(self.state.project)
        summary = f"Project: {status.project}\n"
        summary += f"Health: {status.health} ({status.health_score:.0%})\n"
        summary += f"Phase: {status.phase}\n"
        summary += f"Criteria: {status.criteria_completed}/{status.criteria_total} ({status.criteria_completion:.0%})\n"
        summary += f"Files: {status.total_files} total, {status.recent_changes} recent\n"

        if status.alerts:
            summary += f"Alerts: {len(status.alerts)}\n"
            for a in status.alerts[:3]:
                summary += f"  [{a.level.value}] {a.message}\n"

        return summary

    def synthesize(self) -> str:
        """Run synthesis for current project."""
        err = self._check_vault()
        if err:
            return f"Error: {err}"
        if not self.state.project:
            return "No active project"

        result = self.synthesis.synthesize_project(self.state.project)
        return (
            f"Synthesis complete for {result.project}\n"
            f"Confidence: {result.confidence}\n"
            f"Decisions: {len(result.key_decisions)}\n"
            f"Rules: {len(result.active_rules)}\n"
            f"Components: {len(result.component_map)}\n"
            f"Files updated: {', '.join(result.files_updated)}"
        )

    def get_state(self) -> Dict:
        """Get current vault session state. Always works (no vault check)."""
        return {
            "project": self.state.project,
            "layer": self.state.current_layer,
            "current_file": self.state.current_file,
            "context_loaded": self.state.context_loaded,
            "files_in_context": len(self.state.files_in_context),
            "turn_count": self.state.turn_count,
        }

    def _build_minimal_context(self) -> str:
        """Build minimal vault context when no project is active."""
        try:
            files = scan_vault(self.vault_path)
        except Exception:
            return "# Knowledge Vault\nNo vault found at " + self.vault_path

        projects = set()
        for f in files:
            proj = f.get("project")
            if proj and proj != "general":
                projects.add(proj)

        lines = []
        lines.append("# Knowledge Vault")
        lines.append("")
        lines.append(f"Files: {len(files)}")
        if projects:
            lines.append(f"Projects: {', '.join(sorted(projects))}")
            lines.append("")
            lines.append("Use 'enter <project>' to load project context.")
        else:
            lines.append("No projects found. Use vault commands to create one.")
        lines.append("")

        return "\n".join(lines)


# ─── CLI for Agent ────────────────────────────────────────────────

def main():
    """CLI interface for agent use."""
    if len(sys.argv) < 2:
        print("Usage: vault_context.py <command> [args...]")
        print("Commands: prompt, enter, drill, up, search, file, status, synthesize, decision, authorize, state")
        sys.exit(1)

    vault_path = os.path.expanduser("~/.hermes/memory")
    vcm = VaultContextManager(vault_path)
    cmd = sys.argv[1]

    # Restore state if exists
    state_file = Path(vault_path) / ".vault_state.json"
    if state_file.exists():
        try:
            state_data = json.loads(state_file.read_text())
            vcm.state.project = state_data.get("project")
            vcm.state.current_layer = state_data.get("layer", "L1")
            vcm.state.current_file = state_data.get("current_file")
        except Exception:
            pass

    result = ""

    if cmd == "prompt":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        topic = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
        result = vcm.build_prompt_section(project=project, topic=topic)

    elif cmd == "enter":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            result = "Usage: vault_context.py enter <project>"
        else:
            result = vcm.enter_project(project)

    elif cmd == "drill":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        result = vcm.drill_down(target)

    elif cmd == "up":
        result = vcm.synthesize_up()

    elif cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            result = "Usage: vault_context.py search <query>"
        else:
            result = vcm.search_vault(query)

    elif cmd == "file":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            result = "Usage: vault_context.py file <file_id>"
        else:
            result = vcm.get_file(file_id)

    elif cmd == "status":
        result = vcm.get_status()

    elif cmd == "synthesize":
        result = vcm.synthesize()

    elif cmd == "state":
        state = vcm.get_state()
        result = json.dumps(state, indent=2)

    elif cmd == "decision":
        decision = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        if not decision:
            result = "Usage: vault_context.py decision <decision_text>"
        else:
            result = vcm.log_decision(decision, reasoning_chain=[])

    elif cmd == "authorize":
        area = sys.argv[2] if len(sys.argv) > 2 else "research"
        action = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "explore"
        result = vcm.check_authority(area, action)

    else:
        result = f"Unknown command: {cmd}"

    print(result)

    # Save state
    try:
        state_data = {
            "project": vcm.state.project,
            "layer": vcm.state.current_layer,
            "current_file": vcm.state.current_file,
        }
        state_file.write_text(json.dumps(state_data))
    except Exception:
        pass


if __name__ == "__main__":
    main()

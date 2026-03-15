#!/usr/bin/env python3
"""
Integration tests for Mnemosyne vault + Hermes agent.

Tests: vault_context, vault_cli, setup_vault, AGENTS.md.
"""

import sys
import os
import tempfile
import shutil
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vault_context import VaultContextManager, VaultSessionState

# ─── Test Helpers ─────────────────────────────────────────────────

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def assert_true(self, condition, msg=""):
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"FAIL: {msg}")

    def assert_equal(self, a, b, msg=""):
        if a == b:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"FAIL: {msg} (got {a!r}, expected {b!r})")

    def assert_in(self, item, container, msg=""):
        if item in container:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"FAIL: {msg} ({item!r} not in container)")

    def assert_greater(self, a, b, msg=""):
        if a > b:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"FAIL: {msg} ({a} not > {b})")

    def summary(self):
        total = self.passed + self.failed
        status = "ALL PASSED" if self.failed == 0 else "SOME FAILED"
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed — {status}")
        if self.errors:
            print(f"\nFailures:")
            for e in self.errors:
                print(f"  {e}")
        print(f"{'='*60}")
        return self.failed == 0


# ─── Create Test Vault ────────────────────────────────────────────

def create_test_vault():
    """Create a temporary vault with test content."""
    tmpdir = tempfile.mkdtemp(prefix="mnemosyne_int_test_")
    vault = Path(tmpdir)

    today = datetime.now().strftime("%Y-%m-%d")

    # Structure
    (vault / "projects" / "eeg" / "components").mkdir(parents=True)
    (vault / "projects" / "eeg" / "rules").mkdir(parents=True)
    (vault / "projects" / "eeg" / "research").mkdir(parents=True)
    (vault / "decisions").mkdir(parents=True)
    (vault / "concepts").mkdir(parents=True)
    (vault / "user").mkdir(parents=True)
    (vault / "archive").mkdir(parents=True)
    (vault / "attribution").mkdir(parents=True)
    (vault / "context_audit").mkdir(parents=True)
    (vault / "trust").mkdir(parents=True)
    (vault / "governance").mkdir(parents=True)
    (vault / "alerts").mkdir(parents=True)

    # EEG overview
    (vault / "projects" / "eeg" / "_overview.md").write_text(f"""---
id: _overview
type: overview
layer: L1
project: eeg
created: {today}
updated: {today}
confidence: high
status: active
phase: research
health: green
tags: [eeg]
---

# EEG Headset

## Summary
Building a 256-channel EEG headset with gold electrodes.

## Intent

### Objective
Create research-grade EEG recording system.

### Success Criteria
- [x] Electrode material selected
- [ ] Impedance < 50kΩ

### Decision Autonomy
| Area | Level | Notes |
|------|-------|-------|
| Research | autonomous | |
| Implementation | notify | |
| Spending | approve | |

### Stop Rules
- If budget exceeds $5000 → stop

## Key Decisions
- [[gold_electrodes]] — Use gold electrodes
""", encoding="utf-8")

    # Component
    (vault / "projects" / "eeg" / "components" / "gold_electrodes.md").write_text(f"""---
id: gold_electrodes
type: component
layer: L2
project: eeg
created: {today}
updated: {today}
confidence: high
status: active
tags: [electrodes, gold]
---

# Gold Electrodes
Gold-plated copper disc electrodes.
""", encoding="utf-8")

    # Research
    (vault / "projects" / "eeg" / "research" / "gold_oxidation.md").write_text(f"""---
id: gold_oxidation
type: research
layer: L4
project: eeg
created: {today}
updated: {today}
confidence: high
status: active
tags: [materials]
---

# Gold Oxidation
Gold resists oxidation at skin pH 4-9.
""", encoding="utf-8")

    # Rule
    (vault / "projects" / "eeg" / "rules" / "impedance_spec.md").write_text(f"""---
id: impedance_spec
type: rule
layer: L3
project: eeg
created: {today}
updated: {today}
confidence: high
status: active
tags: [spec]
---

# Impedance Spec
Must be below 50kΩ.
""", encoding="utf-8")

    # Index and user files
    (vault / "_index.md").write_text(f"""---
id: _index
type: index
layer: cross
updated: {today}
---

# Index
""", encoding="utf-8")

    (vault / "user" / "active_context.md").write_text(f"""---
id: active_context
type: context
layer: cross
---

Current: eeg
""", encoding="utf-8")

    return str(vault)


from datetime import datetime


# ─── Tests ────────────────────────────────────────────────────────

def test_vault_context_manager(r, vault_path):
    """Test the main VaultContextManager."""
    print("\n--- VaultContextManager Tests ---")

    vcm = VaultContextManager(vault_path)

    # Initial state
    state = vcm.get_state()
    r.assert_equal(state["project"], None, "No project initially")
    r.assert_equal(state["layer"], "L1", "Starts at L1")
    r.assert_equal(state["turn_count"], 0, "No turns yet")

    # Enter project
    result = vcm.enter_project("eeg")
    r.assert_in("eeg", result, "Enter mentions project")
    r.assert_in("L1", result, "Enter shows L1")

    # State updated
    state = vcm.get_state()
    r.assert_equal(state["project"], "eeg", "Project set after enter")

    # Build prompt section
    prompt = vcm.build_prompt_section(project="eeg", topic="electrodes")
    r.assert_greater(len(prompt), 100, "Prompt has content")
    r.assert_in("eeg", prompt, "Prompt mentions project")

    # State after prompt
    state = vcm.get_state()
    r.assert_equal(state["context_loaded"], True, "Context loaded")
    r.assert_greater(state["files_in_context"], 0, "Files in context")
    r.assert_equal(state["turn_count"], 1, "Turn count incremented")

    # Drill down
    result = vcm.drill_down()
    r.assert_in("L2", result, "Drill goes to L2")

    # Drill to specific file
    result = vcm.drill_down("gold_oxidation")
    r.assert_in("gold_oxidation", result, "Drill to file works")

    # Get file
    content = vcm.get_file("gold_electrodes")
    r.assert_in("Gold", content, "Get file has content")
    r.assert_in("L2", content, "Get file shows layer")

    # Search
    results = vcm.search_vault("gold")
    r.assert_in("results", results.lower(), "Search returns results")

    # Status
    status = vcm.get_status()
    r.assert_in("eeg", status, "Status shows project")
    r.assert_in("green", status, "Status shows health")

    # Check authority
    auth = vcm.check_authority("research", "explore ADC chips")
    r.assert_in("autonomous", auth.lower(), "Research is autonomous")

    auth2 = vcm.check_authority("spending", "buy components")
    r.assert_in("approve", auth2.lower(), "Spending needs approval")

    print("  VaultContextManager: OK")


def test_prompt_section(r, vault_path):
    """Test prompt section generation."""
    print("\n--- Prompt Section Tests ---")

    vcm = VaultContextManager(vault_path)

    # No project — minimal context
    prompt = vcm.build_prompt_section()
    r.assert_in("Vault", prompt, "Minimal context mentions vault")

    # With project
    vcm.enter_project("eeg")
    prompt = vcm.build_prompt_section(project="eeg", topic="gold electrodes")
    r.assert_in("KNOWLEDGE VAULT CONTEXT", prompt, "Has vault header")
    r.assert_in("eeg", prompt, "Has project name")

    # With topic
    prompt2 = vcm.build_prompt_section(project="eeg", topic="impedance")
    r.assert_in("impedance", prompt2, "Topic appears in context")

    print("  Prompt Section: OK")


def test_decision_logging(r, vault_path):
    """Test decision logging through vault context."""
    print("\n--- Decision Logging Tests ---")

    vcm = VaultContextManager(vault_path)
    vcm.enter_project("eeg")

    # Log decision
    result = vcm.log_decision(
        "Use gold electrodes",
        reasoning_chain=[
            {"layer": "L4", "file_id": "gold_oxidation", "finding": "Gold resists oxidation"},
        ],
        confidence="high",
    )
    r.assert_in("Decision logged", result, "Decision logged")
    r.assert_in("gold electrodes", result.lower(), "Decision text in result")

    # Check decision was written
    decisions_dir = Path(vault_path) / "decisions"
    decision_files = list(decisions_dir.glob("*.md"))
    r.assert_greater(len(decision_files), 0, "Decision file created")

    print("  Decision Logging: OK")


def test_state_persistence(r, vault_path):
    """Test state tracking across operations."""
    print("\n--- State Persistence Tests ---")

    vcm = VaultContextManager(vault_path)

    # Start
    vcm.enter_project("eeg")
    state1 = vcm.get_state()
    r.assert_equal(state1["project"], "eeg", "Project set")

    # Drill changes state
    vcm.drill_down()
    state2 = vcm.get_state()
    r.assert_equal(state2["layer"], "L2", "Layer changed to L2")

    # File changes state
    vcm.get_file("gold_oxidation")
    state3 = vcm.get_state()
    r.assert_equal(state3["current_file"], "gold_oxidation", "Current file set")

    print("  State Persistence: OK")


def test_synthesis_via_context(r, vault_path):
    """Test synthesis through vault context manager."""
    print("\n--- Synthesis via Context Tests ---")

    vcm = VaultContextManager(vault_path)
    vcm.enter_project("eeg")

    result = vcm.synthesize()
    r.assert_in("Synthesis complete", result, "Synthesis completes")
    r.assert_in("eeg", result, "Synthesis mentions project")

    # Check synthesis file was created
    synth_file = Path(vault_path) / "projects" / "eeg" / "_synthesis.md"
    r.assert_true(synth_file.exists(), "_synthesis.md created")

    print("  Synthesis: OK")


def test_agents_md(r, workspace_path):
    """Test AGENTS.md exists and has content."""
    print("\n--- AGENTS.md Tests ---")

    agents_path = Path(workspace_path) / "AGENTS.md"
    r.assert_true(agents_path.exists(), "AGENTS.md exists")

    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8")
        r.assert_in("vault", content.lower(), "AGENTS.md mentions vault")
        r.assert_in("enter", content.lower(), "AGENTS.md mentions enter command")
        r.assert_in("L1", content, "AGENTS.md mentions layers")

    print("  AGENTS.md: OK")


def test_setup_script(r, vault_path):
    """Test setup script functions."""
    print("\n--- Setup Script Tests ---")

    # Just verify the script exists and is importable
    setup_path = Path(__file__).parent.parent / "setup_vault.py"
    r.assert_true(setup_path.exists(), "setup_vault.py exists")

    if setup_path.exists():
        content = setup_path.read_text(encoding="utf-8")
        r.assert_in("create_vault_structure", content, "Has structure creation")
        r.assert_in("install_scripts", content, "Has script installation")
        r.assert_in("verify_installation", content, "Has verification")

    print("  Setup Script: OK")


# ─── Main ─────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Mnemosyne Integration Test Suite")
    print("=" * 60)

    r = TestResult()
    vault_path = create_test_vault()
    workspace_path = str(Path(__file__).parent.parent.parent)

    try:
        print(f"\nTest vault: {vault_path}")

        test_vault_context_manager(r, vault_path)
        test_prompt_section(r, vault_path)
        test_decision_logging(r, vault_path)
        test_state_persistence(r, vault_path)
        test_synthesis_via_context(r, vault_path)
        test_agents_md(r, workspace_path)
        test_setup_script(r, vault_path)

    finally:
        shutil.rmtree(vault_path)
        print(f"\nCleaned up test vault")

    success = r.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

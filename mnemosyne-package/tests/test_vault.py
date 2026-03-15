#!/usr/bin/env python3
"""
Test suite for Mnemosyne vault components.
Tests: vault_utils (frontmatter, links) and layer_state (traversal).
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vault_utils import (
    parse_frontmatter, write_frontmatter, extract_links,
    resolve_link, find_broken_links, scan_vault,
    find_by_layer, find_by_project, find_by_tag,
    read_vault_file, update_frontmatter_field, find_backlinks
)
from layer_state import LayerState, TraversalMode, LAYER_ORDER

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
            self.errors.append(f"FAIL: {msg} ({item!r} not in {container!r})")

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
    """Create a temporary vault for testing."""
    tmpdir = tempfile.mkdtemp(prefix="mnemosyne_test_")
    vault = Path(tmpdir)

    # Create directory structure
    (vault / "projects" / "testproj" / "components").mkdir(parents=True)
    (vault / "projects" / "testproj" / "rules").mkdir(parents=True)
    (vault / "projects" / "testproj" / "research").mkdir(parents=True)
    (vault / "decisions").mkdir(parents=True)
    (vault / "concepts").mkdir(parents=True)
    (vault / "user").mkdir(parents=True)

    # Create test files
    (vault / "projects" / "testproj" / "_overview.md").write_text("""---
id: _overview
type: overview
layer: L1
project: testproj
created: 2026-03-13
updated: 2026-03-13
confidence: high
status: active
tags: [main]
---

# Test Project Overview

## Summary
A test project for unit testing.

## Key Decisions
- [[widget]] — Use widgets
- [[constraint_1]] — Budget limit

## Links

### Supports
- [[widget]]
- [[constraint_1]]
""", encoding="utf-8")

    (vault / "projects" / "testproj" / "components" / "widget.md").write_text("""---
id: widget
type: component
layer: L2
project: testproj
created: 2026-03-13
updated: 2026-03-13
confidence: high
status: active
tags: [hardware]
---

# Widget Component

## Summary
A test widget component.

## Links

### Derived From
- [[_overview]]

### Supports
- [[_synthesis]]
""", encoding="utf-8")

    (vault / "projects" / "testproj" / "rules" / "constraint_1.md").write_text("""---
id: constraint_1
type: rule
layer: L3
project: testproj
created: 2026-03-13
updated: 2026-03-13
confidence: high
status: active
tags: [budget]
---

# Budget Constraint

## Rule Statement
Total cost must not exceed $100.

## Links

### Derived From
- [[_overview]]

### Supports
- [[widget]]
""", encoding="utf-8")

    (vault / "projects" / "testproj" / "research" / "market_analysis.md").write_text("""---
id: market_analysis
type: research
layer: L4
project: testproj
created: 2026-03-13
updated: 2026-03-13
confidence: moderate
status: active
tags: [market]
---

# Market Analysis

## Summary
Widgets cost $20-50 on the market.

## Links

### Supports
- [[constraint_1]]
""", encoding="utf-8")

    (vault / "decisions" / "decision_001.md").write_text("""---
id: decision_001
type: decision
layer: L1
project: testproj
created: 2026-03-13
updated: 2026-03-13
confidence: high
status: active
---

# Decision: Use Widgets

## Decision
Use widgets for the project.

## Reasoning Chain
1. L4: [[market_analysis]]
2. L3: [[constraint_1]]
3. L1: Widgets selected
""", encoding="utf-8")

    # Broken link file
    (vault / "concepts" / "broken_test.md").write_text("""---
id: broken_test
type: concept
layer: cross
project: general
created: 2026-03-13
updated: 2026-03-13
---

# Broken Link Test

This links to [[nonexistent_file]] which does not exist.
""", encoding="utf-8")

    return str(vault)


# ─── Tests ────────────────────────────────────────────────────────

def test_frontmatter(r):
    """Test frontmatter parsing and writing."""
    print("\n--- Frontmatter Tests ---")

    # Parse valid frontmatter
    content = """---
id: test
type: research
layer: L4
---
Body text here
"""
    meta, body = parse_frontmatter(content)
    r.assert_equal(meta.get("id"), "test", "Parse id field")
    r.assert_equal(meta.get("type"), "research", "Parse type field")
    r.assert_equal(meta.get("layer"), "L4", "Parse layer field")
    r.assert_true("Body text here" in body, "Body extracted correctly")

    # Parse no frontmatter
    meta2, body2 = parse_frontmatter("Just plain text")
    r.assert_equal(meta2, {}, "No frontmatter returns empty dict")
    r.assert_equal(body2, "Just plain text", "Body is entire content when no frontmatter")

    # Write frontmatter
    written = write_frontmatter({"id": "new", "type": "rule"}, "New body")
    r.assert_true("---" in written, "Written content has frontmatter markers")
    r.assert_true("New body" in written, "Written content has body")

    print("  Frontmatter: OK")


def test_links(r, vault_path):
    """Test link extraction and resolution."""
    print("\n--- Link Tests ---")

    # Extract links
    links = extract_links("See [[file_a]] and [[file_b|Display]] for info")
    r.assert_equal(len(links), 2, "Extract 2 links")
    r.assert_in("file_a", links, "First link extracted")
    r.assert_in("file_b", links, "Second link (with alias) extracted")

    # Resolve existing link
    resolved = resolve_link("widget", vault_path)
    r.assert_true(resolved is not None, "Resolve existing link 'widget'")
    r.assert_true("widget.md" in (resolved or ""), "Resolved path contains widget.md")

    # Resolve broken link
    broken = resolve_link("nonexistent_file", vault_path)
    r.assert_equal(broken, None, "Broken link returns None")

    # Find backlinks
    backs = find_backlinks("widget", vault_path)
    r.assert_true(len(backs) > 0, "Found backlinks to 'widget'")

    print("  Links: OK")


def test_vault_scanner(r, vault_path):
    """Test vault scanning functions."""
    print("\n--- Vault Scanner Tests ---")

    # Scan all
    files = scan_vault(vault_path)
    r.assert_true(len(files) >= 5, f"Scanned vault has files (got {len(files)})")

    # Find by layer
    l1_files = find_by_layer("L1", vault_path, "testproj")
    r.assert_true(len(l1_files) >= 1, "Found L1 files for testproj")

    l4_files = find_by_layer("L4", vault_path, "testproj")
    r.assert_true(len(l4_files) >= 1, "Found L4 files for testproj")

    # Find by project
    proj_files = find_by_project("testproj", vault_path)
    r.assert_true(len(proj_files) >= 4, f"Found project files (got {len(proj_files)})")

    # Find by tag
    tagged = find_by_tag("hardware", vault_path)
    r.assert_true(len(tagged) >= 1, "Found files by tag 'hardware'")

    print("  Vault Scanner: OK")


def test_broken_links(r, vault_path):
    """Test broken link detection."""
    print("\n--- Broken Link Tests ---")

    broken = find_broken_links(vault_path)
    r.assert_true(len(broken) >= 1, "Found broken links in test vault")

    # Check that our known broken link is detected
    found_nonexistent = any("nonexistent_file" in link for _, link in broken)
    r.assert_true(found_nonexistent, "Detected 'nonexistent_file' as broken")

    print("  Broken Links: OK")


def test_layer_state(r, vault_path):
    """Test layer state machine."""
    print("\n--- Layer State Tests ---")

    state = LayerState(vault_path=vault_path)
    state.set_project("testproj")

    # Initial state
    ctx = state.get_context()
    r.assert_equal(ctx["layer"], "L1", "Initial layer is L1")
    r.assert_equal(ctx["project"], "testproj", "Project set correctly")
    r.assert_true(ctx["file_count"] >= 1, "L1 has files")

    # Drill down L1 -> L2
    ctx2 = state.drill_down("testing drill down")
    r.assert_equal(ctx2["layer"], "L2", "Drilled down to L2")
    r.assert_true(ctx2["file_count"] >= 1, "L2 has files")

    # Drill down L2 -> L3
    ctx3 = state.drill_down("testing L3")
    r.assert_equal(ctx3["layer"], "L3", "Drilled down to L3")

    # Drill down L3 -> L4
    ctx4 = state.drill_down("testing L4")
    r.assert_equal(ctx4["layer"], "L4", "Drilled down to L4")
    r.assert_true(ctx4["file_count"] >= 1, "L4 has files")

    # Can't drill down from L4
    ctx5 = state.drill_down("should fail")
    r.assert_equal(ctx5["layer"], "L4", "Still at L4 (can't go deeper)")

    # Synthesize up L4 -> L3
    ctx6 = state.synthesize_up("back to L3")
    r.assert_equal(ctx6["layer"], "L3", "Synthesized up to L3")

    # Direct layer set
    ctx7 = state.set_layer("L1")
    r.assert_equal(ctx7["layer"], "L1", "Direct set to L1")

    # History tracking
    history = state.get_history()
    r.assert_true(len(history) >= 5, f"History tracked ({len(history)} transitions)")

    # Available layers
    layers = state.available_layers()
    r.assert_equal(len(layers), 4, "4 layers available")

    print("  Layer State: OK")


def test_project_init(r, vault_path):
    """Test project initialization."""
    print("\n--- Project Init Tests ---")

    # Create a temp vault for init test
    tmpdir = tempfile.mkdtemp(prefix="mnemosyne_init_test_")
    test_vault = Path(tmpdir)
    (test_vault / "projects").mkdir(parents=True)
    (test_vault / "decisions").mkdir(parents=True)
    (test_vault / "concepts").mkdir(parents=True)
    (test_vault / "user").mkdir(parents=True)
    (test_vault / "archive").mkdir(parents=True)

    try:
        path = LayerState.init_project(str(test_vault), "newproj")
        r.assert_true(os.path.exists(path), "Project directory created")

        overview = Path(path) / "_overview.md"
        r.assert_true(overview.exists(), "_overview.md created")

        synthesis = Path(path) / "_synthesis.md"
        r.assert_true(synthesis.exists(), "_synthesis.md created")

        for subdir in ["components", "rules", "research"]:
            r.assert_true((Path(path) / subdir).exists(), f"{subdir}/ created")

        # Verify overview has correct frontmatter
        meta, _ = read_vault_file(str(overview))
        r.assert_equal(meta.get("project"), "newproj", "Overview has correct project")
        r.assert_equal(meta.get("layer"), "L1", "Overview is L1")
        r.assert_equal(meta.get("type"), "overview", "Overview type correct")

        print("  Project Init: OK")

    finally:
        shutil.rmtree(tmpdir)


def test_file_reading(r, vault_path):
    """Test reading vault files with full content."""
    print("\n--- File Reading Tests ---")

    meta, body = read_vault_file(os.path.join(vault_path, "projects", "testproj", "_overview.md"))
    r.assert_equal(meta.get("id"), "_overview", "Read file metadata")
    r.assert_true("Test Project Overview" in body, "Read file body")

    print("  File Reading: OK")


# ─── Main ─────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Mnemosyne Vault Test Suite")
    print("=" * 60)

    r = TestResult()
    vault_path = create_test_vault()

    try:
        print(f"\nTest vault: {vault_path}")

        test_frontmatter(r)
        test_links(r, vault_path)
        test_vault_scanner(r, vault_path)
        test_broken_links(r, vault_path)
        test_file_reading(r, vault_path)
        test_layer_state(r, vault_path)
        test_project_init(r, vault_path)

    finally:
        shutil.rmtree(vault_path)
        print(f"\nCleaned up test vault")

    success = r.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

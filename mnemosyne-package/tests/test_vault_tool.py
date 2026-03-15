#!/usr/bin/env python3
"""
Test suite for vault_tool.py — Phase 1: Tool Layer

Tests the native vault tool that bridges the Hermes agent to Mnemosyne.
Covers: handler, schema, check_fn, state persistence, error handling.

Run:
    cd ~/.hermes/workspace/mnemosyne-dev
    python3 tests/test_vault_tool.py
"""

import sys
import os
import json
import tempfile
import shutil
from pathlib import Path

# Add paths for imports
MNEMOSYNE_SRC = Path(__file__).parent.parent / "src"
EXTERNAL_TOOLS = Path.home() / ".hermes" / "external_tools"

sys.path.insert(0, str(MNEMOSYNE_SRC))
sys.path.insert(0, str(EXTERNAL_TOOLS))

# Import vault tool
from vault_tool import vault_tool, check_vault_requirements, VAULT_SCHEMA


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def ok(self, name):
        self.passed += 1
        print(f"  ✓ {name}")
    
    def fail(self, name, msg):
        self.failed += 1
        self.errors.append((name, msg))
        print(f"  ✗ {name}: {msg}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed")
        if self.errors:
            print(f"\nFailures:")
            for name, msg in self.errors:
                print(f"  - {name}: {msg}")
        return self.failed == 0


def test_requirements(r):
    """Test 1: Requirements check"""
    print("\n[1] Requirements Check")
    
    result = check_vault_requirements()
    if result:
        r.ok("check_vault_requirements() returns True")
    else:
        r.fail("check_vault_requirements()", "Returned False — vault modules not found")


def test_schema(r):
    """Test 2: Schema validation"""
    print("\n[2] Schema Validation")
    
    if VAULT_SCHEMA.get("name") == "vault":
        r.ok("Schema name is 'vault'")
    else:
        r.fail("Schema name", f"Expected 'vault', got '{VAULT_SCHEMA.get('name')}'")
    
    if "description" in VAULT_SCHEMA and len(VAULT_SCHEMA["description"]) > 100:
        r.ok(f"Schema description present ({len(VAULT_SCHEMA['description'])} chars)")
    else:
        r.fail("Schema description", "Missing or too short")
    
    params = VAULT_SCHEMA.get("parameters", {}).get("properties", {})
    if "action" in params:
        r.ok("Schema has 'action' parameter")
    else:
        r.fail("Schema action param", "Missing")
    
    actions = params.get("action", {}).get("enum", [])
    expected_actions = {"enter", "status", "search", "drill", "up", 
                        "get", "decision", "synthesize", "layers", "state", "init"}
    if set(actions) == expected_actions:
        r.ok(f"All {len(actions)} actions defined in schema")
    else:
        missing = expected_actions - set(actions)
        extra = set(actions) - expected_actions
        r.fail("Schema actions", f"Missing: {missing}, Extra: {extra}")
    
    required = VAULT_SCHEMA.get("parameters", {}).get("required", [])
    if "action" in required:
        r.ok("'action' is required parameter")
    else:
        r.fail("Required params", "'action' not in required")


def test_enter_project(r):
    """Test 3: Enter project"""
    print("\n[3] Enter Project")
    
    result = vault_tool(action="enter", project="eeg")
    
    if "Entered project: eeg" in result:
        r.ok("enter eeg succeeds")
    else:
        r.fail("enter eeg", f"Unexpected result: {result[:80]}")
    
    if "L1" in result and "L2" in result and "L3" in result and "L4" in result:
        r.ok("All 4 layers shown in enter output")
    else:
        r.fail("Layer display", "Not all layers shown")


def test_status(r):
    """Test 4: Status"""
    print("\n[4] Status")
    
    result = vault_tool(action="status")
    
    if "Project:" in result:
        r.ok("Status shows project name")
    else:
        r.fail("Status project", "No project shown")
    
    if "Health:" in result:
        r.ok("Status shows health")
    else:
        r.fail("Status health", "No health shown")
    
    if "Phase:" in result:
        r.ok("Status shows phase")
    else:
        r.fail("Status phase", "No phase shown")


def test_search(r):
    """Test 5: Search"""
    print("\n[5] Search")
    
    result = vault_tool(action="search", query="gold oxidation")
    
    if "Found" in result and "results" in result:
        r.ok("Search returns results")
    else:
        r.fail("Search results", f"Unexpected: {result[:80]}")
    
    # Search with no query
    result = vault_tool(action="search")
    if "Usage:" in result:
        r.ok("Search without query returns usage hint")
    else:
        r.fail("Search no query", "Should return usage hint")


def test_drill_and_up(r):
    """Test 6: Drill and Up navigation"""
    print("\n[6] Drill and Up")
    
    # Drill down
    result = vault_tool(action="drill")
    if "L2" in result or "Cannot drill" in result:
        r.ok("Drill down works")
    else:
        r.fail("Drill down", f"Unexpected: {result[:80]}")
    
    # Go back up
    result = vault_tool(action="up")
    if "L1" in result or "Cannot go higher" in result:
        r.ok("Up navigation works")
    else:
        r.fail("Up navigation", f"Unexpected: {result[:80]}")


def test_layers(r):
    """Test 7: Layers"""
    print("\n[7] Layers")
    
    result = vault_tool(action="layers")
    
    if "L1" in result and "SURFACE" in result:
        r.ok("Layers shows L1")
    else:
        r.fail("Layers L1", "L1 not shown")
    
    if "L4" in result and "DETERMINANTS" in result:
        r.ok("Layers shows L4")
    else:
        r.fail("Layers L4", "L4 not shown")


def test_state(r):
    """Test 8: State persistence"""
    print("\n[8] State")
    
    result = vault_tool(action="state")
    
    try:
        state = json.loads(result)
        if "project" in state and "layer" in state:
            r.ok("State returns valid JSON with project and layer")
        else:
            r.fail("State fields", f"Missing fields: {state}")
    except json.JSONDecodeError:
        r.fail("State JSON", "Not valid JSON")


def test_decision(r):
    """Test 9: Decision logging"""
    print("\n[9] Decision Logging")
    
    result = vault_tool(action="decision", text="Test decision from vault_tool tests")
    
    if "Decision logged" in result or "decision" in result.lower():
        r.ok("Decision logging works")
    else:
        r.fail("Decision logging", f"Unexpected: {result[:80]}")
    
    # Missing text
    result = vault_tool(action="decision")
    if "Usage:" in result:
        r.ok("Decision without text returns usage hint")
    else:
        r.fail("Decision no text", "Should return usage hint")


def test_error_handling(r):
    """Test 10: Error handling"""
    print("\n[10] Error Handling")
    
    # Unknown action
    result = vault_tool(action="nonexistent")
    if "Unknown action" in result and "Valid actions" in result:
        r.ok("Unknown action returns error with valid list")
    else:
        r.fail("Unknown action", f"Unexpected: {result[:80]}")
    
    # Enter without project
    result = vault_tool(action="enter")
    if "Usage:" in result:
        r.ok("Enter without project returns usage hint")
    else:
        r.fail("Enter no project", "Should return usage hint")
    
    # Get without target
    result = vault_tool(action="get")
    if "Usage:" in result:
        r.ok("Get without target returns usage hint")
    else:
        r.fail("Get no target", "Should return usage hint")


def test_state_file(r):
    """Test 11: State file persistence"""
    print("\n[11] State File Persistence")
    
    state_file = Path.home() / ".hermes" / "memory" / ".vault_state.json"
    
    if state_file.exists():
        r.ok("State file exists after operations")
        
        try:
            state = json.loads(state_file.read_text())
            if "project" in state and "layer" in state:
                r.ok("State file has correct structure")
            else:
                r.fail("State file structure", f"Missing fields: {state}")
        except json.JSONDecodeError:
            r.fail("State file JSON", "Not valid JSON")
    else:
        r.fail("State file", "File not created")


def main():
    print("=" * 60)
    print("Vault Tool Test Suite — Phase 1")
    print("=" * 60)
    
    r = TestResult()
    
    # Run all tests
    test_requirements(r)
    test_schema(r)
    test_enter_project(r)
    test_status(r)
    test_search(r)
    test_drill_and_up(r)
    test_layers(r)
    test_state(r)
    test_decision(r)
    test_error_handling(r)
    test_state_file(r)
    
    # Summary
    success = r.summary()
    
    if success:
        print("\n✓ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n✗ {r.failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())

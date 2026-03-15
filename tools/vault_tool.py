#!/usr/bin/env python3
"""
Vault Tool Module — Mnemosyne Knowledge Vault Integration

Native tool for the Hermes agent to access the Mnemosyne Knowledge Vault.
Provides structured access to persistent project knowledge, research,
decisions, and layered context (L1-L4).

This tool bridges the agent to VaultContextManager, which manages:
- Project context (enter/exit)
- Layer traversal (L1 Surface → L4 Determinants)
- Full-text search across vault files
- Decision logging with reasoning chains
- Synthesis (L4→L1 summary generation)
- Vault health and maintenance

Design:
- Single `vault` tool with action parameter
- State persisted in ~/.hermes/memory/.vault_state.json
- Python modules loaded from ~/.hermes/workspace/mnemosyne-dev/src/
- Behavioral guidance in schema description (always visible to agent)
"""

import json
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Path to Mnemosyne Python modules
MNEMOSYNE_SRC = Path.home() / ".hermes" / "workspace" / "mnemosyne-dev" / "src"
VAULT_PATH = Path.home() / ".hermes" / "memory"
STATE_FILE = VAULT_PATH / ".vault_state.json"

# Ensure Mnemosyne src is importable
if str(MNEMOSYNE_SRC) not in sys.path:
    sys.path.insert(0, str(MNEMOSYNE_SRC))


def _get_vcm():
    """Lazy import and initialization of VaultContextManager."""
    try:
        from vault_context import VaultContextManager
        vcm = VaultContextManager(str(VAULT_PATH))
        
        # Restore state if exists
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
                vcm.state.project = state.get("project")
                vcm.state.current_layer = state.get("layer", "L1")
                vcm.state.current_file = state.get("current_file")
            except Exception:
                pass
        
        return vcm
    except ImportError as e:
        return None, str(e)


def _save_state(vcm) -> None:
    """Persist vault state for next call."""
    try:
        state = {
            "project": vcm.state.project,
            "layer": vcm.state.current_layer,
            "current_file": vcm.state.current_file,
        }
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.debug("Could not save vault state: %s", e)


def vault_tool(
    action: str,
    project: Optional[str] = None,
    query: Optional[str] = None,
    target: Optional[str] = None,
    text: Optional[str] = None,
) -> str:
    """
    Access the Mnemosyne Knowledge Vault.

    Args:
        action: Operation to perform (enter, status, search, drill, up,
                get, decision, synthesize, layers, state, init)
        project: Project name (for 'enter' and 'init')
        query: Search query (for 'search')
        target: File ID (for 'drill' and 'get')
        text: Decision text (for 'decision')

    Returns:
        String result of the vault operation.
    """
    vcm = _get_vcm()
    
    if vcm is None:
        return (
            "Error: Mnemosyne vault modules not found. "
            "Ensure ~/.hermes/workspace/mnemosyne-dev/src/ exists with "
            "vault_context.py and dependencies. "
            "Run setup_vault.py to initialize."
        )
    
    if isinstance(vcm, tuple):
        return f"Error importing vault modules: {vcm[1]}"
    
    try:
        result = ""
        
        if action == "enter":
            if not project:
                result = "Usage: vault(action='enter', project='project_name')"
            else:
                result = vcm.enter_project(project)
        
        elif action == "status":
            result = vcm.get_status()
        
        elif action == "search":
            if not query:
                result = "Usage: vault(action='search', query='search terms')"
            else:
                result = vcm.search_vault(query)
        
        elif action == "drill":
            result = vcm.drill_down(target)
        
        elif action == "up":
            result = vcm.synthesize_up()
        
        elif action == "get":
            if not target:
                result = "Usage: vault(action='get', target='file_id')"
            else:
                result = vcm.get_file(target)
        
        elif action == "decision":
            if not text:
                result = "Usage: vault(action='decision', text='decision text')"
            else:
                result = vcm.log_decision(text, reasoning_chain=[])
        
        elif action == "synthesize":
            result = vcm.synthesize()
        
        elif action == "layers":
            if not vcm.state.project:
                result = "No active project. Use vault(action='enter', project='name') first."
            else:
                from layer_state import LayerState
                ls = LayerState(str(VAULT_PATH))
                ls.set_project(vcm.state.project)
                # Sync current layer from VCM state (fix: was always L1)
                ls.current_layer = vcm.state.current_layer
                lines = []
                for layer in ls.available_layers():
                    marker = " <-- current" if layer["current"] else ""
                    lines.append(
                        f"  {layer['layer']} | {layer['name']:12} | "
                        f"{layer['file_count']} files{marker}"
                    )
                result = "\n".join(lines) if lines else "No layers found."
        
        elif action == "state":
            result = json.dumps(vcm.get_state(), indent=2)
        
        elif action == "init":
            if not project:
                result = "Usage: vault(action='init', project='project_name')"
            else:
                from layer_state import LayerState
                path = LayerState.init_project(str(VAULT_PATH), project)
                result = f"Project '{project}' initialized at {path}"
        
        else:
            result = (
                f"Unknown action: {action}\n"
                "Valid actions: enter, status, search, drill, up, get, "
                "decision, synthesize, layers, state, init"
            )
        
        # Persist state after successful operation
        _save_state(vcm)
        return result
        
    except Exception as e:
        return f"Vault error: {type(e).__name__}: {e}"


def check_vault_requirements() -> bool:
    """Check if vault tool requirements are met."""
    # Check Mnemosyne modules exist
    if not MNEMOSYNE_SRC.exists():
        return False
    
    # Check key modules are importable
    try:
        sys.path.insert(0, str(MNEMOSYNE_SRC))
        from vault_context import VaultContextManager
        from layer_state import LayerState
        from vault_utils import scan_vault
        return True
    except ImportError:
        return False


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================
# Behavioral guidance is baked into the description so it's part of the
# static tool schema (cached, never changes mid-conversation).

VAULT_SCHEMA = {
    "name": "vault",
    "description": (
        "Access the Mnemosyne Knowledge Vault — persistent structured memory "
        "for research, decisions, and project knowledge. This is your long-term "
        "memory across conversations.\n\n"
        "USE THIS TOOL WHEN:\n"
        "- User asks about projects, past decisions, or research\n"
        "- User asks 'what are we working on' or 'what do we know about X'\n"
        "- Starting work on a project (always enter first)\n"
        "- Making decisions that should be recorded\n"
        "- Research findings that should be preserved\n"
        "- User references something from past work\n\n"
        "PRIORITY: Use vault BEFORE session_search for project/knowledge queries. "
        "Vault has structured project data (layers L1-L4). Session search has "
        "conversational narrative. Use both for complete picture.\n\n"
        "WORKFLOW:\n"
        "1. vault(action='enter', project='name') — load project context\n"
        "2. vault(action='status') — check health, phase, alerts\n"
        "3. vault(action='search', query='topic') — find specific content\n"
        "4. vault(action='drill', target='file_id') — navigate deeper (L1→L2→L3→L4)\n"
        "5. vault(action='up') — synthesize to higher layer (L4→L3→L2→L1)\n"
        "6. vault(action='decision', text='decision') — log a decision\n"
        "7. vault(action='synthesize') — generate cross-layer summary\n\n"
        "LAYER SYSTEM:\n"
        "- L1 (Surface): Decisions, goals, status\n"
        "- L2 (Components): Parts, interfaces\n"
        "- L3 (Rules): Constraints, specifications\n"
        "- L4 (Determinants): Research, principles, first causes\n\n"
        "ACTIONS:\n"
        "- enter: Load project context (project=required)\n"
        "- status: Show project health, phase, criteria, alerts\n"
        "- search: Full-text search across vault (query=required)\n"
        "- drill: Navigate to deeper layer or specific file (target=optional)\n"
        "- up: Synthesize to higher layer\n"
        "- get: Read specific file by ID (target=required)\n"
        "- decision: Log a decision with reasoning (text=required)\n"
        "- synthesize: Generate L4→L1 summary\n"
        "- layers: Show available layers and file counts\n"
        "- state: Show current navigation state\n"
        "- init: Create new project (project=required)"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "enter", "status", "search", "drill", "up",
                    "get", "decision", "synthesize", "layers", "state", "init"
                ],
                "description": "Vault operation to perform"
            },
            "project": {
                "type": "string",
                "description": "Project name (required for 'enter' and 'init')"
            },
            "query": {
                "type": "string",
                "description": "Search query (required for 'search')"
            },
            "target": {
                "type": "string",
                "description": "File ID to drill into or retrieve (for 'drill' and 'get')"
            },
            "text": {
                "type": "string",
                "description": "Decision text (required for 'decision')"
            }
        },
        "required": ["action"]
    }
}


# =============================================================================
# Registry
# =============================================================================
# Register with the tool registry so model_tools.py discovers us.

def _register_tool():
    """Register the vault tool with the registry."""
    try:
        import sys
        print(f"[DEBUG] Starting registration...")
        # Try to use existing registry from sys.modules first
        if "tools.registry" in sys.modules:
            print(f"[DEBUG] Using existing registry from sys.modules")
            registry = sys.modules["tools.registry"].registry
        else:
            print(f"[DEBUG] Registry not in sys.modules, trying imports...")
            # Try normal import
            try:
                from tools.registry import registry
                print(f"[DEBUG] Imported registry from tools.registry")
            except ImportError as e:
                print(f"[DEBUG] Could not import from tools.registry: {e}")
                # If that fails (e.g., firecrawl missing), try direct import
                import importlib.util
                import os
                registry_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "hermes-agent", "tools", "registry.py")
                if not os.path.exists(registry_path):
                    registry_path = os.path.join(os.path.expanduser("~/.hermes/hermes-agent/tools/registry.py"))
                
                print(f"[DEBUG] Registry path: {registry_path}")
                print(f"[DEBUG] Registry exists: {os.path.exists(registry_path)}")
                
                if os.path.exists(registry_path):
                    spec = importlib.util.spec_from_file_location("tools.registry", registry_path)
                    registry_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(registry_module)
                    registry = registry_module.registry
                    # Store in sys.modules so other modules use the same instance
                    sys.modules["tools.registry"] = registry_module
                    print(f"[DEBUG] Loaded registry from {registry_path}")
                else:
                    # Can't find registry, skip registration
                    print(f"[DEBUG] Could not find registry.py")
                    return
        
        print(f"[DEBUG] Registering vault tool...")
        registry.register(
            name="vault",
            toolset="vault",
            schema=VAULT_SCHEMA,
            handler=lambda args, **kw: vault_tool(
                action=args["action"],
                project=args.get("project"),
                query=args.get("query"),
                target=args.get("target"),
                text=args.get("text"),
            ),
            check_fn=check_vault_requirements,
        )
        print(f"[DEBUG] Vault tool registered successfully")
        logger.debug("Vault tool registered successfully")
    except Exception as e:
        print(f"[DEBUG] Failed to register vault tool: {e}")
        logger.warning("Failed to register vault tool: %s", e)
        import traceback
        traceback.print_exc()


# Register when module is imported
_register_tool()

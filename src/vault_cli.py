#!/usr/bin/env python3
"""
Vault CLI — Agent-facing commands for Mnemosyne Knowledge Vault.

Provides simple CLI commands the agent can use via terminal tool:
  vault <command> [args]

Commands:
  enter <project>     — Enter project context
  status              — Show project status
  drill [file_id]     — Drill down (to file or next layer)
  up                  — Synthesize up one layer
  search <query>      — Search vault
  get <file_id>       — Get file content
  decision <text>     — Log a decision
  check <area> <action> — Check authorization
  synthesize          — Run synthesis pipeline
  state               — Show current state
  prompt [project]    — Build vault context for prompt
  layers              — Show layer overview
  maintenance         — Run vault health check
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vault_context import VaultContextManager


def main():
    vault_path = os.path.expanduser("~/.hermes/memory")
    vcm = VaultContextManager(vault_path)

    # Load state from .vault_state.json (shared with vault_tool.py)
    state_file = Path(vault_path) / ".vault_state.json"
    if state_file.exists():
        try:
            import json
            state = json.loads(state_file.read_text())
            vcm.state.project = state.get("project")
            vcm.state.current_layer = state.get("layer", "L1")
            vcm.state.current_file = state.get("current_file")
        except Exception:
            pass

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    args = sys.argv[2:]

    # Dispatch commands
    if cmd == "enter":
        if not args:
            print("Usage: vault enter <project>")
            return
        project = args[0]
        # Check if project exists, create if not
        project_path = Path(vault_path) / "projects" / project
        if not project_path.exists():
            from layer_state import LayerState
            LayerState.init_project(vault_path, project)
            print(f"Created new project: {project}\n")
        print(vcm.enter_project(project))

    elif cmd == "init":
        if not args:
            print("Usage: vault init <project>")
            return
        from layer_state import LayerState
        path = LayerState.init_project(vault_path, args[0])
        print(f"Project '{args[0]}' initialized at {path}")
        print(f"\nNext steps:")
        print(f"  1. Edit {path}/_overview.md with your project goals")
        print(f"  2. vault enter {args[0]}")

    elif cmd == "status":
        print(vcm.get_status())

    elif cmd == "drill":
        target = args[0] if args else None
        print(vcm.drill_down(target))

    elif cmd == "up":
        print(vcm.synthesize_up())

    elif cmd == "search":
        if not args:
            print("Usage: vault search <query>")
            return
        print(vcm.search_vault(" ".join(args)))

    elif cmd == "get":
        if not args:
            print("Usage: vault get <file_id>")
            return
        print(vcm.get_file(args[0]))

    elif cmd == "decision":
        if not args:
            print("Usage: vault decision <text>")
            return
        print(vcm.log_decision(" ".join(args), reasoning_chain=[]))

    elif cmd == "check":
        area = args[0] if args else "research"
        action = " ".join(args[1:]) if len(args) > 1 else "explore"
        print(vcm.check_authority(area, action))

    elif cmd == "synthesize":
        print(vcm.synthesize())

    elif cmd == "state":
        import json
        print(json.dumps(vcm.get_state(), indent=2))

    elif cmd == "prompt":
        project = args[0] if args else None
        topic = " ".join(args[1:]) if len(args) > 1 else None
        print(vcm.build_prompt_section(project=project, topic=topic))

    elif cmd == "layers":
        if not vcm.state.project:
            print("No active project. Use 'vault enter <project>' first.")
            return
        from layer_state import LayerState
        ls = LayerState(vault_path)
        ls.set_project(vcm.state.project)
        for layer in ls.available_layers():
            marker = " <-- current" if layer["current"] else ""
            print(f"  {layer['layer']} | {layer['name']:12} | {layer['file_count']} files{marker}")

    elif cmd == "maintenance":
        from maintenance import VaultMaintainer
        maint = VaultMaintainer(vault_path)
        report = maint.run_maintenance()
        print(f"Health: {report.health_score:.0%}")
        print(f"Files: {report.files_scanned}, Issues: {report.issues_found}")
        if report.errors:
            print(f"Errors ({len(report.errors)}):")
            for e in report.errors[:5]:
                print(f"  {e.file_id}: {e.message}")
        if report.warnings:
            print(f"Warnings ({len(report.warnings)}):")
            for w in report.warnings[:5]:
                print(f"  {w.file_id}: {w.message}")

    else:
        print(__doc__)

    # Save state after operation (shared with vault_tool.py)
    try:
        import json
        state_data = {
            "project": vcm.state.project,
            "layer": vcm.state.current_layer,
            "current_file": vcm.state.current_file,
        }
        state_file.write_text(json.dumps(state_data, indent=2))
    except Exception:
        pass


if __name__ == "__main__":
    main()

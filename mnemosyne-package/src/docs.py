#!/usr/bin/env python3
"""
Documentation Generator for Mnemosyne Knowledge Vault.

Generates project documentation from vault content:
  - Project README from L1 overview + synthesis
  - API reference from module docstrings
  - Architecture overview from vault structure
  - Usage guide from templates

Usage:
    from docs import DocGenerator

    docs = DocGenerator(vault_path="~/.hermes/memory", src_path="path/to/src")
    
    # Generate project README
    docs.generate_project_readme("eeg")
    
    # Generate API reference
    docs.generate_api_reference()
    
    # Generate full documentation
    docs.generate_all()
"""

import os
import re
import inspect
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from vault_utils import scan_vault, read_vault_file, find_by_project


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class ModuleDoc:
    """Documentation for a single module."""
    name: str
    path: str
    description: str
    classes: List[Dict]  # {name, description, methods}
    functions: List[Dict]  # {name, description, params}
    cli_commands: List[str]


@dataclass
class ProjectDoc:
    """Documentation for a vault project."""
    project: str
    overview: str
    phase: str
    health: str
    criteria: List[str]
    components: List[str]
    rules: List[str]
    research: List[str]
    decisions: List[str]


# ─── Documentation Generator ──────────────────────────────────────

class DocGenerator:
    """
    Generates documentation from vault content and source code.

    Produces:
    - Project README.md from vault files
    - API reference from Python docstrings
    - Architecture overview
    - Usage guide
    """

    def __init__(
        self,
        vault_path: str = "~/.hermes/memory",
        src_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ):
        self.vault_path = os.path.expanduser(vault_path)
        self.src_path = src_path or str(Path(__file__).parent)
        self.output_path = output_path or str(Path(self.vault_path) / "docs")

    def generate_project_readme(
        self,
        project: str,
        output_file: Optional[str] = None,
    ) -> str:
        """
        Generate README.md for a project from vault files.

        Combines L1 overview, synthesis, and layer summaries.
        """
        files = find_by_project(project, self.vault_path)

        # Collect content by layer
        overview_content = ""
        synthesis_content = ""
        components = []
        rules = []
        research = []
        decisions = []

        for meta in files:
            path = meta.get("_path", "")
            if not path or not os.path.exists(path):
                continue

            try:
                fm, body = read_vault_file(path)
            except Exception:
                continue

            layer = fm.get("layer", "cross")
            ftype = fm.get("type", "unknown")
            file_id = fm.get("id", meta.get("_filename", ""))

            if file_id == "_overview":
                overview_content = body
            elif file_id == "_synthesis":
                synthesis_content = body
            elif layer == "L2":
                components.append({"id": file_id, "content": body[:200]})
            elif layer == "L3":
                rules.append({"id": file_id, "content": body[:200]})
            elif layer == "L4":
                research.append({"id": file_id, "content": body[:200]})
            elif ftype == "decision":
                decisions.append({"id": file_id, "content": body[:200]})

        # Generate README
        today = datetime.now().strftime("%Y-%m-%d")
        lines = []

        lines.append(f"# {project.upper()} — Project Documentation")
        lines.append("")
        lines.append(f"_Auto-generated from Mnemosyne vault on {today}_")
        lines.append("")

        # Extract summary from overview
        if overview_content:
            summary_match = re.search(r'## Summary\s*\n(.*?)(?=\n## |\Z)', overview_content, re.DOTALL)
            if summary_match:
                lines.append("## Overview")
                lines.append(summary_match.group(1).strip())
                lines.append("")

        # Extract objective
        if overview_content:
            obj_match = re.search(r'### Objective\s*\n(.*?)(?=\n### |\n## |\Z)', overview_content, re.DOTALL)
            if obj_match:
                lines.append("## Objective")
                lines.append(obj_match.group(1).strip())
                lines.append("")

        # Success criteria
        if overview_content:
            criteria_match = re.search(r'### Success Criteria\s*\n(.*?)(?=\n### |\n## |\Z)', overview_content, re.DOTALL)
            if criteria_match:
                lines.append("## Success Criteria")
                lines.append(criteria_match.group(1).strip())
                lines.append("")

        # Components
        if components:
            lines.append("## Components")
            for comp in components:
                lines.append(f"### [[{comp['id']}]]")
                lines.append(comp['content'][:150])
                lines.append("")

        # Rules
        if rules:
            lines.append("## Rules & Constraints")
            for rule in rules:
                lines.append(f"### [[{rule['id']}]]")
                lines.append(rule['content'][:150])
                lines.append("")

        # Research
        if research:
            lines.append("## Research")
            for res in research:
                lines.append(f"### [[{res['id']}]]")
                lines.append(res['content'][:150])
                lines.append("")

        # Decisions
        if decisions:
            lines.append("## Key Decisions")
            for dec in decisions:
                lines.append(f"- [[{dec['id']}]]")

        # Synthesis
        if synthesis_content:
            lines.append("")
            lines.append("## Synthesis")
            summary_match = re.search(r'## Summary\s*\n(.*?)(?=\n## |\Z)', synthesis_content, re.DOTALL)
            if summary_match:
                lines.append(summary_match.group(1).strip())

        readme = "\n".join(lines)

        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_text(readme, encoding="utf-8")

        return readme

    def generate_api_reference(self, output_file: Optional[str] = None) -> str:
        """
        Generate API reference from source module docstrings.

        Scans all Python files in src/ and extracts class/function docs.
        """
        src_dir = Path(self.src_path)
        modules = []

        for py_file in sorted(src_dir.glob("*.py")):
            if py_file.name.startswith("_") or py_file.name == "docs.py":
                continue

            doc = self._parse_module(py_file)
            if doc:
                modules.append(doc)

        # Generate reference
        today = datetime.now().strftime("%Y-%m-%d")
        lines = []

        lines.append("# Mnemosyne API Reference")
        lines.append("")
        lines.append(f"_Auto-generated on {today}_")
        lines.append("")
        lines.append("## Modules")
        lines.append("")

        for mod in modules:
            lines.append(f"### {mod.name}")
            lines.append(f"_{mod.description}_")
            lines.append("")

            # Classes
            if mod.classes:
                for cls in mod.classes:
                    lines.append(f"#### `{cls['name']}`")
                    if cls.get("description"):
                        lines.append(cls["description"])
                        lines.append("")
                    if cls.get("methods"):
                        for method in cls["methods"]:
                            lines.append(f"- `{method['name']}()` — {method.get('description', '')}")
                        lines.append("")

            # Functions
            if mod.functions:
                lines.append("**Functions:**")
                for func in mod.functions:
                    params = ", ".join(func.get("params", []))
                    lines.append(f"- `{func['name']}({params})` — {func.get('description', '')}")
                lines.append("")

            # CLI
            if mod.cli_commands:
                lines.append("**CLI:** `python3 " + mod.name + ".py " + " | ".join(mod.cli_commands) + "`")
                lines.append("")

        reference = "\n".join(lines)

        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_text(reference, encoding="utf-8")

        return reference

    def generate_architecture_overview(self, output_file: Optional[str] = None) -> str:
        """Generate architecture overview from vault structure."""
        files = scan_vault(self.vault_path)
        today = datetime.now().strftime("%Y-%m-%d")

        # Count by layer/type
        by_layer: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_project: Dict[str, int] = {}

        for meta in files:
            layer = meta.get("layer", "cross")
            by_layer[layer] = by_layer.get(layer, 0) + 1

            ftype = meta.get("type", "unknown")
            by_type[ftype] = by_type.get(ftype, 0) + 1

            project = meta.get("project", "general")
            by_project[project] = by_project.get(project, 0) + 1

        lines = []
        lines.append("# Mnemosyne Architecture Overview")
        lines.append("")
        lines.append(f"_Generated: {today}_")
        lines.append("")
        lines.append("## Vault Structure")
        lines.append("")
        lines.append("```")
        lines.append("~/.hermes/memory/")
        lines.append("├── _index.md              # Navigation hub")
        lines.append("├── _inbox.md              # Quick captures")
        lines.append("├── projects/              # Per-project subgraphs")
        lines.append("│   └── <project>/")
        lines.append("│       ├── _overview.md   # L1: Intent, status")
        lines.append("│       ├── _synthesis.md  # Cross-layer summary")
        lines.append("│       ├── components/    # L2: Parts, interfaces")
        lines.append("│       ├── rules/         # L3: Constraints")
        lines.append("│       └── research/      # L4: Principles, papers")
        lines.append("├── concepts/              # Cross-project knowledge")
        lines.append("├── decisions/             # Decision audit trail")
        lines.append("├── user/                  # User model")
        lines.append("├── archive/               # Completed items")
        lines.append("├── attribution/           # Response source tracking")
        lines.append("├── context_audit/         # Context load logs")
        lines.append("└── trust/                 # Reliability scores")
        lines.append("```")
        lines.append("")

        lines.append("## Layer System")
        lines.append("")
        lines.append("| Layer | Name | Purpose | Files |")
        lines.append("|-------|------|---------|-------|")
        for layer in ["L1", "L2", "L3", "L4", "cross"]:
            count = by_layer.get(layer, 0)
            names = {"L1": "Surface", "L2": "Components", "L3": "Rules", "L4": "Research", "cross": "Cross-layer"}
            purposes = {
                "L1": "Decisions, goals, status",
                "L2": "Parts, interfaces, specs",
                "L3": "Constraints, thresholds",
                "L4": "Physics, research, principles",
                "cross": "Synthesis, concepts, context"
            }
            lines.append(f"| {layer} | {names.get(layer, '')} | {purposes.get(layer, '')} | {count} |")
        lines.append("")

        lines.append("## Projects")
        lines.append("")
        for proj, count in sorted(by_project.items()):
            if proj != "general":
                lines.append(f"- **{proj}**: {count} files")
        lines.append("")

        lines.append("## Source Modules")
        lines.append("")
        src_dir = Path(self.src_path)
        for py_file in sorted(src_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            # Get first docstring line
            try:
                content = py_file.read_text(encoding="utf-8")
                doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
                desc = doc_match.group(1).strip().split("\n")[0] if doc_match else ""
                size = py_file.stat().st_size
                lines.append(f"- **{py_file.name}** ({size/1024:.1f}KB) — {desc}")
            except Exception:
                pass

        overview = "\n".join(lines)

        if output_file:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_text(overview, encoding="utf-8")

        return overview

    def generate_all(self) -> List[str]:
        """Generate all documentation files."""
        output_dir = Path(self.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        generated = []

        # API reference
        api_path = output_dir / "API_REFERENCE.md"
        self.generate_api_reference(str(api_path))
        generated.append(str(api_path))

        # Architecture
        arch_path = output_dir / "ARCHITECTURE.md"
        self.generate_architecture_overview(str(arch_path))
        generated.append(str(arch_path))

        # Project READMEs
        files = scan_vault(self.vault_path)
        projects = set()
        for meta in files:
            proj = meta.get("project")
            if proj and proj != "general":
                projects.add(proj)

        for project in projects:
            readme_path = output_dir / f"README_{project}.md"
            self.generate_project_readme(project, str(readme_path))
            generated.append(str(readme_path))

        return generated

    # ─── Module Parser ────────────────────────────────────────────

    def _parse_module(self, path: Path) -> Optional[ModuleDoc]:
        """Parse a Python module for documentation."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Module docstring
        doc_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        description = doc_match.group(1).strip().split("\n")[0] if doc_match else ""

        # Classes
        classes = []
        for cls_match in re.finditer(r'class\s+(\w+).*?:\s*"""(.*?)"""', content, re.DOTALL):
            cls_name = cls_match.group(1)
            cls_doc = cls_match.group(2).strip()

            # Find methods
            methods = []
            cls_body = content[cls_match.end():]
            for method_match in re.finditer(r'def\s+(\w+)\(self.*?\).*?:\s*(?:"""(.*?)""")?', cls_body[:2000], re.DOTALL):
                methods.append({
                    "name": method_match.group(1),
                    "description": (method_match.group(2) or "").strip().split("\n")[0],
                })

            classes.append({
                "name": cls_name,
                "description": cls_doc.split("\n")[0],
                "methods": methods[:10],
            })

        # Top-level functions
        functions = []
        for func_match in re.finditer(r'^def\s+(\w+)\((.*?)\).*?:\s*(?:"""(.*?)""")?', content, re.MULTILINE | re.DOTALL):
            func_name = func_match.group(1)
            if func_name.startswith("_"):
                continue
            params = [p.strip().split(":")[0].split("=")[0] for p in func_match.group(2).split(",") if p.strip() and p.strip() != "self"]
            params = [p for p in params if p and not p.startswith("*")]

            functions.append({
                "name": func_name,
                "description": (func_match.group(3) or "").strip().split("\n")[0],
                "params": params[:5],
            })

        # CLI commands
        cli_commands = []
        cli_match = re.search(r'if\s+__name__\s*==.*?cmd\s*=\s*sys\.argv\[1\].*?if\s+cmd\s*==\s*["\'](\w+)["\']', content, re.DOTALL)
        if cli_match:
            for cmd in re.findall(r'elif\s+cmd\s*==\s*["\'](\w+)["\']', content):
                cli_commands.append(cmd)

        return ModuleDoc(
            name=path.stem,
            path=str(path),
            description=description,
            classes=classes[:5],
            functions=functions[:10],
            cli_commands=cli_commands[:10],
        )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    src = str(Path(__file__).parent)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    docs = DocGenerator(vault_path=vault, src_path=src)

    if cmd == "project":
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if not project:
            print("Usage: docs.py project <project_name>")
            sys.exit(1)
        readme = docs.generate_project_readme(project)
        print(readme[:1000])

    elif cmd == "api":
        ref = docs.generate_api_reference()
        print(ref[:1000])

    elif cmd == "arch":
        overview = docs.generate_architecture_overview()
        print(overview[:1000])

    elif cmd == "all":
        generated = docs.generate_all()
        print(f"Generated {len(generated)} documentation files:")
        for g in generated:
            print(f"  {g}")

    else:
        print("Commands: project <name>, api, arch, all")

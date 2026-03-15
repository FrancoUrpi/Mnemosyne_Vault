#!/usr/bin/env python3
"""
Obsidian Compatibility Layer for Mnemosyne Knowledge Vault.

Ensures vault works seamlessly with Obsidian:
  - .obsidian directory setup
  - Graph view configuration
  - Template folder configuration
  - Frontmatter display settings
  - Plugin recommendations
  - Vault validation for Obsidian compatibility

Usage:
    from obsidian import ObsidianCompat

    compat = ObsidianCompat(vault_path="~/.hermes/memory")
    
    # Setup Obsidian config
    compat.setup()
    
    # Validate compatibility
    issues = compat.validate()
    
    # Generate graph-friendly index
    compat.generate_graph_index()
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from vault_utils import scan_vault, read_vault_file


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class ObsidianIssue:
    """An Obsidian compatibility issue."""
    severity: str  # "info", "warning", "error"
    category: str
    file_path: Optional[str]
    message: str
    fix_suggestion: str


@dataclass
class ObsidianConfig:
    """Obsidian vault configuration."""
    app_json: Dict
    appearance_json: Dict
    graph_json: Dict
    plugins_json: Dict
    workspace_json: Dict


# ─── Obsidian Compatibility ───────────────────────────────────────

class ObsidianCompat:
    """
    Obsidian compatibility layer for Mnemosyne vault.

    Ensures the vault works well when opened in Obsidian:
    - Configures .obsidian directory
    - Sets up graph view for link visualization
    - Configures templates folder
    - Validates file compatibility
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.obsidian_dir = Path(self.vault_path) / ".obsidian"

    def setup(self, templates_dir: str = "templates") -> None:
        """
        Setup Obsidian configuration.

        Creates .obsidian directory with recommended settings.
        """
        self.obsidian_dir.mkdir(parents=True, exist_ok=True)
        (self.obsidian_dir / "plugins").mkdir(exist_ok=True)

        # app.json - Core settings
        app_config = {
            "attachmentFolderPath": "attachments",
            "newFileLocation": "folder",
            "newFileFolderPath": "projects",
            "useMarkdownLinks": False,  # Use [[wiki-links]]
            "showFrontmatter": True,
            "alwaysUpdateLinks": True,
            "newLinkFormat": "shortest",
            "useTab": True,
            "tabSize": 4,
            "strictLineBreaks": False,
            "showLineNumber": True,
            "showUnsupportedFiles": False,
        }
        self._write_json(self.obsidian_dir / "app.json", app_config)

        # appearance.json
        appearance_config = {
            "accentColor": "#7c3aed",  # Purple (Mnemosyne theme)
            "theme": "obsidian",
            "translucency": False,
            "cssTheme": None,
        }
        self._write_json(self.obsidian_dir / "appearance.json", appearance_config)

        # graph.json - Graph view settings
        graph_config = {
            "collapse-filter": False,
            "search": "",
            "showTags": True,
            "showAttachments": False,
            "hideUnresolved": False,
            "showOrphans": True,
            "collapse-color-groups": False,
            "colorGroups": [
                {"query": "path:projects/eeg", "color": {"a": 1, "rgb": 3901635}},    # Blue
                {"query": "tag:research", "color": {"a": 1, "rgb": 10857855}},         # Purple
                {"query": "tag:decision", "color": {"a": 1, "rgb": 16739584}},         # Orange
                {"query": "path:concepts", "color": {"a": 1, "rgb": 3197040}},         # Green
            ],
            "collapse-display": False,
            "showArrow": True,
            "textFadeMultiplier": 0,
            "nodeSizeMultiplier": 1,
            "lineSizeMultiplier": 1,
            "collapse-forces": False,
            "centerStrength": 0.5,
            "repelStrength": 10,
            "linkStrength": 1,
            "linkDistance": 250,
            "scale": 1,
            "close": False,
        }
        self._write_json(self.obsidian_dir / "graph.json", graph_config)

        # workspace.json
        workspace_config = {
            "main": {
                "id": "mnemosyne-main",
                "type": "split",
                "children": [
                    {
                        "id": "mnemosyne-editor",
                        "type": "leaf",
                        "state": {"type": "markdown", "state": {"file": "_index.md"}}
                    }
                ],
                "direction": "vertical"
            },
            "left": {
                "id": "mnemosyne-left",
                "type": "split",
                "children": [
                    {
                        "id": "mnemosyne-files",
                        "type": "leaf",
                        "state": {"type": "file-explorer"}
                    }
                ],
                "direction": "horizontal",
                "collapsed": False
            },
            "right": {
                "id": "mnemosyne-right",
                "type": "split",
                "children": [
                    {
                        "id": "mnemosyne-graph",
                        "type": "leaf",
                        "state": {"type": "graph"}
                    },
                    {
                        "id": "mnemosyne-backlinks",
                        "type": "leaf",
                        "state": {"type": "backlink"}
                    }
                ],
                "direction": "horizontal",
                "collapsed": True
            },
            "active": "mnemosyne-editor",
            "lastOpenFiles": ["_index.md", "user/active_context.md"]
        }
        self._write_json(self.obsidian_dir / "workspace.json", workspace_config)

        # core-plugins.json
        core_plugins = {
            "file-explorer": True,
            "global-search": True,
            "switcher": True,
            "graph": True,
            "backlink": True,
            "outgoing-link": True,
            "tag-pane": True,
            "page-preview": True,
            "note-composer": True,
            "command-palette": True,
            "markdown-importer": True,
            "outline": True,
            "word-count": True,
            "open-with-default-app": True,
        }
        self._write_json(self.obsidian_dir / "core-plugins.json", core_plugins)

        # Templates config
        templates_config = {
            "templates": {
                "folder": templates_dir,
                "dateFormat": "YYYY-MM-DD",
                "timeFormat": "HH:mm",
            }
        }
        self._write_json(self.obsidian_dir / "templates.json", templates_config)

        # Create attachments folder
        (Path(self.vault_path) / "attachments").mkdir(exist_ok=True)

        # .obsidian/.gitignore
        gitignore = """# Obsidian workspace files (optional to commit)
workspace.json
workspace-mobile.json
"""
        (self.obsidian_dir / ".gitignore").write_text(gitignore, encoding="utf-8")

    def validate(self) -> List[ObsidianIssue]:
        """
        Validate vault for Obsidian compatibility.

        Returns list of issues found.
        """
        issues = []

        # Check .obsidian exists
        if not self.obsidian_dir.exists():
            issues.append(ObsidianIssue(
                severity="info",
                category="config",
                file_path=None,
                message=".obsidian directory not found",
                fix_suggestion="Run compat.setup() to create Obsidian config",
            ))

        # Check files
        files = scan_vault(self.vault_path)

        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue

            filename = Path(path).name

            # Check for problematic characters in filenames
            problematic = ['#', '^', '[', ']', '|', ':']
            for char in problematic:
                if char in filename:
                    issues.append(ObsidianIssue(
                        severity="warning",
                        category="filename",
                        file_path=path,
                        message=f"Filename contains '{char}' which may cause issues in Obsidian",
                        fix_suggestion=f"Rename file to remove '{char}'",
                    ))

            # Check for very long filenames
            if len(filename) > 200:
                issues.append(ObsidianIssue(
                    severity="warning",
                    category="filename",
                    file_path=path,
                    message="Filename is very long (>200 chars)",
                    fix_suggestion="Shorten the filename",
                ))

            # Check frontmatter
            try:
                fm, body = read_vault_file(path)
                if not fm:
                    issues.append(ObsidianIssue(
                        severity="info",
                        category="frontmatter",
                        file_path=path,
                        message="No YAML frontmatter — Obsidian may not display metadata",
                        fix_suggestion="Add ---\nid: ...\n--- frontmatter",
                    ))
            except Exception as e:
                issues.append(ObsidianIssue(
                    severity="error",
                    category="parse",
                    file_path=path,
                    message=f"Failed to parse: {e}",
                    fix_suggestion="Check file encoding and format",
                ))

        # Check attachments directory
        attachments = Path(self.vault_path) / "attachments"
        if not attachments.exists():
            issues.append(ObsidianIssue(
                severity="info",
                category="config",
                file_path=None,
                message="No attachments/ directory",
                fix_suggestion="Create attachments/ for embedded files",
            ))

        return issues

    def generate_graph_index(self) -> None:
        """
        Generate/update the _index.md file optimized for Obsidian graph view.

        Creates links to all projects and key files for better visualization.
        """
        files = scan_vault(self.vault_path)
        today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

        # Collect projects
        projects: Dict[str, List[Dict]] = {}
        concepts: List[Dict] = []

        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue
            if "/archive/" in path:
                continue

            project = meta.get("project", "general")
            file_id = meta.get("_filename", "")
            layer = meta.get("layer", "cross")
            ftype = meta.get("type", "unknown")

            if project == "general" and ftype == "concept":
                concepts.append({"id": file_id, "layer": layer})
            elif project != "general" and file_id == "_overview":
                if project not in projects:
                    projects[project] = []
                projects[project].append({"id": file_id, "layer": "L1"})

        # Build index
        lines = []
        lines.append("---")
        lines.append("id: _index")
        lines.append("type: index")
        lines.append("layer: cross")
        lines.append(f"updated: {today}")
        lines.append("---")
        lines.append("")
        lines.append("# Mnemosyne Vault")
        lines.append("")
        lines.append("## Projects")

        for proj, files_list in sorted(projects.items()):
            lines.append(f"- [[_overview|{proj}]]")

        lines.append("")
        lines.append("## Concepts")
        for c in concepts[:20]:
            lines.append(f"- [[{c['id']}]]")

        lines.append("")
        lines.append("## User")
        lines.append("- [[active_context|Current Context]]")
        lines.append("- [[preferences|Preferences]]")
        lines.append("")
        lines.append(f"_Updated: {today}_")

        index_path = Path(self.vault_path) / "_index.md"
        index_path.write_text("\n".join(lines), encoding="utf-8")

    def get_config(self) -> ObsidianConfig:
        """Get current Obsidian configuration."""
        def read_json(path: Path) -> Dict:
            if path.exists():
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return {}

        return ObsidianConfig(
            app_json=read_json(self.obsidian_dir / "app.json"),
            appearance_json=read_json(self.obsidian_dir / "appearance.json"),
            graph_json=read_json(self.obsidian_dir / "graph.json"),
            plugins_json=read_json(self.obsidian_dir / "core-plugins.json"),
            workspace_json=read_json(self.obsidian_dir / "workspace.json"),
        )

    def is_setup(self) -> bool:
        """Check if Obsidian config exists."""
        return self.obsidian_dir.exists() and (self.obsidian_dir / "app.json").exists()

    # ─── Internal ─────────────────────────────────────────────────

    def _write_json(self, path: Path, data: Dict) -> None:
        """Write JSON config file."""
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    compat = ObsidianCompat(vault)

    if cmd == "setup":
        compat.setup()
        print("Obsidian configuration created in .obsidian/")
        print("Open this folder in Obsidian to start using it.")

    elif cmd == "validate":
        issues = compat.validate()
        print(f"Obsidian compatibility: {len(issues)} issues")
        for i in issues:
            marker = {"error": "✗", "warning": "!", "info": "i"}[i.severity]
            print(f"  [{marker}] {i.category}: {i.message}")
            if i.file_path:
                print(f"       File: {i.file_path}")

    elif cmd == "index":
        compat.generate_graph_index()
        print("_index.md updated for graph view")

    elif cmd == "status":
        if compat.is_setup():
            config = compat.get_config()
            print("Obsidian: Configured")
            print(f"  Theme: {config.appearance_json.get('theme', 'default')}")
            print(f"  Wiki-links: {not config.app_json.get('useMarkdownLinks', True)}")
            print(f"  Graph colors: {len(config.graph_json.get('colorGroups', []))}")
        else:
            print("Obsidian: Not configured (run 'setup')")

    else:
        print("Commands: setup, validate, index, status")

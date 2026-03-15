#!/usr/bin/env python3
"""
Cross-Project Concept Extractor for Mnemosyne Knowledge Vault.

Identifies and manages shared knowledge across projects:
  - Concept detection (similar files across projects)
  - Shared tag analysis
  - Cross-project link discovery
  - Concept file generation in concepts/ directory
  - Project similarity scoring

Usage:
    from cross_project import CrossProjectAnalyzer

    analyzer = CrossProjectAnalyzer(vault_path="~/.hermes/memory")
    
    # Find shared concepts
    concepts = analyzer.find_shared_concepts()
    
    # Generate concept files
    analyzer.generate_concept_files(concepts)
    
    # Find project similarities
    similarities = analyzer.find_project_similarities()
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime

from vault_utils import (
    scan_vault, read_vault_file, extract_links,
    find_by_project, write_frontmatter
)


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class SharedConcept:
    """A concept shared across projects."""
    name: str
    tag: str  # The shared tag or term
    projects: List[str]
    file_count: int
    files: List[Dict]  # {file_id, project, layer}
    description: str = ""
    concept_file: Optional[str] = None


@dataclass
class ProjectSimilarity:
    """Similarity between two projects."""
    project_a: str
    project_b: str
    shared_tags: List[str]
    shared_concepts: int
    similarity_score: float  # 0.0 to 1.0
    shared_files: List[str]  # Concept file IDs


@dataclass
class CrossProjectReport:
    """Analysis report for cross-project knowledge."""
    timestamp: str
    project_count: int
    projects: List[str]
    shared_concepts: List[SharedConcept]
    similarities: List[ProjectSimilarity]
    orphan_tags: List[str]  # Tags in only one project
    concept_files_generated: int


# ─── Cross-Project Analyzer ───────────────────────────────────────

class CrossProjectAnalyzer:
    """
    Analyzes knowledge shared across projects.

    Finds common tags, similar content, and generates
    concept files in the concepts/ directory.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)
        self.concepts_dir = Path(self.vault_path) / "concepts"

    def find_shared_concepts(
        self,
        min_projects: int = 2,
    ) -> List[SharedConcept]:
        """
        Find concepts (tags/terms) shared across multiple projects.

        Args:
            min_projects: Minimum number of projects sharing a concept

        Returns:
            List of SharedConcept sorted by project count
        """
        files = scan_vault(self.vault_path)

        # Collect tags by project
        project_tags: Dict[str, Counter] = {}
        tag_files: Dict[str, List[Dict]] = {}

        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue
            if "/archive/" in path or "/user/" in path:
                continue

            project = meta.get("project", "general")
            tags = meta.get("tags", [])
            if not isinstance(tags, list):
                continue

            if project not in project_tags:
                project_tags[project] = Counter()

            for tag in tags:
                tag = tag.lower().strip()
                if tag:
                    project_tags[project][tag] += 1

                    if tag not in tag_files:
                        tag_files[tag] = []
                    tag_files[tag].append({
                        "file_id": meta.get("_filename", ""),
                        "project": project,
                        "layer": meta.get("layer", "cross"),
                        "type": meta.get("type", "unknown"),
                    })

        # Find tags shared across projects
        shared = []
        for tag, file_list in tag_files.items():
            projects = list(set(f["project"] for f in file_list))
            if len(projects) >= min_projects:
                shared.append(SharedConcept(
                    name=tag.replace("_", " ").title(),
                    tag=tag,
                    projects=projects,
                    file_count=len(file_list),
                    files=file_list,
                ))

        shared.sort(key=lambda c: len(c.projects), reverse=True)
        return shared

    def find_project_similarities(self) -> List[ProjectSimilarity]:
        """
        Calculate similarity between all project pairs.

        Uses shared tags as the similarity metric.
        """
        files = scan_vault(self.vault_path)

        # Collect tags per project
        project_tags: Dict[str, Set[str]] = {}
        for meta in files:
            path = meta.get("_path", "")
            if not path or "/archive/" in path or "/user/" in path:
                continue

            project = meta.get("project", "general")
            tags = meta.get("tags", [])
            if not isinstance(tags, list):
                continue

            if project not in project_tags:
                project_tags[project] = set()
            for tag in tags:
                if tag:
                    project_tags[project].add(tag.lower().strip())

        # Calculate pairwise similarities
        projects = [p for p in project_tags.keys() if p != "general"]
        similarities = []

        for i, proj_a in enumerate(projects):
            for proj_b in projects[i+1:]:
                tags_a = project_tags.get(proj_a, set())
                tags_b = project_tags.get(proj_b, set())

                shared = tags_a & tags_b
                union = tags_a | tags_b

                score = len(shared) / max(1, len(union))  # Jaccard similarity

                if score > 0:
                    similarities.append(ProjectSimilarity(
                        project_a=proj_a,
                        project_b=proj_b,
                        shared_tags=list(shared),
                        shared_concepts=len(shared),
                        similarity_score=score,
                        shared_files=[],
                    ))

        similarities.sort(key=lambda s: s.similarity_score, reverse=True)
        return similarities

    def generate_concept_files(
        self,
        concepts: Optional[List[SharedConcept]] = None,
        overwrite: bool = False,
    ) -> List[str]:
        """
        Generate concept files in concepts/ directory.

        Each shared concept gets a file linking to all source files.

        Args:
            concepts: Concepts to generate (if None, finds all shared concepts)
            overwrite: Whether to overwrite existing concept files

        Returns:
            List of generated file paths
        """
        if concepts is None:
            concepts = self.find_shared_concepts()

        self.concepts_dir.mkdir(parents=True, exist_ok=True)
        generated = []

        today = datetime.now().strftime("%Y-%m-%d")

        for concept in concepts:
            filename = f"{concept.tag}.md"
            filepath = self.concepts_dir / filename

            if filepath.exists() and not overwrite:
                continue

            # Build content
            projects_str = ", ".join(concept.projects)
            files_by_project: Dict[str, List[Dict]] = {}
            for f in concept.files:
                proj = f["project"]
                if proj not in files_by_project:
                    files_by_project[proj] = []
                files_by_project[proj].append(f)

            lines = []
            lines.append(f"# {concept.name}")
            lines.append("")
            lines.append(f"## Summary")
            lines.append(f"Cross-project concept: **{concept.name}**. "
                        f"Referenced in {len(concept.projects)} projects "
                        f"({projects_str}) across {concept.file_count} files.")
            lines.append("")

            # By project
            lines.append("## References by Project")
            for proj, proj_files in files_by_project.items():
                lines.append(f"")
                lines.append(f"### {proj}")
                for f in proj_files:
                    layer = f.get("layer", "cross")
                    file_id = f.get("file_id", "")
                    lines.append(f"- [[{file_id}]] [{layer}]")

            lines.append("")
            lines.append("## Links")
            lines.append("")
            lines.append("### Related")
            for f in concept.files[:10]:
                lines.append(f"- [[{f['file_id']}]]")

            lines.append("")
            lines.append(f"_Auto-generated: {today}_")

            # Write
            metadata = {
                "id": concept.tag,
                "type": "concept",
                "layer": "cross",
                "project": "general",
                "created": today,
                "updated": today,
                "confidence": "moderate",
                "status": "active",
                "tags": [concept.tag, "cross-project"],
            }

            content = write_frontmatter(metadata, "\n".join(lines))
            filepath.write_text(content, encoding="utf-8")
            generated.append(str(filepath))

        return generated

    def get_analysis(self) -> CrossProjectReport:
        """Get complete cross-project analysis."""
        files = scan_vault(self.vault_path)

        # Get all projects
        projects = set()
        for meta in files:
            proj = meta.get("project")
            if proj and proj != "general":
                projects.add(proj)

        concepts = self.find_shared_concepts()
        similarities = self.find_project_similarities()

        # Find orphan tags (in only one project)
        project_tags: Dict[str, Set[str]] = {}
        for meta in files:
            proj = meta.get("project", "general")
            tags = meta.get("tags", [])
            if not isinstance(tags, list):
                continue
            if proj not in project_tags:
                project_tags[proj] = set()
            for tag in tags:
                if tag:
                    project_tags[proj].add(tag.lower().strip())

        all_shared_tags = set()
        for c in concepts:
            all_shared_tags.add(c.tag)

        orphan_tags = []
        for proj, tags in project_tags.items():
            for tag in tags:
                if tag not in all_shared_tags:
                    orphan_tags.append(f"{tag} ({proj})")

        return CrossProjectReport(
            timestamp=datetime.now().isoformat(),
            project_count=len(projects),
            projects=list(projects),
            shared_concepts=concepts,
            similarities=similarities,
            orphan_tags=orphan_tags[:20],
            concept_files_generated=0,
        )

    def find_cross_project_links(self) -> List[Dict]:
        """Find [[links]] that cross project boundaries."""
        files = scan_vault(self.vault_path)
        cross_links = []

        # Build file -> project map
        file_projects: Dict[str, str] = {}
        for meta in files:
            file_projects[meta.get("_filename", "")] = meta.get("project", "general")

        for meta in files:
            path = meta.get("_path", "")
            if not path or not os.path.exists(path):
                continue

            source_project = meta.get("project", "general")

            try:
                _, body = read_vault_file(path)
                links = extract_links(body)

                for link in links:
                    target_project = file_projects.get(link, "unknown")
                    if target_project != source_project and target_project != "general":
                        cross_links.append({
                            "source": meta.get("_filename", ""),
                            "source_project": source_project,
                            "target": link,
                            "target_project": target_project,
                        })
            except Exception:
                continue

        return cross_links


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    analyzer = CrossProjectAnalyzer(vault)

    if cmd == "concepts":
        min_proj = int(sys.argv[2]) if len(sys.argv) > 2 else 2
        concepts = analyzer.find_shared_concepts(min_projects=min_proj)
        print(f"Shared concepts (across {min_proj}+ projects): {len(concepts)}")
        for c in concepts[:15]:
            print(f"  {c.tag:20} {len(c.projects)} projects: {', '.join(c.projects)}")

    elif cmd == "similarities":
        sims = analyzer.find_project_similarities()
        print(f"Project similarities: {len(sims)}")
        for s in sims[:10]:
            print(f"  {s.project_a} <-> {s.project_b}: {s.similarity_score:.2f} "
                  f"({s.shared_concepts} shared)")

    elif cmd == "generate":
        overwrite = "--overwrite" in sys.argv
        generated = analyzer.generate_concept_files(overwrite=overwrite)
        print(f"Generated {len(generated)} concept files:")
        for g in generated:
            print(f"  {g}")

    elif cmd == "links":
        links = analyzer.find_cross_project_links()
        print(f"Cross-project links: {len(links)}")
        for l in links[:10]:
            print(f"  {l['source']} ({l['source_project']}) -> "
                  f"{l['target']} ({l['target_project']})")

    elif cmd == "report":
        report = analyzer.get_analysis()
        print(f"Cross-Project Analysis:")
        print(f"  Projects: {report.project_count}")
        print(f"  Shared concepts: {len(report.shared_concepts)}")
        print(f"  Project pairs with similarity: {len(report.similarities)}")
        if report.shared_concepts:
            print(f"  Top concepts:")
            for c in report.shared_concepts[:5]:
                print(f"    {c.tag}: {', '.join(c.projects)}")

    else:
        print("Commands: concepts [min_projects], similarities, generate [--overwrite], links, report")

#!/usr/bin/env python3
"""
Background Maintenance for Mnemosyne Knowledge Vault.

Automated vault health maintenance:
  - Link validation (find and report broken links)
  - Stale file detection and auto-archiving
  - Frontmatter validation and repair
  - Orphan detection (files with no links in/out)
  - Vault statistics and health check

Usage:
    from maintenance import VaultMaintainer

    maint = VaultMaintainer(vault_path="~/.hermes/memory")
    
    # Run full maintenance
    report = maint.run_maintenance()
    
    # Individual checks
    broken = maint.validate_links()
    stale = maint.find_stale_files(days=30)
    orphans = maint.find_orphans()
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from vault_utils import (
    scan_vault, read_vault_file, extract_links,
    resolve_link, find_broken_links, write_frontmatter, parse_frontmatter
)


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class MaintenanceIssue:
    """A single maintenance issue found."""
    severity: str  # "info", "warning", "error"
    category: str  # "broken_link", "stale", "orphan", "frontmatter", "empty"
    file_path: str
    file_id: str
    message: str
    auto_fixable: bool = False
    fixed: bool = False


@dataclass
class MaintenanceReport:
    """Complete maintenance run report."""
    timestamp: str
    duration_ms: float
    files_scanned: int
    issues_found: int
    issues_fixed: int
    issues: List[MaintenanceIssue]
    vault_stats: Dict
    health_score: float  # 0.0 to 1.0

    @property
    def errors(self) -> List[MaintenanceIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[MaintenanceIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_healthy(self) -> bool:
        return self.health_score >= 0.8


@dataclass
class VaultStats:
    """Vault statistics."""
    total_files: int
    total_links: int
    total_broken_links: int
    files_by_layer: Dict[str, int]
    files_by_type: Dict[str, int]
    files_by_status: Dict[str, int]
    files_by_project: Dict[str, int]
    avg_links_per_file: float
    orphan_count: int
    stale_count: int
    vault_size_bytes: int


# ─── Vault Maintainer ─────────────────────────────────────────────

class VaultMaintainer:
    """
    Automated vault maintenance.

    Runs health checks and optionally auto-fixes issues:
    - Broken links
    - Stale files (no updates in N days)
    - Invalid frontmatter
    - Orphan files (no links in or out)
    - Empty files
    """

    def __init__(
        self,
        vault_path: str = "~/.hermes/memory",
        auto_fix: bool = False,
        archive_after_days: int = 90,
    ):
        self.vault_path = os.path.expanduser(vault_path)
        self.auto_fix = auto_fix
        self.archive_after_days = archive_after_days
        self.archive_dir = Path(self.vault_path) / "archive"

    def run_maintenance(
        self,
        check_links: bool = True,
        check_stale: bool = True,
        check_orphans: bool = True,
        check_frontmatter: bool = True,
        check_empty: bool = True,
    ) -> MaintenanceReport:
        """
        Run full maintenance suite.

        Returns comprehensive report of issues found and fixed.
        """
        import time
        start = time.time()

        issues: List[MaintenanceIssue] = []
        files = scan_vault(self.vault_path)

        # Link validation
        if check_links:
            issues.extend(self._check_broken_links())

        # Stale file detection
        if check_stale:
            issues.extend(self._check_stale_files(files))

        # Orphan detection
        if check_orphans:
            issues.extend(self._check_orphans(files))

        # Frontmatter validation
        if check_frontmatter:
            issues.extend(self._check_frontmatter(files))

        # Empty file detection
        if check_empty:
            issues.extend(self._check_empty_files(files))

        # Auto-fix if enabled
        fixed_count = 0
        if self.auto_fix:
            for issue in issues:
                if issue.auto_fixable and not issue.fixed:
                    if self._auto_fix(issue):
                        issue.fixed = True
                        fixed_count += 1

        # Calculate health score
        total_checks = len(files) * 3  # Rough estimate
        error_count = len([i for i in issues if i.severity == "error"])
        warning_count = len([i for i in issues if i.severity == "warning"])
        health = max(0.0, 1.0 - (error_count * 0.1) - (warning_count * 0.02))

        # Vault stats
        stats = self._collect_stats(files)

        duration_ms = (time.time() - start) * 1000

        return MaintenanceReport(
            timestamp=datetime.now().isoformat(),
            duration_ms=duration_ms,
            files_scanned=len(files),
            issues_found=len(issues),
            issues_fixed=fixed_count,
            issues=issues,
            vault_stats=stats.__dict__ if isinstance(stats, VaultStats) else stats,
            health_score=health,
        )

    def validate_links(self) -> List[MaintenanceIssue]:
        """Find all broken links in the vault."""
        return self._check_broken_links()

    def find_stale_files(self, days: int = 30) -> List[MaintenanceIssue]:
        """Find files not updated in N days."""
        files = scan_vault(self.vault_path)
        return self._check_stale_files(files, days=days)

    def find_orphans(self) -> List[MaintenanceIssue]:
        """Find files with no links in or out."""
        files = scan_vault(self.vault_path)
        return self._check_orphans(files)

    def archive_stale(self, days: int = 90) -> List[str]:
        """
        Archive files stale for more than N days.

        Moves files to archive/ directory.
        Returns list of archived file paths.
        """
        files = scan_vault(self.vault_path)
        archived = []
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue

            # Skip already archived
            if "/archive/" in path or "\\archive\\" in path:
                continue

            # Skip index, inbox, user files
            filename = meta.get("_filename", "")
            if filename.startswith("_") or "/user/" in path:
                continue

            updated = str(meta.get("updated", ""))[:10]
            if updated and updated < cutoff:
                # Move to archive
                src = Path(path)
                rel_path = src.relative_to(self.vault_path)
                dest = self.archive_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)

                try:
                    shutil.move(str(src), str(dest))
                    archived.append(str(dest))
                except Exception:
                    pass

        return archived

    def get_vault_stats(self) -> VaultStats:
        """Get vault statistics."""
        files = scan_vault(self.vault_path)
        return self._collect_stats(files)

    # ─── Check Methods ────────────────────────────────────────────

    def _check_broken_links(self) -> List[MaintenanceIssue]:
        """Check for broken links."""
        issues = []
        broken = find_broken_links(self.vault_path)

        for file_path, link_target in broken:
            issues.append(MaintenanceIssue(
                severity="warning",
                category="broken_link",
                file_path=file_path,
                file_id=Path(file_path).stem,
                message=f"Broken link: [[{link_target}]]",
                auto_fixable=False,
            ))

        return issues

    def _check_stale_files(
        self,
        files: List[Dict],
        days: int = 30,
    ) -> List[MaintenanceIssue]:
        """Check for stale files."""
        issues = []
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        archive_cutoff = (datetime.now() - timedelta(days=self.archive_after_days)).strftime("%Y-%m-%d")

        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue

            # Skip system files
            filename = meta.get("_filename", "")
            if filename.startswith("_") or "/user/" in path or "/archive/" in path:
                continue

            updated = str(meta.get("updated", ""))[:10]
            if not updated:
                continue

            if updated < archive_cutoff:
                issues.append(MaintenanceIssue(
                    severity="warning",
                    category="stale",
                    file_path=path,
                    file_id=meta.get("_filename", ""),
                    message=f"File stale for >{self.archive_after_days} days (last: {updated})",
                    auto_fixable=True,
                ))
            elif updated < cutoff:
                issues.append(MaintenanceIssue(
                    severity="info",
                    category="stale",
                    file_path=path,
                    file_id=meta.get("_filename", ""),
                    message=f"File not updated in {days} days (last: {updated})",
                    auto_fixable=False,
                ))

        return issues

    def _check_orphans(self, files: List[Dict]) -> List[MaintenanceIssue]:
        """Check for orphan files (no links in or out)."""
        issues = []

        # Build link graph
        all_links_out: Dict[str, Set[str]] = {}
        all_links_in: Dict[str, Set[str]] = {}

        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue
            file_id = meta.get("_filename", "")
            all_links_out[file_id] = set()
            all_links_in[file_id] = set()

        for meta in files:
            path = meta.get("_path", "")
            if not path or not os.path.exists(path):
                continue

            try:
                _, body = read_vault_file(path)
                links = extract_links(body)
                source_id = meta.get("_filename", "")

                for link in links:
                    all_links_out[source_id].add(link)
                    if link in all_links_in:
                        all_links_in[link].add(source_id)
            except Exception:
                continue

        # Find orphans
        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue

            # Skip system files
            filename = meta.get("_filename", "")
            if filename.startswith("_") or "/user/" in path or "/archive/" in path:
                continue

            out_count = len(all_links_out.get(filename, set()))
            in_count = len(all_links_in.get(filename, set()))

            if out_count == 0 and in_count == 0:
                issues.append(MaintenanceIssue(
                    severity="info",
                    category="orphan",
                    file_path=path,
                    file_id=filename,
                    message="No links in or out — consider linking or archiving",
                    auto_fixable=False,
                ))

        return issues

    def _check_frontmatter(self, files: List[Dict]) -> List[MaintenanceIssue]:
        """Check for invalid or missing frontmatter."""
        issues = []

        for meta in files:
            path = meta.get("_path", "")
            if not path or not os.path.exists(path):
                continue

            # Skip system files
            if "/archive/" in path:
                continue

            try:
                fm, body = read_vault_file(path)
            except Exception:
                issues.append(MaintenanceIssue(
                    severity="error",
                    category="frontmatter",
                    file_path=path,
                    file_id=meta.get("_filename", ""),
                    message="Failed to parse frontmatter",
                    auto_fixable=False,
                ))
                continue

            # Check required fields
            if not fm:
                issues.append(MaintenanceIssue(
                    severity="warning",
                    category="frontmatter",
                    file_path=path,
                    file_id=meta.get("_filename", ""),
                    message="Missing frontmatter",
                    auto_fixable=True,
                ))
                continue

            if not fm.get("id"):
                issues.append(MaintenanceIssue(
                    severity="warning",
                    category="frontmatter",
                    file_path=path,
                    file_id=meta.get("_filename", ""),
                    message="Missing 'id' field in frontmatter",
                    auto_fixable=True,
                ))

            if not fm.get("updated"):
                issues.append(MaintenanceIssue(
                    severity="info",
                    category="frontmatter",
                    file_path=path,
                    file_id=meta.get("_filename", ""),
                    message="Missing 'updated' field in frontmatter",
                    auto_fixable=True,
                ))

        return issues

    def _check_empty_files(self, files: List[Dict]) -> List[MaintenanceIssue]:
        """Check for files with no meaningful content."""
        issues = []

        for meta in files:
            path = meta.get("_path", "")
            if not path or not os.path.exists(path):
                continue

            try:
                _, body = read_vault_file(path)
                if len(body.strip()) < 20:
                    issues.append(MaintenanceIssue(
                        severity="info",
                        category="empty",
                        file_path=path,
                        file_id=meta.get("_filename", ""),
                        message="File has very little content",
                        auto_fixable=False,
                    ))
            except Exception:
                pass

        return issues

    # ─── Auto-fix ─────────────────────────────────────────────────

    def _auto_fix(self, issue: MaintenanceIssue) -> bool:
        """Attempt to auto-fix an issue."""
        try:
            if issue.category == "stale" and issue.severity == "warning":
                # Archive stale file
                src = Path(issue.file_path)
                if not src.exists():
                    return False
                rel_path = src.relative_to(self.vault_path)
                dest = self.archive_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                return True

            elif issue.category == "frontmatter":
                # Add missing fields
                fm, body = read_vault_file(issue.file_path)
                modified = False

                if not fm.get("id"):
                    fm["id"] = issue.file_id
                    modified = True
                if not fm.get("updated"):
                    fm["updated"] = datetime.now().strftime("%Y-%m-%d")
                    modified = True
                if not fm.get("type"):
                    fm["type"] = "unknown"
                    modified = True
                if not fm.get("layer"):
                    fm["layer"] = "cross"
                    modified = True

                if modified:
                    content = write_frontmatter(fm, body)
                    Path(issue.file_path).write_text(content, encoding="utf-8")
                    return True

        except Exception:
            pass

        return False

    # ─── Stats ────────────────────────────────────────────────────

    def _collect_stats(self, files: List[Dict]) -> VaultStats:
        """Collect vault statistics."""
        total_links = 0
        total_broken = 0
        files_by_layer: Dict[str, int] = {}
        files_by_type: Dict[str, int] = {}
        files_by_status: Dict[str, int] = {}
        files_by_project: Dict[str, int] = {}
        vault_size = 0

        for meta in files:
            path = meta.get("_path", "")
            if not path:
                continue

            # Size
            try:
                vault_size += os.path.getsize(path)
            except OSError:
                pass

            # Count by fields
            layer = meta.get("layer", "cross")
            files_by_layer[layer] = files_by_layer.get(layer, 0) + 1

            ftype = meta.get("type", "unknown")
            files_by_type[ftype] = files_by_type.get(ftype, 0) + 1

            status = meta.get("status", "unknown")
            files_by_status[status] = files_by_status.get(status, 0) + 1

            project = meta.get("project", "general")
            files_by_project[project] = files_by_project.get(project, 0) + 1

            # Count links
            if os.path.exists(path):
                try:
                    _, body = read_vault_file(path)
                    links = extract_links(body)
                    total_links += len(links)
                except Exception:
                    pass

        # Count broken links
        broken = find_broken_links(self.vault_path)
        total_broken = len(broken)

        # Count orphans and stale
        orphan_issues = self._check_orphans(files)
        stale_issues = self._check_stale_files(files, days=30)

        return VaultStats(
            total_files=len(files),
            total_links=total_links,
            total_broken_links=total_broken,
            files_by_layer=files_by_layer,
            files_by_type=files_by_type,
            files_by_status=files_by_status,
            files_by_project=files_by_project,
            avg_links_per_file=total_links / max(1, len(files)),
            orphan_count=len(orphan_issues),
            stale_count=len([i for i in stale_issues if i.severity == "warning"]),
            vault_size_bytes=vault_size,
        )


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    maint = VaultMaintainer(vault)

    if cmd == "check":
        report = maint.run_maintenance()
        print(f"Maintenance Report ({report.duration_ms:.0f}ms):")
        print(f"  Files scanned: {report.files_scanned}")
        print(f"  Issues found: {report.issues_found}")
        print(f"  Health score: {report.health_score:.0%}")
        if report.errors:
            print(f"  Errors ({len(report.errors)}):")
            for e in report.errors[:5]:
                print(f"    {e.file_id}: {e.message}")
        if report.warnings:
            print(f"  Warnings ({len(report.warnings)}):")
            for w in report.warnings[:5]:
                print(f"    {w.file_id}: {w.message}")

    elif cmd == "links":
        broken = maint.validate_links()
        print(f"Broken links: {len(broken)}")
        for b in broken[:10]:
            print(f"  {b.file_id}: {b.message}")

    elif cmd == "stale":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        stale = maint.find_stale_files(days=days)
        print(f"Stale files (>{days} days): {len(stale)}")
        for s in stale[:10]:
            print(f"  {s.file_id}: {s.message}")

    elif cmd == "orphans":
        orphans = maint.find_orphans()
        print(f"Orphan files: {len(orphans)}")
        for o in orphans[:10]:
            print(f"  {o.file_id}")

    elif cmd == "archive":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
        archived = maint.archive_stale(days=days)
        print(f"Archived {len(archived)} files stale for >{days} days")
        for a in archived[:10]:
            print(f"  {a}")

    elif cmd == "stats":
        stats = maint.get_vault_stats()
        print(f"Vault Statistics:")
        print(f"  Files: {stats.total_files}")
        print(f"  Links: {stats.total_links} ({stats.avg_links_per_file:.1f}/file)")
        print(f"  Broken links: {stats.total_broken_links}")
        print(f"  Orphans: {stats.orphan_count}")
        print(f"  Stale: {stats.stale_count}")
        print(f"  Size: {stats.vault_size_bytes / 1024:.1f} KB")
        print(f"  By layer: {stats.files_by_layer}")
        print(f"  By project: {stats.files_by_project}")

    else:
        print("Commands: check, links, stale [days], orphans, archive [days], stats")

#!/usr/bin/env python3
"""
Vault Search Engine for Mnemosyne Knowledge Vault.

Provides content and metadata search across the vault:
  - Full-text search with regex support
  - Metadata search (by field values)
  - Combined search (content + metadata)
  - Ranked results with relevance scoring

Usage:
    from vault_search import VaultSearch

    search = VaultSearch(vault_path="~/.hermes/memory")
    results = search.search("gold oxidation", project="eeg")
    for r in results:
        print(f"{r.score:.2f} {r.file_id}: {r.snippet}")
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from vault_utils import (
    scan_vault, read_vault_file, extract_links,
    find_by_layer, find_by_project, find_by_tag
)


# ─── Data Classes ─────────────────────────────────────────────────

@dataclass
class SearchResult:
    """A single search result."""
    file_id: str
    path: str
    filename: str
    layer: str
    file_type: str
    project: Optional[str]
    score: float
    match_count: int
    snippet: str
    matched_fields: List[str]  # Which fields matched (title, body, tags, etc.)
    metadata: Dict


@dataclass
class SearchQuery:
    """Parsed search query with filters."""
    raw_query: str
    terms: List[str]
    phrases: List[str]  # Quoted phrases
    exclude_terms: List[str]  # Terms prefixed with -
    filters: Dict[str, str]  # field:value pairs
    use_regex: bool


# ─── Query Parser ─────────────────────────────────────────────────

def parse_query(query_str: str) -> SearchQuery:
    """
    Parse a search query string.

    Supports:
    - Simple terms: gold electrode
    - Quoted phrases: "gold electrode"
    - Exclusions: -silver
    - Field filters: layer:L4 type:research tag:materials
    - Regex: re:pattern
    """
    terms = []
    phrases = []
    exclude_terms = []
    filters = {}
    use_regex = False

    # Extract quoted phrases first
    phrase_pattern = r'"([^"]+)"'
    found_phrases = re.findall(phrase_pattern, query_str)
    phrases.extend(found_phrases)
    query_str = re.sub(phrase_pattern, '', query_str)

    # Parse remaining tokens
    tokens = query_str.split()
    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # Regex mode
        if token.startswith("re:"):
            use_regex = True
            terms.append(token[3:])
            continue

        # Exclusion
        if token.startswith("-"):
            exclude_terms.append(token[1:])
            continue

        # Field filter (field:value)
        if ":" in token and not token.startswith(":"):
            field_name, value = token.split(":", 1)
            if field_name in ("layer", "type", "project", "tag", "status", "confidence"):
                filters[field_name] = value
                continue

        # Regular term
        terms.append(token.lower())

    return SearchQuery(
        raw_query=query_str,
        terms=terms,
        phrases=phrases,
        exclude_terms=exclude_terms,
        filters=filters,
        use_regex=use_regex,
    )


# ─── Search Engine ────────────────────────────────────────────────

class VaultSearch:
    """
    Search engine for the Mnemosyne knowledge vault.

    Supports content search, metadata search, and combined queries.
    """

    def __init__(self, vault_path: str = "~/.hermes/memory"):
        self.vault_path = os.path.expanduser(vault_path)

    def search(
        self,
        query: str,
        project: Optional[str] = None,
        layer: Optional[str] = None,
        file_type: Optional[str] = None,
        limit: int = 20,
        min_score: float = 0.1,
    ) -> List[SearchResult]:
        """
        Search the vault.

        Args:
            query: Search query string (supports terms, phrases, filters)
            project: Limit to project
            layer: Limit to layer (L1-L4)
            file_type: Limit to type (overview, component, rule, research, decision)
            limit: Max results
            min_score: Minimum score threshold

        Returns:
            List of SearchResult sorted by score descending
        """
        parsed = parse_query(query)

        # Apply CLI filters to parsed query filters
        if project:
            parsed.filters["project"] = project
        if layer:
            parsed.filters["layer"] = layer
        if file_type:
            parsed.filters["type"] = file_type

        # Scan vault
        all_files = scan_vault(self.vault_path)

        # Filter and score
        results = []
        for meta in all_files:
            path = meta.get("_path", "")
            if not path or not os.path.exists(path):
                continue
            if ".private" in path:
                continue

            # Apply metadata filters
            if not self._matches_filters(meta, parsed.filters):
                continue

            # Load file content
            try:
                fm, body = read_vault_file(path)
            except Exception:
                continue

            # Check exclusions
            if self._has_excluded_terms(body, fm, parsed.exclude_terms):
                continue

            # Score the file
            score, match_count, matched_fields, snippet = self._score_file(
                fm, body, meta, parsed
            )

            if score >= min_score:
                results.append(SearchResult(
                    file_id=fm.get("id", meta.get("_filename", "")),
                    path=path,
                    filename=meta.get("_filename", ""),
                    layer=fm.get("layer", "cross"),
                    file_type=fm.get("type", "unknown"),
                    project=fm.get("project"),
                    score=score,
                    match_count=match_count,
                    snippet=snippet,
                    matched_fields=matched_fields,
                    metadata=fm,
                ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def search_by_link(self, link_target: str) -> List[SearchResult]:
        """Find all files containing a specific [[link]]."""
        pattern = re.compile(
            rf'\[\[{re.escape(link_target)}(?:\|[^\]]+)?\]\]'
        )
        results = []

        for md_file in Path(self.vault_path).rglob("*.md"):
            if ".private" in str(md_file):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                if pattern.search(content):
                    meta, body = read_vault_file(str(md_file))
                    results.append(SearchResult(
                        file_id=meta.get("id", md_file.stem),
                        path=str(md_file),
                        filename=md_file.stem,
                        layer=meta.get("layer", "cross"),
                        file_type=meta.get("type", "unknown"),
                        project=meta.get("project"),
                        score=1.0,
                        match_count=1,
                        snippet=f"Contains [[{link_target}]]",
                        matched_fields=["body"],
                        metadata=meta,
                    ))
            except Exception:
                continue

        return results

    def search_similar(self, file_id: str, limit: int = 5) -> List[SearchResult]:
        """Find files similar to a given file (by shared links and tags)."""
        # Find the source file
        source_path = None
        source_meta = None
        source_body = None

        for md_file in Path(self.vault_path).rglob("*.md"):
            try:
                meta, body = read_vault_file(str(md_file))
                if meta.get("id") == file_id or md_file.stem == file_id:
                    source_path = str(md_file)
                    source_meta = meta
                    source_body = body
                    break
            except Exception:
                continue

        if not source_path:
            return []

        # Extract source links and tags
        source_links = set(extract_links(source_body))
        source_tags = set(source_meta.get("tags", []))
        source_project = source_meta.get("project")

        # Score other files by shared links and tags
        results = []
        for md_file in Path(self.vault_path).rglob("*.md"):
            if str(md_file) == source_path:
                continue
            if ".private" in str(md_file):
                continue

            try:
                meta, body = read_vault_file(str(md_file))
            except Exception:
                continue

            file_links = set(extract_links(body))
            file_tags = set(meta.get("tags", []))

            # Calculate similarity
            shared_links = source_links & file_links
            shared_tags = source_tags & file_tags
            same_project = source_project and meta.get("project") == source_project

            score = 0.0
            score += len(shared_links) * 0.3
            score += len(shared_tags) * 0.2
            if same_project:
                score += 0.3

            if score > 0:
                results.append(SearchResult(
                    file_id=meta.get("id", md_file.stem),
                    path=str(md_file),
                    filename=md_file.stem,
                    layer=meta.get("layer", "cross"),
                    file_type=meta.get("type", "unknown"),
                    project=meta.get("project"),
                    score=score,
                    match_count=len(shared_links) + len(shared_tags),
                    snippet=f"Shared: {', '.join(list(shared_links)[:3])}",
                    matched_fields=["links", "tags"],
                    metadata=meta,
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def search_recent(self, days: int = 7, project: Optional[str] = None) -> List[SearchResult]:
        """Find recently modified files."""
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=days)
        results = []

        all_files = scan_vault(self.vault_path)
        for meta in all_files:
            path = meta.get("_path", "")
            if ".private" in path:
                continue
            if project and meta.get("project") != project:
                continue

            updated_str = meta.get("updated", "")
            try:
                updated = datetime.strptime(str(updated_str), "%Y-%m-%d")
                if updated >= cutoff:
                    fm, _ = read_vault_file(path)
                    days_ago = (datetime.now() - updated).days
                    results.append(SearchResult(
                        file_id=fm.get("id", meta.get("_filename", "")),
                        path=path,
                        filename=meta.get("_filename", ""),
                        layer=fm.get("layer", "cross"),
                        file_type=fm.get("type", "unknown"),
                        project=fm.get("project"),
                        score=1.0 - (days_ago / days),
                        match_count=1,
                        snippet=f"Updated {updated_str} ({days_ago} days ago)",
                        matched_fields=["updated"],
                        metadata=fm,
                    ))
            except (ValueError, TypeError):
                continue

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ─── Scoring ──────────────────────────────────────────────────

    def _score_file(
        self,
        frontmatter: Dict,
        body: str,
        meta: Dict,
        query: SearchQuery,
    ) -> Tuple[float, int, List[str], str]:
        """
        Score a file against a search query.
        Returns (score, match_count, matched_fields, snippet).
        """
        score = 0.0
        match_count = 0
        matched_fields = []
        best_snippet = ""

        searchable_text = body.lower()
        title = frontmatter.get("id", meta.get("_filename", "")).lower()
        tags = " ".join(frontmatter.get("tags", [])).lower()

        # Filter-only queries get a base score
        if not query.terms and not query.phrases:
            score = 0.5  # Base score for filter-only matches

        # Score terms
        for term in query.terms:
            term_lower = term.lower()

            # Title match (highest weight)
            if term_lower in title:
                score += 2.0
                match_count += 1
                if "title" not in matched_fields:
                    matched_fields.append("title")

            # Tag match (high weight)
            if term_lower in tags:
                score += 1.5
                match_count += 1
                if "tags" not in matched_fields:
                    matched_fields.append("tags")

            # Body match
            if query.use_regex:
                try:
                    matches = list(re.finditer(term, body, re.IGNORECASE))
                    if matches:
                        score += len(matches) * 0.5
                        match_count += len(matches)
                        if "body" not in matched_fields:
                            matched_fields.append("body")
                        # Get snippet around first match
                        best_snippet = self._get_snippet(body, matches[0].start())
                except re.error:
                    pass
            else:
                count = searchable_text.count(term_lower)
                if count > 0:
                    score += count * 0.5
                    match_count += count
                    if "body" not in matched_fields:
                        matched_fields.append("body")
                    # Get snippet
                    pos = searchable_text.find(term_lower)
                    if pos >= 0:
                        best_snippet = self._get_snippet(body, pos)

        # Score phrases (bonus for exact phrase match)
        for phrase in query.phrases:
            phrase_lower = phrase.lower()
            if query.use_regex:
                try:
                    if re.search(phrase, body, re.IGNORECASE):
                        score += 3.0
                        match_count += 1
                        if "body" not in matched_fields:
                            matched_fields.append("body")
                except re.error:
                    pass
            else:
                if phrase_lower in searchable_text:
                    score += 3.0
                    match_count += 1
                    if "body" not in matched_fields:
                        matched_fields.append("body")
                    pos = searchable_text.find(phrase_lower)
                    if pos >= 0:
                        best_snippet = self._get_snippet(body, pos)

        # Boost for active status
        if frontmatter.get("status") == "active":
            score *= 1.1

        # Boost for high confidence
        if frontmatter.get("confidence") == "high":
            score *= 1.05

        # Normalize score
        if match_count > 0:
            score = min(1.0, score / (match_count + 2))

        return score, match_count, matched_fields, best_snippet

    def _get_snippet(self, text: str, pos: int, context: int = 80) -> str:
        """Extract a snippet around a position in text."""
        start = max(0, pos - context)
        end = min(len(text), pos + context)
        snippet = text[start:end].replace("\n", " ").strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet

    def _matches_filters(self, meta: Dict, filters: Dict[str, str]) -> bool:
        """Check if file metadata matches all filters."""
        for field_name, value in filters.items():
            if field_name == "tag":
                tags = meta.get("tags", [])
                if value not in tags:
                    return False
            elif field_name == "layer":
                if meta.get("layer") != value:
                    return False
            elif field_name == "type":
                if meta.get("type") != value:
                    return False
            elif field_name == "project":
                if meta.get("project") != value:
                    return False
            elif field_name == "status":
                if meta.get("status") != value:
                    return False
            elif field_name == "confidence":
                if meta.get("confidence") != value:
                    return False
        return True

    def _has_excluded_terms(
        self, body: str, frontmatter: Dict, exclude_terms: List[str]
    ) -> bool:
        """Check if file contains any excluded terms."""
        if not exclude_terms:
            return False
        searchable = (
            body + " " +
            frontmatter.get("id", "") + " " +
            " ".join(frontmatter.get("tags", []))
        ).lower()
        return any(term.lower() in searchable for term in exclude_terms)


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    vault = os.path.expanduser("~/.hermes/memory")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    search = VaultSearch(vault)

    if cmd == "search":
        query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        if not query:
            print("Usage: vault_search.py search <query>")
            sys.exit(1)
        results = search.search(query)
        print(f"Found {len(results)} results for '{query}':")
        print()
        for r in results:
            print(f"  {r.score:.2f}  [{r.layer}/{r.file_type}]  {r.file_id}")
            print(f"         {r.snippet}")
            print()

    elif cmd == "links":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        if not target:
            print("Usage: vault_search.py links <link_target>")
            sys.exit(1)
        results = search.search_by_link(target)
        print(f"Files containing [[{target}]]: {len(results)}")
        for r in results:
            print(f"  {r.path}")

    elif cmd == "similar":
        file_id = sys.argv[2] if len(sys.argv) > 2 else None
        if not file_id:
            print("Usage: vault_search.py similar <file_id>")
            sys.exit(1)
        results = search.search_similar(file_id)
        print(f"Files similar to '{file_id}': {len(results)}")
        for r in results:
            print(f"  {r.score:.2f}  {r.file_id}  {r.snippet}")

    elif cmd == "recent":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        results = search.search_recent(days=days)
        print(f"Files modified in last {days} days: {len(results)}")
        for r in results:
            print(f"  {r.snippet:40}  {r.file_id}")

    else:
        print("Commands: search <query>, links <target>, similar <file_id>, recent [days]")

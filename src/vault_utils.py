#!/usr/bin/env python3
"""
Vault utilities for the Knowledge Vault system.
Frontmatter parser, link resolver, and link validator.
"""

import re
import os
import glob
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


# ─── Frontmatter Parser ───────────────────────────────────────────

def parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """Parse YAML frontmatter from markdown content.
    Returns (metadata_dict, body_text).
    """
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if match:
        try:
            metadata = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            metadata = {}
        return metadata, match.group(2)
    return {}, content


def write_frontmatter(metadata: Dict, body: str) -> str:
    """Write markdown with YAML frontmatter."""
    yaml_str = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
    return f"---\n{yaml_str}---\n\n{body}"


def read_vault_file(path: str) -> Tuple[Dict, str]:
    """Read a vault file and return (metadata, body)."""
    content = Path(path).read_text(encoding='utf-8')
    return parse_frontmatter(content)


def update_frontmatter_field(path: str, field: str, value) -> None:
    """Update a single frontmatter field and save."""
    content = Path(path).read_text(encoding='utf-8')
    metadata, body = parse_frontmatter(content)
    metadata[field] = value
    metadata['updated'] = datetime.now().strftime('%Y-%m-%d')
    Path(path).write_text(write_frontmatter(metadata, body), encoding='utf-8')


# ─── Link Parser & Resolver ──────────────────────────────────────

def extract_links(content: str) -> List[str]:
    """Extract [[wiki-links]] from markdown content.
    Returns list of link targets (without aliases).
    """
    pattern = r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]'
    return re.findall(pattern, content)


def resolve_link(link: str, vault_path: str) -> Optional[str]:
    """Resolve a [[link]] target to a file path.
    Searches by filename AND frontmatter id field.
    """
    # Clean the link
    link = link.strip()

    # Try exact match by filename
    matches = glob.glob(f"{vault_path}/**/{link}.md", recursive=True)
    if matches:
        return matches[0]

    # Try case-insensitive filename
    for md_file in glob.glob(f"{vault_path}/**/*.md", recursive=True):
        if '.private' in md_file:
            continue
        filename = Path(md_file).stem
        if filename.lower() == link.lower():
            return md_file

    # Search by frontmatter id field
    for md_file in glob.glob(f"{vault_path}/**/*.md", recursive=True):
        if '.private' in md_file:
            continue
        try:
            metadata, _ = read_vault_file(md_file)
            if metadata.get('id', '').lower() == link.lower():
                return md_file
        except Exception:
            continue

    return None


def find_backlinks(target_id: str, vault_path: str) -> List[str]:
    """Find all files that link TO the target file.
    Returns list of file paths containing [[target_id]].
    """
    backlinks = []
    pattern = re.compile(rf'\[\[{re.escape(target_id)}(?:\|[^\]]+)?\]\]')

    for md_file in glob.glob(f"{vault_path}/**/*.md", recursive=True):
        content = Path(md_file).read_text(encoding='utf-8')
        if pattern.search(content):
            backlinks.append(md_file)

    return backlinks


# ─── Link Validator ───────────────────────────────────────────────

def find_broken_links(vault_path: str) -> List[Tuple[str, str]]:
    """Find all broken [[links]] in the vault.
    Returns list of (file_path, broken_link_target).
    """
    broken = []

    for md_file in glob.glob(f"{vault_path}/**/*.md", recursive=True):
        # Skip .private directory
        if '.private' in md_file:
            continue

        content = Path(md_file).read_text(encoding='utf-8')
        links = extract_links(content)

        for link in links:
            resolved = resolve_link(link, vault_path)
            if not resolved:
                broken.append((md_file, link))

    return broken


# ─── Vault Scanner ────────────────────────────────────────────────

def scan_vault(vault_path: str) -> List[Dict]:
    """Scan all vault files and return metadata list."""
    files = []

    for md_file in sorted(glob.glob(f"{vault_path}/**/*.md", recursive=True)):
        # Skip .private directory
        if '.private' in md_file:
            continue

        metadata, body = parse_frontmatter(
            Path(md_file).read_text(encoding='utf-8')
        )
        metadata['_path'] = md_file
        metadata['_filename'] = Path(md_file).stem
        files.append(metadata)

    return files


def find_by_tag(tag: str, vault_path: str) -> List[Dict]:
    """Find files with a specific tag."""
    results = []
    for file_meta in scan_vault(vault_path):
        tags = file_meta.get('tags', [])
        if isinstance(tags, list) and tag in tags:
            results.append(file_meta)
    return results


def find_by_layer(layer: str, vault_path: str, project: str = None) -> List[Dict]:
    """Find files at a specific layer, optionally filtered by project."""
    results = []
    for file_meta in scan_vault(vault_path):
        if file_meta.get('layer') == layer:
            if project is None or file_meta.get('project') == project:
                results.append(file_meta)
    return results


def find_by_project(project: str, vault_path: str) -> List[Dict]:
    """Find all files in a project."""
    results = []
    for file_meta in scan_vault(vault_path):
        if file_meta.get('project') == project:
            results.append(file_meta)
    return results


# ─── CLI Interface ────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    import json

    vault = os.path.expanduser('~/.hermes/memory')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'scan'

    if cmd == 'scan':
        files = scan_vault(vault)
        print(f"Vault contains {len(files)} files:")
        for f in files:
            print(f"  {f.get('layer', '??')} | {f.get('type', '??'):10} | {f['_filename']}")

    elif cmd == 'links':
        path = sys.argv[2] if len(sys.argv) > 2 else None
        if path:
            content = Path(path).read_text(encoding='utf-8')
            links = extract_links(content)
            print(f"Links in {path}:")
            for link in links:
                resolved = resolve_link(link, vault)
                status = "OK" if resolved else "BROKEN"
                print(f"  [{status}] [[{link}]] → {resolved or 'NOT FOUND'}")
        else:
            print("Usage: vault_utils.py links <file_path>")

    elif cmd == 'validate':
        broken = find_broken_links(vault)
        if broken:
            print(f"Found {len(broken)} broken links:")
            for file_path, link in broken:
                print(f"  {file_path}: [[{link}]]")
        else:
            print("No broken links found.")

    elif cmd == 'tag':
        tag = sys.argv[2] if len(sys.argv) > 2 else None
        if tag:
            files = find_by_tag(tag, vault)
            print(f"Files tagged #{tag}: {len(files)}")
            for f in files:
                print(f"  {f['_path']}")
        else:
            print("Usage: vault_utils.py tag <tag_name>")

    elif cmd == 'project':
        project = sys.argv[2] if len(sys.argv) > 2 else None
        if project:
            files = find_by_project(project, vault)
            print(f"Files in project '{project}': {len(files)}")
            for f in files:
                print(f"  {f.get('layer', '??')} | {f['_filename']}")
        else:
            print("Usage: vault_utils.py project <project_name>")

    elif cmd == 'backlinks':
        target = sys.argv[2] if len(sys.argv) > 2 else None
        if target:
            links = find_backlinks(target, vault)
            print(f"Files linking to [[{target}]]: {len(links)}")
            for l in links:
                print(f"  {l}")
        else:
            print("Usage: vault_utils.py backlinks <file_id>")

    else:
        print("Commands: scan, links, validate, tag, project, backlinks")

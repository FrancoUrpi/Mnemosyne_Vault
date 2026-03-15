# Changelog

## V1.1.0 — 2026-03-15 (Distribution Package)

### Added
- `config.yaml` platform_toolsets patching in `patch_hermes.py` (cli + telegram channels)
- State persistence in `vault_tool.py` via `~/.hermes/memory/.vault_state.json`
- New vault actions: `up` (synthesize to higher layer), `layers` (show layer info), `state` (show current state)
- Behavioral guidance in vault tool schema (workflow, when-to-use, layer system docs)
- `DESCRIPTION.md` — comprehensive project description, philosophy, and comparisons
- `INSTALL.md` — detailed installation guide with troubleshooting
- `PACKAGE_SUMMARY.md` — distribution package overview
- `MANIFEST` — package file listing
- `validate.py` — package validation script
- `skills/mnemosyne/` — Hermes skill definition with vault-commands reference
- `docs/` directory — moved ARCHITECTURE.md, added docs README

### Changed
- `vault_tool.py` rewritten: 159 → 465 lines with robust error handling and fallback imports
- `patch_hermes.py` expanded: 254 → 415 lines, now patches 3 files instead of 2
- `README.md` condensed: 253 → 132 lines, defers to dedicated docs
- Schema description expanded from 4 lines to 40+ lines with behavioral guidance
- `file_id` parameter replaced by unified `target` parameter
- Removed `limit` parameter from search action

### Removed
- Version tag from README title
- Inline installation instructions (moved to INSTALL.md)
- Python API usage examples from README (moved to INSTALL.md)

## V1.0.0 — 2026-03-15

### Added
- Core vault system with L1-L4 layered context architecture
- `vault_tool.py` — native Hermes tool with 8 actions (enter, init, status, search, decision, drill, synthesize, get)
- `VaultContextManager` — single source of truth for all vault operations
- 24 Python modules covering: frontmatter parsing, wiki-links, layer traversal, full-text search, synthesis, governance, trust, budget management, cross-project linking, and more
- 6 vault file templates (L1-L2-L3-L4, decision, synthesis)
- CLI wrapper (`vault` command) for direct user access
- Obsidian integration (pre-configured graph view, wiki-links, frontmatter-as-properties)
- One-click installer (`install.sh`)
- Hermes patcher (`patch_hermes.py`) for tool registration
- 3 core test suites (vault, vault_tool, integration)
- Documentation: README, AGENTS guide, Architecture reference

### Fixed
- Tool schema format corrected (was OpenAI-wrapped, now simple format for Hermes registry)
- Platform toolsets config updated to include vault in all channels
- Requirements check function added for graceful degradation

### Architecture
- Layer 1: Native tool (always visible to agent)
- Layer 2: Skill (workflow guidance)
- Layer 3: CLI (debugging)
- Layer 4: Python API (programmatic access)
- All layers call `VaultContextManager` — no duplication

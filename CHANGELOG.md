# Changelog

All notable changes, reconstructed from git history on 2026-06-16 (no prior changelog existed). Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-05-06

### Added
- Portability suite + setup scripts for multi-machine parity (573e773).

## 2026-05-05

### Added
- Surfaces: console, Carry, TTL daemon, vault deploy (PR #7) (f9e7d10).
- Scaffold the three-pane operator console (v0) (PR #6) (cd982f4).

## 2026-04-29

### Added
- Core architecture + schemas for the operator-core-minimal substrate (b7a5eec).
- `--json` flag for structured statusline token output (PR #5) (656124a).
- Cross-platform weaver daemon + autostart scripts (4bc11e3).
- Hoard adapter, schema-clean output, doctrine seed, per-surface budgets (PR #3) (938ed92).
- `CONTRIBUTING.md`, python tools, expanded examples (aad1698); `ROADMAP.md` (68d54b4); `CITATIONS.md` (df0cb66); `REPOS.md` org map + Mermaid mindmap (d000a4c).

### Changed
- PR-A correctness foundation refactor (PR #4) (401b92e).
- Rename `scope` → `area`, split the narrator renderer, add flow diagrams (315a088).
- Replace build/migrate tools with `lint.py` + CI (e883090).
- Rewrite `REPOS.md` as a focused architecture map (00c167c).

### Fixed
- Windows encoding + path resolution for cross-platform golden tests (18f5d06).

### Removed
- Em dashes / AI-formatting patterns + citation artifacts from the docs (058746d, 0aacd5f, 1ce7894).

#### Notes
- CI: two-tier goldens, hoard `aged_out_at` warn, energy-routing test (PR #2) (e445391).
- Docs: Phase 3 ingestion pathways + first renderer prototype (525bb80, e2a9d90); Phase 4 renderers finalized + ADR 0005 (ee5ea91); Phase 4 marked shipped (PR #1) (7878eeb).
- Initial commit: operator-core design docs + architecture (a018fc9).

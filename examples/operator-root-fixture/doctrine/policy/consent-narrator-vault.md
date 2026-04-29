---
id: consent-narrator-vault
kind: policy
title: Narrator vault is opt-out at the file level
body: |
  Markdown files in the narrator vault are ingested by default. A file is
  excluded if it contains the frontmatter key 'ingest&#58; false' OR lives
  under a path matching narrator/_private/. Excluded files MUST emit no
  audit event referencing their path.
pinned: true
stability: stable
tags: [consent, narrator]
consent:
  scope: narrator-vault
  posture: opt-out
  applies_to_pathways: [narrator-vault]
  requires:
    - "honor 'ingest: false' frontmatter key"
    - honor narrator/_private/ path prefix
  rationale: The vault is dense; opt-in would require touching hundreds of files.
created_at: 2026-04-15T00:00:00Z
---

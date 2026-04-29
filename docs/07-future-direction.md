# Future Direction

## What to build next

The clearest next move is not a giant replacement app. It is a shared local context core that formalizes the Backpack / Doctrine / Hoard split and exposes that substrate to multiple renderers.[cite:1][cite:2][web:105]

## Short-term priorities

- Formalize Backpack item shape and freshness policy from the current real-world usage.[cite:1]
- Define Doctrine as a separate pinned-truth layer for defaults, identity, routing, and workflows.[cite:1][code_file:214]
- Define Hoard ingestion rules for transcripts, old notes, artifacts, and long-tail historical context.[web:105][cite:1]
- Build renderers instead of building one giant “main app.”[cite:2][code_file:214]

## Renderers worth building

- Work cockpit / dashboard.[cite:2]
- Claude bootstrap + session primer.[web:105][web:228]
- Narrator renderer with role-first, skin-second routing.[code_file:213][code_file:214]
- Statusline renderer for ambient terminal awareness.[web:4][web:199]
- Daily brief / resume surface.[cite:1][code_file:210]
- Journal / weather surface for life-state context.[cite:37][code_file:209]

## Guiding question

How can one local truth layer make it easier to continue being a person and continue doing the work without requiring the truth to be manually rebuilt every time?[cite:1][cite:2][code_file:213][web:105]

## Practical north star

Build the shared substrate first. Let every future dashboard, narrator, buddy, or assistant surface become a client of that substrate rather than a fresh disconnected system.[cite:1][cite:2][code_file:213]

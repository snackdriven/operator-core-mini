# Future Direction

## What to build next

The clearest next move is not a giant replacement app. It is a shared local context core that formalizes the Backpack / Doctrine / Hoard split and exposes that substrate to multiple renderers.

## Short-term priorities

- Formalize Backpack item shape and freshness policy from the current real-world usage.
- Define Doctrine as a separate pinned-truth layer for defaults, identity, routing, and workflows.
- Define Hoard ingestion rules for transcripts, old notes, artifacts, and long-tail historical context.
- Build renderers instead of building one giant “main app.”

## Renderers worth building

- Work cockpit / dashboard.
- Claude bootstrap + session primer.
- Narrator renderer with role-first, skin-second routing.
- Statusline renderer for ambient terminal awareness.
- Daily brief / resume surface.
- Journal / weather surface for life-state context.

## Guiding question

How can one local truth layer make it easier to continue being a person and continue doing the work without requiring the truth to be manually rebuilt every time?

## Practical north star

Build the shared substrate first. Let every future dashboard, narrator, buddy, or assistant surface become a client of that substrate rather than a fresh disconnected system.

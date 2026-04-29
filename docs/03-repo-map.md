# Repo Map

## scratch-pad

`scratch-pad` appears to be the strongest work-state producer in the ecosystem. It contains dailies, scripts, manifests, dashboards, hooks, and Backpack-oriented context handling for QA workflows.

This cluster contributes work ingestion, artifact generation, and operational memory support. It appears to be where active QA reality gets externalized into files and reusable context.

## qa-brain

`qa-brain` appears to be an ambient cockpit for current work-state, likely downstream of Backpack-like operational context.

Its contribution is rendering: making queue, detail, and current project context glanceable instead of buried in notes or reconstruction effort.

## narrator / workspace-narrator

These repos define the interpretation layer. The narrator system keeps facts stable while changing framing, voice, labels, and tone according to narrator, theme, and context.

This cluster contributes emotional usability. It demonstrates that support quality is not only about what information is surfaced, but how that information is delivered.

## hum / better-buddy / Claude continuity ideas

These represent the continuity and companionship direction: making Claude or terminal AI feel less amnesiac, more persistent, and more emotionally usable between sessions.

This cluster contributes the question of what assistant continuity should feel like when it is local, inspectable, and emotionally meaningful rather than invisible and cloud-owned.

## Inside Weather / Margin / Executive Dysfunction Center / Meat-Suit

These projects appear to explore humane self-observation and life-state tracking, especially around body state, mood, executive function, and internal weather.

This cluster contributes the life-state side of the operator environment: not just what work is happening, but what conditions the person is operating under.

## chronicle

`chronicle` was a more direct attempt at local AI memory infrastructure with a timeline store and KV memory store exposed via MCP, but it was later deprecated in practice in favor of Backpack-centered workflow.

Its contribution is still useful as an exploration of infrastructure shape, but it is no longer the practical center of the ecosystem.

## Backpack

Backpack is not a standalone repo, but it is one of the most important artifacts in the ecosystem. The live `backpack.json` suggests that the practical center of the system is a curated, freshness-managed working-memory sidecar rather than a heavier database-first memory product.

That makes Backpack the strongest candidate for the active carry-state layer in the architecture.

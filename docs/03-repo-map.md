# Repo Map

## scratch-pad

`scratch-pad` appears to be the strongest work-state producer in the ecosystem. It contains dailies, scripts, manifests, dashboards, hooks, and Backpack-oriented context handling for QA workflows.[cite:1]

This cluster contributes work ingestion, artifact generation, and operational memory support. It appears to be where active QA reality gets externalized into files and reusable context.[cite:1]

## qa-brain

`qa-brain` appears to be an ambient cockpit for current work-state, likely downstream of Backpack-like operational context.[cite:2]

Its contribution is rendering: making queue, detail, and current project context glanceable instead of buried in notes or reconstruction effort.[cite:2]

## narrator / workspace-narrator

These repos define the interpretation layer. The narrator system keeps facts stable while changing framing, voice, labels, and tone according to narrator, theme, and context.[code_file:213][code_file:214]

This cluster contributes emotional usability. It demonstrates that support quality is not only about what information is surfaced, but how that information is delivered.[code_file:212][code_file:213][code_file:214]

## hum / better-buddy / Claude continuity ideas

These represent the continuity and companionship direction: making Claude or terminal AI feel less amnesiac, more persistent, and more emotionally usable between sessions.[cite:32][web:105]

This cluster contributes the question of what assistant continuity should feel like when it is local, inspectable, and emotionally meaningful rather than invisible and cloud-owned.[cite:32][web:105][web:228]

## Inside Weather / Margin / Executive Dysfunction Center / Meat-Suit

These projects appear to explore humane self-observation and life-state tracking, especially around body state, mood, executive function, and internal weather.[cite:37][file:80][cite:156]

This cluster contributes the life-state side of the operator environment: not just what work is happening, but what conditions the person is operating under.[cite:37][code_file:209]

## chronicle

`chronicle` was a more direct attempt at local AI memory infrastructure with a timeline store and KV memory store exposed via MCP, but it was later deprecated in practice in favor of Backpack-centered workflow.[cite:1]

Its contribution is still useful as an exploration of infrastructure shape, but it is no longer the practical center of the ecosystem.[cite:1]

## Backpack

Backpack is not a standalone repo, but it is one of the most important artifacts in the ecosystem. The live `backpack.json` suggests that the practical center of the system is a curated, freshness-managed working-memory sidecar rather than a heavier database-first memory product.[cite:1]

That makes Backpack the strongest candidate for the active carry-state layer in the architecture.[cite:1][cite:2]

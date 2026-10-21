# Agent instructions

Read `README.md` for project setup and existing contribution guidance.

## Jules PR titles

Before opening or updating a PR, set its title to `type: description` or
`type(scope): description`. Start with a lowercase Conventional Commit type,
not a leading emoji or bracketed task category. Use a lowercase imperative
description, such as `perf: optimize search`, `test: cover invalid inputs`,
`refactor: extract helpers`, or `fix: handle failed requests`.

Release conventions repairs recognized, same-repository Jules titles before
the existing title validator runs. This is a fallback; create a compliant
title directly. Existing valid titles and other contributors are unchanged.
Check the title-policy fixtures with
`node --test .github/tests/jules-pr-titles.check.cjs`.

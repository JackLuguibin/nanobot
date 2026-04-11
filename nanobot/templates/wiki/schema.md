# Wiki schema (nanobot)

Copy or merge this file to **`wiki/schema.md`** in your workspace. It is **prepended** to wiki context for the agent, Dream, and `/wiki-archive` when present. Edit it to match your project.

## Purpose

- **SOUL.md** / **USER.md** — who the bot is and who the user is.
- **This file** — how pages under `wiki/` should be shaped (structure, linking, optional frontmatter).

## Raw sources (immutable)

- Place curated documents under **`raw/sources/`** (and optional **`raw/assets/`**). The LLM **reads** them for `/wiki-ingest` and **must not edit** anything under `raw/` — only write compiled notes under `wiki/`.
- Version-control `raw/` like the rest of the workspace so sources stay reproducible.

## Conventions

- **Directories**: keep **entities** under `wiki/entities/`, **concepts** under `wiki/concepts/`, **source-backed summaries** under `wiki/sources/`. Topic archive merges from `/wiki-archive` stay at `wiki/<category-slug>.md` (root) unless you adopt a different rule here.
- **Wikilinks**: use `[[Page Name]]` for cross-references; resolve paths consistently (e.g. `wiki/concepts/<slug>.md`). Match Dream / `wiki/index.md` guidance.
- **Topic archives**: `/wiki-archive` appends dated blocks under `wiki/<category-slug>.md`; keep `## Summary` at the start of each entry for a good index blurb.
- **Optional YAML frontmatter** on hand-written pages, for Obsidian or tooling, for example:

```yaml
---
title: "Short title"
type: concept
updated: 2026-04-11
---
```

- **Stable slugs**: category slugs stay `kebab-case` ASCII; display titles may be any language.

## Out of scope

Do not put secrets, API keys, or one-off session noise here — those belong in `memory/history.jsonl` or ephemeral chat, not durable wiki rules.

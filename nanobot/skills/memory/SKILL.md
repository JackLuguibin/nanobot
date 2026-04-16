---
name: memory
description: Two-layer memory system with Dream-managed knowledge files.
always: true
---

# Memory

## Structure

- `SOUL.md` — Bot personality and communication style. **Managed by Dream.** Do NOT edit.
- `USER.md` — User profile and preferences. **Managed by Dream.** Do NOT edit.
- `memory/MEMORY.md` — Long-term facts (project context, important events). **Managed by Dream.** Do NOT edit.
- **`raw/sources/`** (and optional **`raw/articles/`**, **`raw/papers/`**, **`raw/transcripts/`**) — Immutable source files for **`/wiki-ingest`**; the agent must not modify `raw/`. Optional **`raw/assets/`** for attachments.
- `wiki/` — Multi-page compiled knowledge (`wiki/index.md`, optional **`wiki/log.md`** timeline, topic pages). Standard subdirs **`wiki/entities/`**, **`wiki/concepts/`**, **`wiki/sources/`**, **`wiki/comparisons/`** (created on first wiki write). Optional **`wiki/schema.md`** defines structure; when present it is injected first into wiki context (Dream, agent, `/wiki-archive`). Layout helpers: **`nanobot.llm_wiki`**. **Managed by Dream** (except user-driven commands). Do NOT edit wiki unless the user explicitly asks you to change a page.
- `memory/history.jsonl` — append-only JSONL, not loaded into context. Prefer the built-in `grep` tool to search it.

## Search Past Events

`memory/history.jsonl` is JSONL format — each line is a JSON object with `cursor`, `timestamp`, `content`.

- For broad searches, start with `grep(..., path="memory", glob="*.jsonl", output_mode="count")` or the default `files_with_matches` mode before expanding to full content
- Use `output_mode="content"` plus `context_before` / `context_after` when you need the exact matching lines
- Use `fixed_strings=true` for literal timestamps or JSON fragments
- Use `head_limit` / `offset` to page through long histories
- Use `exec` only as a last-resort fallback when the built-in search cannot express what you need

Examples (replace `keyword`):
- `grep(pattern="keyword", path="memory/history.jsonl", case_insensitive=true)`
- `grep(pattern="2026-04-02 10:00", path="memory/history.jsonl", fixed_strings=true)`
- `grep(pattern="keyword", path="memory", glob="*.jsonl", output_mode="count", case_insensitive=true)`
- `grep(pattern="oauth|token", path="memory", glob="*.jsonl", output_mode="content", case_insensitive=true)`

## Manual archive

- **`/wiki-archive`** — Model returns **JSON** (array of `{ category_slug, display_title, page_kind, entry_markdown }`). **`page_kind`** routes into `wiki/` subdirs (`entity` / `concept` / `source` / `comparison`) or root (`topic`). Updates **Topic archives** and **`wiki/log.md`**, then **clears** the session and injects the full index. Dedup: `memory/wiki_archive_dedup.json`. Legacy plain-text `CATEGORY_SLUG:` lines still imply **topic** (root).

## Automatic wiki (gateway / `nanobot agent` interactive)

Configured under **`agents.defaults`** in config (JSON / YAML):

| Key | Meaning |
|-----|---------|
| `autoWikiArchiveAtContextFraction` | Already default `0.8` — auto **`/wiki-archive`** when estimated prompt tokens exceed this fraction of the context window. Set `null` to disable. |
| `autoWikiIngestIntervalMinutes` | When set (e.g. `15`), the loop polls every ~60s; if **`raw/`** text fingerprint changed and the cooldown elapsed, runs **`/wiki-ingest`** once. State: `memory/wiki_automation.json`. `null` = off (default). |
| `autoWikiLintIntervalMinutes` | When set (e.g. `1440`), scheduled **`wiki-lint`** on that interval; appends **`wiki/log.md`** only if broken links or orphans exist. First run waits one full interval after gateway start. `null` = off (default). |
| `autoWikiLintAfterWikiWrite` | Default `false` — set `true` to run lint after successful **wiki-archive** or **wiki-ingest** (manual or auto) and append `wiki/log.md` only if there are issues. |

**`/wiki-save-answer`** is not automated (you must choose what to save). OpenAI-compatible **API-only** mode does not run the long-lived `agent.run()` loop, so these automations apply to **gateway** and **CLI interactive** sessions.
- **`/wiki-ingest`** — Reads text files from **`raw/sources/`** (optional filter substring) and merges model output into `wiki/` the same way as archive. Appends **`wiki/log.md`**.
- **`/wiki-lint`** — Reports broken `[[wikilinks]]` and orphan pages; appends **`wiki/log.md`**.
- **`/wiki-save-answer`** — Saves the last assistant reply under **`wiki/queries/<slug>.md`** (optional slug argument).

## Wiki revision (when the user wants to update existing pages)

- **New facts in chat** — Prefer **`/wiki-archive`** with the same `category_slug` (appends a dated section). Do not rely on `/wiki-save-answer` to fix a wrong `wiki/entities/` page.
- **Updated material under `raw/sources/`** — User adds or changes files, then **`/wiki-ingest`**.
- **Multi-page or narrative coherence** — **Dream** may edit `wiki/`; do not fight Dream’s ownership unless the user asks for a direct file edit.
- **Tiny fixes** — User may edit markdown directly; suggest **`/wiki-lint`** after link changes.

Archive and ingest **merge** into existing slugs; full section replacement without history is **manual edit** or **Dream**, not a separate slash command.

## Important

- **Do NOT edit SOUL.md, USER.md, or MEMORY.md.** They are automatically managed by Dream.
- If you notice outdated information, it will be corrected when Dream runs next.
- Users can view Dream's activity with the `/dream-log` command.

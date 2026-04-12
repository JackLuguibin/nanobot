# Wiki index

- **Raw sources** — Put immutable documents in `raw/sources/` and/or `raw/articles/`, `raw/papers/`, `raw/transcripts/` (see `nanobot/templates/raw/`) and run **`/wiki-ingest`** to compile into `wiki/` without modifying `raw/`.
- **Layout** — `wiki/entities/` (people, orgs, products), `wiki/concepts/` (theories, methods), `wiki/sources/` (source-backed summaries), `wiki/comparisons/` (side-by-side analyses). These dirs are created automatically on first wiki write; copy `README.md` stubs from `nanobot/templates/wiki/<dir>/` if you want the same hints in your vault.
- **Queries** — Optional `wiki/queries/` holds answers saved with **`/wiki-save-answer`**.
- **Log** — `wiki/log.md` is append-only: each `/wiki-archive`, Dream run (with edits), `/wiki-lint`, etc. adds a short `## [date] kind | summary` line. Use it as a human timeline alongside Git.
- **Schema (optional)** — `wiki/schema.md` defines how pages should be shaped (linking, frontmatter). When present, it is loaded before other wiki files for Dream, the agent, and `/wiki-archive`. Start from `nanobot/templates/wiki/schema.md` if you need a template.
- **Topic archives** — `/wiki-archive` asks the model for **`page_kind`** per entry (`entity` / `concept` / `source` / `comparison` / `topic`) so files go under `wiki/entities/`, `wiki/concepts/`, `wiki/sources/`, `wiki/comparisons/`, or wiki root automatically. Entries in each file are separated by `---` and `## YYYY-MM-DD HH:MM`.
- **Dream** may add or edit pages under `wiki/`, including `entities/`, `concepts/`, and `sources/`.

## Revision strategy

How to **update** canonical pages (`wiki/entities/`, `wiki/concepts/`, `wiki/sources/`, or root topic files) depends on where the new truth comes from:

| Situation | Prefer |
|-----------|--------|
| New or corrected facts appeared **in the current chat** | **`/wiki-archive`** — reuse the same `category_slug` to **append** a new dated `##` section. Older sections stay as history. |
| Truth lives in **files under `raw/sources/`** | **`/wiki-ingest`** — re-run after you add or change raw files; ingest only writes `wiki/`, never `raw/`. |
| Cross-file coherence, or tie wiki to **`memory/history.jsonl`** / **`memory/MEMORY.md`** | **Dream** — scheduled or `/dream`; it may edit several wiki files in one pass. |
| Small fix (typo, link, wording) | **Edit the `.md` file** in the workspace; Git records it. Run **`/wiki-lint`** if wikilinks moved. |
| Preserve a **good assistant answer** as a snapshot | **`/wiki-save-answer`** — writes under **`wiki/queries/`** only; it does not replace entity/concept pages. |

**Semantics:** `/wiki-archive` and `/wiki-ingest` **merge** entries into existing slugs (append by timestamp). To **replace** a whole section without keeping the old text, edit the file directly or ask Dream for a surgical rewrite.

Link related pages with wikilinks, e.g. `[[OAuth flow]]` → `wiki/concepts/oauth-flow.md` (path rules in `wiki/schema.md`).

## Topic archives

- *(`/wiki-archive` appends a searchable line here for each merge.)*

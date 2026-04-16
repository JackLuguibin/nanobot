{% if wiki_schema %}
## Workspace wiki schema (must follow)

{{ wiki_schema }}

---

{% endif %}
{% if wiki_catalog %}
## Existing wiki pages (reuse slugs when the topic matches)

Prefer **`category_slug`** values that already appear below (same file = same slug over time). Do **not** create a new near-duplicate slug (e.g. `foo` vs `foo-overview`) for the same subject; merge into the existing slug and matching `page_kind`.

{{ wiki_catalog }}

---

{% endif %}
You ingest **immutable raw text files** from `raw/` (paths under `raw/sources/`, `raw/articles/`, `raw/papers/`, or `raw/transcripts/` are provided in the user message). Produce structured wiki updates as **JSON only** — same schema as `/wiki-archive`.

Classify each extracted topic with **`page_kind`**: `entity` | `concept` | `source` | `comparison` | `topic` (see `agent/wiki_archive.md`).

## Output format (required)

Output **only** a JSON array. Each element:

| Field | Meaning |
|-------|---------|
| `category_slug` | `kebab-case` English filename stem |
| `display_title` | Short title for `wiki/index.md` |
| `page_kind` | `entity` / `concept` / `source` / `comparison` / `topic` |
| `entry_markdown` | Start with `## Summary`, then optional details. No level-1 `#` inside the entry. |

Do not invent facts not supported by the raw text. Summarize; do not paste entire sources.

If nothing usable is present, output:

```json
[{"category_slug": "empty-ingest", "display_title": "", "page_kind": "topic", "entry_markdown": "# (empty)"}]
```

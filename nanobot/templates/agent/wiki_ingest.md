{% if wiki_schema %}
## Workspace wiki schema (must follow)

{{ wiki_schema }}

---

{% endif %}
You ingest **immutable raw text files** from `raw/sources/` (paths are provided in the user message). Produce structured wiki updates as **JSON only** — same schema as `/wiki-archive`.

Classify each extracted topic with **`page_kind`**: `entity` | `concept` | `source` | `topic` (see `agent/wiki_archive.md`).

## Output format (required)

Output **only** a JSON array. Each element:

| Field | Meaning |
|-------|---------|
| `category_slug` | `kebab-case` English filename stem |
| `display_title` | Short title for `wiki/index.md` |
| `page_kind` | `entity` / `concept` / `source` / `topic` |
| `entry_markdown` | Start with `## Summary`, then optional details. No level-1 `#` inside the entry. |

Do not invent facts not supported by the raw text. Summarize; do not paste entire sources.

If nothing usable is present, output:

```json
[{"category_slug": "empty-ingest", "display_title": "", "page_kind": "topic", "entry_markdown": "# (empty)"}]
```

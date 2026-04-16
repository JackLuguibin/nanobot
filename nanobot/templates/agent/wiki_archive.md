{% if wiki_schema %}
## Workspace wiki schema (must follow)

{{ wiki_schema }}

---

{% endif %}
You classify lines from a chat transcript into **one or more knowledge categories**. For each category you assign a **page kind** so the entry is stored automatically under the right folder (Karpathy-style layout).

| `page_kind` | Stored as |
|-------------|-----------|
| `entity` | `wiki/entities/<category-slug>.md` — people, organizations, products, named tools |
| `concept` | `wiki/concepts/<category-slug>.md` — methods, patterns, theories, technical ideas |
| `source` | `wiki/sources/<category-slug>.md` — digest of a specific document, paper, or transcript line of inquiry |
| `comparison` | `wiki/comparisons/<category-slug>.md` — side-by-side analyses, A-vs-B, tradeoff tables |
| `topic` | `wiki/<category-slug>.md` — mixed notes, procedures, or when classification is unclear |

One slug still maps to **one file over time** (append-only within that file). Choose the best `page_kind` from the transcript; use `topic` if unsure.

## Output format (required)

Output **only** a JSON array (no markdown outside the array, or wrap the array in a single ` ```json ` fenced block if you prefer).

Each element must be an object with:

| Field | Meaning |
|-------|---------|
| `category_slug` | `kebab-case`, English: lowercase letters, digits, hyphens only (e.g. `auth-oauth`, `db-postgres`). One slug = one wiki file over time. |
| `display_title` | Short human-readable title (Chinese or English) for `wiki/index.md`. |
| `page_kind` | One of `entity`, `concept`, `source`, `comparison`, `topic` (see table above). |
| `entry_markdown` | Markdown for **this archive only** for that category: start with `## Summary` (1–2 factual sentences for the index blurb), then optional `## Details`, bullets, etc. No level-1 `#` heading inside the entry. |

### Multiple topics

If the transcript clearly contains **several independent knowledge domains** (e.g. authentication **and** database schema **and** deployment), emit **one object per domain** with a **different** `category_slug` for each. Split rather than stuffing unrelated content into one slug.

If everything belongs to one domain, emit **a single-element array**.

### Rules

- Keep claims tied to the transcript; do not invent facts.
- Summarize tool results; do not paste huge raw logs.
- Do not duplicate the same semantic content under two slugs unless the user explicitly discussed two separate tracks.

### Empty transcript

If there is nothing to save, output exactly:

```json
[{"category_slug": "empty-session", "display_title": "", "page_kind": "topic", "entry_markdown": "# (empty session)"}]
```

"""LLM Wiki — standalone filesystem helpers (schema + wiki context assembly).

This package encodes the Karpathy / llm-wiki layout: optional structural rules in
``wiki/schema.md``, topic pages under ``wiki/``, ``index.md`` as catalog, optional
``raw/sources`` for immutable inputs. It does not depend on
:class:`~nanobot.agent.memory.MemoryStore`; callers pass a workspace
:class:`~pathlib.Path`.

Public API
----------

- :data:`WIKI_DIR_NAME`, :data:`SCHEMA_FILENAME` — path segments
- :func:`wiki_schema_rel` — relative path string for the schema file
- :func:`read_schema` — load ``wiki/schema.md``
- :func:`list_wiki_page_paths` — ordered list of wiki markdown paths
- :func:`ensure_standard_wiki_dirs` — create ``entities/``, ``concepts/``, ``sources/``
- :func:`build_wiki_context` — bounded prompt text (schema first, then pages; optional relevance ranking)
- Raw helpers in :mod:`nanobot.llm_wiki.raw`
- Lint in :mod:`nanobot.llm_wiki.lint`
"""

from nanobot.llm_wiki.context import (
    DEFAULT_MAX_TOTAL_CHARS,
    DEFAULT_SCHEMA_CONTEXT_CAP,
    SCHEMA_FILENAME,
    STANDARD_WIKI_SUBDIRS,
    WIKI_DIR_NAME,
    build_wiki_context,
    ensure_standard_wiki_dirs,
    list_wiki_page_paths,
    read_schema,
    wiki_schema_rel,
)
from nanobot.llm_wiki.lint import WikiLintReport, format_wiki_lint_message, run_wiki_lint
from nanobot.llm_wiki.raw import (
    RAW_ASSETS_REL,
    RAW_DIR_NAME,
    RAW_SOURCES_REL,
    RAW_SOURCE_TEXT_EXTENSIONS,
    ensure_raw_directories,
    list_raw_source_files,
)

__all__ = [
    "DEFAULT_MAX_TOTAL_CHARS",
    "DEFAULT_SCHEMA_CONTEXT_CAP",
    "RAW_ASSETS_REL",
    "RAW_DIR_NAME",
    "RAW_SOURCES_REL",
    "RAW_SOURCE_TEXT_EXTENSIONS",
    "SCHEMA_FILENAME",
    "STANDARD_WIKI_SUBDIRS",
    "WIKI_DIR_NAME",
    "WikiLintReport",
    "build_wiki_context",
    "ensure_raw_directories",
    "ensure_standard_wiki_dirs",
    "format_wiki_lint_message",
    "list_raw_source_files",
    "list_wiki_page_paths",
    "read_schema",
    "run_wiki_lint",
    "wiki_schema_rel",
]

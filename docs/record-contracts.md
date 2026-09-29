# Detached record contracts

Holder record exports are plain dictionaries with stable field names and
standard-library types. They own no native resources and remain readable,
serialisable, and safe to pass elsewhere after their originating `Context` is
closed.

Identifiers are opaque strings. Timestamps are integer Unix seconds exactly as
reported by libholder; the typed models additionally expose timezone-aware UTC
`datetime` properties. Nullable native fields are always present and use
`None`. Empty exports are ordinary empty lists; `PROJECT_RECORD_FIELDS` and
`CARD_RECORD_FIELDS` describe their schema without requiring a sample row.

## `ProjectRecord`

| Field | Python type | Meaning |
|---|---|---|
| `project_id` | `str` | Stable project identifier |
| `name` | `str` | Project display name |
| `root_path` | `str` | Project storage root reported by libholder |
| `privacy_mode` | `str` | Current privacy mode |
| `id_scheme` | `str` | Identifier scheme reported by libholder |
| `created_at` | `int` | Creation time as Unix seconds |
| `updated_at` | `int` | Last update time as Unix seconds |
| `git_remote_url` | `str \| None` | Configured Git remote URL |
| `git_provider` | `str \| None` | Configured Git provider |
| `project_key_id` | `str \| None` | Encrypted-project key identifier |

## `CardRecord`

| Field | Python type | Meaning |
|---|---|---|
| `card_id` | `str` | Stable card identifier |
| `project_id` | `str` | Owning project identifier |
| `title` | `str` | Card title |
| `content` | `str` | Markdown body |
| `rel_path` | `str` | Card path relative to its project root |
| `parent_card_id` | `str \| None` | Parent card identifier |
| `sort_key` | `float` | Sibling ordering key |
| `created_at` | `int` | Creation time as Unix seconds |
| `updated_at` | `int` | Last update time as Unix seconds |
| `deleted_at` | `int \| None` | Soft-deletion time; live exports use `None` |

`CardCollection` currently exports live cards. Tags, connections, milestones,
and trashed cards are separate future record contracts rather than nested
columns in `CardRecord`.

## Extraction behavior and limitations

`holder_project_list` provides project metadata in one call.
`holder_card_list` provides card metadata for one project, but it does not
include body content. Consequently, complete card extraction currently uses:

1. one project-list call for a cross-project export;
2. one card-list call for each project; and
3. one `holder_card_get_content` call for each card.

This is correct but creates an N+1 content-read pattern that may matter for
large pandas or ML exports. The public C API's backup snapshot endpoint can
page bodies together with links and milestones, but it is backup-specific and
does not carry all normal card metadata (`rel_path`, hierarchy, ordering, tags,
or deleted state). It is therefore not used as an undocumented general-purpose
query.

Exports are detached snapshots, but the current C API does not provide a
single transactional bulk read spanning project metadata, cards, and content.
Concurrent writes may therefore be observed between calls. A future core API
for paginated, complete card records would remove the N+1 reads and define
snapshot consistency explicitly.

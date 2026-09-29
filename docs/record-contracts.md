# Detached record contracts

Holder record exports are plain dictionaries with stable field names and
standard-library types. They own no native resources and remain readable,
serialisable, and safe to pass elsewhere after their originating `Context` is
closed.

Identifiers are opaque strings. Timestamps are integer Unix seconds exactly as
reported by libholder; the typed models additionally expose timezone-aware UTC
`datetime` properties. Nullable native fields are always present and use
`None`. Empty exports are ordinary empty lists; `PROJECT_RECORD_FIELDS` and
the corresponding `*_RECORD_FIELDS` constants describe their schema without
requiring a sample row.

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

## `CardMetadataRecord`

| Field | Python type | Meaning |
|---|---|---|
| `card_id` | `str` | Stable card identifier |
| `project_id` | `str` | Owning project identifier |
| `title` | `str` | Card title |
| `rel_path` | `str` | Card path relative to its project root |
| `parent_card_id` | `str \| None` | Parent card identifier |
| `sort_key` | `float` | Sibling ordering key |
| `created_at` | `int` | Creation time as Unix seconds |
| `updated_at` | `int` | Last update time as Unix seconds |
| `deleted_at` | `int \| None` | Soft-deletion time; live exports use `None` |

This inexpensive contract is returned by `cards.to_records()`. It comes from
`holder_card_list` and does not open or decrypt card files.

## `CompleteCardRecord`

`CompleteCardRecord` contains every `CardMetadataRecord` field plus:

| Field | Python type | Meaning |
|---|---|---|
| `content` | `str` | Markdown body read from the authoritative card file |

It is returned by `cards.to_records(include_content=True)`. The earlier
`CardRecord` name remains an alias of this complete contract, and
`CARD_RECORD_FIELDS` remains an alias of `COMPLETE_CARD_RECORD_FIELDS`.

`CardCollection` currently exports live cards. Tags, connections, milestones,
and trashed cards are separate future record contracts rather than nested
columns in either card record contract.

## Extraction behavior and limitations

Metadata-only extraction calls `holder_card_list` once per selected project.
Complete extraction uses `holder_card_list_complete_page` and follows its
opaque cursor until exhausted, avoiding one native operation per card. Each
page is ordered by `card_id`, contains live cards only, and reads bodies from
their authoritative durable files rather than the disposable FTS index.

Metadata selection and body reads within one complete page share libholder's
process-local project operation lock. Supported operations through the same
process therefore cannot interleave inside that page. There is deliberately no
snapshot promise across pages or projects, and the lock cannot coordinate with
another process or direct filesystem/database edits. A missing card file, or a
read, decryption, or parsing failure, fails the whole page rather than emitting
an empty substitute body.

All returned dictionaries are detached snapshots: they hold copied Python
values and remain usable after their originating context closes.

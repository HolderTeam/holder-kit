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

`CardCollection` currently exports live cards. Tags, milestones and
trashed cards are separate future record contracts rather than nested
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

## pandas conversion

`projects.to_dataframe()` and `cards.to_dataframe()` use these record-field
constants as their authoritative column order. Card conversion is metadata-only
by default; `include_content=True` selects the complete contract and the
paginated authoritative-body operation.

Identifiers and text use pandas' nullable `string` dtype, `sort_key` uses
`float64`, and Holder's integer Unix timestamps become timezone-aware
`datetime64[ns, UTC]` columns. Nullable timestamps use `NaT`; nullable strings
use `pd.NA`. Empty DataFrames preserve the same columns and dtypes as populated
ones. Content that was not requested has no column, while an authoritative
empty card body is the empty string in a complete table.

DataFrames contain copied Python/pandas values, retain no native context, and
have no automatic write-back behavior. Editing one cannot modify Holder.
Complete extraction retains the consistency limits above: each page is guarded
by the process-local project lock, but a DataFrame assembled across pages or
projects is not a transactionally consistent snapshot.

## `ConnectionRecord`

`context.connections.to_records(project_id=None)` exports explicit outgoing
links from selected live source cards. Each link appears once, not again as a
backlink. Core's automatic parent/children hierarchy and inline `[[wikilinks]]`
are excluded. Identifiers retain core's names, including `to_card_id` for
non-card targets; use `to_type` to distinguish those targets.

| Field | Python type | Meaning |
|---|---|---|
| `project_id` | `str` | Source card's owning project |
| `from_card_id` | `str` | Source card identifier |
| `to_card_id` | `str` | Target identifier |
| `to_type` | `str` | Core target type, such as `card` or `resource` |
| `kind` | `str` | Relationship kind; custom kinds are allowed |
| `label` | `str \| None` | Optional connection label |
| `created_at` | `int` | Core timestamp in Unix seconds; core refreshes it on upsert |
| `to_title` | `str \| None` | Resolved target card title, or `None` |

Core has no separate connection ID. Identity is the tuple
`(project_id, from_card_id, to_card_id, to_type, kind)`. Several kinds may connect
the same ordered pair; reverse-direction links and self-links are distinct.
`CONNECTION_RECORD_FIELDS` defines column order, including for empty exports.
The pandas adapter uses nullable string columns and UTC timestamps with the
same rules as the other tables. Join `from_card_id` to card records' `card_id`,
and join card targets by `to_card_id` after selecting `to_type == "card"`.

Extraction first selects card metadata and then calls `holder_card_list_links`
once per source card. It does not read bodies or provide an atomic snapshot
across cards/projects. Errors propagate instead of returning a partial list.
Targets may be outside the selected project, unresolved, or trashed; target
liveness is not guaranteed by this export. Records retain no context handles.

## NetworkX conversion

`Context.to_networkx()` uses the shared card and connection record contracts,
with optional authoritative bodies via `include_content=True`. The output is a
directed multigraph, preserving distinct connection kinds as edge keys, all
selected cards including isolates, and the original record values as attributes.
It reads connections for the same selected source-card records, without a
second card selection. Extraction still spans separate core calls and has no
whole-graph snapshot guarantee.

Selected card nodes have `exported=True`. Referenced card targets lacking a
selected record receive a minimal node containing `card_id`, core's nullable
target title and `exported=False`. This preserves outgoing cross-project and
unresolved connections without claiming complete metadata for those endpoints.
Non-card connections are preserved by records/DataFrames but omitted from the
card graph. Hierarchy remains a node attribute, not a fabricated explicit edge.
All graph data is detached; mutation has no automatic write-back.

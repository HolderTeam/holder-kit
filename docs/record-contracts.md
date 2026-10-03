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

`CardCollection` currently exports live cards. Tags have a separate membership
contract below; milestones and trashed cards remain future contracts rather than nested
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

## Combined DataFrames

`Context.to_dataframes(project_id=None, include_content=False)` returns a
`DataFrames` typed dictionary with four named tables: `projects`,
`cards`, `connections` and `tags`. Each table uses its existing record-field constants,
column order and pandas dtypes. The default cards table is metadata-only;
`include_content=True` requests authoritative bodies through core's complete
card pages. pandas remains optional and is checked before any extraction.

The method selects projects once, extracts cards for those projects and reads
outgoing connections and tag memberships for those same selected source-card records. It does not
repeat card selection to assemble either table. With no project ID,
all projects from that initial selection are exported. With an ID, only that
project and its source cards are exported. An unknown project ID returns four
empty tables with their full schemas; an existing empty project retains its
project row and empty cards/connections/tags tables.

Join `cards.project_id` and `connections.project_id` to `projects.project_id`,
and `connections.from_card_id` to `cards.card_id`. Outgoing targets can be
outside the selected project, unresolved, trashed or non-card resources. Those
connections are preserved without adding target cards/projects to the tables;
filter `to_type == "card"` before joining `to_card_id` to exported card IDs and
use a left join if you need to retain targets absent from that selection.

The tables are detached but **not an atomic snapshot**. Project reads,
card pages and per-card connection/tag reads are separate core operations. Changes
can occur between them, and no export-wide transaction or lock is held. Core
failures propagate rather than returning a partial dictionary. Tables remain
usable after context closure, and editing any table never writes to Holder.

## `TagRecord` and semantic tag operations

`context.tags.to_records(project_id=None)` exports one row per normalized tag
on each selected live card. Repeated occurrences are collapsed by core. Column
order is `TAG_RECORD_FIELDS`: `project_id`, `card_id`, `tag` (strings), then
`editable` (boolean). Identity is `(project_id, card_id, tag)`; core supplies
neither a tag UUID nor a membership timestamp through this API, so none is invented.
The pandas adapter and combined `tags` table use nullable `string` columns and
nullable `boolean` for `editable`, even when empty. Join on `project_id` and
`card_id` to the cards table, and on `project_id` to projects.

The normalized tag list is read from core's extracted index, in alphabetical
order. `editable` is membership in core's trailing-tag-line list, read from
the authoritative body; it is not a guarantee that removing that occurrence
will leave the card untagged. A tag may also occur in prose. There is one
indexed tag read per selected card and, for tagged cards, one editable-list
read. These separate reads do not form an atomic snapshot. No Python-side
Markdown parsing or extra body/content column is introduced.

`tags.list(card_id)` returns normalized names; `tags.list_editable(card_id)`
returns trailing-line names in core's order. `tags.project_counts(project_id)`
returns `ProjectTagRecord` dictionaries (`project_id`, `tag`, integer `count`),
ordered by count descending then tag ascending. `tags.cards_with_tag(project_id,
tag)` returns `TaggedCardRecord` dictionaries (`card_id`, `title`), using
core's case-insensitive live-card search; equal-time matches have no promised
tie ordering. Unknown projects yield empty query/export results. Direct reads
or mutations for unknown cards raise `HolderError`.

`tags.add(card_id, tag)` returns `TagAddResult.ADDED` or `.ALREADY_PRESENT`.
Core lowercases a valid bare tag and adds it to the trailing tag line only if
it does not occur anywhere in the body. `tags.remove(card_id, tag)` returns
`TagRemoveResult.REMOVED`, `.NOT_PRESENT` or
`.PRESENT_OUTSIDE_EDITABLE_TAG_LINE`; it never rewrites prose. `REMOVED` means
the trailing occurrence was removed, not necessarily that the tag disappeared
from the card. These `IntEnum` members mirror core statuses; successful changes
have numeric value zero, so compare named members rather than testing truthiness.
Malformed tags raise `ValueError`; non-string arguments raise `TypeError`.
Core owns tag grammar, extraction, durable edits and reindexing. No bulk/atomic
mutation contract is implied, and previously detached card models/tables do not
refresh automatically after a mutation.

Core's editable-list read currently substitutes an empty body if a card file
is missing. The flag can therefore be false in that situation despite an indexed
tag remaining present. By contrast, `include_content=True` still uses complete
card extraction, whose missing-body failure propagates. Native read failures
propagate without returning partial exports; closed contexts raise `RuntimeError`.

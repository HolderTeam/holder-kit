# Detached record contracts

Holder Kit record exports are plain dictionaries with stable field names and
standard-library types. They own no native resources and remain readable,
serialisable, and safe to pass elsewhere after their originating `Project` or
`Context` is closed. `Project` itself is live: use `project.to_record()` to
capture descriptive values before closing. Its card, connection, tag, milestone,
DataFrame and graph exports automatically select that project's data. The
advanced Context methods also accept explicit project IDs as described below.

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
contract below, as do milestones; trashed cards remain future contracts rather than nested
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

## Card batches

```python
for batch in project.cards(batch_size=256, include_content=True):
    analyse(batch)
```

Calling the cards collection returns a lazy iterator of lists. `batch_size`
must be a positive integer; it defaults to 256. Full batches contain that many
records, the last may be smaller, and an empty project yields no batches.
Iteration reads only the pages needed for the next batch and retains a bounded
number of records rather than the whole project. A batch larger than Core's
page limit is assembled from several pages. Memory also depends on card sizes
and any batches retained by your own code.

`include_content=False` is the default and yields `CardMetadataRecord` values
without opening card files. It uses Core's cursor-paged recent-card query,
ordered by `updated_at` and then `card_id`, both descending.
`include_content=True` yields `CompleteCardRecord` values in ascending `card_id`
order through the existing authoritative-body page operation. Existing
`.list()`, `.to_records()` and `.to_dataframe()` methods retain their behavior.

There is no snapshot across page calls. Keep the project open during iteration;
closing it makes unread batches unavailable, while batches already returned
remain usable. Changes between pages can affect which records are returned,
particularly when recency values change during metadata iteration. Read,
decryption or parse errors propagate; complete pages do not substitute missing
bodies or yield partial results from a failed page.

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
`DataFrames` typed dictionary with five named tables: `projects`,
`cards`, `connections`, `tags` and `milestones`. Each table uses its existing record-field constants,
column order and pandas dtypes. The default cards table is metadata-only;
`include_content=True` requests authoritative bodies through core's complete
card pages. pandas remains optional and is checked before any extraction.

The method selects projects once, extracts cards for those projects and reads
outgoing connections, tag memberships and milestones for those same selected source-card records. It does not
repeat card selection to assemble these tables. With no project ID,
all projects from that initial selection are exported. With an ID, only that
project and its source cards are exported. An unknown project ID returns five
empty tables with their full schemas; an existing empty project retains its
project row and empty cards/connections/tags/milestones tables.

Join `cards.project_id` and `connections.project_id` to `projects.project_id`,
and `connections.from_card_id` to `cards.card_id`. Outgoing targets can be
outside the selected project, unresolved, trashed or non-card resources. Those
connections are preserved without adding target cards/projects to the tables;
filter `to_type == "card"` before joining `to_card_id` to exported card IDs and
use a left join if you need to retain targets absent from that selection.

The tables are detached but **not an atomic snapshot**. Project reads,
card pages and per-card connection/tag/milestone reads are separate core operations. Changes
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

## Milestone records and operations

`context.milestones.list(card_id)` returns detached `MilestoneRecord` dictionaries
in core's ascending `start_at` order. `MILESTONE_RECORD_FIELDS` defines their schema:

| Field | Python type | Meaning |
|---|---|---|
| `milestone_id` | `str` | Core-generated milestone UUID |
| `card_id` | `str` | Owning card identifier |
| `start_at` | `int` | Start time in Unix seconds |
| `end_at` | `int \| None` | Optional end time; None denotes a point |
| `all_day` | `bool` | Core's all-day flag; no Python timezone/date normalization |
| `kind` | `str \| None` | Optional kind, including custom values |
| `description` | `str \| None` | Optional description |
| `created_at` | `int` | Core creation time in Unix seconds |
| `updated_at` | `int` | Core last-update time in Unix seconds |

`milestones.to_records(project_id=None)` selects live cards and reads their
milestones once per card. It returns `ProjectMilestoneRecord` dictionaries adding
`project_id` and `card_title` from the selected card metadata. Field order is
`PROJECT_MILESTONE_RECORD_FIELDS`: `project_id`, the milestone fields above, then
`card_title`. `milestones.in_range(project_id, from_at, to_at)` returns the same
contract, with the project ID supplied by the query and nullable `card_title`
resolved by core. It uses core's bulk calendar query and excludes trashed cards.
Unknown projects and empty selections yield empty results.

Range selection is `from_at <= start_at <= to_at`, **not interval overlap**.
A span beginning before the range is omitted even if it ends inside it. Reversed
query bounds return an empty list. Equal-start ordering is unspecified. Card-local
lists are start-ordered; whole-context exports preserve selected card order, not
a globally sorted calendar. Sort detached data explicitly when needed.

`milestones.to_dataframe()` and the combined `milestones` table preserve that
extended schema. IDs/text use nullable strings, `all_day` uses nullable `boolean`,
and all four time columns use `datetime64[ns, UTC]`; `end_at=None` becomes `NaT`.
Empty tables keep the same columns/dtypes. Join on `project_id` and `card_id` to
cards. Timestamps outside pandas' nanosecond range can remain valid core/record
values but cannot be represented by this DataFrame contract; conversion errors
propagate rather than silently clipping or changing precision.

### Explicit mutations and partial updates

`milestones.add(card_id, start_at, *, end_at=None, all_day=False, kind=None,
description=None)` returns the **full updated card milestone list**, not just the
new row. Each addition gets a new core ID; repeating a successful add creates
another milestone. Empty kind/description strings on add are normalized to None
by core. `milestones.remove(card_id, milestone_id)` returns None; absent IDs and
IDs owned by another card are no-ops, but an unknown card raises `HolderError`.

`milestones.update(project_id, card_id, milestone_id, changes)` accepts a typed
`MilestoneUpdate` dictionary and returns the single updated `MilestoneRecord`:

- Absent fields stay unchanged; an empty dictionary is a no-op for an existing,
  correctly owned live milestone.
- `end_at`, `kind` and `description` accept None to clear their value.
- `start_at` and `all_day` cannot be cleared; None raises `ValueError`.
- Unknown keys raise `ValueError`. Times must be signed 64-bit integer Unix
  seconds, not bool/float; flags must be bool; text must be str or None. Invalid
  Python field types raise `TypeError`, out-of-range integers `OverflowError`.
- Core verifies the matching project/card/milestone ownership and live-card
  status. Mismatch raises `HolderError`. An update creating `end_at < start_at`
  also raises `HolderError` through the current C ABI exception translation.

Core owns durable front-matter editing, index updates and Git commits; Python
does not parse or rewrite Markdown. Existing detached objects/records do not
refresh automatically. Valid calls on a closed context raise `RuntimeError`.
Failed reads abort exports without a partial result; no export-wide snapshot,
transaction, revision check or bulk mutation guarantee is implied.

### Current core limitations

The public add operation does not enforce the update operation's reversed-span
validation. Direct card-list/add/remove operations also do not expose the same
explicit live-card ownership check as update and the calendar query; use selected
live cards. Python preserves these contracts rather than duplicating domain policy.

Add/remove replace index rows before attempting their durable card-file write.
A missing file or another durable-write failure can therefore raise an error
after index changes already occurred. Update checks/reads the file before changing
the index, but none of these APIs promises an atomic multi-store transaction or
automatic rollback on every failure. Do not blindly retry failed additions or
infer unchanged storage from an exception. Strengthening this behavior requires
an owning core change, not a Python-only transaction wrapper.

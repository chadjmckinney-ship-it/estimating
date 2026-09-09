# The bid list — bids apart from projects (2026-09-09)

> **Later the same day:** Notion is pulled onto this list every hour by
> `backend/pull_notion_bids.py` (the bridge; see the runbook), and the 8:05
> bid email reads this list (`backend/email_current_bids.py`).

**Source:** the Notion "Concrete Estimating Bid list" (192 rows on 2026-09-09:
169 not started, 17 submitted, 2 in progress, 2 awarded, 2 canceled) and the
app's `projects` table, which was shaped from it in sql/004. **Chad,
2026-09-09:** "I want to switch from notion to this... no reason to pay for
notion if we have our own database going", then "instead of importing the
notions database into projects how about we create a new table and it be
seperate so we are not scrolling thru a ton of jobs to find the one i want..
then when we choose that we are estimating, it gets copied over" — and, on
the proposal, "build it".

## The shape

Bids are a stream; projects are the few that were chosen. So a **bid
request** is its own row (`sql/082`): name, GC, location, project type,
status, estimators, bid due with an optional time, the invite date, the plans
link, the notes written at intake, the bid price and its revision, the
Outlook message id that stops an invite being entered twice, and the Notion
page id the import carries. The Bid list page is where invites live; the
Projects page stays the short list of jobs being estimated.

**Estimate this** copies a bid into a new project — name, GC, location,
types, dates, plans link, notes, the people — links the two rows both ways,
marks the bid in progress, and opens the project. A second press is refused.
A bid whose invite already became a project by hand is refused too, on the
message id.

Statuses are Notion's, in the app's spelling: `not_started`, `in_progress`,
`submitted`, `awarded`, `canceled`. The bid keeps its own status after it is
estimated; submitted and awarded are typed on the bid list, as in Notion.

## The page

`Bids` in the nav. A table sorted by due date, overdue and this week called
out, with GC, location, types, estimators, status (changed in the row), the
notes, the plans link, and Estimate this or the project it became. Filters
by status, estimator and GC, a search across name, location, GC and notes,
and a board by status. A modal makes and edits a bid.

## The import

`backend/import_bid_requests.py <export.json>` loads a Notion export as the
Notion MCP hands it over (SQL or rows mode). It upserts by page id: a row
never touched in the app takes Notion's values afresh on a rerun; a row
edited here, or already estimated, is skipped. Duplicate names under one GC
and duplicate message ids are listed, not merged. Notion's datetimes become
the office's day and hour; `Cancelation` becomes `canceled`; estimators
match people by name.

## Held

`tests/test_bid_requests.py`: a bid becomes a project with every field and
the people carried and the link both ways; a second Estimate this is a 409;
a repeated message id is a 409; an import of Notion-shaped rows counts,
maps and dedupes, and reruns without doubling; the list filters; a
misspelled field is a 422. The screens test carries the bid modal's payload.

## Next on the box

The 8:05 bid-list email reads this table instead of Notion; the invite
intake writes to it with the message id as its key.

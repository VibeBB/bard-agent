# Sister cooperation (SLP v2)

ux-creator and bard exchange work through JSON files in the shared workspace —
no sockets, no MCP. bard's side lives in `plugins/bard/scripts/bard_liaison.py`
(stdlib mirror of the v2 shapes; nothing is imported from ux-creator).

## Interchange files

- `**/*.ux-request.json` — a sibling's request to bard (`target_agent: "bard"`;
  requests addressed to other sisters are ignored). Validated per
  [contracts.md](contracts.md).
- `<stem>.ux-response.json` — bard's answer beside the request. Written only by
  `bard_cli.py ux-respond`; the protect guard denies hand edits.
- `cues/<slug>/cues.json` — the deliverable ux-creator imports with
  `ux import --from bard`; firmware plays it directly (`freq_hz`, `start_ms`,
  `duration_ms`).

## Inbox states (`bard_cli.py ux-inbox`)

Scan: `**/*.ux-request.json`, depth ≤4, skipping `.git`/`.venv`/`node_modules`.
Output `{requests[], malformed[]}`; exit 0.

| State | Meaning |
| --- | --- |
| `new` | valid request, no valid response, inputs current, no blocking deps |
| `answered` | valid response exists and every request input's sha256 still matches `response.input_hashes` |
| `stale` | an input file changed or vanished since request/response |
| `blocked` | some `depends_on` id has no valid response file anywhere in the scan |
| malformed | unparseable/non-object request or response → `malformed[]` with reasons |

## Response rules (`ux-respond`)

- `reason` ≥20 chars unless status is `accepted`/`in_progress`.
- `done` requires ≥1 artifact (existing, workspace-contained), ≥1
  `decision_ref` (event_id in `decisions.jsonl`) and ≥1 `impression_ref`
  (event_id in `impressions.jsonl` or `vision-reviews.jsonl`), and refuses
  outright when any `gate_verdicts` entry is `fail` or `unknown` — answer
  `needs_info`/`rejected`/`deferred` with a real reason instead.
- `input_hashes` is recomputed from the current files; a missing request input
  is only allowed under the soft statuses.
- Response written as `<stem>.ux-response.json` (sorted keys, indent 2, UTF-8;
  overwrite allowed).

## What bard never does

bard never edits the sibling's `*.ux.json` contracts, never claims pass/fail
authority over the requester's gates, and never rewrites an answered request's
inputs. A request it cannot satisfy gets `needs_info`/`rejected`/`deferred`,
not silence.

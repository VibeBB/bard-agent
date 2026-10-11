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
  Refs resolve only against an intact VRP v2 chain: a log that fails
  `verify_log` (forged, edited or truncated lines) refuses every ref into it.
- `input_hashes` is recomputed from the current files; a missing request input
  is only allowed under the soft statuses.
- Response written as `<stem>.ux-response.json` (sorted keys, indent 2, UTF-8;
  overwrite allowed).

## What bard never does

bard never edits the sibling's `*.ux.json` contracts, never claims pass/fail
authority over the requester's gates, and never rewrites an answered request's
inputs. A request it cannot satisfy gets `needs_info`/`rejected`/`deferred`,
not silence.

## Change control (ECR/ECO)

A change to a file that another agent pins by sha256 goes through
UX-creator's change records, never a silent re-pin. There is no human
approval step.

1. Raise `<id>.ecr.json` with the reason, the proposal and each file to
   change with its current sha256.
2. After regenerating, write `<id>.eco.json` with each file's `before` and
   `after` sha256, the gate report that passed it (verdict `pass`, citing
   the `after` sha256) and the AI review findings with their dispositions.
   A `blocker` closes only as `fixed`, and the author cannot review its own
   change.
3. `ux change <eco>` (MCP `ux_change_check`) finds every consumer that pins
   a changed file. It fails if one still pins the old sha256, or re-pinned
   without being listed in the ECO.

AI review findings can only stop a change. This plugin's deterministic
gates and the change check decide. The record formats are in
[UX-creator-agent `docs/sister-cooperation.md`](https://github.com/VibeBB/UX-creator-agent/blob/main/docs/sister-cooperation.md#change-control-ecreco-and-design-review).

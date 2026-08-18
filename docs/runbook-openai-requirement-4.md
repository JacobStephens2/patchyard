# Runbook: OpenAI requirement 4, federation-rule revocation

Operator instructions for the attended run. This is the *how*; the contract,
the bounded-window rules, and the reasoning stay in
`docs/openai-lifecycle.md` § "Requirement 4: federation-rule revocation
capture", which remains normative. Where the two ever disagree, the lifecycle
document wins and this file is wrong.

Sensitive values are deliberately absent here. The identity-provider ID, the
mapped service-account ID, and the console URL are read from
`policy/openai-wif.json` and the provider page at the time of the run.

## Before you start

**This run needs separate authorization.** It makes three live OpenAI token
exchanges and two console mutations, and it revokes a live federation subject
mapping by editing its claim assertion to a run-scoped sentinel. Do not run it
during build, review, CI, or an unattended session.

> **The mutation is subject-expression revocation (A141). Never `remove` the
> mapping (A140).** On OpenAI, deleting the subject mapping cascades into
> destroying the mapped service account: the 2026-08-12 runs proved it (see
> the inert-leftovers table below), and recreating the mapping minted a
> same-named account with a new id, breaking the frozen policy pin and every
> result pinned to the old id. A140's replacement, `disable`, turned out to be
> a state the console cannot reach - the mapping card offers only Edit /
> delete / Details (run `openai-revocation-20260812-e2f0bcef3c` aborted safely
> at the mutation pause on exactly this). So the named actor **Edits the
> mapping's claim assertion** to
> `sub=patchyard-control-plane-REVOKED-<run id>`; restoration is editing the
> original expression back. The mapping stays present and enabled the whole
> run. Normative text: `docs/openai-lifecycle.md` § "The mutation is
> subject-expression revocation (A141); `remove` is forbidden (A140)".

**It is not finished until the original mapping is back.** Budget an
uninterrupted block. The run pauses twice for a 90-second settling floor and
otherwise moves at the speed you read the console.

**This run uses the A146 model-operated record.** A human-authored GitHub
comment on [Requirement 4: subject-expression revocation attended run](https://github.com/JacobStephens2/patchyard/issues/211)
authorizes one exact attempt. The named Codex task performs both Saves, makes
the five live readings, and writes the Result. The output is not an
Attestation and must never be described as human attestation, independent
evidence, or corroboration. A136 is unchanged for every other requirement.

Have the provider page open and confirm the subject mapping is **present,
enabled, and carrying the original claim assertion**. The run cannot start
from a missing or disabled mapping, or from one still carrying a `-REVOKED-`
sentinel left by a crashed window — the first reading is checked against
`require_active_mapping`, which also rejects sentinel residue. Residue is
self-describing: the expression names the run that broke. Repair it by editing
the original expression back at the console before starting a new run.

## Which way to drive it

Three ways, and the choice is made **at start time** by whether you launch under
the runner and whether you pass `--reply-group`. You cannot switch afterwards.

| | Browser form | Reply files | True terminal |
| :-- | :-- | :-- | :-- |
| Launch | runner, `--reply-group factory` | runner, `--reply-group factory` | collector directly, no runner |
| Where you answer | `/collectors` | write `replies/reply-N.json` | the tmux pane |
| Booleans | real controls | you hand-write JSON | you hand-write JSON |
| Pause steps | **Acknowledge** button | same file mechanism | retype `MUTATION COMPLETE` |
| Status | **needs the fix below** | works today | works today |

> **The browser form does not work until `factory/collectors-prompt-readable`
> is deployed.** `prepare_session` relaxes the session directory to
> `root:<group> 0750` and the replies inbox to `2770`, but `_write_json`
> published `prompt.json` and `status.json` at `0600 root:root` regardless, so
> `conductor` cannot read them. `collectors.py` cats both with `|| printf null`,
> and the page renders the session as **unknown with no form** while the
> collector waits. Confirmed live on 2026-08-10: both reads return
> `Permission denied` as `conductor`.
>
> The write path worked and the read path did not, so the front end could submit
> an answer it could never see the question for. Until that branch lands and
> `/opt/patchyard` is redeployed, use reply files.

**Answering under the runner without the browser.** This is the important one,
because it is not obvious: the runner binds `builtins.input` to the file
channel, so **the collector never reads stdin**. Typing into the tmux pane does
nothing at all. It polls for `replies/reply-<seq>.json` and blocks until it
appears.

The reply is an envelope, and a console reading goes inside it *as a string*:

```json
{"seq": 1, "value": "{\"console_location\": \"...\", \"enabled\": true, ...}"}
```

`_read_reply` requires the `seq` in the file to match the filename and the open
prompt, and `value` to be a string. Build it rather than hand-escaping it, and
**write to a temporary file and rename** — the runner polls on existence, so it
can read a partially written file and fail the run with `reply is not valid
JSON`:

```bash
S=/run/patchyard-openai/<RUN_ID>-session
SEQ=1
python3 - "$S" "$SEQ" <<'PY'
import json, os, sys, pathlib
session, seq = pathlib.Path(sys.argv[1]), int(sys.argv[2])
reading = {                       # values from YOUR live console read
    "console_location": "...",
    "enabled": True,
    "identity_provider_id": "...",
    "mapped_service_account_id": "...",
    "mapping_present": True,
    "subject_mapping_expression": "...",
    "uploaded_jwks_mode": True,
}
final = session / "replies" / f"reply-{seq}.json"
tmp = final.with_suffix(".json.tmp")
tmp.write_text(json.dumps({"seq": seq, "value": json.dumps(reading)}))
os.replace(tmp, final)            # atomic; the poller never sees a partial file
PY
```

For a pause step, `value` is the phrase itself — `"MUTATION COMPLETE"` — not
JSON. No `sudo`: `conductor` is in `factory` and the inbox is `2770`.

**Never write a reply before its prompt opens.** `_refuse_staged_replies` fails
the run closed if a reply for the open prompt or any later one already exists.
That is structural, not advisory: staging every answer up front would produce a
record that passes every checker while attesting to nothing.

**Start the run inside tmux whichever way you answer.** The console *cannot
start a run* — that is deliberate, and it is why the factory host is
`tmux_readonly` in the inventory: an attachable panel would be a
browser-reachable path to root on the box holding the WIF signing key. The
browser only supplies readings to a run it did not start. tmux owns the
pseudo-TTY, so a dropped SSH connection costs nothing; without it the kernel
SIGHUPs the collector and the run dies holding an open mutation window with the
mapping still carrying the sentinel. That has happened once.

## 1. Connect and preflight

```bash
ssh conductor@factory.example.com
tmux new -s rev
cd /opt/patchyard
```

`/opt/patchyard` is `factory-manager:factory`, so anything shelling out to git
must run as that account — git refuses a repository whose owner is not the
calling user, and that includes root. `conductor` and `sudo` both fail with
"detected dubious ownership", which reads like the drift this preflight is meant
to catch and is not:

```bash
fm() { sudo -n -u factory-manager env -C /opt/patchyard "$@"; }
fm git status --short
fm git rev-parse HEAD
fm python3 -I tools/check-freeze-graph.py
fm python3 -I tools/check-openai-wif-federation-revocation.py --allow-missing-results
sudo test "$(stat -c '%U:%G:%a' \
  /etc/patchyard/openai-wif-signing.pem)" = root:root:400
```

**Stop** if the checkout is dirty, the revision is not the reviewed revision for
this run, the freeze graph reports drift, a checker rejects static preflight, or
another OpenAI lifecycle run is genuinely active.

> `/opt/patchyard` has no git credentials and cannot fetch — deploys arrive as
> an incremental bundle. Its HEAD is expected to trail repo master. Confirm the
> deployed revision is the one reviewed for this run rather than assuming the
> newest commit is present.

### Inert leftovers from earlier attempts

Five directories under `/run/patchyard-openai` are dead runs, and all **appear
on `/collectors`**, because that page lists every directory there:

| Directory | State | Cause |
| :-- | :-- | :-- |
| `openai-revocation-20260809-c988690f41` | `in_progress`, no live process | SIGHUP killed the collector; mutation window was left open |
| `openai-revocation-20260810-b25e9cc3b3` | `failed` | Stage/session collision, before any OpenAI call or mutation |
| `openai-revocation-20260812-4924ca4ef5` | `failed` 12:44:36Z | `RevocationCollectorError: bracketing control did not supply a bearer` — the `remove` mutation had cascaded into deleting the mapped service account (A140); its baseline exchange at 12:27:05Z against the old id had returned HTTP 200 |
| `openai-revocation-20260812-64a8668459` | `failed` 12:54Z | `RevocationCollectorError: baseline control did not supply a bearer` — the old service-account id no longer exchanged at all (A140) |
| `openai-revocation-20260812-e2f0bcef3c` | `failed`, aborted at the mutation pause | The console offered no disable affordance for A140's prescribed mutation; the operator aborted with nothing mutated (A141) |

The 2026-08-10 run never reached an exchange or a mutation. Whatever the
2026-08-09 run left behind, the mapping was confirmed present and enabled at the
console immediately before the 2026-08-10 attempt — confirm it again yourself
before opening a window rather than relying on that.

The two runs that mutated are why `remove` is forbidden (A140), and the safely
aborted run is why the mutation is now subject-expression revocation (A141) —
the console had no disable affordance to offer it. The 2026-08-12 stage JSONs
are preserved durably at
`/var/lib/patchyard-evidence-hold/openai-r4-failed-20260812/` (root-only) on
the factory host, so a reboot clearing the tmpfs directories loses nothing.

Do not answer anything into any of them, and do not reuse their run IDs. Your
new run gets a new ID and its own pair of directories. Clearing them is
optional; this is tmpfs and a reboot removes them.

## 2. Start the run

**The stage and the session are two different directories.** Collapsing them
fails the run before anything happens — see the box below. Generate the run ID,
create the stage, write the embedded authorization file from the human-authored
GitHub comment on the requirement-4 attended-run ticket, then start the
collector under the runner. The ID must match
`openai-revocation-[0-9]{8}-[0-9a-f]{10}`. The comment body contains one `json`
fence naming that run ID, the canonical pairing, the Codex task id, the policy
and collector digests, the permitted mutation and restoration, and a deadline
exactly 45 minutes after the comment `created_at`. The same task must perform
the mutations, make the five readings, and write the Result.

```bash
RUN_ID="openai-revocation-$(date -u +%Y%m%d)-$(openssl rand -hex 5)"
STAGE="/run/patchyard-openai/$RUN_ID"
SESSION="$STAGE-session"

sudo install -d -m 0700 -o root -g root "$STAGE"

sudo python3 -I tools/attended-collector-runner.py \
  --collector federation-revocation \
  --session-dir "$SESSION" \
  --reply-group factory \
  -- \
  --run-id "$RUN_ID" \
  --authorization-file "$STAGE/authorization.json" \
  --model-pairing "<provider>/<harness>/<model>/<reasoning>" \
  --codex-task-id "<codex task id>" \
  --mapping-mutation subject-expression \
  --output "$STAGE/openai-federation-revocation.json"
```

> **Do not point `--session-dir` at the stage.** A run on 2026-08-10 died at
> `LifecycleError: lifecycle stage is not owned by root:root` before any OpenAI
> call or console mutation, because an earlier version of this runbook used one
> path for both.
>
> The collector derives its **lifecycle stage** from `--run-id`:
> `openai-wif-federation-revocation.py:90` rebinds `BASE.STAGING_ROOT` to
> `/run/patchyard-openai`, `:553` calls `validate_stage_directory(args.run_id)`,
> and `anthropic-wif-lifecycle.py:271-274` requires that directory to be
> `root:root` and mode `0700`. The collector never creates it — pre-create it.
>
> The runner's **session directory** is only the prompt/reply channel, and with
> `--reply-group factory` it is deliberately `root:factory 0750` so the browser
> can submit. That mode is exactly what the stage check rejects.
>
> `test_attended_collector_runner.py` does not cover this: it drives
> `SessionChannel` against a scratch `tmpdir/session` and never runs the
> collector's stage validation.

Four things about that command:

- **The stage is pre-created; the session is not.** `install -d` makes the stage
  because the collector requires one already there. The runner creates the
  session itself and *refuses to reuse an existing one*, since a second run
  writing where a prompt already sits could answer the wrong window.
- **`--output` must sit inside the stage.** `require_stage_path` at `:554`
  checks that its parent is exactly the stage directory.
- **`--reply-group factory`** is what lets the browser submit. The runner sets
  the session `root:factory 0750` and the replies inbox `root:factory 2770`;
  `conductor` — the dashboard's SSH identity — is in `factory`. Omit the flag
  and the session is root-only, which is correct only if you intend to answer in
  the terminal.
- **The `--` matters.** Everything after it is passed to the collector unchanged.

Then answer prompt 1 by whichever route § "Which way to drive it" left you with.
The first prompt appearing is the confirmation that the wiring is right —
nothing reaches OpenAI until after that reading.

On `/collectors`, each run shows **two** entries: the session, and the root-only
stage, which renders with a null status because `conductor` cannot read inside
`0700`. That one is expected and is not the bug described above — the *session*
rendering as unknown is.

## 3. Answer the prompts

Five reloaded console readings, two Save acknowledgements, and two Save
confirmations, in this order. Answer each only when it appears; do not queue
answers ahead. Reload the live console page before every reading.

| Step | What it asks | Mapping state to report |
| :-- | :-- | :-- |
| 1 | `RELOADED`, then enabled mapping before the baseline control | present and enabled, original expression |
| 2 | `RELOADED`, then immediate state before the mutation | unchanged from step 1 |
| — | **MUTATION COMPLETE**, then save-confirmation JSON | Edit the claim assertion to the sentinel *first* |
| 3 | `RELOADED`, then immediate state after the mutation | present and enabled, expression is the sentinel |
| 4 | `RELOADED`, then current mapping before safe restoration | **still the sentinel** |
| — | **RESTORATION COMPLETE**, then save-confirmation JSON | edit the original expression back *first* |
| 5 | `RELOADED`, then the safely restored mapping | present and enabled, identical to step 1 |

**Reload the console, then read it at each step. Do not prepare readings in
advance.** The capture method is
`model_console_readback_bounded_by_control_plane_utc`. Values written before
the window began produce a file that passes every checker while recording
nothing that was seen live.

**The sentinel is exact.** The mutation-pause prompt prints the run's sentinel,
`sub=patchyard-control-plane-REVOKED-<run id>`; Edit the claim assertion to
exactly that string. The collector rejects a step 3 reading whose expression is
anything else — a freehand "revoked" note is not the named mutation.

**Step 4 is the one that gets missed.** It is captured *before* you restore, so
the mapping must still carry the sentinel when you answer it. Restoring early
fails the run with `mapping returned to its original state before captured
restoration` — and the collector treats that as a failure even though the
console is now safe.

Each reading carries exactly these keys: `console_location`, `enabled`,
`identity_provider_id`, `mapped_service_account_id`, `mapping_present`,
`subject_mapping_expression`, `uploaded_jwks_mode`. `mapping_present`,
`enabled`, and `uploaded_jwks_mode` are strictly boolean. Absent fields are
`null`, not empty strings. The browser form enforces these shapes; if you are in
the terminal, they are yours to get right.

Between step 3 and step 4, and again after step 5, the run holds the 90-second
settling floor and prints the remaining time. An exchange before the floor
measures propagation and cannot be Evidence of revocation.

## 4. If something fails

**Restore the original mapping anyway.** The collector's `finally` block still
prompts for restoration on the failure path, and `safe_mapping_restored` records
whether the mapping came back.

A recovery outside the bounded window is operationally necessary and cannot
repair the record. The run is then not conforming — it is re-run from a
clean window, never patched.

If the pane is gone but the run is alive, `tmux attach -t rev` resumes at the
same prompt. If the process is dead, the mapping may still carry the sentinel
on the control plane: check the provider page first and edit the original
expression back by hand, then treat the run as failed. The residue is
self-describing — the expression names the run that left it — and it is a
*wrong* rule, not a disabled one: the mapping stays present and enabled, and
the worker's real assertion simply no longer matches it.

**If the edit back fails.** Edit reversibility is inferred, not promised —
each run's step 6 restoration reading is what proves it, run by run. If the
console Edit refuses to restore the original expression:

1. Do not remove or recreate the mapping (A140 — the delete cascade destroys
   the mapped service account and re-breaks every pinned result).
2. Retry the Edit from a fresh console session; a transient dashboard failure
   is the likely cause.
3. If the expression still cannot be restored, stop. The mapping is left
   carrying the sentinel: exchanges are denied, nothing is destroyed, and the
   state names this run. Record the failure on the run's ticket and escalate
   to Jacob — the repair decision (support ticket, or a newly discovered
   console surface) is made there, not improvised at the console.

The run is not conforming in that state, but it is safe; requirement 4 stays
unproven rather than broken.

## 5. Verify and copy out

Check the record without editing it:

```bash
sudo python3 -I tools/check-openai-wif-federation-revocation.py \
  --observation "$SESSION/openai-federation-revocation.json"
```

Confirm on the record that `bounded_window` covers all three exchanges, that
`baseline_control` and `bracketing_control` both supplied a bearer, that
`denial_observation` sits between them on the same surface with the same
instrument digest, and that `safe_mapping_restored` is true.

Copy **only** the sanitized JSON through the reviewed management path to a new
operator-host path. Never copy the session directory, request body, assertion,
response body, bearer, process memory, or signing key.

## What this run does not do

It does not make requirement 4 Proven. `--evidence` mode fails by construction:
`validate_qualification_evidence` appends `federation-revocation predicate is
unenforced pending observation` to every input, because the response predicate
is still

```json
{"enforced": false, "basis": "no-observed-openai-federation-revocation-response"}
```

That is A125 working as intended — no OpenAI federation-revocation denial has
ever been observed. **This run produces that first observation.** A reviewed
predicate is written afterwards, against what was actually returned, as a
separate change. The requirement becomes Proven only once a conforming Result is
committed and accepted.

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
exchanges and two console mutations, and it removes a live federation subject
mapping. Do not run it during build, review, CI, or an unattended session.

**It is not finished until the original mapping is back.** Budget an
uninterrupted block. The run pauses twice for a 90-second settling floor and
otherwise moves at the speed you read the console.

**Decide the two roles first.** You need a named `actor` (who makes the console
change) and a named `attester` (who records the attestation). Under A136 one
accountable human may hold both, but the record then carries no independence
and must never later be described as corroboration.

Have the provider page open and confirm the subject mapping is **present and
enabled**. The run cannot start from a removed mapping — the first reading is
checked against `require_active_mapping`.

## Which way to drive it

There are two ways to answer the collector's prompts. **Use the browser.**

| | Browser (`/collectors`) | Terminal |
| :-- | :-- | :-- |
| Where you answer | `https://status.example.com/collectors` | the tmux pane |
| Booleans | real controls | you type raw JSON |
| Pause steps | one **Acknowledge** button | you retype `MUTATION COMPLETE` |
| Before submitting | shows the exact JSON | none |

The browser path exists because of two recorded failures. A live run was
rejected for sending the string `"Uploaded JWKS"` where `true` was required —
the form renders booleans as real controls and nullable fields with an explicit
null toggle, because an empty text box is not the same value as null. And you
are already reading the OpenAI console in a browser; alt-tabbing to a terminal
to hand-assemble JSON is what produced that rejection.

**Start the run inside tmux either way.** The console *cannot start a run* —
that is deliberate, and it is why the factory host is `tmux_readonly` in the
inventory: an attachable panel would be a browser-reachable path to root on the
box holding the WIF signing key. The browser only supplies readings to a run it
did not start. tmux owns the pseudo-TTY, so a dropped SSH connection costs
nothing; without it the kernel SIGHUPs the collector and the run dies holding an
open mutation window with the mapping still removed. That has happened once.

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
  /etc/patchyard/anthropic-wif-signing.pem)" = root:root:400
```

**Stop** if the checkout is dirty, the revision is not the reviewed revision for
this run, the freeze graph reports drift, a checker rejects static preflight, or
another OpenAI lifecycle run is genuinely active.

> `/opt/patchyard` has no git credentials and cannot fetch — deploys arrive as
> an incremental bundle. Its HEAD is expected to trail repo master. Confirm the
> deployed revision is the one reviewed for this run rather than assuming the
> newest commit is present.

### Inert leftovers from earlier attempts

Two directories under `/run/patchyard-openai` are dead runs, and both **appear
on `/collectors`**, because that page lists every directory there:

| Directory | State | Cause |
| :-- | :-- | :-- |
| `openai-revocation-20260809-c988690f41` | `in_progress`, no live process | SIGHUP killed the collector; mutation window was left open |
| `openai-revocation-20260810-b25e9cc3b3` | `failed` | Stage/session collision, before any OpenAI call or mutation |

The 2026-08-10 run never reached an exchange or a mutation. Whatever the
2026-08-09 run left behind, the mapping was confirmed present and enabled at the
console immediately before the 2026-08-10 attempt — confirm it again yourself
before opening a window rather than relying on that.

Do not answer anything into either, and do not reuse their run IDs. Your
new run gets a new ID and its own pair of directories. Clearing them is
optional; this is tmpfs and a reboot removes them.

## 2. Start the run

**The stage and the session are two different directories.** Collapsing them
fails the run before anything happens — see the box below. Generate the run ID,
create the stage, then start the collector under the runner. The ID must match
`openai-revocation-[0-9]{8}-[0-9a-f]{10}`.

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
  --actor "<named actor>" \
  --actor-kind accountable_human \
  --attester "<named attester>" \
  --mapping-mutation remove \
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

Then open `https://status.example.com/collectors` and find your run.

Each run now shows **two** entries: the session, and the root-only stage, which
renders with a null status because `conductor` cannot read inside `0700`. Answer
prompts in the session. The first prompt appearing is the confirmation that the
wiring is right — nothing reaches OpenAI until after that reading.

## 3. Answer the seven prompts

Five console readings and two acknowledgements, in this order. Answer each only
when it appears; do not queue answers ahead.

| Step | What it asks | Mapping state to report |
| :-- | :-- | :-- |
| 1 | enabled mapping before the baseline control | present and enabled |
| 2 | immediate state before the mutation | unchanged from step 1 |
| — | **MUTATION COMPLETE** | remove the subject mapping *first* |
| 3 | immediate state after the mutation | removed |
| 4 | current mapping before safe restoration | **still removed** |
| — | **RESTORATION COMPLETE** | restore the exact original mapping *first* |
| 5 | the safely restored mapping | present and enabled, identical to step 1 |

**Read the console at each step. Do not prepare readings in advance.** The
capture method is `operator_console_readback_bounded_by_control_plane_utc`, and
the entire evidentiary value is that a named human read the live console inside
the bounded window. Values written before the window began produce a file that
passes every checker while attesting to nothing.

**Step 4 is the one that gets missed.** It is captured *before* you restore, so
the mapping must still be removed when you answer it. Restoring early fails the
run with `mapping returned to its original state before captured restoration` —
and the collector treats that as a failure even though the console is now safe.

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
repair the attestation. The run is then not conforming — it is re-run from a
clean window, never patched.

If the pane is gone but the run is alive, `tmux attach -t rev` resumes at the
same prompt. If the process is dead, the mapping may still be removed on the
control plane: check the provider page first and restore by hand, then treat the
run as failed.

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

# A77 adjudication - A101 isolated Python review

## Disposition

The build seat independently resolved all three A78 findings against the exact
reviewed technical commit `a0bd964d2c8b9690af5b257fe14617096b3eb612`:

| Finding | A77 disposition |
| --- | --- |
| F1 unchecked-hash bytecode replaces bound test content | **concede, High sustained** |
| F2 workflow failure masking is not bound | **concede, Medium sustained** |
| F3 three executed sources are outside the binding closure | **concede, Medium sustained** |

No source repair follows. The authorized isolated-Python repair completed its
fresh A78 loop and the review failed. A9 requires this stop and failure record.
Any next repair needs a new explicit bounded authorization under A115 and must
not mint another numbered ruling.

## F1 experiment - conceded

In a disposable detached worktree, A77 placed one PEP 552 unchecked-hash
bytecode file at the normal cache path for the unchanged, digest-bound issuance
test:

```text
infra/ansible/tests/__pycache__/test_anthropic_issuance.cpython-39.pyc
```

The header flags word was exactly `1`, the unchecked-hash mode. The artifact's
SHA-256 was
`0e959612d35c0f3f754578f6adb65e7414b013ad0ac4881636497cf6698563fd`.
It is ignored by the repository's ordinary `__pycache__/` rule but
`git add -n -f` confirmed that it can be force-added at that exact path. No
bound `.py` source changed.

Without the artifact, the unchanged runner executed 20 issuance tests and
returned 1 on the disclosed stale host-contract assertion. With the artifact:

```text
python3 -I tools/check-a101-readiness-root.py
    -> exit 0, A101 readiness trust root: pass
python3 -I tools/check-anthropic-spend.py
    -> exit 0, Anthropic spend check: pass
python3 -I tools/run-isolated-unittest.py \
    infra/ansible/tests/test_anthropic_issuance.py
    -> exit 0, Ran 1 test, test_forged_pass ... OK
```

`sys.dont_write_bytecode` prevents new cache writes but does not prevent the
import loader from reading this artifact. The root census sees only `.py`
sources. This reproduces the former one-case green issuance attack with every
bound source byte-identical, so F1 is independently conceded at High.

## F2 experiments - conceded

A77 installed each workflow weakening separately at the exact reviewed commit:

1. changed the infrastructure command to
   `run: tools/check-infra.sh || true`;
2. added `continue-on-error: true` at the `infrastructure` job level; and
3. added `continue-on-error: true` to the Ansible step.

For all three independent mutations,
`python3 -I tools/check-a101-readiness-root.py` exited 0. The first preserves
the checker's required command substring, the second is outside the captured
step body, and the third is outside the infrastructure step and is not checked
on the Ansible step. Each change masks a gate result whose failure is meant to
remain load-bearing. F2 is independently conceded at Medium.

## F3 experiments - conceded

Source inspection confirms that three repository files execute at test-module
import time but are absent from `BOUND_SOURCES` and its source census:

| Executed source | Loader | SHA-256 |
| --- | --- | --- |
| `tools/anthropic-spend-evidence.py` | `test_anthropic_spend.py` via `spec_from_file_location` | `d79d8c69d7752e70af3119846029de661bceda19e06181baccd247fa671f9d97` |
| `tools/anthropic-wif-admin.py` | `test_anthropic_wif_admin.py` via `spec_from_file_location` | `89794bd6235d5b37dfa4999a792588396ece9935b17820954b75d8b055822c91` |
| `infra/ansible/roles/control_plane/files/patchyard-log-secret-scan` | `test_log_secret_scan.py` via `SourceFileLoader` | `356c4a962a262f4128cd22496b068dbf4b02c8a3867214c7c31f80e1ebb11eb8` |

A77 appended one comment to the independently bound readiness test, changing
its digest from
`65ae6c632e521f264c26f243403901897d786efce83c4b115c98bce6cf198996`
to
`df902ce51451e1c8f8cbaf5f2ffe560e8862d636176780e081b29e6d27bcc702`.
The 27-test spend suite returned 1 on the expected digest mismatch.

In a second worktree with the same readiness mutation, A77 added import-time
code to the unbound `anthropic-spend-evidence.py` that mapped only that exact
mutant digest back to the pinned value. The unchanged isolated runner then
reported all 27 spend tests passing and returned 0. With only the poison and no
bound-source mutation, both the isolated root checker and independent spend
checker also returned 0, proving that the added executed content was invisible
to them.

The poison does not cross into the separately launched root process, so this
experiment does not claim a complete root bypass. It does defeat the reported
independent binder and admits uncensused executable content into three isolated
test processes. F3 is independently conceded at Medium.

## Confirmed closures and scope

A78 also confirmed, and A77 does not reopen, the prior repair's substantive
closures: isolated invocation and standard-library provenance work; repository
package initializers do not execute through the runner and are rejected by the
census; all seven checker scripts are exact-digest bound; `check-infra.sh`
continues through preview and returns the aggregate failure; and the current
workflow does run Ansible after the retained infrastructure failure.

The failure is in the completeness and mutation-resistance of the new binding
boundary, not a claim that those present source bytes already contain a masked
workflow or malicious helper.

## A9 stop and proposed next boundary

The smallest credible next step is one bounded source-binding repair, followed
by focused tests, installed mutations, the full repository gates, and another
clean A78 review. If separately authorized, it should:

1. make the isolated runner compile and execute the exact opened source bytes,
   without consulting repository bytecode caches, and reject repository
   `__pycache__`/`.pyc` artifacts in the protected execution roots;
2. exact-digest bind the three import-executed sources and add a complete census
   for executable Python content reached from the 14 test processes;
3. bind exact workflow command scalars and reject failure masking on the
   infrastructure job, infrastructure step, and continuing Ansible step; and
4. install the F1-F3 attacks, run the focused and complete gate sets, and obtain
   another exact-head A78 review.

No live Factory, worker, DigitalOcean, Anthropic, Console, requirement-1
refresh, acceptance, requirement-3, rotation, or qualification action is part
of that proposed boundary. All seven adjudication worktrees were removed and
pruned after the experiments.

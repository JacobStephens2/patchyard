# A77 adjudication - A101 firewall-readiness source review

## Disposition

The build seat **concedes F1, F2, and F3**. Jacob subsequently authorized one
bounded source repair limited to those findings, their tests and source
mutations, the full repository gates, and a fresh A78 review. The grant is
recorded under A115 and does not mint a new numbered decision-log ruling.

It authorizes no worker plan or apply, host or DigitalOcean mutation, Anthropic
credential or request, Console action, requirement-1 refresh, behavioral
acceptance, requirement 3, rotation work, or qualification-flag change.

## F1 - concede

The build seat ran the exact jq expression from reviewed commit `097a5b4`
against six bodies:

```text
empty       jq_exit=0
whitespace  jq_exit=0
null        jq_exit=1
false       jq_exit=5
object      jq_exit=1
valid       jq_exit=0
```

Empty and whitespace input therefore bypassed all provider predicates while
returning success. A78's high blocking severity is sustained.

## F2 - concede

The build seat independently applied four representative in-memory mutations
to the source contract:

- wrap the operator readiness call in an environment-controlled conditional;
- weaken a state-cardinality equality; and
- remove curl's `--fail`; and
- replace the provider object-type predicate with `true`.

All four mutated sources passed the existing validator. Source inspection also
confirmed that the pending fixture used both `status=waiting` and a nonempty
pending list, masking which predicate caused rejection. A78's medium severity
is sustained.

## F3 - concede

Source inspection confirmed that the helper placed the bearer in curl's
argument vector. The host mounts `/proc` without `hidepid`. The existing
`patchyard-deployed-version` helper supplies its bearer through
`curl --config -`, and its contract test explicitly excludes an Authorization
header from argv. A78's low severity is sustained.

## Nonblocking observations

- **Concede:** the firewall-ID regular expression is permissive and jq 1.6 uses
  last-key-wins duplicate-key behavior. Both shapes remain fail-closed against
  the exact provider readback predicates in the current topology.
- **Concede as a structural limit, not a current bypass:** only root-module
  resources are scanned. The current DigitalOcean stack declares the worker
  and firewall in its root module and has no child module.
- **Refute as a defect in this readiness gate:** revalidating the complete
  firewall rule set is not this precondition's contract. OpenTofu binds desired
  rules, this helper waits for the exact attachment to settle, and A101 remains
  the independent management-path check.
- **Concede as preexisting and out of scope:** the tag-firewall guard runs in
  plan mode rather than apply mode.
- **Concede:** jq is not version-pinned and provider response size has no
  explicit byte ceiling. The authorized repair must not depend on jq's
  empty-input exit behavior and retains curl's fixed time bounds.

## Authorized repair boundary

The bounded repair will:

1. reject empty and whitespace provider bodies and require jq's captured output
   to equal the single value `true`;
2. require exact HTTP 200 with curl HTTP failures still fatal;
3. deliver the validated DigitalOcean bearer through curl config on standard
   input;
4. add independent provider and state fixtures for every F2 gap; and
5. reject source mutations that weaken the new body, HTTP, state-cardinality,
   direct-call, and bearer-delivery bindings.

No live action follows from a green source repair. A new worker replacement
plan remains a separate, later decision after a clean A78 source verdict.

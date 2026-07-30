# A77 adjudication - successor worker-replacement plan

The build seat adjudicated A78's nine observations against exact source
`673b89fbfad5c287f79f9d6b7d046c35f1881cee` and saved-plan SHA-256
`944f8af406006cee8c92ec377e374fd697ba53d472290b42b565846f20dec550`.
A78 returned PASS with no material finding, so no post-review source repair was
made.

## Observations 1 and 2 - Concede, non-blocking for the exact plan

The wrapper's structural gate does not compare every attribute or separately
restrict `output_changes`. A78 proved both limits. They do not admit a different
plan at apply because the wrapper checks the A78-reviewed digest before
preflight and again immediately before apply. Independent full-plan inspection
found only a stock-image worker replacement, the matching firewall attachment,
and the expected worker address outputs. A future general-purpose semantic gate
would be stronger; it is not a prerequisite for these pinned bytes.

## Observations 3 through 7 - Concede as operational limits

The production-tag firewall check is point-in-time; DigitalOcean attachment
propagation is asynchronous; the state wrapper materializes the existing
backend credential even for plan inspection; input preflight cannot predict
later package/build success; and the authorized operator controls the bounded
check-to-apply interval. These are accurate limits. For this operation the tag
check was rerun immediately before apply, secret files and the plan remained
owner-only, the exact digest and revision were rechecked, and every later stage
remained fail-closed. None is evidence that the reviewed plan contains an
additional action.

## Observations 8 and 9 - Concede and resolve by experiment

DigitalOcean returned HTTP 404 for quarantined worker `588590370`. The complete
production-tag list contained the failed current Factory worker, the control
plane, manager, GDD, and Fieldbook - no orphan replacement. Account readback
reported 19 droplets against a 500-droplet limit, and NYC3 advertised
`s-8vcpu-16gb` as available. Both prerequisites therefore passed before apply.

## Mutation observations - Concede

B1-B8 were rejected by the resource/action gate. B9 and B10 demonstrated the
gate's broad semantic limit and are conceded. They do not alter the adjudication
because the approved SHA-256 fixes the exact reviewed plan, and full decoded
inspection found neither malicious output nor snapshot/foreign user data.

No second repair followed A78's PASS. The apply was authorized only for the
exact reviewed bytes and source revision.

# Issue tracker: Trello (wayfinder)

Wayfinding for this repo is tracked on Trello, not GitHub Issues. Board:
**Patchyard Factory** — https://trello.com/b/Tdiikiov (id `6a7b2192db06f2d821023c62`).

Credentials are already in the environment when launched via `va`:
`TRELLO_API_KEY` for the key, and `TRELLO_FACTORY_API_TOKEN` for the
read-write token (vault item `trello-api` field `factory-token`, added to the
`va` manifest 2026-08-11). The older `TRELLO_API_TOKEN` still resolves the
original field, which reads fine but returns 401 on writes — prefer
`TRELLO_FACTORY_API_TOKEN`, falling back to `TRELLO_API_TOKEN` only for
read-only calls or in a session launched before the manifest gained the new
variable:

```bash
TOKEN=${TRELLO_FACTORY_API_TOKEN:-$TRELLO_API_TOKEN}
curl -s "https://api.trello.com/1/cards/<card>?key=$TRELLO_API_KEY&token=$TOKEN"
```

If a write (POST/PUT) returns 401 while reads work, you are holding the
read-only token — say so and stop; do not prompt for the token.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single card; tickets are sibling cards
on the same board.

- **Current map**: [MAP: form -> daemon-claimed -> model-authored draft PR](https://trello.com/c/NfgyqpJf) — card `NfgyqpJf`, in the **Map** list, labelled `wayfinder:map`.
- **Lists** (state machine): `Map` (the map card only) · `Frontier` (open + unblocked + unclaimed) · `Blocked` · `Doing` (claimed) · `Done` (closed).
- **Ticket labels**: `wayfinder:research` / `wayfinder:prototype` / `wayfinder:grilling` / `wayfinder:task` (label ids on the board; attach via `POST /1/cards/<id>/idLabels`).
- **Blocking**: Trello has no native dependency edges here — a `Blocked by: <card link>` line in the child's description, and the card sits in the **Blocked** list. Unblocked when every named blocker is in Done; move it to Frontier then.
- **Frontier query**: `GET /1/lists/6a7b27f762e367c91053bf62/cards` (the Frontier list); first in list order wins.
- **Claim**: add yourself as a member (`POST /1/cards/<id>/idMembers`) and move the card to **Doing** — the session's first write.
- **Resolve**: post the answer as a comment (`POST /1/cards/<id>/actions/comments`), move the card to **Done**, then append a one-line gist + link to the map card's *Decisions so far*.
- **New tickets**: `POST /1/cards` into Frontier or Blocked with the right `wayfinder:` label; wire `Blocked by:` lines in a second pass once card URLs exist.

## When a skill says "publish to the issue tracker"

Create a Trello card on the Patchyard Factory board (Frontier or Blocked, as wired).

## When a skill says "fetch the relevant ticket"

`GET /1/cards/<card>` plus `GET /1/cards/<card>/actions?filter=commentCard`.

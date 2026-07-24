# Browserbase vs the factory's evidence-capture browser

*2026-07-24. **Desk assessment, not a probe** - no Browserbase account was created, no vendor evaluation run, and nothing here is measured evidence. Vendor capabilities are stated as of an early-2026 understanding of the product category and may have changed; re-check before acting on any specific claim. The factory-side facts are read from this repo at `6096e2f`.*

## Question

Should the factory's browser evidence capture (A89, session 13) use hosted browser infrastructure such as Browserbase instead of the Chromium process it runs itself?

## What Browserbase is

Hosted headless-browser infrastructure for agents and automation that drive the open web at scale: you connect to remote Chrome sessions in the vendor's cloud over the Chrome DevTools Protocol, typically through Playwright or Puppeteer.

Its differentiating features are the ones the open web forces on you - rotating and residential proxies, stealth/anti-bot and CAPTCHA handling, persistent browser contexts, live session view and replay for debugging, file-download handling, and horizontal concurrency across many simultaneous sessions.

The same vendor publishes Stagehand, an LLM-driven automation layer where the model decides the browser actions (act/extract/observe) rather than the caller scripting them.

## What the factory does today

`preview/patchyard-headless.py` runs a single one-shot Chromium subprocess and exits: `chromium-browser --headless=new --no-sandbox --user-data-dir=<profile> --load-extension=<ext> --disable-extensions-except=<ext> --screenshot=page.png --window-size=1440,1200 --virtual-time-budget=5000 --dump-dom <url>`.

`--dump-dom` yields the DOM evidence, `--screenshot` the image, and `--virtual-time-budget=5000` bounds settling in deterministic virtual time rather than wall clock. Authentication is a generated Manifest-V3 extension whose `declarativeNetRequest` rule sets `Authorization: Bearer <token>`; the bearer is read from an absolute non-symlink file and the extension is written to a 0700 temp directory with 0600 files.

Outputs are size-bounded (screenshot capped at 5 MB, mode 0600) and the DOM is parsed for wanted tags only through a bounded `HTMLParser`. There is no long-lived session, no WebDriver or CDP socket, and no caller-supplied JavaScript.

The target is a leased preview slot (owner, request id, expected SHA, TTL, random lease id, guaranteed cleanup) whose running revision is confirmed in-preview with `git rev-parse HEAD`; captures are taken at the base SHA and the candidate SHA, each SHA-256'd, and `factory-verify postconditions` runs against the pair. Session 7's records are the worked example.

## Comparison

| Axis | Factory harness | Browserbase |
| :-- | :-- | :-- |
| Control surface | CLI flags only; no automation protocol | CDP/Playwright remote control (that *is* the product) |
| Target | Private, leased preview slot running our own app at a pinned SHA | Arbitrary open-web sites |
| Execution location | Our control-plane VM; session 13 puts it in an OS sandbox | Vendor cloud |
| Interaction model | One navigation, fixed selectors, no caller JS | Full scripted multi-step flows |
| Anti-bot, proxies, CAPTCHA, session replay | None - not needed against our own app | Core features |
| Concurrency | A couple of captures per run | Designed for many simultaneous sessions |
| Evidence chain | DOM + screenshot hashed locally, SHA-pinned | Adds a third party and a network hop to the chain of custody |
| Cost shape | Marginal on an already-owned VM; ops burden is the pinned Chromium upgrade queue (A-14) | Usage-priced; no browser ops |

## Why it is not a fit here

**The automation surface is the liability, not a feature.** Browserbase's value is the remote-control socket. The A89 threat model is that an agent-modified (attacker-influenceable) page meets a live preview credential, and the reason session 13 can wrap our harness cleanly is precisely that there is no CDP/WebDriver socket and no caller JS to escape through. Adding a remote-control protocol re-opens the surface the design deliberately closed.

**Reachability runs the wrong direction.** The capture target is a private leased preview slot. A vendor-hosted browser would need inbound reach into Patchyard's preview fleet - a firewall exception or tunnel - which is strictly worse than a local process talking to a local host, and it cuts against A89's network-layer egress profile (leased preview host plus DNS only, metadata and private fleet denied).

**Data and provenance.** The preview carries redacted-but-real Fieldbook data (A85's seeded snapshot lineage) plus a one-use bearer. Routing that through a third party is a data decision, not a tooling decision. A verification system's product *is* trustworthy evidence, so an extra party in the chain of custody costs exactly what the system sells.

## Where Browserbase would genuinely win

It moves untrusted rendering off Patchyard infrastructure entirely - the same instinct that motivates A89, solved by purchase instead of by Firecracker or a scoped helper. That is a real argument, not a strawman.

The flags-only approach has a hard ceiling: it cannot do multi-step interaction (clicking through a wizard, waiting on an XHR, filling a form). ALPHABETIZE-class defects are visible on first render, so the ceiling has not bound yet, but a request class needing genuine interaction would hit it immediately.

It would also win on open-web browsing and on concurrency at scale - neither of which the factory does.

Stagehand's model-decides-the-actions design is the opposite of the fixed helper contract (allowed URL, bounded selectors and actions, timeouts, maximum output sizes, expected SHA) and would not be wanted even if the infrastructure were adopted.

## Standing rulings that bear on this

**R16** already rejected cloud sandboxes (Modal/E2B) on the reasoning that "the isolation goal is met by A57's Patchyard-owned worker/publisher split without outsourcing execution." Browserbase is the same shape of proposal, so adopting it would mean reopening R16 rather than making a tooling choice.

**A68** (no factory runtime function depends on anything outside the factory's own control plane), **A61** (single allowlisted provider egress per boot), **A57** (secret-free execution plane), and **A89** (evidence capture holds no authority and reaches only the leased preview host) all point the same way.

## Verdict

Stay with the self-hosted one-shot Chromium capture; do not open a Browserbase evaluation now. The features that justify hosted browser infrastructure are the ones the open web forces, and the factory does not browse the open web.

Revisit only if one of these triggers fires, and even then prefer a bounded scripted driver *inside* our own sandbox before outsourcing execution:

- A request class requires genuine multi-step interaction on the preview (the real ceiling of the flags-only design).
- The factory acquires a need to browse sites it does not host.
- Evidence-capture concurrency outgrows what the control-plane VM can run.

Any adoption is a ruling-level decision (it reopens R16 and touches A68/A61/A89), not a build-time choice.

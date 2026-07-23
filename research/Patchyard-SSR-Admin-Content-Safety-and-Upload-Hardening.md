# Safely Rendering Untrusted Content and Hardening Uploads for a Privileged SSR Admin Dashboard

**Scope:** Patchyard Factory internal admin (Rust / Axum / Askama SSR)  
**Threat model:** malicious or careless staff request text and PNG/JPEG screenshots viewed by three privileged admins who also hold a kill-switch session  
**Scale:** ~20 requests/week, one VM, self-hosted assets, no external origins, no client JS framework  
**Date:** 2026-07-23  
**Evidence base:** primary sources (OWASP cheat sheets, W3C CSP3, RFCs, MDN, Google Security Blog, PortSwigger research, RustSec/NVD, crate docs, cargo-fuzz / libFuzzer)

---

## Executive summary

At this scale the dominant failure mode is not mass upload abuse or anonymous account takeover. It is **one crafted request (text or screenshot) that executes in the kill-switch session** — stored XSS / content injection in a privileged browser — or a **decoder/path bug that turns an upload into process compromise or disk exhaustion**.

What holds:

| Belief | Verdict |
|---|---|
| HTML-escape untrusted text by default | **Essential.** Established OWASP primary defense. |
| pulldown-cmark with “raw HTML disabled” | **Directionally right, but the API does not offer a disable flag.** CommonMark emits `Event::Html` / `InlineHtml`; you must **filter events** and/or sanitize with ammonia. |
| Strict CSP with per-response nonce, no `unsafe-inline` | **Essential defense-in-depth**, not primary defense. Nonce preferred over hash for SSR. Must add `base-uri`, `object-src`, `form-action`, `frame-ancestors`, and correct `connect-src` for SSE. |
| Re-encode images; `Content-Disposition: attachment`; restrictive CSP | **Essential.** Re-encode is the real neutralizer; headers are the browser-side cage. |
| Separate content origin | **Optional at this scale** if Google’s inactive-content header set is applied rigorously. Worth it if a second hostname is cheap; not worth multi-service ops complexity. |

**Calibration rule used throughout:** anything that assumes multi-tenant public traffic, CDN edge sanitization, or continuous 24/7 fuzz fleets is labeled “at 100× / public app.” Unconditional “you need X” is reserved for load-bearing controls given kill-switch impact.

---

## 1. Rendering untrusted content to a privileged SSR admin UI

### 1.1 Primary defense: contextual output encoding

The [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) is unambiguous: no single technique solves XSS; **perfect injection resistance** means every variable is validated then escaped or sanitized for its **output context**. Output encoding is the recommended control when displaying data “exactly as a user types it.” CSP is explicitly **not** the primary defense — “It’s easy to make mistakes with the implementation so it should not be your primary defense mechanism.”

OWASP defines distinct contexts and encoders:

| Context | Required encoding | Dangerous if untrusted data lands here |
|---|---|---|
| HTML body | Entity-encode `& < > " '` | `<script>`, unexpected tags |
| HTML attribute | Encode all non-alphanumerics as `&#xHH;` (quoted attributes) | Breaking out of quotes into event handlers |
| URL parameter | Percent-encode values only; then attribute-encode the whole attribute | `javascript:`, `data:` |
| JavaScript string | `\uXXXX` for non-alphanumerics; **only** inside quoted data values | Any unquoted JS context is unsafe even with encoding |
| CSS | `\XX` / `\XXXXXX` hex | `expression()`, `url(javascript:…)` |
| HTML comment, raw `<script>`, raw `<style>`, tag/attr **names** | **Do not put untrusted data here at all** | Encoding will not fully protect |

[PortSwigger’s stored XSS material](https://portswigger.net/web-security/cross-site-scripting/stored) and OWASP both stress that privileged viewers amplify impact: account impersonation and session abuse. In this system that maps directly to kill-switch and factory control-plane actions.

### 1.2 What Askama auto-escaping genuinely protects

[Askama template syntax](https://askama.rs/en/stable/template_syntax.html) states that Askama **by default escapes variables when it thinks it is rendering HTML**, inferred from template extension (`html` / `htm` / `xml`), or forced via `escape = "html"`. The [Html escaper](https://docs.rs/askama/latest/askama/filters/index.html) is documented as escaping “characters in a safe way for HTML texts and attributes,” aligned with OWASP recommendations. Filters of note:

- `|escape` / `|e` — force escape  
- `|safe` — **marks output safe; disables escaping for that expression**  
- `|urlencode` / `|urlencode_strict` — URI percent-encoding (`urlencode` does **not** encode `/`)  
- `HtmlSafe` marker trait — types that skip HTML escaping  

**Where auto-escape protects (established):**

- Untrusted staff request text rendered in HTML body: `{{ request_text }}` in an `.html` template.  
- Untrusted text in quoted, hardcoded-name attributes like `title="{{ … }}"`, `class="{{ … }}"`, `data-id="{{ … }}"`.

**Where it silently does not (escape-context traps):**

1. **`|safe` / `HtmlSafe` / `escape = "none"`** — any path that marks markdown HTML or “trusted” governance HTML as safe becomes a raw injection sink. This is the Askama equivalent of React’s `dangerouslySetInnerHTML`.  
2. **URL attributes (`href`, `src`, `action`, `formaction`)** — HTML escaping does **not** neutralize `javascript:…` or `data:text/html,…`. OWASP requires URL validation / allowlisting of schemes (`https:`, maybe `mailto:`) **before** attribute encoding. Askama’s `|urlencode` encodes a component; it does not validate scheme.  
3. **Unquoted attributes** — `value={{ x }}` without quotes is an attribute-context failure even if characters are partially escaped. Always quote.  
4. **Event-handler attributes** — `onclick="{{ x }}"` is a JavaScript context, not HTML-attribute context. Auto-HTML-escape is the wrong encoder; OWASP says do not put untrusted data in event handlers at all.  
5. **CSS contexts** — `style="…{{ x }}…"` or inline `<style>` blocks need CSS encoding; HTML escape is insufficient. Prefer zero untrusted CSS.  
6. **JavaScript string embedding** — even the one inline `EventSource` fragment must not interpolate request text. Pass IDs via data attributes (HTML-escaped) and read them from `dataset` in the static/nonce script, or hardcode the SSE URL path.  
7. **Template injection of attribute/tag names** — never build `<{{ tag }}>` or `{{ attrname }}="…"` from untrusted input.  
8. **Nested templates** — rendering an inner template into an outer one without `|safe` double-escapes; with `|safe`, the inner template’s safety becomes load-bearing. Prefer composing only templates that themselves never emit untrusted raw HTML.

**Honest uncertainty:** Askama’s public docs assert OWASP-aligned HTML/attribute escaping but do not publish a machine-checked “context-aware multi-encoder” model (unlike some enterprise encoder libraries that pick encoder by sink type). Treat Askama as **strong for HTML body + quoted innocuous attributes**, and **not** as a universal contextual encoder for URL/JS/CSS.

### 1.3 Markdown (pulldown-cmark) — challenge the “disable raw HTML” belief

[pulldown-cmark](https://docs.rs/pulldown-cmark/latest/pulldown_cmark/) is a CommonMark pull parser. Its [Event enum](https://docs.rs/pulldown-cmark/latest/pulldown_cmark/enum.Event.html) includes:

- `Event::Html` — “An HTML node” (block HTML lines)  
- `Event::InlineHtml` — “An inline HTML node” (e.g. `<open-tag>`, comments)  

[Options](https://docs.rs/pulldown-cmark/latest/pulldown_cmark/struct.Options.html) enables extensions (tables, footnotes, tasklists, heading attributes, math, wikilinks, etc.). **There is no `DISABLE_RAW_HTML` flag.** Raw HTML is part of CommonMark; the default HTML renderer will emit it.

**Established safe patterns in the Rust ecosystem:**

1. **Event filter (prefer for untrusted staff requests):** drop `Html`, `InlineHtml`, and HTML block tags before `html::push_html`. The [event-filter example](https://pulldown-cmark.github.io/pulldown-cmark/examples/event-filter.html) shows the iterator pattern (used there for images; same pattern for HTML events).  
2. **Sanitize after render:** [ammonia](https://github.com/rust-ammonia/ammonia) is a whitelist HTML sanitizer using html5ever; its README explicitly pairs with pulldown-cmark for “friendly user-facing” markdown. Ammonia’s own docs note: if you want **no** HTML at all, a sanitizer is slower than never emitting HTML — filter events first.  
3. **Defense-in-depth:** filter events **and** run ammonia with a minimal allowlist (or empty tag allowlist for request text that should be plain-structure-only).

**Markdown-specific traps beyond raw HTML:**

| Trap | Risk | Mitigation |
|---|---|---|
| `[x](javascript:…)` / `data:` links | Click → JS in admin session | Allowlist schemes on `Event::Start(Tag::Link …)`; rewrite or drop |
| Autolinks / reference links | Same | Same link policy |
| `ENABLE_HEADING_ATTRIBUTES` | `{ #id .class onmouseover=… }`-style attribute injection into headings | **Do not enable** for untrusted input |
| Images `![](…)` | SSRF if server fetches; XSS if SVG; tracking pixels | For staff requests: either strip images from markdown (screenshots are a separate upload path) or allow only same-app screenshot IDs |
| Nested markdown in governance files | Supply-chain of internal docs | Treat governance markdown as **semi-trusted**: still no raw HTML; pin repo; review changes |

**Disagreement / nuance:** Some teams “disable HTML” in other markdown engines and stop there. That is incomplete: **markdown links and heading-attribute extensions remain XSS vectors** even with zero raw HTML. Prefer explicit link scheme allowlisting.

### 1.4 Privileged-viewer specifics (this threat model)

OWASP notes attackers plant XSS bombs in fields later viewed by staff (“malicious customer decides to plant an XSS bomb in the address field”). Your case is stricter: the viewer **is** the control plane.

Additional practices calibrated to three admins:

- **Never render request bodies inside the kill-switch page’s DOM tree if avoidable.** Prefer a two-route UI: `/requests/:id` (untrusted content) vs `/ops/kill` (no untrusted interpolation). Same session cookie is still shared (XSS on either origin path is still fatal if same site), but reducing sinks on the most sensitive templates reduces accident surface.  
- **HttpOnly + Secure + SameSite=Strict** session cookies limit some exfil/CSRF paths but **do not stop XSS** from calling same-origin kill endpoints from the admin’s browser. OWASP states cookie flags “try to limit the impact of an XSS attack but don’t prevent the execution of malicious content.”  
- **CSRF tokens** on state-changing POSTs (including kill switch and intake) remain mandatory even with SameSite cookies ([OWASP File Upload CS](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) also requires CSRF protection on upload).  
- **Trusted Types** (`require-trusted-types-for 'script'`) eliminate classes of DOM XSS on Chromium ([OWASP XSS CS](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)). With almost no client JS this is low-cost and high-value — enable it. Firefox support remains incomplete; treat as defense-in-depth, not universal.

**At 100× / public app you would also need:** multi-role CAP, per-action step-up auth for kill, separate viewing role without kill capability, and possibly an isolated “reviewer” browser profile. At three trusted admins, **role separation of view vs kill is still the highest ROI architectural control** if operationally acceptable — it is not on the XSS checklist, but it caps blast radius when content safety fails.

---

## 2. CSP for a strict SSR app with one inline fragment

### 2.1 Philosophy

[W3C CSP Level 3](https://www.w3.org/TR/CSP3/) states CSP is **not** a first line of defense against injection; it reduces harm as defense-in-depth. [OWASP CSP Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html) and [web.dev Strict CSP](https://web.dev/articles/strict-csp) converge: prefer **nonce- or hash-based “strict CSP”** over host allowlists; allowlists “can be bypassed in most configurations.”

### 2.2 Nonce vs hash for the one EventSource fragment

| Mechanism | Fit for this app | Notes |
|---|---|---|
| **Per-response nonce** | **Best fit** | [web.dev](https://web.dev/articles/strict-csp): “Use a nonce-based CSP for HTML pages rendered on the server.” Nonce must be cryptographically strong (ideally ≥128 bits), base64, **new every response**. |
| Hash (`'sha256-…'`) | Workable if script is byte-stable | Fragile: any whitespace change breaks the hash ([OWASP CSP CS](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)). Fine if the fragment is a compile-time constant string. |
| `'strict-dynamic'` | Optional; low need here | Helps apps that load scripts dynamically. With one static inline fragment and no third-party JS, it adds little and can surprise if anything ever injects script nodes. |
| `'unsafe-inline'` | **Forbidden** in enforced policy | Recent browsers ignore it when a nonce/hash is present, but shipping it as primary is a footgun. |

**OWASP warning that applies directly:** do **not** run middleware that rewrites all `<script>` tags to add nonces — attacker-injected scripts would get nonces too. Nonces must be applied only by the template engine to developer-authored tags.

### 2.3 Strongest workable policy (recommended)

Deliver as HTTP header on **all** HTML responses (not only index; not meta-only — meta cannot do `frame-ancestors` or violation reporting per OWASP).

```http
Content-Security-Policy:
  default-src 'none';
  base-uri 'none';
  object-src 'none';
  script-src 'nonce-{RANDOM}';
  style-src 'self';
  img-src 'self';
  font-src 'none';
  connect-src 'self';
  form-action 'self';
  frame-ancestors 'none';
  frame-src 'none';
  worker-src 'none';
  media-src 'none';
  manifest-src 'none';
  upgrade-insecure-requests
```

Rationale by directive:

| Directive | Why |
|---|---|
| `default-src 'none'` | Fail-closed fetch default ([MDN CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)). |
| `script-src 'nonce-…'` only | Blocks inline event handlers, `javascript:` URIs, and injected scripts without the nonce ([web.dev](https://web.dev/articles/strict-csp)). **Do not add `'self'`** if user uploads are same-origin — see §3 polyglot bypass ([PortSwigger polyglot JPEGs](https://portswigger.net/research/bypassing-csp-using-polyglot-jpegs)). |
| `style-src 'self'` | Two self-hosted CSS files. Prefer no inline style; if a tiny inline style is required, use a style nonce. Avoid `'unsafe-inline'`. |
| `img-src 'self'` | Screenshots and UI icons from same app. If screenshots are forced `Content-Disposition: attachment` only, admins may open them as downloads rather than `<img>` — either works; if you use `<img>`, ensure response headers still apply (§3). |
| `connect-src 'self'` | [EventSource](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src) is governed by `connect-src` (falls back to `default-src`). `'self'` covers same-origin SSE. |
| `base-uri 'none'` | Blocks injected `<base>` from rewriting relative script/style URLs ([web.dev](https://web.dev/articles/strict-csp), [MDN base-uri](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/base-uri)). |
| `object-src 'none'` | Disables plugins / `<object>` ([web.dev](https://web.dev/articles/strict-csp)). |
| `form-action 'self'` | **Critical:** `default-src` does **not** cover form actions ([PortSwigger form hijacking](https://portswigger.net/research/using-form-hijacking-to-bypass-csp)). Without this, HTML injection + password-manager autofill can exfil credentials even when script is blocked. If the UI truly has no forms that POST, `'none'` is stricter. |
| `frame-ancestors 'none'` | Clickjacking defense; supersedes `X-Frame-Options` ([OWASP CSP CS](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)). |
| `frame-src 'none'` / `worker-src 'none'` | No frames/workers expected. |

Optional Chromium hardening on HTML responses:

```http
Content-Security-Policy: require-trusted-types-for 'script'
```

(combine into the same policy string).

### 2.4 CSP mistakes that leave holes in “looks strict” policies

Established (PortSwigger / Google / OWASP):

1. **`script-src 'self'` + same-origin uploads** — polyglot JPEG/GIF executed as script ([PortSwigger](https://portswigger.net/research/bypassing-csp-using-polyglot-jpegs), [Mozilla MIME confusion](https://blog.mozilla.org/security/2016/08/26/mitigating-mime-confusion-attacks-in-firefox/)).  
2. **Missing `form-action`** — form hijacking bypasses script-less CSP ([PortSwigger](https://portswigger.net/research/using-form-hijacking-to-bypass-csp)).  
3. **Missing `base-uri`** — relative URL takeover.  
4. **Static / guessable nonce** — nonce must be per-response CSPRNG.  
5. **Unquoted nonces/hashes** — `script-src sha256-…` is ignored; must be `'sha256-…'` ([PortSwigger](https://portswigger.net/research/using-form-hijacking-to-bypass-csp)).  
6. **Missing semicolons** — next directive name parsed as a value; directive silently ineffective.  
7. **Report-Only left as the only policy** — no enforcement.  
8. **Allowlisting CDNs / `https:`** — script gadgets; not needed here.  
9. **JSON endpoints served as `text/html`** — OWASP XSS CS: ensure API responses use `application/json`.  
10. **Policy only on some routes** — upload and SSE error pages included.

**Disagreement:** Google’s minimal “strict CSP” sample emphasizes `script-src` + `object-src` + `base-uri` and relies on other product controls. For a **privileged admin with forms and SSE**, the fuller fetch-directive lockdown above is the better fit; the disagreement is about minimal vs defense-in-depth completeness, not about nonce vs allowlist.

---

## 3. Serving user-uploaded images safely

### 3.1 Same-origin vs separate origin vs data-URI

| Approach | Security property | Ops cost at this scale | Verdict |
|---|---|---|---|
| **Same-origin + hard headers + re-encode** | Google (2023): inactive content **can** be served safely **without** a sandbox domain if headers isolate the response | Lowest | **Default recommendation** |
| **Separate hostname** (e.g. `uploads.patchyard.internal`) on same VM | Cookie isolation from admin session; blocks `script-src 'self'` polyglot class if scripts never load from that host | Low–medium (TLS cert, cookie `Domain` hygiene) | **Worth it if cert/DNS is trivial**; skip if it delays shipping headers |
| **Fully separate site on PSL / usercontent domain** | Google’s classic + modern sandbox-domain designs | High | **Overkill at 3 users** |
| **data: URIs in HTML** | Avoids separate requests; blows CSP (`img-src data:` weakens policy); huge HTML; no `Content-Disposition` cage | Low but weakens CSP | **Avoid** |

[Google Security Blog — Securely Hosting User Data (2023)](https://security.googleblog.com/2023/04/securely-hosting-user-data-in-modern.html) for **inactive** content (images/downloads):

1. Set `Content-Type` to a well-known non-active MIME (when in doubt, `application/octet-stream`).  
2. Set isolation headers (extracted from the article’s header list):

```http
X-Content-Type-Options: nosniff
Content-Disposition: attachment; filename="download"
Content-Security-Policy: sandbox
Content-Security-Policy: default-src 'none'
Cross-Origin-Resource-Policy: same-site
```

Plus defense-in-depth they list: `frame-ancestors 'none'`, and optionally COOP/COEP for cross-origin isolation. Google’s claim: this combination ensures the response can only load as a subresource or download, with multiple layers against browser bugs via CSP `sandbox` + `default-src`.

**Calibration:** For three internal admins on modern browsers, **headers + re-encode suffice**. A separate upload hostname is a nice hardening if free; it is not the difference between safe and unsafe if the header set is correct and `script-src` does not include a path that can load uploads as scripts.

### 3.2 `Content-Disposition: attachment` vs inline

[RFC 6266](https://www.rfc-editor.org/rfc/rfc6266) defines `Content-Disposition` for HTTP: `attachment` prompts download treatment; `inline` suggests on-page display. [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Disposition) matches.

| Mode | Use |
|---|---|
| `attachment` | **Default for untrusted screenshots** — reduces drive-by rendering as active document; aligns with Google’s inactive-content recipe |
| `inline` | Only if product requires `<img>` preview **and** `Content-Type` is a safe image MIME **and** `nosniff` + CSP sandbox still set |

Filenames in `Content-Disposition` must be server-controlled (RFC 6266 `filename` / `filename*`); never echo raw user filenames (header injection / XSS in odd clients).

### 3.3 Polyglots, sniffing, nosniff

- [Mozilla on MIME confusion](https://blog.mozilla.org/security/2016/08/26/mitigating-mime-confusion-attacks-in-firefox/): browsers historically sniffed; polyglot GIF/JS etc. enable XSS when uploads are served in a script-capable way.  
- [PortSwigger polyglot JPEGs](https://portswigger.net/research/bypassing-csp-using-polyglot-jpegs): same-origin JPEG + `script-src 'self'` → CSP bypass in browsers that execute the polyglot as script (historically Safari/Firefox/Edge; Chrome refused). Mitigations stated: **separate domain for assets**, **rewrite JPEG headers / strip comments**, and **never whitelist the image domain for script**.  
- [X-Content-Type-Options: nosniff](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options): blocks MIME sniffing; **essential** companion to correct `Content-Type`.

### 3.4 Does re-encoding fully neutralize embedded payloads?

[OWASP File Upload CS](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): “For **images**, applying image rewriting techniques destroys any kind of malicious content injected in an image.”

**Established:** full decode → pixel buffer → encode to a clean PNG or JPEG **strips** trailing polyglot tails, JPEG comment JS payloads, HTML appended after IEND, EXIF-based trickery aimed at naive servers, and most “image as script” constructs — **provided** the encoder writes a fresh bitstream and you serve **only** the re-encoded bytes.

**Limits (honest):**

- Re-encoding does **not** fix **decoder vulnerabilities** during the decode step itself (memory corruption, bombs) — that is a pre-decode limit + sandbox/timeout problem (§4).  
- Re-encoding does **not** make an image safe to serve as `text/html` or execute as script; headers still matter.  
- Exotic “polyglot that remains valid JS after re-encode” is **not** a practical concern if you control the encoder and output format; treat claims otherwise as unproven unless demonstrated against your exact encoder.  
- [Glasswall polyglot research](https://docs.glasswall.com/research/polyglot-research-unmasking-images-pdf) documents format-level polyglots more broadly (PDF/image, etc.) — reinforces allowlisting formats and reconstructing files, not signature checks alone.

**SVG:** reject entirely. SVG is active content (script, external refs). Not an image in the security sense.

---

## 4. Image upload pipeline hardening (Rust)

### 4.1 Validation order (pressure-tested)

Align with [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) and [PortSwigger file upload](https://portswigger.net/web-security/file-upload):

1. **Authenticate + authorize + CSRF** before reading body.  
2. **Hard body size limit** at the HTTP layer (before multipart parse completes into memory). [RFC 7578](https://www.rfc-editor.org/rfc/rfc7578) multipart is just the transport; it does not protect you.  
3. **Per-user / per-request quotas and rate limits.**  
4. **Declared Content-Type** as a soft check only — “cannot be trusted… trivial to spoof” (OWASP).  
5. **Magic-byte sniff** allowlist: PNG (`89 50 4E 47…`), JPEG (`FF D8 FF`). Reject mismatch.  
6. **Dimension / allocation limits before full decode** (§4.2).  
7. **Decode → strip metadata → re-encode** to fixed encoder settings.  
8. **Store only re-encoded bytes** under server-generated IDs.  
9. **Serve with §3 headers.**

Magic-byte checks alone are “pretty common and easy” to bypass (OWASP) — hence re-encode is mandatory, not optional.

### 4.2 `image` crate limits and decoder bombs

[`image::Limits`](https://docs.rs/image/latest/image/struct.Limits.html):

| Field | Default | Strictness |
|---|---|---|
| `max_image_width` | **no limit** | strict when set |
| `max_image_height` | **no limit** | strict when set |
| `max_alloc` | **512 MiB** | **non-strict**; some decoders may ignore |

Docs warn: non-strict limits are best-effort; “some of the underlying decoders do not support such limits.” `Default` “adds some reasonable limits” but “is not equivalent to *not* adding limits” and may change across major versions.

**Practical floor for ERP screenshots:**

- Set **strict** `max_image_width` / `max_image_height` (e.g. 4096×4096 or whatever matches real screenshots + margin).  
- Set `max_alloc` far below process RAM (e.g. 32–64 MiB) knowing it is non-strict — **also** enforce OS `ulimit`/cgroup memory on the service.  
- Prefer `ImageReader` + `with_guessed_format` + `set_limits` **before** `decode` ([ImageDecoder::set_limits](https://docs.rs/image/latest/image/trait.ImageDecoder.html)).  
- Enforce **compressed byte length** and **timeout** around decode (tokio `timeout` or blocking pool with wall clock).  
- Disable or do not compile decoders you do not need (HDR, GIF, ANI, etc.) via crate features — reduces CVE surface ([CVE-2019-16138](https://nvd.nist.gov/vuln/detail/CVE-2019-16138) was in the **HDR** decoder).

Historical [image-png issue #80](https://github.com/image-rs/image-png/issues/80) documents unbounded memory on malformed PNG inputs — class of bug that dimension headers + `max_alloc` + cgroup aim to contain. [image issue #938](https://github.com/image-rs/image/issues/938) tracks library-wide memory limits evolution — limits exist now but are incomplete across decoders.

### 4.3 Known `image` crate advisories (representative)

| ID | Issue | Affected | Fixed |
|---|---|---|---|
| [CVE-2019-16138](https://nvd.nist.gov/vuln/detail/CVE-2019-16138) / [RUSTSEC-2019-0014](https://rustsec.org/advisories/RUSTSEC-2019-0014.html) / [GHSA-m2pf-hprp-3vqm](https://github.com/advisories/GHSA-m2pf-hprp-3vqm) | HDR decoder `Vec::set_len` on uninitialized buffer → UAF / possible ACE | `image` ≥0.10.2, <0.21.3 | 0.21.3; interface hardened further in 0.22+ |
| [CVE-2020-35916](https://github.com/advisories/GHSA-9wgh-vjj7-7433) / RUSTSEC-2020-0073 | Mutable ref with immutable provenance | <0.23.12 | 0.23.12 |

**Operational rule:** pin a current `image` version; run `cargo audit` in CI; enable only `png` and `jpeg` features; treat decoder code as **untrusted-input-facing** and keep it updated.

### 4.4 What naive “load then re-save” misses

| Missed attack | Why load+save fails | Fix |
|---|---|---|
| Decompression / pixel bomb | Decode allocates huge buffers before save | Strict dimensions + `max_alloc` + cgroup + timeout **before/during** decode |
| Format confusion | `image` may guess a surprising format | Allowlist formats explicitly; reject others |
| Partial decode panic / abort paths | Historical unsafe issues in edge decoders | Feature-minimize; audit; fuzz |
| Serving original bytes “if re-encode fails” | Fail-open restores polyglot | **Fail closed**; discard original |
| EXIF orientation-only “strip” without re-encode | Leaves comment/ICC/trailer payloads | Full re-encode; do not copy APP markers |
| Streaming write of untrusted bytes to final path | TOCTOU / partial files | Write temp + fsync + atomic rename of **re-encoded** output only |
| ImageMagick-style delegate/RCE | Not Rust `image`, but dangerous if shelling out | Do not shell out to ImageMagick for this pipeline |
| Multi-image/APNG | Unexpected frames / memory | Disable animation; single-frame still only |
| Color profile / ICC quirks | Rare renderer bugs | Re-encode with encoder defaults; strip profiles |

**EXIF/metadata:** stripping via re-encode is the robust approach. “EXIF XSS” is mostly a **server-side reflection** or **naive parser** story; still strip so admin tools and future features cannot reflect metadata into HTML.

### 4.5 Crate posture

| Crate | Role | Posture |
|---|---|---|
| `image` (+ `png`, `jpeg` only) | Decode/encode | Maintained; use limits; audit CVEs |
| `zune-jpeg` (via recent image) | JPEG decode backend | Be aware of backend switches in CHANGES; still apply limits |
| ammonia | HTML sanitize | Maintained; pair with markdown |
| pulldown-cmark | Markdown parse | Safe Rust parser; **not** an HTML sanitizer |
| Avoid `magick_rust` / CLI ImageMagick | — | High historical CVE density (ImageTragick class) |

---

## 5. Filesystem and path safety for uploads

### 5.1 Essential patterns

From OWASP File Upload + Unix atomicity practice:

| Control | Mechanism |
|---|---|
| Server-generated names | UUID/ULID only; never user filename on disk ([OWASP](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)) |
| Outside web root / not executed | Store under data dir the static asset server does not map as scripts |
| ID → path map in app | Handler maps `someid → file`; user never supplies path segments |
| Create-new | `O_CREAT\|O_EXCL` (or Rust `OpenOptions::create_new(true)`) so existing files are not overwritten |
| No follow symlinks | `O_NOFOLLOW` on open where supported; refuse if parent path contains symlinks you do not own |
| Atomic publish | Write to `tmp/name.partial` on **same filesystem** → `fsync` → `rename(2)` to final name |
| Directory permissions | Upload dir not world-writable; process user least privilege; **no exec** mount (`noexec`) if feasible |
| Quotas | Enforce before write; pre-check free space; fail closed on ENOSPC |
| Disk-full | Return 507/503; do not leave truncated finals; alert |

### 5.2 Subtle bugs fixtures usually miss

1. **TOCTOU between `exists()` and `create`** — use `create_new`, not check-then-create.  
2. **`rename` over existing** — `rename` replaces; if IDs collide (bug) you clobber. `O_EXCL` on final create or ensure cryptographic uniqueness.  
3. **Symlink in parent path** — attacker with another foothold swaps `uploads` → `/etc`. Defend with root-owned parents, `O_DIRECTORY`+`O_NOFOLLOW` walk from a trusted base fd (`openat` chain).  
4. **Hardlink farming** — on shared FS, link final path elsewhere; prefer exclusive create and restrictive dir perms (sticky bit where multi-user). Less relevant on single-service VM.  
5. **NFS `O_EXCL` weakness** — man pages historically warn `O_EXCL` is broken on some NFS; keep uploads on local disk.  
6. **Partial multipart → path from `filename` header** — [RFC 7578](https://www.rfc-editor.org/rfc/rfc7578) `filename` is advisory; **ignore for storage path**.  
7. **Double extensions / null bytes** — irrelevant if you never use user filename; still do not log raw filenames into shell scripts.  
8. **Same-FS assumption for atomic rename** — cross-device rename becomes copy+delete (non-atomic). Keep tmp and final on one mount.  
9. **Cleanup races** — deleting while serving; use immutable finals + GC by age.  
10. **Zip/slip class** — N/A if you reject archives; do not add “helpful” archive extract later without a separate design.

**At 100×:** object storage (S3) with generated keys removes most local FS races. At one VM, local FS + `create_new` + `rename` is appropriate.

---

## 6. Threat-model + fuzz session at this scale

### 6.1 What is high-value vs theater

| Activity | Value at 20 uploads/week | Notes |
|---|---|---|
| `cargo-fuzz` on **re-encode pipeline** entrypoint | **High** | Catches panics/OOMs/hangs in decode path |
| Seed corpus of real PNG/JPEG + crafted malformed | **High** | [libFuzzer](https://llvm.org/docs/LibFuzzer.html): graphics libs should seed small valid + invalid images |
| Fuzz path-join / ID parsing | **Medium** | Simple if IDs are UUID-only; still fuzz any leftover path code |
| Continuous 24/7 multi-week fuzz without triage | **Theater** | Budget better spent on header/CSP review + `cargo audit` |
| Full browser XSS crawl | **Medium** | One manual + semgrep for `|safe` may beat tooling cost |
| Antivirus / VirusTotal on every upload | **Marginal** | After re-encode of PNG/JPEG, low residual; privacy cost of shipping internal ERP screenshots to third parties (OWASP warns about public scanners) |

### 6.2 Concrete cargo-fuzz plan

Follow the [Rust Fuzz Book](https://rust-fuzz.github.io/book/) / [cargo-fuzz tutorial](https://rust-fuzz.github.io/book/cargo-fuzz/tutorial.html):

**Targets (suggested):**

1. `fuzz_image_ingest(&[u8])` — magic sniff → limits → decode → encode PNG → encode JPEG; discard output.  
2. `fuzz_multipart_filename(&[u8])` — if any filename parsing remains; should be trivial reject.  
3. `fuzz_markdown_request(&[u8])` — pulldown event filter + ammonia; assert no `<script` in output (heuristic) / no panic.

**Corpus construction ([libFuzzer guidance](https://llvm.org/docs/LibFuzzer.html)):**

- Small valid PNG/JPEG (various color types, progressive JPEG, interlaced PNG).  
- Truncated headers, truncated IDAT, wrong CRCs.  
- Oversized dimension claims in IHDR/SOF.  
- Polyglot samples (JPEG+JS comment style from public research — for **decoder resilience**, not to “detect” polyglots).  
- Random noise and empty files.  
- Minimize with `-merge=1` periodically.

**Structure-aware (optional):** [cargo-fuzz structure-aware chapter](https://rust-fuzz.github.io/book/cargo-fuzz/structure-aware-fuzzing.html) — worth it if dumb mutation stalls; not mandatory for a time-boxed first campaign.

**Sanitizers:** AddressSanitizer (default with cargo-fuzz); consider enabling overflow checks. Run with a **memory cap** and `-timeout=` so bombs surface as timeouts/OOMs you then fix with stricter limits.

### 6.3 Coverage / stopping criteria — what “zero unresolved findings” should mean

At this scale, a honest definition:

1. **Time box:** e.g. 4–8 CPU-hours on `fuzz_image_ingest` + 1–2 hours on markdown filter after corpus seeding.  
2. **Coverage plateau:** edge coverage growth flattens for a sustained window (order of tens of minutes with no new edges) **and** corpus has been merged/minimized. Plateau alone is not proof of absence — only of diminishing returns for that budget ([FuzzBench/community experience](https://github.com/google/fuzzbench/issues/654) on coverage plateaus).  
3. **Zero unresolved findings means:**  
   - No reproducible crash/hang/OOM on the **ingest API you will ship** (including limit enforcement).  
   - Every unique crash filed as issue: fixed or accepted with documented residual risk.  
   - `cargo audit` clean for `image` and HTTP stack, or risk-accepted with pins.  
4. **It does not mean:** “the decoder is proven correct” or “no XSS exists.”

**Regression:** keep the minimized corpus and run it in CI (libFuzzer “run files without fuzzing” mode) on each `image` upgrade.

---

## 7. What to instrument (quiet, rare events)

Volume is low — design for **high-signal alerts**, not dashboards nobody watches. Map to [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) / [Logging Vocabulary](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html): security events with who/what/when/outcome, no secrets.

| Signal | Why | Alert? |
|---|---|---|
| Upload rejected: magic mismatch, oversize, dimension limit, decode fail, re-encode fail | Attacker probing or client bug | Yes if burst; sample otherwise |
| Decode duration / memory high-water | Bomb attempts | Yes on threshold |
| ENOSPC / quota hit | Availability | Immediate |
| CSP violation reports (`report-to` / `report-uri`) | XSS attempt or policy bug | Yes — even 1 matters at this scale |
| `|safe` / markdown render errors | Misconfig | Yes |
| Admin session: kill-switch invoked | Control plane | Always (audit) |
| Admin session: mass request views atypical for user | Stolen session / XSS automation | Soft anomaly |
| Response `Content-Type` sniffer mismatch on static paths | Mis-serve of uploads | Yes |
| Auth failures on admin | Credential stuffing (low likelihood) | Standard |
| Any HTML response missing CSP header | Deploy regression | Synthetic check |

Implementation notes:

- Prefer **structured logs** (JSON) with `event_type`, `actor_id`, `request_id`, `upload_id`, `byte_len`, `detected_type`, `reject_reason`.  
- **Do not log** raw request bodies or screenshot bytes (ERP data sensitivity).  
- CSP `Content-Security-Policy-Report-Only` can run **in parallel** with enforced policy during rollout ([OWASP CSP CS](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)).  
- Synthetic uptime check: fetch a canary admin HTML page (authenticated harness or header-only probe) and assert CSP + `nosniff` present.

---

## 8. The one thing most teams get wrong (not on the usual checklist)

**They treat “we re-encode images and have a strict CSP” as permission to be sloppy about *where* untrusted strings enter templates — especially markdown-to-HTML marked `|safe`, and `script-src 'self'` while hosting uploads on the same origin.**

More precisely, the failure cluster is:

1. **Primary defense inversion** — CSP/headers as the plan, contextual escaping as an afterthought (directly contradicts OWASP and CSP3).  
2. **Same-origin user content + `'self'` scripts** — polyglot class ([PortSwigger](https://portswigger.net/research/bypassing-csp-using-polyglot-jpegs)).  
3. **Markdown pipeline that is “CommonMark default”** — raw HTML events pass through; nobody filters `Event::Html`.  
4. **form-action omitted** — scriptless exfil ([PortSwigger](https://portswigger.net/research/using-form-hijacking-to-bypass-csp)).  
5. **Privileged session monolith** — same cookie views poison content and fires kill switch, with no second factor on kill.

The checklist item that is easy to miss operationally: **every Askama `|safe` and every markdown HTML emission path is a security boundary review gate**, equal in severity to a new SQL string concat.

---

## Draft upload contract — pressure test

| Your control | Rating | Notes |
|---|---|---|
| Canonical server-generated IDs/filenames | **Essential** | OWASP baseline |
| create-new + atomic rename | **Essential** | Use `create_new` + same-FS `rename`; fsync before rename |
| Magic-byte sniffing | **Essential but insufficient alone** | Pair with re-encode |
| Decoder pixel limits | **Essential** | Set **strict** width/height; do not rely on default “no limit” |
| Re-encode to clean PNG/JPEG | **Essential** | Only store/serve re-encoded bytes; fail closed |
| Reject archives/executables/SVG | **Essential** | SVG is active content |
| Per-request and per-user quotas | **Essential** | Low volume still needs caps (bugs, loops, malice) |
| Rate limits | **Essential** | Cheap; stops accidents and noisy probes |
| Disk-full fail-closed | **Essential** | Alert + 507 |
| Strict CSP + `Content-Disposition: attachment` | **Essential** | Add Google’s full inactive set: `nosniff`, CSP `sandbox` + `default-src 'none'`, CORP |
| Symlink/hardlink defense | **Essential** on multi-writer FS; **still do** single-service | `O_NOFOLLOW` / trusted base fd |
| Antivirus / CDR sandbox | **Marginal at this scale** for PNG/JPEG after re-encode | Skip third-party scanners for internal ERP screenshots unless policy requires |
| Separate content origin | **Optional / situational** | Headers-first; second hostname if free |
| EXIF strip explicit step | **Covered by re-encode** if complete; document it | Do not “copy APP1” |
| Timeout around decode | **Missing — add** | Wall-clock timeout + blocking thread pool |
| Crate feature minimization + `cargo audit` CI | **Missing — add** | HDR history shows why |
| Ignore RFC 7578 user filename entirely | **Make explicit** | |
| Serve path never uses user input | **Make explicit** | |
| CSRF on upload | **Missing from list — add** | OWASP required |
| Original bytes never retained “for forensics” on disk web-reachable | **Recommend** | If retain, offline quarantine dir, not served |

---

## Minimum viable floor

Non-negotiable for a privileged internal SSR admin dashboard at this scale.

### A. Rendering / CSP

1. **Contextual HTML escaping by default** in Askama (`.html` templates, no global `escape = "none"`); ban untrusted data in URL/JS/CSS/event-handler sinks; scheme-allowlist any URL.  
2. **Markdown:** filter out `Event::Html` / `InlineHtml` / HTML blocks; scheme-allowlist links; do **not** enable heading attributes for untrusted input; optional ammonia pass; never `|safe` on untrusted markdown without sanitizer.  
3. **Strict CSP** on all HTML: `default-src 'none'`; `script-src` **nonce-only** (no `'self'`, no `'unsafe-inline'`); `style-src 'self'`; `connect-src 'self'` (SSE); `base-uri 'none'`; `object-src 'none'`; `form-action 'self'` (or `'none'`); `frame-ancestors 'none'`.  
4. **Session cookie:** `HttpOnly`, `Secure`, `SameSite=Strict`; **CSRF** on all state-changing routes including kill and upload.  
5. **CSP violation reporting + synthetic header check** in deploy/monitoring.

### B. Upload pipeline

6. **Authz + size limits + quotas + rate limits** before trusting body; CSRF on upload.  
7. **Magic allowlist → strict dimension/alloc limits → timed decode → re-encode → store only clean bytes** under server IDs; fail closed; originals not served.  
8. **Filesystem:** `create_new` + fsync + atomic rename on local disk; no user path segments; least privilege; disk-full fail-closed.  
9. **Serve uploads** with `X-Content-Type-Options: nosniff`, correct image or `application/octet-stream` type, `Content-Disposition: attachment`, `Content-Security-Policy: sandbox; default-src 'none'`, `Cross-Origin-Resource-Policy: same-site` (Google inactive-content recipe).  
10. **Supply chain:** minimal `image` features (png/jpeg only), `cargo audit` in CI, time-boxed `cargo-fuzz` on ingest + corpus retained for regression.

---

## Belief check — summary answers

| Your belief | Deepened guidance |
|---|---|
| Escape text; disable raw HTML in markdown | Escape yes. For pulldown-cmark, **filter HTML events** (and sanitize); also lock down **links** and **extensions**. |
| Strict CSP + nonce is backbone defense-in-depth | Correct as **second** layer; add `form-action`, `base-uri`, `object-src`, `frame-ancestors`; **omit `script-src 'self'`** if uploads are same-origin. |
| Re-encode + attachment + restrictive CSP | Correct; adopt Google’s full inactive header set; re-encode is necessary but not sufficient without decode limits and fail-closed behavior. |

---

## Source quality and residual uncertainty

| Claim class | Status |
|---|---|
| OWASP contextual encoding rules; CSP as defense-in-depth | **Established** |
| Google 2023 inactive-content headers without sandbox domain | **Established** (Google Security Blog); browser edge-cases always possible |
| Polyglot JPEG + `script-src 'self'` bypass | **Established** historically; browser mitigations improved; still design as if `'self'`+uploads is unsafe |
| `image::Limits` fully stop all decoder bombs | **Partial** — width/height strict; `max_alloc` non-strict; OS limits still required |
| Re-encode destroys malicious in-image content | **Established** as industry practice (OWASP); residual decoder-RCE risk separate |
| Separate origin mandatory at 3-user scale | **Not established**; optional hardening |
| Trusted Types everywhere | **Chromium-strong**; not universal — defense-in-depth only |

Primary references used include: [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html), [OWASP CSP](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html), [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html), [OWASP Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [W3C CSP3](https://www.w3.org/TR/CSP3/), [MDN CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP), [RFC 6266](https://www.rfc-editor.org/rfc/rfc6266), [RFC 7578](https://www.rfc-editor.org/rfc/rfc7578), [Google Securely Hosting User Data](https://security.googleblog.com/2023/04/securely-hosting-user-data-in-modern.html), [web.dev Strict CSP](https://web.dev/articles/strict-csp), [PortSwigger polyglot JPEGs](https://portswigger.net/research/bypassing-csp-using-polyglot-jpegs), [PortSwigger form hijacking](https://portswigger.net/research/using-form-hijacking-to-bypass-csp), [Mozilla MIME confusion](https://blog.mozilla.org/security/2016/08/26/mitigating-mime-confusion-attacks-in-firefox/), [Askama syntax](https://askama.rs/en/stable/template_syntax.html), [pulldown-cmark Event](https://docs.rs/pulldown-cmark/latest/pulldown_cmark/enum.Event.html), [image Limits](https://docs.rs/image/latest/image/struct.Limits.html), [CVE-2019-16138](https://nvd.nist.gov/vuln/detail/CVE-2019-16138), [Rust Fuzz Book](https://rust-fuzz.github.io/book/), [libFuzzer](https://llvm.org/docs/LibFuzzer.html), [ammonia](https://github.com/rust-ammonia/ammonia).

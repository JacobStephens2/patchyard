# Session 12 upload threat model and predeclared fuzz campaign

Status: declared before implementation and before any Session 12 fuzz run.

## Security boundary

An authenticated submitter may attach one PNG or JPEG screenshot to the dashboard intake form. The screenshot, multipart metadata, media type, and user filename are untrusted content under F2. The upload path is intake only: it calls the same `factory-core` request constructor as the text-only path, creates the intake row and clean screenshot artifact, and performs no pipeline or verifier transition (A53). The form remains the only phase-1 intake surface (A66).

The protected asset is the factory admin browser session, which can operate the kill switch. The primary threat is one crafted screenshot executing in that browser or exhausting the control plane, not anonymous bulk traffic.

## Fixed limits and fail-closed policy

- Authentication and submit authorization are checked before reading multipart fields.
- A submission that admits **zero** uploads is re-rendered with a warning and a `confirm_no_screenshots` checkbox rather than queued, and only a second submission carrying that field reaches the intake row ([#324](https://github.com/JacobStephens2/patchyard/issues/324) item 3). The signal is the count of admitted uploads, which is trusted structured data; the request body's prose about attachments is untrusted content and is never parsed for it. The unconfirmed attempt releases its admission as `no-screenshot-unconfirmed`.
- `Content-Length` is mandatory and the complete multipart request is capped at 8 MiB plus 128 KiB of framing.
- One screenshot is allowed per request. The compressed screenshot field is capped at 8 MiB.
- Each user is limited to 20 admitted uploads and 256 MiB of clean-image reservations per UTC day. Pending reservations count against both limits.
- Each user is limited to five upload admissions per rolling 10 minutes.
- The only accepted magic bytes are PNG and JPEG. Client media types, extensions, and RFC 7578 filenames have no authority.
- Decode limits are set explicitly before decode: width and height at most 4,096 pixels each and decoder allocation at most 128 MiB.
- At most two decode jobs run concurrently. Decode and re-encode execute on Tokio's blocking pool with a two-second wall-clock timeout.
- Re-encoded output is capped at 32 MiB. Original bytes remain in bounded process memory only and are never written or served.
- Storage uses server UUIDs, a trusted upload-root file descriptor, `O_NOFOLLOW`, `create_new`, file `fsync`, no-replace same-filesystem rename, directory `fsync`, one-link regular-file checks, 0700 directories, and 0600 files.
- Disk exhaustion emits an error alert and returns HTTP 507. Every validation, timeout, persistence, and cleanup ambiguity fails closed.
- The serve route accepts only a server UUID, reopens beneath the trusted root without following links, verifies the clean artifact hash, and applies the complete inactive-content header set from `docs/dashboard-security.md` section B. No original-byte route exists.

## Threats and required evidence

| Threat | Control | Evidence |
| --- | --- | --- |
| Cross-site upload | Session-bound CSRF token validated before the screenshot field | Route tests for missing, invalid, and reordered tokens |
| Oversize or quota exhaustion | Header/body caps plus transactional per-user admission reservations | Boundary, rate, daily quota, and concurrent-admission tests |
| MIME or extension spoofing | Magic-byte allowlist; filename and declared type ignored | PNG/JPEG positive cases; SVG, archive, executable, and spoof fixtures rejected |
| Decoder/decompression bomb | Explicit decoder dimensions/allocation, bounded blocking work, timeout | Oversize-dimension, malformed, timeout, and concurrency tests |
| Metadata or polyglot payload | Decode to pixels and re-encode; no APP1 copy; clean bytes only | EXIF/after-IEND payload absent from stored output |
| Traversal, symlink, hardlink, or race | UUID-only canonical paths and trusted-base-fd filesystem operations | Path corpus, symlink/hardlink fixtures, no-replace concurrent store test |
| Active same-origin serving | Authz plus inactive-content headers and attachment disposition | Exact header-set route test |
| Disk full or partial write | Create-new temporary file, sync, atomic no-replace rename, explicit cleanup | Injected ENOSPC/cleanup tests returning 507 with no artifact row |
| Duplicate/concurrent intake | Database uniqueness plus transactional artifact registration and cleanup | Two simultaneous identical submissions yield one intake/artifact; the duplicate is rejected |

## Predeclared fuzz campaign

The campaign has two `cargo-fuzz` targets:

1. `ingest_decode` - magic classification, explicit-limit image decode, bounded re-encode, and fail-closed error handling.
2. `canonical_path` - stored relative-path parsing and the invariant that every accepted path round-trips to the canonical UUID-derived path without user-controlled components.

The retained seed corpus is declared as:

- `fuzz/corpus/ingest_decode/valid-1x1.png`
- `fuzz/corpus/ingest_decode/valid-1x1.jpg`
- `fuzz/corpus/ingest_decode/truncated-png`
- `fuzz/corpus/ingest_decode/truncated-jpeg`
- `fuzz/corpus/ingest_decode/svg-active`
- `fuzz/corpus/ingest_decode/zip-magic`
- `fuzz/corpus/ingest_decode/elf-magic`
- `fuzz/corpus/ingest_decode/png-oversize-dimensions`
- `fuzz/corpus/ingest_decode/jpeg-malformed-segments`
- `fuzz/corpus/canonical_path/canonical-png`
- `fuzz/corpus/canonical_path/canonical-jpeg`
- `fuzz/corpus/canonical_path/traversal`
- `fuzz/corpus/canonical_path/double-extension`
- `fuzz/corpus/canonical_path/absolute`
- `fuzz/corpus/canonical_path/encoded-separator`
- `fuzz/corpus/canonical_path/non-utf8`

The declared execution budget is 120 seconds per target, 240 seconds total target runtime, using `-max_total_time=120`. Compilation time is excluded. The campaign runs from one recorded PR commit. Every crash, timeout, excessive allocation, or invariant violation is retained and triaged before the Session 12 exit can be claimed. Success means both targets reach their full budget with zero unresolved findings.

### Runtime and finding triage

Toolchain: nightly-2026-07-01 with cargo-fuzz 0.13.2. (The originally-pinned
nightly-2026-07-24 fails to compile the instrumented build due to a rustc codegen
bug; the pin was updated in this branch.) Both targets ran to the declared 120-second
budget with zero unresolved findings:

- ingest_decode - 49,515 runs in 121 s, exit 0, no crashes.
- canonical_path - 9,527,768 runs in 121 s, exit 0, no crashes.

Finding F-1 (resolved). An initial canonical_path run surfaced one invariant
violation: CanonicalUploadPath::parse accepted non-canonical byte spellings of an
otherwise-valid path (a doubled separator, uploads/<uuid>//<uuid>.jpg, and a trailing
separator) because it validated through Path::components(), which normalizes;
relative_path() then reproduced a single separator, so the parse->serialize round trip
was not byte-exact. Severity was low - both call sites rebuild the served path from the
parsed UUID via openat(NOFOLLOW) under a trusted root fd, never from the raw bytes, and
the stored path is server-generated - but the canonicalizer was non-injective. Fixed by
requiring byte-exact canonical input in parse; regression cases added to
canonical_path_parser_has_exact_shape; the reproducer is retained in the seed corpus.
The post-fix canonical_path run above is clean.

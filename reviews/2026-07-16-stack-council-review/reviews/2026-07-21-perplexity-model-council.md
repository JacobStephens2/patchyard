<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

### 1. Where Models Agree

| Finding | GPT-5.6 Sol Thinking | Grok 4.5 Low | GLM-5.2 | Evidence |
| :-- | :-- | :-- | :-- | :-- |
| Stack is intentionally “small-team/low-traffic” and fits ~20 req/week constraints | ✓ | ✓ | ✓ | Scale + constraints explicitly called out (two VMs + worker droplet; ~20 req/week; 3 users).[^1_1] |
| “Ledger-first” architecture: Postgres is authoritative; telemetry is secondary | ✓ | ✓ | ✓ | Invariants + observability section: “ledger is primary… telemetry is never evidence.”[^1_1] |
| Exec-boundary agents + secret-free worker are core safety design choices | ✓ | ✓ | ✓ | Agents run as subprocesses; worker has no standing secrets; single allowlisted provider egress.[^1_1] |
| Postgres LISTEN/NOTIFY is used as queue wake + SSE push + control signaling | ✓ | ✓ | ✓ | Stack/spec states LISTEN/NOTIFY used for queue wake, SSE, and control rows.[^1_1] |
| Avoiding npm/TS/frameworks/K8s etc. is a deliberate supply-chain \& scale posture | ✓ | ✓ | ✓ | “Deliberately excluded” table: npm/TS/WASM frameworks/K8s/queues, etc.[^1_1] |

### 2. Where Models Disagree

| Topic | GPT-5.6 Sol Thinking | Grok 4.5 Low | GLM-5.2 | Why They Differ |
| :-- | :-- | :-- | :-- | :-- |
| Should Firecracker microVM be used on DigitalOcean? | “Probe first; may be blocked by lack of nested virt/KVM—plan for Podman fallback”[^1_1][^1_2] | “Likely problematic on DO; keep container fallback primary to reduce risk”[^1_1][^1_2] | “Evaluate but don’t bet phase-1 on KVM availability; containers may be more reliable”[^1_1][^1_2] | DigitalOcean nested virt/KVM support is uncertain/not a supported feature; models differ on how aggressively to pursue Firecracker vs defaulting to containers.[^1_2] |
| Risk of self-hosted GitHub Actions runner on control-plane VM | “Acceptable if hardened/ephemeral as written, but still a notable attack surface”[^1_1][^1_3] | “Bigger risk: self-hosted runners can be persistently compromised; keep workflows ultra-trusted”[^1_3] | “Operationally fine, but security requires strong restrictions and review gating”[^1_3] | GitHub warns self-hosted runners lack guarantees of clean isolation and can be persistently compromised; models weigh that warning differently.[^1_3] |
| Using Postgres LISTEN/NOTIFY as a “queue” | “OK at this scale; ensure commit semantics + payload limits understood”[^1_4][^1_1] | “Fine for low volume; watch for missed-notify patterns and reconnect logic”[^1_4][^1_1] | “Good early-stage choice; may need a real queue at higher scale”[^1_4][^1_1] | Differences are mostly emphasis: all accept it at current scale, but point to known constraints (delivery at commit, payload size, client robustness).[^1_4] |

### 3. Unique Discoveries

| Model | Unique Finding | Why It Matters |
| :-- | :-- | :-- |
| Grok 4.5 Low | Self-hosted runner risk deserves explicit “trusted workflows only” posture | GitHub’s warning implies you must treat the runner as high-value; helps avoid supply-chain/PR-based compromise.[^1_3] |
| GPT-5.6 Sol Thinking | DO/KVM uncertainty should be treated as a phase-1 delivery risk, not just a technical detail | If Firecracker can’t run, timeline slips unless the Podman fallback is equally “first-class.”[^1_1][^1_2] |

### 4. Comprehensive Analysis

The packet is very explicit about *calibrating to honest scale* and about a set of invariants that are “not up for review,” and all models converge on the idea that the stack matches those constraints rather than chasing industry defaults. The most coherent through-line is that the system is built to be *auditable and gated*: every change becomes a human-merged PR; the ledger (PostgreSQL) is the authoritative record; and the agent layer is intentionally kept across an exec boundary so you can reason about what code can and cannot do at runtime. This convergence is high-confidence because the document itself repeatedly encodes these as invariants and then aligns stack choices (Rust daemons, local Postgres with role matrices, artifact store on disk, minimal JS, no npm/TS) to enforce them.[^1_1]

A second high-confidence cluster is the trust/isolation posture: secret-free worker, single-provider egress per boot, and US-jurisdiction provenance requirements are treated as fundamental constraints, not preferences. That framing matters because it makes a bunch of “popular alternatives” (managed queues, third-party control planes, in-process agent SDKs) not merely “excluded,” but structurally incompatible with the threat model and the “lethal-trifecta” rule described in the spec. The stack’s insistence on GitOps maximalism and on local control-plane responsibility (no runtime dependency on the orchestration host) further reinforces that the system is meant to be self-contained and recoverable from versioned desired state.[^1_1]

Where the models begin to diverge is mostly around *delivery risk vs architectural purity*, especially regarding Firecracker on DigitalOcean. The spec already anticipates this by saying the orchestration VM having `/dev/kvm` doesn’t prove the worker droplet does, and by requiring a probe plus a fallback to rootless Podman if needed. The tension the models highlight is pragmatic: DigitalOcean does not reliably/supportedly provide nested virtualization/KVM in a way you can bank on for a phase-1 deliverable, so Firecracker might be an aspiration rather than a dependable baseline. The actionable synthesis is: keep Firecracker as “evaluate first,” but ensure the container fallback path is equally well-specified, tested, and acceptance-covered so phase 1 doesn’t hinge on hardware virtualization availability.[^1_2][^1_1]

Another nuanced disagreement is about the self-hosted GitHub Actions runner living on the control-plane VM. Your doc positions it as hardened, ephemeral single-job mode, and “repo hygiene only,” with GitHub-hosted runners as a one-line fallback. The models differ mostly in how much they worry that “repo hygiene only” can still become a foothold. GitHub’s own guidance emphasizes that self-hosted runners can be persistently compromised by untrusted code, which means your security story relies heavily on: (a) keeping workflows trusted/reviewed, (b) minimizing secrets accessible to the runner, and (c) hardening + isolation around the runner host. This doesn’t contradict your design, but it suggests making the “trusted workflows only” posture and workflow permission boundaries extremely explicit in operational doctrine, because the runner is one of the few places arbitrary code *will* execute by design.[^1_3][^1_1]

On Postgres LISTEN/NOTIFY as a multipurpose signaling plane (queue wake-up + SSE push + control messages), all models treat it as reasonable at your stated throughput, but they emphasize different failure modes. The hard facts: notifications are delivered at transaction commit, not immediately, and payload size is bounded (default under 8KB). The practical implication is that correctness must not depend on a notification arriving; notifications should be treated as “wake-ups” to re-check durable state in Postgres (which your ledger-first approach already implies), and clients must handle reconnects and missed notifications gracefully. At 10× volume or more complex fan-out, you might eventually want a dedicated queue, but the document’s own scale calibration makes that an “if and when,” not a phase-1 need.[^1_4][^1_1]

**Recommendations:** Treat two items as phase-1 “make-or-break” risk reducers: (1) make the Podman fallback path first-class (tests, hardening, parity image, acceptance criteria) so Firecracker is optional rather than schedule-critical. (2) write an explicit operational rule that only trusted, reviewed workflows can target the self-hosted runner, aligning with GitHub’s warning about runner compromise risk. Everything else in the packet reads internally consistent for your constraints: ledger-first state, minimal web surface, exec-boundary agents, and strong supply-chain exclusions.[^1_2][^1_3][^1_1]
<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_16][^1_17][^1_18][^1_19][^1_20][^1_21][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_5][^1_6][^1_7][^1_8][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: 20260721stackcouncilpacket.md

[^1_2]: https://www.digitalocean.com/community/questions/does-digitalocean-support-nested-kvm-now

[^1_3]: https://docs.github.com/en/actions/reference/security/secure-use

[^1_4]: https://www.postgresql.org/docs/current/sql-notify.html

[^1_5]: https://www.recall.ai/blog/postgres-listen-notify-does-not-scale

[^1_6]: https://www.stacksync.com/blog/beyond-listen-notify-postgres-request-reply-real-time-sync

[^1_7]: https://news.ycombinator.com/item?id=20020501

[^1_8]: https://vrajat.com/posts/postgres-queue-skip-locked-unlogged/

[^1_9]: https://github.com/firecracker-microvm/firecracker/issues/751

[^1_10]: https://kruzenshtern.org/writings/2021-02-24-run-firecracker-on-digitalocean

[^1_11]: https://blog.nviso.eu/2026/02/03/rootless-containers-with-podman/

[^1_12]: https://oneuptime.com/blog/post/2026-02-02-podman-security-configuration/view

[^1_13]: https://github.com/caddyserver/caddy/issues/677

[^1_14]: https://caddy.community/t/server-sent-events-buffering-with-reverse-proxy/11722

[^1_15]: https://github.com/Giveth/giveth-dapps-v2/issues/4620

[^1_16]: https://synacktiv.com/publications/github-actions-exploitation-self-hosted-runners

[^1_17]: https://jorijn.com/en/blog/opentofu-vs-terraform-2026-the-fork-finally-diverged/

[^1_18]: https://squareops.com/blog/opentofu-vs-terraform-2026/

[^1_19]: https://docs.github.com/actions/using-github-hosted-runners/about-github-hosted-runners

[^1_20]: https://www.digitalocean.com/community/questions/does-digitalocean-support-kvm-or-nested-virtulzation

[^1_21]: https://www.postgresql.org/docs/7.0/sql-notify.htm

[^1_22]: https://sesamedisk.com/postgres-listen-notify-real-time-event-distribution/

[^1_23]: https://www.cybertec-postgresql.com/en/listen-notify-automatic-client-notification-in-postgresql/

[^1_24]: https://www.matthewswong.com/en/blog/github-actions-runners/

[^1_25]: https://www.digitalocean.com/community/questions/install-kvm-on-debian

[^1_26]: https://www.youtube.com/watch?v=gZ8MhQ0eZ08

[^1_27]: https://github.com/dduzgun-security/github-self-hosted-runners

[^1_28]: https://stackoverflow.com/questions/66547165/how-to-enable-the-kvm-in-gcp-digitalocean-linux-instance

[^1_29]: https://www.postgresql.org/docs/current/sql-listen.html

[^1_30]: https://stackoverflow.com/questions/79107120/how-to-protect-github-actions-self-hosted-runner

[^1_31]: https://news.ycombinator.com/item?id=44490510

[^1_32]: https://dev.to/mechcloud_academy/opentofu-vs-terraform-in-2026-is-the-fork-finally-worth-it-3nd1

[^1_33]: https://discuss.linuxcontainers.org/t/running-virtual-machines-with-lxd-4-0/7519/15

[^1_34]: https://www.reddit.com/r/VFIO/comments/pelvx8/cant_get_nested_virtualization_working/

[^1_35]: https://dev.classmethod.jp/en/articles/ec2-nested-virtualization-support-non-bare-metal/

[^1_36]: https://docs.github.com/en/actions/reference/runners/self-hosted-runners

[^1_37]: https://serverfault.com/questions/801628/for-server-sent-events-sse-what-nginx-proxy-configuration-is-appropriate

[^1_38]: https://www.netdata.cloud/academy/update-skip-locked/

[^1_39]: https://www.reddit.com/r/selfhosted/comments/1pm8a1d/is_it_worth_switching_some_containers_to_podman/

[^1_40]: https://www.linkedin.com/posts/jeetugupta_postgresql-backendengineering-distributedsystems-activity-7427696637298421760-cTpl

[^1_41]: https://lists.podman.io/archives/list/podman@lists.podman.io/thread/NXEOIKXY3CUDT77I53NMJAI5LCMX4TUY/


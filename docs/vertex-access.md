# Vertex AI access (example-model-bench)

*Provisioned 2026-07-17 by Jacob via browser agent; handoff recorded here 2026-07-18. Living ops reference - update if the project/SA/key changes.*

| Item | Value |
| --- | --- |
| Project ID | `example-model-bench` |
| Project number | `000000000000` |
| Organization | `example.com` |
| Billing | "My Billing Account" (`000000-000000-000000`) |
| Vertex API | `aiplatform.googleapis.com` - Enabled (console label: "Agent Platform API") |
| Service account | `example-vertex@example-model-bench.iam.gserviceaccount.com` |
| SA role (only one) | `roles/aiplatform.user` (console: "Agent Platform User") |
| Key location | 1Password example vault - see env.tpl reference (pending vault move as of 2026-07-18) |

Usage notes:

- The wrapper injects credentials as **raw JSON in env**; Gemini CLI's Vertex mode needs a **file path**. Materialize to a `mktemp` file (0600), export `GOOGLE_APPLICATION_CREDENTIALS=<path>`, delete after (trap on EXIT).
- Vertex surface: `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT=example-model-bench`, `GOOGLE_CLOUD_LOCATION=<region serving the model>` (availability is regional - a wrong region reads as model-not-found, not an auth error).
- Failure checklist: role bound → API enabled (propagation takes minutes) → billing linked → region serves the model → credentials var is a file path.
- Identity hygiene: factory model spend stays on this project; this SA gets no additional roles - new capability means a new identity. Prefer Workload Identity Federation over long-lived keys when practical.

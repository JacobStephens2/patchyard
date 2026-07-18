# Request

Create `docx/specs.md` as a production-ready implementation specification for
an unattended Markdown-to-DOCX rendering service used by an AI agent factory.

The service receives a Markdown source document plus a small JSON style
profile, renders a deterministic `.docx`, validates the artifact, and returns
either the document or a structured failure. Workers run in disposable,
network-restricted containers. The design must support headings, paragraphs,
ordered and unordered lists, tables, links, images, page breaks, headers,
footers, page numbers, and a generated table of contents. Unsupported Markdown
must fail explicitly rather than silently degrade. Replaying the same accepted
inputs with the same pinned renderer version must produce the same logical
document, ignoring ZIP container timestamps.

Write 1,400-1,800 words of concrete Markdown. Use exactly these level-two
sections, in this order:

1. `## Purpose and scope`
2. `## Inputs and outputs`
3. `## Architecture`
4. `## Rendering contract`
5. `## Validation and acceptance`
6. `## Failure handling and retries`
7. `## Security and isolation`
8. `## Rollout plan`

Include specific interfaces, lifecycle steps, deterministic acceptance checks,
failure categories, retry boundaries, security controls, observability fields,
and rollout gates. Resolve reasonable implementation details yourself. Do not
ask questions, use placeholders, discuss the prompt, or create any other file.

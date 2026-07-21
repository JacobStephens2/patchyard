

# What This Data Is

*Renamed 2026-07-21: the snapshot lives at `2026-07-20.tsv` in this folder. The Drive JSON export of the same sheet was removed as a duplicate - `tools/aa-join.py` consumes the TSV.*

This spreadsheet (artificial-analysis-llm-api-providers-leaderboard-2026-07-20, sheet Sheet1) is a snapshot of the Artificial Analysis LLM API Providers Leaderboard, comparing hosted API endpoints for large language models across different providers.  
Each row represents a single provider \+ model endpoint (for example, Anthropic | Claude Fable 5 (with fallback), SiliconFlow | DeepSeek V4 Pro (max), Parasail | Kimi K2.6). The same model appears on multiple rows when served by multiple providers, since pricing, throughput, and capabilities differ by host. The current dataset contains 523 endpoint rows.

## Column layout

| Col | Field | Description |
| :---- | :---- | :---- |
| A | API Provider | The company/service hosting the endpoint (e.g., OpenAI, Amazon Bedrock, Microsoft Azure, SiliconFlow, Novita) |
| B | Model | Model name incl. variant suffixes such as (max), (xhigh), (high), (FP4), (FP8), (with fallback), (Non-reasoning) |
| C | Context Window | Maximum context length (e.g., 1M, 262k, 500k) |
| D | License | Proprietary or Open |
| E | Intelligence Index | Artificial Analysis composite quality/intelligence score |
| F | Cost per Task (USD) | Blended cost per representative task |
| G | Median Tokens/s | Output throughput |
| H | Median First Chunk (s) | Time to first token / first chunk latency |
| I | Total Response (s) | Total end-to-end response time |
| J | Reasoning Time (s) | Time spent reasoning (blank/-- for non-reasoning models) |
| K | Function Calling | Yes if tool/function calling supported, else blank |
| L | JSON Mode | Yes if structured JSON output supported, else blank |
| M | OpenAI Compatible | Yes if OpenAI-compatible API exposed, else blank |
| N | API ID | Exact model identifier used when calling the API |
| O | Footnotes | Reserved for annotations; currently blank |

Columns A-J were already present. Columns K-O are the Expanded Columns fields populated in the most recent update.

# How It Was Generated

## 1\. Source

All values originate from the public Artificial Analysis leaderboard: https://artificialanalysis.ai/leaderboards/providers  
The Expand Columns toggle must be enabled to reveal the capability fields (Function Calling, JSON Mode, OpenAI Compatible, API ID). Values were confirmed against the live page before being written.

## 2\. Populating columns K-O via Google Apps Script

An Apps Script function (fillLeaderboardColumns) was used instead of manual cell entry. A hard-coded raw array holds one pipe-delimited string per endpoint: Provider|Model|FunctionCalling|JSONMode|OpenAICompatible|APIID|Footnotes. Each line is split on | and stored in a lookup map keyed by Provider \+ '\#\#\#' \+ Model. The script reads columns A and B from every sheet row, builds the same key, and on a match writes Function Calling, JSON Mode, OpenAI Compatible, API ID, and Footnotes into columns K-O.  
Key properties: matches by provider \+ model (order-independent), idempotent (safe to re-run), and only touches columns K-O. Issues resolved during generation: a key-separator mismatch (unified to \#\#\#) and a missing Parasail | Kimi K2.6 entry (added and re-run).

## 3\. JSON export via Google Apps Script

A second function, exportLeaderboardJson(), produces a clean JSON representation directly from the sheet, avoiding the delimiter/quoting fragility of CSV/TSV. It reads the used range, uses row 1 as object keys, emits an array of objects (one per data row), preserves native types (numbers stay numbers; \-- placeholders stay strings), and writes the result to a Google Drive file.  
Drive output (latest run): file artificial-analysis-leaderboard.json, MIME type application/json, 523 rows, at https://drive.google.com/file/d/1AT0NBS6NiGSUCvO4qNl6oZn08\_kGhNer/view  
Idempotency of the export: each run overwrites the existing file's content in place (setContent) rather than creating duplicates, so the file URL/ID stays stable across runs. Authorization note: the first run required a one-time Google OAuth consent granting the Drive scope (in addition to Sheets); this has been granted, so subsequent runs need no re-authorization. Note: Apps Script truncates very large on-screen logs, but the full dataset is written to the Drive file.

# How To Keep It Up To Date

The leaderboard is a living data source \- providers, prices, throughput, and capabilities change frequently.

## Routine refresh

* Snapshot first. Duplicate Sheet1 with a dated name (e.g., Sheet1\_backup\_YYYY-MM-DD) before changes. Backups already exist: Sheet1\_backup\_2026-07-20\_13-24 and Sheet1\_backup\_2026-07-20\_13-25.  
* Open the source and enable Expand Columns.  
* Update A-J for existing rows; add/remove rows for new or retired endpoints, matching exact model names (including suffixes).  
* Update the raw array in fillLeaderboardColumns for any new endpoints, confirming each capability against the live page.  
* Run fillLeaderboardColumns to refill columns K-O (idempotent; matches by provider+model).  
* Spot-check for gaps \- a blank K-O usually means the model name in the array does not exactly match the sheet.  
* Run exportLeaderboardJson to regenerate the Drive JSON. It overwrites the same file, so the URL stays constant.

## Important maintenance rules

* Exact-match discipline: matching is on Provider \+ Model text; any difference in spacing, capitalization, or suffix causes a silent miss. Copy names verbatim from the source.  
* Keep the separator consistent: the parse loop and lookup loop must use the same key separator (currently \#\#\#).  
* Capabilities are Yes-or-blank in columns K/L/M; the script normalizes this automatically.  
* Footnotes (O) are intentionally blank and can be filled manually.

## Optional improvements

* Time-based trigger: run fillLeaderboardColumns and/or exportLeaderboardJson on a schedule.  
* Direct fetch: if Artificial Analysis exposes an API or downloadable dataset, replace the hard-coded raw array with a UrlFetchApp call.  
* Serve JSON as an endpoint: convert exportLeaderboardJson logic into a doGet(e) web app returning ContentService-typed JSON.  
* Rename the Apps Script project (currently Untitled project) to something like AA-Leaderboard-Sync.
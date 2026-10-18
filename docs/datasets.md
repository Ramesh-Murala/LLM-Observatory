# Custom datasets and evidence review

The dashboard accepts UTF-8 JSONL files containing 1–200 cases and at most 512,000 bytes.
Each line defines `id`, `category`, `prompt`, `baseline`, `candidate`, and nonempty `checks`.
IDs must be unique ASCII identifiers using letters, digits, dash, dot, or underscore.
Prompts and fixture responses are bounded at 20,000 characters each. Every contract is
validated before the first provider call, including CLI remote evaluations.

```json
{"id":"order-1","category":"orders","prompt":"Return quantity 2 as an integer.","baseline":"{\"quantity\":2}","candidate":"{\"quantity\":\"2\"}","checks":[{"type":"json_schema","schema":{"type":"object","required":["quantity"],"properties":{"quantity":{"type":"integer","minimum":1}},"additionalProperties":false}}]}
```

For fixtures, the response fields are the actual scripted outputs. For remote runs, the
provider receives only `prompt`; response fields remain mandatory to make the same file
usable offline. They are never reference labels for a live generation. Checks contain the
actual references and constraints. A baseline is allowed to fail: it is measured, not assumed
correct. Stable fixture mode deliberately replays the baseline for both variants.

## Versioning

The registry hashes the exact UTF-8 file bytes. An upload with identical content returns the
existing version, even if submitted under another name. Any byte change creates a new version;
whitespace and line-ending changes therefore count. Names are labels, not mutable aliases.
Runs embed the dataset hash and name. Versions survive application restarts in SQLite or
PostgreSQL. There are no update or delete routes. List endpoints show the latest 100 entries.

## Run the complete API example

Start the API from the README, then from a second terminal:

```sh
python examples/custom_dataset.py
```

This uploads the included 12-case structured-contract dataset, runs stable and regression
fixtures, saves both reports and a CSV under `reports/`, and prints their comparison.
It makes no paid model calls. The dashboard can perform the same upload and evaluations.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/datasets` | Built-in dataset plus uploaded version metadata |
| `POST /api/datasets` | JSON body with `name` and `jsonl`; validates and persists |
| `POST /api/runs` | Optional `dataset_id`, `scenario`, `max_quality_drop`, `max_latency_ratio` |
| `GET /api/compare?baseline=ID&candidate=ID` | Compare the candidate traces from two runs |
| `GET /api/runs/ID/export?format=json` | Full evidence with prompts and responses |
| `GET /api/runs/ID/export?format=csv` | Case metrics without prompt/response bodies |

Comparing different dataset fingerprints returns HTTP 409, even when case IDs happen to match.
Reports count paired pass→fail regressions and fail→pass improvements, retaining failures by
category. They also provide Wilson 95% intervals for the two individual pass proportions.
Those intervals assume independent, representative cases. They do not measure repeatability
of nondeterministic models, do not give an interval for the paired delta, and are descriptive
only on the small synthetic suites. A produced comparison report is not a release approval.

## Schema semantics

The `json_schema` evaluator uses Draft 2020-12. It checks nested types, bounds, arrays, required
fields, enums, conditionals, and local references. Only document-local `$ref`/`$dynamicRef`
values are accepted. External schema retrieval is disabled, and the tool never fetches remote
schemas. Format annotations are not assertions. Invalid JSON, duplicate object keys, NaN,
Infinity, and overflowing numeric literals fail the JSON checks.

JSON Schema permits `2.0` for an integer constraint (a mathematically integral number); the
legacy `json` field contract intentionally uses exact Python types instead. These semantics
are different and are preserved for compatibility.

Use trusted contract definitions: regex patterns and recursive schemas can be computationally
expensive. This local tool has no hostile-input execution sandbox, authentication, or dataset
retention policy. Run on loopback and avoid private data unless you control the machine and
database. Prompt and response bodies are persisted for trace inspection.

## Browser checks

CI installs Playwright 1.62.1 and Chromium and exercises the custom-dataset workflow on
desktop and at a 390-pixel mobile viewport. To reproduce manually with Node.js installed:

```sh
npm install --no-save playwright@1.62.1
npx playwright install chromium
# Start the Python API in a second terminal, then:
node scripts/browser_smoke.cjs
```

The browser test checks upload, both release decisions, seven paired regressions, failed-case
filtering, trace details, CSV download, client errors, and document width on mobile. Its screenshots
are saved under `/tmp/observatory-workspace-*.png` and uploaded as CI artifacts. Screenshot
paths can be adjusted for Windows; browser automation is optional for running the application.

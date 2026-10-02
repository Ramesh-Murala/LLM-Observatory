# Provider setup

The fixture provider is the default. Remote calls use a `/chat/completions` endpoint and a bearer
token; use a provider that implements that shape. The adapter has a 45-second timeout and makes
one request per case per variant. The included dataset therefore creates 32 remote requests.

## Environment

```sh
export LLM_BASE_URL=https://your-provider.example/v1
export LLM_API_KEY=your-key
export LLM_BASELINE_MODEL=your-baseline-model
export LLM_CANDIDATE_MODEL=your-candidate-model
observatory gate --provider compatible --scenario regression
```

```powershell
$env:LLM_BASE_URL = 'https://your-provider.example/v1'
$env:LLM_API_KEY = 'your-key'
$env:LLM_BASELINE_MODEL = 'your-baseline-model'
$env:LLM_CANDIDATE_MODEL = 'your-candidate-model'
observatory gate --provider compatible --scenario regression
```

`.env.example` documents the variables; the application does not automatically load `.env` files.
Set them in your shell or container environment. Never commit a populated key. Remote requests
are opt-in and may incur charges.

## Pricing

Supply both input and output rates for each model, in USD per million tokens:

```sh
export LLM_BASELINE_INPUT_USD_PER_MILLION=0.10
export LLM_BASELINE_OUTPUT_USD_PER_MILLION=0.40
export LLM_CANDIDATE_INPUT_USD_PER_MILLION=0.20
export LLM_CANDIDATE_OUTPUT_USD_PER_MILLION=0.80
```

These are arithmetic examples, not current provider prices. Cost is `(input tokens × input rate
+ output tokens × output rate) / 1,000,000`. Missing prices or missing provider usage yield `null`.
The report records the rates you supplied. Failed requests can still have provider charges that
are absent from the report, so estimates must not be used as billing reconciliation.

## Custom datasets

Copy the included JSONL file and add representative cases. Each line needs a unique `id`, a
`category`, `prompt`, fixture `baseline` and `candidate` strings, and a nonempty `checks` array.
Remote providers ignore the fixture response strings but use the same prompts and checks.

```json
{"id":"contract-01","category":"Structured output","prompt":"Return JSON with count as an integer.","baseline":"{\"count\":3}","candidate":"{\"count\":\"3\"}","checks":[{"type":"json","fields":{"count":"int"}}]}
```

Supported field type names are Python JSON value types such as `str`, `int`, `float`, `bool`,
`list`, and `dict`. Required top-level fields are checked; nested contents and additional fields
are not. Use reference checks where output values also matter.

```sh
observatory gate --dataset datasets/team-contracts.jsonl --scenario regression
observatory seed --dataset datasets/team-contracts.jsonl --provider compatible --scenario regression
```

The remote adapter is tested with an HTTP mock. A live commercial provider has not been called
as part of this build. Providers may require different options; add a separate adapter for native
APIs rather than assuming compatibility.

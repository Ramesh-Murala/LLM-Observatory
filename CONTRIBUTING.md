# Contributing

Start with an issue describing the behavior you want to change. Keep fixes focused and include a
test when a change affects scoring, provider handling, persistence, or release decisions.

```sh
pip install -c constraints.txt -e '.[dev]'
ruff check .
pytest -q
observatory gate --scenario stable
```

Dataset changes must include an explanation of the expected baseline and candidate behavior.
Do not add credentials, private prompts, or evaluation reports containing personal data.
Use concrete commit messages such as `Handle missing token usage in compatible provider`.

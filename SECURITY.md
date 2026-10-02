# Security

This release is a local development tool. Bind it to loopback. Authentication, authorization,
rate limiting, retention controls, and multi-user isolation are not implemented.

Prompts and responses are stored in the database and CLI reports. Use public or synthetic cases.
OpenTelemetry spans contain case IDs, variants, fingerprints, and pass/fail results; they do not
contain prompt or response bodies. Provider errors retain only the exception class.

Remote provider calls are opt-in through the CLI and can incur charges. Never commit `.env` or
API keys. Docker Compose credentials are intended for local development only.

For a vulnerability, use the repository's private vulnerability reporting feature when enabled.
Do not publish secrets or exploit details in a public issue.

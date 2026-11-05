# Security Policy

Portuguese version: [SECURITY.pt-BR.md](SECURITY.pt-BR.md).

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.3.x (macOS) | Yes |
| Older | No |
| 1.3.0 test builds (Windows, Linux) | Not released as stable; reports are welcome |

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private reporting: **Security > Report a vulnerability** on this repository, or write to manager@byvulcan.com. Include the version, the steps to reproduce and the impact.

This is a project maintained by one person, so there is no guaranteed response time. Reports are read as soon as possible, and fixes are credited in the changelog if you wish.

## Scope

The threat model is in [docs/en/security.md](docs/en/security.md). Especially relevant:

- Access to the local server without the token, or from another origin.
- Anything that writes to `~/.claude` or `~/.codex`, or that deletes data for good.
- Code execution through a project folder, a session file or a prompt being read.
- Secrets reaching Anthropic or a log despite the masking.

Out of scope, by design: another process of the same user reading the app's memory or the Keychain item, and running an unsigned app. Both are documented as accepted risks.

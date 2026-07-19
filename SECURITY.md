# Security policy

## Supported version

Only the current `main` branch of this alpha is maintained. There is no stable or production release yet.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting or security-advisory feature for the repository. Do not place credentials, memory contents, private prompts, machine identifiers, or exploit details in a public issue.

Include the affected revision, impact, a minimal synthetic reproduction, and whether the issue crosses the documented IPv4-loopback boundary. Remove tokens, cookies, local paths, personal information, and model-generated private content from logs before attaching them.

## Security boundary

JARVIS is designed for one local macOS user and binds its application and model services to IPv4 loopback. It is not a security boundary against other processes running as the same operating-system user. Cloud fallback, LAN exposure, telemetry, and remote authentication are outside the current alpha.

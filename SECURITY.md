# Security Policy

## Supported Versions

Security updates are provided for the latest version of this project available on the main branch.

| Version | Supported |
| ------- | --------- |
| latest  | Yes       |
| older versions | No |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

**Do not disclose security vulnerabilities through public GitHub issues.**

To report a vulnerability, contact the maintainer privately or use GitHub's private vulnerability reporting feature if enabled.

When reporting a vulnerability, please include:

- A clear description of the issue
- Steps to reproduce the vulnerability
- Potential impact
- Relevant logs, screenshots, or proof-of-concept details, if available

## Responsible Disclosure

Please allow reasonable time for the vulnerability to be investigated and addressed before any public disclosure.

## AI/LLM Security Scope

This project includes AI/LLM-assisted components. Security-relevant issues include, but are not limited to:

- Prompt injection or jailbreak attempts
- Data leakage or exposure of sensitive information
- Unsafe handling of uploaded or retrieved documents
- Hallucinated outputs that may cause unsafe behavior
- Unauthorized access to model, API, database, or vector store resources
- Model denial-of-service or excessive resource consumption
- Dependency, model, dataset, or supply-chain vulnerabilities
- Insecure configuration of API keys, secrets, environment variables, or deployment settings

## Sensitive Data

Do not submit secrets, credentials, API keys, private documents, personal data, or confidential information to the system unless appropriate safeguards are in place.

If sensitive data exposure is discovered, report it as a security vulnerability.

## Out of Scope

The following are generally out of scope unless they demonstrate a concrete security impact:

- General AI hallucinations without security impact
- Inaccurate or low-quality generated answers
- Feature requests or usability issues
- Issues caused by unsupported local modifications
- Social engineering attempts without a technical vulnerability

## Security Best Practices for Deployment

Anyone deploying this project is responsible for implementing appropriate safeguards, including:

- Access control and authentication
- Input validation and file validation
- Rate limiting and abuse prevention
- Secret management through environment variables or secret stores
- Logging and monitoring
- Dependency updates and vulnerability scanning
- Review of AI-generated outputs before relying on them
- Proper isolation of model, database, and vector store services

# Security policy
- Report vulnerabilities privately by email: sriramojunikhil66@gmail.com (please do not open public issues for security bugs).
- Never commit secrets. Use `.env` (git-ignored). The site stores a user's Groq key only in their own browser.
- Backend controls: JWT access/refresh tokens, bcrypt, scoped RBAC, Redis leaky-bucket rate limiting, prompt-injection and PII guardrails.

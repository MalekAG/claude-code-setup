---
name: security-review
description: Run a comprehensive security review on a project directory. Scans for OWASP Top 10 vulnerabilities, hardcoded secrets, auth flaws, injection risks, dependency issues, and infrastructure misconfigurations. Works without git. Use when user asks to "security review", "audit security", "check for vulnerabilities", or "scan for security issues".
argument-hint: './al-atheer, ./plc-documenter, ./SCADA-Dashboard, or any project path'
---

# security-review: Comprehensive Project Security Audit

Perform a deep security review of any project directory. No git required. Scans source code, configs, dependencies, and infrastructure files. Produces a structured report with severity ratings and actionable fixes.

## Input Parsing

Parse the user's invocation:
- **Argument provided** (e.g., `/security-review ./al-atheer`) -> `PROJECT_PATH = resolved absolute path`
- **No argument** -> Use current working directory as `PROJECT_PATH`
- **Flags**: `--quick` (surface scan, ~5 min), default (standard, ~10 min), `--deep` (exhaustive, ~15 min)

Store:
- `PROJECT_PATH` — absolute path to project root
- `PROJECT_NAME` — directory basename
- `DEPTH_MODE` — quick | standard | deep

## Pre-Flight

Before scanning:

1. **Verify project exists**: Check `PROJECT_PATH` is a valid directory
2. **Detect stack**: Read package.json, requirements.txt, Cargo.toml, go.mod, Dockerfile, etc. to determine:
   - `LANGUAGES` — js/ts, python, go, rust, etc.
   - `FRAMEWORK` — Next.js, FastAPI, Express, Django, etc.
   - `DATABASE` — Supabase, Postgres, MongoDB, etc.
   - `HAS_DOCKER` — true/false
   - `HAS_ENV` — true/false (check for .env, .env.local, .env.example)
3. **Read project CLAUDE.md** if it exists — extract architecture context
4. **Map source files**: Glob for source files, excluding node_modules, .next, __pycache__, .venv, dist, build, .git

Display to user:
```
Security Review: {PROJECT_NAME}
Stack: {FRAMEWORK} + {LANGUAGES} + {DATABASE}
Mode: {DEPTH_MODE}
Scanning {N} source files across {M} directories...
```

---

## Scan Categories

Run these as **parallel subagents** using the Task tool. Each subagent gets `model: "sonnet"` and `subagent_type: "general-purpose"`.

### Category 1: Secrets & Configuration

**Subagent prompt template:**
```
You are a security auditor. Review the project at {PROJECT_PATH} for hardcoded secrets and configuration issues.

SCAN FOR:
1. Hardcoded API keys, tokens, passwords, database credentials in source files
2. .env files committed or accessible (check .gitignore if exists)
3. JWT secrets, encryption keys, or salts in source code
4. Default/weak credentials (admin/admin, test/test, password123)
5. Sensitive data in client-side code (browser-accessible secrets)
6. Debug mode enabled in production configs
7. Verbose error messages that leak internal details

TOOLS: Use Grep to search for patterns like:
- password, secret, api_key, apikey, token, credential, auth
- Bearer, Basic, sk-, pk-, AKIA (AWS), ghp_ (GitHub)
- process.env usage without validation
- .env files and .env.example comparison

Use Read to examine suspicious files.

OUTPUT FORMAT:
For each finding:
- **ID**: SEC-001, SEC-002, etc.
- **Severity**: CRITICAL / HIGH / MEDIUM / LOW / INFO
- **File**: path:line_number
- **Finding**: What was found
- **Evidence**: The actual code/string (redact actual secret values with ****)
- **Fix**: How to remediate

Write findings to {PROJECT_PATH}/.tmp/security-review/01-secrets.md
```

### Category 2: Authentication & Authorization

**Subagent prompt template:**
```
You are a security auditor. Review the project at {PROJECT_PATH} for authentication and authorization vulnerabilities.

SCAN FOR:
1. Authentication bypass possibilities (missing auth checks on routes/endpoints)
2. Weak password policies (no validation, no hashing, plaintext storage)
3. Session management issues (no expiry, predictable tokens, missing httpOnly/secure flags)
4. JWT issues (weak algorithm, no expiry, secret in code, missing validation)
5. OAuth/OIDC misconfigurations (open redirect, state parameter missing)
6. Role-based access control gaps (missing checks, privilege escalation paths)
7. Supabase RLS policies — check if all tables have RLS enabled and policies are correct
8. API routes without authentication middleware
9. CORS misconfiguration (wildcard origins, credentials with wildcard)
10. CSRF protection gaps

TOOLS: Use Grep to find auth-related code (middleware, guards, policies, RLS).
Use Read to examine auth files, middleware, API routes, and Supabase migrations.

OUTPUT FORMAT: Same as Category 1 (ID: AUTH-001, etc.)
Write findings to {PROJECT_PATH}/.tmp/security-review/02-auth.md
```

### Category 3: Injection & XSS

**Subagent prompt template:**
```
You are a security auditor. Review the project at {PROJECT_PATH} for injection and cross-site scripting vulnerabilities.

SCAN FOR:
1. SQL injection — raw queries, string concatenation in SQL, missing parameterization
2. Command injection — exec(), os.system(), child_process, subprocess with user input
3. XSS — dangerouslySetInnerHTML, innerHTML, document.write, unescaped template vars
4. Template injection — user input in server-side templates without escaping
5. Path traversal — user-controlled file paths without sanitization
6. NoSQL injection — unsanitized queries to MongoDB/similar
7. LDAP/XML injection if applicable
8. Deserialization — pickle, eval, Function(), JSON.parse on untrusted input
9. Header injection — user input in HTTP headers without validation
10. Log injection — user input written directly to logs

TOOLS: Use Grep for dangerous patterns (eval, exec, innerHTML, raw SQL, subprocess).
Use Read to examine data flow from user input to dangerous sinks.

OUTPUT FORMAT: Same as Category 1 (ID: INJ-001, etc.)
Write findings to {PROJECT_PATH}/.tmp/security-review/03-injection.md
```

### Category 4: API & Data Security

**Subagent prompt template:**
```
You are a security auditor. Review the project at {PROJECT_PATH} for API and data security issues.

SCAN FOR:
1. Missing input validation on API endpoints (no schema validation, no type checking)
2. Mass assignment — accepting all fields from request body without allowlist
3. Missing rate limiting on sensitive endpoints (login, signup, password reset)
4. Information disclosure in error responses (stack traces, internal paths, DB errors)
5. Insecure file upload (no type validation, no size limits, executable uploads)
6. Missing security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
7. Insecure data exposure — returning sensitive fields (password hashes, internal IDs)
8. Missing pagination / resource limits (denial of service via large queries)
9. SSRF — server making requests to user-controlled URLs
10. Insecure redirects — open redirect vulnerabilities

TOOLS: Use Grep to find API route definitions, middleware, response patterns.
Use Read to examine endpoint handlers and middleware chains.

OUTPUT FORMAT: Same as Category 1 (ID: API-001, etc.)
Write findings to {PROJECT_PATH}/.tmp/security-review/04-api.md
```

### Category 5: Dependencies & Infrastructure

**Subagent prompt template:**
```
You are a security auditor. Review the project at {PROJECT_PATH} for dependency and infrastructure security issues.

SCAN FOR:
1. Known vulnerable dependencies — check package.json/requirements.txt versions against known CVEs
   Run: npm audit (if package-lock.json exists) or pip audit (if requirements.txt exists)
2. Outdated dependencies with security patches available
3. Docker security — running as root, exposing unnecessary ports, secrets in Dockerfile/docker-compose
4. Docker Compose — hardcoded passwords, exposed ports, missing network isolation
5. CI/CD security — secrets in workflow files, unsafe GitHub Actions patterns
6. Deployment configs — debug mode, verbose logging, unnecessary services exposed
7. TLS/SSL — missing HTTPS enforcement, insecure redirects
8. File permissions — overly permissive configs, world-readable sensitive files
9. Missing .gitignore entries for sensitive files (.env, credentials, keys)
10. Supply chain — pinned vs unpinned dependencies, lockfile integrity

TOOLS: Use Bash to run npm audit or pip-audit if available.
Use Read to examine Dockerfile, docker-compose.yml, .github/workflows/, vercel.json, next.config.
Use Grep to find port exposures, volume mounts, environment variable patterns.

OUTPUT FORMAT: Same as Category 1 (ID: DEP-001, etc.)
Write findings to {PROJECT_PATH}/.tmp/security-review/05-deps.md
```

---

## Execution

### Step 1: Create output directory
```bash
mkdir -p {PROJECT_PATH}/.tmp/security-review
```

### Step 2: Launch subagents

**Quick mode**: Run Categories 1 + 3 only (secrets + injection — highest impact).
**Standard mode**: Run all 5 categories in parallel.
**Deep mode**: Run all 5 categories, then a follow-up pass for cross-cutting concerns.

Launch all applicable subagents in parallel using the Task tool:
- `model: "sonnet"` for all subagents
- `subagent_type: "general-purpose"`
- `mode: "bypassPermissions"` (read-only scanning, safe to auto-approve)

### Step 3: Collect results

After all subagents complete, read each findings file:
- `{PROJECT_PATH}/.tmp/security-review/01-secrets.md`
- `{PROJECT_PATH}/.tmp/security-review/02-auth.md`
- `{PROJECT_PATH}/.tmp/security-review/03-injection.md`
- `{PROJECT_PATH}/.tmp/security-review/04-api.md`
- `{PROJECT_PATH}/.tmp/security-review/05-deps.md`

### Step 4: Synthesize report

Combine all findings into a single report. Deduplicate overlapping findings.

Count by severity:
- `CRITICAL_COUNT`, `HIGH_COUNT`, `MEDIUM_COUNT`, `LOW_COUNT`, `INFO_COUNT`

Calculate risk score (0-100):
- Each CRITICAL = 25 points
- Each HIGH = 10 points
- Each MEDIUM = 3 points
- Each LOW = 1 point
- Cap at 100

### Step 5: Write final report

Write to `{PROJECT_PATH}/.tmp/security-review/SECURITY-REPORT.md`:

```markdown
# Security Assessment Report: {PROJECT_NAME}

## Executive Summary
- **Target**: {PROJECT_PATH}
- **Assessment Date**: {YYYY-MM-DD}
- **Stack**: {FRAMEWORK} + {LANGUAGES} + {DATABASE}
- **Risk Score**: {SCORE}/100 ({CRITICAL if >= 75, HIGH if >= 50, MEDIUM if >= 25, LOW if < 25})
- **Findings**: {TOTAL} total ({CRITICAL_COUNT} Critical, {HIGH_COUNT} High, {MEDIUM_COUNT} Medium, {LOW_COUNT} Low, {INFO_COUNT} Info)

## Risk Summary

| Severity | Count | Categories |
|----------|-------|------------|
| CRITICAL | {N}   | {list}     |
| HIGH     | {N}   | {list}     |
| MEDIUM   | {N}   | {list}     |
| LOW      | {N}   | {list}     |
| INFO     | {N}   | {list}     |

## Critical & High Findings (Act Now)

{For each CRITICAL and HIGH finding, full detail with evidence and fix}

## Medium Findings (Plan to Fix)

{For each MEDIUM finding, summary with fix}

## Low & Info Findings

{Brief list}

## Recommendations

### Immediate Actions (This Sprint)
1. {Fix critical findings}

### Short-Term (Next 2 Sprints)
1. {Fix high findings}

### Long-Term (Backlog)
1. {Fix medium/low findings}

## Methodology
- **Scan type**: Static analysis (source code review)
- **Categories reviewed**: Secrets, Auth, Injection/XSS, API Security, Dependencies/Infrastructure
- **Files scanned**: {N} source files
- **Tool**: Claude Sonnet 4.5 security review agents
```

### Step 6: Display summary to user

```
---
Security Review Complete: {PROJECT_NAME}

Risk Score: {SCORE}/100 ({RATING})

Findings:
  CRITICAL  {N}  {bar}
  HIGH      {N}  {bar}
  MEDIUM    {N}  {bar}
  LOW       {N}  {bar}
  INFO      {N}  {bar}

Top Issues:
1. {Most critical finding — one line}
2. {Second most critical — one line}
3. {Third most critical — one line}

Full report: {PROJECT_PATH}/.tmp/security-review/SECURITY-REPORT.md

Want me to fix any of these issues?
---
```

---

## Deep Mode: Cross-Cutting Pass

In `--deep` mode, after the initial 5 categories, run one additional subagent:

**Cross-Cutting Analysis subagent:**
```
Review the security findings from the initial scan at {PROJECT_PATH}/.tmp/security-review/.
Read all 5 finding files (01-secrets.md through 05-deps.md).

Look for:
1. Attack chains — combinations of findings that create a more severe vulnerability
2. Missing findings — common vulnerabilities for {FRAMEWORK} not yet covered
3. Business logic flaws — based on the application's purpose and data flow
4. Data flow analysis — trace user input from entry to storage, looking for gaps

Write additional findings to {PROJECT_PATH}/.tmp/security-review/06-cross-cutting.md
```

---

## Error Handling

- **Project not found**: Tell user the path doesn't exist, ask for correct path
- **No source files**: Report "No scannable source files found" with list of what was checked
- **Subagent failure**: Report which category failed, include results from categories that succeeded
- **Empty findings**: A category with zero findings is a GOOD result — report it as "No issues found"

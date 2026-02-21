# Style Rules

## Code Style
- Concise code, minimal comments — only comment where logic isn't self-evident
- No over-engineering: only make changes directly requested or clearly necessary
- Don't add features, refactoring, or "improvements" beyond what was asked
- Don't add docstrings, comments, or type annotations to code you didn't change

## File Management
- Always read existing code before modifying it
- Prefer editing existing files over creating new ones
- Never create documentation files unless explicitly asked
- Don't create helpers, utilities, or abstractions for one-time operations

## Error Handling
- Only validate at system boundaries (user input, external APIs)
- Trust internal code and framework guarantees
- Don't add error handling for scenarios that can't happen

## Complexity Budget
- Three similar lines > premature abstraction
- Don't design for hypothetical future requirements
- The right amount of complexity = minimum needed for current task
- No backwards-compatibility hacks (unused vars, re-exports, removal comments)

## Skills-First
- Before writing any custom script, check if an installed skill handles it
- Skills are pre-built and tested — prefer them over custom code

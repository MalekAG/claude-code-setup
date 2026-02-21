---
name: interview
description: Conducts in-depth PRD interviews using AskUserQuestion to uncover hidden assumptions, edge cases, technical implications, and UI/UX concerns. Reads PRD.md, asks probing non-obvious questions, and writes the refined PRD back to the file.
---

# PRD Interview Skill

This skill transforms a rough PRD into a comprehensive specification through systematic, non-obvious questioning.

## When to Use

- When a PRD.md file exists but needs deeper exploration
- Before starting implementation to uncover blind spots
- To challenge assumptions and surface hidden complexity
- To document decisions and tradeoffs explicitly
- When starting from scratch with just an idea (no PRD yet)

## Workflow

### Phase 1: PRD Analysis

**If PRD.md exists:**
1. Read the PRD.md file from the current context or specified path
2. Identify key areas that need deeper exploration:
   - Stated requirements (what's explicitly written)
   - Implied requirements (what's assumed but not stated)
   - Missing requirements (what should be there but isn't)
   - Technical dependencies
   - User journey gaps

**If no PRD.md exists (starting from scratch):**
1. Begin with foundational questions to establish the product vision
2. Ask about the problem being solved and who it's for
3. Build the PRD structure progressively through interview questions
4. Create PRD.md at the end with all gathered information

### Phase 2: Systematic Interviewing

Use AskUserQuestion to conduct a multi-turn interview. Questions should be:
- **Non-obvious**: Not things that can be inferred from the PRD
- **Probing**: Challenge assumptions, not just confirm them
- **Specific**: Ask about concrete scenarios, not abstract concepts

#### Question Categories

**Starting from Scratch** (when no PRD exists):
- "In one sentence, what problem are we solving?"
- "Who specifically has this problem? Be more specific than 'users'."
- "What are they doing today to solve it? Why does that suck?"
- "What's the smallest thing we could build that would be useful?"
- "If this is wildly successful in 6 months, what does that look like?"
- "What are the 3 things this absolutely MUST do? And what are 3 things it should NOT do?"

**Technical Implementation**:
- "You mention [X feature]. When this fails--and it will--what should the user see? What happens to their data?"
- "If [component A] goes down, does [component B] continue working independently, or is it a hard dependency?"
- "What's the data migration story for users who have existing [related data]?"
- "You want [real-time feature]. What's acceptable latency? 100ms? 500ms? 2 seconds?"
- "How does this behave with 10 users? 10,000? 10 million concurrent?"

**UI/UX**:
- "Walk me through what happens if the user is interrupted mid-flow. Do they lose progress?"
- "On a 3G connection in a tunnel, what does the user experience?"
- "What's the empty state? First-time users see what exactly?"
- "If a user makes a mistake, can they undo it? How far back?"
- "Accessibility: How does a screen reader announce [specific interaction]?"

**Edge Cases & Error States**:
- "User submits [form], but network drops. What happens client-side? Server-side?"
- "Two users edit the same [resource] simultaneously. Who wins?"
- "What if the user's session expires mid-[action]?"
- "User has 10,000 [items]. Does this UI still work? Pagination? Virtual scrolling?"

**Business Logic & Tradeoffs**:
- "If you had to cut one feature from this scope, which one and why?"
- "What's the 'good enough' version that could ship in half the time?"
- "This implies [inference]. Is that intentional or am I misreading it?"
- "What existing behavior does this change? Who might be surprised?"

**Security & Privacy**:
- "What data is stored? Where? Who can access it?"
- "If someone malicious gets access to [X], what's the blast radius?"
- "GDPR: How do users delete their data from this feature?"

**Dependencies & Integration**:
- "What third-party services does this depend on? What if they go down?"
- "Does this require changes to [other system/API]? Who owns that?"
- "What's the rollback plan if this ships and breaks something?"

### Phase 3: Iterative Refinement

Continue asking follow-up questions until:
1. All major sections have been explored
2. User indicates they've covered enough
3. Questions start becoming obvious/redundant

Use multi-select questions when presenting options or gathering preferences.

### Phase 4: PRD Enhancement

After the interview, update the PRD.md with:
1. **Clarifications**: Answers to questions integrated into requirements
2. **Edge Cases**: New section documenting edge case decisions
3. **Technical Notes**: Implementation considerations surfaced
4. **Tradeoffs**: Documented decisions and their rationale
5. **Open Questions**: Any remaining items that need stakeholder input

## Interview Technique Guidelines

**Start broad, then narrow**:
- Begin with high-level architecture questions
- Drill into specific flows that seem underspecified
- End with edge cases and error handling

**Don't accept the first answer**:
- Follow up with "And if that fails?"
- Ask "What if the user doesn't do that?"
- Challenge with "Why not [alternative approach]?"

**Make assumptions explicit**:
- "I'm assuming [X]. Correct?"
- "This implies you want [Y behavior]. Is that right?"

**Surface tradeoffs**:
- "This will make [A] easier but [B] harder. Acceptable?"
- "Fast or thorough? Pick one for this feature."

## Output Format

After interviewing, write the enhanced PRD back to the file with this structure:

```markdown
# [PRD Title]

## Overview
[Original + refined overview]

## Requirements

### Core Requirements
[Refined and prioritized requirements]

### Edge Cases & Error Handling
[New section with all edge cases discussed]

### Technical Specifications
[Implementation details surfaced during interview]

## Decisions & Tradeoffs
| Decision | Options Considered | Choice | Rationale |
|----------|-------------------|--------|-----------|
| ...      | ...               | ...    | ...       |

## Open Questions
- [ ] Questions that still need answers

## Interview Notes
[Summary of key insights from the interview]
```

## Example Session

**User invokes**: `/interview` with PRD.md in context

**Claude reads PRD, then asks**:
> "Your PRD mentions a 'save draft' feature. Three questions:
> 1. How often does auto-save trigger--time-based, action-based, or both?
> 2. If the user closes the browser with unsaved changes, do we warn them?
> 3. Drafts live forever, or do they expire?"

**User answers**, Claude follows up:
> "You said drafts expire after 30 days. What happens to users mid-document when it expires? Do they get a warning at 25 days? What's the recovery path if they miss it?"

**This continues across all sections until complete.**
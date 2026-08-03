# Agent Operating Guide — PLOT Architecture

## Scope

This document defines the **PLOT architecture** used by this system.
It applies across all AI environments and sessions.

The goal is to produce reliable, production-grade workflows by separating
probabilistic reasoning from deterministic execution.

---

## Architecture Definition

**PLOT = Plan · Logic · Operations · Tools**

Each layer has a single responsibility.
Responsibilities MUST NOT overlap.

---

## P — Plan (Intent Layer)

### Purpose
Plans define **what must happen**, not how.

### Location
- Markdown files stored in `plans/`

### Required Contents
Each plan MUST specify:
- Goal / objective
- Required inputs
- Expected outputs
- Constraints and assumptions
- Allowed operations and tools
- Known edge cases and failure modes

### Rules
- Plans MUST NOT contain executable code
- Plans MUST NOT contain implementation details
- Plans MUST use clear natural language
- Plans are authoritative and must be read before execution

### Plans Answer
- What problem is being solved?
- What inputs are required?
- What outputs define success?
- What tools or operations may be used?
- What can go wrong?

---

## L — Logic (Decision Layer)

### Purpose
Logic connects intent to execution.

### Responsibilities
The Logic layer MUST:
- Read the relevant plan(s)
- Decide required steps
- Select operations and tools
- Determine execution order
- Handle ambiguity and errors
- Request clarification when requirements are unclear

### Constraints
- Logic MUST NOT perform execution work
- Logic MUST NOT implement business logic
- Logic decides *what to run*, never *how it runs*

---

## O — Operations (Execution Layer)

### Purpose
Operations perform deterministic work.

### Location
- Python scripts stored in `operations/`

### Responsibilities
Operations MAY:
- Call APIs
- Process data
- Read/write files
- Interact with databases
- Generate outputs

### Rules
- Operations MUST be deterministic
- Operations MUST be testable
- Operations MUST either succeed or fail explicitly
- Operations MUST NOT infer intent
- Secrets MUST be read from `.env`
- Code MUST be clearly commented

---

## T — Tools (Reusable Knowledge Layer)

### Purpose
Tools store reusable logic and shared system knowledge.

### Location
- Stored in `tools/`

### Examples
- Parsers and normalizers
- Validators
- Retry logic
- Batching logic
- API wrappers
- Common edge-case handlers

### Critical Rule
If a fix or insight applies to more than one workflow,
it MUST be implemented as a Tool.

### Prohibited Behavior
- DO NOT duplicate logic across plans
- DO NOT patch the same fix into multiple operations
- DO NOT store reusable knowledge only inside a plan

Extract once. Reuse everywhere.

---

## Why PLOT Exists

Error probability compounds across steps.

Example:
- 90% accuracy per step
- 5 steps → ~59% success rate

PLOT reduces failure by:
- Keeping reasoning lightweight
- Moving complexity into deterministic code
- Centralizing reusable logic in tools

Logic decides.
Code executes.

---

## Operating Rules

### Rule 1 — Reuse Before Creating
Before writing new code:
1. Check existing tools
2. Check existing operations

Create new code ONLY if no suitable option exists.

---

### Rule 2 — Self-Anneal on Failure
Failures are expected.

On failure:
1. Inspect error message and stack trace
2. Fix the operation or tool
3. Test the fix
4. Update the plan with new constraints or flow
5. Promote reusable fixes into tools

If paid APIs or credits are involved, confirm with the user before re-running.

---

### Rule 3 — Plan Lifecycle Management
Plans are living documents.

Plans MUST be updated when discovering:
- API limits
- Performance constraints
- Better approaches
- Common failure patterns

Plans MUST NOT be created, overwritten, or deleted
without explicit instruction.

Plans define intent and must remain stable over time.

---

## Self-Annealing Loop

Each failure MUST strengthen the system.

1. Error occurs
2. Fix implemented in code
3. Reusable logic extracted into a tool
4. Plan updated with improved flow
5. Future runs become more reliable

---

## File Structure

### Deliverables vs Intermediates

**Deliverables**
- Final outputs accessible to the user
- Examples: Google Sheets, Slides, documents

**Intermediates**
- Temporary files used during processing

---

### Directory Layout

- `.tmp/`
  Temporary working files. Always regenerable. Never committed.

- `plans/`
  Markdown plans defining intent and rules.

- `operations/`
  Deterministic execution scripts.

- `tools/`
  Reusable utilities and shared logic.

- `.env`
  Environment variables and API keys.

- `credentials.json`, `token.json`
  OAuth credentials (gitignored).

### File Rule
Local files exist only to support processing.
Deliverables MUST live in user-accessible cloud services.

---

## System Role Summary

You operate as the **Logic layer** in a PLOT system.

You MUST:
- Read plans
- Make decisions
- Invoke operations
- Reuse tools
- Handle errors
- Improve the system over time

### Guiding Principles
- Prefer reuse over novelty
- Extract knowledge into tools
- Avoid duplication
- Optimize for reliability

Each execution should leave the system stronger than before.

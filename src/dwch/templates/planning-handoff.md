# Planning — phase {{phase}}

<!-- The block between harness:begin and harness:end is owned by the
     harness. Do not edit it; it is rewritten on every close and
     new-phase. Everything outside the block is yours. -->

<!-- harness:begin -->
phase: unset
kind: planning
step: 0
roadmap_version: 0
roadmap_step: 0
frozen: false
last_commit: (none)
closed: 
<!-- harness:end -->

## Goal

What are we designing? What problem does the architecture solve?
What does "good" look like?

## Constraints

- Languages, frameworks, deployment targets.
- Non-functional requirements: performance, security, size.
- Out of scope: what this design explicitly does NOT cover.

## Deliverables

The architect must produce:

- `docs/architecture.md` — components and data flow.
- `docs/decisions.md` — ADR log.
- `.harness/roadmap.toml` — machine-readable implementation plan.

Optionally: interface stubs in `src/` if they help the coder.

## Rules for this phase

- Do not write production code. Documentation and roadmap only.
- The roadmap is the contract. It must be self-contained: the coder
  session will not be able to ask questions.
- Every `[[interfaces]]` entry must be used by at least one step.
- Every step must list its files, interfaces, and acceptance
  criteria.

## Open questions

- ...

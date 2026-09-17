# Handoff — phase {{phase}}

<!-- harness:begin -->
phase: unset
kind: development
step: 0
roadmap_version: 0
roadmap_step: 0
frozen: false
last_commit: (none)
closed: 
<!-- harness:end -->

## Goal

Describe the phase goal here. What does "done" look like?

## Scope

- Which roadmap steps does this phase cover?
- What is explicitly out of scope?

## Notes for the coder

- Implement the roadmap step by step.
- If a step is impossible as specified, write
  `.harness/deviations/step-NN.toml` with `type = "blocker"` and do
  not send substantive files. `roadmap_step` will not advance.
- If the spec is incomplete, decide, and write a deviation with
  `type = "assumption"`.
- If a prior step's code has a bug, fix it and write a deviation
  with `type = "bugfix-prior"`.

## Next

The first roadmap step of this phase.

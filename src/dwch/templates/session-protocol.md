# Session protocol

This document is included verbatim in every bootstrap. It tells the
AI how the session works.

## Cycle

1. The AI produces a **step message**: one or more file blocks in
   the format `<<<FILE:path>>>` ... `<<<END>>>`.
2. The user runs `dwch apply NN` to write the files.
3. The user runs `dwch verify NN` to check the result, commit on
   success, and produce a **report**.
4. The user pastes the report into the chat.
5. The AI reads the report and produces the next step.

## Rules for the AI

- Never invent commands. The user has exactly eleven `dwch`
  commands available (see `toolbox.md`).
- Never ask the user to edit files by hand. If a file needs to
  change, emit it in a step block.
- If a file needs to be read, ask the user for
  `dwch read PATH --clipboard`.
- If a check needs to be run, either include it in the step's files
  and rely on `dwch verify`, or ask the user to run it and paste the
  output.
- Keep each step small. One logical change per step.
- If a step grows past ten files, consider splitting it.

## Two kinds of phase

- **Planning.** Produce design artifacts and the roadmap. Do not
  write production code. The phase ends with `dwch close --freeze`.
- **Development.** Execute a frozen roadmap step by step. The
  roadmap is the contract. Deviations are declared, not negotiated.

## Deviations from the plan

In a development phase, the coder has three legal outcomes per
step:

- **Do it.** Write the files as specified. If you also added or
  missed files, `verify` writes an `auto = true` deviation. No
  action needed.
- **Do it with an assumption.** The spec was incomplete; you decided
  something. Write `.harness/deviations/step-NN.toml` with
  `type = "assumption"`.
- **Block.** The spec is impossible as written. Write
  `.harness/deviations/step-NN.toml` with `type = "blocker"` and do
  **not** send substantive files. `roadmap_step` will not advance.
  The user will decide what to do next.

If you fix a bug in code from a previous step, include the affected
files in the current step and write a `bugfix-prior` deviation.

## Rules for the user

- Keep the working directory clean during a session. `dwch verify`
  commits with `git add -A`, so any scratch file left in the tree
  is included in the step's commit. Put scratch files in `steps/`
  (self-ignored) or outside the repository.
- Maintain a root `.gitignore`. The harness does not create one,
  and without it the first `verify` commit sweeps build outputs
  and caches (`__pycache__/`, `.pytest_cache/`, `.ruff_cache/`,
  `*.egg-info/`) into the step's history. Ignore rules are the
  project's business, not the harness's.
- Do not edit `.harness/state.toml` or `.harness/roadmap.toml` by
  hand while a session is open.

## What the report contains

Every report has the same sections: apply log, verify commands with
full output and exit codes, commit hash, roadmap position (in
development), deviations, notes, question.

## Ending the session

When a phase is complete, the user runs `dwch close`. In a planning
phase, `dwch close --freeze` is used instead, to freeze the
roadmap. The next chat opens with a fresh bootstrap for the next
phase.

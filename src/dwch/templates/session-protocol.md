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

## Rules for the user

- Keep the working directory clean during a session. `dwch verify`
  commits with `git add -A`, so any scratch file left in the tree
  is included in the step's commit. Put scratch files in `steps/`
  (self-ignored) or outside the repository.
- Do not edit `.harness/state.toml` by hand while a session is
  open. `verify`, `close`, `new-phase`, and `rollback` write it.

## What the report contains

Every report has the same sections: apply log, verify commands with
full output and exit codes, commit hash, notes, question. The
`notes` and `question` fields are the user's; the AI may read them
but does not write them.

## Ending the session

When a phase is complete, the user runs `dwch close`. The AI should
signal this clearly: "Phase X is complete. Run `dwch close`." The
next chat opens with a fresh bootstrap for the next phase.
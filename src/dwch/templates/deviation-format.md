# Deviation format

Deviations are how a coder session reports that it departed from
the roadmap. They live in `.harness/deviations/`.

Two files can exist per step:

- `step-NN.toml` — declared by the coder.
- `step-NN-auto.toml` — written by `verify` when it detects a
  file-set mismatch.

Both use the same schema:

```toml
[[deviation]]
type = "assumption"
affected = ["src/todo/models.py"]
reason = "Roadmap didn't specify Task.priority; omitted it."
detail = ""
auto = false
```

## Types

| Type | Meaning |
|---|---|
| `extra-file` | File written, not listed in `step.files`. |
| `missing-file` | File in `step.files`, not written. |
| `extra-removal` | File removed, not in `step.removes` or `step.moves.from`. |
| `missing-removal` | File in `step.removes` or `step.moves.from`, not removed. |
| `extra-move` | A `MOVE` op that is not in `step.moves`, or whose `to` differs. |
| `missing-move` | A pair in `step.moves` with no corresponding `MOVE` op. |
| `interface-change` | Public symbol added, removed, or renamed. |
| `bugfix-prior` | Change to code from a previous step. |
| `assumption` | Spec was incomplete; the coder decided. |
| `plan-correction` | Step spec was wrong, but workable. |
| `blocker` | Step is impossible as specified. |

The first six are normally written by `verify` as
`step-NN-auto.toml`. The last five are declared by the coder.

## When to write

- **Bugs in the current step's code** — just fix them. No
  deviation needed.
- **Bugs in a prior step's code** — fix them, include the
  affected files in the current step, write a `bugfix-prior`
  deviation.
- **Incomplete spec** — decide, write an `assumption` deviation.
- **Impossible step** — write a `blocker` deviation and send **no
  substantive files**. `roadmap_step` will not advance.

## Effects on state

- A step whose only paths are under `.harness/deviations/`,
  `.harness/summaries/`, or `.harness/handoff.md` does not
  advance `roadmap_step`.
- A step that deletes or moves a file outside those prefixes does
  advance it.

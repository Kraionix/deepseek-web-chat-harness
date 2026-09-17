# Report format

`dwch verify NN` produces one report per step. The format is
fixed; every section appears, even when empty.

```
=== Step NN report ===

apply output:
<lines from dwch apply>

verify commands:
$ <command>
<stdout>
[stderr]
<stderr>
exit: <code>

commit:
<hash> <message>

roadmap position: <before> -> <after>

deviations:
- <type> (declared|auto): <affected> — <reason>

notes:
(fill)

question for AI:
(none)
```

Notes:

- `apply output` is a copy of the log written by `dwch apply`.
- Every configured verify command appears, in order.
- `(optional)` after the exit code means `required = false`.
- `commit:` is `not committed` when a required check failed.
- `roadmap position` appears only in a development phase.
- `deviations` lists both declared and auto deviations for the
  step. `(none)` when there are none.
- `notes:` and `question:` are the user's fields; the AI reads but
  does not write them.

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
- `notes:` and `question:` are the user's fields; the AI reads but
  does not write them.

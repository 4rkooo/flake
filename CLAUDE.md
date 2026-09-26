# Working instructions for this repo

- **Follow the build guide as source of truth.** The hackathon build guide (artifact) has near-verbatim reference code for each lane. Before implementing anything in `harness/`, check whether the guide already specifies the exact function names, signatures, and data shapes -- match it rather than inventing an independent design. When in doubt, re-read the relevant section instead of guessing.
- **After every implementation, give a human-friendly summary.** State what changed and *why* -- not a code narration, a plain-English explanation of the decision, in the chat, after the change is made.
- **Surface ambiguity, don't silently resolve it.** If a decision has more than one reasonable answer (naming, data shape, which lane owns something, a missing spec detail), ask before picking one -- don't guess and move on.
- **TDD where practical.** For real logic (not stubs), write a failing test first, then implement against it. Stubs for other lanes' not-yet-built modules are exempt -- they exist only so imports don't break.
- **Comment code for a human following along.** Short, non-verbose inline comments on non-obvious logic (why, not what). Not a comment on every line, not paragraph-length docstrings.
- **Keep it coherent.** Match existing naming/style in the file you're editing over introducing a new convention. Prefer the simplest change that satisfies the guide's spec.

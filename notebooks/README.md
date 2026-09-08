# Notebooks

Exploration only. **Nothing here is imported by `src/`.** If a notebook produces
something worth keeping, it moves into the package with types, a docstring and a test;
the notebook then stands as a record of how the idea arrived, not as the
implementation.

Outputs are stripped by `nbstripout` on commit (see `.pre-commit-config.yaml`), so a
notebook cannot smuggle a data sample, an absolute path or a credential into git
through its cell outputs.

## `_reference/` (git-ignored)

Holds the instructor's reference notebook from the author's LLM-engineering course. It
is a **source that was ported**, not an artefact of this project: it carries the
instructor's absolute paths and `!pip install` cells, and it is not this repository's
to redistribute. The port is recorded cell by cell in `docs/COURSE_PORT.md`, and the
resulting implementation lives in `src/faultline/data/text/`.

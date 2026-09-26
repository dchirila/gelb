# Contributing to GeLB

Thanks for your interest in GeLB. This page covers the day-to-day
mechanics of working on the compiler; the
[Language Tutorial](https://gelb-lang.org/tutorial)
covers the language itself.

## Setting up

- `./scripts/gelb_bootstrap.sh` (Linux, macOS) or
  `scripts\gelb_bootstrap.ps1` (Windows) creates the `uv` virtual
  environment and installs the package with its `dev`, `docs`, and
  `gui` extras. Equivalent by hand: `uv sync --all-extras`.
- Run Python commands through `uv run` (`uv run gelbc ...`,
  `uv run pytest`) or activate `.venv` first.
- Running the generated programs needs a host compiler and NetCDF:
  `g++` with OpenMP for `cpu_highway` (the default backend), `gfortran`
  plus NetCDF-Fortran for `cpu_fortran_serial`, and `nvcc` for
  `gpu_cuda_cpp`. The README's *Prerequisites* section lists the
  packages per platform. `scripts/gelb-run` compiles and runs a
  `.gelb` program in one step.

## Workflow

- Branch from `main` for anything beyond a one-line fix and open a pull
  request against `main`.
- Keep each commit to one concern. Write the message body in the
  imperative and say *why*, not only what changed.
- Make commit messages understandable on their own: describe the
  affected behavior and the rationale.
- Do not commit build output. The exception is
  `gelb/antlr_part/generated_code/`: the ANTLR-generated Python modules
  are tracked so that the package installs without a JDK, and they must
  be regenerated in the same commit as any grammar change.

## Changing the grammar

- Edit `gelb/antlr_part/grammars/GeLB.g4`, then run
  `./scripts/regenerate_antlr.sh` (or `regenerate_antlr.ps1`). Do not
  invoke ANTLR by hand from inside the grammars directory: it drops a
  `.antlr/` folder there that must never be committed.
- A grammar change usually also touches the AST
  (`gelb/gelb_ast/ASTNodes.py`), the parse-tree visitor, the VS Code
  extension's scanner (`vscode-gelb/`), the examples, and the manual.

## Tests

- `uv run pytest` runs the unit and integration suites. Backend tests
  skip themselves when the matching compiler or NetCDF library is
  missing; `uv run pytest -rs` shows the reasons.
- Backend work must keep the emitted code byte-identical unless the
  change is intentional and explained:
  `uv run python scripts/emission_snapshot.py snapshot -o <dir>` before,
  `... compare -o <dir>` after.
- The examples smoke suite is opt-in and slow:
  `uv run pytest gelb/tests/integration/test_examples_smoke.py --run-smoke`.
- Use the helpers in `gelb/tests/test_utils.py` (`get_typed_ast`,
  `minimal_gelb_program_2d`, the `assert_*_error` functions) instead of
  re-creating them, and prefer `pytest.mark.parametrize` over
  near-duplicate test functions.
- VS Code extension: `cd vscode-gelb && npm test`.

## Documentation

- The manual lives under `docs/` (Sphinx, reStructuredText). Build with
  `uv run sphinx-build -b html -W --keep-going docs docs/_build/html`;
  warnings are errors, as in CI.
- Document the language as it is today. `docs/LANGUAGE_DESIGN.md`
  is the only place for historical notes (it records the design
  decisions and the changes since the original thesis).
- A user-facing syntax change is complete when the grammar, the
  manual, the examples, the VS Code extension, and
  `docs/LANGUAGE_DESIGN.md` all agree.
- Keep code comments, docstrings (including tests), the comments the
  backends write into generated code, and the manual self-contained:
  state the relevant invariant or rationale directly, and refer to
  stable manual sections and named tests rather than to issue threads,
  branch notes or other transient documents.
- Give each rule one authoritative home: current language guarantees
  (the numerical semantics among them) in the user manual, compiler
  mechanisms and invariants in the docstrings of the modules that
  implement them, and the rationale behind the language in
  `docs/LANGUAGE_DESIGN.md`.

## Design principle

*Familiarity without baggage.* Someone arriving from another LBM
framework should recognise the same mental model with less ceremony,
and a newcomer to LBM should not have to learn framework-isms first.
When in doubt, prefer the explicit, simpler construct.

## Reporting problems

Open a GitHub issue with the `.gelb` program (or a reduced version),
the exact command line, the backend, and the compiler and OS versions.
The output of `uv run gelbc prog.gelb --diagnostics-json` is useful for
frontend problems.

## License

Contributions are accepted under the project's MPL-2.0 license.

Contributors and their AI agents can check a clone before starting work with
`uv run --script scripts/doctor.py`: it says whether the branch is behind Trayi's `main` (in a
fork too), and whether uv, the git name and email, the dependencies, the pre-commit hooks and the
database's migrations are set up, each problem with its fix
([#366](https://github.com/dipbazz/trayi/issues/366)).

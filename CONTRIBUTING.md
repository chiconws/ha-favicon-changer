# Contributing to Favicon Changer

Thanks for helping. The tooling mirrors Home Assistant core, so if you have contributed there, this will feel familiar.

## Setup

```bash
uv venv --python 3.14 .venv
uv pip install -r requirements_test.txt
.venv/bin/prek install
```

`prek` is a drop-in for `pre-commit`; `pre-commit install` works too. The hook runs ruff (lint and format), codespell, yamllint, prettier, zizmor, markdownlint, mypy and Pyright on every commit.

## Checks

```bash
.venv/bin/prek run --all-files
.venv/bin/pytest
```

CI runs the same hooks plus the tests with branch coverage; coverage must not drop below the floor in `pyproject.toml`.

## Pull requests

- Branch from `dev` and open the PR against `dev` (`main` only receives releases).
- One topic per PR; use conventional commit titles (`feat:`, `fix:`, `chore:`, `docs:`).
- User-facing text goes through `strings.json` and `translations/` (English and Brazilian Portuguese).
- Code structure and conventions are in [AGENTS.md](AGENTS.md).

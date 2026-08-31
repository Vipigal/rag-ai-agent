# Decision Records

Architecture and project decisions, one concept per decision, numbered
sequentially. See the [Authoring Guide](/docs/authoring-guide.md) for the
format. Superseded decisions are deprecated, never deleted.

- [0003 — Toolchain: plain pip + venv, Python 3.14, docker-first](0003-toolchain-plain-pip-docker-first.md) - The project uses classic pip with a pinned requirements.txt inside a venv (no uv/poetry), Python 3.14 provided by pyenv on the host, and Docker Compose as the official way evaluators run the system.
- [0002 — Module documentation is co-located with module code](0002-colocate-docs-with-code.md) - The bundle is re-rooted at the repo root so each module's OKF concepts live in the directory that defines the module; docs/ keeps only cross-cutting knowledge.
- [0001 — Documentation lives in an OKF bundle at docs/](0001-okf-bundle-at-docs.md) - _Deprecated, superseded by 0002._ OKF v0.2 is the official documentation format, rooted at docs/ rather than the repo root.

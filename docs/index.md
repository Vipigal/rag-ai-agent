# Cross-Cutting Knowledge

Project-wide concepts that belong to no single module. Module-specific
knowledge is co-located with the module's code (see the
[Authoring Guide](authoring-guide.md)).

- [Challenge Brief](challenge.md) - What the system must do: the case, required features, API contract, and deliverables.
- [Golden Rules](golden-rules.md) - The challenge's evaluation criteria, adopted as the non-negotiable priorities of every change in this repo.
- [Development Workflow](development-workflow.md) - Testing-first and eval-first: how modules get built (TDD) and how system accuracy gets measured (evals).
- [Authoring Guide](authoring-guide.md) - How to add knowledge to this bundle: co-location with code, what deserves documentation, and the OKF conventions.
- [System Architecture — Ports & Adapters Lite](architecture.md) - The operating map of the codebase — the hexagonal-lite structure, the concepts behind it (ports, adapters, domain services, composition root), the rules every implementation must follow, and how to extend the system.

# Decisions

- [Decisions](decisions/) - Architecture and project decisions, one concept per decision, numbered chronologically.

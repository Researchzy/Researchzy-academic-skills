---
name: researchzy-data-availability
description: "Draft or audit manuscript Data/Code Availability statements, dataset access routes, repository plans, and FAIR metadata. Use for Data Availability statements, data sharing, repository choice and dataset citations; not general data cleaning or statistical analysis."
metadata:
  author: Yuan1z skill, refactored into static/dynamic layers
---

# Researchzy Data Availability — Router

<!-- Modified by Researchzy; the changes are listed in THIRD_PARTY_NOTICES.md. -->

## Routing protocol

For a new task, load the core and matching resources below. Reuse already loaded guidance on follow-ups; load more only when the task needs it.

### 1. Load the manifest and the core layer

Read [manifest.yaml](manifest.yaml). Then read every file listed under `always_load`:

- `static/core/stance.md` — what the data-availability package is, the default stance, and the source hierarchy.
- `static/core/workflow.md` — the eight-step workflow and the output format.

### 2. No content axis — confirm journal and language inline

This skill has no fragment axis. Its variation is handled at runtime, not by loading different content bodies:

- **journal/article type** — if journal-specific instructions conflict with this skill, follow the journal.
- **access route** — each dataset is classified into one route (public repository, controlled access, within paper, reused public, third-party restricted, justified request, or not applicable).
- **user language** — accept author notes in any language. Draft the submission-ready statement in English unless the user explicitly asks otherwise; when the user writes in another language, explain the unresolved fields in that language. Translate intent, not wording: a vague request-only note still needs a restriction reason and an access route.

### 3. Run the workflow

For a wording edit or audit of one existing statement, preserve supplied repository identifiers
and access conditions and check the affected claims. Report gaps relevant to that statement;
do not require a full study-wide dataset inventory or repository redesign. Use the complete
workflow below for a new data-sharing plan, full statement, or submission audit.

Follow the eight-step workflow in `static/core/workflow.md`: identify the journal, inventory every supporting dataset, classify each into one access route, choose repository and identifier strategy before drafting, draft the statement with explicit dataset-to-location mapping, add formal dataset citations, run the FAIR/metadata audit, and return ready-to-paste text plus unresolved fields.

Do not invent DOIs, accession numbers, repository names, licences, embargo dates, ethics approvals, access committees, or data-use conditions. Flag "available upon request" as weak unless there is a specific legal, ethical, commercial, or third-party restriction.

### 4. Reach for references only when needed

The files under `references/` are deep references, not defaults. Open them on demand per the `references.on_demand` table in the manifest — for example `references/policy-principles.md` for the governing rules and edge cases, `references/repository-and-identifiers.md` for repository/accession/DOI choices, `references/statement-patterns.md` for ready-to-adapt statements, `references/fair-metadata-checklist.md` for the FAIR audit, and `references/source-basis.md` to justify a rule with its official source.

When the target is the flagship journal Nature, also open
`references/nature-article-requirements.md` for statement placement,
mandatory-deposition routing, central-code review access, materials and
structure-file checks.

When the target is Nature Machine Intelligence, open
`shared/journal-formats/nature-machine-intelligence.md`. Enforce a
Data Availability statement and a separate `Code availability` section after
it and before references; check reviewer access, precise restrictions,
repository/identifier quality and the Software Submission Checklist for newly
developed central code.

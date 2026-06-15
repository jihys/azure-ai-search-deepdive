# Issue Tracker: Local Markdown

This repo uses local markdown work artifacts under `.scratch/` instead of a hosted issue tracker.

## Structure

- PRDs: `.scratch/prds/<prd-slug>.md`
- Implementation issues: `.scratch/issues/<feature-slug>/<NN>-<issue-slug>.md`, numbered from `01`
- Rejected or deferred items: `.scratch/out-of-scope/<slug>.md`

Keep PRDs and implementation issues separate. A PRD may describe the full product or feature decision; implementation issues must be independently grabbable vertical slices.

## Artifact Metadata

Each PRD or issue file should include these lines near the top when applicable:

```markdown
Status: ready-for-agent
Parent: .scratch/prds/<prd-slug>.md
```

Use the status strings from `docs/agents/triage-labels.md`. For implementation issues, `Parent:` points to the source PRD or parent issue.

## Publishing Rules

When a skill says "publish to the issue tracker":

- `to-prd` creates or updates one PRD file under `.scratch/prds/`.
- `to-issues` creates implementation issue files under `.scratch/issues/<feature-slug>/` in dependency order.
- Out-of-scope, rejected, or deferred work goes under `.scratch/out-of-scope/` only when it needs a durable record.

For spec-to-implementation work, implementation must not start from a PRD alone. The required flow is `to-prd` publish -> `to-issues` publish -> execute a ready implementation issue.

When a skill says "fetch the relevant ticket," read the referenced markdown file path. If the user provides only a feature or issue slug, search the `.scratch/prds/` and `.scratch/issues/` trees.

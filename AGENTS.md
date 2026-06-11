# AGENTS.md

## Task mode detection

Before making changes, classify the task automatically.

Use the smallest sufficient mode.

Default to QUICK FIX unless the user clearly requests a larger task.

If the user explicitly names a mode, follow the user's mode.

Mode selection rules:

1. Use QUICK FIX if the task is a small local change:
   - text edit;
   - small CSS/layout fix;
   - small bugfix;
   - one component/page change;
   - no API/architecture change;
   - expected diff is small.

2. Use NORMAL TASK if the task requires:
   - several related files;
   - new behavior in an existing feature;
   - non-trivial bug investigation;
   - frontend + backend coordination;
   - API usage but no contract redesign.

3. Use DESIGN TASK only if the task clearly asks for:
   - new design;
   - redesign;
   - visual concept;
   - UI system;
   - new screen layout;
   - design references;
   - gpt-taste/lazyweb.

4. Use RELEASE TASK only if the user clearly asks for:
   - final check;
   - release preparation;
   - deploy/pre-deploy check;
   - full audit;
   - full project verification.

Do not upgrade the mode just because a tool exists.

Do not use DESIGN TASK for small CSS fixes unless the user asks for redesign or visual exploration.

Do not use RELEASE TASK for ordinary coding tasks.

At the start of the response, state the selected mode in one short line, then proceed.

## Main instruction

Before starting any task, read:

- `vault/01_Rules/AI_RULES.md`

Use the task modes from `AI_RULES.md`:

- QUICK FIX
- NORMAL TASK
- DESIGN TASK
- RELEASE TASK

Do not read the whole vault by default.

---

## Default behavior

For small local fixes, use QUICK FIX mode.

In QUICK FIX mode:

- do not use lazyweb;
- do not use gpt-taste;
- do not read the whole vault;
- do not read `CHECKLIST_RELEASE.md`;
- do not update `CHANGELOG_AI.md`;
- do not update `API_MAP.md`;
- do not update `GLOSSARY.md`;
- make the smallest safe diff.

---

## Design tools

Use gpt-taste only for DESIGN TASK.

Use lazyweb only when:

- the task is about a new design;
- the task is about redesign;
- the task requires visual references;
- the user explicitly asks for references.

Do not use lazyweb or gpt-taste for:

- backend tasks;
- API tasks;
- small bugfixes;
- text edits;
- local CSS fixes;
- small changes to an existing component.

---

## Release checklist

Read `vault/01_Rules/CHECKLIST_RELEASE.md` only for RELEASE TASK.

RELEASE TASK means the user explicitly asks for:

- final check;
- release preparation;
- deployment check;
- full project audit;
- full pre-deploy verification.

Do not run the release checklist for ordinary coding tasks.

---

## Scope control

Work only inside the requested scope.

Do not refactor unrelated files.

If a required fix needs changes outside the requested scope, explain why before making those changes.

Before finishing, report:

- changed files;
- what was changed;
- what was checked.
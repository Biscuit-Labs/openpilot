# Branch workflow

This repo (`RiskyBiscuit-arc/openpilot`) is the shared codebase for the Honda CR-V PTM work.
Collaborators push here directly. Nobody works from a separate fork.

## Branches

```
Honda-PTM-Stable   <-  Honda-PTM-Stage   <-  Honda-PTM-Testing   <-  feature / fix branches
  (default)            (release candidate)    (integration)            (one per change)
```

| Branch | What it is | Who changes it |
| --- | --- | --- |
| `Honda-PTM-Stable` | The default branch and the build you install for normal driving. It started as an exact copy of VFN's (JamesL787) `night-star7` at `c81a86eb` (2026-10-28). | Only by promoting Stage. |
| `Honda-PTM-Stage` | The release candidate. It holds what is about to become Stable, while it gets driven. | Only by promoting Testing. |
| `Honda-PTM-Testing` | The integration branch. Finished feature and fix branches merge here first. | Pull requests from feature and fix branches. |
| feature / fix branches | One change each, branched off Testing. | Anyone. |

## Making a change

1. Branch off the latest `Honda-PTM-Testing`.
2. Commit, push, and open a pull request **into `Honda-PTM-Testing`**.
3. Merge after review and once CI is green.

Never open a pull request straight into Stage or Stable.

## Promoting

Changes move in one direction only: Testing → Stage → Stable.

- **Testing → Stage:** open a pull request from `Honda-PTM-Testing` into `Honda-PTM-Stage` when Testing has a set of changes worth driving.
- **Stage → Stable:** open a pull request from `Honda-PTM-Stage` into `Honda-PTM-Stable` once Stage has been driven and nothing new is wrong.

A fix found on Stage goes through the same path: branch off Testing, merge into Testing, then promote it again.

## Naming

- Name a branch after the work, in lowercase with hyphens, for example `wifi-power-save` or `jetlink-0.8.10-update`.
- Don't use tool or agent prefixes such as `claude/`.
- Only the three long-lived branches above use the `Honda-PTM-` prefix.

## Bringing in upstream (VFN `night-star7`)

Upstream changes come in like any other change. Merge `night-star7` into a branch off Testing, open a pull request into Testing, and then promote it as usual.

## Device builds

`night-star7` ships a `prebuilt` marker and committed binaries, so the comma does not compile on install. A Python-only change needs no rebuild. A change to native code needs the binaries rebuilt and committed in the same pull request.

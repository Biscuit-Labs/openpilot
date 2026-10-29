# Branch workflow

This repo (`RiskyBiscuit-arc/openpilot`) is the shared openpilot codebase for Honda EPS torque modding. It is not specific to one model: it covers any Honda whose power steering is torque-modded.
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

## Rules and guardrails

GitHub enforces most of this workflow, so a mistake fails a check instead of reaching a car.

**Rulesets** (`.github/rulesets/`, imported by a repo admin under Settings → Rules → Rulesets → Import):

- `honda-ptm-branches.json` covers Stable, Stage, Testing and Clean:
  - no deleting the branch and no force-push;
  - changes arrive only by pull request, with merge commits only (no squash, no rebase, so upstream merges keep their history);
  - one approval from someone other than the last person to push, and new pushes dismiss earlier approvals;
  - every review thread resolved;
  - the required checks pass. The branch does not have to be up to date with its base: promotions use merge commits, so Stage and Stable always hold a merge commit that Testing lacks, and Testing cannot take it back. Push CI on each long-lived branch tests the merged result.
- `branch-names.json` refuses to create branches under `claude/`, `codex/`, `copilot/`, `cursor/` or `gemini/`.

**branch guard** (`.github/workflows/branch_guard.yaml`, `tools/ci/branch_guard.py`) is a required check. Rulesets cannot say where a pull request comes from, so this check does:

| Into | Only from |
| --- | --- |
| `Honda-PTM-Stable` | `Honda-PTM-Stage` in this repo |
| `Honda-PTM-Stage` | `Honda-PTM-Testing` in this repo |
| `Honda-PTM-Testing` | a feature or fix branch: not Stage, Stable or Clean, and no tool prefix |
| `Honda-PTM-Clean` | anything that leaves Clean equal to Stable plus exactly the clean changes (`tools/night_star_port/check_clean_branch.py`) |

The guard also runs on every push to Clean.

**Required checks** are the CI jobs that pass today. `process replay` and `complete custom pytest catalog` join the list once issue #13 is closed; until then a reviewer reads their results by hand.

### Before you ask for review

- Refresh the device build receipt in the same pull request: `python3 openpilot/common/prebuilt_manifest.py .`. If native code changed, rebuild the binaries in Docker first. Source integrity fails without it.
- Say in the description what the change does on the car and how it was checked: static, replay or road.

### Reviewing

- Read the diff, not only the checks.
- A new process replay reference (`refs/starpilot/manifest.json`) needs a written contract, and the reviewer has to agree with that contract.
- Some changes make a check less strict, such as driver monitoring, panda safety or steering limits. The author must name that in the description. The reviewer has to confirm it is intended before approving.
- No approving your own promotion: the person who opens a Testing → Stage or Stage → Stable pull request does not approve it.

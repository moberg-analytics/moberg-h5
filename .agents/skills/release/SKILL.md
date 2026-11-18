---
name: release
description: Cut a moberg-h5 release to PyPI. Use when asked to release, publish, tag, or bump the version of moberg-h5, or to follow up on a release run waiting for approval.
---

# Release moberg-h5

A release is a `vX.Y.Z` tag on `main`. Pushing the tag starts
`.github/workflows/release.yml`, which checks the tag, tests, builds, then waits
on the `pypi` environment. Tony approves that deployment in the browser; PyPI
accepts the upload through Trusted Publishing, and the workflow then creates
the GitHub release from the same files.

You prepare the release and hand Tony the approval link. Approval is his.
Leave the deployment-review API (`.../pending_deployments`) alone, even when
`gh` has admin rights on the repo.

Run every command against `moberg-analytics/moberg-h5`, in a checkout whose
`origin` is that repo.

## 1. Preflight

Done when all of these hold:

- `git fetch origin --tags` succeeded and you are working from `origin/main`.
- The latest CI run on `main` is for the current `origin/main` commit and
  passed: `gh run list -R moberg-analytics/moberg-h5 --workflow ci.yml --branch main --limit 1 --json headSha,conclusion,url`.
  A run for an older commit does not count.
- You know the last release: `git tag -l 'v*' --sort=-v:refname | head -1`
  (none before the first release).

## 2. Choose the version

Read `CHANGELOG.md` `## Unreleased` and `git log <last tag>..origin/main`.

- If `uv version --short` has no matching tag yet (the first release, or a
  bump already merged), release that version as it stands.
- Otherwise bump. While the version is `0.x`, a change that breaks callers is
  a minor bump and everything else is a patch.

Tony confirms the version before you open the PR.

## 3. Release PR

On a branch `release/vX.Y.Z` from `origin/main`:

1. `uv version X.Y.Z` when bumping. It rewrites `pyproject.toml` and relocks
   `uv.lock`. In `git diff uv.lock`, moberg-h5's `version` is the only package
   version that changes; lock-format and marker rewrites from a newer uv are
   fine.
2. In `CHANGELOG.md`, rename `## Unreleased` to `## X.Y.Z - YYYY-MM-DD` and
   start a fresh empty `## Unreleased` above it. The workflow publishes the
   `## X.Y.Z` section as the release notes and refuses a tag without one.
3. If `src/moberg_h5/` or `docs/hdf5-format.md` changed which files the reader
   accepts or how it reads them (`SUPPORTED_MAJOR`, layout handling), check
   that `docs/format-changelog.md` covers it and ask Tony if it does not.
4. `uv run --locked pytest` passes.
5. Open the PR titled `Release vX.Y.Z` and give Tony its URL.

Done when the PR is merged into `main`.

## 4. Tag

```sh
git fetch origin
sha=$(git rev-parse origin/main)
git tag -a vX.Y.Z "$sha" -m "moberg-h5 X.Y.Z"
git push origin vX.Y.Z
```

`origin/main` must be the merge commit of the release PR. Check
`git show "$sha":pyproject.toml` reports `X.Y.Z` before pushing. A pushed tag is
the release trigger, so get Tony's go-ahead if anything else landed on `main`
after the PR merged.

## 5. Hand over the approval

Find the run for this tag and commit:

```sh
gh run list -R moberg-analytics/moberg-h5 --workflow release.yml --commit "$sha" \
  --json databaseId,headBranch,status,url \
  --jq '.[] | select(.headBranch == "vX.Y.Z")'
```

Keep its `databaseId` and follow that run. When the `Build and check` job
passes, the run status becomes `waiting`. Send Tony the run `url`; the
**Review deployments** button on that page approves `pypi`.

If `Build and check` fails, report the failing step from
`gh run view <id> --log-failed`. Fix forward with a new patch version. A
failed tag stays as a record and is never moved or reused.

## 6. Confirm

After Tony approves, the run finishes `success`. Done when:

- `https://pypi.org/pypi/moberg-h5/X.Y.Z/json` returns 200;
- `uv run --isolated --no-project --refresh-package moberg-h5 --with moberg-h5==X.Y.Z python -c 'import moberg_h5; print(moberg_h5.__version__)'` prints `X.Y.Z`;
- `gh release view vX.Y.Z -R moberg-analytics/moberg-h5` shows the wheel and
  sdist.

PyPI never accepts the same version twice, even after a delete. A broken
release gets yanked on PyPI by Tony and replaced by the next patch version.

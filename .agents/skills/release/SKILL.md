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

- `git fetch origin --tags` succeeded and you are working from `origin/main`
  with a clean worktree.
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

When Tony's request names the version, that is his confirmation. Otherwise
propose one and wait for his answer.

## 3. Release commit

The release commit goes straight onto `main`; Tony's approval of the `pypi`
deployment is the review. On a detached checkout of `origin/main`:

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
5. Commit only those files as `Release vX.Y.Z`.

## 4. Push and tag

Push the commit and the tag in one atomic push over SSH, so `main` never holds
a release commit without its tag:

```sh
git tag -a vX.Y.Z -m "moberg-h5 X.Y.Z"
sha=$(git rev-parse HEAD)
git push --atomic origin HEAD:main vX.Y.Z
```

A rejected push means `main` moved. Delete the local tag, rebase the release
commit onto the new `origin/main`, rerun the tests, and push again. Never force
`main`.

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
- `uv run --no-config --python 3.12 --isolated --no-project --refresh-package moberg-h5 --with moberg-h5==X.Y.Z python -c 'import moberg_h5; print(moberg_h5.__version__)'`
  prints `X.Y.Z`. `--no-config` skips the user config's 2-day `exclude-newer`,
  which hides a version uploaded minutes ago;
- `gh release view vX.Y.Z -R moberg-analytics/moberg-h5` shows the wheel and
  sdist.

PyPI never accepts the same version twice, even after a delete. A broken
release gets yanked on PyPI by Tony and replaced by the next patch version.

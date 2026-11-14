# Maker Career Lab — Phase 1: review-first AI PDCA

## Status on 2026-11-14

The owner confirmed: EDINET v3.26 monthly workflow is **Disabled**; no GitHub Ruleset exists yet; Cloudflare Workers Builds connects to `cog-vja/maker-career-lab`; production branch is `main`; build is `python3 cloudflare-build.py`; deploy is `npx wrangler deploy`; root directory is `/`.

This package is intended for **a new branch**, then a pull request. NEVER upload it directly to `main`.

## Procedure

1. Use branch `automation/pdca-bootstrap-20261114` from the latest `main`.
2. Review the 5 files in a **draft** PR against `main`.
3. Review the PR checks. Existing regressions may reveal failures; do not merge until investigated.
4. When CI passes, create a GitHub Ruleset for `main`: require PR and status check `quality`, prohibit force-pushes and deletion, and ensure the ruleset is Active. A solo owner should start with 0 required approvals, not a self-review requirement.
5. Only after confirming the PR checks and Cloudflare preview are safe, approve and merge personally.

## EDINET updates — leave workflow Disabled for now

The former EDINET v3.26 workflow directly pushed to `main`. The updated workflow now prepares **a review-only PR** with `peter-evans/create-pull-request@v7`, after existing source validation. Its changes are restricted to `company-data.js`; the existing monthly artifact is retained. No PR is created when the verified update count is zero.

Before re-enabling: store a newly scoped GitHub App token or fine-grained PAT with **Contents: Read/Write** and **Pull requests: Read/Write** for only this repository in GitHub Actions secret `MCL_PDCA_PR_TOKEN`. Do not paste secrets into ChatGPT. Without this token the job fails closed after storing evidence. Review and revoke unused legacy `MCL_PAGES_PUBLISH_PAT` after checking other workflows for references.

A PR created by the built-in `GITHUB_TOKEN` may not trigger the separate CI flow, so the dedicated token must be configured and tested before enabling the monthly workflow.

## Reproducible tests

```sh
python3 -m unittest -v test_v325.py test_v326_monthly.py test_pipeline.py
python3 cloudflare-build.py
python3 tests/test_pdca_smoke.py
node --check dist/analytics-events.js
node --check dist/company-data.js
node --check dist/company-compare.js
node --check dist/mcl-editorial.js
```

These tests verify output contracts and offline EDINET regressions, not actual Cloudflare production behavior, ads conversion, browser analytics delivery or live mobile rendering. Validate those manually before claiming full end-to-end coverage.

## Rollback

If a merged change causes defects, revert the merge by PR and test it, then redeploy via the normal `main` branch process. For an urgent production incident, use Cloudflare's available rollback controls and reconcile the deployed version with Git afterward.

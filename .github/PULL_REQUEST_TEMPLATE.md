<!--
Thank you for contributing. Complete each section and tick every box that
applies. A PR that documents its testing and its impact is reviewed far faster
than one that does not. Keep the change as small as it can be while still being
complete — no unrelated churn.
-->

## Summary

<!-- What does this change do, and why? One or two paragraphs. -->

## Related issues

<!-- e.g. "Closes #123", "Refs #456". If there is no issue, say why. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes a defect)
- [ ] New feature (non-breaking change that adds capability)
- [ ] Breaking change (alters existing behavior, defaults, or interfaces)
- [ ] Documentation only
- [ ] Tooling, packaging, or CI
- [ ] Refactor (no functional change)

## What changed

<!-- Bullet the concrete changes: modules touched, new functions, new options. -->

## Testing evidence

<!--
Describe how you proved this works. For a bug fix, a regression test that FAILS
without the change and PASSES with it is expected. Paste the relevant test run.
-->

- [ ] `python3 -m pytest tests/` passes locally.
- [ ] New or changed behavior is covered by tests.
- [ ] For a bug fix: a regression test was added that fails without this change.
- [ ] `ruff check src/` is clean (no new findings).

```
# paste the relevant pytest / ruff output here
```

## Documentation

- [ ] User-facing docs updated to describe the new behavior as present-tense fact
      (no "new in vX" phrasing outside the changelog).
- [ ] `docs/DEVELOPER_GUIDE.md` updated for new or changed functions, with line
      annotations regenerated (`python3 tasks/resync_devguide_lines.py`).
- [ ] Wiki pages under `docs/wiki/` updated where they mirror the change.
- [ ] A changelog entry was added to both `docs/CHANGELOG.md` and
      `docs/wiki/Changelog.md`; existing historical entries were not edited.

## Security and safety

- [ ] No secrets, credentials, or private keys are committed.
- [ ] Untrusted input is validated at the trust boundary; no `shell=True`, `eval`,
      or `exec` on external data.
- [ ] The change does not weaken process isolation, file permissions, or the
      protocol-scoping of session operations.

## Quality gates

- [ ] No stubs, placeholders, or commented-out dead code.
- [ ] Existing functionality is preserved (nothing truncated or removed without cause).
- [ ] New scripts and modules carry the standard header (Synopsis, Description,
      Notes, Version) and are annotated.
- [ ] Author notation, where present, uses `Sandler73` or
      `Socat Network Operations Manager Contributors` — not a personal name.

## Additional notes

<!-- Anything reviewers should know: trade-offs, follow-ups, out-of-scope items. -->

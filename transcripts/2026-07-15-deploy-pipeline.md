---
date: 2026-07-15
title: Deploy pipeline discussion
tags: deploy, infra
---
User: What's the current deploy checklist before pushing to prod?
Claude: Run the test suite, check the staging smoke tests, then tag the release.
User: Should we automate the smoke tests?
Claude: Yes — flaky manual smoke tests were the main cause of the last rollback.

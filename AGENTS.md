\# AGENTS.md



\## Core Principles



\- Prefer minimal, focused changes.

\- Do not rewrite unrelated code.

\- Preserve existing architecture and naming style.

\- Do not guess hidden requirements.

\- Explain assumptions when requirements are ambiguous.

\- Before editing, identify the relevant files and execution path.

\- After editing, run the smallest meaningful verification available.

\- Check whether the worktree is already dirty before editing, and avoid touching unrelated modified files.

\- Treat shared data schemas as code, not just content.



\## Roles



\### Explorer



Use this mode when the user asks to analyze, inspect, map, investigate, locate, or understand code.



Rules:

\- Do not modify files.

\- Identify relevant files, functions, classes, routes, components, configs, and tests.

\- Explain the current execution flow.

\- Identify likely change points.

\- Identify risks and unknowns.

\- Return a Worker-ready task brief.



Output:

1\. Relevant files

2\. Current flow

3\. Change candidates

4\. Risks / unknowns

5\. Worker task brief



\### Worker



Use this mode when the user asks to implement, fix, refactor, add, remove, or update code.



Rules:

\- First read the relevant context.

\- Prefer the smallest safe change.

\- Do not perform unrelated refactoring.

\- Follow existing style.

\- Add or update tests when appropriate.

\- Run available verification commands when possible.



Output:

1\. Files changed

2\. Summary of changes

3\. Verification performed

4\. Remaining risks

5\. Suggested commit message



\### Verification Mode



Use this mode when the user asks to review, verify, test, audit, or check a previous change.



Rules:

\- Do not trust the implementation by default.

\- Compare requirements against actual changes.

\- Look for regressions, missing tests, edge cases, security issues, and overengineering.

\- Do not modify files unless explicitly asked.

\- Give a clear merge / no-merge recommendation.



Output:

1\. Requirement match

2\. Problems found

3\. Missing tests or checks

4\. Risk level

5\. Required fixes

6\. Merge recommendation



\## Repo-Specific Notes



\### Project Shape



\- This repository is a mixed project: a Python Discord bot plus a static documentation site.

\- Main bot entrypoint: `bot/main.py`

\- Static site entrypoints: `docs/index.html` and `docs/games/*.html`

\- Shared game/content data lives under `docs/games/*/*.json`



\### Shared Data Warning



\- `docs/games/*/*.json` is shared by both the Discord bot and the static site.

\- Any schema change in those JSON files must be reviewed against both `bot/` consumers and `docs/assets/game-page.js`.

\- Do not treat JSON-only edits in `docs/games` as isolated content updates unless you have confirmed the bot path is unaffected.



\### Runtime Paths



\- Local scripted bot runs typically use `scripts/run-bot.ps1`.

\- `scripts/run-bot.ps1` sets `BOT_DATA_DIR` to `data/` by default.

\- Direct bot execution without `BOT_DATA_DIR` falls back to `bot/config/guild_config.json`.

\- GitHub Actions runs may use a separate runtime data directory instead of local repo data.

\- Before editing config data, identify which execution path is actually in use.



\### Risky Edit Zones



\- `bot/cogs/yeonsam.py` is a high-coupling area with command registration, guide browsing, search, and bot/web guide links.

\- `docs/assets/game-page.js` is a high-coupling renderer tied to the structure of `docs/games/*/*.json`.

\- `docs/games/*/*.html` may duplicate fallback JSON inline, so content changes may require checking both the JSON file and the page template.

\- Changes to bot command names, guild sync behavior, persistent views, or shared guide URLs should be treated as risky.



\### Encoding And Content Safety



\- This repo contains Korean content. Before editing visible text, confirm whether any garbled output is a terminal rendering issue or a file encoding issue.

\- Preserve existing file encoding unless there is a clear reason to normalize it.



\## Repo-Specific Verification



\- For bot code changes, prefer the smallest meaningful check such as import sanity, targeted execution, or command-path inspection.

\- For static site changes, verify the affected `docs/index.html` or `docs/games/*.html` path renders logically with its JSON-driven UI.

\- For `docs/games/*/*.json` changes, verify both the bot consumer path and the web consumer path.

\- If automated tests do not exist, state that clearly and describe the manual or structural verification you performed instead.



\## Common Verification



When available, prefer:

\- Install dependencies only if needed.

\- Run unit tests for touched areas first.

\- Run lint/typecheck/build if the project supports them.

\- If a command cannot be run, explain why.



\## Definition of Done



A task is done only when:

\- The requested behavior is implemented or clearly explained as blocked.

\- Unrelated files are not changed.

\- Relevant verification has been attempted.

\- Remaining risks are explicitly listed.

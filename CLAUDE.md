# Claude Code Instructions for simple_bot

## Git Push Workflow

Start every session by cutting the working branch from a freshly fetched `main`:
`git fetch origin main && git checkout -B <branch> origin/main`. Reuse an
existing branch only while its PR is still open — once merged, that branch is
dead, so start a new one.

Before pushing to the feature branch:
1. Re-read `VERSION` from the refreshed `main`, not from whatever the branch
   started at — a stale base leads to bumping to a version `main` already used
2. Ask the user whether to bump the version (patch/minor/major/skip)
3. If not skipping, update the `VERSION` file, commit it, then push

After every `git push` to the feature branch, automatically:
1. Create a pull request from the pushed branch into `main` using `mcp__github__create_pull_request`
2. Immediately squash-merge it using `mcp__github__merge_pull_request` with `merge_method: "squash"`

Repository: `jzxky/simple_bot`

## Project Rules

- No async — synchronous Python with threading only
- Credentials (email/password) MUST NEVER be stored in config.json — always in `.env` file
- `.env`, `config.json`, `.browser_profile/` must always be in `.gitignore` and never committed
- Use patchright (not playwright), with `channel="chrome"` and patchright's built-in launcher
- Bot runs headed (headless=False) — machines always have a display
- No mobile user-agent globally — use mobile UA only for agcrime.asp pages via `set_extra_http_headers`
- Community service always picks the last option (highest tier) automatically

# deploy/ — running operator-core-mini against a real vault

`operator-core-mini` is the *substrate*: schemas, renderers, the console,
Carry, the TTL daemon. **Your data does not live here.** Your data lives
in a separate repo — call it `operator-vault` — that is shaped like an
operator-root and is private.

This folder has the templates and runbook for setting that vault up so:

1. The vault repo is just plain markdown + JSON (git is your sync layer).
2. A nightly GitHub Action runs `tools/expire.py` against it.
3. A morning GitHub Action commits today's renders to the vault root for
   phone-friendly browsing.

```
deploy/
├── README.md                            <— you are here
├── operator-vault-template/             <— files copied into a new vault
│   ├── .github/workflows/
│   │   ├── expire.yml                   nightly TTL daemon
│   │   └── today.yml                    morning render commits
│   ├── .gitignore
│   └── README.md                        what a vault README looks like
└── (no code; tools/bootstrap_vault.py is the mover)
```

---

## Step 0 — sanity check

These steps assume you are `snackdriven` on github.com and that you
already have operator-core-mini cloned locally. Adjust paths to taste.

```bash
cd /path/to/operator-core-mini
git status        # should be clean / on main
python tools/validate.py    # should print ALL PASSED twice
```

## Step 1 — create the vault repo on github.com

Make a **private** repo. The simplest path:

```bash
gh repo create snackdriven/operator-vault --private --confirm
```

Or use the website: New repository → name `operator-vault` → private →
Create. **Don't** check "Initialize with README"; we want it empty.

> Why private: backpack + journal + life-state items are personal. Hoard
> in particular is write-once, so anything ever in your bag stays in the
> hoard branch forever. Treat it like email, not a portfolio.

## Step 2 — bootstrap the local layout

```bash
mkdir ~/code/operator-vault
cd ~/code/operator-vault
python /path/to/operator-core-mini/tools/bootstrap_vault.py . \
    --name "Kayla" \
    --summary "QA at Tebra/NHHA. Bentonville, AR."
```

This creates `backpack/`, `doctrine/`, `hoard/`, `policy/freshness.json`,
`.github/workflows/{expire,today}.yml`, `.gitignore`, and a `README.md`.

Review `doctrine/` and hand-edit anything obviously wrong before the first
commit. The 9 seeds are working defaults but they don't know you yet.

## Step 3 — first commit, push to GitHub

```bash
git init
git add -A
git commit -m "initial vault — bootstrapped from operator-core-mini"
git branch -M main
git remote add origin https://github.com/snackdriven/operator-vault.git
git push -u origin main
```

## Step 4 — confirm Actions are enabled

On github.com → your vault repo → **Settings → Actions → General**:

- **Allow all actions and reusable workflows** (or "Allow actions and
  reusable workflows from owners" + add `snackdriven/*`).
- Under **Workflow permissions**: pick **Read and write permissions** so
  the workflow can push commits back to the vault.

You shouldn't need a PAT — the default `GITHUB_TOKEN` is enough for
self-checkout + self-push.

## Step 5 — fire the workflows manually for the first run

```bash
gh workflow run expire.yml --repo snackdriven/operator-vault
gh workflow run today.yml  --repo snackdriven/operator-vault
gh run list --repo snackdriven/operator-vault
```

Or click **Actions → expire / today → Run workflow** in the website.

After the runs complete, `git pull` and you should see (a) any
expired items moved into `hoard/YYYY/MM/DD/`, (b) `today.md`,
`today.narrator-prompt.md`, and `today.statusline.txt` at the vault root.

## Step 6 — done

The schedule will fire automatically from now on:

- **23:55 UTC** — `expire` sweeps the bag.
- **12:30 UTC** — `today` writes the morning brief.

Edit either workflow's `cron:` to match your timezone. Cron strings are
UTC; `7:30 CDT` is `30 12 * * *`.

---

## Daily loop

```bash
# morning — pull today's renders
git pull
cat today.statusline.txt
glow today.md         # or just open in any markdown viewer

# during the day — capture / triage via Carry
python /path/to/operator-core-mini/console/server.py .
# open http://127.0.0.1:8765/carry

# evening — push the day's edits
git add -A && git commit -m "evening" && git push
```

The two Actions handle overnight cleanup. You don't need to remember to
run anything locally for the daemon.

---

## What this *doesn't* set up (yet)

### GitHub Pages publishing

GitHub Pages on a free-plan **private** repo is gated behind GitHub Pro /
Enterprise. Three options:

1. **Stay private, browse via repo UI.** What `today.yml` does today.
   `today.md` renders as nice markdown in the GitHub web UI on any
   device. Free, zero setup beyond the workflow you already have.
2. **Separate public `today` repo.** Create a public
   `snackdriven/today` repo. Add a deploy key (read+write) to it, store
   the SSH key as a vault secret, and add a step to `today.yml` that
   pushes the rendered HTML/markdown there. That repo enables Pages.
   The vault stays private; only the rendered surface is public.
3. **Pay for Pro.** Then enable Pages on the vault directly with
   `peaceiris/actions-gh-pages@v4`.

If you want option (2), the additional workflow snippet looks like:

```yaml
      - name: Push to public today repo
        run: |
          mkdir -p /tmp/today
          cp vault/today.md /tmp/today/index.md
          cd /tmp/today
          git init -q
          git add -A
          git -c user.email=weaver@snackdriven.dev -c user.name=weaver \
              commit -q -m "today $(date -u +%Y-%m-%d)"
          git push -f \
              https://x:${{ secrets.TODAY_REPO_TOKEN }}@github.com/snackdriven/today.git \
              HEAD:main
```

`TODAY_REPO_TOKEN` is a fine-grained PAT with `contents:write` on
`snackdriven/today`.

### iOS / Android quick-capture

Carry's `PUT /api/file` endpoint is shaped for an iOS Shortcut / Android
intent — see [`console/static/carry/README.md`](../console/static/carry/README.md).
The vault has nothing to do with that wiring; you just need the console
running on a device the phone can reach (Tailscale is the usual trick).

### Local TTL daemon (laptop, not GitHub)

If you'd rather the daemon run on your laptop than on Actions, the
existing `tools/weaver.py` has a `schedule.every().day.at(...)` seam.
Add:

```python
schedule.every().day.at("23:55").do(
    lambda: subprocess.run([sys.executable, "tools/expire.py", str(VAULT)])
)
```

You'd skip `expire.yml` in that case. Don't run both — the workflow
would fight your laptop daemon.

---

## Troubleshooting

**The workflow ran but nothing committed.** That's normal when nothing
expired and the renders are byte-identical to last run. Check the run
logs for `no changes — nothing to commit`.

**The workflow fails with "remote rejected: refusing to update protected
branch".** Branch protection is on `main` and the workflow's commit
violates a rule. Either (a) loosen branch protection for the bot, (b)
have the workflow push to a `weaver/<date>` branch and open a PR, or
(c) use a PAT with bypass rights. Option (a) is fine for a single-user
private repo.

**`tools/expire.py: ModuleNotFoundError: substrate`.** The workflow runs
the daemon from the operator-core-mini checkout (`../substrate/tools/`),
which puts `tools/` on `sys.path` automatically. If you copied
`expire.py` into the vault directly instead, also copy `substrate.py`
next to it.

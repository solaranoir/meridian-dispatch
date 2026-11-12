# The Meridian Dispatch: GitHub Actions Edition

A daily geography/timekeeping news digest, hosted on GitHub's Linux runners. **No server, Mac scheduler, or Nextcloud needed.** The workflow runs at 06:00 America/Los_Angeles (subject to GitHub Actions scheduling delays), emails via Gmail SMTP, and stores Markdown/HTML/JSON output as workflow artifacts for 30 days.

## 1. Create a PRIVATE GitHub repository

Create a new private repository (for example `meridian-dispatch`). Upload the contents of this folder to the **root** of that repository. Do not upload `.env` or passwords. From your local terminal, inside the extracted folder:

```bash
git init
git add .
git commit -m 'Initial Meridian Dispatch GitHub Actions deployment'
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/meridian-dispatch.git
git push -u origin main
```

If you create the GitHub repo with an initial README, resolve that separate commit before pushing, or create it empty. Alternatively upload files in the GitHub web interface, including the hidden `.github/workflows/dispatch.yml` path.

## 2. Gmail App Password

Enable Google 2-Step Verification, then visit https://myaccount.google.com/apppasswords and create an app password named `Meridian Dispatch`. App Password availability depends on your account. Do not share it in chat or commit it to Git.

In the GitHub repository, go to **Settings → Secrets and variables → Actions → New repository secret**. Add all four secrets:

| Secret | Value |
|---|---|
| `SMTP_USER` | Gmail address used for sending |
| `SMTP_PASSWORD` | 16-character Google App Password |
| `EMAIL_FROM` | Same Gmail address |
| `EMAIL_TO` | Recipient email address (may be the same) |

`SMTP_HOST`, `SMTP_PORT`, and `SMTP_SSL` are already configured in the workflow. No Nextcloud variables are needed.

## 3. Enable write permission for history

Repository **Settings → Actions → General → Workflow permissions → Read and write permissions**. This is required because the workflow commits `data/articles.sqlite3` after successfully sending. If your organization disallows write permissions, the history persistence step will fail; see the notes below.

## 4. Preview first (no email)

Open **Actions → Meridian Dispatch Daily → Run workflow**, leave `dry_run` checked, and start the workflow. Open the run logs and download its `meridian-dispatch-...` artifact to inspect the Markdown/HTML/JSON report. A dry run does not mark articles seen.

## 5. Test real email

Run the workflow again with `dry_run` unchecked. Verify Gmail receives the digest. The SQLite deduplication file will be committed to the repository after a successful email send. The daily schedule is active as soon as the workflow exists on the default branch and Actions is enabled; there is no separate timer activation step. For a cautious rollout, comment out the `schedule:` stanza until the test passes, then restore it.

## 6. Daily operation

The workflow uses `cron: '0 6 * * *'` and `timezone: 'America/Los_Angeles'`. Scheduled jobs can be delayed or occasionally dropped by GitHub. Logs and downloadable report files appear in the **Actions** tab. The project uses Python's standard library only; no `pip install` is required.

### Reliability and limitations

- RSS-derived titles are **not** verified article summaries. Follow the source links for full reporting.
- This edition saves seen-article hashes in tracked `data/articles.sqlite3`. Use a **private repository** if you prefer not to publish that history.
- **Email-then-commit is not transactional.** If Gmail succeeds but the final Git push fails, a retry may resend some stories. Check logs before retrying a failed run.
- GitHub Actions artifacts expire after 30 days by default in this workflow; the SQLite history remains in Git. Adjust artifact retention to suit your repository settings.
- If all RSS feeds fail, the workflow fails rather than sending a misleading empty digest.
- Gmail sending limits and App Password account restrictions apply.
- Do not use `--upload-nextcloud` in this deployment.

## Local preview

```bash
python3 -m unittest discover -s tests -v
python3 -m meridian_dispatch.main --dry-run --days 7 --max-items 10
```

## Troubleshooting

- `Missing required GitHub Actions secret`: check the exact four secret names.
- `SMTPAuthenticationError`: confirm Gmail address, App Password, and 2-Step Verification.
- `Permission denied` on `git push`: enable read/write workflow permissions, and verify branch protection rules permit the bot's commit.
- `0 new item(s)`: review RSS and selection diagnostics; if the state file has already seen those articles, use the dry-run to inspect candidates without sending.

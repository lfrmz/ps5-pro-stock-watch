# PS5 Pro Stock Watch — Australia

A lightweight, automatically updating website to track **new and professionally refurbished PlayStation 5 Pro consoles** at Australian retailers. No program needs to be installed or left running on your PC.

- **Automatic checks:** GitHub Actions runs the Python monitor approximately every 15 minutes (GitHub schedules can be delayed).
- **Dashboard:** Free static website on GitHub Pages, viewable from phone or desktop. Shows price detected, condition, retailer, link and last check.
- **Notifications:** Free Telegram alerts, or optionally a Discord webhook, when stock is first detected / returns. No spam on each subsequent check. An explicit out-of-stock result re-arms the alert; unknown results never do.
- **Pre-orders:** Shown as a different status; not notified by default.
- **Unknown results:** Sites that block bots / change page markup are **unknown**, never incorrectly reported as in stock. No false 'sold out' on a timeout.
- **Not included:** Unrefurbished preowned, ordinary used items, PS5 Slim/base, PS4 Pro and third-party marketplace listings.

## Retailers included

| Retailer | Listing | Condition |
|---|---|---|
| JB Hi-Fi | Official PS5 Pro | New |
| Sony Australia | Sony Store PS5 Pro | New |
| BIG W | Official BIG W PS5 Pro | New |
| Target | Target PS5 Pro | New |
| Harvey Norman | PS5 Pro (category listing, cautious parsing) | New |
| EB Games | Refurbished digital PS5 Pro | Refurbished |
| EB Games | Refurbished PS5 Pro with disc drive | Refurbished |

**EB Games caveat:** These two specifically selected EB Games products explicitly say *Refurbished by EB Games* in the listing title, although EB's own site also calls them "preowned." Unrefurbished used stock is excluded. Each URL is maintained separately in `retailers.json` so the monitor does not accidentally match arbitrary other products.

## Set up — browser only, no install

### 1. Create a GitHub repository

1. Sign in to [GitHub](https://github.com) (a free account is enough).
2. Click **+ → New repository**. Name it `ps5-pro-stock-watch`; choose **Public** to use free GitHub Pages. Do not add a README/license initially.
3. Download and **extract** the provided ZIP. In the repository click **uploading an existing file** and upload the *contents of the extracted folder*, keeping the `.github/workflows/check-stock.yml` structure and the `docs` folder. On some systems hidden folders like `.github` are not visible; ensure it is included. GitHub's web uploader may not reliably accept whole nested folder trees: if so, use GitHub's web editor to create `.github/workflows/check-stock.yml` (and paste its supplied content), and upload the remaining folder files.
4. Commit the files to the default `main` branch. The workflows file must appear under `.github/workflows/check-stock.yml`.

**Simpler alternative:** If you already use Git, extract the folder, create an empty GitHub repo and run `git init`, `git add .`, `git commit -m "Initial version"`, `git branch -M main`, `git remote add origin YOUR_REPO_URL`, `git push -u origin main`. No need for this method if GitHub's browser upload works.

### 2. Turn on free GitHub Pages

1. Go to the repository's **Settings → Pages**.
2. Under **Build and deployment**, select **GitHub Actions** (NOT "Deploy from a branch").
3. Under **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, if that option is available, and save. The workflow requests permission to update the report, deploy Pages and obtain an ID token. Some organisations restrict this.
4. Once you run the stock-check workflow, the published URL will be `https://YOUR-GITHUB-USERNAME.github.io/ps5-pro-stock-watch/` (unless you gave the repo a different name). GitHub will also show the actual deployment URL on the Pages settings screen.

### 3. Set up Telegram notifications (recommended)

1. Open [Telegram](https://web.telegram.org) on the web or phone, and message **@BotFather**.
2. Send `/newbot` and follow the prompts. Copy the **bot token** it supplies. Treat the token like a password.
3. Open the new bot you created, click **Start** and send `hello`.
4. In your browser, replace `YOUR_TOKEN` in `https://api.telegram.org/botYOUR_TOKEN/getUpdates`. In the JSON reply, find `"chat":{"id":123456789,...}`. That number is your **chat ID**. You might need to send another message to the bot if `result` is empty. **Do not share the token URL or token publicly.**
5. In your GitHub repository go to **Settings → Secrets and variables → Actions → Secrets → New repository secret**, adding:
   - `TELEGRAM_BOT_TOKEN` — your bot token
   - `TELEGRAM_CHAT_ID` — your chat ID
6. Optional alternative: create a Discord channel webhook and add secret `DISCORD_WEBHOOK_URL`. Telegram takes priority if both are configured.

**Never put Telegram credentials in `retailers.json`, website files, or committed code.** The dashboard is public, while Secrets remain private to GitHub Actions.

### 4. Run it!

1. In the GitHub repository choose **Actions → Check Australian PS5 Pro stock → Run workflow**.
2. The initial run fetches retailer listings, records `docs/stock.json`, and deploys the dashboard to Pages. The schedule continues automatically.
3. To test notifications without falsely claiming a real restock, choose **Run workflow**, tick **Send a test alert**, and run. This sends an alert clearly labeled `TEST` and does **not** modify your stock report.
4. Bookmark the Pages URL on your phone or computer. The page refreshes the last saved report once per minute while open. Actual retailer checks run on GitHub's servers whether your browser is open or not.

## Custom settings

- **Preorder alerts:** Add a repository **variable** (not a Secret) named `NOTIFY_PREORDERS` with value `true` under **Settings → Secrets and variables → Actions → Variables**. Default `false`.
- **Check frequency:** Edit the cron expression in `.github/workflows/check-stock.yml`. Default `*/15 * * * *` = every 15 minutes. GitHub schedules are approximate; check scheduling/platform limits before making it more frequent. Excessive scraping may get you blocked.
- **Retailers:** Add/edit **specific verified retailer product URLs** in `retailers.json` rather than generic search pages. The tracker uses a strict curated list and cautious in-stock detection. Each listing needs a unique `id`, `retailer`, `name`, `condition`, and `url`.
- **Run tests:** `python -m unittest discover -s tests -v` (if you do use a local Python interpreter, install `requirements.txt` first). GitHub runs the tests for you too.
- **Live debug:** Open **Actions**, select the most recent scheduled run, and expand *Check retailers or send test alert* to see why any listing is `unknown`.

## Important limitations

**This is a working deployable project, not a pre-deployed monitoring service.** It only begins running automatically after you create the GitHub repo, turn on Pages and run the workflow. I cannot deploy it to your personal GitHub or configure your Telegram account without your access.

Retailer anti-bot protection can return HTTP 403/429, captchas or incomplete JavaScript pages. These are marked `unknown` and **do not cause stock alerts**. If a store makes stock available only after a postcode/store selection, a public purchase button may not mean stock is deliverable to Cairns. Verify stock and the final price at the actual checkout. This monitor does not reserve or purchase consoles. GitHub's scheduled workflows can be late or skipped during high load; scheduled workflows on public repos can be disabled after extended inactivity, subject to GitHub's current policies. Free Pages is public and your stock report is visible to everyone who finds the URL. A scheduled run creates an updated commit for stateful alert suppression, so commit history also contains stock observations (never your Telegram credentials).

Check each site's terms/robots policies before running long-term; scripts are deliberately low-frequency and make only one page request per product per cycle. Some retailers may change markup, which will require adapting the parser. The monitor has automated **mock-data tests**, but we cannot guarantee future live requests or actual checkout availability across all seven listings.

## Files

- `monitor.py` — fetching, cautious parsing, stock-change detection and Telegram/Discord alerts
- `retailers.json` — whitelisted Australian listings and classifications
- `.github/workflows/check-stock.yml` — cloud schedule, tests and Pages deployment
- `docs/index.html` — no-build, mobile-friendly dashboard
- `docs/stock.json` — automatically updated report and alert-suppression state
- `tests/test_monitor.py` — unit tests for stock/pre-order/error logic

No telemetry or analytics are included. All code can be inspected and modified.

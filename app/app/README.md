# Lead Ledger — Amazon Affiliate Outreach Scraper

Finds contact info on Amazon-affiliate sites (via [Scrapling](https://github.com/D4Vinci/Scrapling))
and shows it in a copyable sheet, so you can paste it straight into your
cold-email tool or n8n workflow.

```
amazon-affiliate-leads/
├── config.py              # all settings, loaded from .env
├── main.py                # CLI: run the scraper
├── api.py                 # FastAPI: serves scraped leads to the frontend
├── requirements.txt
├── .env.example
├── data/
│   ├── seeds.txt          # URLs you want scraped (you fill this in)
│   └── leads.json         # output — created automatically
├── scraper/
│   ├── models.py          # the Lead data shape
│   ├── extractor.py       # fetch + parse a page with Scrapling
│   ├── discovery.py       # seed-list loader (+ optional keyword search)
│   ├── utils.py           # regex/text helpers (emails, phones, signals)
│   └── store.py           # JSON read/write for leads.json
└── frontend/              # Vite + React "sheet" UI
    ├── src/App.jsx
    └── src/components/Sheet.jsx
```

## 1. Backend setup (Python)

```bash
cd amazon-affiliate-leads
python3 -m venv venv

# activate it
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows

pip install -r requirements.txt

# Scrapling ships browser drivers separately — this installs them
scrapling install

cp .env.example .env            # then edit values if you want
```

## 2. Add sites to scrape

Open `data/seeds.txt` and add one Amazon-affiliate site URL per line:

```
https://real-site-you-found.com
https://another-affiliate-blog.com
```

This is the reliable way to feed the scraper. `scraper/discovery.py` also
has an optional `search_candidate_urls()` helper that scrapes DuckDuckGo's
HTML results for a keyword — it's there for convenience, but automated
search-engine querying is more legally/ToS-sensitive than scraping a site
you've already identified by hand, so treat it as a low-volume supplement,
not your main source.

## 3. Run the scraper

```bash
python main.py                     # scrapes everything in data/seeds.txt
python main.py --url https://x.com # scrape just one site
python main.py --mode stealthy     # use a real headless browser instead
                                    # of plain HTTP (slower, gets past more
                                    # anti-bot / JS-rendered sites)
```

Results are written to `data/leads.json`. Re-running is safe — a site
already in the file gets updated in place rather than duplicated.

## 4. Start the API

```bash
uvicorn api:app --reload --port 8000
```

## 5. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the printed `localhost:5173` URL. The sheet loads leads from the API,
lets you filter by business/domain/email, and has **Copy sheet** (tab-
separated, pastes cleanly into Google Sheets/Excel with columns intact)
and **Download CSV** buttons.

## Wiring it into n8n

The realistic pattern for what you're pitching to these leads: rather than
having n8n call Scrapling directly, run this scraper on a schedule
(cron / `main.py` as a scheduled job) and have n8n pick up the results —
either by reading `data/leads.json` (an n8n **Read Binary File** /
**Local File Trigger** node), or by calling your own `/api/leads` endpoint
with an **HTTP Request** node. From there n8n can push new rows into your
CRM, a Google Sheet, or your cold-email sending tool.

## Compliance — read before sending anything

- **Only scrape what's publicly published** (site text, listed emails).
  Don't attempt to bypass logins or paywalls.
- Check each site's `robots.txt` if you plan to scrape at real volume —
  Scrapling doesn't enforce it automatically.
- Cold email law varies by where your leads are: in the US, **CAN-SPAM**
  requires a working opt-out, your real physical address, and an
  honest subject line/sender. In the EU/UK, unsolicited B2C email
  generally needs consent under **GDPR/PECR**; B2B is more permissive
  but still requires an easy opt-out and honest identification.
- Keep an unsubscribe/suppression list from message one, and honor it
  immediately.

None of this blocks the workflow above — it just shapes the email copy
and how you track opt-outs, which is worth building into the n8n side.

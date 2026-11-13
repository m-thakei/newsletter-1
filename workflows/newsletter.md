# Workflow: Executive Newsletter

## Objective
Turn a topic from the user into a short, formal newsletter for executives,
with two infographics, and send it through Gmail. Runs on demand in chat.

## Inputs
- **Topic** (required), from the user.
- **Recipients** (required before the final send), from the user, for every issue.
  They change each time and are never stored. Ask for them if not given.
- Optional: specific angles, sources or figures the user wants included.
- `.env`: `TAVILY_API_KEY`, `GMAIL_SENDER`, `GMAIL_SENDER_NAME`.
- `credentials.json` (Gmail OAuth Desktop client) in the project root.

## Editorial rules
- **Audience:** executives. **Tone:** formal, concise, decision-oriented. No hype, no emojis.
- **Name:** derive a short name (2–3 words) from the topic, e.g. "The AI Brief".
  Propose it to the user on the first issue of a new topic; reuse it afterwards.
- **Length:** the written text is at most one A4 page, which the builder enforces as
  550 words. The two infographics come on top and don't count toward it.
- **Infographics:** exactly 2. Use real figures from the research only, and cite the source on the graphic.
- **Structure:** headline, 3-point executive summary, 2–3 short sections,
  "The bottom line" (1–2 sentences), sources.
- Every number in the text or an infographic must come from the research file. Never invent figures.
- Use British or American spelling consistently within an issue.

## Steps

### 1. Research
```
.venv/bin/python tools/research_topic.py "<topic>" --query "<angle 1>" --query "<angle 2>"
```
- Add 2–3 `--query` angles: latest developments, key statistics, business impact.
- For fast-moving topics add `--news --time-range month`.
- Output: `.tmp/research/<slug>.json`. Read it fully before writing.
- Cost: 2 Tavily credits per query (advanced). Free tier is about 1,000 credits a month.

### 2. Write the content
- Write `.tmp/issues/<slug>.content.json` in the format documented at the top of
  `tools/build_newsletter_html.py`. Use `tools/examples/content.json` as a model.
- Pick the 2 infographics while writing: which figures deserve a visual.

### 3. Make the infographics
- Write one spec per infographic, e.g. `.tmp/infographics/<slug>-1.json`. Templates:
  | Template | Use for | Items |
  |---|---|---|
  | `key_figures` | headline statistics | 2–4 (3 fits best on one page) |
  | `bar_chart` | comparing values across categories | 3–7 |
  | `process` | steps, phases, a timeline | 3–5 |
  | `comparison` | two options side by side | 2 columns |
- Examples: `tools/examples/*.json`. Icons are Lucide names (lucide.dev/icons).
```
.venv/bin/python tools/render_infographic.py .tmp/infographics/<slug>-1.json
```
- Look at each PNG before using it.

### 4. Build the email
```
.venv/bin/python tools/build_newsletter_html.py .tmp/issues/<slug>.content.json
```
- Fix any word-count WARNING by tightening copy, then rebuild.
- Show the user `preview.html` (or `preview.pdf`) and get approval of the content.

### 5. Send
1. Test to the sender: `.venv/bin/python tools/send_gmail.py .tmp/issues/<issue>/manifest.json`
2. Ask the user to check the test email in Gmail, and confirm this issue's recipients.
3. Only after the user explicitly approves, send to the recipients they gave:
   `.venv/bin/python tools/send_gmail.py <manifest> --to "a@example.com, b@example.com"`

## Edge cases and lessons learned
- **Lucide icon renamed:** `line-chart` is now `chart-line`. If an icon 404s, search lucide.dev for the current name.
- **Gmail and images:** Gmail blocks SVG and base64 images. Infographics are PNG inline attachments (cid:), which display reliably.
- **First Gmail send:** opens a browser for OAuth consent; `token.json` is saved and reused.
  If the token is revoked or expires, delete `token.json` and send again.
- **Sending limit:** a personal Gmail account sends to about 500 recipients a day.
- **Python:** the project uses Homebrew Python 3.14 in `.venv`. The macOS system Python (3.9)
  is end-of-life and printed OpenSSL warnings; don't use it.
- **A4 limit applies to text only:** two full-size infographics take about half an A4 page at
  email width, so a full issue prints to about 1.5 pages. That is expected; the user decided
  the A4 limit is for the written text.

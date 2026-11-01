# Post Formatter Bot 🤖✍️

Ye Telegram bot **Claude AI (Anthropic API)** se aapke channel posts ko **Spitting** ya **GeoSight** style
mein format karta hai.

Ye **@Priyanshipostbot (posting bot) se alag** hai. Ye channel par kuch post nahi karta – sirf final post
usi chat mein bhejta hai (owner ka DM ya aapka group), aap use @Priyanshipostbot ko forward karte ho, wahan approval ke baad post hoti hai.

## Kaise use karein

1. Group mein (ya owner apne DM mein) raw content bhejo – sirf text, ya photo + text.
2. Style chuno: **🔥 Spitting style** ya **🌍 GeoSight style**.
3. Bot formatted post ka preview bhejega. Neeche buttons:
   - 🔁 **Regenerate text** – naya version likhta hai
   - ✏️ **Edit** – aap likh kar batao kya badalna hai (jaise "headline chhoti karo")
   - ✅ **Done** – final post (photo + caption, ya text) usi chat mein aa jayegi
4. Final post ko **@Priyanshipostbot** ko forward kar do. Footer / "Join" line woh bot khud lagata hai.

Commands: `/start` `/help` `/cancel` (edit cancel) `/id` (apna user ID, group mein group ka chat ID bhi).

**Kaun use kar sakta hai:**
- **DM mein sirf owner** (`OWNER_ID`). Koi aur DM kare to bot sirf mana karta hai aur uska user ID dikha deta hai.
- **Ek specific group** (`GROUP_CHAT_ID`) – us group ka har member use kar sakta hai.
- Kisi aur group mein bot chup rehta hai.
- Preview ke buttons sirf wahi daba sakta hai jisne woh content bheja tha.

**Group setup:**
1. Bot ko group mein add karo aur **admin bana do** (warna bot group ke normal messages dekh nahi pata).
   Ya @BotFather → `/setprivacy` → bot chuno → **Disable**.
2. Group mein `/id` bhejo – bot group ka chat ID batayega (jaise `-1001234567890`).
3. Woh ID `GROUP_CHAT_ID` secret mein daal do (neeche dekho). Bot restart hote hi group mein kaam karega.

Tip: is kaam ke liye alag group rakho – group ke har text/photo message par bot style ke buttons bhejta hai.

## Styles

- **Spitting (@spitting_fact):** line 1 par chhoti punchy headline, neeche simple body. Hindi/Hinglish/English
  jaisa bheja waisa hi rehta hai (translate nahi hota).
- **GeoSight (@GeoSight):** channel admins ke rules – post simple aur samajhne mein aasaan, heading mein
  country flag (🇮🇳), points ▪️ 🔹 🔺 ke saath, quality over quantity.
  (Do posts ke beech 30-35 minute ka gap @Priyanshipostbot ka kaam hai – wahan GeoSight channel ka gap set karein.)
- Har style mein: koi fact, naam, number, link ya @mention badla/banaya nahi jaata. Photo wali post max
  1024 characters.

**Style aur behtar karna hai?** Apne channel ki 3-5 achhi posts `bot/styles/spitting_examples.txt` ya
`bot/styles/geosight_examples.txt` mein daal do (har post ke beech ek line par sirf `---`). Push karte hi
bot restart hokar unhi jaisa likhne lagega. Rules badalne hain to `bot/styles.py` dekho.

## Setup (GitHub Actions – 24/7, free)

Bot GitHub Actions par ~6 ghante ke runs ki chain mein chalta hai (purane bot jaisa). Har run khatam hone se
pehle agla run start kar deta hai. MongoDB lease ensure karta hai ki ek time par sirf ek copy chale.

**Repo secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Kya hai |
|---|---|
| `BOT_TOKEN` | @BotFather se naye bot ka token |
| `OWNER_ID` | `7364684102` |
| `GROUP_CHAT_ID` | woh group jahan sab members bot use kar sakein (group mein `/id` se milega) |
| `ANTHROPIC_API_KEY` | platform.claude.com → API keys (credits add hone chahiye) |
| `MONGO_URL` | MongoDB Atlas connection string (purane bot wala cluster chalega) |
| `MONGO_DB_NAME` | optional, default `post_formatter_bot` (`channel_poster_bot` allowed nahi hai) |

Terminal se secret set karna (value paste karne ka prompt aata hai, screen par nahi dikhti):

```bash
gh secret set ANTHROPIC_API_KEY -R varungaur777/post-formatter-bot
```

**Optional variables** (Secrets and variables → Actions → Variables):

| Variable | Default | Matlab |
|---|---|---|
| `AI_MODEL` | `claude-opus-5-5` | Claude model (sasta: `claude-sonnet-5-5`, sabse sasta: `claude-haiku-5-5`) |
| `AI_EFFORT` | `low` | Claude kitna sochta hai: `low` / `medium` / `high` |

⚠️ **Claude.ai ka subscription (Pro/Max) API key nahi hai.** API alag hai: platform.claude.com par
account → Billing mein credits add karo → API Keys se key banao (`sk-ant-...`).

**Bot rokna:** Actions → bot → "..." → Disable workflow, phir chalta hua run Cancel.
**Dobara chalana:** Enable workflow → Run workflow.

## Apne computer par chalana (testing)

```bash
cp .env.example .env   # values bharo
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m bot
```

Dhyan rahe: GitHub par bot chal raha ho to local copy lease ka wait karegi (ek time par ek hi copy).

Tests aur lint:

```bash
.venv/bin/pytest -q && .venv/bin/ruff check .
```

## Files

- `bot/handlers.py` – Telegram flow (buttons, preview, final post)
- `bot/ai.py` – Claude API call (post formatting)
- `bot/styles.py` – Spitting / GeoSight rules
- `bot/access.py` – kaun use kar sakta hai
- `bot/lease.py` – single-instance lease (MongoDB)
- `.github/workflows/bot.yml` – 24/7 run, `ci.yml` – tests, `keepalive.yml` – workflows ko active rakhta hai

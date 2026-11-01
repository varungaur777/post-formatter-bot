# Post Formatter Bot 🤖✍️

Ye Telegram bot **Claude AI (Anthropic API)** se aapke channel posts ko ek saaf format mein likhta hai:
**bold heading** (flag ke saath), ▪️🔹🔺 pointers, aur hamesha **English** mein. Bot ke apne messages bhi English mein hain.

Ye **@Priyanshipostbot (posting bot) se alag** hai. Ye channel par kuch post nahi karta – sirf final post
usi chat mein bhejta hai (owner ka DM ya aapka group), aap use @Priyanshipostbot ko forward karte ho, wahan approval ke baad post hoti hai.

## Kaise use karein

1. Group mein (ya owner apne DM mein) **`/format`** lagakar content bhejo. Bina `/format` ke bot kuch nahi karta.
   - `/format` aur uske aage post ka text
   - kisi message/photo par **reply** karke `/format` (aage extra text bhi likh sakte ho)
   - photo ke caption mein `/format ...`
2. Bot turant formatted post ka preview bhejega (heading bold). Neeche buttons:
   - 🔁 **Regenerate** – naya version likhta hai
   - ✏️ **Edit** – aap likh kar batao kya badalna hai (jaise "headline chhoti karo") – iske liye `/format` nahi lagana
   - ✅ **Done** – final post (photo + caption, ya text, heading bold) usi chat mein aa jayegi
   - ❌ **Cancel** – draft band
3. Final post ko **@Priyanshipostbot** ko forward kar do. Footer / "Join" line woh bot khud lagata hai.

Commands: `/format` `/start` `/help` `/cancel` (edit cancel) `/id` (apna user ID, group mein group ka chat ID bhi).

**Kaun use kar sakta hai:**
- **DM mein sirf owner** (`OWNER_ID`). Koi aur DM kare to bot sirf mana karta hai aur uska user ID dikha deta hai.
- **Ek specific group** (`GROUP_CHAT_ID`) – us group ka har member use kar sakta hai.
- Kisi aur group mein bot chup rehta hai.
- Preview ke buttons sirf wahi daba sakta hai jisne woh content bheja tha.

**Group setup:**
1. Bot ko group mein add karo aur **admin bana do** (`/format` bina admin ke bhi chalta hai, par ✏️ Edit ke
   baad wala normal message bot tabhi dekh pata hai jab woh admin ho).
   Ya @BotFather → `/setprivacy` → bot chuno → **Disable**.
2. Group mein `/id` bhejo – bot group ka chat ID batayega (jaise `-1001234567890`).
3. Woh ID `GROUP_CHAT_ID` secret mein daal do (neeche dekho). Bot restart hote hi group mein kaam karega.

Bot sirf `/format` wale messages par kaam karta hai, baaki group chat ko ignore karta hai.

## Post ka format

Rules @GeoSight admins ke hain:
- Line 1: heading, shuru mein main country ka flag (🇮🇳). Ye heading bot apne aap **bold** karta hai.
- Neeche short pointers: ▪️ main points, 🔹 details, 🔺 sabse important point.
- Simple aur samajhne mein aasaan, quality over quantity.
- Hamesha English. Hindi/Hinglish input bhi English mein translate hota hai (naam, jagah, @mention waise hi rehte hain).
- Koi fact, naam, number, link ya @mention badla ya banaya nahi jaata. Photo wali post max 1024 characters.
- Footer / "Join" / "Follow" line nahi lagti – woh @Priyanshipostbot lagata hai.
  (Do posts ke beech 30-35 minute ka gap bhi @Priyanshipostbot ka kaam hai.)

**Format aur behtar karna hai?** Apne channel ki 3-5 achhi posts `bot/styles/post_examples.txt` mein daal do
(har post ke beech ek line par sirf `---`). Push karte hi bot restart hokar unhi jaisa likhne lagega.
Rules badalne hain to `bot/styles.py` dekho.

## Setup (GitHub Actions – 24/7, free)

Bot GitHub Actions par ~6 ghante ke runs ki chain mein chalta hai (purane bot jaisa). Har run khatam hone se
pehle agla run start kar deta hai. MongoDB lease ensure karta hai ki ek time par sirf ek copy chale.

**Repo secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Kya hai |
|---|---|
| `BOT_TOKEN` | @BotFather se naye bot ka token |
| `OWNER_ID` | `8322550258` |
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
- `bot/styles.py` – post format ke rules
- `bot/access.py` – kaun use kar sakta hai
- `bot/lease.py` – single-instance lease (MongoDB)
- `.github/workflows/bot.yml` – 24/7 run, `ci.yml` – tests, `keepalive.yml` – workflows ko active rakhta hai

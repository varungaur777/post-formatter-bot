"""Every message the bot sends (simple Hinglish)."""

BOT_COMMANDS = [
    ("start", "Bot kaise use karein"),
    ("help", "Help"),
    ("cancel", "Edit cancel karein"),
    ("id", "User ID / group chat ID dekhein"),
]

HELP = (
    "👋 <b>Post Formatter Bot</b>\n\n"
    "1️⃣ Post ka raw content bhejiye – sirf text, ya photo + text.\n"
    "2️⃣ Style chuniye: <b>Spitting</b> ya <b>GeoSight</b>.\n"
    "3️⃣ Main Claude AI se post format karke preview bhejunga.\n"
    "4️⃣ Neeche buttons: 🔁 dobara likho, ✏️ badlav batao, ✅ Done.\n"
    "5️⃣ ✅ Done ke baad final post aayegi – use <b>@Priyanshipostbot</b> ko forward kar dijiye.\n"
    "🔒 Buttons sirf wahi daba sakta hai jisne content bheja.\n\n"
    "ℹ️ Footer / Join line main nahi lagata – woh posting bot khud lagata hai."
)
NOT_ALLOWED = (
    "⛔ DM mein ye bot sirf owner use kar sakta hai.\n"
    "Aapka user ID: <code>{uid}</code>"
)
YOUR_ID = "Aapka user ID: <code>{uid}</code>"
CHAT_ID = "Is group ka chat ID: <code>{cid}</code>"
CHOOSE_STYLE = "Kis channel ke style mein format karun? 👇"
UNSUPPORTED = "Abhi sirf <b>text</b> ya <b>photo + text</b> bhejiye. (Video / file / album support nahi hai.)"
ALBUM_FIRST_ONLY = "ℹ️ Album mein se sirf pehli photo use hogi."
WORKING = "⏳ {style} mein format ho raha hai..."
BUSY = "Ruko, pichla kaam chal raha hai..."
STALE = "Ye draft purana ho gaya – naya content bhejiye."
ASK_EDIT = (
    "✏️ Kya badalna hai? Likh kar bhejiye.\n"
    "Jaise: <i>headline chhoti karo</i>, <i>Hindi mein likho</i>, <i>last point hata do</i>.\n"
    "Cancel ke liye /cancel"
)
EDIT_CANCELLED = "Theek hai, edit cancel."
NOTHING_TO_CANCEL = "Cancel karne ko kuch nahi hai."
FINAL_NOTE = "👆 Ye final post hai – ise <b>@Priyanshipostbot</b> ko forward kar dijiye."
CANCELLED = "❌ Draft cancel ho gaya."
ERROR = "⚠️ {error}"
FAILED_RETRY = "Neeche button se dobara try kar sakte hain."

BTN_SPITTING = "🔥 Spitting style"
BTN_GEOSIGHT = "🌍 GeoSight style"
BTN_CANCEL = "❌ Cancel"
BTN_REGEN = "🔁 Regenerate text"
BTN_EDIT = "✏️ Edit"
BTN_DONE = "✅ Done"

"""Every message the bot sends (simple Hinglish)."""

BOT_COMMANDS = [
    ("format", "Post format karo (text likho ya message par reply karo)"),
    ("start", "Bot kaise use karein"),
    ("help", "Help"),
    ("cancel", "Edit cancel karein"),
    ("id", "User ID / group chat ID dekhein"),
]

HELP = (
    "<b>/format</b> ke saath post bhejo → style chuno → ✅ Done → final post "
    "<b>@Priyanshipostbot</b> ko forward karo.\n\n"
    "• <code>/format</code> aur uske aage post ka text\n"
    "• kisi message/photo par reply karke <code>/format</code>\n"
    "• photo ke caption mein <code>/format ...</code>"
)
FORMAT_USAGE = (
    "Kya format karun? <code>/format</code> ke aage text likho, ya kisi message/photo par reply karke "
    "<code>/format</code> likho."
)
FORMAT_HINT = "Post format karne ke liye <code>/format</code> lagao. (Help: /start)"
NOT_ALLOWED = (
    "⛔ DM mein ye bot sirf owner use kar sakta hai.\n"
    "Aapka user ID: <code>{uid}</code>"
)
YOUR_ID = "Aapka user ID: <code>{uid}</code>"
CHAT_ID = "Is group ka chat ID: <code>{cid}</code>"
CHOOSE_STYLE = "Kis channel ke style mein format karun? 👇"
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

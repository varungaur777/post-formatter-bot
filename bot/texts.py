"""Every message the bot sends (simple Hinglish)."""

BOT_COMMANDS = [
    ("start", "Bot kaise use karein"),
    ("help", "Help"),
    ("cancel", "Edit cancel karein"),
    ("id", "Apna Telegram user ID dekhein"),
    ("users", "Admin list (owner)"),
    ("adduser", "Admin add karein (owner)"),
    ("removeuser", "Admin hatayein (owner)"),
]

HELP = (
    "👋 <b>Post Formatter Bot</b>\n\n"
    "1️⃣ Mujhe post ka raw content bhejiye – sirf text, ya photo + text.\n"
    "2️⃣ Style chuniye: <b>Spitting</b> ya <b>GeoSight</b>.\n"
    "3️⃣ Main ChatGPT se post format karke preview bhejunga.\n"
    "4️⃣ Neeche buttons: 🎨 image banao, 🔁 dobara likho, ✏️ badlav batao, ✅ Done.\n"
    "5️⃣ ✅ Done ke baad final post aayegi – use <b>@Priyanshipostbot</b> ko forward kar dijiye.\n\n"
    "ℹ️ Footer / Join line main nahi lagata – woh posting bot khud lagata hai."
)
OWNER_HELP = (
    "\n\n<b>Owner commands</b>\n"
    "/adduser 123456789 – admin add\n"
    "/removeuser 123456789 – admin hatao\n"
    "/users – admin list"
)
NOT_ALLOWED = (
    "⛔ Aap is bot ko use nahi kar sakte.\n"
    "Aapka user ID: <code>{uid}</code>\n"
    "Owner ko ye ID bhejiye taaki woh aapko add kar sake."
)
YOUR_ID = "Aapka user ID: <code>{uid}</code>"
CHOOSE_STYLE = "Kis channel ke style mein format karun? 👇"
UNSUPPORTED = "Abhi sirf <b>text</b> ya <b>photo + text</b> bhejiye. (Video / file / album support nahi hai.)"
ALBUM_FIRST_ONLY = "ℹ️ Album mein se sirf pehli photo use hogi."
WORKING = "⏳ {style} mein format ho raha hai..."
IMAGE_WORKING = "🎨 Image ban rahi hai... (30-60 second lag sakte hain)"
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
BTN_IMAGE = "🎨 Generate image"
BTN_REGEN = "🔁 Regenerate text"
BTN_EDIT = "✏️ Edit"
BTN_DONE = "✅ Done"

OWNER_ONLY = "Ye command sirf owner ke liye hai."
ADD_USAGE = "Aise likhiye: /adduser 123456789"
REMOVE_USAGE = "Aise likhiye: /removeuser 123456789"
ADDED = "✅ <code>{uid}</code> ab bot use kar sakta hai."
ALREADY = "<code>{uid}</code> pehle se allowed hai."
REMOVED = "🗑 <code>{uid}</code> hata diya."
REMOVE_ENV = "<code>{uid}</code> SUBMITTER_IDS secret mein hai – GitHub secret se hatana padega."
REMOVE_OWNER = "Owner ko nahi hata sakte."
REMOVE_MISSING = "<code>{uid}</code> list mein nahi hai."
USERS = "<b>Owner:</b> <code>{owner}</code>\n<b>SUBMITTER_IDS (secret):</b> {env}\n<b>/adduser se added:</b> {added}"

"""Every message the bot sends (plain, simple English)."""

BOT_COMMANDS = [
    ("format", "Format a post (add text, or reply to a message)"),
    ("start", "How to use the bot"),
    ("help", "Help"),
    ("cancel", "Cancel a pending edit"),
    ("id", "Show your user ID / this group's chat ID"),
]
# shown only in the owner's private chat
OWNER_COMMANDS = [("wallet", "How much the bot has spent on Claude"), ("groups", "List authorized groups")]

HELP = (
    "<b>Post Formatter</b>\n\n"
    "Send <b>/format</b> with your content and I'll turn it into a clean post.\n\n"
    "• <code>/format</code> followed by the text\n"
    "• Reply to a message or photo with <code>/format</code>\n"
    "• Send a photo with <code>/format ...</code> in the caption\n\n"
    "Then use the buttons: 🔁 Regenerate, ✏️ Edit, ✅ Done.\n"
    "Forward the final post to <b>@Priyanshipostbot</b> for approval."
)
FORMAT_USAGE = (
    "Nothing to format. Write the text after <code>/format</code>, or reply to a message or photo with "
    "<code>/format</code>."
)
FORMAT_HINT = "To format a post, use <code>/format</code>. See /start for help."
NOT_ALLOWED = (
    "⛔ Sorry, only the owner can use this bot in private chat.\n"
    "Your user ID: <code>{uid}</code>"
)
YOUR_ID = "Your user ID: <code>{uid}</code>"
CHAT_ID = "This group's chat ID: <code>{cid}</code>"
WORKING = "⏳ Formatting your post..."
BUSY = "Please wait, I'm still working on this post..."
STALE = "This draft has expired or isn't yours. Send /format again."
ASK_EDIT = (
    "✏️ What should I change? Just type it.\n"
    "For example: <i>make the heading shorter</i>, <i>remove the last point</i>.\n"
    "Send /cancel to stop."
)
EDIT_CANCELLED = "OK, edit cancelled."
NOTHING_TO_CANCEL = "There's nothing to cancel."
FINAL_NOTE = "👆 Final post is ready. Forward it to <b>@Priyanshipostbot</b>."
CANCELLED = "❌ Draft cancelled."
ERROR = "⚠️ {error}"
FAILED_RETRY = "You can try again with the button below."

BTN_REGEN = "🔁 Regenerate"
BTN_EDIT = "✏️ Edit"
BTN_DONE = "✅ Done"
BTN_CANCEL = "❌ Cancel"
BTN_RETRY = "🔁 Try again"

WALLET = (
    "💰 <b>Claude spend</b> (estimate)\n\n"
    "{today}\n{month}\n{total}\n\n"
    "Model: <code>{model}</code> · ₹ at {rate:g} per $\n"
    "Exact bill and remaining balance: platform.claude.com → Billing"
)
WALLET_LINE = "<b>{label}:</b> ${usd:.4f} (≈ ₹{inr:.2f}) · {posts} posts · {calls} AI requests"

AUTH_OK = "✅ This group is authorized. Members can now use <code>/format</code> here."
AUTH_NOT_ADMIN = "Make me an admin of this group first, then send /auth again."
AUTH_OWNER_ONLY = "Only the bot owner can do this. (If that's you, turn off \"Remain anonymous\" in your admin rights.)"
AUTH_IN_GROUP = "Send this command inside the group."
AUTH_FIRST = "This group isn't authorized yet. Make me an admin and send /auth."
UNAUTH_OK = "This group is no longer authorized."
UNAUTH_ENV = "This group is set by the GROUP_CHAT_ID secret, so it can't be removed here."
UNAUTH_MISSING = "This group isn't authorized."
GROUPS = "<b>Authorized groups</b>\n{groups}"
GROUPS_EMPTY = "No groups are authorized yet."
GROUP_LINE = "• {title} <code>{cid}</code>"

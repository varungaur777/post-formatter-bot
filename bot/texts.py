"""Every message the bot sends (plain, simple English)."""

BOT_COMMANDS = [
    ("format", "Format a post (add text, or reply to a message)"),
    ("start", "How to use the bot"),
    ("help", "Help"),
    ("cancel", "Cancel a pending edit"),
    ("id", "Show your user ID / this group's chat ID"),
]

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

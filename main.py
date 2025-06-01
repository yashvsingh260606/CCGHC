import logging
import random
import uuid
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# In-memory match storage
PM_MATCHES = {}
CCL_MATCHES = {}

USERS = {}  # user_id -> username for demo

def ensure_user(user):
    if user.id not in USERS:
        USERS[user.id] = user.first_name or user.username or "Player"

# --- PM MODE ---

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ /pm matches can only be started in groups.")
        return
    user = update.effective_user
    ensure_user(user)
    chat_id = update.effective_chat.id
    match_id = str(uuid.uuid4())
    PM_MATCHES[match_id] = {
        "initiator": user.id,
        "opponent": None,
        "state": "waiting_join",
        "chat_id": chat_id,
    }
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join Match", callback_data=f"pm_join_{match_id}")]])
    await update.message.reply_text(f"{USERS[user.id]} started a /pm match! Join now.", reply_markup=keyboard)

async def pm_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)
    if match_id not in PM_MATCHES:
        await query.answer("Match not found.", show_alert=True)
        return
    match = PM_MATCHES[match_id]
    if match["state"] != "waiting_join":
        await query.answer("Match already started.", show_alert=True)
        return
    if user.id == match["initiator"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return
    match["opponent"] = user.id
    match["state"] = "toss"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Heads", callback_data=f"pm_toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"pm_toss_tails_{match_id}"),
        ]
    ])
    await query.message.edit_text(f"{USERS[match['initiator']]}, choose Heads or Tails for the toss.", reply_markup=keyboard)
    await query.answer()

async def pm_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    try:
        _, _, choice, match_id = query.data.split("_", 3)
    except ValueError:
        await query.answer("Invalid callback data.", show_alert=True)
        return
    if match_id not in PM_MATCHES:
        await query.answer("Match not found.", show_alert=True)
        return
    match = PM_MATCHES[match_id]
    logger.info(f"PM toss choice by user {user.id}, initiator {match['initiator']}, state {match['state']}")
    if match["state"] != "toss":
        await query.answer("Not in toss phase.", show_alert=True)
        return
    if user.id != match["initiator"]:
        await query.answer("Only the initiator can choose the toss.", show_alert=True)
        return
    coin_result = random.choice(["heads", "tails"])
    toss_winner = match["initiator"] if choice == coin_result else match["opponent"]
    await query.message.edit_text(f"{USERS[toss_winner]} won the toss! (Coin was {coin_result})")
    await query.answer()

# --- CCL MODE ---

async def ccl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ /ccl matches can only be started in groups.")
        return
    user = update.effective_user
    ensure_user(user)
    chat_id = update.effective_chat.id
    match_id = str(uuid.uuid4())
    CCL_MATCHES[match_id] = {
        "initiator": user.id,
        "opponent": None,
        "state": "waiting_join",
        "chat_id": chat_id,
    }
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Join CCL Match", callback_data=f"ccl_join_{match_id}"),
            InlineKeyboardButton("Cancel Match ❌", callback_data=f"ccl_cancel_{match_id}"),
        ]
    ])
    await update.message.reply_text(f"{USERS[user.id]} started a /ccl match! Join now.", reply_markup=keyboard)

async def ccl_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)
    if match_id not in CCL_MATCHES:
        await query.answer("Match not found.", show_alert=True)
        return
    match = CCL_MATCHES[match_id]
    if match["state"] != "waiting_join":
        await query.answer("Match already started.", show_alert=True)
        return
    if user.id == match["initiator"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return
    match["opponent"] = user.id
    match["state"] = "toss"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Heads", callback_data=f"ccl_toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"ccl_toss_tails_{match_id}"),
        ]
    ])
    await query.message.edit_text(f"{USERS[match['initiator']]}, choose Heads or Tails for the toss.", reply_markup=keyboard)
    await query.answer()

async def ccl_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)
    if match_id not in CCL_MATCHES:
        await query.answer("Match not found or already ended.", show_alert=True)
        return
    match = CCL_MATCHES[match_id]
    if user.id != match["initiator"]:
        await query.answer("Only initiator can cancel the match.", show_alert=True)
        return
    del CCL_MATCHES[match_id]
    await query.message.edit_text("The CCL match was cancelled by the initiator.")
    await query.answer()

async def ccl_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    try:
        _, _, choice, match_id = query.data.split("_", 3)
    except ValueError:
        await query.answer("Invalid callback data.", show_alert=True)
        return
    if match_id not in CCL_MATCHES:
        await query.answer("Match not found.", show_alert=True)
        return
    match = CCL_MATCHES[match_id]
    logger.info(f"CCL toss choice by user {user.id}, initiator {match['initiator']}, state {match['state']}")
    if match["state"] != "toss":
        await query.answer("Not in toss phase.", show_alert=True)
        return
    if user.id != match["initiator"]:
        await query.answer("Only the initiator can choose the toss.", show_alert=True)
        return
    coin_result = random.choice(["heads", "tails"])
    toss_winner = match["initiator"] if choice == coin_result else match["opponent"]
    await query.message.edit_text(f"{USERS[toss_winner]} won the toss! (Coin was {coin_result})")
    await query.answer()

# --- Main ---

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("pm", pm_command))
    app.add_handler(CallbackQueryHandler(pm_join_callback, pattern=r"^pm_join_"))
    app.add_handler(CallbackQueryHandler(pm_toss_choice_callback, pattern=r"^pm_toss_"))

    app.add_handler(CommandHandler("ccl", ccl_command))
    app.add_handler(CallbackQueryHandler(ccl_join_callback, pattern=r"^ccl_join_"))
    app.add_handler(CallbackQueryHandler(ccl_cancel_callback, pattern=r"^ccl_cancel_"))
    app.add_handler(CallbackQueryHandler(ccl_toss_choice_callback, pattern=r"^ccl_toss_"))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
    

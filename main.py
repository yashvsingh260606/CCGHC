# PART 1: Config, Utilities, JSON Storage, User Registration, and Profile

import os
import json
import logging
import asyncio
import random
import time
from typing import List, Dict, Any, Optional

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

# ===== CONFIGURATION =====
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # <-- PUT YOUR BOT TOKEN HERE
ADMIN_IDS: List[int] = [123456789, 987654321]  # <-- PUT ADMIN USER IDs HERE

USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== JSON UTILITIES ======

def load_json(filename: str) -> Any:
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename: str, data: Any):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def get_users() -> Dict[str, Any]:
    return load_json(USERS_FILE)

def save_users(users: Dict[str, Any]):
    save_json(USERS_FILE, users)

def get_matches() -> Dict[str, Any]:
    return load_json(MATCHES_FILE)

def save_matches(matches: Dict[str, Any]):
    save_json(MATCHES_FILE, matches)

# ====== USER REGISTRATION ======
CHOOSING_USERNAME = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to HandCricket CCG Bot!\n"
        "Use /register to join the game.\n"
        "Use /help for all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Start the bot\n"
        "/register - Register as a player\n"
        "/profile - View your stats\n"
        "/leaderboard - Top players\n"
        "/pm - Start a match (groups only)\n"
        "/toss <match_id> - Start toss for a match\n"
        "/forfeit - Forfeit/cancel a match\n"
        "/add <user_id> <amount> - (admin) Add coins to a user"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = get_users()
    if str(user.id) in users:
        await update.message.reply_text("You are already registered!")
        return ConversationHandler.END
    await update.message.reply_text("Enter your preferred username:")
    return CHOOSING_USERNAME

async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    user = update.effective_user
    users = get_users()
    users[str(user.id)] = {
        "user_id": user.id,
        "name": user.full_name,
        "username": username,
        "coins": 100,
        "wins": 0,
        "losses": 0,
        "games_played": 0,
        "registered": True,
        "created_at": time.time()
    }
    save_users(users)
    await update.message.reply_text(f"Registered as {username}! Use /profile to view your stats.")
    return ConversationHandler.END

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = get_users()
    data = users.get(str(user.id))
    if data:
        await update.message.reply_text(
            f"👤 {data['username']}\n"
            f"Coins: {data['coins']}\n"
            f"Wins: {data['wins']}\n"
            f"Losses: {data['losses']}\n"
            f"Games Played: {data['games_played']}"
        )
    else:
        await update.message.reply_text("You are not registered yet. Use /register first.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_users()
    top = sorted(users.values(), key=lambda x: x.get("coins", 0), reverse=True)[:10]
    if not top:
        await update.message.reply_text("No players registered yet.")
        return
    msg = "🏆 Top 10 Players:\n"
    for i, user in enumerate(top):
        msg += f"{i+1}. {user.get('username', user.get('name', 'Unknown'))}: {user.get('coins', 0)} coins\n"
    await update.message.reply_text(msg)
# PART 2: /pm Command (Play Match), Join Logic, and Match Creation

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # Only allow in groups
    if chat.type == "private":
        await update.message.reply_text("❌ /pm can only be used in groups!")
        return

    # Generate a unique match_id (timestamp + user_id + chat_id)
    match_id = f"{int(time.time())}_{user.id}_{chat.id}"

    matches = get_matches()
    matches[match_id] = {
        "match_id": match_id,
        "chat_id": chat.id,
        "creator_id": user.id,
        "creator_name": user.full_name,
        "players": [user.id],
        "player_names": [user.full_name],
        "status": "waiting",
        "created_at": time.time()
    }
    save_matches(matches)

    join_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join", callback_data=f"join_{match_id}")]
    ])

    await update.message.reply_text(
        f"🏏 {user.full_name} started the match!\nClick below to join the game.",
        reply_markup=join_button
    )

async def join_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    match_id = data.split("_", 1)[1]

    matches = get_matches()
    match = matches.get(match_id)
    if not match:
        await query.answer("Match not found.", show_alert=True)
        return

    if user.id in match["players"]:
        await query.answer("You have already joined this match.", show_alert=True)
        return

    match["players"].append(user.id)
    match["player_names"].append(user.full_name)
    save_matches(matches)

    await query.answer("You joined the match!", show_alert=True)
    player_list = "\n".join(match["player_names"])
    await query.edit_message_text(
        f"🏏 {match['creator_name']} started the match!\nPlayers:\n{player_list}\nClick below to join the game.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Join", callback_data=f"join_{match_id}")]
        ])
    )
# PART 3: Toss, Forfeit, and Admin Add Coins

async def toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    try:
        match_id = context.args[0]
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /toss <match_id>")
        return

    matches = get_matches()
    match = matches.get(match_id)
    if not match or match["status"] != "waiting":
        await update.message.reply_text("Match not found or already started.")
        return

    if user.id not in match["players"]:
        await update.message.reply_text("You are not a player in this match.")
        return

    if len(match["players"]) < 2:
        await update.message.reply_text("At least 2 players required to start the toss.")
        return

    toss_winner = random.choice(match["players"])
    toss_loser = [pid for pid in match["players"] if pid != toss_winner][0]

    match["status"] = "in_progress"
    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["current_inning"] = 1
    match["scores"] = {str(toss_winner): 0, str(toss_loser): 0}
    match["turn"] = toss_winner
    save_matches(matches)

    await update.message.reply_text(
        f"Toss done! <a href='tg://user?id={toss_winner}'>Player</a> won the toss and will bat first.",
        parse_mode="HTML"
    )

async def forfeit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    matches = get_matches()
    # Find an active match where this user is a player and status is not ended
    match = next(
        (m for m in matches.values() if m["chat_id"] == chat.id and user.id in m["players"] and m["status"] in ["waiting", "in_progress"]),
        None
    )

    if not match:
        await update.message.reply_text("You are not in any active match here.")
        return

    users = get_users()

    # If toss not started (status == 'waiting')
    if match["status"] == "waiting":
        del matches[match["match_id"]]
        save_matches(matches)
        await update.message.reply_text("Match canceled. No win/loss recorded.")
        return

    # If toss started or game in progress
    opponent_ids = [p for p in match["players"] if p != user.id]
    if not opponent_ids:
        await update.message.reply_text("No opponent found.")
        return
    opponent_id = opponent_ids[0]

    # Update stats: win for opponent, loss for forfeiter
    if str(opponent_id) in users:
        users[str(opponent_id)]["wins"] += 1
    if str(user.id) in users:
        users[str(user.id)]["losses"] += 1
    save_users(users)
    match["status"] = "forfeited"
    match["winner"] = opponent_id
    match["ended_at"] = time.time()
    save_matches(matches)
    await update.message.reply_text("You forfeited the match. Opponent is declared the winner.")

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return

    users = get_users()
    if str(target_id) in users:
        users[str(target_id)]["coins"] += amount
        save_users(users)
        await update.message.reply_text(f"Added {amount} coins to user {target_id}.")
    else:
        await update.message.reply_text("User not found.")
# PART 4: Main Function, Handlers, and Application Setup

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("pm", pm_command))
    application.add_handler(CommandHandler("toss", toss))
    application.add_handler(CommandHandler("forfeit", forfeit))
    application.add_handler(CommandHandler("add", add_coins))

    # Registration conversation
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register)],
        states={
            CHOOSING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username)],
        },
        fallbacks=[],
    )
    application.add_handler(registration_handler)

    # Callback handler for join button
    application.add_handler(CallbackQueryHandler(join_match_callback, pattern=r"^join_"))

    print("HandCricket CCG Bot is running...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
    

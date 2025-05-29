# PART 1: Config, Database, Utilities, User Registration, and Profile

import os
import logging
import asyncio
import random
import time
from typing import List, Dict, Any, Optional

from pymongo import MongoClient, DESCENDING
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

MONGO_URL = os.environ.get("MONGO_URL")
if not MONGO_URL:
    raise Exception("MONGO_URL environment variable not set!")

client = MongoClient(MONGO_URL)
db = client["handcricket_bot"]
users_col = db["users"]
matches_col = db["matches"]

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
    if users_col.find_one({"user_id": user.id}):
        await update.message.reply_text("You are already registered!")
        return ConversationHandler.END
    await update.message.reply_text("Enter your preferred username:")
    return CHOOSING_USERNAME

async def register_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    user = update.effective_user
    users_col.insert_one({
        "user_id": user.id,
        "name": user.full_name,
        "username": username,
        "coins": 100,
        "wins": 0,
        "losses": 0,
        "games_played": 0,
        "registered": True,
        "created_at": time.time()
    })
    await update.message.reply_text(f"Registered as {username}! Use /profile to view your stats.")
    return ConversationHandler.END

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = users_col.find_one({"user_id": user.id})
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
    top = list(users_col.find().sort("coins", DESCENDING).limit(10))
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

    # Insert match into MongoDB
    matches_col.insert_one({
        "match_id": match_id,
        "chat_id": chat.id,
        "creator_id": user.id,
        "creator_name": user.full_name,
        "players": [user.id],
        "player_names": [user.full_name],
        "status": "waiting",
        "created_at": time.time()
    })

    # Build join button
    join_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join", callback_data=f"join_{match_id}")]
    ])

    # Announce match with join button
    await update.message.reply_text(
        f"🏏 {user.full_name} started the match!\nClick below to join the game.",
        reply_markup=join_button
    )

async def join_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data  # e.g., "join_1234567890_12345_67890"
    match_id = data.split("_", 1)[1]

    match = matches_col.find_one({"match_id": match_id})
    if not match:
        await query.answer("Match not found.", show_alert=True)
        return

    if user.id in match["players"]:
        await query.answer("You have already joined this match.", show_alert=True)
        return

    # Add user to match
    matches_col.update_one(
        {"match_id": match_id},
        {"$push": {"players": user.id, "player_names": user.full_name}}
    )

    await query.answer("You joined the match!", show_alert=True)
    # Optionally, edit the message to show updated player list
    updated_match = matches_col.find_one({"match_id": match_id})
    player_list = "\n".join(updated_match["player_names"])
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

    # Expect: /toss <match_id>
    try:
        match_id = context.args[0]
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /toss <match_id>")
        return

    match = matches_col.find_one({"match_id": match_id, "status": "waiting"})
    if not match:
        await update.message.reply_text("Match not found or already started.")
        return

    if user.id not in match["players"]:
        await update.message.reply_text("You are not a player in this match.")
        return

    if len(match["players"]) < 2:
        await update.message.reply_text("At least 2 players required to start the toss.")
        return

    # Randomly pick who bats/bowls first
    toss_winner = random.choice(match["players"])
    toss_loser = [pid for pid in match["players"] if pid != toss_winner][0]

    matches_col.update_one(
        {"match_id": match_id},
        {"$set": {
            "status": "in_progress",
            "toss_winner": toss_winner,
            "toss_loser": toss_loser,
            "current_inning": 1,
            "scores": {str(toss_winner): 0, str(toss_loser): 0},
            "turn": toss_winner
        }}
    )

    await update.message.reply_text(
        f"Toss done! <a href='tg://user?id={toss_winner}'>Player</a> won the toss and will bat first.",
        parse_mode="HTML"
    )

async def forfeit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # Find an active match where this user is a player and status is not ended
    match = matches_col.find_one({
        "chat_id": chat.id,
        "players": user.id,
        "status": {"$in": ["waiting", "in_progress"]}
    })

    if not match:
        await update.message.reply_text("You are not in any active match here.")
        return

    # If toss not started (status == 'waiting')
    if match["status"] == "waiting":
        matches_col.delete_one({"match_id": match["match_id"]})
        await update.message.reply_text("Match canceled. No win/loss recorded.")
        return

    # If toss started or game in progress
    opponent_ids = [p for p in match["players"] if p != user.id]
    if not opponent_ids:
        await update.message.reply_text("No opponent found.")
        return
    opponent_id = opponent_ids[0]

    # Update stats: win for opponent, loss for forfeiter
    users_col.update_one({"user_id": opponent_id}, {"$inc": {"wins": 1}})
    users_col.update_one({"user_id": user.id}, {"$inc": {"losses": 1}})
    matches_col.update_one(
        {"match_id": match["match_id"]},
        {"$set": {"status": "forfeited", "winner": opponent_id, "ended_at": time.time()}}
    )
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

    result = users_col.update_one({"user_id": target_id}, {"$inc": {"coins": amount}})
    if result.matched_count:
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
  

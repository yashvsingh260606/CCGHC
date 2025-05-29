# PART 1: Imports, Config, JSON Utilities, User Registration & Profile

import os
import json
import logging
import asyncio
import random
import time
from typing import List, Dict, Any, Optional

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, Chat
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
INACTIVITY_TIMEOUT = 20 * 60  # 20 minutes in seconds

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
# PART 2: /pm Command, Join Button, Match Creation & Multiple Matches

def get_new_match_id(user_id, chat_id):
    return f"{int(time.time())}_{user_id}_{chat_id}_{random.randint(1000,9999)}"

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # Only allow in groups
    if chat.type == "private":
        await update.message.reply_text("❌ /pm can only be used in groups!")
        return

    # Generate a unique match_id (timestamp + user_id + chat_id + random)
    match_id = get_new_match_id(user.id, chat.id)

    matches = get_matches()
    matches[match_id] = {
        "match_id": match_id,
        "chat_id": chat.id,
        "creator_id": user.id,
        "creator_name": user.full_name,
        "players": [user.id],
        "player_names": [user.full_name],
        "status": "waiting",
        "created_at": time.time(),
        "last_action": time.time(),
        "turn": None,
        "toss": None,
        "innings": 1,
        "scores": {},
        "wickets": {},
        "target": None,
        "logs": []
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
    match["last_action"] = time.time()
    save_matches(matches)

    await query.answer("You joined the match!", show_alert=True)
    player_list = "\n".join(match["player_names"])
    await query.edit_message_text(
        f"🏏 {match['creator_name']} started the match!\nPlayers:\n{player_list}\nClick below to join the game.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Join", callback_data=f"join_{match_id}")]
        ])
    )
# PART 3: Match Flow - Toss, Bat/Bowl, Innings, Switching, End Game

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text.strip().lower()

    matches = get_matches()
    # Find the latest match in this chat where this user is a player and match is not ended
    active_matches = [
        m for m in matches.values()
        if m["chat_id"] == chat.id and user.id in m["players"] and m["status"] in ["waiting", "in_progress"]
    ]
    if not active_matches:
        return  # Ignore unrelated messages

    # Always pick the most recent active match for this user in this chat
    match = sorted(active_matches, key=lambda m: m["created_at"], reverse=True)[0]
    match_id = match["match_id"]

    # Update last action time
    match["last_action"] = time.time()

    # TOSS PHASE
    if match["status"] == "waiting" and len(match["players"]) == 2:
        if not match.get("toss"):
            # Ask both players for "heads" or "tails"
            if "toss_choice" not in match:
                match["toss_choice"] = {}
            if user.id not in match["toss_choice"]:
                if text in ["heads", "tails"]:
                    match["toss_choice"][user.id] = text
                    save_matches(matches)
                    await update.message.reply_text(f"{user.first_name} picked {text} for toss.")
                else:
                    await update.message.reply_text("Toss time! Type 'heads' or 'tails'.")
                    save_matches(matches)
                    return
            # Wait for both
            if len(match["toss_choice"]) < 2:
                save_matches(matches)
                return
            # Both have chosen, do the toss
            toss_result = random.choice(["heads", "tails"])
            p1, p2 = match["players"]
            p1_choice = match["toss_choice"][p1]
            p2_choice = match["toss_choice"][p2]
            if p1_choice == toss_result:
                toss_winner = p1
                toss_loser = p2
            else:
                toss_winner = p2
                toss_loser = p1
            match["toss"] = {
                "result": toss_result,
                "winner": toss_winner,
                "loser": toss_loser
            }
            match["status"] = "in_progress"
            match["turn"] = toss_winner
            match["innings"] = 1
            match["scores"] = {str(p1): 0, str(p2): 0}
            match["wickets"] = {str(p1): 0, str(p2): 0}
            match["logs"].append(f"Toss: {toss_result}. {toss_winner} bats first.")
            save_matches(matches)
            await update.message.reply_text(
                f"Toss result: {toss_result}. <a href='tg://user?id={toss_winner}'>Player</a> bats first!\n"
                "Batting: Send a number (1-6) to bat. Bowler: Send a number (1-6) to bowl.",
                parse_mode="HTML"
            )
            return

    # INNINGS PHASE
    if match["status"] == "in_progress" and len(match["players"]) == 2:
        p1, p2 = match["players"]
        batsman = match["turn"]
        bowler = p2 if batsman == p1 else p1
        # Both must send a number 1-6
        if "current_play" not in match:
            match["current_play"] = {}
        if user.id not in [batsman, bowler]:
            await update.message.reply_text("You're not batting or bowling in this match.")
            save_matches(matches)
            return
        try:
            num = int(text)
            if num < 1 or num > 6:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Send a number between 1 and 6.")
            save_matches(matches)
            return
        match["current_play"][user.id] = num
        # Wait for both
        if len(match["current_play"]) < 2:
            save_matches(matches)
            return
        # Both have played, resolve
        bat_num = match["current_play"][batsman]
        bowl_num = match["current_play"][bowler]
        if bat_num == bowl_num:
            match["wickets"][str(batsman)] += 1
            match["logs"].append(f"OUT! Bat: {bat_num}, Bowl: {bowl_num}")
            await update.message.reply_text(f"OUT! Bat: {bat_num}, Bowl: {bowl_num}")
        else:
            match["scores"][str(batsman)] += bat_num
            match["logs"].append(f"Run! Bat: {bat_num}, Bowl: {bowl_num}")
            await update.message.reply_text(f"Run! Bat: {bat_num}, Bowl: {bowl_num}")
        match["current_play"] = {}
        # Check for innings end
        if match["wickets"][str(batsman)] >= 2:  # 2 wickets per innings
            if match["innings"] == 1:
                match["innings"] = 2
                match["turn"] = bowler
                match["target"] = match["scores"][str(batsman)] + 1
                await update.message.reply_text(
                    f"Innings over! Target for next player: {match['target']} runs. Switch roles!"
                )
                match["logs"].append(f"Innings over. Target: {match['target']}")
            else:
                # End game, decide winner
                score1 = match["scores"][str(p1)]
                score2 = match["scores"][str(p2)]
                if score1 > score2:
                    winner = p1
                    loser = p2
                elif score2 > score1:
                    winner = p2
                    loser = p1
                else:
                    winner = None
                    loser = None
                match["status"] = "ended"
                match["ended_at"] = time.time()
                users = get_users()
                if winner:
                    users[str(winner)]["wins"] += 1
                    users[str(loser)]["losses"] += 1
                    await update.message.reply_text(
                        f"🏆 <a href='tg://user?id={winner}'>Player</a> wins the match!\n"
                        f"Scores: {score1} - {score2}",
                        parse_mode="HTML"
                    )
                else:
                    await update.message.reply_text(f"Match tied! Scores: {score1} - {score2}")
                save_users(users)
                save_matches(matches)
                return
        save_matches(matches)
        return
# PART 4: Admin /add Command, Inactivity Checker, and Utilities

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

async def inactivity_checker(application):
    while True:
        matches = get_matches()
        users = get_users()
        now = time.time()
        changed = False
        for match_id, match in list(matches.items()):
            if match["status"] in ["ended", "forfeited"]:
                continue
            if now - match.get("last_action", now) > INACTIVITY_TIMEOUT:
                # Find which player's turn it is
                if match["status"] == "waiting":
                    # Cancel match, no win/loss
                    match["status"] = "ended"
                    match["ended_at"] = now
                    changed = True
                    continue
                batsman = match["turn"]
                bowler = [p for p in match["players"] if p != batsman][0]
                # The player who didn't act loses
                loser = batsman
                winner = bowler
                match["status"] = "ended"
                match["ended_at"] = now
                if str(winner) in users:
                    users[str(winner)]["wins"] += 1
                if str(loser) in users:
                    users[str(loser)]["losses"] += 1
                changed = True
        if changed:
            save_matches(matches)
            save_users(users)
        await asyncio.sleep(60)
# PART 5: Main Function, Handlers, and Application Setup

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("pm", pm_command))
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
    # Message handler for match flow (toss, bat, bowl, etc.)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start inactivity checker
    loop = asyncio.get_event_loop()
    loop.create_task(inactivity_checker(application))

    print("HandCricket CCG Bot is running...")
    await application.run_polling()

if __name__ == "__main__":
    import sys
    import asyncio

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise

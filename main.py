import json
import random
import os
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- SET YOUR BOT TOKEN HERE ---
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# --- ADMIN USER IDS FOR /add COMMAND ---
ADMINS = [123456789]  # Replace with your Telegram user IDs

# --- FILE PATHS ---
USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

# --- LOAD/ SAVE USER DATA ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

# --- LOAD / SAVE MATCH DATA ---
def load_matches():
    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_matches():
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f)

# --- GLOBAL DATA ---
users = load_users()     # user_id(str) -> user data dict
matches = load_matches() # match_id(str) -> match data dict

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {
            "name": update.effective_user.first_name,
            "coins": 4000,
            "wins": 0,
            "losses": 0,
            "last_daily": None,
            "in_match": None,
        }
        save_users()
    text = (
        f"**Welcome {update.effective_user.first_name}!**\n\n"
        "Use /help to see all commands.\n"
        "You start with 4000 coins."
    )
    await update.message.reply_text(text)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in users:
        await update.message.reply_text("You are already registered.")
        return
    users[user_id] = {
        "name": update.effective_user.first_name,
        "coins": 4000,
        "wins": 0,
        "losses": 0,
        "last_daily": None,
        "in_match": None,
    }
    save_users()
    await update.message.reply_text(
        f"Registered! You received 4000 coins, {update.effective_user.first_name}."
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        await update.message.reply_text("You are not registered. Use /register.")
        return
    last_daily = users[user_id].get("last_daily")
    now = datetime.utcnow()
    if last_daily:
        last = datetime.fromisoformat(last_daily)
        if now - last < timedelta(hours=24):
            await update.message.reply_text(
                "You have already claimed daily coins in the last 24 hours."
            )
            return
    users[user_id]["coins"] += 3000
    users[user_id]["last_daily"] = now.isoformat()
    save_users()
    await update.message.reply_text("You received 3000 daily coins!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = [
        "/start - Welcome message",
        "/register - Register and get 4000 coins",
        "/daily - Get 3000 coins once per 24h",
        "/pm - Play a match",
        "/leaderboard - Top players by wins",
        "/profile - Show your profile",
    ]
    help_text = "**Available Commands:**\n" + "\n".join(commands)
    await update.message.reply_text(help_text)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        await update.message.reply_text("You are not registered. Use /register.")
        return
    u = users[user_id]
    text = (
        f"**{u['name']}'s Profile**\n\n"
        f"**Name:** {u['name']}\n"
        f"**ID:** {user_id}\n"
        f"**Purse:** {u['coins']} coins\n"
        f"**Wins:** {u['wins']}\n"
        f"**Losses:** {u['losses']}"
    )
    await update.message.reply_text(text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not users:
        await update.message.reply_text("No players registered yet.")
        return
    sorted_users = sorted(users.values(), key=lambda x: x.get("wins", 0), reverse=True)
    text = "**🏆 Leaderboard (Top 10 by Wins) 🏆**\n\n"
    for i, u in enumerate(sorted_users[:10], start=1):
        text += f"{i}. {u['name']} - Wins: {u.get('wins',0)}\n"
    await update.message.reply_text(text)

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    target_id, coins = args[0], args[1]
    if target_id not in users:
        await update.message.reply_text("User not found.")
        return
    try:
        coins = int(coins)
        if coins <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Coins must be a positive integer.")
        return
    users[target_id]["coins"] += coins
    save_users()
    await update.message.reply_text(
        f"Added {coins} coins to {users[target_id]['name']} (ID: {target_id})."
    )

# --- PvP Match Setup and Gameplay ---

def get_bat_bowl_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("1", callback_data="num_1"),
            InlineKeyboardButton("2", callback_data="num_2"),
            InlineKeyboardButton("3", callback_data="num_3"),
        ],
        [
            InlineKeyboardButton("4", callback_data="num_4"),
            InlineKeyboardButton("5", callback_data="num_5"),
            InlineKeyboardButton("6", callback_data="num_6"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        await update.message.reply_text("Register first with /register.")
        return

    if users[user_id].get("in_match"):
        await update.message.reply_text("You are already in a match.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /pm <opponent_user_id>")
        return

    opponent_id = context.args[0]
    if opponent_id == user_id:
        await update.message.reply_text("You can't play with yourself.")
        return

    if opponent_id not in users:
        await update.message.reply_text("Opponent not found or not registered.")
        return

    if users[opponent_id].get("in_match"):
        await update.message.reply_text("Opponent is already in a match.")
        return

    match_id = "_".join(sorted([user_id, opponent_id]))

    if match_id in matches:
        await update.message.reply_text("A match between you two is already ongoing.")
        return

    stake = 1000
    if users[user_id]["coins"] < stake or users[opponent_id]["coins"] < stake:
        await update.message.reply_text("Both players need at least 1000 coins to play.")
        return

    users[user_id]["coins"] -= stake
    users[opponent_id]["coins"] -= stake

    matches[match_id] = {
        "p1_id": user_id,
        "p1_name": users[user_id]["name"],
        "p2_id": opponent_id,
        "p2_name": users[opponent_id]["name"],
        "status": "toss",
        "toss_winner": None,
        "toss_choice": None,
        "batting": None,
        "bowling": None,
        "innings": 1,
        "runs": 0,
        "balls": 0,
        "target": 0,
        "message_id": None,
        "chat_id": update.effective_chat.id,
        "bat_input": None,
        "bowl_input": None,
    }
    users[user_id]["in_match"] = match_id
    users[opponent_id]["in_match"] = match_id
    save_users()
    save_matches()

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Heads", callback_data="toss_heads"),
                InlineKeyboardButton("Tails", callback_data="toss_tails"),
            ]
        ]
    )
    msg = await update.message.reply_text(
        f"Match started between **{users[user_id]['name']}** and **{users[opponent_id]['name']}**!\n\n"
        f"**{users[user_id]['name']}**, call the toss: Heads or Tails?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    matches[match_id]["message_id"] = msg.message_id
    save_matches()
# Part 2 - Callback Query Handler and Game Logic
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    data = query.data

    # Find the match for this user
    match = None
    for m_id, m in matches.items():
        if m["p1_id"] == user_id or m["p2_id"] == user_id:
            match = m
            match_id = m_id
            break
    if not match:
        await query.answer("You are not in a match.")
        return

    # Handle toss choice
    if match["status"] == "toss":
        if data not in ["toss_heads", "toss_tails"]:
            await query.answer()
            return
        # Only player 1 can call toss (the one who started /pm)
        if user_id != match["p1_id"]:
            await query.answer("Only the challenger can call the toss.")
            return

        call = "heads" if data == "toss_heads" else "tails"
        toss_result = random.choice(["heads", "tails"])
        await query.answer()
        text = f"**Toss call:** {call.capitalize()}\n**Toss result:** {toss_result.capitalize()}\n"
        if call == toss_result:
            match["toss_winner"] = match["p1_id"]
            winner_name = match["p1_name"]
            loser_id = match["p2_id"]
            loser_name = match["p2_name"]
        else:
            match["toss_winner"] = match["p2_id"]
            winner_name = match["p2_name"]
            loser_id = match["p1_id"]
            loser_name = match["p1_name"]

        match["status"] = "toss_choice"
        save_matches()

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Bat", callback_data="choose_bat"),
                    InlineKeyboardButton("Bowl", callback_data="choose_bowl"),
                ]
            ]
        )
        msg = f"{text}\n**{winner_name} won the toss!**\nChoose to Bat or Bowl first."
        await query.edit_message_text(
            msg, reply_markup=keyboard, parse_mode="Markdown"
        )
        return

    # Handle toss winner choosing bat or bowl
    if match["status"] == "toss_choice":
        if user_id != match["toss_winner"]:
            await query.answer("Waiting for toss winner to choose.")
            return
        if data not in ["choose_bat", "choose_bowl"]:
            await query.answer()
            return
        await query.answer()
        choice = "bat" if data == "choose_bat" else "bowl"
        match["batting"] = match["toss_winner"] if choice == "bat" else (
            match["p1_id"] if match["toss_winner"] == match["p2_id"] else match["p2_id"]
        )
        match["bowling"] = match["p1_id"] if match["batting"] == match["p2_id"] else match["p2_id"]
        match["status"] = "batting"
        match["innings"] = 1
        match["runs"] = 0
        match["balls"] = 0
        match["target"] = 0
        match["bat_input"] = None
        match["bowl_input"] = None
        save_matches()

        bat_name = users[match["batting"]]["name"]
        bowl_name = users[match["bowling"]]["name"]

        text = (
            f"**Innings 1:**\n"
            f"**{bat_name}** is batting.\n"
            f"**{bowl_name}** is bowling.\n\n"
            f"{bat_name}, choose your number:"
        )
        await query.edit_message_text(
            text,
            reply_markup=get_bat_bowl_keyboard(),
            parse_mode="Markdown"
        )
        return

    # Handle batting/bowling input during the match
    if match["status"] == "batting":
        # Only batting or bowling player can choose number
        if user_id != match["batting"] and user_id != match["bowling"]:
            await query.answer("You are not playing right now.")
            return
        if not data.startswith("num_"):
            await query.answer()
            return
        num = int(data.split("_")[1])
        await query.answer()

        # Record the input
        if user_id == match["batting"]:
            if match["bat_input"] is not None:
                await query.answer("You have already chosen your number.")
                return
            match["bat_input"] = num
            bat_name = users[user_id]["name"]
            bowl_name = users[match["bowling"]]["name"]
            await query.edit_message_text(
                f"**{bat_name}** chose a number.\nNow, **{bowl_name}**'s turn to bowl.",
                reply_markup=None,
                parse_mode="Markdown"
            )
        elif user_id == match["bowling"]:
            if match["bowl_input"] is not None:
                await query.answer("You have already chosen your number.")
                return
            match["bowl_input"] = num

        # Once both inputs are collected, process the ball
        if match["bat_input"] is not None and match["bowl_input"] is not None:
            bat_num = match["bat_input"]
            bowl_num = match["bowl_input"]
            match["balls"] += 1
            text = f"**Ball {match['balls']}**\n"
            bat_name = users[match["batting"]]["name"]
            bowl_name = users[match["bowling"]]["name"]

            if bat_num == bowl_num:
                text += f"{bat_name} chose {bat_num}, {bowl_name} chose {bowl_num}.\n"
                text += "**WICKET!**\n"
                # Handle innings change or match end
                if match["innings"] == 1:
                    match["target"] = match["runs"] + 1
                    match["runs"] = 0
                    match["balls"] = 0
                    match["innings"] = 2
                    # Swap batting and bowling
                    match["batting"], match["bowling"] = match["bowling"], match["batting"]
                    text += (
                        f"\nInnings 1 over. Target for second innings: {match['target']} runs.\n"
                        f"**Innings 2 started.**\n"
                        f"**{users[match['batting']]['name']}** is batting now.\n"
                        f"Choose your number:"
                    )
                    match["bat_input"] = None
                    match["bowl_input"] = None
                    save_matches()
                    await query.edit_message_text(text, reply_markup=get_bat_bowl_keyboard(), parse_mode="Markdown")
                    return
                else:
                    # Innings 2 wicket means match over
                    if match["runs"] >= match["target"]:
                        # batting player won before wicket
                        winner = users[match["batting"]]["name"]
                        loser_id = match["bowling"]
                    else:
                        winner = users[match["bowling"]]["name"]
                        loser_id = match["batting"]

                    # Update wins/losses
                    winner_id = match["batting"] if winner == users[match["batting"]]["name"] else match["bowling"]
                    users[winner_id]["wins"] += 1
                    users[loser_id]["losses"] += 1

                    text += f"\nMatch Over!\n**{winner}** won the match!\n"
                    users[match["p1_id"]]["in_match"] = None
                    users[match["p2_id"]]["in_match"] = None

                    save_users()
                    del matches[match_id]
                    save_matches()
                    await query.edit_message_text(text, reply_markup=None, parse_mode="Markdown")
                    return
            else:
                match["runs"] += bat_num
                text += (
                    f"{bat_name} chose {bat_num}, {bowl_name} chose {bowl_num}.\n"
                    f"Runs scored: {match['runs']} / Balls: {match['balls']}\n"
                )
                # Check if in 2nd innings target is reached
                if match["innings"] == 2 and match["runs"] >= match["target"]:
                    text += f"\n**{bat_name} reached the target and won the match!**"
                    users[match["batting"]]["wins"] += 1
                    users[match["bowling"]]["losses"] += 1
                    users[match["p1_id"]]["in_match"] = None
                    users[match["p2_id"]]["in_match"] = None
                    save_users()
                    del matches[match_id]
                    save_matches()
                    await query.edit_message_text(text, reply_markup=None, parse_mode="Markdown")
                    return
                else:
                    text += f"\n{bat_name}, choose your next number:"
                    match["bat_input"] = None
                    match["bowl_input"] = None
                    save_matches()
                    await query.edit_message_text(text, reply_markup=get_bat_bowl_keyboard(), parse_mode="Markdown")
                    return

    # If unknown state
    await query.answer("Invalid action or not your turn.")

def main():
    app = Application.builder
from telegram.ext import ApplicationBuilder

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("pm", pm))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot started...")
    await app.run_polling()

import asyncio
asyncio.run(main())

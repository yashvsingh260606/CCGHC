# Part 1/2 — Hand Cricket Bot (Token + Commands + Match Start/Join)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # <----- Put your bot token here

import logging
import json
import os
import time
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    CallbackQueryHandler
)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATA_FILE = "handcricket_data.json"
ADMINS = [123456789]  # <-- Put your Telegram user IDs here

# Load or init data
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
else:
    data = {"users": {}, "matches": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def get_user(uid):
    uid = str(uid)
    if uid not in data["users"]:
        data["users"][uid] = {"coins": 1000, "wins": 0, "last_daily": 0}
        save_data()
    return data["users"][uid]

def create_join_button(match_id):
    keyboard = [[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]]
    return InlineKeyboardMarkup(keyboard)

def create_number_buttons():
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1,4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4,7)],
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_match_id():
    return str(int(time.time() * 1000))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id)
    cmds = (
        "/start - Welcome message\n"
        "/pm [bet] - Start or join a match, bet optional\n"
        "/profile - Show your coins and wins\n"
        "/daily - Claim 500 coins once daily\n"
        "/leaderboard - Top players by coins\n"
        "/help - List commands\n"
        "/add <user_id> <coins> - Admin command\n"
    )
    await update.message.reply_text(f"Welcome to Hand Cricket!\n\nCommands:\n{cmds}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    text = f"Your Profile:\nCoins: {user['coins']}\nWins: {user['wins']}"
    await update.message.reply_text(text)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    now = int(time.time())
    if now - user['last_daily'] < 86400:
        await update.message.reply_text("You can claim daily coins only once every 24 hours.")
        return
    user['coins'] += 500
    user['last_daily'] = now
    save_data()
    await update.message.reply_text("You claimed 500 daily coins!")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = data["users"]
    top = sorted(users.items(), key=lambda x: x[1]['coins'], reverse=True)[:10]
    text = "🏆 Top Players by Coins:\n"
    for i, (uid, u) in enumerate(top, start=1):
        text += f"{i}. User {uid}: {u['coins']} coins\n"
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmds = (
        "/start\n/pm [bet]\n/profile\n/daily\n/leaderboard\n/help\n/add <user_id> <coins>"
    )
    await update.message.reply_text(f"Commands:\n{cmds}")

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMINS:
        await update.message.reply_text("You are not authorized to use this.")
        return
    try:
        target_id = context.args[0]
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    target = get_user(target_id)
    target['coins'] += amount
    save_data()
    await update.message.reply_text(f"Added {amount} coins to user {target_id}.")

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid bet amount.")
            return
    if bet > user['coins']:
        await update.message.reply_text("You don't have enough coins for that bet.")
        return

    # Check if user already in a match
    for m in data["matches"].values():
        if uid in [m['player1_id'], m.get('player2_id', '')]:
            await update.message.reply_text("You already joined a game!")
            return

    match_id = generate_match_id()
    match = {
        'id': match_id,
        'player1_id': uid,
        'player1_name': update.effective_user.first_name,
        'player2_id': None,
        'player2_name': None,
        'bet': bet,
        'status': 'waiting',  # waiting for player2 to join
        'toss_winner_id': None,
        'toss_winner_name': None,
        'toss_choice': None,
        'batting_id': None,
        'batting_name': None,
        'bowling_id': None,
        'bowling_name': None,
        'innings': 1,
        'runs': 0,
        'wickets': 0,
        'balls': 0,
        'target': 0,
        'balls_left': 36,  # 6 overs max
        'bat_num': None,
        'bowl_num': None,
        'waiting_for': None,  # 'bat' or 'bowl'
        'message_id': None,
        'chat_id': update.effective_chat.id,
    }
    data["matches"][match_id] = match
    save_data()

    join_btn = create_join_button(match_id)
    sent = await update.message.reply_text(
        f"Match created by {match['player1_name']}.\nBet: {bet} coins\n\nWaiting for opponent to join.",
        reply_markup=join_btn,
    )
    match['message_id'] = sent.message_id
    save_data()

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    user = get_user(uid)
    await query.answer()

    match_id = query.data.split("_")[1]
    match = data["matches"].get(match_id)
    if not match:
        await query.edit_message_text("This match no longer exists.")
        return

    if match['player2_id']:
        await query.answer("Match already has two players.", show_alert=True)
        return

    if match['player1_id'] == uid:
        await query.answer("You cannot join your own match.", show_alert=True)
        return

    if match['bet'] > user['coins']:
        await query.answer("You don't have enough coins for this match bet.", show_alert=True)
        return

    # Check if user already in another match
    for m in data["matches"].values():
        if uid in [m['player1_id'], m.get('player2_id', '')]:
            await query.answer("You already joined a game!", show_alert=True)
            return

    # Assign player2 and start the match
    match['player2_id'] = uid
    match['player2_name'] = query.from_user.first_name
    match['status'] = 'started'

    # Determine toss winner randomly
    import random
    toss_winner = random.choice([match['player1_id'], match['player2_id']])
    match['toss_winner_id'] = toss_winner
    match['toss_winner_name'] = (
        match['player1_name'] if toss_winner == match['player1_id'] else match['player2_name']
    )
    # Toss winner chooses bat or bowl next (we will ask in message)
    match['waiting_for'] = 'toss_choice'

    await query.edit_message_text(
        f"Match started!\nToss winner: {match['toss_winner_name']}.\n"
        f"{match['toss_winner_name']}, please choose:\n\n"
        "Batting or Bowling?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Bat", callback_data="toss_bat")],
            [InlineKeyboardButton("Bowl", callback_data="toss_bowl")]
        ])
    )
    save_data()

# Remaining handlers (toss choice, batting/bowling picks, number selection, scoring, innings switching, match end)
# ... (Part 2 will have this to keep Part 1 under manageable size)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("pm", pm_command))
    app.add_handler(CallbackQueryHandler(join_callback, pattern=r"^join_"))

    # The rest of CallbackQueryHandlers for game play will be added in Part 2

    app.run_polling()

if __name__ == "__main__":
    main()
# Part 2/2 — Gameplay handlers

from telegram import InlineKeyboardMarkup, InlineKeyboardButton

import random

# Use global `data` and `save_data()` from Part 1

async def toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(query.from_user.id)
    data_loaded = data
    await query.answer()

    match = None
    for m in data["matches"].values():
        if m['toss_winner_id'] == uid and m['waiting_for'] == 'toss_choice':
            match = m
            break
    if not match:
        await query.answer("No toss to choose.")
        return

    choice = query.data.split("_")[1]  # 'bat' or 'bowl'
    match['toss_choice'] = choice
    # Assign batting and bowling based on choice
    if choice == 'bat':
        match['batting_id'] = match['toss_winner_id']
        match['batting_name'] = match['toss_winner_name']
        other_id = match['player1_id'] if match['player2_id'] == match['toss_winner_id'] else match['player2_id']
        other_name = match['player1_name'] if match['player2_id'] == match['toss_winner_id'] else match['player2_name']
        match['bowling_id'] = other_id
        match['bowling_name'] = other_name
    else:
        # Toss winner bowls first
        match['bowling_id'] = match['toss_winner_id']
        match['bowling_name'] = match['toss_winner_name']
        other_id = match['player1_id'] if match['player2_id'] == match['toss_winner_id'] else match['player2_id']
        other_name = match['player1_name'] if match['player2_id'] == match['toss_winner_id'] else match['player2_name']
        match['batting_id'] = other_id
        match['batting_name'] = other_name

    match['waiting_for'] = 'bat'  # batsman picks first number
    chat_id = match['chat_id']
    message_id = match['message_id']

    # Show message for batsman to choose number
    msg = (
        f"1st Innings Started!\nBatsman: {match['batting_name']}\n"
        f"Bowler: {match['bowling_name']}\n\n"
        f"{match['batting_name']}, select your number."
    )
    keyboard = create_number_buttons()

    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=message_id, text=msg, reply_markup=keyboard
    )
    save_data()

import logging
import json
import os
import random
import time
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
)
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext, Filters
)

# ====== SET YOUR BOT TOKEN AND ADMINS HERE ======
BOT_TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo'  # Replace with your bot token
ADMINS = [123456789]  # Replace with your Telegram user IDs as admins

# ====== SETUP LOGGING ======
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====== DATA FILE PATHS ======
USERS_FILE = 'users.json'
MATCHES_FILE = 'matches.json'

# ====== GLOBAL VARIABLES ======
users = {}
matches = {}

# ====== HELPER FUNCTIONS FOR DATA PERSISTENCE ======
def load_data():
    global users, matches
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
    else:
        users = {}

    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, 'r') as f:
            matches = json.load(f)
    else:
        matches = {}

def save_data():
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)
    with open(MATCHES_FILE, 'w') as f:
        json.dump(matches, f)

# ====== USER MANAGEMENT ======
def register_user(user_id, username):
    user_id = str(user_id)
    if user_id not in users:
        users[user_id] = {
            'username': username,
            'coins': 1000,
            'wins': 0,
            'last_daily': None,
        }
        save_data()

def is_admin(user_id):
    return user_id in ADMINS

# ====== COMMAND HANDLERS ======
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    register_user(user.id, user.username or user.first_name)
    text = (
        f"Welcome {user.first_name}! This is the Hand Cricket Bot.\n\n"
        "Use /help to see available commands."
    )
    update.message.reply_text(text)

def help_command(update: Update, context: CallbackContext):
    text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/pm <bet> - Start or join a PvP match (bet optional)\n"
        "/profile - Show your stats\n"
        "/daily - Claim daily coins\n"
        "/leaderboard - Show top players\n"
        "/help - Show this help message\n"
        "/add <user_id> <coins> - Admin only: Add coins to user"
    )
    update.message.reply_text(text)
# ====== PROFILE & DAILY ======
def profile(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        register_user(update.effective_user.id, update.effective_user.username or update.effective_user.first_name)
    user = users[user_id]
    text = (
        f"Profile of {update.effective_user.first_name}:\n"
        f"Coins: {user['coins']}\n"
        f"Wins: {user['wins']}"
    )
    update.message.reply_text(text)

def daily(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    now = datetime.utcnow()
    if user_id not in users:
        register_user(update.effective_user.id, update.effective_user.username or update.effective_user.first_name)
    user = users[user_id]

    last_daily = user['last_daily']
    if last_daily:
        last_claim = datetime.strptime(last_daily, '%Y-%m-%dT%H:%M:%S')
        if now < last_claim + timedelta(hours=24):
            next_time = last_claim + timedelta(hours=24)
            diff = next_time - now
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            update.message.reply_text(
                f"You have already claimed your daily coins. Try again in {hours}h {minutes}m."
            )
            return

    reward = 500
    user['coins'] += reward
    user['last_daily'] = now.strftime('%Y-%m-%dT%H:%M:%S')
    save_data()
    update.message.reply_text(f"You claimed {reward} coins as daily reward!")

# ====== ADMIN COMMAND: ADD COINS ======
def add_coins(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        update.message.reply_text("Usage: /add <user_id> <coins>")
        return

    target_id, amount = args
    if target_id not in users:
        update.message.reply_text("User ID not found.")
        return

    try:
        amount = int(amount)
    except ValueError:
        update.message.reply_text("Coins must be a number.")
        return

    users[target_id]['coins'] += amount
    save_data()
    update.message.reply_text(f"Added {amount} coins to user {target_id}.")

# ====== LEADERBOARD ======
def leaderboard(update: Update, context: CallbackContext):
    # Sort users by coins descending
    sorted_users = sorted(users.items(), key=lambda x: x[1]['coins'], reverse=True)[:10]
    lines = []
    for i, (uid, data) in enumerate(sorted_users, 1):
        name = data.get('username') or "Unknown"
        coins = data.get('coins', 0)
        wins = data.get('wins', 0)
        lines.append(f"{i}. {name} — Coins: {coins} | Wins: {wins}")
    text = "🏆 Top Players:\n" + "\n".join(lines)
    update.message.reply_text(text)
# ====== MATCH MANAGEMENT ======

def start_match(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    args = context.args

    if user_id not in users:
        register_user(update.effective_user.id, update.effective_user.username or update.effective_user.first_name)

    bet = 0
    if args:
        try:
            bet = int(args[0])
            if bet < 0:
                update.message.reply_text("Bet must be positive.")
                return
            if users[user_id]['coins'] < bet:
                update.message.reply_text("You don't have enough coins for that bet.")
                return
        except ValueError:
            update.message.reply_text("Usage: /pm <bet>")
            return

    if user_id in active_matches:
        update.message.reply_text("You are already in a match.")
        return

    # Create a match object with player1 = current user, no player2 yet
    match_id = str(update.message.message_id) + user_id
    match = {
        'player1': user_id,
        'player2': None,
        'bet': bet,
        'state': 'waiting',  # waiting for second player to join
        'message_id': None,
        'chat_id': update.effective_chat.id,
        'player1_name': update.effective_user.first_name,
        'player2_name': None,
        'player1_choice': None,
        'player2_choice': None,
        'innings': 1,
        'scores': {user_id: 0},
        'wickets': {user_id: 0},
        'current_batsman': user_id,
        'current_bowler': None,
        'toss_winner': None,
        'target': None,
    }
    matches[match_id] = match
    active_matches[user_id] = match_id

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]])
    sent_msg = update.message.reply_text(
        f"Match created by {match['player1_name']} with bet {bet} coins.\nWaiting for opponent to join.",
        reply_markup=keyboard
    )
    match['message_id'] = sent_msg.message_id

def join_match(update: Update, context: CallbackContext, match_id):
    user_id = str(update.effective_user.id)
    match = matches.get(match_id)
    if not match:
        update.callback_query.answer("Match not found or expired.")
        return

    if match['player2']:
        update.callback_query.answer("Match already has two players.")
        return

    if user_id == match['player1']:
        update.callback_query.answer("You can't join your own match.")
        return

    if user_id in active_matches:
        update.callback_query.answer("You are already in a match.")
        return

    # Check if player has enough coins for the bet
    if users[user_id]['coins'] < match['bet']:
        update.callback_query.answer("You don't have enough coins to join this match.")
        return

    match['player2'] = user_id
    match['player2_name'] = update.effective_user.first_name
    match['scores'][user_id] = 0
    match['wickets'][user_id] = 0
    match['current_bowler'] = user_id
    active_matches[user_id] = match_id
    match['state'] = 'toss'

    # Deduct bet coins from both players if bet > 0
    if match['bet'] > 0:
        users[match['player1']]['coins'] -= match['bet']
        users[match['player2']]['coins'] -= match['bet']

    save_data()

    # Update message to show toss options
    buttons = [
        [InlineKeyboardButton("Heads", callback_data=f"toss_H_{match_id}"),
         InlineKeyboardButton("Tails", callback_data=f"toss_T_{match_id}")]
    ]
    context.bot.edit_message_text(
        chat_id=match['chat_id'],
        message_id=match['message_id'],
        text=f"Match started between {match['player1_name']} and {match['player2_name']}!\n"
             f"{match['player1_name']}, choose Heads or Tails for the toss:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    update.callback_query.answer("You joined the match!")

def handle_toss(update: Update, context: CallbackContext, toss_choice, match_id):
    match = matches.get(match_id)
    if not match:
        update.callback_query.answer("Match not found or expired.")
        return

    user_id = str(update.effective_user.id)
    if match['state'] != 'toss':
        update.callback_query.answer("Toss already done.")
        return

    if user_id != match['player1']:
        update.callback_query.answer("Only player1 can choose toss.")
        return

    toss_result = random.choice(['H', 'T'])
    if toss_choice == toss_result:
        match['toss_winner'] = user_id
        winner_name = match['player1_name']
    else:
        match['toss_winner'] = match['player2']
        winner_name = match['player2_name']

    match['state'] = 'bat_or_bowl'

    buttons = [
        [InlineKeyboardButton("Bat", callback_data=f"bat_{match_id}"),
         InlineKeyboardButton("Bowl", callback_data=f"bowl_{match_id}")]
    ]

    context.bot.edit_message_text(
        chat_id=match['chat_id'],
        message_id=match['message_id'],
        text=(f"Toss result: {'Heads' if toss_result == 'H' else 'Tails'}\n"
              f"{winner_name} won the toss! Choose to Bat or Bowl:"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    update.callback_query.answer()

def handle_bat_or_bowl(update: Update, context: CallbackContext, choice, match_id):
    match = matches.get(match_id)
    if not match:
        update.callback_query.answer("Match not found or expired.")
        return

    if match['state'] != 'bat_or_bowl':
        update.callback_query.answer("Already chosen.")
        return

    winner = match['toss_winner']
    user_id = str(update.effective_user.id)
    if user_id != winner:
        update.callback_query.answer("Only toss winner can choose.")
        return

    if choice == 'bat':
        match['current_batsman'] = winner
        match['current_bowler'] = match['player2'] if winner == match['player1'] else match['player1']
    else:
        match['current_bowler'] = winner
        match['current_batsman'] = match['player2'] if winner == match['player1'] else match['player1']

    match['state'] = 'inning_1'
    match['innings'] = 1
    match['scores'] = {match['player1']: 0, match['player2']: 0}
    match['wickets'] = {match['player1']: 0, match['player2']: 0}
    match['player1_choice'] = None
    match['player2_choice'] = None

    text = (f"Innings 1 started!\n"
            f"Batsman: {users[match['current_batsman']]['username'] or 'Player'}\n"
            f"Bowler: {users[match['current_bowler']]['username'] or 'Player'}\n"
            f"Choose your number:")

    buttons = [
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in [1,2,3]],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in [4,5,6]],
    ]

    context.bot.edit_message_text(
        chat_id=match['chat_id'],
        message_id=match['message_id'],
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    update.callback_query.answer()

def handle_number_choice(update: Update, context: CallbackContext, number, match_id):
    match = matches.get(match_id)
    if not match:
        update.callback_query.answer("Match not found or expired.")
        return

    user_id = str(update.effective_user.id)

    # Determine if user is batsman or bowler
    if user_id not in (match['current_batsman'], match['current_bowler']):
        update.callback_query.answer("You are not playing in this match.")
        return

    # Store the choice
    if user_id == match['current_batsman']:
        if match['player1_choice'] is not None:
            update.callback_query.answer("You already chose.")
            return
        match['player1_choice'] = number
        # After batsman picks, prompt bowler's turn
        bowler_name = users[match['current_bowler']]['username'] or 'Bowler'
        batsman_name = users[user_id]['username'] or 'Batsman'
        text = f"{batsman_name} chose a number, now it's {bowler_name}'s turn."
        buttons = [
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in [1,2,3]],
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in [4,5,6]],
        ]
        context.bot.edit_message_text(
            chat_id=match['chat_id'],
            message_id=match['message_id'],
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        update.callback_query.answer()

    elif user_id == match['current_bowler']:
        if match['player2_choice'] is not None:
            update.callback_query.answer("You already chose.")
            return
        match['player2_choice'] = number

        # Now reveal numbers and update scores
        batsman_num = match['player1_choice']
        bowler_num = match['player2_choice']

        batsman_id = match['current_batsman']
        bowler_id = match['current_bowler']

        text_lines = []

        if batsman_num == bowler_num:
            match['wickets'][batsman_id] += 1
            text_lines.append(
                f"WICKET! {users[batsman_id]['username']} got out! "
                f"Score: {match['scores'][batsman_id]}"
            )
        else:
            match['scores'][batsman_id] += batsman_num
            text_lines.append(
                f"{users[batsman_id]['username']} scored {batsman_num} runs! "
                f"Total: {match['scores'][batsman_id]}"
            )

        # Check for innings or match end
        # Simple example: 6 wickets or 30 balls per innings etc. (not fully implemented here)

        # Reset choices for next ball
        match['player1_choice'] = None
        match['player2_choice'] = None

        # Update message with next batsman/bowler turn info
        text_lines.append("Choose your numbers for the next ball:")

        buttons = [
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in [1,2,3]],
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in [4,5,6]],
        ]

        context.bot.edit_message_text(
            chat_id=match['chat_id'],
            message_id=match['message_id'],
            text="\n".join(text_lines),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        update.callback_query.answer()

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data

    if data.startswith("join_"):
        match_id = data.split("_",1)[1]
        join_match(update, context, match_id)

    elif data.startswith("toss_"):
        parts = data.split("_")
        toss_choice = parts[1]
        match_id = parts[2]
        handle_toss(update, context, toss_choice, match_id)

    elif data.startswith("bat_"):
        match_id = data.split("_",1)[1]
        handle_bat_or_bowl(update, context, 'bat', match_id)

    elif data.startswith("bowl_"):
        match_id = data.split("_",1)[1]
        handle_bat_or_bowl(update, context, 'bowl', match_id)

    elif data.startswith("num_"):
        parts = data.split("_")
        number = int(parts[1])
        match_id = parts[2]
        handle_number_choice(update, context, number, match_id)

# ====== MAIN FUNCTION ======
def main():
    load_data()

    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("register", register))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("leaderboard", leaderboard))
    dp.add_handler(CommandHandler("add", add_coins))
    dp.add_handler(CommandHandler("pm", start_match))

    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

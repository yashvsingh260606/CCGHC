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
BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN_HERE'  # Replace with your bot token
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

# You want me to send the rest? Just ask!
# ====== MATCH MANAGEMENT ======

def pm(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    register_user(user.id, user.username or user.first_name)

    # Parse bet from args
    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if bet < 0:
                bet = 0
        except ValueError:
            bet = 0

    # Check if user has enough coins for bet
    if bet > users[user_id]['coins']:
        update.message.reply_text("You don't have enough coins for that bet.")
        return

    # Look for a waiting match to join
    for match_id, match in matches.items():
        if match['status'] == 'waiting' and match['bet'] == bet and user_id not in match['players']:
            # Join this match
            match['players'].append(user_id)
            match['status'] = 'toss'
            match['turn'] = None
            match['choices'] = {}
            match['scores'] = {match['players'][0]: 0, match['players'][1]: 0}
            match['innings'] = 1
            match['wickets'] = {match['players'][0]: 0, match['players'][1]: 0}
            save_data()

            start_match(update, context, match_id)
            return

    # If no waiting match, create a new one
    match_id = str(int(time.time() * 1000))
    matches[match_id] = {
        'players': [user_id],
        'bet': bet,
        'status': 'waiting',
        'turn': None,
        'choices': {},
        'scores': {},
        'innings': 0,
        'wickets': {},
        'message_id': None,
        'chat_id': update.effective_chat.id,
    }
    save_data()

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]]
    )
    update.message.reply_text(
        f"Match created with bet {bet} coins.\nWaiting for another player to join...",
        reply_markup=keyboard,
    )


def start_match(update: Update, context: CallbackContext, match_id):
    match = matches[match_id]
    chat_id = match['chat_id']

    # Toss: randomly select heads/tails
    match['toss_choice'] = random.choice(['Heads', 'Tails'])
    match['status'] = 'toss_wait'

    text = (
        f"Match started between:\n"
        f"Player 1: {users[match['players'][0]]['username']}\n"
        f"Player 2: {users[match['players'][1]]['username']}\n\n"
        "Toss time! Choose Heads or Tails:"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Heads", callback_data=f"toss_{match_id}_Heads"),
                InlineKeyboardButton("Tails", callback_data=f"toss_{match_id}_Tails"),
            ]
        ]
    )
    sent = context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    match['message_id'] = sent.message_id
    save_data()


def join_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    data = query.data

    if data.startswith("join_"):
        match_id = data.split("_")[1]
        match = matches.get(match_id)

        if not match:
            query.answer("Match not found.")
            return

        if user_id in match['players']:
            query.answer("You are already in this match.")
            return

        if len(match['players']) >= 2:
            query.answer("Match already has two players.")
            return

        if match['status'] != 'waiting':
            query.answer("Match is no longer joinable.")
            return

        # Join match
        match['players'].append(user_id)
        match['status'] = 'toss'
        save_data()

        query.answer("You joined the match!")
        context.bot.delete_message(chat_id=match['chat_id'], message_id=match['message_id'])
        start_match(update, context, match_id)


def toss_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    data = query.data  # format: toss_<match_id>_<choice>
    _, match_id, choice = data.split("_")

    match = matches.get(match_id)
    if not match:
        query.answer("Match not found.")
        return

    if match['status'] != 'toss_wait':
        query.answer("Toss already decided.")
        return

    # Allow only players to toss
    if user_id not in match['players']:
        query.answer("You are not part of this match.")
        return

    # Record player's toss guess
    if 'toss_guesses' not in match:
        match['toss_guesses'] = {}

    if user_id in match['toss_guesses']:
        query.answer("You already guessed.")
        return

    match['toss_guesses'][user_id] = choice
    save_data()

    query.answer(f"You chose {choice}")

    # Once both players have guessed, decide winner
    if len(match['toss_guesses']) == 2:
        real_toss = match['toss_choice']
        p1, p2 = match['players']

        p1_guess = match['toss_guesses'].get(p1)
        p2_guess = match['toss_guesses'].get(p2)

        chat_id = match['chat_id']

        if p1_guess == real_toss and p2_guess == real_toss:
            # Both guessed correctly: random winner
            toss_winner = random.choice(match['players'])
        elif p1_guess == real_toss:
            toss_winner = p1
        elif p2_guess == real_toss:
            toss_winner = p2
        else:
            # Nobody guessed correctly, random winner
            toss_winner = random.choice(match['players'])

        match['toss_winner'] = toss_winner
        match['status'] = 'bat_bowl_choice'
        save_data()

        winner_name = users[toss_winner]['username']
        text = (
            f"Toss result: {real_toss}\n"
            f"{winner_name} won the toss!\n\n"
            "Choose to Bat or Bowl first:"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Bat", callback_data=f"bat_{match_id}"),
                    InlineKeyboardButton("Bowl", callback_data=f"bowl_{match_id}"),
                ]
            ]
        )

        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=match['message_id'],
            text=text,
            reply_markup=keyboard,
        )


def bat_bowl_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    data = query.data  # format: bat_<match_id> or bowl_<match_id>

    choice, match_id = data.split("_")

    match = matches.get(match_id)
    if not match:
        query.answer("Match not found.")
        return

    if match['status'] != 'bat_bowl_choice':
        query.answer("Bat/Bowl already chosen.")
        return

    if user_id != match['toss_winner']:
        query.answer("Only toss winner can choose.")
        return

    if choice == 'bat':
        match['batting'] = match['toss_winner']
        match['bowling'] = [p for p in match['players'] if p != match['toss_winner']][0]
    else:
        match['bowling'] = match['toss_winner']
        match['batting'] = [p for p in match['players'] if p != match['toss_winner']][0]

    match['status'] = 'batting'
    match['innings'] = 1
    match['scores'] = {match['players'][0]: 0, match['players'][1]: 0}
    match['wickets'] = {match['players'][0]: 0, match['players'][1]: 0}
    match['choices'] = {}
    match['overs'] = 0
    match['balls'] = 0
    save_data()

    batting_name = users[match['batting']]['username']
    bowling_name = users[match['bowling']]['username']

    text = (
        f"{batting_name} is batting first.\n"
        f"{bowling_name} is bowling.\n\n"
        f"Over: 0\n"
        f"Score: 0/{match['wickets'][match['batting']]}\n\n"
        f"{batting_name}, choose a number (1-6):"
    )
    keyboard = get_number_buttons()
    context.bot.edit_message_text(
        chat_id=match['chat_id'],
        message_id=match['message_id'],
        text=text,
        reply_markup=keyboard,
    )
    query.answer()


def get_number_buttons():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in [1, 2, 3]],
            [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in [4, 5, 6]],
        ]
    )


def number_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    user_id = str(user.id)
    data = query.data  # format: num_<number>

    number = int(data.split("_")[1])

    # Find the match user is part of and currently batting or bowling turn
    match_id, match = find_active_match_by_user(user_id)
    if not match:
        query.answer("No active match found.")
        return

    if match['status'] != 'batting':
        query.answer("Match not in batting state.")
        return

    # Turn management: batsman chooses first, then bowler
    if 'current_turn' not in match:
        match['current_turn'] = 'batsman'  # 'batsman' or 'bowler'
        match['choices'] = {}

    if user_id == match['batting'] and match['current_turn'] == 'batsman':
        if 'batsman' in match['choices']:
            query.answer("You already chose your number.")
            return
        match['choices']['batsman'] = number
        match['current_turn'] = 'bowler'
        save_data()

        batsman_name = users[match['batting']]['username']
        bowler_name = users[match['bowling']]['username']
        text = f"{batsman_name} chose the number. Now it's {bowler_name}'s turn."
        keyboard = get_number_buttons()
        context.bot.edit_message_text(
            chat_id=match['chat_id'],
            message_id=match['message_id'],
            text=text,
            reply_markup=keyboard,
        )
        query.answer()

    elif user_id == match['bowling'] and match['current_turn'] == 'bowler':
        if 'bowler' in match['choices']:
            query.answer("You already chose your number.")
            return
        match['choices']['bowler'] = number

        # Both choices made, evaluate ball
        batsman_num = match['choices']['batsman']
        bowler_num = match['choices']['bowler']
        batsman_name = users[match['batting']]['username']
        bowler_name = users[match['bowling']]['username']

        # Ball result
        if batsman_num == bowler_num:
            # Wicket
            match['wickets'][match['batting']] += 1
            ball_text = f"WICKET! {batsman_name} got out."
        else:
            # Runs
            match['scores'][match['batting']] += batsman_num
            ball_text = f"{batsman_name} scored {batsman_num} run(s)."

        # Increment ball count
        match['balls'] = match.get('balls', 0) + 1
        if match['balls'] == 6:
            match['overs'] = match.get('overs', 0) + 1
            match['balls'] = 0

        # Prepare score text
        score_text = (
            f"Over: {match['overs']}.{match['balls']}\n"
            f"{batsman_name} vs {bowler_name}\n"
            f"{ball_text}\n"
            f"Score: {match['scores'][match['batting']]}/"
            f"{match['wickets'][match['batting']]}\n"
        )

        # Check innings end conditions
        innings_over = False
        if match['wickets'][match['batting']] >= 10:
            innings_over = True
        if match['innings'] == 2:
            target = match['target']
            if match['scores'][match['batting']] > target:
                innings_over = True

        if innings_over:
            if match['innings'] == 1:
                # Switch innings
                match['innings'] = 2
                match['target'] = match['scores'][match['batting']]
                # Swap batting and bowling
                match['batting'], match['bowling'] = match['bowling'], match['batting']
                match['wickets'] = {match['batting']: 0, match['bowling']: 0}
                match['scores'][match['batting']] = 0
                match['overs'] = 0
                match['balls'] = 0
                match['choices'] = {}
                match['current_turn'] = 'batsman'
                match['status'] = 'batting'

                batting_name = users[match['batting']]['username']
                bowling_name = users[match['bowling']]['username']

                score_text += (
                    f"\nInnings over! Target for {batting_name} is {match['target'] + 1} runs.\n\n"
                    f"{batting_name} is batting now.\n"
                    f"{bowling_name} is bowling.\n"
                    f"{batting_name}, choose a number (1-6):"
                )
                keyboard = get_number_buttons()

                context.bot.edit_message_text(
                    chat_id=match['chat_id'],
                    message_id=match['message_id'],
                    text=score_text,
                    reply_markup=keyboard,
                )
            else:
                # Match over
                p1_score = match['scores'][match['players'][0]]
                p2_score = match['scores'][match['players'][1]]

                if p1_score > p2_score:
                    winner_id = match['players'][0]
                elif p2_score > p1_score:
                    winner_id = match['players'][1]
                else:
                    winner_id = None  # Draw

                if winner_id:
                    winner_name = users[winner_id]['username']
                    users[winner_id]['wins'] += 1
                    if match['bet'] > 0:
                        users[winner_id]['coins'] += match['bet']
                        loser_id = [p for p in match['players'] if p != winner_id][0]
                        users[loser_id]['coins'] -= match['bet']
                    result_text = f"Match Over! {winner_name} won the match!"
                else:
                    result_text = "Match Over! It's a draw!"

                save_data()
                match['status'] = 'finished'

                context.bot.edit_message_text(
                    chat_id=match['chat_id'],
                    message_id=match['message_id'],
                    text=score_text + "\n\n" + result_text,
                )
        else:
            # Continue innings
            match['choices'] = {}
            match['current_turn'] = 'batsman'
            save_data()

            score_text += f"\n{users[match['batting']]['username']}, choose a number (1-6):"
            keyboard = get_number_buttons()

            context.bot.edit_message_text(
                chat_id=match['chat_id'],
                message_id=match['message_id'],
                text=score_text,
                reply_markup=keyboard,
            )

        query.answer()
    else:
        query.answer("It's not your turn.")

def find_active_match_by_user(user_id):
    user_id = str(user_id)
    for match_id, match in matches.items():
        if match['status'] == 'batting' and user_id in match['players']:
            return match_id, match
    return None, None

# ====== /profile COMMAND ======
def profile(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    register_user(user.id, user.username or user.first_name)
    user_data = users[user_id]

    text = (
        f"Profile for {user.username or user.first_name}:\n"
        f"Coins: {user_data['coins']}\n"
        f"Wins: {user_data['wins']}"
    )
    update.message.reply_text(text)

# ====== /daily COMMAND ======
def daily(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    register_user(user.id, user.username or user.first_name)
    user_data = users[user_id]

    now = datetime.utcnow()
    last_daily_str = user_data.get('last_daily')
    if last_daily_str:
        last_daily = datetime.strptime(last_daily_str, "%Y-%m-%dT%H:%M:%S")
        if now - last_daily < timedelta(hours=24):
            next_time = last_daily + timedelta(hours=24)
            remaining = next_time - now
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            update.message.reply_text(
                f"You have already claimed daily coins. Try again in {hours}h {minutes}m."
            )
            return

    user_data['coins'] += 100
    user_data['last_daily'] = now.strftime("%Y-%m-%dT%H:%M:%S")
    save_data()
    update.message.reply_text("You claimed 100 daily coins!")

# ====== /leaderboard COMMAND ======

def leaderboard(update, context):
    users_sorted = sorted(users.items(), key=lambda x: x[1].get('coins', 0), reverse=True)
    top_users = users_sorted[:10]

    text = "🏆 Leaderboard - Top 10 Users by Coins 🏆\n\n"
    for i, (user_id, user_data) in enumerate(top_users, start=1):
        username = user_data.get('username', 'Unknown')
        coins = user_data.get('coins', 0)
        text += f"{i}. {username} - {coins} coins\n"

    update.message.reply_text(text)


def daily(update, context):
    user_id = str(update.message.from_user.id)
    now = time.time()
    last_claim = users.get(user_id, {}).get('last_daily', 0)

    if now - last_claim >= 86400:  # 24 hours
        coins = users[user_id].get('coins', 0)
        daily_coins = 100
        users[user_id]['coins'] = coins + daily_coins
        users[user_id]['last_daily'] = now
        save_data()
        update.message.reply_text(f"You claimed your daily {daily_coins} coins!")
    else:
        remaining = int((86400 - (now - last_claim)) / 3600)
        update.message.reply_text(f"Daily already claimed! Try again in {remaining} hours.")


def help_command(update, context):
    text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/pm <bet> - Start or join a PvP match (optional bet)\n"
        "/profile - Show your profile\n"
        "/daily - Claim daily coins\n"
        "/leaderboard - Show top users\n"
        "/help - This help message\n"
        "/add <user_id> <coins> - Admin only: Add coins to a user"
    )
    update.message.reply_text(text)


def add_coins(update, context):
    user_id = str(update.message.from_user.id)
    if user_id not in ADMINS:
        update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) != 2:
        update.message.reply_text("Usage: /add <user_id> <coins>")
        return

    target_id, coins_str = context.args
    if target_id not in users:
        update.message.reply_text("User not found.")
        return

    try:
        coins = int(coins_str)
    except ValueError:
        update.message.reply_text("Coins must be a number.")
        return

    users[target_id]['coins'] = users[target_id].get('coins', 0) + coins
    save_data()
    update.message.reply_text(f"Added {coins} coins to user {users[target_id].get('username', 'Unknown')}.")


def main():
    global updater
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('profile', profile))
    dp.add_handler(CommandHandler('daily', daily))
    dp.add_handler(CommandHandler('leaderboard', leaderboard))
    dp.add_handler(CommandHandler('help', help_command))
    dp.add_handler(CommandHandler('add', add_coins, pass_args=True))
    dp.add_handler(CommandHandler('pm', pm_command, pass_args=True))
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    load_data()
    main()

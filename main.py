import logging
import sqlite3
import random
import uuid
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    ConversationHandler, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo'
ADMINS = [123456789]  # Your admin user IDs here
COIN_EMOJI = "🪙"
DAILY_REWARD = 2000
REGISTER_BONUS = 4000
BAT_EMOJI = "🏏"
BOWL_EMOJI = "⚾"
NUMBERS = [[1, 2, 3], [4, 5, 6]]

(
    PM_WAIT_JOIN,
    PM_TOSS_CHOICE,
    PM_BAT_BOWL_CHOICE,
    PM_BAT_NUMBER,
    PM_BOWL_NUMBER,
) = range(5)

conn = sqlite3.connect('ccg_handcricket.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    coins INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    last_daily TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    initiator INTEGER,
    opponent INTEGER,
    bet INTEGER,
    status TEXT,
    toss_winner INTEGER,
    batting INTEGER,
    bowling INTEGER,
    score_innings1 INTEGER,
    score_innings2 INTEGER,
    current_over INTEGER,
    current_ball INTEGER,
    batsman_choice INTEGER,
    bowler_choice INTEGER
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def register_user(user_id, username):
    if get_user(user_id):
        return False
    c.execute("INSERT INTO users (user_id, username, coins) VALUES (?, ?, ?)", (user_id, username, REGISTER_BONUS))
    conn.commit()
    return True

def update_coins(user_id, amount):
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def get_coins(user_id):
    c.execute("SELECT coins FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    return res[0] if res else 0

def update_wins(user_id, wins=1):
    c.execute("UPDATE users SET wins = wins + ? WHERE user_id=?", (wins, user_id))
    conn.commit()

def update_losses(user_id, losses=1):
    c.execute("UPDATE users SET losses = losses + ? WHERE user_id=?", (losses, user_id))
    conn.commit()

def get_profile(user_id):
    c.execute("SELECT username, coins, wins, losses FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def can_claim_daily(user_id):
    c.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    if not res or not res[0]:
        return True
    last_daily = datetime.fromisoformat(res[0])
    return datetime.utcnow() - last_daily >= timedelta(hours=24)

def update_daily_time(user_id):
    c.execute("UPDATE users SET last_daily = ? WHERE user_id=?", (datetime.utcnow().isoformat(), user_id))
    conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 Welcome to CCG HandCricket!\n\n"
        "Commands:\n"
        "/register - Register and get 4000🪙 coins\n"
        "/pm - Start a match\n"
        "/profile - Show your profile\n"
        "/daily - Claim 2000🪙 daily reward\n"
        "/leaderboard - Show top players\n"
        "/help - Show commands"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if register_user(user.id, user.first_name):
        await update.message.reply_text(f"✅ Registered! You received {REGISTER_BONUS}{COIN_EMOJI} coins.")
    else:
        await update.message.reply_text("❌ You are already registered.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    profile = get_profile(user.id)
    if not profile:
        await update.message.reply_text("You are not registered. Use /register first.")
        return
    username, coins, wins, losses = profile

    text = (
        f"*{username}'s Profile*\n\n"
        f"*Name:* {username}\n"
        f"*ID:* `{user.id}`\n"
        f"*Purse:* {coins}{COIN_EMOJI}\n\n"
        f"*Performance History:*\n"
        f"  • *Wins:* {wins}\n"
        f"  • *Losses:* {losses}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not get_user(user.id):
        await update.message.reply_text("You are not registered. Use /register first.")
        return
    if can_claim_daily(user.id):
        update_coins(user.id, DAILY_REWARD)
        update_daily_time(user.id)
        await update.message.reply_text(f"✅ You claimed {DAILY_REWARD}{COIN_EMOJI} coins today!")
    else:
        await update.message.reply_text("❌ You can claim daily reward only once every 24 hours.")
LEADERBOARD_PAGE_COINS, LEADERBOARD_PAGE_WINS = range(2)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_leaderboard(update, context, by='coins')

async def show_leaderboard(update_obj, context: ContextTypes.DEFAULT_TYPE, by='coins', page=0):
    limit = 10
    offset = page * limit
    if by == 'coins':
        c.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT ? OFFSET ?", (limit, offset))
        title = f"🏆 Top {limit} Richest Players by Coins"
    else:
        c.execute("SELECT username, wins FROM users ORDER BY wins DESC LIMIT ? OFFSET ?", (limit, offset))
        title = f"🏆 Top {limit} Players by Wins"
    rows = c.fetchall()
    if not rows:
        await update_obj.message.reply_text("No data found.")
        return

    text = f"*{title}*\n\n"
    for i, row in enumerate(rows, start=1 + offset):
        if by == 'coins':
            text += f"{i}. {row[0]} - {row[1]}{COIN_EMOJI}\n"
        else:
            text += f"{i}. {row[0]} - {row[1]} Wins\n"

    keyboard = [
        [
            InlineKeyboardButton("Wins 🏆", callback_data=f"leaderboard_wins_{page}"),
            InlineKeyboardButton("Coins 🪙", callback_data=f"leaderboard_coins_{page}")
        ]
    ]

    if hasattr(update_obj, 'callback_query') and update_obj.callback_query:
        await update_obj.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await update_obj.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split('_')
    by = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    await show_leaderboard(update, context, by=by, page=page)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("Please provide valid user_id and amount.")
        return
    if not get_user(target_id):
        await update.message.reply_text("User not found.")
        return
    update_coins(target_id, amount)
    await update.message.reply_text(f"✅ Added {amount}{COIN_EMOJI} coins to user {target_id}.")
def create_join_keyboard(match_id, initiator_name):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join", callback_data=f'join_match_{match_id}')]
    ])
    return keyboard

ongoing_matches = {}

async def pm_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    bet_amount = 0
    if args:
        try:
            bet_amount = int(args[0])
            if bet_amount < 0:
                await update.message.reply_text("Bet amount must be positive.")
                return
        except:
            await update.message.reply_text("Invalid bet amount.")
            return
    if not get_user(user.id):
        await update.message.reply_text("You must /register before starting a match.")
        return
    coins = get_coins(user.id)
    if bet_amount > coins:
        await update.message.reply_text(f"You don't have enough coins to bet {bet_amount}{COIN_EMOJI}.")
        return

    match_id = str(uuid.uuid4())
    ongoing_matches[match_id] = {
        'match_id': match_id,
        'initiator': user.id,
        'initiator_name': user.first_name,
        'opponent': None,
        'bet': bet_amount,
        'status': 'waiting_join',
        'toss_winner': None,
        'batting': None,
        'bowling': None,
        'score_innings1': 0,
        'score_innings2': 0,
        'current_over': 0,
        'current_ball': 0,
        'batsman_choice': None,
        'bowler_choice': None,
        'batting_player_name': None,
        'bowling_player_name': None,
        'toss_choice': None,
        'message_id': None,
        'chat_id': update.effective_chat.id,
        'state': PM_WAIT_JOIN,
        'player_turn': None,
        'batting_user': None,
        'bowling_user': None,
        'innings': 1,
    }

    text = f"🏏 Cricket game has been started!\nPress Join below to play with {user.first_name}"
    sent = await update.message.reply_text(text, reply_markup=create_join_keyboard(match_id, user.first_name))
    ongoing_matches[match_id]['message_id'] = sent.message_id

    return PM_WAIT_JOIN

async def pm_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    if not data.startswith('join_match_'):
        await query.answer()
        return
    match_id = data.split('_', 2)[2]
    match = ongoing_matches.get(match_id)
    if not match:
        await query.answer("Match not found or already started.")
        return
    if match['initiator'] == user.id:
        await query.answer("You cannot join your own match.")
        return
    if match['opponent']:
        await query.answer("Match already started.")
        return

    if match['bet'] > 0:
        coins = get_coins(user.id)
        if coins < match['bet']:
            await query.answer(f"You don't have enough coins to join the bet of {match['bet']}{COIN_EMOJI}.")
            return

    match['opponent'] = user.id
    match['opponent_name'] = user.first_name
    match['status'] = 'toss'

    if match['bet'] > 0:
        update_coins(match['initiator'], -match['bet'])
        update_coins(match['opponent'], -match['bet'])

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Heads", callback_data=f'toss_heads_{match_id}'),
            InlineKeyboardButton("Tails", callback_data=f'toss_tails_{match_id}')
        ]
    ])
    text = (
        f"🏏 Match started between {match['initiator_name']} and {match['opponent_name']}!\n\n"
        f"{match['initiator_name']}, choose Heads or Tails for the toss."
    )
    await context.bot.edit_message_text(
        chat_id=match['chat_id'],
        message_id=match['message_id'],
        text=text,
        reply_markup=keyboard
    )
    await query.answer()
    return PM_TOSS_CHOICE
async def pm_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    parts = data.split('_')
    toss_choice = parts[1]
    match_id = parts[2]

    match = ongoing_matches.get(match_id)
    if not match:
        await query.answer("No toss pending.")
        return ConversationHandler.END
    if user.id != match['initiator']:
        await query.answer("Only initiator can choose toss.")
        return

    match['toss_choice'] = toss_choice
    bot_choice = random.choice(['heads', 'tails'])
    toss_winner = match['initiator'] if match['toss_choice'] == bot_choice else match['opponent']
    match['toss_winner'] = toss_winner
    match['status'] = 'bat_bowl_choice'

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{BAT_EMOJI} Bat", callback_data=f'choose_bat_{match_id}'),
            InlineKeyboardButton(f"{BOWL_EMOJI} Bowl", callback_data=f'choose_bowl_{match_id}')
        ]
    ])

    winner_name = match['initiator_name'] if toss_winner == match['initiator'] else match['opponent_name']
    text = (
        f"🪙 Toss result: {bot_choice.capitalize()}!\n"
        f"{winner_name} won the toss!\n\n"
        f"{winner_name}, choose to Bat or Bowl first."
    )
    await context.bot.edit_message_text(
        chat_id=match['chat_id'],
        message_id=match['message_id'],
        text=text,
        reply_markup=keyboard
    )
    await query.answer()
    return PM_BAT_BOWL_CHOICE

async def pm_bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    parts = data.split('_')
    choice = parts[1]
    match_id = parts[2]

    match = ongoing_matches.get(match_id)
    if not match:
        await query.answer("No bat/bowl choice pending.")
        return
    if user.id != match['toss_winner']:
        await query.answer("Only toss winner can choose bat or bowl.")
        return

    if choice == 'bat':
        match['batting'] = match['toss_winner']
        match['bowling'] = match['opponent'] if match['toss_winner'] == match['initiator'] else match['initiator']
    else:
        match['bowling'] = match['toss_winner']
        match['batting'] = match['opponent'] if match['toss_winner'] == match['initiator'] else match['initiator']

    match['status'] = 'bat_number'
    match['innings'] = 1
    match['score_innings1'] = 0
    match['score_innings2'] = 0
    match['current_over'] = 0
    match['current_ball'] = 0
    match['batsman_choice'] = None
    match['bowler_choice'] = None
    match['player_turn'] = 'bat'

    match['batting_player_name'] = match['initiator_name'] if match['batting'] == match['initiator'] else match['opponent_name']
    match['bowling_player_name'] = match['initiator_name'] if match['bowling'] == match['initiator'] else match['opponent_name']

    keyboard = numbers_keyboard(match_id)
    text = (
        f"🎯 {match['batting_player_name']}, choose your number to Bat.\n"
        f"(Numbers 1-6, select below)"
    )
    await context.bot.edit_message_text(
        chat_id=match['chat_id'],
        message_id=match['message_id'],
        text=text,
        reply_markup=keyboard
    )
    await query.answer()
    return PM_BAT_NUMBER

def numbers_keyboard(match_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in NUMBERS[0]],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in NUMBERS[1]],
    ])
async def pm_number_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    parts = data.split('_')
    if len(parts) < 3:
        await query.answer("Invalid selection.")
        return

    number = int(parts[1])
    match_id = parts[2]

    match = ongoing_matches.get(match_id)
    if not match:
        await query.answer("No active match found.")
        return

    if match['status'] == 'bat_number' and user.id != match['batting']:
        await query.answer("It's not your turn to bat.")
        return
    if match['status'] == 'bowl_number' and user.id != match['bowling']:
        await query.answer("It's not your turn to bowl.")
        return

    if match['player_turn'] == 'bat' and match['status'] == 'bat_number':
        match['batsman_choice'] = number
        match['player_turn'] = 'bowl'
        match['status'] = 'bowl_number'
        keyboard = numbers_keyboard(match_id)
        text = (
            f"🎯 {match['bowling_player_name']}, choose your number to Bowl.\n"
            f"(Numbers 1-6, select below)"
        )
        await context.bot.edit_message_text(
            chat_id=match['chat_id'],
            message_id=match['message_id'],
            text=text,
            reply_markup=keyboard
        )
        await query.answer("You chose your batting number.")
        return PM_BOWL_NUMBER

    elif match['player_turn'] == 'bowl' and match['status'] == 'bowl_number':
        match['bowler_choice'] = number
        bat_num = match['batsman_choice']
        bowl_num = match['bowler_choice']

        match['current_ball'] += 1
        if match['current_ball'] > 6:
            match['current_ball'] = 1
            match['current_over'] += 1

        over_str = f"Over : {match['current_over']}.{match['current_ball']}"
        batter = match['batting_player_name']
        bowler = match['bowling_player_name']

        if bat_num == bowl_num:
            text = (
                f"{over_str}\n\n"
                f"{BAT_EMOJI} Batter : {batter}\n"
                f"{BOWL_EMOJI} Bowler : {bowler}\n\n"
                f"{batter} is OUT! 🏏\n\n"
                f"Match finished (implement innings and scoring logic)."
            )
            await context.bot.edit_message_text(
                chat_id=match['chat_id'],
                message_id=match['message_id'],
                text=text
            )
            del ongoing_matches[match_id]
            await query.answer("Batsman is out! Match ended.")
            return ConversationHandler.END
        else:
            runs = bat_num
            if match['innings'] == 1:
                match['score_innings1'] += runs
                score = match['score_innings1']
            else:
                match['score_innings2'] += runs
                score = match['score_innings2']

            text = (
                f"{over_str}\n\n"
                f"{BAT_EMOJI} Batter : {batter}\n"
                f"{BOWL_EMOJI} Bowler : {bowler}\n\n"
                f"{batter} Bat {bat_num}\n"
                f"{bowler} Bowl {bowl_num}\n\n"
                f"Total Score : {score}\n\n"
                f"Next Move : {batter}, continue your Bat!"
            )
            match['player_turn'] = 'bat'
            match['status'] = 'bat_number'
            match['batsman_choice'] = None
            match['bowler_choice'] = None

            await context.bot.edit_message_text(
                chat_id=match['chat_id'],
                message_id=match['message_id'],
                text=text,
                reply_markup=numbers_keyboard(match_id)
            )
            await query.answer("Move recorded. Next batsman turn.")
            return PM_BAT_NUMBER

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "CCG HandCricket Commands:\n\n"
        "/start - Welcome message\n"
        "/register - Register and get 4000🪙 coins\n"
        "/pm [betamount] - Start a match with optional bet\n"
        "/profile - Show your profile\n"
        "/daily - Claim daily 2000🪙 coins\n"
        "/leaderboard - Show top players\n"
        "/add <user_id> <amount> - Admin only: Add coins to user\n"
    )
    await update.message.reply_text(text)

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(set_bot_commands).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("help", help_command))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('pm', pm_start)],
        states={
            PM_WAIT_JOIN: [CallbackQueryHandler(pm_join_callback, pattern=r'^join_match_')],
            PM_TOSS_CHOICE: [CallbackQueryHandler(pm_toss_choice_callback, pattern=r'^toss_(heads|tails)_')],
            PM_BAT_BOWL_CHOICE: [CallbackQueryHandler(pm_bat_bowl_choice_callback, pattern=r'^choose_(bat|bowl)_')],
            PM_BAT_NUMBER: [CallbackQueryHandler(pm_number_choice_callback, pattern=r'^num_[1-6]_')],
            PM_BOWL_NUMBER: [CallbackQueryHandler(pm_number_choice_callback, pattern=r'^num_[1-6]_')],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)

    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern='^leaderboard_'))

    application.run_polling()

async def set_bot_commands(app, context=None):
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("register", "Register and get 4000🪙 coins"),
        BotCommand("pm", "Start a hand cricket match"),
        BotCommand("profile", "Show your profile"),
        BotCommand("daily", "Claim daily 2000🪙 coins"),
        BotCommand("leaderboard", "Show top players"),
        BotCommand("help", "Show all commands"),
    ]
    await app.bot.set_my_commands(commands)

if __name__ == '__main__':
    main()

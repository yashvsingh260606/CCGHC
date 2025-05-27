import json
import os
import random
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
import asyncio

# Config
TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo'
USER_DATA_FILE = 'ccgusers.json'
MATCH_DATA_FILE = 'ccgmatches.json'
ADMINS = [123456789]  # Put your Telegram user ID here

logging.basicConfig(level=logging.INFO)

# Load/save helpers
def load_data(file):
    if os.path.exists(file):
        with open(file, 'r') as f:
            return json.load(f)
    return {}

def save_data(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

# Load stored data or empty dicts
users = load_data(USER_DATA_FILE)
matches = load_data(MATCH_DATA_FILE)

# Get or create user entry
def get_user(uid):
    uid = str(uid)
    if uid not in users:
        users[uid] = {
            "coins": 0,
            "wins": 0,
            "losses": 0,
            "last_daily": "2000-01-01"
        }
    return users[uid]

def save_all():
    save_data(USER_DATA_FILE, users)
    save_data(MATCH_DATA_FILE, matches)

def coins_emoji():
    return "🪙"

def format_coins(c):
    return f"{c:,} {coins_emoji()}"

def make_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)]
    ])

def help_text():
    return (
        "**Hand Cricket Bot Commands:**\n"
        "/start - Start & show help\n"
        "/register - Claim starting coins\n"
        "/pm <bet> - Start or join a match\n"
        "/profile - Show your profile\n"
        "/leaderboard - Show top players\n"
        "/daily - Claim daily coins\n"
        "/add <user_id> <amount> - (Admin) Add coins\n"
        "/help - Show this help"
    )

# Handlers start here
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to **Hand Cricket Bot!**\n\n" + help_text(), parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text(), parse_mode='Markdown')

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if user['coins'] == 0:
        user['coins'] = 1000
        save_all()
        await update.message.reply_text(f"Registered! You received {format_coins(1000)}.")
    else:
        await update.message.reply_text("You are already registered.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    name = update.effective_user.first_name
    msg = (
        f"**{name}'s Profile**\n\n"
        f"Name: {name}\n"
        f"ID: {uid}\n"
        f"Purse: {format_coins(user['coins'])}\n\n"
        f"Match History -\n"
        f"Wins: {user.get('wins', 0)}\n"
        f"Losses: {user.get('losses', 0)}"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

# --- Part 1 ends here ---

# Next I will send you Part 2 including pm, join, toss, and number input logic plus main()
# Helper to create a new match
def create_match(creator_id, creator_name, bet=0):
    match_id = str(random.randint(100000, 999999))
    while match_id in matches:
        match_id = str(random.randint(100000, 999999))
    matches[match_id] = {
        "players": {
            str(creator_id): {"name": creator_name, "batting": None, "bowling": None, "score": 0, "balls": 0}
        },
        "bet": bet,
        "state": "waiting",  # waiting, toss, innings1, innings2, ended
        "toss_winner": None,
        "toss_choice": None,
        "batting_player": None,
        "bowling_player": None,
        "innings": 1,
        "target": None,
        "msg_id": None,
        "chat_id": None,
        "over": "0.0"
    }
    save_all()
    return match_id

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.first_name
    args = context.args
    bet = 0
    if args and args[0].isdigit():
        bet = int(args[0])
    user = get_user(uid)
    if bet > user['coins']:
        await update.message.reply_text("You don't have enough coins for that bet.")
        return
    # Create match and show join button
    match_id = create_match(uid, uname, bet)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]])
    text = f"Match ID: {match_id}\n{uname} created a match"
    if bet > 0:
        text += f" with bet {format_coins(bet)}"
    text += "\nWaiting for opponent to join..."
    msg = await update.message.reply_text(text, reply_markup=kb)
    matches[match_id]["msg_id"] = msg.message_id
    matches[match_id]["chat_id"] = msg.chat_id
    save_all()

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    uname = query.from_user.first_name
    data = query.data
    if not data.startswith("join_"):
        return
    match_id = data.split("_")[1]
    if match_id not in matches:
        await query.edit_message_text("Match no longer available.")
        return
    match = matches[match_id]
    if len(match['players']) >= 2:
        await query.edit_message_text("Match is already full.")
        return
    if str(uid) in match['players']:
        await query.answer("You are already in this match.")
        return
    user = get_user(uid)
    bet = match["bet"]
    if bet > user['coins']:
        await query.answer("You don't have enough coins to join this bet.")
        return
    # Deduct coins for bet immediately
    if bet > 0:
        user['coins'] -= bet
        creator_id = list(match['players'].keys())[0]
        creator = get_user(creator_id)
        creator['coins'] -= bet
    # Add player
    match['players'][str(uid)] = {"name": uname, "batting": None, "bowling": None, "score": 0, "balls": 0}
    match['state'] = "toss"
    save_all()

    # Start toss prompt
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Heads", callback_data=f"toss_{match_id}_Heads"),
         InlineKeyboardButton("Tails", callback_data=f"toss_{match_id}_Tails")]
    ])
    text = (f"Match {match_id} started between:\n"
            f"{list(match['players'].values())[0]['name']} vs {uname}\n\n"
            f"{uname}, choose Heads or Tails for toss:")
    await query.edit_message_text(text, reply_markup=kb)

async def toss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) != 3:
        return
    _, match_id, choice = parts
    if match_id not in matches:
        await query.edit_message_text("Match no longer available.")
        return
    match = matches[match_id]
    if match['state'] != "toss":
        await query.edit_message_text("Toss already done.")
        return

    # Toss logic
    toss_result = random.choice(["Heads", "Tails"])
    toss_winner_id = str(query.from_user.id)
    toss_winner_name = query.from_user.first_name

    if choice == toss_result:
        match['toss_winner'] = toss_winner_id
        match['toss_choice'] = choice
        msg = f"Toss Result: {toss_result}\n{toss_winner_name} won the toss and will bat first."
        # Set batting and bowling players
        match['batting_player'] = toss_winner_id
        # other player bowls
        other = [pid for pid in match['players'] if pid != toss_winner_id][0]
        match['bowling_player'] = other
        match['state'] = "innings1"
        match['over'] = "0.0"
        save_all()

        # Show batting buttons
        kb = make_keyboard()
        await query.edit_message_text(msg + "\n\nBatsman, choose your number:", reply_markup=kb)
    else:
        # Toss lost, other player wins
        other_id = [pid for pid in match['players'] if pid != toss_winner_id][0]
        other_name = match['players'][other_id]['name']
        match['toss_winner'] = other_id
        match['toss_choice'] = toss_result
        msg = f"Toss Result: {toss_result}\n{other_name} won the toss and will bat first."
        match['batting_player'] = other_id
        match['bowling_player'] = toss_winner_id
        match['state'] = "innings1"
        match['over'] = "0.0"
        save_all()
        kb = make_keyboard()
        await query.edit_message_text(msg + "\n\nBatsman, choose your number:", reply_markup=kb)

async def number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("num_"):
        return
    num = int(data.split("_")[1])
    uid = str(query.from_user.id)

    # Find match user is playing in
    user_match = None
    for mid, m in matches.items():
        if uid in m['players'] and m['state'] in ["innings1", "innings2"]:
            user_match = mid
            break
    if not user_match:
        await query.answer("You are not in an active match.")
        return

    match = matches[user_match]
    if match['state'] not in ["innings1", "innings2"]:
        await query.answer("Match not in play.")
        return

    # Whose turn?
    batting = match['batting_player']
    bowling = match['bowling_player']
    players = match['players']

    # Store chosen number in batting or bowling player record
    # We'll track temporarily in match dict for both chosen numbers
    if 'bat_chosen' not in match:
        match['bat_chosen'] = None
    if 'bowl_chosen' not in match:
        match['bowl_chosen'] = None

    # Decide if this user is batter or bowler and store chosen number
    if uid == batting and match['bat_chosen'] is None:
        match['bat_chosen'] = num
        await query.edit_message_text(
            f"{players[batting]['name']} chose the number, now it's {players[bowling]['name']}'s turn.",
            reply_markup=None
        )
        save_all()
        return
    elif uid == bowling and match['bat_chosen'] is not None and match['bowl_chosen'] is None:
        match['bowl_chosen'] = num
    else:
        await query.answer("Wait for your turn.")
        return

    # Now both numbers chosen, process ball
    bat_num = match['bat_chosen']
    bowl_num = match['bowl_chosen']

    # Update over count
    ov_split = match['over'].split('.')
    over_int = int(ov_split[0])
    ball_int = int(ov_split[1]) + 1
    if ball_int == 6:
        ball_int = 0
        over_int += 1
    match['over'] = f"{over_int}.{ball_int}"

    batsman = players[batting]
    bowler = players[bowling]

    # Ball processed message base
    msg = (f"Over: {match['over']}  \n\n"
           f"🏏 Batter {batsman['name']}\n"
           f"⚾ Bowler {bowler['name']}\n\n"
           f"{batsman['name']} chose: {bat_num}  \n"
           f"{bowler['name']} chose: {bowl_num}  \n\n")

    # If numbers equal -> wicket
    if bat_num == bowl_num:
        msg += f"Wicket! {batsman['name']} is out.\n"
        batsman['balls'] += 1
        match['state'] = "innings2" if match['innings'] == 1 else "ended"
        if match['state'] == "innings2":
            # Switch innings players
            match['innings'] = 2
            match['batting_player'], match['bowling_player'] = match['bowling_player'], match['batting_player']
            # Reset chosen numbers for next innings
            match['bat_chosen'] = None
            match['bowl_chosen'] = None
            match['over'] = "0.0"
            msg += "\nSecond innings started.\n\nBatsman, choose your number:"
            save_all()
            kb = make_keyboard()
            await query.edit_message_text(msg, reply_markup=kb)
            return
        else:
            # Match ended, decide winner
            batscore = batsman['score']
            bowlerid = match['bowling_player']
            bowler_score = players[bowlerid]['score']
            # Determine winner
            if batscore > bowler_score:
                winner_id = batting
            elif batscore < bowler_score:
                winner_id = bowling
            else:
                winner_id = None  # Draw - handle later
            if winner_id:
                users[winner_id]['wins'] += 1
                loser = bowling if winner_id == batting else batting
                users[loser]['losses'] += 1
            save_all()
            win_msg = "Match Ended!\n"
            if winner_id:
                win_msg += f"{players[winner_id]['name']} won the match!"
            else:
                win_msg += "Match Draw!"
            await query.edit_message_text(msg + "\n\n" + win_msg)
            # Clean up match data
            del matches[user_match]
            save_all()
            return

    else:
        # Runs scored
        batsman['score'] += bat_num
        batsman['balls'] += 1
        msg += f"{batsman['name']} scores {bat_num} runs!\n\n{batsman['name']} Continue To Bat"
        # Reset chosen numbers for next ball
        match['bat_chosen'] = None
        match['bowl_chosen'] = None
        save_all()
        kb = make_keyboard()
        await query.edit_message_text(msg, reply_markup=kb)


async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("pm", pm))

    app.add_handler(CallbackQueryHandler(join_callback, pattern=r"^join_"))
    app.add_handler(CallbackQueryHandler(toss_callback, pattern=r"^toss_"))
    app.add_handler(CallbackQueryHandler(number_callback, pattern=r"^num_"))

    print("Bot started...")
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
import datetime

# Claim daily coins (once per 24 hours)
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    now = datetime.datetime.utcnow()
    last_claim = user.get("last_daily")
    if last_claim:
        last_claim_dt = datetime.datetime.fromisoformat(last_claim)
        diff = now - last_claim_dt
        if diff.total_seconds() < 86400:
            remaining = 86400 - diff.total_seconds()
            hrs = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            await update.message.reply_text(f"You already claimed daily coins. Try again in {hrs}h {mins}m.")
            return
    daily_amount = 100
    user["coins"] += daily_amount
    user["last_daily"] = now.isoformat()
    save_all()
    await update.message.reply_text(f"Daily reward claimed! You got {format_coins(daily_amount)}.")

# Show leaderboard by coins or wins
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users_list = list(users.items())
    # Sort by coins descending
    users_list.sort(key=lambda x: (x[1]['coins'], x[1]['wins']), reverse=True)
    top10 = users_list[:10]
    text = "🏆 Top Players 🏆\n\n"
    for i, (uid, udata) in enumerate(top10, 1):
        name = udata['name']
        coins = format_coins(udata['coins'])
        wins = udata['wins']
        text += f"{i}. {name} — {coins}, Wins: {wins}\n"
    await update.message.reply_text(text)

# Admin command: add coins to user
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except:
        await update.message.reply_text("Invalid arguments. Use integers for user_id and coins.")
        return
    if target_id not in users:
        await update.message.reply_text("User not found.")
        return
    users[target_id]['coins'] += amount
    save_all()
    await update.message.reply_text(f"Added {format_coins(amount)} to user {users[target_id]['name']}.")

# /profile command to show user stats
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    text = (f"👤 Profile:\n\n"
            f"Name: {user['name']}\n"
            f"Telegram ID: {uid}\n"
            f"🪙 Coins: {format_coins(user['coins'])}\n"
            f"🏅 Wins: {user['wins']}\n"
            f"❌ Losses: {user['losses']}\n")
    await update.message.reply_text(text)

# Utility to format coins with emoji
def format_coins(amount):
    return f"{amount} 🪙"

# Save users and matches data to JSON files
def save_all():
    with open("ccgusers.json", "w") as f:
        json.dump(users, f, indent=2)
    with open("ccgmatches.json", "w") as f:
        json.dump(matches, f, indent=2)

# Load users and matches data from JSON files
def load_all():
    global users, matches
    try:
        with open("ccgusers.json") as f:
            users = json.load(f)
    except:
        users = {}
    try:
        with open("ccgmatches.json") as f:
            matches = json.load(f)
    except:
        matches = {}

# Call load_all on startup
load_all()

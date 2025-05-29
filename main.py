# =========================
# CCG HandCricket Telegram Bot
# PART 1: Imports, Config, Utilities, Data Structures
# =========================

import logging
import random
import time
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
)

# ========== BOT TOKEN & ADMIN IDS ==========
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # <-- PUT YOUR TOKEN HERE
ADMIN_IDS = [123456789, 987654321]  # <-- PUT YOUR ADMIN USER IDS HERE

# ========== IN-MEMORY STORAGE ==========
users = {}  # user_id: {name, coins, wins, losses, last_daily, registered}
ongoing_matches = {}  # chat_id: match_data

# ========== CONSTANTS ==========
START_COINS = 4000
DAILY_COINS = 2000
DEFAULT_COINS = 1000
DAILY_COOLDOWN = 86400  # 24 hours in seconds

# ========== LOGGING ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== HELP MESSAGE ==========
HELP_MSG = """
<b>CCG HandCricket Commands</b>
/start - Welcome message
/register - Register & get 4000🪙
/pm [bet] - Start a PVP hand cricket match (optionally with bet)
/profile - View your profile
/daily - Claim 2000🪙 every 24h
/leaderboard - View top players by coins or wins
"""

# ========== UTILITY FUNCTIONS ==========

def get_user(user_id, name):
    """Retrieve user data or create a new user entry."""
    if user_id not in users:
        users[user_id] = {
            "name": name,
            "coins": DEFAULT_COINS,
            "wins": 0,
            "losses": 0,
            "last_daily": 0,
            "registered": False
        }
    return users[user_id]

def update_user(user_id, **kwargs):
    """Update user data."""
    users[user_id].update(kwargs)

def format_profile(user_id):
    """Format user profile for display."""
    u = users[user_id]
    return (
        f"<b>{u['name']}'s Profile</b> -\n\n"
        f"Name : {u['name']}\n"
        f"ID : {user_id}\n"
        f"Purse : {u['coins']}🪙\n\n"
        f"Performance History :\n"
        f"Wins : {u['wins']}\n"
        f"Loss : {u['losses']}"
    )

def get_leaderboard(by="coins"):
    """Return a formatted leaderboard string."""
    if by == "coins":
        sorted_users = sorted(users.items(), key=lambda x: -x[1]["coins"])
        title = "🏆 <b>Top 10 Richest Players</b> 🏆"
        rows = [
            f"{i+1}. {u['name']} - {u['coins']}🪙"
            for i, (uid, u) in enumerate(sorted_users[:10])
        ]
    else:
        sorted_users = sorted(users.items(), key=lambda x: -x[1]["wins"])
        title = "🏏 <b>Top 10 by Wins</b> 🏏"
        rows = [
            f"{i+1}. {u['name']} - {u['wins']} Wins"
            for i, (uid, u) in enumerate(sorted_users[:10])
        ]
    return f"{title}\n\n" + "\n".join(rows)

def readable_time(secs):
    """Convert seconds to human-readable time."""
    h, m, s = secs//3600, (secs%3600)//60, secs%60
    return f"{h}h {m}m {s}s"

def ensure_registered(user_id, name):
    """Ensure the user is registered, else prompt."""
    u = get_user(user_id, name)
    if not u.get("registered", False):
        return False
    return True

def get_number_buttons(prefix="batnum"):
    """Return inline keyboard for numbers 1-6."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"{prefix}:{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"{prefix}:{i}") for i in range(4, 7)],
    ])
from telegram.constants import ParseMode

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message on /start."""
    await update.message.reply_text(
        "👋 Welcome to CCG HandCricket!\nType /help to see all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message on /help."""
    await update.message.reply_html(HELP_MSG)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register user and give 4000🪙 if not already registered."""
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    user = get_user(user_id, name)
    if user["registered"]:
        await update.message.reply_text("You are already registered!")
        return
    user["coins"] = START_COINS
    user["registered"] = True
    await update.message.reply_text(f"🎉 Registered! You received {START_COINS}🪙")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show profile info on /profile."""
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    if not ensure_registered(user_id, name):
        await update.message.reply_text("❌ Please register first using /register.")
        return
    await update.message.reply_html(format_profile(user_id))

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Claim daily 2000🪙 coins once every 24 hours."""
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    if not ensure_registered(user_id, name):
        await update.message.reply_text("❌ Please register first using /register.")
        return
    user = get_user(user_id, name)
    now = int(time.time())
    if now - user["last_daily"] >= DAILY_COOLDOWN:
        user["coins"] += DAILY_COINS
        user["last_daily"] = now
        await update.message.reply_text(f"✅ Claimed {DAILY_COINS}🪙! Come back tomorrow.")
    else:
        left = DAILY_COOLDOWN - (now - user["last_daily"])
        await update.message.reply_text(f"⏳ Please wait {readable_time(left)} to claim again.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard by coins with button to switch to wins."""
    msg = await update.message.reply_html(
        get_leaderboard("coins"),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ By Wins", callback_data="lb:wins")]
        ])
    )
    context.chat_data["lb_msg_id"] = msg.message_id

async def leaderboard_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback query handler for leaderboard pagination."""
    query = update.callback_query
    await query.answer()
    if query.data == "lb:wins":
        await query.edit_message_text(
            get_leaderboard("wins"),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ By Coins", callback_data="lb:coins")]
            ])
        )
    elif query.data == "lb:coins":
        await query.edit_message_text(
            get_leaderboard("coins"),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ By Wins", callback_data="lb:wins")]
            ])
        )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add coins to a user: /add <user_id> <amount>."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can use this command.")
        return
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive.")
            return
        target_user = get_user(target_user_id, "Unknown")
        target_user["coins"] += amount
        await update.message.reply_text(f"✅ Added {amount}🪙 to user {target_user_id}.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <user_id> <amount>")
async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate a PVP match, optionally with bet amount."""
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    if not ensure_registered(user_id, name):
        await update.message.reply_text("❌ Please register first using /register.")
        return

    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if bet <= 0:
                await update.message.reply_text("❌ Bet must be positive.")
                return
            if users[user_id]["coins"] < bet:
                await update.message.reply_text("❌ Not enough coins for this bet.")
                return
        except:
            await update.message.reply_text("Usage: /pm [bet]")
            return

    chat_id = update.effective_chat.id
    if chat_id in ongoing_matches:
        await update.message.reply_text("A match is already waiting in this chat.")
        return

    # Deduct bet coins from initiator now (opponent will be checked on join)
    if bet > 0:
        users[user_id]["coins"] -= bet

    ongoing_matches[chat_id] = {
        "initiator": user_id,
        "initiator_name": name,
        "bet": bet,
        "status": "waiting",
        "players": [user_id],
        "player_names": [name],
        "bat_first": None,      # index (0 or 1)
        "bowl_first": None,     # index (0 or 1)
        "toss_winner": None,    # index (0 or 1)
        "innings": 1,
        "scores": [0, 0],
        "balls": 0,
        "target": None,
        "batsman_choice": None,
        "bowler_choice": None,
        "current_batsman": None,  # index (0 or 1)
        "current_bowler": None,   # index (0 or 1)
        "over": 0.0,
        "turn": 0,  # 0 = waiting for join, 1 = toss, 2 = bat/bowl, 3 = play
    }
    join_btn = InlineKeyboardButton("Join", callback_data="join_match")
    await update.message.reply_text(
        f"🏏 Cricket game has been started!\nPress Join below to play with {name}",
        reply_markup=InlineKeyboardMarkup([[join_btn]])
    )

async def join_match_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opponent joins the match."""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    name = query.from_user.first_name

    if chat_id not in ongoing_matches:
        await query.answer("No match to join.", show_alert=True)
        return
    match = ongoing_matches[chat_id]
    if match["status"] != "waiting":
        await query.answer("Match already started.", show_alert=True)
        return
    if user_id == match["initiator"]:
        await query.answer("You can't join your own match.", show_alert=True)
        return

    if not ensure_registered(user_id, name):
        await query.answer("❌ Please register first using /register.", show_alert=True)
        return

    # Bet check for opponent
    if match["bet"] > 0:
        if users[user_id]["coins"] < match["bet"]:
            await query.answer("You don't have enough coins to join this bet match.", show_alert=True)
            return
        users[user_id]["coins"] -= match["bet"]

    match["players"].append(user_id)
    match["player_names"].append(name)
    match["status"] = "toss"
    match["turn"] = 1
    # Ask initiator for heads/tails choice
    btns = [
        InlineKeyboardButton("Heads", callback_data="toss:heads"),
        InlineKeyboardButton("Tails", callback_data="toss:tails"),
    ]
    await query.edit_message_text(
        f"🪙 Toss Time!\n{match['player_names'][0]}, choose Heads or Tails.",
        reply_markup=InlineKeyboardMarkup([btns])
    )

async def toss_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toss: initiator picks heads/tails, winner is random."""
    query = update.callback_query
    chat_id = query.message.chat_id
    match = ongoing_matches.get(chat_id)
    if not match or match["status"] != "toss":
        await query.answer("No toss in progress.", show_alert=True)
        return
    initiator_id = match["players"][0]
    if query.from_user.id != initiator_id:
        await query.answer("Only match initiator can pick.", show_alert=True)
        return
    choice = query.data.split(":")[1]
    toss_result = random.choice(["heads", "tails"])
    if choice == toss_result:
        winner = 0
    else:
        winner = 1
    match["toss_winner"] = winner
    match["status"] = "choose"
    match["turn"] = 2
    btns = [
        InlineKeyboardButton("Bat🏏", callback_data="batbowl:bat"),
        InlineKeyboardButton("Bowl⚾", callback_data="batbowl:bowl"),
    ]
    await query.edit_message_text(
        f"🪙 Toss Result: {toss_result.capitalize()}!\n"
        f"{match['player_names'][winner]} won the toss.\n"
        f"{match['player_names'][winner]}, choose Bat🏏 or Bowl⚾.",
        reply_markup=InlineKeyboardMarkup([btns])
    )

async def batbowl_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toss winner chooses to bat or bowl first."""
    query = update.callback_query
    chat_id = query.message.chat_id
    match = ongoing_matches.get(chat_id)
    if not match or match["status"] != "choose":
        await query.answer("No selection in progress.", show_alert=True)
        return
    winner = match["toss_winner"]
    if query.from_user.id != match["players"][winner]:
        await query.answer("Only toss winner can pick.", show_alert=True)
        return
    choice = query.data.split(":")[1]
    if choice == "bat":
        match["bat_first"] = winner
        match["bowl_first"] = 1 - winner
    else:
        match["bat_first"] = 1 - winner
        match["bowl_first"] = winner
    match["status"] = "play"
    match["turn"] = 3
    match["innings"] = 1
    match["scores"] = [0, 0]
    match["balls"] = 0
    match["target"] = None
    match["batsman_choice"] = None
    match["bowler_choice"] = None
    match["current_batsman"] = match["bat_first"]
    match["current_bowler"] = match["bowl_first"]
    match["over"] = 0.0

    await query.edit_message_text(
        f"🎮 Match started!\n\n"
        f"Over : {match['over']}\n"
        f"🏏 Batter : {match['player_names'][match['current_batsman']]}\n"
        f"⚾ Bowler : {match['player_names'][match['current_bowler']]}\n\n"
        f"{match['player_names'][match['current_batsman']]}, choose your number to Bat (1-6).",
        reply_markup=get_number_buttons()
    )
async def batnum_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle batsman's number choice (1-6)."""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    match = ongoing_matches.get(chat_id)
    if not match or match["status"] != "play":
        await query.answer("No game in progress.", show_alert=True)
        return
    # FIX: Use user_id == match["players"][match["current_batsman"]]
    if user_id != match["players"][match["current_batsman"]]:
        await query.answer("It's not your turn to bat.", show_alert=True)
        return
    if match["batsman_choice"] is not None:
        await query.answer("You already chose your number.", show_alert=True)
        return
    try:
        num = int(query.data.split(":")[1])
        if not 1 <= num <= 6:
            await query.answer("Choose a number between 1 and 6.", show_alert=True)
            return
    except:
        await query.answer("Invalid choice.", show_alert=True)
        return
    match["batsman_choice"] = num
    await query.answer("Number chosen for batting.")
    # Ask bowler to choose number
    await query.edit_message_text(
        f"{match['player_names'][match['current_bowler']]}, choose your number to Bowl (1-6).",
        reply_markup=get_number_buttons(prefix="bownum")
    )

async def bownum_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bowler's number choice (1-6) and resolve the ball."""
    query = update.callback_query
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    match = ongoing_matches.get(chat_id)
    if not match or match["status"] != "play":
        await query.answer("No game in progress.", show_alert=True)
        return
    # FIX: Use user_id == match["players"][match["current_bowler"]]
    if user_id != match["players"][match["current_bowler"]]:
        await query.answer("It's not your turn to bowl.", show_alert=True)
        return
    if match["bowler_choice"] is not None:
        await query.answer("You already chose your number.", show_alert=True)
        return
    try:
        num = int(query.data.split(":")[1])
        if not 1 <= num <= 6:
            await query.answer("Choose a number between 1 and 6.", show_alert=True)
            return
    except:
        await query.answer("Invalid choice.", show_alert=True)
        return
    match["bowler_choice"] = num
    await query.answer("Number chosen for bowling.")
    await resolve_ball(update, context, match, query)

async def resolve_ball(update, context, match, query):
    """Resolve the ball after batsman and bowler have chosen numbers."""
    batsman_num = match["batsman_choice"]
    bowler_num = match["bowler_choice"]
    batsman_idx = match["current_batsman"]
    bowler_idx = match["current_bowler"]
    batsman_name = match["player_names"][batsman_idx]
    bowler_name = match["player_names"][bowler_idx]

    # Update ball count and over number
    match["balls"] += 1
    balls = match["balls"]
    over = (balls - 1) // 6 + ((balls - 1) % 6 + 1) * 0.1
    match["over"] = over

    msg = (
        f"Over : {over:.1f}\n"
        f"🏏 Batter : {batsman_name}\n"
        f"⚾ Bowler : {bowler_name}\n\n"
        f"{batsman_name} Bat {batsman_num}\n"
        f"{bowler_name} Bowl {bowler_num}\n\n"
    )

    # Check if wicket (numbers match)
    if batsman_num == bowler_num:
        msg += f"💥 WICKET! {batsman_name} is OUT!\n\n"
        if match["innings"] == 1:
            # Set target for second innings
            match["target"] = match["scores"][match["bat_first"]] + 1
            match["innings"] = 2
            match["balls"] = 0
            match["batsman_choice"] = None
            match["bowler_choice"] = None
            # Swap batsman and bowler roles
            match["current_batsman"] = match["bowl_first"]
            match["current_bowler"] = match["bat_first"]
            msg += (
                f"{bowler_name} sets a target of {match['target']} runs.\n\n"
                f"{match['player_names'][match['current_batsman']]} will now Bat and "
                f"{match['player_names'][match['current_bowler']]} will Bowl!\n\n"
                f"{match['player_names'][match['current_batsman']]}, choose your number to Bat (1-6)."
            )
            await query.edit_message_text(msg, reply_markup=get_number_buttons())
        else:
            # Match over, bowler's team wins
            winner = match["current_bowler"]
            loser = match["current_batsman"]
            await query.edit_message_text(msg)
            await end_match(context, query.message.chat_id, winner, loser, match)
    else:
        # Runs scored = batsman_num
        match["scores"][batsman_idx] += batsman_num
        total_runs = match["scores"][batsman_idx]
        msg += f"Total Score : {total_runs}\n\n"

        # Check if chasing team reached target
        if match["innings"] == 2 and total_runs >= match["target"]:
            msg += f"🎉 {batsman_name} has reached the target and won the match!"
            await query.edit_message_text(msg)
            winner = batsman_idx
            loser = bowler_idx
            await end_match(context, query.message.chat_id, winner, loser, match)
            return
        else:
            msg += f"Next Move : {batsman_name} Continue your Bat!\n\n{batsman_name}, choose your number to Bat (1-6)."
            match["batsman_choice"] = None
            match["bowler_choice"] = None
            await query.edit_message_text(msg, reply_markup=get_number_buttons())
async def end_match(context: ContextTypes.DEFAULT_TYPE, chat_id, winner_idx, loser_idx, match):
winner_id = match["players"][winner_idx]
    loser_id = match["players"][loser_idx]
    winner_name = match["player_names"][winner_idx]
    loser_name = match["player_names"][loser_idx]
    bet = match["bet"]

    # Update stats
    users[winner_id]["wins"] += 1
    users[loser_id]["losses"] += 1

    # Handle bet payout
    if bet > 0:
        users[winner_id]["coins"] += bet * 2  # winner gets back their bet + opponent's bet

    # Remove match from ongoing
    ongoing_matches.pop(chat_id, None)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🏆 Match Over!\n\n"
            f"Winner: {winner_name}\n"
            f"Loser: {loser_name}\n"
            f"Bet Amount: {bet}🪙\n\n"
            f"Congratulations {winner_name}! You won {bet * 2}🪙."
            if bet > 0 else
            f"🏆 Match Over!\n\nWinner: {winner_name}\nLoser: {loser_name}\n\nCongratulations {winner_name}!"
        )
    )

# =========================
# Handler Registration & Main
# =========================

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("pm", pm))

    # Callback query handlers
    application.add_handler(CallbackQueryHandler(join_match_cb, pattern="^join_match$"))
    application.add_handler(CallbackQueryHandler(toss_cb, pattern="^toss:(heads|tails)$"))
    application.add_handler(CallbackQueryHandler(batbowl_cb, pattern="^batbowl:(bat|bowl)$"))
    application.add_handler(CallbackQueryHandler(batnum_cb, pattern="^batnum:[1-6]$"))
    application.add_handler(CallbackQueryHandler(bownum_cb, pattern="^bownum:[1-6]$"))
    application.add_handler(CallbackQueryHandler(leaderboard_cb, pattern="^lb:(coins|wins)$"))

    print("Bot started...")
    # For Android/Pydroid compatibility:
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(application.run_polling())

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())
    

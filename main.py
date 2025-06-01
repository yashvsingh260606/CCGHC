import logging
import random
import uuid
import asyncio
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMIN_IDS = {7361215114}

MONGO_URL = "mongodb://mongo:GhpHMiZizYnvJfKIQKxoDbRyzBCpqEyC@mainline.proxy.rlwy.net:54853"
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.handcricket
users_collection = db.users
matches_collection = db.matches

USERS = {}
USER_PM_MATCHES = {}
GROUP_PM_MATCHES = {}
PM_MATCHES = {}

USER_CCL_MATCH = {}
GROUP_CCL_MATCH = {}
CCL_MATCHES = {}

COINS_EMOJI = "🪙"

# Bowling types mapped to numbers for comparison and out logic
BOWLING_TYPE_TO_NUMBER = {
    "rs": 0,
    "bouncer": 1,
    "yorker": 2,
    "short": 3,
    "slower": 4,
    "knuckle": 5,
}

# Reverse mapping for display convenience
NUMBER_TO_BOWLING_TYPE = {v: k for k, v in BOWLING_TYPE_TO_NUMBER.items()}

# Bowling commentary text and GIF placeholders (put your GIF URLs later)
BOWLING_COMMENTARY = {
    "rs": ("🎯 Rs...", ""),
    "bouncer": ("🔥 Bouncer...", ""),
    "yorker": ("🎯 Yorker...", ""),
    "short": ("⚡ Short ball...", ""),
    "slower": ("🐢 Slower ball...", ""),
    "knuckle": ("🤜 Knuckle ball...", ""),
}

# Run commentary options for each run count and out
RUN_COMMENTARY = {
    "0": [
        "🟢 Dot Ball!",
        "😶 No run.",
        "⏸️ Well bowled, no run.",
    ],
    "1": [
        "🏃‍♂️ Quick single.",
        "👟 One run taken.",
        "➡️ They sneak a single.",
    ],
    "2": [
        "🏃‍♂️🏃‍♂️ Two runs!",
        "💨 Good running between the wickets.",
        "↔️ They pick up a couple.",
    ],
    "3": [
        "🏃‍♂️🏃‍♂️🏃‍♂️ Three runs!",
        "🔥 Great running, three!",
        "↔️ Three runs taken.",
    ],
    "4": [
        "💥 He smashed a Four!",
        "🏏 Beautiful boundary!",
        "🚀 Cracking shot for four!",
        "🎯 That's a maximum four!",
    ],
    "6": [
        "🚀 He Smoked It For A Six!",
        "💣 Maximum!",
        "🔥 What a massive six!",
        "🎉 Huge hit over the boundary!",
    ],
    "out": [
        "❌ It's Out!",
        "💥 Bowled him!",
        "😱 What a wicket!",
        "⚡ Caught behind!",
    ],
}

def get_username(user):
    return user.first_name or user.username or "Player"

async def load_users():
    try:
        cursor = users_collection.find({})
        async for user in cursor:
            user_id = user.get("user_id") or user.get("_id")
            if not user_id:
                logger.warning(f"Skipping user without user_id: {user}")
                continue
            user["user_id"] = user_id
            USERS[user_id] = user
            USER_PM_MATCHES[user_id] = set()
            USER_CCL_MATCH[user_id] = None
        logger.info("Users loaded successfully.")
    except Exception as e:
        logger.error(f"Error loading users: {e}", exc_info=True)

async def save_user(user_id):
    try:
        user = USERS[user_id]
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": user},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Error saving user {user_id}: {e}", exc_info=True)

def ensure_user(user):
    if user.id not in USERS:
        USERS[user.id] = {
            "user_id": user.id,
            "name": get_username(user),
            "coins": 0,
            "wins": 0,
            "losses": 0,
            "registered": False,
            "last_daily": None,
        }
        USER_PM_MATCHES[user.id] = set()
        USER_CCL_MATCH[user.id] = None

def profile_text(user_id):
    u = USERS.get(user_id, {})
    name = u.get("name", "Unknown")
    coins = u.get("coins", 0)
    wins = u.get("wins", 0)
    losses = u.get("losses", 0)
    return (
        f"**{name}'s Profile**\n\n"
        f"💰 Coins: {coins}{COINS_EMOJI}\n"
        f"🏆 Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    await save_user(user.id)
    await update.message.reply_text(
        f"Welcome to Hand Cricket, {USERS[user.id]['name']}! Use /register to get 4000 {COINS_EMOJI}.",
        parse_mode="Markdown"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    u = USERS[user.id]
    if u["registered"]:
        await update.message.reply_text("You have already registered.", parse_mode="Markdown")
        return
    u["coins"] += 4000
    u["registered"] = True
    await save_user(user.id)
    await update.message.reply_text(f"Registered! You received 4000 {COINS_EMOJI}.", parse_mode="Markdown")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    await update.message.reply_text(profile_text(user.id), parse_mode="Markdown")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    now = datetime.utcnow()
    last = USERS[user.id].get("last_daily")
    if last and (now - last) < timedelta(hours=24):
        rem = timedelta(hours=24) - (now - last)
        h, m = divmod(rem.seconds // 60, 60)
        await update.message.reply_text(f"Daily already claimed. Try again in {h}h {m}m.", parse_mode="Markdown")
        return
    USERS[user.id]["coins"] += 2000
    USERS[user.id]["last_daily"] = now
    await save_user(user.id)
    await update.message.reply_text(f"You received 2000 {COINS_EMOJI} as daily reward!", parse_mode="Markdown")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    sorted_users = sorted(USERS.values(), key=lambda u: u.get("wins", 0), reverse=True)
    text = "🏆 **Top Players by Wins:**\n\n"
    for i, u in enumerate(sorted_users[:10], 1):
        text += f"{i}. {u.get('name', 'Unknown')} - {u.get('wins', 0)} Wins\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.", parse_mode="Markdown")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <amount>", parse_mode="Markdown")
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("Please provide valid user_id and amount.", parse_mode="Markdown")
        return
    if target_id not in USERS:
        await update.message.reply_text("User not found.", parse_mode="Markdown")
        return
    USERS[target_id]["coins"] += amount
    await save_user(target_id)
    await update.message.reply_text(
        f"Added {amount}{COINS_EMOJI} to {USERS[target_id]['name']}.", parse_mode="Markdown"
        )
async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ You cannot start a /pm match in private chat. Please use a group.")
        return

    user = update.effective_user
    ensure_user(user)
    chat_id = update.effective_chat.id
    args = context.args
    bet = int(args[0]) if args and args[0].isdigit() else 0

    if bet > 0 and USERS[user.id]["coins"] < bet:
        await update.message.reply_text("You don't have enough coins to bet that amount.")
        return

    match_id = str(uuid.uuid4())
    PM_MATCHES[match_id] = {
        "match_id": match_id,
        "group_chat_id": chat_id,
        "initiator": user.id,
        "opponent": None,
        "bet": bet,
        "state": "waiting_join",
        "toss_winner": None,
        "toss_loser": None,
        "batting_user": None,
        "bowling_user": None,
        "score": 0,
        "wickets": 0,
        "balls": 0,
        "current_batsman_choice": None,
        "current_bowler_choice": None,
        "start_time": datetime.utcnow(),
    }
    USER_PM_MATCHES.setdefault(user.id, set()).add(match_id)
    GROUP_PM_MATCHES.setdefault(chat_id, set()).add(match_id)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Match ✅", callback_data=f"pm_join_{match_id}")]]
    )
    await update.message.reply_text(
        f"🎮 {USERS[user.id]['name']} started a Hand Cricket 1v1 match! Click below to join.",
        reply_markup=keyboard,
    )

async def pm_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    if match_id not in PM_MATCHES:
        await query.answer("❌ Match not found.", show_alert=True)
        return

    match = PM_MATCHES[match_id]
    if match["state"] != "waiting_join":
        await query.answer("❌ Match already started.", show_alert=True)
        return

    if user.id == match["initiator"]:
        await query.answer("❌ You cannot join your own match.", show_alert=True)
        return

    match["opponent"] = user.id
    match["state"] = "toss"

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Heads", callback_data=f"pm_toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"pm_toss_tails_{match_id}")
        ]]
    )
    await query.message.edit_text(
        f"Coin toss! {USERS[match['initiator']]['name']}, choose Heads or Tails.",
        reply_markup=keyboard,
    )
    await query.answer()

async def pm_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, choice, match_id = query.data.split("_", 3)

    match = PM_MATCHES.get(match_id)
    if not match or match["state"] != "toss":
        await query.answer("Invalid toss state.", show_alert=True)
        return

    if user.id != match["initiator"]:
        await query.answer("Only initiator chooses toss.", show_alert=True)
        return

    coin_result = random.choice(["heads", "tails"])

    toss_winner = match["initiator"] if choice == coin_result else match["opponent"]
    toss_loser = match["opponent"] if toss_winner == match["initiator"] else match["initiator"]

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "bat_bowl_choice"

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Bat 🏏", callback_data=f"pm_bat_{match_id}"),
            InlineKeyboardButton("Bowl ⚾", callback_data=f"pm_bowl_{match_id}"),
        ]]
    )
    await query.message.edit_text(
        f"{USERS[toss_winner]['name']} won the toss! Choose to Bat or Bowl first. (Coin was {coin_result})",
        reply_markup=keyboard,
    )
    await query.answer()

async def pm_bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, choice, match_id = query.data.split("_", 2)

    match = PM_MATCHES.get(match_id)
    if not match or match["state"] != "bat_bowl_choice":
        await query.answer("Invalid state for Bat/Bowl choice.", show_alert=True)
        return

    if user.id != match["toss_winner"]:
        await query.answer("Only toss winner can choose.", show_alert=True)
        return

    if choice == "bat":
        match["batting_user"] = match["toss_winner"]
        match["bowling_user"] = match["toss_loser"]
    else:
        match["batting_user"] = match["toss_loser"]
        match["bowling_user"] = match["toss_winner"]

    match["state"] = "batting"
    match["current_batsman_choice"] = None
    match["current_bowler_choice"] = None
    match["score"] = 0
    match["wickets"] = 0
    match["balls"] = 0

    await query.message.edit_text(
        f"Match started!\n\n"
        f"🏏 Batter: {USERS[match['batting_user']]['name']}\n"
        f"⚾ Bowler: {USERS[match['bowling_user']]['name']}\n\n"
        f"{USERS[match['batting_user']]['name']}, choose your batting number:",
        reply_markup=batting_keyboard(),
    )
    await query.answer()

def batting_keyboard():
    buttons = [
        [InlineKeyboardButton(str(n), callback_data=f"pm_batnum_{n}") for n in [0, 1, 2]],
        [InlineKeyboardButton(str(n), callback_data=f"pm_batnum_{n}") for n in [3, 4, 6]],
    ]
    return InlineKeyboardMarkup(buttons)

def bowling_keyboard():
    types = ["rs", "bouncer", "yorker", "short", "slower", "knuckle"]
    buttons = []
    row = []
    for i, t in enumerate(types, 1):
        row.append(InlineKeyboardButton(t.capitalize(), callback_data=f"pm_bowltype_{t}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

async def pm_batnum_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, num = query.data.split("_", 2)
    num = int(num)
    match = None
    for m in PM_MATCHES.values():
        if m["state"] == "batting" and m["batting_user"] == user.id and m["current_batsman_choice"] is None:
            match = m
            break
    if not match:
        await query.answer("No active batting turn found.", show_alert=True)
        return
    match["current_batsman_choice"] = num
    await query.message.reply_text(f"Batsman chose {num}. Waiting for bowler to choose.")
    try:
        await context.bot.send_message(
            chat_id=match["bowling_user"],
            text="Your turn to bowl! Choose bowling type:",
            reply_markup=bowling_keyboard(),
        )
    except Exception:
        await query.message.reply_text("Cannot DM bowler. Ask them to start the bot.")
    await query.answer()

async def pm_bowltype_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, bowl_type = query.data.split("_", 2)
    match = None
    for m in PM_MATCHES.values():
        if m["state"] == "batting" and m["bowling_user"] == user.id and m["current_bowler_choice"] is None:
            match = m
            break
    if not match:
        await query.answer("No active bowling turn found.", show_alert=True)
        return
    if bowl_type not in BOWLING_TYPE_TO_NUMBER:
        await query.answer("Invalid bowling type.", show_alert=True)
        return
    match["current_bowler_choice"] = bowl_type
    await process_pm_ball(context, match)
    await query.answer()

async def process_pm_ball(context: ContextTypes.DEFAULT_TYPE, match):
    chat_id = match["group_chat_id"]
    batsman_choice = match["current_batsman_choice"]
    bowler_choice_type = match["current_bowler_choice"]

    is_out = (batsman_choice == BOWLING_TYPE_TO_NUMBER.get(bowler_choice_type, -1))

    # Send bowling type message
    await context.bot.send_message(chat_id=chat_id, text=f"{USERS[match['bowling_user']]['name']} Bowled A {bowler_choice_type.capitalize()}")

    # Wait 2.5 seconds for suspense
    await asyncio.sleep(2.5)

    if is_out:
        run_text = random.choice(RUN_COMMENTARY["out"])
        result_text = f"{run_text} It's Out! 💥"
        match["wickets"] += 1
    else:
        run_text = random.choice(RUN_COMMENTARY.get(str(batsman_choice), ["Runs scored!"]))
        result_text = f"{run_text} {batsman_choice} run(s) scored."
        match["score"] += batsman_choice

    match["balls"] += 1
    match["current_batsman_choice"] = None
    match["current_bowler_choice"] = None

    score_msg = (
        f"Total Score: {match['score']} Runs, {match['wickets']} Wickets"
    )
    await context.bot.send_message(chat_id=chat_id, text=result_text)
    await context.bot.send_message(chat_id=chat_id, text=score_msg)

    if match["balls"] >= 6 or match["wickets"] >= 1:
        await context.bot.send_message(chat_id=chat_id, text="Innings over! (Extend logic as needed)")
        # Clean up match data
        del PM_MATCHES[match["match_id"]]
        USER_PM_MATCHES[match["batting_user"]].discard(match["match_id"])
        USER_PM_MATCHES[match["bowling_user"]].discard(match["match_id"])
        GROUP_PM_MATCHES[chat_id].discard(match["match_id"])
        return

    try:
        await context.bot.send_message(
            chat_id=match["batting_user"],
            text="Your turn to bat! Choose a number:",
            reply_markup=batting_keyboard(),
        )
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text="Cannot DM batsman. Ask them to start the bot.")
async def ccl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ You cannot start a /ccl match in private chat. Please use a group.")
        return

    user = update.effective_user
    ensure_user(user)
    chat_id = update.effective_chat.id

    if USER_CCL_MATCH.get(user.id):
        await update.message.reply_text("You already have an active CCL match. Finish it before starting a new one.")
        return
    if GROUP_CCL_MATCH.get(chat_id):
        await update.message.reply_text("This group already has an active CCL match. Wait for it to finish.")
        return

    match_id = str(uuid.uuid4())
    match = {
        "match_id": match_id,
        "group_chat_id": chat_id,
        "initiator": user.id,
        "opponent": None,
        "state": "waiting_join",
        "toss_winner": None,
        "toss_loser": None,
        "batting_user": None,
        "bowling_user": None,
        "score": 0,
        "wickets": 0,
        "balls": 0,
        "batsman_choice": None,
        "bowler_choice": None,
        "start_time": datetime.utcnow(),
        "last_active": datetime.utcnow(),
    }
    CCL_MATCHES[match_id] = match
    USER_CCL_MATCH[user.id] = match_id
    GROUP_CCL_MATCH[chat_id] = match_id

    await update.message.reply_text(
        f"🎮 {USERS[user.id]['name']} started a CCL 1v1 match! Click below button to join.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Join ✅", callback_data=f"ccl_join_{match_id}"),
                InlineKeyboardButton("Cancel ❌", callback_data=f"ccl_cancel_{match_id}")
            ]
        ]),
    )

async def ccl_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    if match_id not in CCL_MATCHES:
        await query.answer("❌ Match not found.", show_alert=True)
        return

    match = CCL_MATCHES[match_id]
    if match["state"] != "waiting_join":
        await query.answer("❌ Match already started.", show_alert=True)
        return

    if user.id == match["initiator"]:
        await query.answer("❌ You cannot join your own match.", show_alert=True)
        return

    if USER_CCL_MATCH.get(user.id):
        await query.answer("You already have an active CCL match. Finish it before joining another.", show_alert=True)
        return

    match["opponent"] = user.id
    match["state"] = "toss"
    USER_CCL_MATCH[user.id] = match_id
    match["last_active"] = datetime.utcnow()

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Heads", callback_data=f"ccl_toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"ccl_toss_tails_{match_id}")
        ]]
    )
    await query.message.edit_text(
        f"Coin toss! {USERS[match['initiator']]['name']}, choose Heads or Tails.",
        reply_markup=keyboard,
    )
    await query.answer()

async def ccl_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    if match_id not in CCL_MATCHES:
        await query.answer("Match not found or already ended.", show_alert=True)
        return

    match = CCL_MATCHES[match_id]

    if user.id != match["initiator"]:
        await query.answer("Only the initiator can cancel this match.", show_alert=True)
        return

    group_chat_id = match["group_chat_id"]

    del CCL_MATCHES[match_id]
    USER_CCL_MATCH[match["initiator"]] = None
    if match.get("opponent"):
        USER_CCL_MATCH[match["opponent"]] = None
    GROUP_CCL_MATCH[group_chat_id] = None

    await query.message.edit_text("The CCL match has been cancelled by the initiator.")
    await query.answer()

async def ccl_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, choice, match_id = query.data.split("_", 3)

    if match_id not in CCL_MATCHES:
        await query.answer("Match not found.", show_alert=True)
        return

    match = CCL_MATCHES[match_id]

    if match["state"] != "toss":
        await query.answer("Not in toss phase.", show_alert=True)
        return

    if user.id != match["initiator"]:
        await query.answer("Only the initiator can choose the toss.", show_alert=True)
        return

    coin_result = random.choice(["heads", "tails"])

    toss_winner = match["initiator"] if choice == coin_result else match["opponent"]
    toss_loser = match["opponent"] if toss_winner == match["initiator"] else match["initiator"]

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "bat_bowl_choice"
    match["last_active"] = datetime.utcnow()

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Bat 🏏", callback_data=f"ccl_bat_{match_id}"),
            InlineKeyboardButton("Bowl ⚾", callback_data=f"ccl_bowl_{match_id}"),
        ]]
    )
    await query.message.edit_text(
        f"{USERS[toss_winner]['name']} won the toss! Choose to Bat or Bowl first. (Coin was {coin_result})",
        reply_markup=keyboard,
    )
    await query.answer()

async def ccl_bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, choice, match_id = query.data.split("_", 2)

    if match_id not in CCL_MATCHES:
        await query.answer("Match not found.", show_alert=True)
        return

    match = CCL_MATCHES[match_id]

    if match["state"] != "bat_bowl_choice":
        await query.answer("Not in Bat/Bowl choice phase.", show_alert=True)
        return

    if user.id != match["toss_winner"]:
        await query.answer("Only toss winner can choose.", show_alert=True)
        return

    if choice == "bat":
        match["batting_user"] = match["toss_winner"]
        match["bowling_user"] = match["toss_loser"]
    else:
        match["batting_user"] = match["toss_loser"]
        match["bowling_user"] = match["toss_winner"]

    match["state"] = "batting"
    match["batsman_choice"] = None
    match["bowler_choice"] = None
    match["score"] = 0
    match["wickets"] = 0
    match["balls"] = 0
    match["last_active"] = datetime.utcnow()

    await query.message.edit_text(
        f"Match started!\n\n"
        f"🏏 Batter: {USERS[match['batting_user']]['name']}\n"
        f"⚾ Bowler: {USERS[match['bowling_user']]['name']}\n\n"
        f"{USERS[match['batting_user']]['name']}, please send your batting number (0,1,2,3,4,6) in DM.",
    )
    await query.answer()

async def ccl_dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()
    valid_batting_numbers = {"0", "1", "2", "3", "4", "6"}
    valid_bowling_types = set(BOWLING_TYPE_TO_NUMBER.keys())

    match_id = USER_CCL_MATCH.get(user.id)
    if not match_id or match_id not in CCL_MATCHES:
        await update.message.reply_text("You have no active CCL match.")
        return

    match = CCL_MATCHES[match_id]

    if match["state"] != "batting":
        await update.message.reply_text("Match is not in batting phase.")
        return

    if user.id == match["batting_user"]:
        if text not in valid_batting_numbers:
            await update.message.reply_text("Please send a valid batting number: 0,1,2,3,4,6")
            return
        if match["batsman_choice"] is not None:
            await update.message.reply_text("You have already chosen your batting number for this ball.")
            return
        match["batsman_choice"] = int(text)
        await update.message.reply_text(f"You chose to bat {text}. Waiting for bowler.")
    elif user.id == match["bowling_user"]:
        if text not in valid_bowling_types:
            await update.message.reply_text("Please send a valid bowling type: rs, bouncer, yorker, short, slower, knuckle")
            return
        if match["bowler_choice"] is not None:
            await update.message.reply_text("You have already chosen your bowling type for this ball.")
            return
        match["bowler_choice"] = text
        await update.message.reply_text(f"You chose bowling type {text}. Waiting for batsman.")
    else:
        await update.message.reply_text("You are not part of the active match.")
        return

    if match["batsman_choice"] is not None and match["bowler_choice"] is not None:
        await process_ccl_ball(context, match)

async def process_ccl_ball(context: ContextTypes.DEFAULT_TYPE, match):
    chat_id = match["group_chat_id"]
    batsman_choice = match["batsman_choice"]
    bowler_choice_type = match["bowler_choice"]

    is_out = (batsman_choice == BOWLING_TYPE_TO_NUMBER.get(bowler_choice_type, -1))

    # Send first message: bowler and bowling type
    await context.bot.send_message(chat_id=chat_id, text=f"{USERS[match['bowling_user']]['name']} Bowled A {bowler_choice_type.capitalize()}")

    # Wait 2.5 seconds for suspense
    await asyncio.sleep(2.5)

    if is_out:
        run_text = random.choice(RUN_COMMENTARY["out"])
        result_text = f"{run_text} It's Out! 💥"
        match["wickets"] += 1
    else:
        run_text = random.choice(RUN_COMMENTARY.get(str(batsman_choice), ["Runs scored!"]))
        result_text = f"{run_text} {batsman_choice} run(s) scored."
        match["score"] += batsman_choice

    match["balls"] += 1
    match["batsman_choice"] = None
    match["bowler_choice"] = None
    match["last_active"] = datetime.utcnow()

    score_msg = f"Total Score: {match['score']} Runs, {match['wickets']} Wickets"
    await context.bot.send_message(chat_id=chat_id, text=result_text)
    await context.bot.send_message(chat_id=chat_id, text=score_msg)

    if match["balls"] >= 6 or match["wickets"] >= 1:
        await context.bot.send_message(chat_id=chat_id, text="Innings over! (Extend logic as needed)")
        del CCL_MATCHES[match["match_id"]]
        USER_CCL_MATCH[match["batting_user"]] = None
        USER_CCL_MATCH[match["bowling_user"]] = None
        GROUP_CCL_MATCH[chat_id] = None
        return

    try:
        await context.bot.send_message(
            chat_id=match["batting_user"],
            text="Your turn to bat! Send your batting number (0,1,2,3,4,6) in DM.",
        )
        await context.bot.send_message(
            chat_id=match["bowling_user"],
            text="Your turn to bowl! Send your bowling type (rs, bouncer, yorker, short, slower, knuckle) in DM.",
        )
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text="Cannot DM one or both players. Ask them to start the bot.")
from telegram import BotCommand

async def endmatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ This command can only be used in groups.")
        return

    match_id = GROUP_CCL_MATCH.get(chat.id)
    if not match_id or match_id not in CCL_MATCHES:
        await update.message.reply_text("❌ No active CCL match in this group.")
        return

    match = CCL_MATCHES[match_id]

    is_initiator = (user.id == match["initiator"])
    member = await context.bot.get_chat_member(chat.id, user.id)
    is_admin = member.status in ["administrator", "creator"]

    if not (is_initiator or is_admin):
        await update.message.reply_text("❌ Only the match initiator or group admins can end the match.")
        return

    del CCL_MATCHES[match_id]
    USER_CCL_MATCH[match["initiator"]] = None
    if match.get("opponent"):
        USER_CCL_MATCH[match["opponent"]] = None
    GROUP_CCL_MATCH[chat.id] = None

    await update.message.reply_text("✅ The active CCL match has been ended.")

async def ccl_inactivity_checker(app):
    while True:
        now = datetime.utcnow()
        to_remove = []
        for match_id, match in CCL_MATCHES.items():
            if (now - match.get("last_active", now)).total_seconds() > 600:
                to_remove.append(match_id)
        for match_id in to_remove:
            match = CCL_MATCHES[match_id]
            chat_id = match["group_chat_id"]
            await app.bot.send_message(chat_id, "CCL match ended due to inactivity.")
            del CCL_MATCHES[match_id]
            USER_CCL_MATCH[match["initiator"]] = None
            if match.get("opponent"):
                USER_CCL_MATCH[match["opponent"]] = None
            GROUP_CCL_MATCH[chat_id] = None
        await asyncio.sleep(60)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Basic commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))

    # PM mode handlers
    app.add_handler(CommandHandler("pm", pm_command))
    app.add_handler(CallbackQueryHandler(pm_join_callback, pattern=r"^pm_join_"))
    app.add_handler(CallbackQueryHandler(pm_toss_choice_callback, pattern=r"^pm_toss_"))
    app.add_handler(CallbackQueryHandler(pm_bat_bowl_choice_callback, pattern=r"^pm_(bat|bowl)_"))
    app.add_handler(CallbackQueryHandler(pm_batnum_choice_callback, pattern=r"^pm_batnum_"))
    app.add_handler(CallbackQueryHandler(pm_bowltype_choice_callback, pattern=r"^pm_bowltype_"))

    # CCL mode handlers
    app.add_handler(CommandHandler("ccl", ccl_command))
    app.add_handler(CallbackQueryHandler(ccl_join_callback, pattern=r"^ccl_join_"))
    app.add_handler(CallbackQueryHandler(ccl_cancel_callback, pattern=r"^ccl_cancel_"))
    app.add_handler(CallbackQueryHandler(ccl_toss_choice_callback, pattern=r"^ccl_toss_"))
    app.add_handler(CallbackQueryHandler(ccl_bat_bowl_choice_callback, pattern=r"^ccl_(bat|bowl)_"))

    # DM handler for CCL batsman and bowler choices
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, ccl_dm_handler))

    # /endmatch command
    app.add_handler(CommandHandler("endmatch", endmatch_command))

    async def set_bot_commands(application):
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("register", "Register and get coins"),
            BotCommand("profile", "Show your profile"),
            BotCommand("daily", "Get daily 2000 🪙 reward"),
            BotCommand("leaderboard", "Show leaderboard"),
            BotCommand("add", "Add coins to user (admin only)"),
            BotCommand("pm", "Start a Hand Cricket 1v1 match"),
            BotCommand("ccl", "Start a CCL 1v1 match"),
            BotCommand("endmatch", "End/cancel the active CCL match"),
        ]
        await application.bot.set_my_commands(commands)

    async def on_startup(app):
        await load_users()
        await set_bot_commands(app)
        app.create_task(ccl_inactivity_checker(app))
        logger.info("Bot started and ready")

    app.post_init = on_startup

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
    

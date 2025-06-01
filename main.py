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

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Replace with your actual token and admin IDs
TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMIN_IDS = {7361215114}

# MongoDB setup
MONGO_URL = "mongodb://mongo:GhpHMiZizYnvJfKIQKxoDbRyzBCpqEyC@mainline.proxy.rlwy.net:54853"
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.handcricket
users_collection = db.users
matches_collection = db.matches

# In-memory caches
USERS = {}
USER_PM_MATCHES = {}   # user_id -> set of pm match_ids
GROUP_PM_MATCHES = {}  # group_id -> set of pm match_ids
PM_MATCHES = {}        # pm match_id -> match dict

USER_CCL_MATCH = {}    # user_id -> ccl match_id or None
GROUP_CCL_MATCH = {}   # group_id -> ccl match_id or None
CCL_MATCHES = {}       # ccl match_id -> match dict

LEADERBOARD_PAGE = {}

# Emoji and placeholders
COINS_EMOJI = "🪙"
RUN_GIFS = {
    "0": None,
    "4": None,
    "6": None,
}

# Commentary data
BOWLING_COMMENTARY = {
    "rs": "🎯 Rs...",
    "bouncer": "🔥 Bouncer...",
    "yorker": "🎯 Yorker...",
    "short": "⚡ Short ball...",
    "slower": "🐢 Slower ball...",
    "knuckle": "🤜 Knuckle ball...",
}

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

async def load_matches():
    try:
        cursor = matches_collection.find({})
        async for match in cursor:
            if "match_id" not in match:
                logger.warning(f"Skipping match without match_id: {match}")
                continue
            # For simplicity, load all into PM_MATCHES; adjust if needed
            PM_MATCHES[match["match_id"]] = match
        logger.info("Matches loaded successfully.")
    except Exception as e:
        logger.error(f"Error loading matches: {e}", exc_info=True)

async def save_match(match_id):
    try:
        match = PM_MATCHES.get(match_id) or CCL_MATCHES.get(match_id)
        if not match:
            logger.warning(f"Match {match_id} not found for saving.")
            return
        await matches_collection.update_one(
            {"match_id": match_id},
            {"$set": match},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Error saving match {match_id}: {e}", exc_info=True)

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

def leaderboard_text(page):
    top = 10
    if page == 0:
        sorted_users = sorted(USERS.values(), key=lambda u: u.get("wins", 0), reverse=True)
        text = "🏆 **Top 10 Players by Wins:**\n\n"
        for i, u in enumerate(sorted_users[:top], 1):
            name = u.get("name", "Unknown")
            wins = u.get("wins", 0)
            text += f"{i}. {name} - {wins} Wins\n"
    else:
        sorted_users = sorted(USERS.values(), key=lambda u: u.get("coins", 0), reverse=True)
        text = "💰 **Top 10 Richest Players by Coins:**\n\n"
        for i, u in enumerate(sorted_users[:top], 1):
            name = u.get("name", "Unknown")
            coins = u.get("coins", 0)
            text += f"{i}. {name} - {coins}{COINS_EMOJI}\n"
    return text

def leaderboard_buttons(page):
    if page == 0:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("➡️ Coins Leaderboard", callback_data="leaderboard_right")]]
        )
    else:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Wins Leaderboard", callback_data="leaderboard_left")]]
        )
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        ensure_user(user)
        await save_user(user.id)
        await update.message.reply_text(
            f"Welcome to Hand Cricket, {USERS[user.id]['name']}! Use /register to get 4000 {COINS_EMOJI}.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in /start: {e}", exc_info=True)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
    except Exception as e:
        logger.error(f"Error in /register: {e}", exc_info=True)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        ensure_user(user)
        await update.message.reply_text(profile_text(user.id), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in /profile: {e}", exc_info=True)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
    except Exception as e:
        logger.error(f"Error in /daily: {e}", exc_info=True)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        ensure_user(user)
        LEADERBOARD_PAGE[user.id] = 0
        await update.message.reply_text(
            leaderboard_text(0),
            reply_markup=leaderboard_buttons(0),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in /leaderboard: {e}", exc_info=True)

async def leaderboard_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user = update.effective_user
        await query.answer()
        page = LEADERBOARD_PAGE.get(user.id, 0)
        if query.data == "leaderboard_right":
            page = 1
        elif query.data == "leaderboard_left":
            page = 0
        LEADERBOARD_PAGE[user.id] = page
        await query.edit_message_text(
            text=leaderboard_text(page),
            reply_markup=leaderboard_buttons(page),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in leaderboard pagination: {e}", exc_info=True)

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
    except Exception as e:
        logger.error(f"Error in /add: {e}", exc_info=True)
async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ You cannot start a /pm match in private chat. Please use a group.")
        return

    try:
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
            [[InlineKeyboardButton("Join Match", callback_data=f"pm_join_{match_id}")]]
        )
        await update.message.reply_text(
            f"🎮 {USERS[user.id]['name']} started a Hand Cricket 1v1 match! Click below to join.",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Error in /pm command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error starting match.")
async def pm_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
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
        group_chat_id = match["group_chat_id"]

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
    except Exception as e:
        logger.error(f"Error in pm_join_callback: {e}", exc_info=True)
        await update.callback_query.answer("❌ Error joining match.", show_alert=True)

async def pm_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user = update.effective_user
        _, choice, match_id = query.data.split("_", 3)

        if match_id not in PM_MATCHES:
            await query.answer("❌ Match not found.", show_alert=True)
            return

        match = PM_MATCHES[match_id]
        if match["state"] != "toss":
            await query.answer("❌ Not in toss phase.", show_alert=True)
            return

        if user.id != match["initiator"]:
            await query.answer("❌ Only initiator chooses toss.", show_alert=True)
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
            f"{USERS[toss_winner]['name']} won the toss! Choose to Bat or Bowl first.",
            reply_markup=keyboard,
        )
        await query.answer()
    except Exception as e:
        logger.error(f"Error in pm_toss_choice_callback: {e}", exc_info=True)
        await update.callback_query.answer("❌ Error in toss choice.", show_alert=True)

async def pm_bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user = update.effective_user
        _, choice, match_id = query.data.split("_", 3)

        if match_id not in PM_MATCHES:
            await query.answer("❌ Match not found.", show_alert=True)
            return

        match = PM_MATCHES[match_id]
        if match["state"] != "bat_bowl_choice":
            await query.answer("❌ Not in Bat/Bowl choice phase.", show_alert=True)
            return

        if user.id != match["toss_winner"]:
            await query.answer("❌ Only toss winner can choose.", show_alert=True)
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
    except Exception as e:
        logger.error(f"Error in pm_bat_bowl_choice_callback: {e}", exc_info=True)
        await update.callback_query.answer("❌ Error in bat/bowl choice.", show_alert=True)

def batting_keyboard():
    buttons = [
        [InlineKeyboardButton(str(n), callback_data=f"pm_batnum_{n}") for n in [0,1,2]],
        [InlineKeyboardButton(str(n), callback_data=f"pm_batnum_{n}") for n in [3,4,6]],
    ]
    return InlineKeyboardMarkup(buttons)

async def pm_batnum_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user = update.effective_user
        _, _, num = query.data.split("_", 2)
        num = int(num)

        # Find match where user is batting and waiting for bat choice
        match = None
        for m in PM_MATCHES.values():
            if m["state"] == "batting" and m.get("batting_user") == user.id and m["current_batsman_choice"] is None:
                match = m
                break

        if not match:
            await query.answer("❌ No active batting turn found.", show_alert=True)
            return

        match["current_batsman_choice"] = num

        await query.message.reply_text(
            f"Batsman chose {num}. Waiting for bowler to choose.",
            reply_markup=None,
        )

        bowler_id = match["bowling_user"]
        try:
            await context.bot.send_message(
                chat_id=bowler_id,
                text=f"Your turn to bowl! Choose your bowling type:",
                reply_markup=bowling_keyboard(),
            )
        except Exception:
            await query.message.reply_text("Cannot send DM to bowler. Ask them to start the bot.")
        await query.answer()
    except Exception as e:
        logger.error(f"Error in pm_batnum_choice_callback: {e}", exc_info=True)
        await update.callback_query.answer("❌ Error processing batting choice.", show_alert=True)

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

async def pm_bowltype_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user = update.effective_user
        _, _, bowl_type = query.data.split("_", 2)

        # Find match where user is bowling and waiting for bowl choice
        match = None
        for m in PM_MATCHES.values():
            if m["state"] == "batting" and m.get("bowling_user") == user.id and m["current_bowler_choice"] is None:
                match = m
                break

        if not match:
            await query.answer("❌ No active bowling turn found.", show_alert=True)
            return

        match["current_bowler_choice"] = bowl_type

        await process_pm_ball(update, context, match)
        await query.answer()
    except Exception as e:
        logger.error(f"Error in pm_bowltype_choice_callback: {e}", exc_info=True)
        await update.callback_query.answer("❌ Error processing bowling choice.", show_alert=True)

async def process_pm_ball(update, context, match):
    chat_id = match["group_chat_id"]
    batsman_choice = match["current_batsman_choice"]
    bowler_choice = match["current_bowler_choice"]

    is_out = (str(batsman_choice) == bowler_choice)

    if is_out:
        match["wickets"] += 1
        result_text = "It's Out! 💥"
    else:
        match["score"] += batsman_choice
        result_text = f"{batsman_choice} run(s) scored."

    match["balls"] += 1
    match["current_batsman_choice"] = None
    match["current_bowler_choice"] = None

    msg = (
        f"Over: {match['balls'] // 6}.{match['balls'] % 6}\n\n"
        f"🏏 Batter: {USERS[match['batting_user']]['name']}\n"
        f"⚾ Bowler: {USERS[match['bowling_user']]['name']}\n\n"
        f"{USERS[match['batting_user']]['name']} Bat {batsman_choice}\n"
        f"{USERS[match['bowling_user']]['name']} Bowl {bowler_choice}\n\n"
        f"Total Score: {match['score']} Runs, {match['wickets']} Wickets\n\n"
        f"{result_text}\n"
    )
    await context.bot.send_message(chat_id=chat_id, text=msg)

    if match["balls"] >= 6 or match["wickets"] >= 1:
        await context.bot.send_message(chat_id=chat_id, text="Innings over! (Extend logic as needed)")
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

    try:
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
            "batting_user": None,
            "bowling_user": None,
            "batsman_choice": None,
            "bowler_choice": None,
            "score": 0,
            "wickets": 0,
            "balls": 0,
            "start_time": datetime.utcnow(),
            "last_active": datetime.utcnow(),
        }
        CCL_MATCHES[match_id] = match
        USER_CCL_MATCH[user.id] = match_id
        GROUP_CCL_MATCH[chat_id] = match_id

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Join CCL Match", callback_data=f"ccl_join_{match_id}"),
                InlineKeyboardButton("Cancel Match ❌", callback_data=f"ccl_cancel_{match_id}")
            ]
        ])
        await update.message.reply_text(
            f"⚡ {USERS[user.id]['name']} started a CCL 1v1 match! Click below to join.",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Error in /ccl command: {e}", exc_info=True)
        await update.message.reply_text("❌ Error starting CCL match.")
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
    group_chat_id = match["group_chat_id"]

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
    _, choice, match_id = query.data.split("_", 3)

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
        f"{USERS[toss_winner]['name']} won the toss! Choose to Bat or Bowl first.",
        reply_markup=keyboard,
    )
    await query.answer()

async def ccl_bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, choice, match_id = query.data.split("_", 3)

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
        f"{USERS[match['batting_user']]['name']}, send your batting choice (0,1,2,3,4,6) in DM to me.\n"
        f"{USERS[match['bowling_user']]['name']}, send your bowling choice (rs,bouncer,yorker,short,slower,knuckle) in DM.",
    )
    await query.answer()

VALID_BAT_CHOICES = {"0", "1", "2", "3", "4", "6"}
VALID_BOWL_CHOICES = {"rs", "bouncer", "yorker", "short", "slower", "knuckle"}

async def ccl_dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()

    match = None
    for m in CCL_MATCHES.values():
        if m["state"] == "batting" and user.id in {m["batting_user"], m["bowling_user"]}:
            if user.id == m["batting_user"] and m["batsman_choice"] is None:
                match = m
                role = "batsman"
                break
            elif user.id == m["bowling_user"] and m["bowler_choice"] is None:
                match = m
                role = "bowler"
                break

    if not match:
        await update.message.reply_text("You have no active CCL match awaiting your input.")
        return

    if role == "batsman":
        if text not in VALID_BAT_CHOICES:
            await update.message.reply_text(
                "Invalid choice. Please choose one of: 0,1,2,3,4,6"
            )
            return
        match["batsman_choice"] = text
        await update.message.reply_text(f"Batsman choice {text} received. Waiting for bowler.")
    else:
        if text not in VALID_BOWL_CHOICES:
            await update.message.reply_text(
                "Invalid choice. Please choose one of: rs,bouncer,yorker,short,slower,knuckle"
            )
            return
        match["bowler_choice"] = text
        await update.message.reply_text(f"Bowler choice '{text}' received. Waiting for batsman.")

    match["last_active"] = datetime.utcnow()

    if match["batsman_choice"] is not None and match["bowler_choice"] is not None:
        await process_ccl_ball(context.bot, match)

async def process_ccl_ball(bot, match):
    group_chat_id = match["group_chat_id"]
    batsman_choice = match["batsman_choice"]
    bowler_choice = match["bowler_choice"]

    bowling_text = BOWLING_COMMENTARY.get(bowler_choice, bowler_choice.capitalize() + "...")
    await bot.send_message(chat_id=group_chat_id, text=bowling_text)
    await asyncio.sleep(random.uniform(2, 3))

    if bowler_choice == "knuckle" and batsman_choice == "6":
        result = "out"
    elif batsman_choice == bowler_choice:
        result = "out"
    else:
        result = batsman_choice

    if result in RUN_GIFS and RUN_GIFS[result]:
        await bot.send_animation(chat_id=group_chat_id, animation=RUN_GIFS[result])

    commentary_list = RUN_COMMENTARY.get(str(result), [f"{result} run(s)."])
    commentary = random.choice(commentary_list)
    await bot.send_message(chat_id=group_chat_id, text=commentary)

    if result == "out":
        match["wickets"] += 1
    else:
        match["score"] += int(result)

    match["balls"] += 1
    match["batsman_choice"] = None
    match["bowler_choice"] = None
    match["last_active"] = datetime.utcnow()

    if match["balls"] >= 6 or match["wickets"] >= 1:
        await bot.send_message(
            chat_id=group_chat_id,
            text=f"Match over! Final Score: {match['score']} runs, {match['wickets']} wicket(s)."
        )
        USER_CCL_MATCH[match["initiator"]] = None
        if match.get("opponent"):
            USER_CCL_MATCH[match["opponent"]] = None
        GROUP_CCL_MATCH[group_chat_id] = None
        del CCL_MATCHES[match["match_id"]]
        return

    await bot.send_message(
        chat_id=group_chat_id,
        text=f"Next ball! {USERS[match['batting_user']]['name']} bat, {USERS[match['bowling_user']]['name']} bowl."
    )
    await bot.send_message(
        chat_id=match["batting_user"],
        text="Send your batting choice (0,1,2,3,4,6):"
    )
    await bot.send_message(
        chat_id=match["bowling_user"],
        text="Send your bowling choice (rs,bouncer,yorker,short,slower,knuckle):"
    )

INACTIVITY_LIMIT = 600  # 10 minutes

async def ccl_inactivity_checker(app):
    while True:
        now = datetime.utcnow()
        to_remove = []
        for match_id, match in list(CCL_MATCHES.items()):
            last_active = match.get("last_active", match.get("start_time", now))
            if (now - last_active).total_seconds() > INACTIVITY_LIMIT:
                group_chat_id = match["group_chat_id"]
                await app.bot.send_message(
                    chat_id=group_chat_id,
                    text="⏰ Match ended due to inactivity."
                )
                USER_CCL_MATCH[match["initiator"]] = None
                if match.get("opponent"):
                    USER_CCL_MATCH[match["opponent"]] = None
                GROUP_CCL_MATCH[group_chat_id] = None
                to_remove.append(match_id)
        for mid in to_remove:
            del CCL_MATCHES[mid]
        await asyncio.sleep(60)
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

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Old commands
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

    # Leaderboard pagination callback
    app.add_handler(CallbackQueryHandler(leaderboard_pagination, pattern=r"^leaderboard_"))

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
        await load_matches()
        await set_bot_commands(app)
        app.create_task(ccl_inactivity_checker(app))
        logger.info("Bot started and ready")

    app.post_init = on_startup

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
    

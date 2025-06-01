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

USERS = {}
USER_PM_MATCHES = {}
GROUP_PM_MATCHES = {}
PM_MATCHES = {}

USER_CCL_MATCH = {}
GROUP_CCL_MATCH = {}
CCL_MATCHES = {}

COINS_EMOJI = "🪙"

BOWLING_TYPE_TO_NUMBER = {
    "rs": 0,
    "bouncer": 1,
    "yorker": 2,
    "short": 3,
    "slower": 4,
    "knuckle": 5,
}

NUMBER_TO_BOWLING_TYPE = {v: k for k, v in BOWLING_TYPE_TO_NUMBER.items()}

BOWLING_COMMENTARY = {
    "rs": ("🎯 Rs...", "GIF_URL_RS"),
    "bouncer": ("🔥 Bouncer...", "GIF_URL_BOUNCER"),
    "yorker": ("🎯 Yorker...", "GIF_URL_YORKER"),
    "short": ("⚡ Short ball...", "GIF_URL_SHORT"),
    "slower": ("🐢 Slower ball...", "GIF_URL_SLOWER"),
    "knuckle": ("🤜 Knuckle ball...", "GIF_URL_KNUCKLE"),
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
        f"Name: {name}\n"
        f"ID: {user_id}\n"
        f"Purse: {coins}{COINS_EMOJI}\n\n"
        f"Performance History:\n"
        f"Wins: {wins}\n"
        f"Losses: {losses}\n"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    await save_user(user.id)
    await update.message.reply_text(
        f"Welcome to CCG HandCricket, {USERS[user.id]['name']}! Use /register to get 4000 {COINS_EMOJI}.",
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
    sorted_users = sorted(USERS.values(), key=lambda u: u.get("coins", 0), reverse=True)
    page = 1
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    total_pages = 2
    text = ""
    if page == 1:
        text = "🏆 **Top 10 Richest Players by Coins:**\n\n"
        sorted_list = sorted_users[:10]
        for i, u in enumerate(sorted_list, 1):
            text += f"{i}. {u.get('name', 'Unknown')} - {u.get('coins', 0)} {COINS_EMOJI}\n"
    else:
        sorted_wins = sorted(USERS.values(), key=lambda u: u.get("wins", 0), reverse=True)
        text = "🏆 **Top 10 Players by Wins:**\n\n"
        for i, u in enumerate(sorted_wins[:10], 1):
            text += f"{i}. {u.get('name', 'Unknown')} - {u.get('wins', 0)} Wins\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Coins", callback_data=f"leaderboard_1"),
            InlineKeyboardButton("Wins ➡️", callback_data=f"leaderboard_2"),
        ]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, page = query.data.split("_")
    page = int(page)
    sorted_users = sorted(USERS.values(), key=lambda u: u.get("coins", 0), reverse=True)
    total_pages = 2
    text = ""
    if page == 1:
        text = "🏆 **Top 10 Richest Players by Coins:**\n\n"
        sorted_list = sorted_users[:10]
        for i, u in enumerate(sorted_list, 1):
            text += f"{i}. {u.get('name', 'Unknown')} - {u.get('coins', 0)} {COINS_EMOJI}\n"
    else:
        sorted_wins = sorted(USERS.values(), key=lambda u: u.get("wins", 0), reverse=True)
        text = "🏆 **Top 10 Players by Wins:**\n\n"
        for i, u in enumerate(sorted_wins[:10], 1):
            text += f"{i}. {u.get('name', 'Unknown')} - {u.get('wins', 0)} Wins\n"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Coins", callback_data=f"leaderboard_1"),
            InlineKeyboardButton("Wins ➡️", callback_data=f"leaderboard_2"),
        ]
    ])
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer()

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "**CCG HandCricket Commands:**\n\n"
        "/start - Start the bot\n"
        "/register - Register and get 4000 🪙 coins\n"
        "/pm [bet] - Start a PM match optionally with bet\n"
        "/ccl - Start a CCL match\n"
        "/profile - Show your profile\n"
        "/daily - Claim daily 2000 🪙 coins\n"
        "/leaderboard - Show leaderboard with coins and wins\n"
        "/help - Show this help message\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
# PM Mode Keyboards

def pm_join_cancel_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Join ✅", callback_data=f"pm_join_{match_id}"),
            InlineKeyboardButton("Cancel ❌", callback_data=f"pm_cancel_{match_id}")
        ]]
    )

def pm_toss_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Heads", callback_data=f"pm_toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"pm_toss_tails_{match_id}")
        ]]
    )

def pm_bat_bowl_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Bat 🏏", callback_data=f"pm_bat_{match_id}"),
            InlineKeyboardButton("Bowl ⚾", callback_data=f"pm_bowl_{match_id}")
        ]]
    )

def pm_number_keyboard(prefix):
    # Buttons 1-3 first row, 4-6 second row
    buttons = [
        [InlineKeyboardButton(str(n), callback_data=f"{prefix}_{n}") for n in [1, 2, 3]],
        [InlineKeyboardButton(str(n), callback_data=f"{prefix}_{n}") for n in [4, 5, 6]],
    ]
    return InlineKeyboardMarkup(buttons)

# /pm Command Handler

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    args = context.args

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ PM matches can only be started in groups.")
        return

    ensure_user(user)

    bet = 0
    if args:
        try:
            bet = int(args[0])
            if bet < 0:
                await update.message.reply_text("Bet amount must be positive.")
                return
        except ValueError:
            await update.message.reply_text("Invalid bet amount.")
            return

    if bet > 0 and USERS[user.id]["coins"] < bet:
        await update.message.reply_text("You don't have enough coins for that bet.")
        return

    # Check if user already in a PM match in this group
    for match_id in USER_PM_MATCHES.get(user.id, set()):
        match = PM_MATCHES.get(match_id)
        if match and match["group_chat_id"] == chat.id and match["state"] != "finished":
            await update.message.reply_text("You already have an active PM match in this group.")
            return

    match_id = str(uuid.uuid4())
    PM_MATCHES[match_id] = {
        "match_id": match_id,
        "group_chat_id": chat.id,
        "initiator": user.id,
        "opponent": None,
        "bet": bet,
        "state": "waiting_join",
        "toss_winner": None,
        "toss_loser": None,
        "batting_user": None,
        "bowling_user": None,
        "score": 0,
        "balls": 0,
        "wickets": 0,
        "innings": 1,
        "target": None,
        "batsman_choice": None,
        "bowler_choice": None,
        "superball": False,
    }
    USER_PM_MATCHES.setdefault(user.id, set()).add(match_id)
    GROUP_PM_MATCHES.setdefault(chat.id, set()).add(match_id)

    await update.message.reply_text(
        f"🏏 Cricket game has been started by {USERS[user.id]['name']}!\nPress Join below to play.",
        reply_markup=pm_join_cancel_keyboard(match_id),
    )

# Join Callback

async def pm_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    match = PM_MATCHES.get(match_id)
    if not match or match["state"] != "waiting_join":
        await query.answer("Match not available to join.", show_alert=True)
        return

    if user.id == match["initiator"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return

    if match["opponent"]:
        await query.answer("Match already has an opponent.", show_alert=True)
        return

    ensure_user(user)

    if match["bet"] > 0 and USERS[user.id]["coins"] < match["bet"]:
        await query.answer("You don't have enough coins to join this bet match.", show_alert=True)
        return

    match["opponent"] = user.id
    match["state"] = "toss"

    USER_PM_MATCHES.setdefault(user.id, set()).add(match_id)

    await query.message.edit_text(
        f"Match started between {USERS[match['initiator']]['name']} and {USERS[user.id]['name']}!\n"
        f"{USERS[match['initiator']]['name']}, choose Heads or Tails for the toss.",
        reply_markup=pm_toss_keyboard(match_id),
    )
    await query.answer()

# Cancel Callback

async def pm_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    match = PM_MATCHES.get(match_id)
    if not match:
        await query.answer("Match not found or already ended.", show_alert=True)
        return

    if user.id != match["initiator"]:
        await query.answer("Only the match initiator can cancel.", show_alert=True)
        return

    chat_id = match["group_chat_id"]

    # Refund bets if any
    if match["bet"] > 0:
        USERS[match["initiator"]]["coins"] += match["bet"]
        if match["opponent"]:
            USERS[match["opponent"]]["coins"] += match["bet"]

    del PM_MATCHES[match_id]
    USER_PM_MATCHES[match["initiator"]].discard(match_id)
    if match.get("opponent"):
        USER_PM_MATCHES[match["opponent"]].discard(match_id)
    GROUP_PM_MATCHES[chat_id].discard(match_id)

    await query.message.edit_text("The PM match has been cancelled by the initiator.")
    await query.answer()

# Toss Callback

async def pm_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, choice, match_id = query.data.split("_", 3)

    match = PM_MATCHES.get(match_id)
    if not match or match["state"] != "toss":
        await query.answer("Invalid toss state.", show_alert=True)
        return

    if user.id != match["initiator"]:
        await query.answer("Only the initiator chooses toss.", show_alert=True)
        return

    coin_result = random.choice(["heads", "tails"])
    toss_winner = match["initiator"] if choice == coin_result else match["opponent"]
    toss_loser = match["opponent"] if toss_winner == match["initiator"] else match["initiator"]

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "bat_bowl_choice"

    await query.message.edit_text(
        f"The coin landed on {coin_result.capitalize()}!\n"
        f"{USERS[toss_winner]['name']} won the toss! Choose to Bat or Bowl first.",
        reply_markup=pm_bat_bowl_keyboard(match_id),
    )
    await query.answer()

# Bat/Bowl Choice Callback

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

    match.update({
        "state": "batting",
        "score": 0,
        "balls": 0,
        "wickets": 0,
        "innings": 1,
        "target": None,
        "batsman_choice": None,
        "bowler_choice": None,
        "superball": False,
    })

    await query.message.edit_text(
        f"Match started!\n\n"
        f"🏏 Batter: {USERS[match['batting_user']]['name']}\n"
        f"⚾ Bowler: {USERS[match['bowling_user']]['name']}\n\n"
        f"{USERS[match['batting_user']]['name']}, choose your batting number:",
        reply_markup=pm_number_keyboard("pm_batnum"),
    )
    await query.answer()

# Batsman Number Choice Callback

async def pm_batnum_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, num_str = query.data.split("_", 2)
    num = int(num_str)

    # Find match where user is batting and waiting for batsman choice
    match = None
    for m in PM_MATCHES.values():
        if m["state"] == "batting" and m["batting_user"] == user.id and m["batsman_choice"] is None:
            match = m
            break

    if not match:
        await query.answer("No active batting turn found or already chosen.", show_alert=True)
        return

    match["batsman_choice"] = num

    await query.answer(f"You chose {num} for batting.")

    # Inform group chat that batsman chose number, now bowler turn
    await context.bot.send_message(
        chat_id=match["group_chat_id"],
        text=f"{USERS[match['batting_user']]['name']} has chosen their number. Now {USERS[match['bowling_user']]['name']}, choose your bowling number:",
        reply_markup=pm_number_keyboard("pm_bowlnum"),
    )

# Bowler Number Choice Callback

async def pm_bowlnum_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, num_str = query.data.split("_", 2)
    num = int(num_str)

    # Find match where user is bowling and waiting for bowler choice
    match = None
    for m in PM_MATCHES.values():
        if m["state"] == "batting" and m["bowling_user"] == user.id and m["bowler_choice"] is None:
            match = m
            break

    if not match:
        await query.answer("No active bowling turn found or already chosen.", show_alert=True)
        return

    match["bowler_choice"] = num

    await query.answer(f"You chose {num} for bowling.")

    # Process ball result
    await process_pm_ball(context, match)

async def process_pm_ball(context: ContextTypes.DEFAULT_TYPE, match):
    chat_id = match["group_chat_id"]

    batsman_choice = match["batsman_choice"]
    bowler_choice = match["bowler_choice"]

    match["balls"] += 1
    over_num = (match["balls"] - 1) // 6
    ball_num = (match["balls"] - 1) % 6 + 1

    # Check for wicket
    is_out = batsman_choice == bowler_choice

    text_lines = []
    text_lines.append(f"Over: {over_num}.{ball_num}")
    text_lines.append(f"🏏 Batter: {USERS[match['batting_user']]['name']}")
    text_lines.append(f"⚾ Bowler: {USERS[match['bowling_user']]['name']}")
    text_lines.append(f"{USERS[match['batting_user']]['name']} Bat {batsman_choice}")
    text_lines.append(f"{USERS[match['bowling_user']]['name']} Bowl {bowler_choice}")

    if is_out:
        match["wickets"] += 1
        text_lines.append("\n" + random.choice(RUN_COMMENTARY["out"]))
        if match["innings"] == 1:
            # Set target for second innings
            match["target"] = match["score"]
            # Swap batting and bowling
            match["batting_user"], match["bowling_user"] = match["bowling_user"], match["batting_user"]
            match["score"] = 0
            match["balls"] = 0
            match["wickets"] = 0
            match["innings"] = 2
            match["batsman_choice"] = None
            match["bowler_choice"] = None
            text_lines.append(f"\n{USERS[match['bowling_user']]['name']} sets a target of {match['target'] + 1}")
            text_lines.append(f"{USERS[match['batting_user']]['name']} will now Bat and {USERS[match['bowling_user']]['name']} will now Bowl!")
        else:
            # Second innings wicket, match ends
            if match["score"] > match["target"]:
                winner = USERS[match["batting_user"]]["name"]
            elif match["score"] < match["target"]:
                winner = USERS[match["bowling_user"]]["name"]
            else:
                # Tie triggers superball
                match["superball"] = True
                match["batsman_choice"] = None
                match["bowler_choice"] = None
                text_lines.append("\nMatch tied! Superball time! Both players get one ball each.")
                # Prompt batsman for superball choice
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{USERS[match['batting_user']]['name']}, choose your batting number for Superball:",
                    reply_markup=pm_number_keyboard("pm_batnum"),
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{USERS[match['bowling_user']]['name']}, wait for your turn to bowl.",
                )
                await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
                return
            # Declare winner
            text_lines.append(f"\n🏆 {winner} won the match!")
            await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
            # Handle bet payout
            if match["bet"] > 0:
                if winner == USERS[match["batting_user"]]["name"]:
                    USERS[match["batting_user"]]["coins"] += match["bet"] * 2
                else:
                    USERS[match["bowling_user"]]["coins"] += match["bet"] * 2
            # Clean up
            del PM_MATCHES[match["match_id"]]
            USER_PM_MATCHES[match["batting_user"]].discard(match["match_id"])
            USER_PM_MATCHES[match["bowling_user"]].discard(match["match_id"])
            GROUP_PM_MATCHES[chat_id].discard(match["match_id"])
            return
    else:
        match["score"] += batsman_choice
        text_lines.append(f"\nTotal Score : {match['score']} Runs")
        text_lines.append(f"Next Move : {USERS[match['batting_user']]['name']} Continue your Bat!")

    # Reset choices for next ball
    match["batsman_choice"] = None
    match["bowler_choice"] = None

    await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))

    # Prompt batsman for next choice
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{USERS[match['batting_user']]['name']}, choose your batting number:",
        reply_markup=pm_number_keyboard("pm_batnum"),
    )
# CCL Mode Keyboards

def ccl_join_cancel_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Join ✅", callback_data=f"ccl_join_{match_id}"),
            InlineKeyboardButton("Cancel ❌", callback_data=f"ccl_cancel_{match_id}")
        ]]
    )

def ccl_toss_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Heads", callback_data=f"ccl_toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"ccl_toss_tails_{match_id}")
        ]]
    )

def ccl_bat_bowl_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Bat 🏏", callback_data=f"ccl_bat_{match_id}"),
            InlineKeyboardButton("Bowl ⚾", callback_data=f"ccl_bowl_{match_id}")
        ]]
    )

def ccl_batting_keyboard():
    buttons = [
        [InlineKeyboardButton(str(n), callback_data=f"ccl_batnum_{n}") for n in [0, 1, 2]],
        [InlineKeyboardButton(str(n), callback_data=f"ccl_batnum_{n}") for n in [3, 4, 6]],
    ]
    return InlineKeyboardMarkup(buttons)

def ccl_bowling_keyboard():
    types = ["rs", "bouncer", "yorker", "short", "slower", "knuckle"]
    buttons = []
    row = []
    for i, t in enumerate(types, 1):
        row.append(InlineKeyboardButton(t.capitalize(), callback_data=f"ccl_bowltype_{t}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

# /ccl Command Handler

async def ccl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ CCL matches can only be started in groups.")
        return

    ensure_user(user)

    # Check if user already in a CCL match in this group
    for match_id in USER_CCL_MATCH.get(user.id, set()) if USER_CCL_MATCH.get(user.id) else []:
        match = CCL_MATCHES.get(match_id)
        if match and match["group_chat_id"] == chat.id and match["state"] != "finished":
            await update.message.reply_text("You already have an active CCL match in this group.")
            return

    match_id = str(uuid.uuid4())
    CCL_MATCHES[match_id] = {
        "match_id": match_id,
        "group_chat_id": chat.id,
        "initiator": user.id,
        "opponent": None,
        "state": "waiting_join",
        "toss_winner": None,
        "toss_loser": None,
        "batting_user": None,
        "bowling_user": None,
        "score": 0,
        "balls": 0,
        "wickets": 0,
        "innings": 1,
        "target": None,
        "batsman_choice": None,
        "bowler_choice": None,
        "superball": False,
    }
    USER_CCL_MATCH[user.id] = match_id
    GROUP_CCL_MATCH.setdefault(chat.id, set()).add(match_id)

    await update.message.reply_text(
        f"🏏 CCL Cricket game has been started by {USERS[user.id]['name']}!\nPress Join below to play.",
        reply_markup=ccl_join_cancel_keyboard(match_id),
    )

# Join Callback

async def ccl_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "waiting_join":
        await query.answer("Match not available to join.", show_alert=True)
        return

    if user.id == match["initiator"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return

    if match["opponent"]:
        await query.answer("Match already has an opponent.", show_alert=True)
        return

    ensure_user(user)

    match["opponent"] = user.id
    match["state"] = "toss"

    USER_CCL_MATCH[user.id] = match_id

    await query.message.edit_text(
        f"Match started between {USERS[match['initiator']]['name']} and {USERS[user.id]['name']}!\n"
        f"{USERS[match['initiator']]['name']}, choose Heads or Tails for the toss.",
        reply_markup=ccl_toss_keyboard(match_id),
    )
    await query.answer()

# Cancel Callback

async def ccl_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    match = CCL_MATCHES.get(match_id)
    if not match:
        await query.answer("Match not found or already ended.", show_alert=True)
        return

    if user.id != match["initiator"]:
        await query.answer("Only the initiator can cancel.", show_alert=True)
        return

    chat_id = match["group_chat_id"]

    del CCL_MATCHES[match_id]
    USER_CCL_MATCH[match["initiator"]] = None
    if match.get("opponent"):
        USER_CCL_MATCH[match["opponent"]] = None
    GROUP_CCL_MATCH[chat_id].discard(match_id)

    await query.message.edit_text("The CCL match has been cancelled by the initiator.")
    await query.answer()

# Toss Callback

async def ccl_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, choice, match_id = query.data.split("_", 3)

    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "toss":
        await query.answer("Invalid toss state.", show_alert=True)
        return

    if user.id != match["initiator"]:
        await query.answer("Only the initiator chooses toss.", show_alert=True)
        return

    coin_result = random.choice(["heads", "tails"])
    toss_winner = match["initiator"] if choice == coin_result else match["opponent"]
    toss_loser = match["opponent"] if toss_winner == match["initiator"] else match["initiator"]

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "bat_bowl_choice"

    await query.message.edit_text(
        f"The coin landed on {coin_result.capitalize()}!\n"
        f"{USERS[toss_winner]['name']} won the toss! Choose to Bat or Bowl first.",
        reply_markup=ccl_bat_bowl_keyboard(match_id),
    )
    await query.answer()

# Bat/Bowl Choice Callback

async def ccl_bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, choice, match_id = query.data.split("_", 2)

    match = CCL_MATCHES.get(match_id)
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

    match.update({
        "state": "batting",
        "score": 0,
        "balls": 0,
        "wickets": 0,
        "innings": 1,
        "target": None,
        "batsman_choice": None,
        "bowler_choice": None,
        "superball": False,
    })

    # Tag batsman and bowler in group chat and prompt them to send choices in DM
    batting_mention = f"[{USERS[match['batting_user']]['name']}](tg://user?id={match['batting_user']})"
    bowling_mention = f"[{USERS[match['bowling_user']]['name']}](tg://user?id={match['bowling_user']})"

    await query.message.edit_text(
        f"Match started!\n\n"
        f"🏏 Batter: {batting_mention}\n"
        f"⚾ Bowler: {bowling_mention}\n\n"
        f"{batting_mention} and {bowling_mention}, please send your choices in DM to me.",
        parse_mode="Markdown",
    )
    # Send DM to batsman
    try:
        await context.bot.send_message(
            chat_id=match["batting_user"],
            text="Please choose your batting number:",
            reply_markup=ccl_batting_keyboard(),
        )
    except:
        await query.message.reply_text(f"Cannot send DM to {batting_mention}. Please start a chat with me first.", parse_mode="Markdown")
    # Send DM to bowler
    try:
        await context.bot.send_message(
            chat_id=match["bowling_user"],
            text="Please choose your bowling type:",
            reply_markup=ccl_bowling_keyboard(),
        )
    except:
        await query.message.reply_text(f"Cannot send DM to {bowling_mention}. Please start a chat with me first.", parse_mode="Markdown")

    await query.answer()

# DM Handlers for batsman and bowler choices

async def ccl_batnum_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, num_str = query.data.split("_", 2)
    num = int(num_str)

    match_id = USER_CCL_MATCH.get(user.id)
    if not match_id:
        await query.answer("You are not in an active CCL match.", show_alert=True)
        return

    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "batting" or match["batting_user"] != user.id:
        await query.answer("Not your turn to bat or invalid match state.", show_alert=True)
        return

    if match["batsman_choice"] is not None:
        await query.answer("You already chose your batting number.", show_alert=True)
        return

    match["batsman_choice"] = num
    await query.answer(f"You chose {num} for batting.")

    # Check if bowler has chosen
    if match["bowler_choice"] is not None:
        await process_ccl_ball(context, match)
    else:
        # Prompt bowler to choose if not chosen yet
        try:
            await context.bot.send_message(
                chat_id=match["bowling_user"],
                text="Waiting for you to choose bowling type:",
                reply_markup=ccl_bowling_keyboard(),
            )
        except:
            pass

async def ccl_bowltype_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, bowl_type = query.data.split("_", 2)

    match_id = USER_CCL_MATCH.get(user.id)
    if not match_id:
        await query.answer("You are not in an active CCL match.", show_alert=True)
        return

    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "batting" or match["bowling_user"] != user.id:
        await query.answer("Not your turn to bowl or invalid match state.", show_alert=True)
        return

    if match["bowler_choice"] is not None:
        await query.answer("You already chose your bowling type.", show_alert=True)
        return

    if bowl_type not in BOWLING_TYPE_TO_NUMBER:
        await query.answer("Invalid bowling type.", show_alert=True)
        return

    match["bowler_choice"] = bowl_type
    await query.answer(f"You chose {bowl_type} for bowling.")

    # Check if batsman has chosen
    if match["batsman_choice"] is not None:
        await process_ccl_ball(context, match)
    else:
        # Prompt batsman to choose if not chosen yet
        try:
            await context.bot.send_message(
                chat_id=match["batting_user"],
                text="Waiting for you to choose batting number:",
                reply_markup=ccl_batting_keyboard(),
            )
        except:
            pass

# Process ball for CCL mode with suspense and delays

async def process_ccl_ball(context: ContextTypes.DEFAULT_TYPE, match):
    chat_id = match["group_chat_id"]
    batsman_choice = match["batsman_choice"]
    bowler_choice_type = match["bowler_choice"]

    match["balls"] += 1
    over_num = (match["balls"] - 1) // 6 + 1
    ball_num = (match["balls"] - 1) % 6 + 1

    # Announce over and ball
    await context.bot.send_message(chat_id=chat_id, text=f"Over {over_num}")
    await asyncio.sleep(1)
    await context.bot.send_message(chat_id=chat_id, text=f"Ball {ball_num}")
    await asyncio.sleep(1)

    # Bowling type message with GIF placeholder
    bowling_text, bowling_gif = BOWLING_COMMENTARY.get(bowler_choice_type, ("", None))
    await context.bot.send_message(chat_id=chat_id, text=f"{USERS[match['bowling_user']]['name']} Bowled A {bowler_choice_type.capitalize()}")
    # Uncomment to send GIF if you have URLs
    # if bowling_gif:
    #     await context.bot.send_animation(chat_id=chat_id, animation=bowling_gif)
    await asyncio.sleep(random.randint(5,7))  # suspense delay

    # Determine out or runs
    is_out = batsman_choice == BOWLING_TYPE_TO_NUMBER.get(bowler_choice_type, -1)

    if is_out:
        run_text = random.choice(RUN_COMMENTARY["out"])
        match["wickets"] += 1
        result_text = f"{run_text} It's Out! 💥"
    else:
        run_text = random.choice(RUN_COMMENTARY.get(str(batsman_choice), ["Runs scored!"]))
        match["score"] += batsman_choice
        result_text = f"{run_text} {batsman_choice} run(s) scored."

    await context.bot.send_message(chat_id=chat_id, text=result_text)
    await asyncio.sleep(1)

    # Score update
    await context.bot.send_message(chat_id=chat_id, text=f"Score: {match['score']} Runs, {match['wickets']} Wickets")

    # Reset choices for next ball
    match["batsman_choice"] = None
    match["bowler_choice"] = None

    # Check innings end conditions
    if match["balls"] >= 6 or match["wickets"] >= 1:
        if match["innings"] == 1:
            # Switch innings
            match["innings"] = 2
            match["target"] = match["score"] + 1
            match["balls"] = 0
            match["wickets"] = 0
            match["score"] = 0
            match["batting_user"], match["bowling_user"] = match["bowling_user"], match["batting_user"]
            await context.bot.send_message(chat_id=chat_id, text=f"Innings over! Target for second innings: {match['target']} runs.")
            await context.bot.send_message(chat_id=chat_id,
                text=f"Second innings started!\n🏏 Batter: {USERS[match['batting_user']]['name']}\n⚾ Bowler: {USERS[match['bowling_user']]['name']}")
        else:
            # Match end
            if match["score"] >= match["target"]:
                winner = USERS[match["batting_user"]]["name"]
            else:
                winner = USERS[match["bowling_user"]]["name"]
            await context.bot.send_message(chat_id=chat_id, text=f"🏆 {winner} won the match!")
            # Clean up
            del CCL_MATCHES[match["match_id"]]
            USER_CCL_MATCH[match["batting_user"]] = None
            USER_CCL_MATCH[match["bowling_user"]] = None
            GROUP_CCL_MATCH[chat_id].discard(match["match_id"])
            return

    # Tag players and prompt next choices in DM
    batting_mention = f"[{USERS[match['batting_user']]['name']}](tg://user?id={match['batting_user']})"
    bowling_mention = f"[{USERS[match['bowling_user']]['name']}](tg://user?id={match['bowling_user']})"
    await context.bot.send_message(chat_id=chat_id,
        text=f"{batting_mention} and {bowling_mention}, please send your next choices in DM.",
        parse_mode="Markdown")

    # Prompt batsman DM
    try:
        await context.bot.send_message(
            chat_id=match["batting_user"],
            text="Choose your batting number:",
            reply_markup=ccl_batting_keyboard(),
        )
    except:
        pass

    # Prompt bowler DM
    try:
        await context.bot.send_message(
            chat_id=match["bowling_user"],
            text="Choose your bowling type:",
            reply_markup=ccl_bowling_keyboard(),
        )
    except:
        pass
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Use /help to see available commands.")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern=r"^leaderboard_\d$"))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("help", help_command))

    # PM mode handlers
    application.add_handler(CommandHandler("pm", pm_command))
    application.add_handler(CallbackQueryHandler(pm_join_callback, pattern=r"^pm_join_"))
    application.add_handler(CallbackQueryHandler(pm_cancel_callback, pattern=r"^pm_cancel_"))
    application.add_handler(CallbackQueryHandler(pm_toss_choice_callback, pattern=r"^pm_toss_"))
    application.add_handler(CallbackQueryHandler(pm_bat_bowl_choice_callback, pattern=r"^pm_bat_|^pm_bowl_"))
    application.add_handler(CallbackQueryHandler(pm_batnum_choice_callback, pattern=r"^pm_batnum_"))
    application.add_handler(CallbackQueryHandler(pm_bowlnum_choice_callback, pattern=r"^pm_bowlnum_"))

    # CCL mode handlers
    application.add_handler(CommandHandler("ccl", ccl_command))
    application.add_handler(CallbackQueryHandler(ccl_join_callback, pattern=r"^ccl_join_"))
    application.add_handler(CallbackQueryHandler(ccl_cancel_callback, pattern=r"^ccl_cancel_"))
    application.add_handler(CallbackQueryHandler(ccl_toss_choice_callback, pattern=r"^ccl_toss_"))
    application.add_handler(CallbackQueryHandler(ccl_bat_bowl_choice_callback, pattern=r"^ccl_bat_|^ccl_bowl_"))
    application.add_handler(CallbackQueryHandler(ccl_batnum_choice_callback, pattern=r"^ccl_batnum_"))
    application.add_handler(CallbackQueryHandler(ccl_bowltype_choice_callback, pattern=r"^ccl_bowltype_"))

    # Unknown commands handler
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Load users from DB on startup
    application.job_queue.run_once(lambda ctx: load_users(), 0)

    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()

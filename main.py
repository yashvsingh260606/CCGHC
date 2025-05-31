
# -*- coding: utf-8 -*-

"""
CCG HandCricket Telegram Bot with MongoDB storage
Features:
- Multiple simultaneous matches per player and per group
- PvP matches with bets and toss
- Gameplay via inline keyboard buttons
- Coin economy with 💰 emoji
- Commands: /start, /help, /register, /profile, /daily, /leaderboard, /add (admin)
- Messages formatted with emojis and bold text for mobile clarity
"""

import logging
import random
import datetime
from typing import Optional, Dict, List
from pymongo import MongoClient
from pymongo.collection import Collection
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    User,
    Chat,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ------------------------------
# Part 1: Imports, MongoDB connection, user data handling, basic commands
# ------------------------------

BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
MONGO_URL = "mongodb://mongo:GhpHMiZizYnvJfKIQKxoDbRyzBCpqEyC@mainline.proxy.rlwy.net:54853"

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Connect to MongoDB
mongo_client = MongoClient(MONGO_URL)
db = mongo_client.ccg_handcricket

users_col: Collection = db.users
matches_col: Collection = db.matches

COINS_EMOJI = "💰"
TOSS_EMOJIS = {"heads": "🪙 Heads", "tails": "🎲 Tails"}
BAT_EMOJI = "🏏"
WICKET_EMOJI = "💥"
WAIT_EMOJI = "⌛"
TOSS_WIN_EMOJI = "🎉"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    msg = (
        f"👋 **Hello, {user.first_name}!**\n\n"
        f"Welcome to *CCG HandCricket* {BAT_EMOJI}\n"
        f"Use /help to see all commands and start your cricket journey!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        f"**CCG HandCricket Commands:**\n\n"
        f"/start - Welcome message\n"
        f"/help - Show this help\n"
        f"/register - Register and get 4000 {COINS_EMOJI}\n"
        f"/daily - Claim daily 2000 {COINS_EMOJI}\n"
        f"/profile - Show your profile and stats\n"
        f"/leaderboard - Show top players by coins and wins\n"
        f"/pm <bet> - Start a match in group with optional bet\n"
        f"/add <user_id> <amount> - (Admin only) Add coins\n\n"
        f"⚠️ *Note:* /pm only works in groups.\n"
        f"Multiple matches per user and group supported!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def ensure_user(user: User):
    """Ensure user document exists in MongoDB"""
    data = users_col.find_one({"user_id": user.id})
    if not data:
        users_col.insert_one(
            {
                "user_id": user.id,
                "name": user.first_name,
                "coins": 0,
                "wins": 0,
                "losses": 0,
                "registered": False,
                "last_daily": None,
            }
        )
    else:
        # Update name if changed
        if data.get("name") != user.first_name:
            users_col.update_one(
                {"user_id": user.id}, {"$set": {"name": user.first_name}}
            )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    user_data = users_col.find_one({"user_id": user.id})
    if user_data.get("registered"):
        await update.message.reply_text("You are already registered!")
        return
    users_col.update_one(
        {"user_id": user.id},
        {"$set": {"registered": True}, "$inc": {"coins": 4000}},
    )
    await update.message.reply_text(
        f"🎉 You have been registered and received 4000 {COINS_EMOJI}!"
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = users_col.find_one({"user_id": user.id})
    if not user_data or not user_data.get("registered", False):
        await update.message.reply_text(
            "You are not registered yet. Use /register to start playing."
        )
        return
    text = (
        f"**{user_data['name']}'s Profile:**\n\n"
        f"💰 Coins: {user_data.get('coins', 0)} {COINS_EMOJI}\n"
        f"🏆 Wins: {user_data.get('wins', 0)}\n"
        f"❌ Losses: {user_data.get('losses', 0)}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Claim daily 2000 coins, cooldown 24h"""
    user = update.effective_user
    user_data = users_col.find_one({"user_id": user.id})
    if not user_data or not user_data.get("registered", False):
        await update.message.reply_text(
            "You are not registered yet. Use /register to start playing."
        )
        return
    now = datetime.datetime.utcnow()
    last_daily = user_data.get("last_daily")
    if last_daily:
        last_daily_dt = last_daily if isinstance(last_daily, datetime.datetime) else datetime.datetime.strptime(last_daily, "%Y-%m-%dT%H:%M:%S.%f")
        diff = (now - last_daily_dt).total_seconds()
        if diff < 86400:
            await update.message.reply_text(
                "⌛ You have already claimed your daily reward. Try again later."
            )
            return
    users_col.update_one(
        {"user_id": user.id},
        {"$set": {"last_daily": now.isoformat()}, "$inc": {"coins": 2000}},
    )
    await update.message.reply_text(
        f"🎉 You received your daily 2000 {COINS_EMOJI}! Come back tomorrow for more."
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard with coins and wins, toggle with buttons"""
    chat = update.effective_chat
    # Fetch top 10 coins and wins
    top_coins = list(
        users_col.find({"registered": True}).sort("coins", -1).limit(10)
    )
    top_wins = list(users_col.find({"registered": True}).sort("wins", -1).limit(10))

    context.chat_data["leaderboard_coins"] = top_coins
    context.chat_data["leaderboard_wins"] = top_wins
    context.chat_data["leaderboard_page"] = "coins"

    text = format_leaderboard_text(top_coins, "Coins")
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("← Coins", callback_data="leaderboard_coins"),
                InlineKeyboardButton("Wins →", callback_data="leaderboard_wins"),
            ]
        ]
    )
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add coins to a user"""
    user = update.effective_user
    if user.id not in (  # Put your admin IDs here
        123456789,
    ):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except Exception:
        await update.message.reply_text("User ID and amount must be numbers.")
        return
    target_user = users_col.find_one({"user_id": target_id})
    if not target_user:
        await update.message.reply_text("User not found.")
        return
    users_col.update_one({"user_id": target_id}, {"$inc": {"coins": amount}})
    await update.message.reply_text(
        f"✅ Added {amount} {COINS_EMOJI} to {target_user['name']}."
    )


def format_leaderboard_text(data: List[Dict], mode: str) -> str:
    text = f"**Leaderboard by {mode}:**\n\n"
    if not data:
        return text + "No data available."
    for i, u in enumerate(data, 1):
        if mode == "Coins":
            text += f"{i}. {u['name']} — {u['coins']} {COINS_EMOJI}\n"
        else:
            text += f"{i}. {u['name']} — {u['wins']} Wins\n"
    return text


# ------------------------------
# Part 2: Utility functions, coin economy logic, user data updates
# ------------------------------

def create_number_keyboard() -> InlineKeyboardMarkup:
    # Two rows: [1️⃣, 2️⃣, 3️⃣], [4️⃣, 5️⃣, 6️⃣]
    buttons = [
        [InlineKeyboardButton("1️⃣", callback_data="num_1"),
         InlineKeyboardButton("2️⃣", callback_data="num_2"),
         InlineKeyboardButton("3️⃣", callback_data="num_3")],
        [InlineKeyboardButton("4️⃣", callback_data="num_4"),
         InlineKeyboardButton("5️⃣", callback_data="num_5"),
         InlineKeyboardButton("6️⃣", callback_data="num_6")],
    ]
    return InlineKeyboardMarkup(buttons)


def create_join_button(match_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join", callback_data=f"join_{match_id}")]]
    )


def create_toss_buttons(match_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Heads 🪙", callback_data=f"tosschoice_{match_id}_heads"),
                InlineKeyboardButton("Tails 🎲", callback_data=f"tosschoice_{match_id}_tails"),
            ]
        ]
    )


def user_can_play(user_id: int) -> bool:
    """Check if user is registered and has coins to play"""
    user = users_col.find_one({"user_id": user_id})
    return user is not None and user.get("registered", False)


def get_active_matches_for_user_in_chat(user_id: int, chat_id: int) -> List[Dict]:
    """Return list of active matches for user in a specific chat"""
    active_matches = list(
        matches_col.find(
            {
                "players": user_id,
                "chat_id": chat_id,
                "state": {"$ne": "ended"},
            }
        )
    )
    return active_matches


def get_match_by_id(match_id: str) -> Optional[Dict]:
    return matches_col.find_one({"match_id": match_id})


def save_match(match: Dict):
    matches_col.replace_one({"match_id": match["match_id"]}, match, upsert=True)


def update_user_coins(user_id: int, amount: int):
    users_col.update_one({"user_id": user_id}, {"$inc": {"coins": amount}})


def update_user_wins(user_id: int):
    users_col.update_one({"user_id": user_id}, {"$inc": {"wins": 1}})


def update_user_losses(user_id: int):
    users_col.update_one({"user_id": user_id}, {"$inc": {"losses": 1}})


# ------------------------------
# Part 3: /pm command, join match button, toss selection, inline keyboards
# ------------------------------

async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new match with optional bet"""
    chat: Chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❗ This command works only in groups.")
        return

    await ensure_user(user)
    user_data = users_col.find_one({"user_id": user.id})
    if not user_data.get("registered", False):
        await update.message.reply_text(
            "You must register first with /register to play."
        )
        return

    bet = 0
    if context.args and context.args[0].isdigit():
        bet = int(context.args[0])
        if bet > user_data.get("coins", 0):
            await update.message.reply_text(
                f"❌ You don't have enough {COINS_EMOJI} to bet {bet}."
            )
            return

    # Allow multiple matches per user and group
    match_id = f"{chat.id}_{user.id}_{random.randint(1000,9999)}"
    match = {
        "match_id": match_id,
        "chat_id": chat.id,
        "players": [user.id],
        "bet": bet,
        "state": "waiting",  # waiting -> toss -> bat_or_bowl -> batting -> ended
        "initiator": user.id,
        "scores": {user.id: 0},
        "wickets": {user.id: 0},
        "current_over": 0.0,
        "batter": None,
        "bowler": None,
        "toss_winner": None,
        "toss_choice": None,
        "batting_order": [],
        "batting_numbers": {},
        "target": None,
        "superball": False,
        "superball_choices": {},
        "balls_faced": {user.id: 0},
    }
    matches_col.insert_one(match)

    join_keyboard = create_join_button(match_id)
    bet_text = f"Bet: {bet} {COINS_EMOJI}" if bet > 0 else "No bet"
    msg = (
        f"{BAT_EMOJI} **Cricket game started!**\n\n"
        f"Player *{user.first_name}* started a match.\n"
        f"{bet_text}\n\n"
        f"Press *Join* below to play!"
    )
    await update.message.reply_text(msg, reply_markup=join_keyboard, parse_mode="Markdown")


async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Join button press"""
    query = update.callback_query
    user = query.from_user
    data = query.data  # join_<match_id>
    _, match_id = data.split("_", 1)

    match = get_match_by_id(match_id)
    if not match:
        await query.answer("❌ Match not found or already started.", show_alert=True)
        return

    if match["state"] != "waiting":
        await query.answer("❌ Match already started.", show_alert=True)
        return

    if user.id == match["players"][0]:
        await query.answer("❌ You cannot join your own match.", show_alert=True)
        return

    # Check if user already in active match in this chat
    active = get_active_matches_for_user_in_chat(user.id, match["chat_id"])
    if active:
        await query.answer(
            "❌ You already have an active match in this group. Finish it first.",
            show_alert=True,
        )
        return

    # Check if user has enough coins to join bet
    user_data = users_col.find_one({"user_id": user.id})
    if not user_data or not user_data.get("registered", False):
        await query.answer("❌ You must register first with /register.", show_alert=True)
        return

    bet = match.get("bet", 0)
    if bet > 0 and user_data.get("coins", 0) < bet:
        await query.answer(
            f"❌ You don't have enough {COINS_EMOJI} to join this bet ({bet}).",
            show_alert=True,
        )
        return

    # Add player to match
    match["players"].append(user.id)
    match["scores"][user.id] = 0
    match["wickets"][user.id] = 0
    match["balls_faced"][user.id] = 0
    match["state"] = "toss"
    save_match(match)

    initiator_name = users_col.find_one({"user_id": match["initiator"]})["name"]
    opponent_name = user.first_name

    # Ask initiator to choose heads or tails
    toss_keyboard = create_toss_buttons(match_id)
    text = (
        f"👥 Match between *{initiator_name}* and *{opponent_name}* has started!\n\n"
        f"{initiator_name}, choose Heads or Tails for the toss."
    )
    await query.edit_message_text(text, reply_markup=toss_keyboard, parse_mode="Markdown")
    await query.answer()


async def toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle toss choice by initiator"""
    query = update.callback_query
    user = query.from_user
    data = query.data  # tosschoice_<match_id>_<choice>
    _, match_id, choice = data.split("_", 2)

    match = get_match_by_id(match_id)
    if not match:
        await query.answer("❌ Match not found.", show_alert=True)
        return

    if match["state"] != "toss":
        await query.answer("❌ Toss already decided.", show_alert=True)
        return

    if user.id != match["initiator"]:
        await query.answer("❌ Only the match initiator can choose toss.", show_alert=True)
        return

    toss_result = random.choice(["heads", "tails"])
    match["toss_choice"] = choice
    match["toss_result"] = toss_result

    initiator_name = users_col.find_one({"user_id": match["initiator"]})["name"]
    opponent_id = [pid for pid in match["players"] if pid != match["initiator"]][0]
    opponent_name = users_col.find_one({"user_id": opponent_id})["name"]

    if choice == toss_result:
        winner_id = match["initiator"]
        winner_name = initiator_name
    else:
        winner_id = opponent_id
        winner_name = opponent_name

    match["toss_winner"] = winner_id
    match["state"] = "bat_or_bowl"
    save_match(match)

    # Show toss winner message + ask for Bat or Bowl
    batbowl_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Bat 🏏", callback_data=f"batbowl_{match_id}_bat"),
                InlineKeyboardButton("Bowl ⚾", callback_data=f"batbowl_{match_id}_bowl"),
            ]
        ]
    )
    text = (
        f"🎲 Toss result: *{toss_result.capitalize()}*\n"
        f"{TOSS_WIN_EMOJI} *{winner_name}* won the toss and will choose to bat or bowl first."
    )
    await query.edit_message_text(text, reply_markup=batbowl_keyboard, parse_mode="Markdown")
    await query.answer()


async def batbowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Bat or Bowl choice by toss winner"""
    query = update.callback_query
    user = query.from_user
    data = query.data  # batbowl_<match_id>_<choice>
    _, match_id, choice = data.split("_", 2)

    match = get_match_by_id(match_id)
    if not match:
        await query.answer("❌ Match not found.", show_alert=True)
        return

    if match["state"] != "bat_or_bowl":
        await query.answer("❌ Bat/Bowl choice already made.", show_alert=True)
        return

    if user.id != match["toss_winner"]:
        await query.answer("❌ Only toss winner can choose.", show_alert=True)
        return

    players = match["players"]
    batter = match["toss_winner"] if choice == "bat" else [p for p in players if p != match["toss_winner"]][0]
    bowler = [p for p in players if p != batter][0]

    match["batter"] = batter
    match["bowler"] = bowler
    match["state"] = "batting"
    match["batting_order"] = [batter, bowler]
    match["current_over"] = 0.0
    match["scores"] = {pid: 0 for pid in players}
    match["wickets"] = {pid: 0 for pid in players}
    match["balls_faced"] = {pid: 0 for pid in players}
    match["batting_numbers"] = {}
    match["target"] = None
    match["superball"] = False
    match["superball_choices"] = {}
    save_match(match)

    batter_name = users_col.find_one({"user_id": batter})["name"]
    bowler_name = users_col.find_one({"user_id": bowler})["name"]

    text = (
        f"🏏 *{batter_name}* will bat first.\n"
        f"⚾ *{bowler_name}* will bowl.\n\n"
        f"{batter_name}, choose your number to bat:"
    )
    keyboard = create_number_keyboard()
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer()


# ------------------------------
# Part 4: Number selection handling, score updates, innings management, match result logic, main bot startup
# ------------------------------

async def number_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle batsman/bowler number choice"""
    query = update.callback_query
    user = query.from_user
    data = query.data  # num_<number>
    if not data.startswith("num_"):
        await query.answer()
        return
    num = int(data.split("_")[1])

    # Find active match where user is playing and expecting input
    match = None
    # We try to find the match by chat id and user
    chat_id = query.message.chat_id
    active_matches = list(
        matches_col.find(
            {
                "chat_id": chat_id,
                "players": user.id,
                "state": {"$in": ["batting", "superball"]},
            }
        )
    )
    if not active_matches:
        await query.answer("❌ You are not in an active match here.")
        return
    # If multiple matches, pick the one where user needs to pick number (batting_numbers)
    for m in active_matches:
        if user.id not in m.get("batting_numbers", {}):
            match = m
            break
    if not match:
        # Already picked number for all matches
        await query.answer("⌛ Waiting for the other player to choose...")
        return

    # Save user's number choice
    match["batting_numbers"][user.id] = num
    save_match(match)

    batter_id = match["batter"]
    bowler_id = match["bowler"]
    batter_name = users_col.find_one({"user_id": batter_id})["name"]
    bowler_name = users_col.find_one({"user_id": bowler_id})["name"]

    # Case 1: Only batsman chose number (bowler hasn't)
    if user.id == batter_id and bowler_id not in match["batting_numbers"]:
        # Show message batsman chose number, now bowler's turn
        text = (
            f"**{batter_name}** chose a number, now it's **{bowler_name}**'s turn {WAIT_EMOJI}"
        )
        await query.edit_message_text(text)
        await query.answer()
        return

    # Case 2: Only bowler chose number (batsman hasn't)
    if user.id == bowler_id and batter_id not in match["batting_numbers"]:
        text = (
            f"**{bowler_name}** chose a number, now it's **{batter_name}**'s turn {WAIT_EMOJI}"
        )
        await query.edit_message_text(text)
        await query.answer()
        return

    # Case 3: Both chose numbers - calculate outcome
    if batter_id in match["batting_numbers"] and bowler_id in match["batting_numbers"]:
        batter_num = match["batting_numbers"][batter_id]
        bowler_num = match["batting_numbers"][bowler_id]

        # Clear choices for next ball
        match["batting_numbers"] = {}

        # Increment balls faced for batter
        match["balls_faced"][batter_id] += 1

        # Calculate over.ball notation
        current_over_float = match.get("current_over", 0.0)
        whole = int(current_over_float)
        dec = int(round((current_over_float - whole) * 10))
        dec += 1
        if dec > 6:
            whole += 1
            dec = 1
        match["current_over"] = whole + dec / 10

        runs_scored = 0
        innings_over = False
        out_happened = False

        if batter_num == bowler_num:
            # Wicket!
            match["wickets"][batter_id] += 1
            out_happened = True
            runs_scored = 0
        else:
            runs_scored = batter_num
            match["scores"][batter_id] += runs_scored

        total_runs = match["scores"][batter_id]
        balls_faced = match["balls_faced"][batter_id]

        over_ball_text = f"{int(match['current_over'])}.{int((match['current_over']*10)%10)}"

        if out_happened:
            text = (
                f"Over: {over_ball_text}\n"
                f"{WICKET_EMOJI} Wicket!\n"
                f"**{batter_name}** played: {batter_num}\n"
                f"**{bowler_name}** played: {bowler_num}\n"
                f"Runs scored this ball: 0\n"
                f"Total runs: {total_runs}\n"
                f"Innings over."
            )
            innings_over = True
        else:
            text = (
                f"Over: {over_ball_text}\n"
                f"**{batter_name}** chose: {batter_num}\n"
                f"**{bowler_name}** chose: {bowler_num}\n"
                f"Runs scored this ball: {runs_scored}\n"
                f"Total runs: {total_runs}\n"
                f"Balls faced: {balls_faced}\n\n"
                f"Choose your next number:"
            )

        # Save updated match
        save_match(match)

        # Edit message with the appropriate text and keyboard
        if innings_over:
            # Handle innings over - switch innings or end match
            await query.edit_message_text(text, parse_mode="Markdown")
            await handle_innings_over(match, query)
        else:
            keyboard = create_number_keyboard()
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await query.answer()


async def handle_innings_over(match: Dict, query):
    """Manage innings switch or match end"""
    # Inning just ended, check if first or second inning
    if match.get("target") is None:
        # First innings ended, set target and swap roles
        batter = match["batter"]
        bowler = match["bowler"]
        target = match["scores"][batter]
        match["target"] = target
        # Swap batter and bowler
        match["batter"], match["bowler"] = bowler, batter
        match["scores"][match["batter"]] = 0
        match["balls_faced"][match["batter"]] = 0
        match["wickets"][match["batter"]] = 0
        match["current_over"] = 0.0
        match["batting_numbers"] = {}
        match["state"] = "batting"
        save_match(match)

        batter_name = users_col.find_one({"user_id": match["batter"]})["name"]
        bowler_name = users_col.find_one({"user_id": match["bowler"]})["name"]

        text = (
            f"{BAT_EMOJI} Innings over!\n"
            f"Target set: {target} runs\n\n"
            f"Now *{batter_name}* will bat and *{bowler_name}* will bowl.\n"
            f"{batter_name}, choose your number to bat:"
        )
        keyboard = create_number_keyboard()
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        await query.answer()
    else:
        # Second innings ended - decide winner or superball
        batter = match["batter"]
        bowler = match["bowler"]
        scores = match["scores"]
        target = match["target"]

        batter_score = scores[batter]
        opponent = bowler
        opponent_score = scores[opponent]

        if batter_score > target:
            # Batter wins
            await end_match(match, batter, query)
        elif batter_score == target:
            # Tie - superball
            match["state"] = "superball"
            match["batting_numbers"] = {}
            match["superball_choices"] = {}
            save_match(match)
            batter_name = users_col.find_one({"user_id": batter})["name"]
            bowler_name = users_col.find_one({"user_id": bowler})["name"]
            text = (
                f"🤝 Match tied! Going into Superball!\n\n"
                f"{batter_name} bats vs {bowler_name} bowls.\n"
                f"Choose your numbers:"
            )
            keyboard = create_number_keyboard()
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
            await query.answer()
        else:
            # Opponent wins
            await end_match(match, opponent, query)


async def end_match(match: Dict, winner_id: int, query):
    loser_id = [pid for pid in match["players"] if pid != winner_id][0]

    winner_name = users_col.find_one({"user_id": winner_id})["name"]
    loser_name = users_col.find_one({"user_id": loser_id})["name"]

    bet = match.get("bet", 0)

    # Update user stats and coins atomically
    users_col.update_one(
        {"user_id": winner_id},
        {"$inc": {"wins": 1, "coins": bet * 2}},
    )
    users_col.update_one(
        {"user_id": loser_id},
        {"$inc": {"losses": 1, "coins": -bet}},
    )

    # Mark match ended
    match["state"] = "ended"
    save_match(match)

    text = (
        f"🏆 Match ended!\n\n"
        f"Winner: *{winner_name}*\n"
        f"Loser: *{loser_name}*\n\n"
        f"Bet: {bet} {COINS_EMOJI}\n"
        f"{winner_name} wins {bet * 2} {COINS_EMOJI}!\n\n"
        f"Use /pm <bet> to start a new match."
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    await query.answer()


# ------------------------------
# Bot main startup and handlers
# ------------------------------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("pm", pm_command))

    # CallbackQuery handlers
    app.add_handler(CallbackQueryHandler(join_callback, pattern=r"^join_"))
    app.add_handler(CallbackQueryHandler(toss_choice_callback, pattern=r"^tosschoice_"))
    app.add_handler(CallbackQueryHandler(batbowl_choice_callback, pattern=r"^batbowl_"))
    app.add_handler(CallbackQueryHandler(number_choice_callback, pattern=r"^num_"))

    logger.info("CCG HandCricket Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()

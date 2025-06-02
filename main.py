import logging
import random
import uuid
import asyncio
from datetime import datetime, timedelta

import nest_asyncio
nest_asyncio.apply()

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
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

# Replace with your actual bot token and admin IDs
TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMIN_IDS = {123456789}  # Replace with your admin user IDs

MONGO_URL = "mongodb://mongo:GhpHMiZizYnvJfKIQKxoDbRyzBCpqEyC@mainline.proxy.rlwy.net:54853"
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.handcricket
users_collection = db.users

USERS = {}
USER_PM_MATCHES = {}
GROUP_PM_MATCHES = {}
PM_MATCHES = {}

USER_CCL_MATCH = {}
GROUP_CCL_MATCH = {}  # Stores single active match_id per group to enforce one match per group
CCL_MATCHES = {}

COINS_EMOJI = "🪙"

# Bowling types allowed in CCL mode and their mapped numbers
BOWLING_TYPES = {
    "rs": 0,
    "bouncer": 1,
    "yorker": 2,
    "short": 3,
    "slower": 4,
    "knuckle": 6,
}

BOWLING_COMMENTARY = {
    "rs": "Rs...",
    "bouncer": "Bouncer...",
    "yorker": "Yorker...",
    "short": "Short ball...",
    "slower": "Slower ball...",
    "knuckle": "Knuckle ball...",
}

RUN_GIFS = {
    "0": "https://media0.giphy.com/media/QtipHdYxYopX3W6vMs/giphy.gif",
    "4": "https://media0.giphy.com/media/3o7btXfjIjTcU64YdG/giphy.gif",
    "6": "https://media4.giphy.com/media/pbhDFQQfXRX8CTmZ4O/giphy.gif",
    "out": "https://media3.giphy.com/media/Wq3WRGe9N5HkSqjITT/giphy.gif",
    "halfcentury": "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif",
    "century": "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif"
}

RUN_COMMENTARY_CCL = {
    0: ["Dot Ball!", "No run.", "Well bowled, no run."],
    1: ["Quick single.", "One run taken.", "They sneak a single."],
    2: ["Two runs!", "Good running between the wickets.", "They pick up a couple."],
    3: ["Three runs!", "Great running, three!", "Three runs taken."],
    4: ["He smashed a Four!", "Beautiful boundary!", "Cracking shot for four!"],
    6: ["He Smoked It For A Six!", "Maximum!", "What a massive six!"],
    "out": ["It's Out!", "Bowled him!", "What a wicket!", "Caught behind!"],
}

RUN_COMMENTARY_PM = {
    1: ["Quick single.", "One run taken.", "They sneak a single."],
    2: ["Two runs!", "Good running between the wickets.", "They pick up a couple."],
    3: ["Three runs!", "Great running, three!", "Three runs taken."],
    4: ["He smashed a Four!", "Beautiful boundary!", "Cracking shot for four!"],
    5: ["Five runs! (Rare!)"],
    6: ["He Smoked It For A Six!", "Maximum!", "What a massive six!"],
    "0": ["Dot Ball!", "No run.", "Well bowled, no run."],
    "out": ["It's Out!", "Bowled him!", "What a wicket!", "Caught behind!"],
}

def get_username(user):
    return user.first_name or user.username or "Player"

def ensure_user(user):
    if user.id not in USERS:
        USERS[user.id] = {
            "user_id": user.id,
            "name": get_username(user),
            "coins": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "registered": False,
            "last_daily": None,
        }
        USER_PM_MATCHES[user.id] = set()
        USER_CCL_MATCH[user.id] = None

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

async def load_users():
    try:
        cursor = users_collection.find({})
        async for user in cursor:
            user_id = user.get("user_id") or user.get("_id")
            if not user_id:
                logger.warning(f"Skipping user without user_id: {user}")
                continue
            USERS[user_id] = user
            USER_PM_MATCHES[user_id] = set()
            USER_CCL_MATCH[user_id] = None
        logger.info("Users loaded successfully.")
    except Exception as e:
        logger.error(f"Error loading users: {e}", exc_info=True)

def profile_text(user_id):
    u = USERS.get(user_id, {})
    name = u.get("name", "Unknown")
    coins = u.get("coins", 0)
    wins = u.get("wins", 0)
    losses = u.get("losses", 0)
    ties = u.get("ties", 0)
    return (
        f"**{name}'s Profile**\n\n"
        f"Name: {name}\n"
        f"ID: {user_id}\n"
        f"Purse: {coins}{COINS_EMOJI}\n\n"
        f"Performance History:\n"
        f"Wins: {wins}\n"
        f"Losses: {losses}\n"
        f"Ties: {ties}\n"
    )

# Command Handlers

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
    text = ""
    if page == 1:
        text = "🏆 **Top 10 Richest Players by Coins:**\n\n"
        for i, u in enumerate(sorted_users[:10], 1):
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
    text = ""
    if page == 1:
        text = "🏆 **Top 10 Richest Players by Coins:**\n\n"
        for i, u in enumerate(sorted_users[:10], 1):
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
        "/ccl [bet] - Start a CCL match optionally with bet\n"
        "/profile - Show your profile\n"
        "/daily - Claim daily 2000 🪙 coins\n"
        "/leaderboard - Show leaderboard with coins and wins\n"
        "/endmatch - End ongoing CCL match in group (admin only)\n"
        "/help - Show this help message\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# PM Mode Keyboards (runs 1-6)

def pm_number_keyboard(prefix):
    # Two rows: 1-3 and 4-6
    buttons = [
        [InlineKeyboardButton(str(n), callback_data=f"{prefix}_{n}") for n in range(1, 4)],
        [InlineKeyboardButton(str(n), callback_data=f"{prefix}_{n}") for n in range(4, 7)],
    ]
    return InlineKeyboardMarkup(buttons)

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
        "milestone_50": False,
        "milestone_100": False,
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

    current_match = PM_MATCHES.get(match_id)
    if not current_match or current_match["state"] != "waiting_join":
        await query.answer("Match not available to join.", show_alert=True)
        return

    if user.id == current_match["initiator"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return

    if current_match["opponent"]:
        await query.answer("Match already has an opponent.", show_alert=True)
        return

    ensure_user(user)

    if current_match["bet"] > 0 and USERS[user.id]["coins"] < current_match["bet"]:
        await query.answer("You don't have enough coins to join this bet match.", show_alert=True)
        return

    current_match["opponent"] = user.id
    current_match["state"] = "toss"

    USER_PM_MATCHES.setdefault(user.id, set()).add(match_id)

    await query.message.edit_text(
        f"Match started between {USERS[current_match['initiator']]['name']} and {USERS[user.id]['name']}!\n"
        f"{USERS[current_match['initiator']]['name']}, choose Heads or Tails for the toss.",
        reply_markup=pm_toss_keyboard(match_id),
    )
    await query.answer()

# Cancel Callback

async def pm_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    current_match = PM_MATCHES.get(match_id)
    if not current_match:
        await query.answer("Match not found or already ended.", show_alert=True)
        return

    if user.id != current_match["initiator"]:
        await query.answer("Only the match initiator can cancel.", show_alert=True)
        return

    chat_id = current_match["group_chat_id"]

    # Refund bets if any
    if current_match["bet"] > 0:
        USERS[current_match["initiator"]]["coins"] += current_match["bet"]
        if current_match["opponent"]:
            USERS[current_match["opponent"]]["coins"] += current_match["bet"]

    del PM_MATCHES[match_id]
    USER_PM_MATCHES[current_match["initiator"]].discard(match_id)
    if current_match.get("opponent"):
        USER_PM_MATCHES[current_match["opponent"]].discard(match_id)
    GROUP_PM_MATCHES[chat_id].discard(match_id)

    await query.message.edit_text("The PM match has been cancelled by the initiator.")
    await query.answer()

# Toss Callback

async def pm_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, choice, match_id = query.data.split("_", 3)

    current_match = PM_MATCHES.get(match_id)
    if not current_match or current_match["state"] != "toss":
        await query.answer("Invalid toss state.", show_alert=True)
        return

    if user.id != current_match["initiator"]:
        await query.answer("Only the initiator chooses toss.", show_alert=True)
        return

    coin_result = random.choice(["heads", "tails"])
    toss_winner = current_match["initiator"] if choice == coin_result else current_match["opponent"]
    toss_loser = current_match["opponent"] if toss_winner == current_match["initiator"] else current_match["initiator"]

    current_match["toss_winner"] = toss_winner
    current_match["toss_loser"] = toss_loser
    current_match["state"] = "bat_bowl_choice"

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

    current_match = PM_MATCHES.get(match_id)
    if not current_match or current_match["state"] != "bat_bowl_choice":
        await query.answer("Invalid state for Bat/Bowl choice.", show_alert=True)
        return

    if user.id != current_match["toss_winner"]:
        await query.answer("Only toss winner can choose.", show_alert=True)
        return

    if choice == "bat":
        current_match["batting_user"] = current_match["toss_winner"]
        current_match["bowling_user"] = current_match["toss_loser"]
    else:
        current_match["batting_user"] = current_match["toss_loser"]
        current_match["bowling_user"] = current_match["toss_winner"]

    current_match.update({
        "state": "batting",
        "score": 0,
        "balls": 0,
        "wickets": 0,
        "innings": 1,
        "target": None,
        "batsman_choice": None,
        "bowler_choice": None,
        "milestone_50": False,
        "milestone_100": False,
    })

    await query.message.edit_text(
        f"Match started!\n\n"
        f"🏏 Batter: {USERS[current_match['batting_user']]['name']}\n"
        f"⚾ Bowler: {USERS[current_match['bowling_user']]['name']}\n\n"
        f"{USERS[current_match['batting_user']]['name']}, choose your batting number:",
        reply_markup=pm_number_keyboard("pm_batnum"),
    )
    await query.answer()

# Batsman Number Choice Callback

async def pm_batnum_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, num_str = query.data.split("_", 2)
    num = int(num_str)

    current_match = None
    for m in PM_MATCHES.values():
        if m["state"] == "batting" and m["batting_user"] == user.id and m["batsman_choice"] is None:
            current_match = m
            break

    if not current_match:
        await query.answer("No active batting turn found or already chosen.", show_alert=True)
        return

    current_match["batsman_choice"] = num
    await query.answer(f"You chose {num} for batting.")

    await context.bot.send_message(
        chat_id=current_match["group_chat_id"],
        text=f"{USERS[current_match['batting_user']]['name']} has chosen their number. Now {USERS[current_match['bowling_user']]['name']}, choose your bowling number:",
        reply_markup=pm_number_keyboard("pm_bowlnum"),
    )

# Bowler Number Choice Callback

async def pm_bowlnum_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, num_str = query.data.split("_", 2)
    num = int(num_str)

    current_match = None
    for m in PM_MATCHES.values():
        if m["state"] == "batting" and m["bowling_user"] == user.id and m["bowler_choice"] is None:
            current_match = m
            break

    if not current_match:
        await query.answer("No active bowling turn found or already chosen.", show_alert=True)
        return

    current_match["bowler_choice"] = num
    await query.answer(f"You chose {num} for bowling.")

    await process_pm_ball(context, current_match)

# Process each ball in PM mode with tie handling

async def process_pm_ball(context: ContextTypes.DEFAULT_TYPE, current_match):
    chat_id = current_match["group_chat_id"]

    batsman_choice = current_match["batsman_choice"]
    bowler_choice = current_match["bowler_choice"]

    current_match["balls"] += 1
    over_num = (current_match["balls"] - 1) // 6
    ball_num = (current_match["balls"] - 1) % 6 + 1

    is_out = batsman_choice == bowler_choice

    text_lines = [
        f"Over: {over_num}.{ball_num}",
        f"🏏 Batter: {USERS[current_match['batting_user']]['name']}",
        f"⚾ Bowler: {USERS[current_match['bowling_user']]['name']}",
        f"{USERS[current_match['batting_user']]['name']} Bat {batsman_choice}",
        f"{USERS[current_match['bowling_user']]['name']} Bowl {bowler_choice}",
    ]

    milestone_gif = None
    milestone_text = None

    if is_out:
        current_match["wickets"] += 1
        text_lines.append("\n" + random.choice(RUN_COMMENTARY_PM["out"]))
        gif_url = RUN_GIFS["out"]
    else:
        current_match["score"] += batsman_choice
        run_comment_list = RUN_COMMENTARY_PM.get(batsman_choice, ["Runs scored!"])
        text_lines.append(f"\nTotal Score : {current_match['score']} Runs")
        text_lines.append(random.choice(run_comment_list))
        gif_url = RUN_GIFS.get(str(batsman_choice), None)

        # Milestone checks
        if not current_match.get("milestone_50") and current_match["score"] >= 50:
            milestone_gif = RUN_GIFS["halfcentury"]
            milestone_text = "🏏 Half-century! 50 runs!"
            current_match["milestone_50"] = True
        if not current_match.get("milestone_100") and current_match["score"] >= 100:
            milestone_gif = RUN_GIFS["century"]
            milestone_text = "💯 Century! 100 runs!"
            current_match["milestone_100"] = True

    # First Innings: continues until wicket falls
    if current_match["innings"] == 1:
        if current_match["wickets"] >= 1:
            current_match["target"] = current_match["score"]
            current_match["batting_user"], current_match["bowling_user"] = current_match["bowling_user"], current_match["batting_user"]
            current_match["score"] = 0
            current_match["balls"] = 0
            current_match["wickets"] = 0
            current_match["innings"] = 2
            current_match["batsman_choice"] = None
            current_match["bowler_choice"] = None
            current_match["milestone_50"] = False
            current_match["milestone_100"] = False
            text_lines.append(f"\nInnings over! Target for second innings: {current_match['target'] + 1}")
            text_lines.append(f"{USERS[current_match['batting_user']]['name']} will now Bat and {USERS[current_match['bowling_user']]['name']} will Bowl!")
            await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
            if milestone_gif:
                await context.bot.send_animation(chat_id=chat_id, animation=milestone_gif, caption=milestone_text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{USERS[current_match['batting_user']]['name']}, choose your batting number:",
                reply_markup=pm_number_keyboard("pm_batnum"),
            )
            return
    else:
        # Second Innings: ends on chase, wicket, or tie
        target_plus_one = current_match["target"] + 1
        if current_match["score"] > current_match["target"]:
            winner_id = current_match["batting_user"]
            loser_id = current_match["bowling_user"]
            result_text = f"🏆 {USERS[winner_id]['name']} won the match!"
        elif current_match["score"] == current_match["target"]:
            # Tie condition
            winner_id = None
            loser_id = None
            result_text = "🤝 The match is a tie!"
        elif current_match["wickets"] >= 1:
            winner_id = current_match["bowling_user"]
            loser_id = current_match["batting_user"]
            result_text = f"🏆 {USERS[winner_id]['name']} won the match!"
        else:
            winner_id = None
            loser_id = None
            result_text = None

        if result_text:
            text_lines.append(f"\n{result_text}")
            await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
            if milestone_gif:
                await context.bot.send_animation(chat_id=chat_id, animation=milestone_gif, caption=milestone_text)

            bet = current_match.get("bet", 0)
            if bet > 0 and winner_id:
                USERS[winner_id]["coins"] += bet * 2
                USERS[loser_id]["coins"] = max(0, USERS[loser_id]["coins"] - bet)

            if winner_id:
                USERS[winner_id]["wins"] += 1
                USERS[loser_id]["losses"] += 1
            else:
                # Tie increment
                USERS[current_match["batting_user"]]["ties"] += 1
                USERS[current_match["bowling_user"]]["ties"] += 1

            # Save users
            if winner_id:
                await save_user(winner_id)
                await save_user(loser_id)
            else:
                await save_user(current_match["batting_user"])
                await save_user(current_match["bowling_user"])

            del PM_MATCHES[current_match["match_id"]]
            USER_PM_MATCHES[current_match["batting_user"]].discard(current_match["match_id"])
            USER_PM_MATCHES[current_match["bowling_user"]].discard(current_match["match_id"])
            GROUP_PM_MATCHES[chat_id].discard(current_match["match_id"])
            return

    current_match["batsman_choice"] = None
    current_match["bowler_choice"] = None

    await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
    if gif_url:
        await context.bot.send_animation(chat_id=chat_id, animation=gif_url)
    if milestone_gif:
        await context.bot.send_animation(chat_id=chat_id, animation=milestone_gif, caption=milestone_text)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{USERS[current_match['batting_user']]['name']}, choose your batting number:",
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

# /ccl Command Handler

async def ccl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    args = context.args

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ CCL matches can only be started in groups.")
        return

    ensure_user(user)

    # Check if group already has an active CCL match
    if GROUP_CCL_MATCH.get(chat.id):
        await update.message.reply_text("❌ There is already an ongoing CCL match in this group. Please wait for it to finish.")
        return

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

    match_id = str(uuid.uuid4())
    CCL_MATCHES[match_id] = {
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
        "milestone_50": False,
        "milestone_100": False,
    }
    USER_CCL_MATCH[user.id] = match_id
    GROUP_CCL_MATCH[chat.id] = match_id

    await update.message.reply_text(
        f"🏏 CCL Cricket game has been started by {USERS[user.id]['name']}! Bet: {bet}{COINS_EMOJI}\nPress Join below to play.",
        reply_markup=ccl_join_cancel_keyboard(match_id),
    )

# Join Callback

async def ccl_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    current_match = CCL_MATCHES.get(match_id)
    if not current_match or current_match["state"] != "waiting_join":
        await query.answer("Match not available to join.", show_alert=True)
        return

    if user.id == current_match["initiator"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return

    if current_match["opponent"]:
        await query.answer("Match already has an opponent.", show_alert=True)
        return

    ensure_user(user)

    bet = current_match.get("bet", 0)
    if bet > 0 and USERS[user.id]["coins"] < bet:
        await query.answer("You don't have enough coins to join this bet match.", show_alert=True)
        return

    current_match["opponent"] = user.id
    current_match["state"] = "toss"

    USER_CCL_MATCH[user.id] = match_id

    await query.message.edit_text(
        f"Match started between {USERS[current_match['initiator']]['name']} and {USERS[user.id]['name']}!\n"
        f"{USERS[current_match['initiator']]['name']}, choose Heads or Tails for the toss.",
        reply_markup=ccl_toss_keyboard(match_id),
    )
    await query.answer()

# Cancel Callback

async def ccl_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)

    current_match = CCL_MATCHES.get(match_id)
    if not current_match:
        await query.answer("Match not found or already ended.", show_alert=True)
        return

    if user.id != current_match["initiator"]:
        await query.answer("Only the initiator can cancel.", show_alert=True)
        return

    chat_id = current_match["group_chat_id"]

    del CCL_MATCHES[match_id]
    USER_CCL_MATCH[current_match["initiator"]] = None
    if current_match.get("opponent"):
        USER_CCL_MATCH[current_match["opponent"]] = None
    GROUP_CCL_MATCH.pop(chat_id, None)

    await query.message.edit_text("The CCL match has been cancelled by the initiator.")
    await query.answer()

# Toss Callback

async def ccl_toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, choice, match_id = query.data.split("_", 3)

    current_match = CCL_MATCHES.get(match_id)
    if not current_match or current_match["state"] != "toss":
        await query.answer("Invalid toss state.", show_alert=True)
        return

    if user.id != current_match["initiator"]:
        await query.answer("Only the initiator chooses toss.", show_alert=True)
        return

    coin_result = random.choice(["heads", "tails"])
    toss_winner = current_match["initiator"] if choice == coin_result else current_match["opponent"]
    toss_loser = current_match["opponent"] if toss_winner == current_match["initiator"] else current_match["initiator"]

    current_match["toss_winner"] = toss_winner
    current_match["toss_loser"] = toss_loser
    current_match["state"] = "bat_bowl_choice"

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

    current_match = CCL_MATCHES.get(match_id)
    if not current_match or current_match["state"] != "bat_bowl_choice":
        await query.answer("Invalid state for Bat/Bowl choice.", show_alert=True)
        return

    if user.id != current_match["toss_winner"]:
        await query.answer("Only toss winner can choose.", show_alert=True)
        return

    if choice == "bat":
        current_match["batting_user"] = current_match["toss_winner"]
        current_match["bowling_user"] = current_match["toss_loser"]
    else:
        current_match["batting_user"] = current_match["toss_loser"]
        current_match["bowling_user"] = current_match["toss_winner"]

    current_match.update({
        "state": "batting",
        "score": 0,
        "balls": 0,
        "wickets": 0,
        "innings": 1,
        "target": None,
        "batsman_choice": None,
        "bowler_choice": None,
        "milestone_50": False,
        "milestone_100": False,
    })

    batting_mention = f"[{USERS[current_match['batting_user']]['name']}](tg://user?id={current_match['batting_user']})"
    bowling_mention = f"[{USERS[current_match['bowling_user']]['name']}](tg://user?id={current_match['bowling_user']})"

    await query.message.edit_text(
        f"Match started!\n\n"
        f"🏏 Batter: {batting_mention}\n"
        f"⚾ Bowler: {bowling_mention}\n\n"
        f"{batting_mention} and {bowling_mention}, please send your choices in DM to me.",
        parse_mode="Markdown",
    )

    try:
        await context.bot.send_message(
            chat_id=current_match["batting_user"],
            text="Please send your batting number (0,1,2,3,4,6):"
        )
    except:
        await query.message.reply_text(f"Cannot send DM to {batting_mention}. Please start a chat with me first.", parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=current_match["bowling_user"],
            text="Please send your bowling type (rs, bouncer, yorker, short, slower, knuckle):"
        )
    except:
        await query.message.reply_text(f"Cannot send DM to {bowling_mention}. Please start a chat with me first.", parse_mode="Markdown")

    await query.answer()

# DM Handler for CCL mode

async def ccl_dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip().lower()

    match_id = USER_CCL_MATCH.get(user.id)
    if not match_id:
        await update.message.reply_text("You are not currently in a CCL match.")
        return

    current_match = CCL_MATCHES.get(match_id)
    if not current_match or current_match["state"] != "batting":
        await update.message.reply_text("Match is not in batting state.")
        return

    if user.id == current_match["batting_user"]:
        if text not in {"0", "1", "2", "3", "4", "6"}:
            await update.message.reply_text("Invalid batting number. Please send one of 0,1,2,3,4,6.")
            return
        if current_match["batsman_choice"] is not None:
            await update.message.reply_text("You have already sent your batting number for this ball.")
            return
        current_match["batsman_choice"] = int(text)
        await update.message.reply_text(f"Batting number {text} received.")
    elif user.id == current_match["bowling_user"]:
        if text not in BOWLING_TYPES:
            await update.message.reply_text(f"Invalid bowling type. Please send one of {', '.join(BOWLING_TYPES.keys())}.")
            return
        if current_match["bowler_choice"] is not None:
            await update.message.reply_text("You have already sent your bowling type for this ball.")
            return
        current_match["bowler_choice"] = text
        await update.message.reply_text(f"Bowling type '{text}' received.")
    else:
        await update.message.reply_text("You are not a player in this match.")
        return

    if current_match["batsman_choice"] is not None and current_match["bowler_choice"] is not None:
        await process_ccl_ball(context, current_match)
import asyncio

async def process_ccl_ball(context: ContextTypes.DEFAULT_TYPE, current_match):
    chat_id = current_match["group_chat_id"]
    batsman_choice = current_match["batsman_choice"]
    bowler_choice = current_match["bowler_choice"]

    current_match["balls"] += 1
    over_num = (current_match["balls"] - 1) // 6 + 1
    ball_num = (current_match["balls"] - 1) % 6 + 1

    bowler_number = BOWLING_TYPES.get(bowler_choice, -1)
    is_out = (batsman_choice == bowler_number)

    await context.bot.send_message(chat_id=chat_id, text=f"Over {over_num} Ball {ball_num}")

    bowling_comment = BOWLING_COMMENTARY.get(bowler_choice, "Bowled...")
    bowler_name = USERS[current_match["bowling_user"]]["name"]
    await context.bot.send_message(chat_id=chat_id, text=f"{bowler_name} Bowled A {bowling_comment}")

    await asyncio.sleep(5)

    text_lines = []
    milestone_gif = None
    milestone_text = None

    if is_out:
        current_match["wickets"] += 1
        text_lines.append(random.choice(RUN_COMMENTARY_CCL["out"]))
        gif_url = RUN_GIFS["out"]
    else:
        current_match["score"] += batsman_choice
        run_comment_list = RUN_COMMENTARY_CCL.get(batsman_choice, ["Runs scored!"])
        text_lines.append(random.choice(run_comment_list))
        gif_url = RUN_GIFS.get(str(batsman_choice), None)

        text_lines.append(f"Total Score: {current_match['score']} Runs")

        if not current_match.get("milestone_50") and current_match["score"] >= 50:
            milestone_gif = RUN_GIFS["halfcentury"]
            milestone_text = "🏏 Half-century! 50 runs!"
            current_match["milestone_50"] = True
        if not current_match.get("milestone_100") and current_match["score"] >= 100:
            milestone_gif = RUN_GIFS["century"]
            milestone_text = "💯 Century! 100 runs!"
            current_match["milestone_100"] = True

    await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
    if gif_url:
        await context.bot.send_animation(chat_id=chat_id, animation=gif_url)
    if milestone_gif:
        await context.bot.send_animation(chat_id=chat_id, animation=milestone_gif, caption=milestone_text)

    if current_match["innings"] == 1:
        if current_match["wickets"] >= 1:
            current_match["target"] = current_match["score"]
            current_match["batting_user"], current_match["bowling_user"] = current_match["bowling_user"], current_match["batting_user"]
            current_match["score"] = 0
            current_match["balls"] = 0
            current_match["wickets"] = 0
            current_match["innings"] = 2
            current_match["batsman_choice"] = None
            current_match["bowler_choice"] = None
            current_match["milestone_50"] = False
            current_match["milestone_100"] = False
            await context.bot.send_message(chat_id=chat_id,
                text=f"Innings over! Target for second innings: {current_match['target'] + 1}\n"
                     f"{USERS[current_match['batting_user']]['name']} will now Bat and {USERS[current_match['bowling_user']]['name']} will Bowl!")
            await context.bot.send_message(chat_id=current_match["batting_user"],
                text="Please send your batting number (0,1,2,3,4,6).")
            await context.bot.send_message(chat_id=current_match["bowling_user"],
                text="Please send your bowling type (rs, bouncer, yorker, short, slower, knuckle).")
            return
    else:
        target_plus_one = current_match["target"] + 1
        if current_match["score"] > current_match["target"]:
            winner_id = current_match["batting_user"]
            loser_id = current_match["bowling_user"]
            result_text = f"🏆 {USERS[winner_id]['name']} won the match!"
        elif current_match["score"] == current_match["target"]:
            winner_id = None
            loser_id = None
            result_text = "🤝 The match is a tie!"
        elif current_match["wickets"] >= 1:
            winner_id = current_match["bowling_user"]
            loser_id = current_match["batting_user"]
            result_text = f"🏆 {USERS[winner_id]['name']} won the match!"
        else:
            winner_id = None
            loser_id = None
            result_text = None

        if result_text:
            text_lines.append(f"\n{result_text}")
            await context.bot.send_message(chat_id=chat_id, text="\n".join(text_lines))
            if milestone_gif:
                await context.bot.send_animation(chat_id=chat_id, animation=milestone_gif, caption=milestone_text)

            bet = current_match.get("bet", 0)
            if bet > 0 and winner_id:
                USERS[winner_id]["coins"] += bet * 2
                USERS[loser_id]["coins"] = max(0, USERS[loser_id]["coins"] - bet)

            if winner_id:
                USERS[winner_id]["wins"] += 1
                USERS[loser_id]["losses"] += 1
            else:
                USERS[current_match["batting_user"]]["ties"] += 1
                USERS[current_match["bowling_user"]]["ties"] += 1

            if winner_id:
                await save_user(winner_id)
                await save_user(loser_id)
            else:
                await save_user(current_match["batting_user"])
                await save_user(current_match["bowling_user"])

            del CCL_MATCHES[current_match["match_id"]]
            USER_CCL_MATCH[current_match["initiator"]] = None
            USER_CCL_MATCH[current_match["opponent"]] = None
            GROUP_CCL_MATCH.pop(chat_id, None)
            return

    current_match["batsman_choice"] = None
    current_match["bowler_choice"] = None

    await context.bot.send_message(chat_id=current_match["batting_user"],
                                   text="Please send your batting number (0,1,2,3,4,6).")
    await context.bot.send_message(chat_id=current_match["bowling_user"],
                                   text="Please send your bowling type (rs, bouncer, yorker, short, slower, knuckle).")

# Admin command to end match

async def endmatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in groups.")
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("Only group admins can use this command.")
        return

    match_id = GROUP_CCL_MATCH.get(chat.id)
    if not match_id:
        await update.message.reply_text("No ongoing CCL match in this group.")
        return

    current_match = CCL_MATCHES.get(match_id)
    if current_match:
        del CCL_MATCHES[match_id]
        USER_CCL_MATCH[current_match["initiator"]] = None
        if current_match.get("opponent"):
            USER_CCL_MATCH[current_match["opponent"]] = None
        GROUP_CCL_MATCH.pop(chat.id, None)

    await update.message.reply_text("The ongoing CCL match in this group has been ended by admin.")

# Unknown command handler

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Use /help to see available commands.")

# Error handler

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# Main function and bot setup

async def main():
    await load_users()

    application = ApplicationBuilder().token(TOKEN).build()

    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("help", help_command))

    # PM mode handlers
    application.add_handler(CommandHandler("pm", pm_command))
    application.add_handler(CallbackQueryHandler(pm_join_callback, pattern=r"^pm_join_"))
    application.add_handler(CallbackQueryHandler(pm_cancel_callback, pattern=r"^pm_cancel_"))
    application.add_handler(CallbackQueryHandler(pm_toss_choice_callback, pattern=r"^pm_toss_(heads|tails)_"))
    application.add_handler(CallbackQueryHandler(pm_bat_bowl_choice_callback, pattern=r"^pm_(bat|bowl)_"))
    application.add_handler(CallbackQueryHandler(pm_batnum_choice_callback, pattern=r"^pm_batnum_"))
    application.add_handler(CallbackQueryHandler(pm_bowlnum_choice_callback, pattern=r"^pm_bowlnum_"))
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern=r"^leaderboard_"))

    # CCL mode handlers
    application.add_handler(CommandHandler("ccl", ccl_command))
    application.add_handler(CallbackQueryHandler(ccl_join_callback, pattern=r"^ccl_join_"))
    application.add_handler(CallbackQueryHandler(ccl_cancel_callback, pattern=r"^ccl_cancel_"))
    application.add_handler(CallbackQueryHandler(ccl_toss_choice_callback, pattern=r"^ccl_toss_(heads|tails)_"))
    application.add_handler(CallbackQueryHandler(ccl_bat_bowl_choice_callback, pattern=r"^ccl_(bat|bowl)_"))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT, ccl_dm_handler))

    # Admin command
    application.add_handler(CommandHandler("endmatch", endmatch))

    # Unknown commands handler
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Error handler
    application.add_error_handler(error_handler)

    logger.info("Bot started.")
    await application.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
    

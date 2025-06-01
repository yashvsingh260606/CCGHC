import logging
import random
import uuid
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
    ContextTypes,
)

from motor.motor_asyncio import AsyncIOMotorClient

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
BOT_NAME = "CCG HandCricket"
COINS_EMOJI = "🪙"
ADMIN_IDS = {7361215114}  # Replace with your Telegram admin IDs

# Bot token and MongoDB URL
TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
MONGO_URL = "YOUR_MONGODB_CONNECTION_STRING_HERE"

# MongoDB setup
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.handcricket
users_collection = db.users
matches_collection = db.matches

# In-memory caches
USERS = {}
MATCHES = {}
USER_MATCHES = {}
LEADERBOARD_PAGE = {}

# Helper functions
def get_username(user):
    return user.first_name or user.username or "Player"

async def load_users():
    cursor = users_collection.find({})
    async for user in cursor:
        if "user_id" not in user:
            logger.warning(f"Skipping user document without user_id: {user}")
            continue
        USERS[user["user_id"]] = user
        USER_MATCHES[user["user_id"]] = set(user.get("active_matches", []))
    logger.info("Users loaded")

async def save_user(user_id):
    user = USERS[user_id]
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {**user, "active_matches": list(USER_MATCHES.get(user_id, []))}},
        upsert=True,
    )

async def load_matches():
    cursor = matches_collection.find({})
    async for match in cursor:
        if "match_id" not in match:
            logger.warning(f"Skipping match document without match_id: {match}")
            continue
        MATCHES[match["match_id"]] = match
    logger.info("Matches loaded")

async def save_match(match_id):
    match = MATCHES[match_id]
    await matches_collection.update_one(
        {"match_id": match_id},
        {"$set": match},
        upsert=True,
    )

async def delete_match(match_id):
    await matches_collection.delete_one({"match_id": match_id})

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
        USER_MATCHES[user.id] = set()

def profile_text(user_id):
    u = USERS[user_id]
    return (
        f"**{u['name']}'s Profile**\n\n"
        f"💰 Coins: {u['coins']}{COINS_EMOJI}\n"
        f"🏆 Wins: {u['wins']}\n"
        f"❌ Losses: {u['losses']}\n"
    )

def leaderboard_text(page):
    top = 10
    if page == 0:
        sorted_users = sorted(USERS.values(), key=lambda u: u["wins"], reverse=True)
        text = "🏆 **Top 10 Players by Wins:**\n\n"
        for i, u in enumerate(sorted_users[:top], 1):
            text += f"{i}. {u['name']} - {u['wins']} Wins\n"
    else:
        sorted_users = sorted(USERS.values(), key=lambda u: u["coins"], reverse=True)
        text = "💰 **Top 10 Richest Players by Coins:**\n\n"
        for i, u in enumerate(sorted_users[:top], 1):
            text += f"{i}. {u['name']} - {u['coins']}{COINS_EMOJI}\n"
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

def number_buttons(match_id):
    buttons = [
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{match_id}") for i in range(4, 7)],
    ]
    return InlineKeyboardMarkup(buttons)

def join_button(match_id, bet):
    if bet > 0:
        text = f"Join (Bet: {bet}{COINS_EMOJI})"
    else:
        text = "Join"
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=f"join_match_{match_id}")]])

def bat_bowl_buttons(match_id):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Bat 🏏", callback_data=f"choose_bat_{match_id}"),
                InlineKeyboardButton("Bowl ⚾", callback_data=f"choose_bowl_{match_id}"),
            ]
        ]
            )
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    await save_user(user.id)
    await update.message.reply_text(
        f"Welcome to {BOT_NAME}, {USERS[user.id]['name']}! Use /register to get 4000 {COINS_EMOJI}.",
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
    last = USERS[user.id]["last_daily"]
    if last and (now - last) < timedelta(hours=24):
        rem = timedelta(hours=24) - (now - last)
        h, m = divmod(rem.seconds // 60, 60)
        await update.message.reply_text(f"Daily already claimed. Try again in {h}h {m}m.", parse_mode="Markdown")
        return
    USERS[user.id]["coins"] += 2000
    USERS[user.id]["last_daily"] = now
    await save_user(user.id)
    await update.message.reply_text(f"You received 2000 {COINS_EMOJI} as daily reward!", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - Welcome\n"
        "/register - Get 4000 coins\n"
        "/pm [bet] - Start a match\n"
        "/profile - Show profile\n"
        "/daily - Daily coins\n"
        "/leaderboard - Show leaderboard\n"
    )
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

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    LEADERBOARD_PAGE[user.id] = 0  # Default page: wins
    await update.message.reply_text(
        leaderboard_text(0),
        reply_markup=leaderboard_buttons(0),
        parse_mode="Markdown"
    )

async def leaderboard_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    chat_id = update.effective_chat.id

    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if bet < 0:
                await update.message.reply_text("❌ Bet must be a positive number.", parse_mode="Markdown")
                return
        except:
            await update.message.reply_text("❌ Invalid bet amount.", parse_mode="Markdown")
            return

    if bet > 0 and USERS[user.id]["coins"] < bet:
        await update.message.reply_text(f"❌ You don't have enough coins to bet {bet}{COINS_EMOJI}.", parse_mode="Markdown")
        return

    match_id = str(uuid.uuid4())
    MATCHES[match_id] = {
        "match_id": match_id,
        "chat_id": chat_id,
        "players": [user.id],
        "inviter": user.id,
        "state": "waiting_join",
        "bet": bet,
        "scores": {user.id: 0},
        "wickets": 0,
        "over": 0.0,
        "batsman_choice": None,
        "bowler_choice": None,
        "batting_first": None,
        "toss_winner": None,
        "toss_loser": None,
        "batting_player": None,
        "bowling_player": None,
        "turn": None,
        "innings": 0,
        "target": None,
        "superball": False,
    }
    USER_MATCHES.setdefault(user.id, set()).add(match_id)
    await save_match(match_id)

    if bet > 0:
        text = f"**{USERS[user.id]['name']}** started the match with a bet of **{bet}{COINS_EMOJI}**!\nClick below to join."
    else:
        text = f"**{USERS[user.id]['name']}** started the match!\nClick below to join."

    sent = await update.message.reply_text(text, reply_markup=join_button(match_id, bet), parse_mode="Markdown")
    MATCHES[match_id]["message_id"] = sent.message_id
    await save_match(match_id)

async def join_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    data = query.data
    _, _, match_id = data.split("_", 2)

    if match_id not in MATCHES:
        await query.answer("❌ Match not found.", show_alert=True)
        return

    match = MATCHES[match_id]
    if match["state"] != "waiting_join":
        await query.answer("❌ Match already started.", show_alert=True)
        return

    if user.id == match["inviter"]:
        await query.answer("❌ You cannot join your own match.", show_alert=True)
        return

    ensure_user(user)
    bet = match["bet"]
    if bet > 0 and USERS[user.id]["coins"] < bet:
        await query.answer(f"❌ Not enough coins to join bet {bet}{COINS_EMOJI}.", show_alert=True)
        return

    match["players"].append(user.id)
    match["scores"][user.id] = 0
    USER_MATCHES.setdefault(user.id, set()).add(match_id)

    if bet > 0:
        USERS[match["inviter"]]["coins"] -= bet
        USERS[user.id]["coins"] -= bet
        await save_user(match["inviter"])
        await save_user(user.id)

    match["state"] = "toss"
    await save_match(match_id)

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Heads", callback_data=f"toss_heads_{match_id}"),
            InlineKeyboardButton("Tails", callback_data=f"toss_tails_{match_id}")
        ]]
    )
    text = f"**Coin Toss!**\n{USERS[match['inviter']]['name']}, choose Heads or Tails."
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer()

async def toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, choice, match_id = query.data.split("_", 2)

    if match_id not in MATCHES:
        await query.answer("❌ Match not found.", show_alert=True)
        return

    match = MATCHES[match_id]
    if match["state"] != "toss":
        await query.answer("❌ Not in toss phase.", show_alert=True)
        return

    if user.id != match["inviter"]:
        await query.answer("❌ Only inviter can choose toss.", show_alert=True)
        return

    coin_result = random.choice(["heads", "tails"])
    toss_winner = match["inviter"] if choice == coin_result else [p for p in match["players"] if p != match["inviter"]][0]
    toss_loser = [p for p in match["players"] if p != toss_winner][0]

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "bat_bowl"
    await save_match(match_id)

    text = f"**{USERS[toss_winner]['name']}** won the toss! Choose to Bat or Bowl first."
    keyboard = bat_bowl_buttons(match_id)
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer()

async def bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, choice, match_id = query.data.split("_", 2)

    if match_id not in MATCHES:
        await query.answer("❌ Match not found.", show_alert=True)
        return
    match = MATCHES[match_id]
    if match["state"] != "bat_bowl":
        await query.answer("❌ Not in Bat/Bowl phase.", show_alert=True)
        return
    if user.id != match["toss_winner"]:
        await query.answer("❌ Only toss winner can choose.", show_alert=True)
        return

    batting_first = choice == "bat"
    match["batting_first"] = batting_first
    if batting_first:
        match["batting_player"] = match["toss_winner"]
        match["bowling_player"] = match["toss_loser"]
    else:
        match["batting_player"] = match["toss_loser"]
        match["bowling_player"] = match["toss_winner"]

    match.update({
        "state": "batting",
        "over": 0.0,
        "wickets": 0,
        "batsman_choice": None,
        "bowler_choice": None,
        "turn": "batsman",
        "innings": 1,
        "target": None,
        "superball": False,
    })
    await save_match(match_id)

    text = (
        f"**Over : {match['over']:.1f}**\n\n"
        f"🏏 **Batter** : {USERS[match['batting_player']]['name']}\n"
        f"⚾ **Bowler** : {USERS[match['bowling_player']]['name']}\n\n"
        f"{USERS[match['batting_player']]['name']}, choose your number to bat."
    )
    await query.message.edit_text(text, reply_markup=number_buttons(match_id), parse_mode="Markdown")
    await query.answer()

async def number_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, num_str, match_id = query.data.split("_", 2)

    if match_id not in MATCHES:
        await query.answer("❌ Match not found.", show_alert=True)
        return
    match = MATCHES[match_id]
    if match["state"] != "batting":
        await query.answer("❌ Not in batting phase.", show_alert=True)
        return
    if user.id not in match["players"]:
        await query.answer("❌ You are not part of this match.", show_alert=True)
        return

    try:
        number = int(num_str)
    except:
        await query.answer("❌ Invalid number.", show_alert=True)
        return
    if not 1 <= number <= 6:
        await query.answer("❌ Choose a number between 1 and 6.", show_alert=True)
        return

    # Batsman turn
    if match["turn"] == "batsman":
        if user.id != match["batting_player"]:
            await query.answer("❌ It's batsman's turn.", show_alert=True)
            return
        if match["batsman_choice"] is not None:
            await query.answer("❌ You already chose.", show_alert=True)
            return
        match["batsman_choice"] = number
        match["turn"] = "bowler"
        await save_match(match_id)

        text = (
            f"**Over : {match['over']:.1f}**\n\n"
            f"🏏 **Batter** : {USERS[match['batting_player']]['name']} has selected a number.\n"
            f"⚾ **Bowler** : {USERS[match['bowling_player']]['name']}, it's your turn to bowl."
        )
        await query.message.edit_text(text, reply_markup=number_buttons(match_id), parse_mode="Markdown")
        await query.answer()
        return

    # Bowler turn
    if match["turn"] == "bowler":
        if user.id != match["bowling_player"]:
            await query.answer("❌ It's bowler's turn.", show_alert=True)
            return
        if match["bowler_choice"] is not None:
            await query.answer("❌ You already chose.", show_alert=True)
            return
        match["bowler_choice"] = number

        batsman = match["batting_player"]
        bowler = match["bowling_player"]
        b_choice = match["batsman_choice"]
        bw_choice = match["bowler_choice"]

        # Update over count (simple logic)
        decimal = round((match["over"] * 10) % 10)
        if decimal < 5:
            match["over"] += 0.1
        else:
            match["over"] = round(match["over"]) + 1.0

        text = (
            f"**Over : {match['over']:.1f}**\n\n"
            f"🏏 **Batter** : {USERS[batsman]['name']}\n"
            f"⚾ **Bowler** : {USERS[bowler]['name']}\n\n"
            f"{USERS[batsman]['name']} Bat {b_choice}\n"
            f"{USERS[bowler]['name']} Bowl {bw_choice}\n\n"
        )

        if b_choice == bw_choice:
            # Wicket
            match["wickets"] += 1
            text += f"💥 {USERS[batsman]['name']} is OUT!\n"
            if match["wickets"] >= 1:
                if match["innings"] == 1:
                    match["target"] = match["scores"][batsman] + 1
                    match["innings"] = 2
                    match["wickets"] = 0
                    match["over"] = 0.0
                    match["batting_player"], match["bowling_player"] = match["bowling_player"], match["batting_player"]
                    match["batsman_choice"] = None
                    match["bowler_choice"] = None
                    match["turn"] = "batsman"
                    match["state"] = "batting"
                    await save_match(match_id)

                    text += (
                        f"🎯 {USERS[batsman]['name']} sets a target of {match['target']}\n\n"
                        f"🏏 {USERS[match['batting_player']]['name']} will now Bat and "
                        f"⚾ {USERS[match['bowling_player']]['name']} will now Bowl!\n\n"
                        f"{USERS[match['batting_player']]['name']}, choose your number to bat."
                    )
                    await query.message.edit_text(text, reply_markup=number_buttons(match_id), parse_mode="Markdown")
                    await query.answer()
                    return
                else:
                    await finish_match(update, context, match, text)
                    return
            else:
                match["batsman_choice"] = None
                match["bowler_choice"] = None
                match["turn"] = "batsman"
                await save_match(match_id)
                text += f"\n{USERS[batsman]['name']}, choose your number to bat."
                await query.message.edit_text(text, reply_markup=number_buttons(match_id), parse_mode="Markdown")
                await query.answer()
                return
        else:
            # Runs scored
            match["scores"][batsman] += b_choice
            text += f"Total Score:\n{USERS[batsman]['name']} scored total of {match['scores'][batsman]} Runs\n\n"
            if match["innings"] == 2 and match["scores"][batsman] >= match["target"]:
                text += f"🏆 Target achieved! {USERS[batsman]['name']} wins!\n"
                await finish_match(update, context, match, text)
                return
            match["batsman_choice"] = None
            match["bowler_choice"] = None
            match["turn"] = "batsman"
            await save_match(match_id)
            text += f"Next Move:\n{USERS[batsman]['name']} continue your Bat!"
            await query.message.edit_text(text, reply_markup=number_buttons(match_id), parse_mode="Markdown")
            await query.answer()
            return

async def finish_match(update, context, match, text):
    scores = match["scores"]
    players = match["players"]
    bet = match["bet"]

    p1_score = scores[players[0]]
    p2_score = scores[players[1]]

    if p1_score > p2_score:
        winner = players[0]
        loser = players[1]
    elif p2_score > p1_score:
        winner = players[1]
        loser = players[0]
    else:
        await update.callback_query.message.reply_text("🤝 Match tied! Superball not implemented.", parse_mode="Markdown")
        return

    USERS[winner]["wins"] += 1
    USERS[loser]["losses"] += 1

    if bet > 0:
        USERS[winner]["coins"] += bet * 2

    await save_user(winner)
    await save_user(loser)

    text += f"\n\n🏆 Match Over!\nWinner: {USERS[winner]['name']} 🏆"
    await update.callback_query.message.edit_text(text, parse_mode="Markdown")

    match_id = match["match_id"]
    del MATCHES[match_id]
    for pid in players:
        USER_MATCHES[pid].discard(match_id)
        await save_user(pid)
    await delete_match(match_id)

if __name__ == "__main__":
    main()

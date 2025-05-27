# === PART 1: IMPORTS, SETUP, AND BASIC COMMANDS ===

import json
import os
import random
import time
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# === CONFIG ===
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace with your bot token
DATA_FILE = "users.json"

# Admin Telegram user IDs (replace with real ones)
ADMINS = [123456789]

# Matches storage (in-memory)
matches = {}

# === USER DATA HELPERS ===

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user(user_id):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"coins": 0, "wins": 0, "losses": 0, "last_daily": 0}
        save_data(data)
    return data[uid]

def update_user(user_id, key, value):
    data = load_data()
    uid = str(user_id)
    if uid in data:
        data[uid][key] = value
        save_data(data)

def add_user_coins(user_id, amount):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"coins": 0, "wins": 0, "losses": 0, "last_daily": 0}
    data[uid]["coins"] += amount
    save_data(data)

# === UI BUTTON HELPERS ===

def get_number_buttons():
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_join_button(match_id):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]]
    )

# === COMMAND HANDLERS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 Welcome to Hand Cricket Bot!\n\n"
        "Use /register to get started and receive free coins.\n"
        "Use /help to see all available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Commands Guide:*\n"
        "/register - Claim free starting coins\n"
        "/profile - View your stats\n"
        "/daily - Claim your daily bonus\n"
        "/pm <bet> - Start a PvP match with optional bet\n"
        "/leaderboard - See top players\n"
        "/add <user_id> <coins> - (Admin) Add coins to a user",
        parse_mode="Markdown",
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if user["coins"] > 0:
        await update.message.reply_text("You are already registered!")
    else:
        add_user_coins(user_id, 100)
        await update.message.reply_text("🎉 Registration complete! You've received 100 coins.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id)
    await update.message.reply_text(
        f"🧾 *Profile of {user.first_name}*\n"
        f"🆔 ID: {user.id}\n"
        f"💰 Coins: {data['coins']}\n"
        f"✅ Wins: {data['wins']} | ❌ Losses: {data['losses']}",
        parse_mode="Markdown",
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    now = int(time.time())
    if now - user["last_daily"] >= 86400:
        add_user_coins(user_id, 50)
        update_user(user_id, "last_daily", now)
        await update.message.reply_text("🎁 You've received 50 daily coins!")
    else:
        wait = 86400 - (now - user["last_daily"])
        hours = wait // 3600
        mins = (wait % 3600) // 60
        await update.message.reply_text(
            f"⏳ Please wait {hours}h {mins}m to claim your next daily bonus."
        )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    sorted_users = sorted(data.items(), key=lambda x: x[1]["coins"], reverse=True)[:10]
    msg = "🏆 *Top 10 Players by Coins:*\n"
    for i, (uid, udata) in enumerate(sorted_users, 1):
        msg += f"{i}. ID {uid} - {udata['coins']} coins\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("❌ You're not authorized.")
        return
    try:
        uid = int(context.args[0])
        amount = int(context.args[1])
        add_user_coins(uid, amount)
        await update.message.reply_text(f"✅ Added {amount} coins to user {uid}.")
    except:
        await update.message.reply_text("⚠️ Usage: /add <user_id> <coins>")

# === END OF PART 1 ===
# === PART 2: MATCH CREATION AND JOINING ===

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    data = get_user(user_id)
    
    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if bet < 0:
                await update.message.reply_text("❌ Bet cannot be negative.")
                return
            if bet > data["coins"]:
                await update.message.reply_text("❌ You don't have enough coins to bet that amount.")
                return
        except ValueError:
            await update.message.reply_text("❌ Bet must be a valid number.")
            return
    
    # Create match ID
    match_id = str(uuid.uuid4())
    
    # Create match data
    matches[match_id] = {
        "players": {user_id: {"id": user_id, "name": user.first_name, "coins": data["coins"]}},
        "bet": bet,
        "status": "waiting",  # waiting for second player
        "turn": None,
        "innings": 1,
        "scores": {user_id: 0},
        "outs": {user_id: False},
        "batsman": None,
        "bowler": None,
        "choices": {},
        "message_id": None,
        "chat_id": update.effective_chat.id,
    }
    
    join_markup = get_join_button(match_id)
    
    await update.message.reply_text(
        f"🎮 Match created by {user.first_name} with bet: {bet} coins.\n"
        "Waiting for an opponent to join.",
        reply_markup=join_markup,
    )

async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    
    _, match_id = query.data.split("_")
    if match_id not in matches:
        await query.answer("❌ This match no longer exists.")
        return
    
    match = matches[match_id]
    
    if user_id in match["players"]:
        await query.answer("❌ You are already in this match.")
        return
    
    if len(match["players"]) >= 2:
        await query.answer("❌ This match already has 2 players.")
        return
    
    data = get_user(user_id)
    
    bet = match["bet"]
    if bet > data["coins"]:
        await query.answer("❌ You don't have enough coins to join this match.")
        return
    
    # Add player to match
    match["players"][user_id] = {"id": user_id, "name": user.first_name, "coins": data["coins"]}
    match["scores"][user_id] = 0
    match["outs"][user_id] = False
    
    # Deduct bet coins from both players if bet > 0
    if bet > 0:
        for pid in match["players"]:
            update_user(pid, "coins", get_user(pid)["coins"] - bet)
    
    match["status"] = "started"
    
    # Choose who bats and bowls first randomly
    pids = list(match["players"].keys())
    batsman = random.choice(pids)
    bowler = pids[1] if batsman == pids[0] else pids[0]
    match["batsman"] = batsman
    match["bowler"] = bowler
    match["turn"] = batsman
    
    # Send starting message with buttons
    start_text = (
        f"🏏 Match Started!\n"
        f"Batsman: {match['players'][batsman]['name']}\n"
        f"Bowler: {match['players'][bowler]['name']}\n\n"
        f"{match['players'][batsman]['name']}, choose your number (1-6):"
    )
    
    sent_message = await query.message.reply_text(
        start_text,
        reply_markup=get_number_buttons(),
    )
    
    match["message_id"] = sent_message.message_id
    match["chat_id"] = sent_message.chat_id
    
    # Delete the join button message to keep chat clean
    await query.message.delete()

# === CALLBACK QUERY HANDLER FOR JOIN AND NUMBERS WILL BE IN PART 3 ===
# === PART 3: GAMEPLAY CALLBACKS AND MATCH LOGIC ===

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    data = query.data
    
    if data.startswith("join_"):
        # Join button handled in Part 2 (to avoid double code, you can link here)
        await join_match(update, context)
        return
    
    if data.startswith("num_"):
        number = int(data.split("_")[1])
        # Find match where this user is playing and is in turn or bowling
        match = find_user_active_match(user_id)
        if not match:
            await query.answer("❌ You are not in any active match.")
            return
        
        if match["status"] != "started":
            await query.answer("❌ Match is not active.")
            return
        
        # Check if user is batsman or bowler currently expected to input
        current_turn = match["turn"]
        
        # We need to store choices: batsman chooses first, then bowler
        # After both choose, reveal numbers and update score or wicket
        
        if user_id not in [match["batsman"], match["bowler"]]:
            await query.answer("❌ You are not currently playing as batsman or bowler.")
            return
        
        # Only allow input when it's user's turn
        if user_id != current_turn:
            await query.answer("⏳ Wait for your turn.")
            return
        
        # Store the choice
        match["choices"][user_id] = number
        
        if user_id == match["batsman"]:
            # After batsman chooses, prompt bowler
            match["turn"] = match["bowler"]
            await query.answer(f"You chose {number}. Now waiting for bowler.")
            text = (
                f"{match['players'][match['batsman']]['name']} chose the number.\n"
                f"Now it's {match['players'][match['bowler']]['name']}'s turn to bowl."
            )
            await edit_match_message(match, text, hide_choice=True)
        else:
            # Bowler has chosen, reveal both numbers
            batsman_num = match["choices"][match["batsman"]]
            bowler_num = match["choices"][match["bowler"]]
            
            # Calculate result
            if batsman_num == bowler_num:
                # Wicket falls
                match["outs"][match["batsman"]] = True
                out_text = f"Wicket! {match['players'][match['batsman']]['name']} is out."
            else:
                # Runs scored
                match["scores"][match["batsman"]] += batsman_num
                out_text = f"{batsman_num} runs scored."
            
            # Prepare next state: switch roles or innings if needed
            # For simplicity, each player bats once, then match ends
            
            # Compose score text
            score_text = (
                f"Over: {match.get('over', 1)}\n"
                f"{match['players'][match['batsman']]['name']} chose: {batsman_num}\n"
                f"{match['players'][match['bowler']]['name']} chose: {bowler_num}\n"
                f"{out_text}\n\n"
                f"Score: {match['scores'][match['batsman']]}"
            )
            
            await edit_match_message(match, score_text, hide_choice=False)
            
            # Clear choices
            match["choices"] = {}
            
            if match["outs"][match["batsman"]]:
                # End innings or match
                if match["innings"] == 1:
                    # Switch innings: swap batsman and bowler
                    match["innings"] = 2
                    match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                    match["outs"][match["batsman"]] = False
                    match["scores"][match["batsman"]] = 0
                    match["turn"] = match["batsman"]
                    match["over"] = 1
                    next_text = (
                        f"Innings 2 started!\n"
                        f"Batsman: {match['players'][match['batsman']]['name']}\n"
                        f"Bowler: {match['players'][match['bowler']]['name']}\n\n"
                        f"{match['players'][match['batsman']]['name']}, choose your number:"
                    )
                    await edit_match_message(match, next_text, hide_choice=True)
                else:
                    # Match ends
                    winner_id = determine_winner(match)
                    winner_name = match["players"][winner_id]["name"]
                    final_score1 = match["scores"][list(match["scores"].keys())[0]]
                    final_score2 = match["scores"][list(match["scores"].keys())[1]]
                    end_text = (
                        f"Match ended!\n"
                        f"{match['players'][list(match['scores'].keys())[0]]['name']} scored {final_score1}\n"
                        f"{match['players'][list(match['scores'].keys())[1]]['name']} scored {final_score2}\n\n"
                        f"🏆 Winner: {winner_name}"
                    )
                    await edit_match_message(match, end_text, hide_choice=False)
                    match["status"] = "finished"
                    # Reward coins if bet > 0
                    reward_winner_coins(winner_id, match["bet"])
                    # Remove match from memory or keep for history
                    del matches[match["chat_id"]]
                    return
            else:
                # Continue current innings, batsman chooses again
                match["turn"] = match["batsman"]
                continue_text = (
                    f"Score: {match['scores'][match['batsman']]}\n"
                    f"{match['players'][match['batsman']]['name']}, choose your number:"
                )
                await edit_match_message(match, continue_text, hide_choice=True)
            
            await query.answer()

async def edit_match_message(match, text, hide_choice=False):
    chat_id = match["chat_id"]
    message_id = match["message_id"]
    
    # Buttons always same layout for number selection
    keyboard = get_number_buttons() if not hide_choice else None
    
    bot = Bot(token=BOT_TOKEN)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Failed to edit match message: {e}")

def determine_winner(match):
    scores = match["scores"]
    p1, p2 = list(scores.keys())
    if scores[p1] > scores[p2]:
        return p1
    elif scores[p2] > scores[p1]:
        return p2
    else:
        # Tie breaker logic (can be expanded)
        return p1  # for now, player 1 wins tie

def reward_winner_coins(winner_id, bet):
    if bet <= 0:
        return
    user_data = get_user(winner_id)
    user_data["coins"] += bet * 2  # winner gets double the bet (from both players)
    save_user_data(winner_id, user_data)

def find_user_active_match(user_id):
    for m in matches.values():
        if m["status"] == "started" and user_id in m["players"]:
            return m
    return None
# === BUTTON HANDLER ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Find match where user is playing
    user_match = None
    for mid, m in matches.items():
        if user_id in m["players"]:
            user_match = (mid, m)
            break
    if not user_match:
        await query.edit_message_text("⚠️ Match not found or already ended.")
        return

    match_id, match = user_match

    # Joining a waiting match
    if data.startswith("join_"):
        if match["stage"] != "waiting":
            await query.edit_message_text("⚠️ Match unavailable or already started.")
            return
        if len(match["players"]) > 1:
            await query.edit_message_text("⚠️ Match already has two players.")
            return
        if user_id == match["players"][0]:
            await query.answer("You cannot join your own match.", show_alert=True)
            return

        # Check coins
        for pid in match["players"] + [user_id]:
            u = get_user(pid)
            if u["coins"] < match["bet"]:
                await query.edit_message_text("❌ One or both players don't have enough coins.")
                del matches[match_id]
                return

        match["players"].append(user_id)
        for pid in match["players"]:
            add_user_coins(pid, -match["bet"])  # Deduct bet coins

        # Initialize match state
        p1, p2 = match["players"]
        match.update({
            "scores": {p1: 0, p2: 0},
            "innings": [p1, p2],
            "turn": p1,
            "waiting_for": "batsman",
            "choices": {},
            "stage": "playing",
            "overs": 0,
            "max_overs": 10,
            "balls_in_over": 0,
        })

        text = (f"🏏 Match Started!\n"
                f"{context.bot.get_chat(p1).first_name} vs {context.bot.get_chat(p2).first_name}\n\n"
                f"{context.bot.get_chat(p1).first_name} is batting first.\n"
                "Choose your number:")

        await query.edit_message_text(
            text=text,
            reply_markup=get_number_buttons()
        )
        return

    # Handling number selection for bat/bowl
    if data.startswith("num_"):
        number = int(data.split("_")[1])
        if match["stage"] != "playing":
            await query.answer("Match not in playing stage.", show_alert=True)
            return

        player_turn = match["turn"]
        other_player = [pid for pid in match["players"] if pid != player_turn][0]

        # Role assignment
        role = None
        # If waiting for batsman, only batsman can choose
        if match["waiting_for"] == "batsman" and user_id == player_turn:
            role = "bat"
        # If waiting for bowler, only bowler can choose
        elif match["waiting_for"] == "bowler" and user_id == other_player:
            role = "bowl"
        else:
            await query.answer("Not your turn or wrong role.", show_alert=True)
            return

        if role in match["choices"]:
            await query.answer("You already chose a number.", show_alert=True)
            return

        match["choices"][role] = number

        # Reveal messages logic
        if len(match["choices"]) == 1:
            # After batsman chooses
            if role == "bat":
                await query.edit_message_text(
                    f"{context.bot.get_chat(player_turn).first_name} chose a number.\nNow it's "
                    f"{context.bot.get_chat(other_player).first_name}'s turn to bowl.",
                    reply_markup=get_number_buttons()
                )
                match["waiting_for"] = "bowler"
            else:
                # Bowler chose first? unlikely, but just reset
                match["waiting_for"] = "batsman"
            return

        # Both chose numbers
        bat = match["choices"]["bat"]
        bowl = match["choices"]["bowl"]
        batter = player_turn
        bowler = other_player

        text = (f"🏏 Over: {match['overs']}.{match['balls_in_over']+1}\n"
                f"{context.bot.get_chat(batter).first_name} chose {bat}\n"
                f"{context.bot.get_chat(bowler).first_name} chose {bowl}\n")

        if bat == bowl:
            # Wicket falls
            text += f"❌ OUT! {context.bot.get_chat(batter).first_name} is out with {match['scores'][batter]} runs.\n"

            # Innings change or end match
            if match["turn"] == match["innings"][0]:
                # Switch innings
                match["turn"] = match["innings"][1]
                match["waiting_for"] = "batsman"
                match["choices"] = {}
                match["balls_in_over"] = 0
                match["overs"] = 0
                text += f"🔄 Now {context.bot.get_chat(match['turn']).first_name} will bat.\nChoose your number:"
                match["scores"][match["turn"]] = 0  # reset second innings score

                await context.bot.edit_message_text(
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                    text=text,
                    reply_markup=get_number_buttons()
                )
                return

            else:
                # Match over, determine winner
                p1, p2 = match["innings"]
                s1, s2 = match["scores"][p1], match["scores"][p2]
                winner = None
                if s1 > s2:
                    winner = p1
                elif s2 > s1:
                    winner = p2

                if winner:
                    loser = p1 if winner == p2 else p2
                    add_user_coins(winner, match["bet"] * 2)
                    uw = get_user(winner)
                    ul = get_user(loser)
                    update_user(winner, "wins", uw["wins"] + 1)
                    update_user(loser, "losses", ul["losses"] + 1)
                    text += f"🏆 Winner: {context.bot.get_chat(winner).first_name}!"
                else:
                    # Draw: refund bets
                    for pid in match["players"]:
                        add_user_coins(pid, match["bet"])
                    text += "🤝 Match Drawn!"

                await context.bot.edit_message_text(
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                    text=text
                )
                del matches[match_id]
                return
        else:
            # Runs scored
            match["scores"][batter] += bat
            match["balls_in_over"] += 1

            # Over increment logic (max 6 balls per over)
            if match["balls_in_over"] >= 6:
                match["overs"] += 1
                match["balls_in_over"] = 0

            match["choices"] = {}
            match["waiting_for"] = "batsman"  # back to batsman to choose
            # No change in batting turn, batsman continues
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=text + f"✅ {context.bot.get_chat(batter).first_name} scored {bat} runs and continues. Choose your number:",
                reply_markup=get_number_buttons()
            )
            return
# === COMMANDS AND HELPERS ===

def get_number_buttons():
    """Return InlineKeyboardMarkup with numbers 1-6 in two rows."""
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in users:
        users[user.id] = {"coins": 1000, "wins": 0, "losses": 0, "daily": 0}
        save_data()
    text = (
        f"👋 Hello {user.first_name}!\n\n"
        "Welcome to Hand Cricket Bot!\n"
        "Commands:\n"
        "/pm <bet> - Start or join a PvP match with optional bet\n"
        "/profile - View your stats\n"
        "/daily - Claim daily bonus\n"
        "/leaderboard - Show top players\n"
        "/help - Show help\n"
        "/add <user_id> <coins> - Admin only: Add coins to user\n"
    )
    await update.message.reply_text(text)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    text = (
        f"👤 Profile of {user.first_name} (ID: {user.id})\n"
        f"💰 Coins: {u['coins']}\n"
        f"🏆 Wins: {u['wins']}\n"
        f"❌ Losses: {u['losses']}\n"
    )
    await update.message.reply_text(text)


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    now = time.time()
    if now - u.get("daily", 0) < 86400:
        await update.message.reply_text("⏳ You have already claimed your daily bonus. Try again later.")
        return
    u["coins"] += 500
    u["daily"] = now
    save_data()
    await update.message.reply_text("🎉 You claimed 500 coins as daily bonus!")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Top 5 users by coins
    sorted_users = sorted(users.items(), key=lambda x: x[1]["coins"], reverse=True)[:5]
    text = "🏅 Leaderboard - Top Coins\n"
    for i, (uid, data) in enumerate(sorted_users, start=1):
        text += f"{i}. {context.bot.get_chat(uid).first_name}: {data['coins']} coins\n"
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 Hand Cricket Bot Commands:\n"
        "/start - Start the bot\n"
        "/pm <bet> - Start or join a PvP match with optional bet\n"
        "/profile - Show your stats\n"
        "/daily - Claim daily coins\n"
        "/leaderboard - Show top players\n"
        "/help - Show this help\n"
        "/add <user_id> <coins> - Admin only: Add coins to user\n"
    )
    await update.message.reply_text(text)


async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid arguments. Use numeric user_id and coins.")
        return
    add_user_coins(target_id, amount)
    await update.message.reply_text(f"✅ Added {amount} coins to user {target_id}.")


async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if bet < 0:
                raise ValueError()
        except:
            await update.message.reply_text("❌ Invalid bet amount.")
            return
    if u["coins"] < bet:
        await update.message.reply_text("❌ You don't have enough coins to bet that amount.")
        return

    # Create new match waiting for opponent
    match_id = str(uuid.uuid4())
    matches[match_id] = {
        "players": [user.id],
        "bet": bet,
        "stage": "waiting"
    }

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]]
    )
    await update.message.reply_text(
        f"🔔 Match created with bet {bet} coins. Waiting for an opponent to join.",
        reply_markup=keyboard
    )


# === HANDLERS SETUP ===
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("daily", daily))
app.add_handler(CommandHandler("leaderboard", leaderboard))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("add", add_coins))
app.add_handler(CommandHandler("pm", pm_command))
app.add_handler(CallbackQueryHandler(button_handler))


if __name__ == "__main__":
    load_data()
    print("Bot is running...")
    app.run_polling()

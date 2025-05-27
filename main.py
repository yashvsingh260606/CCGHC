import json
import random
import os
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --- SET YOUR BOT TOKEN HERE ---
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# --- ADMIN USER IDS FOR /add COMMAND ---
ADMINS = [123456789]  # Replace with your Telegram user IDs

# --- FILE PATHS ---
USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

# --- LOAD / SAVE USER DATA ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

# --- LOAD / SAVE MATCH DATA ---
def load_matches():
    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_matches():
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f)

# --- GLOBAL DATA ---
users = load_users()     # user_id(str) -> user data dict
matches = load_matches() # match_id(str) -> match data dict

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        users[user_id] = {
            "name": update.effective_user.first_name,
            "coins": 4000,
            "wins": 0,
            "losses": 0,
            "last_daily": None,
            "in_match": None,
        }
        save_users()
    text = (
        f"Welcome {update.effective_user.first_name}!\n\n"
        "Use /help to see all commands.\n"
        "You start with 4000 coins."
    )
    await update.message.reply_text(text)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in users:
        await update.message.reply_text("You are already registered.")
        return
    users[user_id] = {
        "name": update.effective_user.first_name,
        "coins": 4000,
        "wins": 0,
        "losses": 0,
        "last_daily": None,
        "in_match": None,
    }
    save_users()
    await update.message.reply_text(
        f"Registered! You received 4000 coins, {update.effective_user.first_name}."
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        await update.message.reply_text("You are not registered. Use /register.")
        return
    last_daily = users[user_id].get("last_daily")
    now = datetime.utcnow()
    if last_daily:
        last = datetime.fromisoformat(last_daily)
        if now - last < timedelta(hours=24):
            await update.message.reply_text(
                "You have already claimed daily coins in the last 24 hours."
            )
            return
    users[user_id]["coins"] += 3000
    users[user_id]["last_daily"] = now.isoformat()
    save_users()
    await update.message.reply_text("You received 3000 daily coins!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = [
        "/start - Welcome message",
        "/register - Register and get 4000 coins",
        "/daily - Get 3000 coins once per 24h",
        "/pm - Play a match",
        "/leaderboard - Top players by wins",
        "/profile - Show your profile",
    ]
    help_text = "Available Commands:\n" + "\n".join(commands)
    await update.message.reply_text(help_text)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id not in users:
        await update.message.reply_text("You are not registered. Use /register.")
        return
    u = users[user_id]
    text = (
        f"{u['name']}'s Profile\n\n"
        f"Name: {u['name']}\n"
        f"ID: {user_id}\n"
        f"Purse: {u['coins']} coins\n"
        f"Wins: {u['wins']}\n"
        f"Losses: {u['losses']}"
    )
    await update.message.reply_text(text)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not users:
        await update.message.reply_text("No players registered yet.")
        return
    sorted_users = sorted(users.values(), key=lambda x: x.get("wins", 0), reverse=True)
    text = "🏆 Leaderboard (Top 10 by Wins) 🏆\n\n"
    for i, u in enumerate(sorted_users[:10], start=1):
        text += f"{i}. {u['name']} - Wins: {u.get('wins',0)}\n"
    await update.message.reply_text(text)

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    target_id, coins = args[0], args[1]
    if target_id not in users:
        await update.message.reply_text("User not found.")
        return
    try:
        coins = int(coins)
        if coins <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Coins must be a positive integer.")
        return
    users[target_id]["coins"] += coins
    save_users()
    await update.message.reply_text(
        f"Added {coins} coins to {users[target_id]['name']} (ID: {target_id})."
    )
# --- UTILITY FUNCTIONS ---

def create_choice_keyboard():
    keyboard = [
        [InlineKeyboardButton("1", callback_data="num_1"),
         InlineKeyboardButton("2", callback_data="num_2"),
         InlineKeyboardButton("3", callback_data="num_3")],
        [InlineKeyboardButton("4", callback_data="num_4"),
         InlineKeyboardButton("5", callback_data="num_5"),
         InlineKeyboardButton("6", callback_data="num_6")],
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_match_id():
    return str(random.randint(100000, 999999))

def opponent_waiting_text(user_name):
    return f"Waiting for an opponent...\nShare your Match ID to invite a friend."

# --- MATCH COMMANDS ---

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start or join a Player vs Player match."""
    user_id = str(update.effective_user.id)
    if user_id not in users:
        await update.message.reply_text("You are not registered. Use /register.")
        return
    if users[user_id]["in_match"]:
        await update.message.reply_text("You are already in a match.")
        return

    # If user supplied a match ID, try to join that match
    if context.args:
        join_id = context.args[0]
        if join_id not in matches:
            await update.message.reply_text("Match ID not found.")
            return
        match = matches[join_id]
        if len(match["players"]) >= 2:
            await update.message.reply_text("This match is full.")
            return
        if user_id in match["players"]:
            await update.message.reply_text("You are already in this match.")
            return
        # Add player 2
        match["players"].append(user_id)
        match["state"] = "toss"
        match["toss_winner"] = None
        match["batting"] = None
        match["innings"] = 1
        match["scores"] = {match["players"][0]: 0, match["players"][1]: 0}
        match["wickets"] = {match["players"][0]: 0, match["players"][1]: 0}
        match["balls"] = 0
        match["choices"] = {}
        match["turn"] = None  # "batsman" or "bowler"
        match["message_id"] = None
        match["chat_id"] = update.effective_chat.id
        matches[join_id] = match
        users[user_id]["in_match"] = join_id
        users[match["players"][0]]["in_match"] = join_id
        save_matches()
        save_users()

        # Send starting message and prompt toss
        p1_name = users[match["players"][0]]["name"]
        p2_name = users[match["players"][1]]["name"]
        text = (
            f"Match {join_id} started between {p1_name} and {p2_name}!\n\n"
            "Deciding toss... Each player, choose Heads or Tails.\n"
            "Use /toss to make your choice."
        )
        await update.message.reply_text(text)
        return

    # Otherwise, create a new match ID and wait for opponent
    match_id = generate_match_id()
    matches[match_id] = {
        "players": [user_id],
        "state": "waiting",
        "chat_id": update.effective_chat.id,
        "message_id": None,
    }
    users[user_id]["in_match"] = match_id
    save_matches()
    save_users()

    await update.message.reply_text(
        f"Match created! Your Match ID is: {match_id}\n"
        "Share this ID with a friend to let them join using:\n"
        f"/pm {match_id}\n\nWaiting for an opponent..."
    )

# --- TOSS LOGIC ---

async def toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Players call toss: /toss heads or /toss tails"""
    user_id = str(update.effective_user.id)
    if user_id not in users or not users[user_id]["in_match"]:
        await update.message.reply_text("You are not in any match.")
        return
    match_id = users[user_id]["in_match"]
    match = matches.get(match_id)
    if not match:
        await update.message.reply_text("Match data not found.")
        return
    if match["state"] != "toss":
        await update.message.reply_text("Toss is not active right now.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /toss heads OR /toss tails")
        return
    choice = context.args[0].lower()
    if choice not in ("heads", "tails"):
        await update.message.reply_text("Choose 'heads' or 'tails'.")
        return

    if "toss_calls" not in match:
        match["toss_calls"] = {}

    if user_id in match["toss_calls"]:
        await update.message.reply_text("You have already called the toss.")
        return

    match["toss_calls"][user_id] = choice
    save_matches()

    if len(match["toss_calls"]) < 2:
        await update.message.reply_text("Waiting for opponent to call toss...")
        return

    # Both players have called toss - determine winner
    toss_result = random.choice(["heads", "tails"])
    p1 = match["players"][0]
    p2 = match["players"][1]
    p1_call = match["toss_calls"][p1]
    p2_call = match["toss_calls"][p2]

    winner = None
    if p1_call == toss_result:
        winner = p1
    elif p2_call == toss_result:
        winner = p2

    if not winner:
        # Rare case both called wrong? Pick randomly
        winner = random.choice(match["players"])

    match["toss_winner"] = winner
    match["state"] = "choose_bat_bowl"
    save_matches()

    winner_name = users[winner]["name"]
    text = (
        f"Toss result: {toss_result.upper()}!\n"
        f"{users[p1]['name']} called {p1_call}, {users[p2]['name']} called {p2_call}\n\n"
        f"{winner_name} won the toss!\n"
        "Use /bat or /bowl to choose your role first innings."
    )
    await update.message.reply_text(text)

# --- CHOOSE BAT OR BOWL ---

async def choose_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Choose batting or bowling after toss"""
    user_id = str(update.effective_user.id)
    if user_id not in users or not users[user_id]["in_match"]:
        await update.message.reply_text("You are not in a match.")
        return
    match_id = users[user_id]["in_match"]
    match = matches.get(match_id)
    if not match or match["state"] != "choose_bat_bowl":
        await update.message.reply_text("Not time to choose role now.")
        return
    if user_id != match["toss_winner"]:
        await update.message.reply_text("Only toss winner can choose role.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /bat or /bowl")
        return
    choice = context.args[0].lower()
    if choice not in ("bat", "bowl"):
        await update.message.reply_text("Choose /bat or /bowl")
        return

    match["batting"] = user_id if choice == "bat" else [p for p in match["players"] if p != user_id][0]
    match["bowling"] = [p for p in match["players"] if p != match["batting"]][0]
    match["state"] = "in_progress"
    match["innings"] = 1
    match["scores"] = {p: 0 for p in match["players"]}
    match["wickets"] = {p: 0 for p in match["players"]}
    match["balls"] = 0
    match["choices"] = {}
    match["turn"] = "batsman"
    save_matches()

    bat_name = users[match["batting"]]["name"]
    bowl_name = users[match["bowling"]]["name"]

    text = (
        f"{bat_name} will bat first.\n"
        f"{bowl_name} will bowl first.\n\n"
        f"Match started! {bat_name} to play first.\n"
        f"Choose a number between 1-6."
    )
    sent_msg = await update.message.reply_text(text, reply_markup=create_choice_keyboard())
    match["message_id"] = sent_msg.message_id
    save_matches()

# --- CALLBACK QUERY HANDLER FOR GAMEPLAY ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    if user_id not in users or not users[user_id]["in_match"]:
        await query.answer("You are not in a match.")
        return
    match_id = users[user_id]["in_match"]
    match = matches.get(match_id)
    if not match or match["state"] != "in_progress":
        await query.answer("Game not in progress.")
        return

    chosen_num = int(query.data.split("_")[1])
    p_bat = match["batting"]
    p_bowl = match["bowling"]
    turn = match["turn"]

    # Only allow batsman and bowler to press buttons
    if user_id != p_bat and user_id != p_bowl:
        await query.answer("You are not playing right now.")
        return

    if user_id in match["choices"]:
        await query.answer("You already chose your number this ball.")
        return

    match["choices"][user_id] = chosen_num
    save_matches()
    await query.answer(f"You chose {chosen_num}")

    # If only one has chosen, wait for other
    if len(match["choices"]) < 2:
        # Show text to other player without revealing chosen number
        if user_id == p_bat:
            waiting_text = f"{users[p_bat]['name']} chose their number. Now it's {users[p_bowl]['name']}'s turn."
        else:
            waiting_text = f"{users[p_bowl]['name']} chose their number. Now it's {users[p_bat]['name']}'s turn."

        # Edit the game message with waiting info
        try:
            await context.bot.edit_message_text(
                chat_id=match["chat_id"],
                message_id=match["message_id"],
                text=waiting_text,
                reply_markup=create_choice_keyboard(),
            )
        except:
            pass
        return

    # Both players chose, resolve the ball
    bat_num = match["choices"][p_bat]
    bowl_num = match["choices"][p_bowl]
    match["choices"] = {}
    match["balls"] += 1

    # If numbers equal -> wicket
    if bat_num == bowl_num:
        match["wickets"][p_bat] += 1
        wicket_fell = True
    else:
        match["scores"][p_bat] += bat_num
        wicket_fell = False

    # Format status text
    text = (
        f"Ball {match['balls']}:\n"
        f"{users[p_bat]['name']} played {bat_num}\n"
        f"{users[p_bowl]['name']} bowled {bowl_num}\n\n"
    )
    if wicket_fell:
        text += f"WICKET! {users[p_bat]['name']} is out.\n"
    else:
        text += f"{bat_num} runs scored.\n"

    text += (
        f"Score: {match['scores'][p_bat]} / {match['wickets'][p_bat]}\n"
        f"Overs: {match['balls'] // 6}.{match['balls'] % 6}\n\n"
    )

    # Check innings end conditions
    max_wickets = 1  # Only one wicket to keep game simple
    max_balls = 12   # 2 overs per innings for quick game

    if match["wickets"][p_bat] >= max_wickets or match["balls"] >= max_balls:
        # End innings or match
        if match["innings"] == 1:
            # Switch innings
            match["innings"] = 2
            match["balls"] = 0
            match["choices"] = {}
            # Swap batting and bowling
            match["batting"], match["bowling"] = match["bowling"], match["batting"]
            match["turn"] = "batsman"
            text += (
                f"End of 1st innings.\n"
                f"Target for {users[match['batting']]['name']}: {match['scores'][p_bat] + 1}\n\n"
                f"{users[match['batting']]['name']} to bat now. Choose a number."
            )
            try:
                await context.bot.edit_message_text(
                    chat_id=match["chat_id"],
                    message_id=match["message_id"],
                    text=text,
                    reply_markup=create_choice_keyboard(),
                )
            except:
                pass
            save_matches()
            return
        else:
            # Match over, decide winner
            p1_score = match["scores"][match["players"][0]]
            p2_score = match["scores"][match["players"][1]]
            if p1_score > p2_score:
                winner = match["players"][0]
            elif p2_score > p1_score:
                winner = match["players"][1]
            else:
                winner = None

            if winner:
                win_name = users[winner]["name"]
                text += f"Match Over!\nWinner: {win_name}\n"
                users[winner]["wins"] += 1
                loser = [p for p in match["players"] if p != winner][0]
                users[loser]["losses"] += 1
                # Winner coins reward
                users[winner]["coins"] += 5000
                save_users()
            else:
                text += "Match Over! It's a tie!\n"

            # Clear match data from users
            for p in match["players"]:
                users[p]["in_match"] = None
            save_users()

            # Remove match from matches
            if match_id in matches:
                del matches[match_id]
                save_matches()

            try:
                await context.bot.edit_message_text(
                    chat_id=match["chat_id"],
                    message_id=match["message_id"],
                    text=text,
                )
            except:
                pass
            return

    # Continue innings
    match["turn"] = "batsman"
    save_matches()

    try:
        await context.bot.edit_message_text(
            chat_id=match["chat_id"],
            message_id=match["message_id"],
            text=text,
            reply_markup=create_choice_keyboard(),
        )
    except:
        pass

# --- MAIN SETUP ---

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("add", add_coins))
    application.add_handler(CommandHandler("pm", pm))
    application.add_handler(CommandHandler("toss", toss))
    application.add_handler(CommandHandler("bat", choose_role))
    application.add_handler(CommandHandler("bowl", choose_role))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()

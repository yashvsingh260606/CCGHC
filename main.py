import json
import time
import random
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ====== Set your bot token here =======
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace this with your actual bot token

# ====== Global variables & data loading =======
USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"
ADMIN_IDS = [123456789]  # Replace with your Telegram user ID(s) who are admins

# Load or initialize user data
try:
    with open(USERS_FILE, "r") as f:
        users = json.load(f)
except FileNotFoundError:
    users = {}

# Load or initialize matches data
try:
    with open(MATCHES_FILE, "r") as f:
        matches = json.load(f)
except FileNotFoundError:
    matches = {}

# Helper functions to save data
def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def save_matches():
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f)

# Function to register user if not registered
def register_user(user_id, username):
    if str(user_id) not in users:
        users[str(user_id)] = {
            "name": username or "Player",
            "coins": 3000,
            "wins": 0,
            "losses": 0,
            "last_daily": 0,
        }
        save_users()

# /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name)
    welcome_text = (
        f"🏏 Welcome {user.first_name} to Hand Cricket Bot!\n\n"
        "Use /help to see available commands.\n"
        "Get coins with /daily and start a match with /pm or /pm <bet>."
    )
    await update.message.reply_text(welcome_text)

# /register command (if you want separate welcome coins)
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if str(user.id) in users:
        await update.message.reply_text("You are already registered.")
    else:
        register_user(user.id, user.first_name)
        await update.message.reply_text("You have been registered and credited 3000 🪙!")

# /profile command
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in users:
        await update.message.reply_text("You are not registered. Use /start to register.")
        return
    data = users[uid]
    text = (
        f"{data['name']}'s Profile\n\n"
        f"Name : {data['name']}\n"
        f"ID : {uid}\n"
        f"Purse: {data['coins']} 🪙\n\n"
        "Match Stats -\n"
        f"Wins : {data['wins']}\n"
        f"Losses : {data['losses']}"
    )
    await update.message.reply_text(text)

# /add command - admin only to add coins to user
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    target_id, coins = args
    if target_id not in users:
        await update.message.reply_text("User ID not found.")
        return
    try:
        coins = int(coins)
    except ValueError:
        await update.message.reply_text("Coins must be a number.")
        return
    users[target_id]["coins"] += coins
    save_users()
    await update.message.reply_text(f"Added {coins} 🪙 to user {users[target_id]['name']}.")

# The rest of the commands and match logic will be in Part 2
# Part 2 - Match system, commands, gameplay logic

# Helper: Get user display name safely
def get_name(user_id):
    return users.get(str(user_id), {}).get("name", "Player")

# /daily command - claim daily coins once every 24 hours
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in users:
        await update.message.reply_text("You are not registered. Use /start to register.")
        return
    now = time.time()
    last = users[uid].get("last_daily", 0)
    if now - last < 86400:
        remain = int((86400 - (now - last)) // 3600)
        await update.message.reply_text(f"Daily already claimed! Come back in {remain} hours.")
        return
    users[uid]["coins"] += 500
    users[uid]["last_daily"] = now
    save_users()
    await update.message.reply_text("You have claimed your daily 500 🪙! Use /profile to check your purse.")

# /leaderboard command - top 10 by coins
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(users.items(), key=lambda x: x[1]["coins"], reverse=True)
    text = "🏆 Leaderboard - Top 10 Players by Coins 🏆\n\n"
    for i, (uid, data) in enumerate(sorted_users[:10], 1):
        text += f"{i}. {data['name']} - {data['coins']} 🪙\n"
    await update.message.reply_text(text)

# /help command - list commands except add/help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Available Commands:\n\n"
        "/start - Welcome message and register\n"
        "/register - Register yourself and get coins\n"
        "/profile - Show your profile and stats\n"
        "/daily - Claim daily 500 🪙 bonus\n"
        "/pm [bet] - Start or join a PvP hand cricket match\n"
        "/leaderboard - Show top players by coins\n"
        # intentionally exclude /add and /help from user help
    )
    await update.message.reply_text(text)

# Create the buttons keyboard - two rows [1,2,3], [4,5,6]
def get_buttons():
    buttons = [
        [InlineKeyboardButton(str(n), callback_data=str(n)) for n in [1,2,3]],
        [InlineKeyboardButton(str(n), callback_data=str(n)) for n in [4,5,6]],
    ]
    return InlineKeyboardMarkup(buttons)

# Create the join match keyboard
def join_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]]
    )

# /pm command handler - start or join a match, optional bet
async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    register_user(user.id, user.first_name)
    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if bet < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Invalid bet amount. It must be a positive number or zero.")
            return
    if users[uid]["coins"] < bet:
        await update.message.reply_text("You do not have enough coins for this bet.")
        return
    # Check if user already in a match
    for mid, match in matches.items():
        if uid in match["players"]:
            await update.message.reply_text("You are already in a match.")
            return
    # Create new match waiting for opponent
    match_id = str(random.randint(100000,999999))
    matches[match_id] = {
        "players": [uid],
        "player_names": {uid: get_name(uid)},
        "bet": bet,
        "state": "waiting_for_opponent",
        "turn": None,
        "scores": {uid: 0},
        "innings": 1,
        "batsman": uid,
        "bowler": None,
        "chosen": {},
        "target": None,
        "message_id": None,
        "chat_id": update.effective_chat.id,
    }
    save_matches()
    text = (
        f"Match Created with bet {bet} 🪙.\n\n"
        "Waiting for an opponent to join.\n"
        "Press 'Join Match' to accept."
    )
    sent = await update.message.reply_text(text, reply_markup=join_keyboard(match_id))
    matches[match_id]["message_id"] = sent.message_id
    save_matches()

# Callback query handler for join and number selection
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = str(query.from_user.id)

    # Join match
    if data.startswith("join_"):
        match_id = data.split("_")[1]
        if match_id not in matches:
            await query.edit_message_text("Match no longer available.")
            return
        match = matches[match_id]
        if match["state"] != "waiting_for_opponent":
            await query.edit_message_text("Match already started or unavailable.")
            return
        if uid in match["players"]:
            await query.edit_message_text("You are already in this match.")
            return
        # Check if user has enough coins for bet
        bet = match["bet"]
        if users.get(uid, {}).get("coins", 0) < bet:
            await query.edit_message_text("You do not have enough coins to join this match.")
            return
        match["players"].append(uid)
        match["player_names"][uid] = get_name(uid)
        match["scores"][uid] = 0
        # Deduct bet coins from both players if bet > 0
        if bet > 0:
            users[match["players"][0]]["coins"] -= bet
            users[uid]["coins"] -= bet
        # Decide who bats first by toss (random)
        first_batsman = random.choice(match["players"])
        match["batsman"] = first_batsman
        match["bowler"] = match["players"][1] if match["players"][0] == first_batsman else match["players"][0]
        match["state"] = "playing"
        match["turn"] = "batsman"
        match["chosen"] = {}
        match["innings"] = 1
        match["target"] = None
        save_users()
        save_matches()
        # Send first message with batting prompt
        text = (
            f"Match started! Bet: {bet} 🪙\n\n"
            f"{get_name(match['batsman'])} is batting first.\n\n"
            f"{get_name(match['batsman'])}, choose your number."
        )
        await query.edit_message_text(text, reply_markup=get_buttons())
        return

    # Handle number selection in active match
    if data in ['1','2','3','4','5','6']:
        # Find match where this user is playing and it's their turn
        found_match = None
        for mid, match in matches.items():
            if uid in match["players"] and match["state"] == "playing":
                if match["turn"] == "batsman" and uid == match["batsman"]:
                    found_match = match
                    match_id = mid
                    break
                if match["turn"] == "bowler" and uid == match["bowler"]:
                    found_match = match
                    match_id = mid
                    break
        if not found_match:
            await query.answer("Not your turn or no active match found.", show_alert=True)
            return
        match = found_match
        chosen_num = int(data)

        # Save choice
        match["chosen"][uid] = chosen_num

        if match["turn"] == "batsman":
            # After batsman chooses, prompt bowler without revealing batsman number
            match["turn"] = "bowler"
            save_matches()
            text = (
                f"{get_name(match['batsman'])} chose a number.\n"
                f"Now it's {get_name(match['bowler'])}'s turn to bowl."
            )
            await query.edit_message_text(text)
        elif match["turn"] == "bowler":
            # After bowler chooses, reveal both numbers and update scores
            batsman_num = match["chosen"][match["batsman"]]
            bowler_num = match["chosen"][match["bowler"]]
            chat_id = match["chat_id"]
            message_id = match["message_id"]
            # Clear chosen for next ball
            match["chosen"] = {}
            match["turn"] = "batsman"

            if batsman_num == bowler_num:
                # Wicket falls - innings ends
                match["scores"][match["batsman"]] += 0
                # Update scores & declare inning end
                innings_score = match["scores"][match["batsman"]]
                # If first innings, set target and swap batsman/bowler
                if match["innings"] == 1:
                    match["target"] = innings_score + 1
                    match["innings"] = 2
                    # Swap roles
                    old_batsman = match["batsman"]
                    old_bowler = match["bowler"]
                    match["batsman"] = old_bowler
                    match["bowler"] = old_batsman
                    match["turn"] = "batsman"
                    save_matches()
                    # Message for wicket and innings break
                    text = (
                        f"🏏 Over {match['innings']-1}\n"
                        f"{get_name(old_batsman)} chose {batsman_num}, {get_name(old_bowler)} chose {bowler_num}\n\n"
                        f"Wicket! {get_name(old_batsman)} is out.\n\n"
                        f"Target for {get_name(match['batsman'])} is {match['target']} 🪙\n\n"
                        f"{get_name(match['batsman'])}, choose your number to start the chase."
                    )
                    await query.edit_message_text(text, reply_markup=get_buttons())
                    return
                else:
                    # Second innings wicket - match ends
                    first_player = match["players"][0]
                    second_player = match["players"][1]
                    first_score = match["scores"][first_player]
                    second_score = match["scores"][second_player]
                    winner = None
                    if first_score > second_score:
                        winner = first_player
                    elif second_score > first_score:
                        winner = second_player
                    # If draw, choose no winner (could be tie)
                    if winner:
                        users[winner]["wins"] += 1
                        loser = first_player if winner == second_player else second_player
                        users[loser]["losses"] += 1
                        # Pay out bet to winner
                        bet = match["bet"]
                        if bet > 0:
                            users[winner]["coins"] += bet * 2
                        save_users()
                        win_text = f"{get_name(winner)} wins the match and earns {bet*2} 🪙!"
                    else:
                        win_text = "Match tied! No winner."

                    text = (
                        f"🏏 Over {match['innings']}\n"
                        f"{get_name(match['batsman'])} chose {batsman_num}, {get_name(match['bowler'])} chose {bowler_num}\n\n"
                        f"Wicket! {get_name(match['batsman'])} is out.\n\n"
                        f"Final Scores:\n"
                        f"{get_name(first_player)}: {first_score}\n"
                        f"{get_name(second_player)}: {second_score}\n\n"
                        f"{win_text}"
                    )
                    # Remove match
                    del matches[match_id]
                    save_matches()
                    await query.edit_message_text(text)
                    return
            else:
                # Runs scored = batsman_num (add to score)
                match["scores"][match["batsman"]] += batsman_num
                total_score = match["scores"][match["batsman"]]
                text = (
                    f"🏏 Over {match['innings']}\n"
                    f"{get_name(match['batsman'])} chose {batsman_num}, {get_name(match['bowler'])} chose {bowler_num}\n\n"
                    f"Runs scored this ball: {batsman_num}\n"
                    f"Total Score: {total_score}\n\n"
                    f"{get_name(match['batsman'])} continues to bat."
                )
                save_matches()
                await query.edit_message_text(text, reply_markup=get_buttons())
        if __name__ == "__main__":
    application.run_polling()

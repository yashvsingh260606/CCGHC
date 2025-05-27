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

# Register user if not already
def register_user(user_id, username):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "name": username or "Player",
            "coins": 3000,
            "wins": 0,
            "losses": 0,
            "last_daily": 0,
        }
        save_users()

def get_name(user_id):
    return users.get(str(user_id), {}).get("name", "Player")

# ====== Commands ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.first_name)
    text = (
        f"🏏 Welcome {user.first_name} to Hand Cricket Bot!\n\n"
        "Use /help to see available commands.\n"
        "Get coins with /daily and start a match with /pm or /pm <bet>."
    )
    await update.message.reply_text(text)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in users:
        await update.message.reply_text("You are not registered. Use /start to register.")
        return
    d = users[uid]
    text = (
        f"{d['name']}'s Profile\n\n"
        f"Name: {d['name']}\n"
        f"ID: {uid}\n"
        f"Purse: {d['coins']} 🪙\n\n"
        f"Wins: {d['wins']}\n"
        f"Losses: {d['losses']}"
    )
    await update.message.reply_text(text)

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

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(users.items(), key=lambda x: x[1]["coins"], reverse=True)
    text = "🏆 Leaderboard - Top 10 Players by Coins 🏆\n\n"
    for i, (uid, d) in enumerate(sorted_users[:10], 1):
        text += f"{i}. {d['name']} - {d['coins']} 🪙\n"
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Available Commands:\n\n"
        "/start - Welcome message and register\n"
        "/profile - Show your profile and stats\n"
        "/daily - Claim daily 500 🪙 bonus\n"
        "/pm [bet] - Start or join a PvP hand cricket match\n"
        "/leaderboard - Show top players by coins\n"
    )
    await update.message.reply_text(text)

# ====== Match buttons ======

def get_buttons():
    buttons = [
        [InlineKeyboardButton(str(n), callback_data=str(n)) for n in [1,2,3]],
        [InlineKeyboardButton(str(n), callback_data=str(n)) for n in [4,5,6]],
    ]
    return InlineKeyboardMarkup(buttons)

def join_keyboard(match_id):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Match", callback_data=f"join_{match_id}")]]
    )

# ====== /pm command to start/join match ======

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
    # Check if already in a match
    for m in matches.values():
        if uid in m["players"] and m["state"] in ["waiting_for_opponent", "playing"]:
            await update.message.reply_text("You are already in a match.")
            return

    # Create match
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
# ====== Helper function to edit match message ======
async def edit_match_message(context, match_id, text, reply_markup=None):
    match = matches.get(match_id)
    if not match:
        return
    chat_id = match["chat_id"]
    message_id = match["message_id"]
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception:
        pass  # Ignore edit errors (message deleted etc)

# ====== Callback Query Handler ======
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    uid = str(user.id)

    # Join match handler
    if data.startswith("join_"):
        match_id = data.split("_")[1]
        match = matches.get(match_id)
        if not match:
            await query.edit_message_text("Match not found or already started.")
            return
        if uid in match["players"]:
            await query.answer("You are already in this match.", show_alert=True)
            return
        if len(match["players"]) >= 2:
            await query.answer("Match is full.", show_alert=True)
            return
        bet = match["bet"]
        if users[uid]["coins"] < bet:
            await query.answer("You don't have enough coins for this bet.", show_alert=True)
            return
        # Add player 2
        match["players"].append(uid)
        match["player_names"][uid] = get_name(uid)
        match["scores"][uid] = 0
        match["state"] = "toss"
        match["bowler"] = uid  # temporarily set, will be updated after toss
        save_matches()

        text = (
            f"Match started between {match['player_names'][match['players'][0]]} and {match['player_names'][uid]}.\n\n"
            "Toss time! Both players select Heads or Tails.\n"
            "Waiting for toss choice..."
        )
        # Toss buttons
        toss_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Heads", callback_data=f"toss_{match_id}_heads"),
                InlineKeyboardButton("Tails", callback_data=f"toss_{match_id}_tails"),
            ]
        ])
        await edit_match_message(context, match_id, text, toss_buttons)
        return

    # Toss handling
    if data.startswith("toss_"):
        parts = data.split("_")
        match_id = parts[1]
        choice = parts[2]
        match = matches.get(match_id)
        if not match or match["state"] != "toss":
            await query.answer("Invalid toss state.")
            return
        if uid not in match["players"]:
            await query.answer("You are not part of this match.")
            return
        if "toss_choices" not in match:
            match["toss_choices"] = {}
        if uid in match["toss_choices"]:
            await query.answer("You have already chosen toss side.")
            return
        match["toss_choices"][uid] = choice
        save_matches()

        if len(match["toss_choices"]) < 2:
            await query.edit_message_text(
                f"{match['player_names'][uid]} chose {choice}. Waiting for other player..."
            )
            return

        # Both chose toss, decide winner
        toss_winner = None
        toss_choice = random.choice(["heads", "tails"])
        p1, p2 = match["players"]
        p1_choice = match["toss_choices"].get(p1)
        p2_choice = match["toss_choices"].get(p2)
        if toss_choice == p1_choice:
            toss_winner = p1
        else:
            toss_winner = p2

        match["state"] = "toss_result"
        match["toss_winner"] = toss_winner
        match["toss_choice"] = toss_choice
        match["toss_choices"] = None  # clear toss choices for innings
        save_matches()

        text = (
            f"Toss coin landed on *{toss_choice.capitalize()}*.\n"
            f"{match['player_names'][toss_winner]} won the toss!\n\n"
            "Choose to bat or bowl first."
        )
        bat_bowl_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Bat", callback_data=f"choice_{match_id}_bat"),
                InlineKeyboardButton("Bowl", callback_data=f"choice_{match_id}_bowl"),
            ]
        ])
        await edit_match_message(context, match_id, text, bat_bowl_buttons)
        return

    # Bat/Bowl choice after toss
    if data.startswith("choice_"):
        parts = data.split("_")
        match_id = parts[1]
        choice = parts[2]  # bat or bowl
        match = matches.get(match_id)
        if not match or match["state"] != "toss_result":
            await query.answer("Invalid choice state.")
            return
        if uid != match["toss_winner"]:
            await query.answer("Only toss winner can choose.")
            return
        p1, p2 = match["players"]
        if choice == "bat":
            match["batsman"] = uid
            match["bowler"] = p2 if p1 == uid else p1
        else:
            match["bowler"] = uid
            match["batsman"] = p2 if p1 == uid else p1
        match["state"] = "playing"
        match["innings"] = 1
        match["scores"] = {p1: 0, p2: 0}
        match["chosen"] = {}
        match["target"] = None
        save_matches()

        text = (
            f"Match started!\n\n"
            f"🏏 *{match['player_names'][match['batsman']]}* is batting first.\n"
            f"🎳 *{match['player_names'][match['bowler']]}* is bowling first.\n\n"
            "Batsman, please choose your number."
        )
        await edit_match_message(context, match_id, text, get_buttons())
        return

    # Gameplay number selection
    if data in ["1","2","3","4","5","6"]:
        match_id = None
        # find which match this user is in and in playing state
        for mid, m in matches.items():
            if m["state"] == "playing" and uid in m["players"]:
                match_id = mid
                break
        if not match_id:
            await query.answer("You are not in an active match.")
            return
        match = matches[match_id]

        # Check whose turn
        if "turn" not in match or match["turn"] is None:
            # start with batsman turn
            match["turn"] = "batsman"

        # Save choice based on turn
        if match["turn"] == "batsman":
            if uid != match["batsman"]:
                await query.answer("It's batsman's turn to choose.")
                return
            if "batsman_choice" in match["chosen"]:
                await query.answer("You already chose. Waiting for bowler.")
                return
            match["chosen"]["batsman_choice"] = int(data)
            save_matches()
            # Prompt bowler
            text = (
                f"{match['player_names'][uid]} chose the number.\n"
                f"Now it's {match['player_names'][match['bowler']]}'s turn to bowl.\n"
                "Bowler, please choose your number."
            )
            await edit_match_message(context, match_id, text, get_buttons())
            match["turn"] = "bowler"
            save_matches()
            return

        if match["turn"] == "bowler":
            if uid != match["bowler"]:
                await query.answer("It's bowler's turn to choose.")
                return
            if "bowler_choice" in match["chosen"]:
                await query.answer("You already chose. Waiting for processing.")
                return
            match["chosen"]["bowler_choice"] = int(data)
            save_matches()

            # Now both choices are in, calculate result
            b_choice = match["chosen"]["batsman_choice"]
            bow_choice = match["chosen"]["bowler_choice"]
            batsman = match["batsman"]
            bowler = match["bowler"]

            # Reveal both choices
            over = match.get("over", 1)
            batsman_name = match["player_names"][batsman]
            bowler_name = match["player_names"][bowler]

            # Calculate wicket or runs
            if b_choice == bow_choice:
                # Wicket falls
                text = (
                    f"Over {over}\n"
                    f"*{batsman_name}* chose {b_choice} and *{bowler_name}* chose {bow_choice}.\n\n"
                    f"WICKET! {batsman_name} is OUT.\n"
                )
                # End innings or match
                if match["innings"] == 1:
                    # Switch innings
                    match["innings"] = 2
                    match["target"] = match["scores"][batsman] + 1
                    # Swap batsman and bowler
                    match["batsman"], match["bowler"] = match["bowler"], match["batsman"]
                    match["chosen"] = {}
                    match["turn"] = "batsman"
                    match["over"] = match.get("over", 1) + 1
                    text += (
                        f"Innings 1 ended. Target for {match['player_names'][match['batsman']]}: {match['target']} runs.\n\n"
                        f"{match['player_names'][match['batsman']]}, you are batting now. Choose your number."
                    )
                    save_matches()
                    await edit_match_message(context, match_id, text, get_buttons())
                    return
                else:
                    # Innings 2 wicket = match over
                    # Decide winner
                    p1, p2 = match["players"]
                    score1 = match["scores"][p1]
                    score2 = match["scores"][p2]
                    if score1 > score2:
                        winner = p1
                    elif score2 > score1:
                        winner = p2
                    else:
                        winner = None  # Draw or super ball scenario can be added

                    if winner:
                        users[winner]["wins"] += 1
                        loser = p2 if winner == p1 else p1
                        users[loser]["losses"] += 1
                        if match["bet"] > 0:
                            users[winner]["coins"] += 2 * match["bet"]
                    else:
                        # Draw: refund bets
                        if match["bet"] > 0:
                            users[p1]["coins"] += match["bet"]
                            users[p2]["coins"] += match["bet"]

                    save_users()
                    save_matches()

                    result_text = f"Match Over!\n"
                    if winner:
                        result_text += f"🏆 {match['player_names'][winner]} wins the match!\n"
                    else:
                        result_text += "Match is a Draw!\n"

                    result_text += (
                        f"Final Scores:\n"
                        f"{match['player_names'][p1]}: {score1}\n"
                        f"{match['player_names'][p2]}: {score2}\n"
                    )
                    await edit_match_message(context, match_id, text + "\n" + result_text)
                    # Remove match
                    matches.pop(match_id)
                    save_matches()
                    return
            else:
                # Runs scored
                match["scores"][batsman] += b_choice
                over = match.get("over", 1)
                text = (
                    f"Over {over}\n"
                    f"*{batsman_name}* chose {b_choice} and *{bowler_name}* chose {bow_choice}.\n"
                    f"Runs scored: {b_choice}\n"
                    f"Current Score: {match['scores'][batsman]}\n\n"
                    f"{batsman_name}, choose your next number."
                )
                match["chosen"] = {}
                match["turn"] = "batsman"
                match["over"] = over + 1
                save_matches()
                await edit_match_message(context, match_id, text, get_buttons())
                return


# ====== Main function to start bot ======
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("pm", pm))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()

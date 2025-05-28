# --- Telegram Hand Cricket Bot (Part 1/3) ---

# ✅ All Import Statements Here
import json
import os
import random
import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ✅ Bot Token and Admins
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMINS = [123456789]  # Replace with actual Telegram user IDs

# ✅ File paths
USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

# ✅ Utility: Load/Save JSON Data
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# ✅ Data Storage
users = load_json(USERS_FILE)
matches = load_json(MATCHES_FILE)

# ✅ Save Data Periodically
def save_all():
    save_json(USERS_FILE, users)
    save_json(MATCHES_FILE, matches)

# ✅ Helper: Format user profile
def get_profile(user_id):
    u = users.get(str(user_id), {})
    return f"""👤 *Name:* {u.get('name', 'N/A')}
🆔 *ID:* `{user_id}`
💰 *Coins:* ₹{u.get('coins', 0)}
🏏 *Wins:* {u.get('wins', 0)}
💔 *Losses:* {u.get('losses', 0)}"""

# ✅ Ensure User Exists
def ensure_user(user: Update.effective_user):
    uid = str(user.id)
    if uid not in users:
        users[uid] = {
            "name": user.first_name,
            "coins": 500,
            "wins": 0,
            "losses": 0,
            "daily": ""
        }
# --- Telegram Hand Cricket Bot (Part 2/3) ---

# ✅ /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.message.reply_text(
        "🏏 *Welcome to Hand Cricket Bot!*\n\n"
        "Use /register to claim coins and start playing!\n\n"
        "Available Commands:\n"
        "• /pm <bet> - Start PvP Match\n"
        "• /profile - View Your Stats\n"
        "• /daily - Claim Daily Bonus\n"
        "• /leaderboard - Top Users\n"
        "• /help - Commands\n"
        "• /add <id> <coins> - [Admin]\n",
        parse_mode=ParseMode.MARKDOWN
    )

# ✅ /register command
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    uid = str(user.id)
    if users[uid]["coins"] == 0:
        users[uid]["coins"] = 500
        await update.message.reply_text("🎉 You've been registered and received ₹500!")
    else:
        await update.message.reply_text("✅ You're already registered!")
    save_all()

# ✅ /profile command
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    text = get_profile(update.effective_user.id)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ✅ /daily command
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    uid = str(user.id)
    today = str(datetime.date.today())
    if users[uid]["daily"] == today:
        await update.message.reply_text("🕒 You already claimed your daily bonus.")
    else:
        users[uid]["coins"] += 200
        users[uid]["daily"] = today
        await update.message.reply_text("💸 You received ₹200 daily bonus!")
    save_all()

# ✅ /leaderboard command
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(users.items(), key=lambda x: x[1].get("coins", 0), reverse=True)[:10]
    text = "*🏆 Top 10 Users by Coins:*\n\n"
    for i, (uid, u) in enumerate(top, 1):
        text += f"{i}. {u['name']} - ₹{u['coins']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ✅ /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Available Commands:*\n\n"
        "/start - Welcome Guide\n"
        "/register - Claim Free Coins\n"
        "/pm <bet> - Start Match (Optional Bet)\n"
        "/profile - View Your Stats\n"
        "/daily - Get Daily Bonus\n"
        "/leaderboard - Top Users\n"
        "/add <id> <coins> - Admins Only\n",
        parse_mode=ParseMode.MARKDOWN
    )

# ✅ /add <user_id> <coins>
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMINS:
        await update.message.reply_text("⛔ You are not authorized to use this.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <coins>")
        return
    try:
        target_id = str(context.args[0])
        coins = int(context.args[1])
        ensure_user(Update.effective_user)
        users[target_id]["coins"] += coins
        await update.message.reply_text(f"✅ Added ₹{coins} to {target_id}")
        save_all()
    except Exception as e:
        await update.message.reply_text("❌ Error: " + str(e))

# ✅ /pm [<bet>] - start match
async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    uid = str(user.id)

    if uid in matches:
        await update.message.reply_text("⛔ You're already in a match.")
        return

    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if users[uid]["coins"] < bet:
                await update.message.reply_text("💸 Not enough coins to place this bet.")
                return
        except:
            await update.message.reply_text("Usage: /pm <bet> (optional)")
            return

    match_id = str(update.message.message_id)
    matches[uid] = {
        "id": match_id,
        "player1": uid,
        "player2": None,
        "bet": bet,
        "turn": None,
        "innings": 1,
        "scores": {uid: 0},
        "wickets": {uid: 0},
        "choices": {},
        "msg_id": None,
        "target": None
    }

    join_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Match", callback_data=f"join_{uid}")]
    ])
    msg = await update.message.reply_text(
        f"🎮 *{user.first_name}* started a match!\n"
        f"💰 Bet: ₹{bet}\n\n"
        f"Waiting for an opponent...",
        reply_markup=join_btn,
        parse_mode=ParseMode.MARKDOWN
    )
    matches[uid]["msg_id"] = msg.message_id
    save_all()
# --- Telegram Hand Cricket Bot (Part 3/4) ---

# ✅ Handle Join Match
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("join_"):
        p1_id = data.split("_")[1]
        p2_id = str(query.from_user.id)

        if p1_id == p2_id:
            await query.edit_message_text("⛔ You can't join your own match.")
            return
        if p2_id in matches:
            await query.edit_message_text("⛔ You're already in a match.")
            return

        match = matches.get(p1_id)
        if not match or match["player2"]:
            await query.edit_message_text("❌ Match not found or already joined.")
            return

        match["player2"] = p2_id
        match["scores"][p2_id] = 0
        match["wickets"][p2_id] = 0

        users[p1_id]["coins"] -= match["bet"]
        users[p2_id]["coins"] -= match["bet"]

        save_all()

        toss_btns = InlineKeyboardMarkup([
            [InlineKeyboardButton("Heads", callback_data=f"toss_H_{p1_id}_{p2_id}"),
             InlineKeyboardButton("Tails", callback_data=f"toss_T_{p1_id}_{p2_id}")]
        ])

        await query.edit_message_text(
            f"🆚 *Match Started!*\n\n"
            f"{users[p1_id]['name']} vs {users[p2_id]['name']}\n\n"
            f"{users[p1_id]['name']}, choose Heads or Tails for toss:",
            reply_markup=toss_btns,
            parse_mode=ParseMode.MARKDOWN
        )

# ✅ Handle Toss
async def toss_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    call = data[1]
    p1, p2 = data[2], data[3]
    match = matches.get(p1)

    if not match or match["player2"] != p2:
        await query.edit_message_text("❌ Invalid toss or expired match.")
        return

    toss_result = random.choice(["H", "T"])
    winner = p1 if toss_result == call else p2
    loser = p2 if winner == p1 else p1

    match["turn"] = winner  # batting first
    match["innings"] = 1
    match["choices"] = {}

    save_all()

    await query.edit_message_text(
        f"🪙 Toss Result: *{toss_result}*\n"
        f"{users[winner]['name']} won the toss and will bat first.\n\n"
        f"{users[winner]['name']} to choose a number (1–6)",
        reply_markup=build_number_buttons(winner),
        parse_mode=ParseMode.MARKDOWN
    )

# ✅ Build Buttons (1-6)
def build_number_buttons(player_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"num_{player_id}_{i}")]
        for i in range(1, 7)
    ])

# ✅ Handle Number Inputs (Bat/Bowl)
async def num_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    pid, num = data[1], int(data[2])
    uid = str(query.from_user.id)

    # Find the match this user is part of
    match = None
    for m in matches.values():
        if uid in [m["player1"], m["player2"]]:
            match = m
            break

    if not match or uid not in [match["player1"], match["player2"]]:
        await query.edit_message_text("❌ You are not part of any match.")
        return

    match["choices"][uid] = num
    opponent_id = match["player2"] if uid == match["player1"] else match["player1"]

    if opponent_id not in match["choices"]:
        await query.edit_message_text(
            f"✅ You chose a number.\n"
            f"Waiting for {users[opponent_id]['name']} to respond..."
        )
        return

    # Both have chosen: reveal outcome
    p1, p2 = match["player1"], match["player2"]
    bat = match["turn"]
    bowl = p2 if bat == p1 else p1

    bat_num = match["choices"][bat]
    bowl_num = match["choices"][bowl]

    msg = f"🏏 {users[bat]['name']} (Bat): {bat_num}  |  {users[bowl]['name']} (Bowl): {bowl_num}\n"

    if bat_num == bowl_num:
        match["wickets"][bat] += 1
        msg += f"💥 WICKET! {users[bat]['name']} is OUT!\n"
    else:
        match["scores"][bat] += bat_num
        msg += f"➕ {bat_num} runs added."

    match["choices"] = {}

    # Check innings or game end
    if match["wickets"][bat] >= 1:  # 1 wicket per player (for now)
        if match["innings"] == 1:
            match["innings"] = 2
            match["turn"] = bowl
            match["target"] = match["scores"][bat] + 1
            msg += f"\n\n🎯 Target for {users[bowl]['name']}: {match['target']}"
        else:
            # Game over: determine winner
            p1_score = match["scores"][p1]
            p2_score = match["scores"][p2]
            winner = p1 if p1_score > p2_score else p2
            loser = p2 if winner == p1 else p1
            msg += f"\n\n🏁 Match Over!\nWinner: {users[winner]['name']}\n"

            # Coins + Win count
            prize = match["bet"] * 2 if match["bet"] else 0
            users[winner]["coins"] += prize
            users[winner]["wins"] += 1
            users[loser]["losses"] += 1

            # Remove match
            del matches[p1]
            save_all()

            await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

    save_all()
    await query.edit_message_text(
        msg + f"\n\n👉 {users[match['turn']]['name']} to play next.",
        reply_markup=build_number_buttons(match["turn"]),
        parse_mode=ParseMode.MARKDOWN
    )
# --- Telegram Hand Cricket Bot (Part 4/4) ---

# ✅ Main Function
def main():
    app = Application.builder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("pm", pm))

    # CallbackQuery handlers (buttons)
    app.add_handler(CallbackQueryHandler(button_handler, pattern=r"^join_"))
    app.add_handler(CallbackQueryHandler(toss_handler, pattern=r"^toss_"))
    app.add_handler(CallbackQueryHandler(num_handler, pattern=r"^num_"))

    # Start polling
    print("🤖 Bot is running...")
    app.run_polling()

# ✅ Entry Point
if __name__ == "__main__":
    main()

# Part 1 - Telegram Hand Cricket Bot (with emojis)

import json
import random
import time
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters
)

TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
DATA_FILE = "users.json"
MATCH_FILE = "matches.json"
admins = [123456789]  # Replace with actual admin Telegram user ID

def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_matches():
    try:
        with open(MATCH_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_matches(data):
    with open(MATCH_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=str(i)) for i in [1, 2, 3]],
        [InlineKeyboardButton(str(i), callback_data=str(i)) for i in [4, 5, 6]]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 *Welcome to Hand Cricket Bot!*\n\n"
        "Use /register to get started and receive free coins.\n"
        "Here are some commands:\n\n"
        "🎮 /pm <bet> - Start or join a PvP match\n"
        "👤 /profile - View your stats\n"
        "🎁 /daily - Claim your daily bonus\n"
        "🏆 /leaderboard - See top players\n"
        "🆘 /help - Show all commands",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 *Command List:*\n\n"
        "🆕 /register - Register and get free coins\n"
        "🎮 /pm <bet> - Start or join a PvP match\n"
        "👤 /profile - View your stats\n"
        "🎁 /daily - Claim daily bonus coins\n"
        "🏆 /leaderboard - View top players\n"
        "🛠️ /add <user_id> <coins> - (Admin only)",
        parse_mode="Markdown"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    data = load_data()
    if user_id in data:
        await update.message.reply_text("✅ You're already registered!")
    else:
        data[user_id] = {"coins": 500, "wins": 0, "daily": "1970-01-01"}
        save_data(data)
        await update.message.reply_text("🎉 Registration successful! You've received ₹500.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    data = load_data()
    if user_id in data:
        u = data[user_id]
        await update.message.reply_text(
            f"👤 *Your Profile:*\n\n"
            f"💰 Coins: ₹{u['coins']}\n"
            f"🏆 Wins: {u['wins']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ You're not registered yet! Use /register first.")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    data = load_data()
    if user_id not in data:
        await update.message.reply_text("⚠️ You need to /register first.")
        return

    last_claim = datetime.strptime(data[user_id]["daily"], "%Y-%m-%d")
    now = datetime.now()
    if now.date() > last_claim.date():
        data[user_id]["coins"] += 250
        data[user_id]["daily"] = now.strftime("%Y-%m-%d")
        save_data(data)
        await update.message.reply_text("🎁 You've claimed ₹250 daily bonus!")
    else:
        await update.message.reply_text("⏳ You already claimed your daily bonus today.")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) not in map(str, admins):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    try:
        uid, coins = context.args
        data = load_data()
        if uid in data:
            data[uid]["coins"] += int(coins)
            save_data(data)
            await update.message.reply_text("✅ Coins added successfully.")
        else:
            await update.message.reply_text("⚠️ User not found.")
    except:
        await update.message.reply_text("⚠️ Usage: /add <user_id> <coins>")
# Part 2 - Match logic, toss, leaderboard, buttons (with emojis)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    top = sorted(data.items(), key=lambda x: x[1]["coins"], reverse=True)[:10]
    text = "🏆 *Top 10 Richest Players:*\n\n"
    for i, (uid, u) in enumerate(top, 1):
        text += f"{i}. 🧑 ID: `{uid}` - 💰 ₹{u['coins']} | 🏆 {u['wins']} wins\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = str(user.id)
    data = load_data()
    if user_id not in data:
        await update.message.reply_text("⚠️ Please /register first.")
        return

    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if data[user_id]["coins"] < bet:
                await update.message.reply_text("💸 Not enough coins to bet.")
                return
        except:
            await update.message.reply_text("⚠️ Invalid bet amount.")
            return

    matches = load_matches()
    for mid, match in matches.items():
        if match["status"] == "waiting" and match["player1_id"] != user_id:
            match["player2_id"] = user_id
            match["status"] = "toss"
            match["bet"] = bet
            save_matches(matches)
            await context.bot.edit_message_text(
                chat_id=match["chat_id"],
                message_id=match["msg_id"],
                text=f"🎮 Match Started!\n\n"
                     f"👤 {match['player1_name']} vs 👤 {user.full_name}\n\n"
                     "🪙 Toss Time!\nChoose Heads or Tails:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🪙 Heads", callback_data="toss_heads"),
                     InlineKeyboardButton("🔄 Tails", callback_data="toss_tails")]
                ])
            )
            return

    msg = await update.message.reply_text(
        f"🎯 Waiting for opponent...\n"
        f"👤 Player 1: {user.full_name}\n"
        f"💰 Bet: ₹{bet}\n\n"
        f"Tap 'Join' to play!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Join", callback_data=f"join|{user_id}|{user.full_name}|{bet}")]
        ])
    )
    match_id = str(msg.message_id)
    matches[match_id] = {
        "status": "waiting",
        "player1_id": user_id,
        "player1_name": user.full_name,
        "chat_id": msg.chat.id,
        "msg_id": msg.message_id,
        "bet": bet
    }
    save_matches(matches)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = load_data()
    matches = load_matches()

    if query.data.startswith("join|"):
        _, p1_id, p1_name, bet = query.data.split("|")
        if user_id == p1_id:
            await query.answer("⛔ You can't join your own match.", show_alert=True)
            return
        match_id = str(query.message.message_id)
        matches[match_id] = {
            "status": "toss",
            "player1_id": p1_id,
            "player1_name": p1_name,
            "player2_id": user_id,
            "player2_name": query.from_user.full_name,
            "chat_id": query.message.chat.id,
            "msg_id": query.message.message_id,
            "bet": int(bet)
        }
        save_matches(matches)
        await context.bot.edit_message_text(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            text=f"🎮 Match Started!\n\n"
                 f"👤 {p1_name} vs 👤 {query.from_user.full_name}\n\n"
                 "🪙 Toss Time!\nChoose Heads or Tails:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🪙 Heads", callback_data="toss_heads"),
                 InlineKeyboardButton("🔄 Tails", callback_data="toss_tails")]
            ])
        )
        return

    match_id = str(query.message.message_id)
    match = matches.get(match_id)

    if match and match["status"] == "toss" and user_id == match["player1_id"]:
        player_choice = "heads" if "heads" in query.data else "tails"
        bot_choice = random.choice(["heads", "tails"])
        toss_winner = user_id if player_choice == bot_choice else match["player2_id"]
        match["toss_winner"] = toss_winner
        match["status"] = "choose_bat_bowl"
        match["batting"] = None
        match["bowling"] = None
        save_matches(matches)

        toss_text = "✅ You won the toss! Choose to bat or bowl:" if toss_winner == user_id else "🎲 You lost the toss. Opponent will choose."

        if toss_winner == user_id:
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=f"🪙 Toss result: You chose *{player_choice.capitalize()}*, bot chose *{bot_choice.capitalize()}*\n\n{toss_text}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏏 Bat", callback_data="choose_bat"),
                     InlineKeyboardButton("🎯 Bowl", callback_data="choose_bowl")]
                ]),
                parse_mode="Markdown"
            )
        else:
            match["batting"] = match["player2_id"]
            match["bowling"] = match["player1_id"]
            match["status"] = "playing"
            match["turn"] = "bat"
            match["scores"] = {match["batting"]: 0}
            match["numbers"] = {}
            save_matches(matches)
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=f"🪙 Toss result: You chose *{player_choice.capitalize()}*, bot chose *{bot_choice.capitalize()}*\n\n"
                     f"👤 {match['player2_name']} chose to bat first!\n\n"
                     "🎮 Let the game begin!",
                reply_markup=get_keyboard(),
                parse_mode="Markdown"
            )
        return

    if match and match["status"] == "choose_bat_bowl" and user_id == match["toss_winner"]:
        if query.data == "choose_bat":
            match["batting"] = user_id
            match["bowling"] = match["player2_id"] if user_id == match["player1_id"] else match["player1_id"]
        else:
            match["bowling"] = user_id
            match["batting"] = match["player2_id"] if user_id == match["player1_id"] else match["player1_id"]
        match["status"] = "playing"
        match["turn"] = "bat"
        match["scores"] = {match["batting"]: 0}
        match["numbers"] = {}
        save_matches(matches)
        await context.bot.edit_message_text(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            text=f"🏏 {query.from_user.full_name} chose to {'bat' if query.data == 'choose_bat' else 'bowl'} first!\n\n"
                 f"🎮 Let the game begin!",
            reply_markup=get_keyboard()
        )
        return

    if match and match["status"] == "playing":
        if user_id not in [match["batting"], match["bowling"]]:
            await query.answer("⛔ You're not part of this match.", show_alert=True)
            return

        match["numbers"][user_id] = int(query.data)

        if len(match["numbers"]) == 2:
            b_num = match["numbers"][match["batting"]]
            bw_num = match["numbers"][match["bowling"]]
            out = b_num == bw_num
            if out:
                text = f"💥 WICKET! {match['batting']} chose {b_num}, {match['bowling']} chose {bw_num}.\n\n"
                text += f"🏁 First innings over. Total: {match['scores'][match['batting']]}\n"
                match["batting"], match["bowling"] = match["bowling"], match["batting"]
                match["scores"][match["batting"]] = 0
                match["target"] = match["scores"][match["bowling"]] + 1
            else:
                match["scores"][match["batting"]] += b_num
                text = f"🏏 {match['batting']} chose {b_num}, {match['bowling']} chose {bw_num}.\n"
                text += f"✅ Total: {match['scores'][match['batting']]}"
            match["numbers"] = {}
            save_matches(matches)
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=text,
                reply_markup=get_keyboard()
            )
        else:
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=f"⏳ {query.from_user.first_name} has chosen a number. Waiting for opponent...",
                reply_markup=get_keyboard()
        )
# Part 3 - Match end, winner logic, coin handling (with emojis)

def get_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣", callback_data="1"),
         InlineKeyboardButton("2️⃣", callback_data="2"),
         InlineKeyboardButton("3️⃣", callback_data="3")],
        [InlineKeyboardButton("4️⃣", callback_data="4"),
         InlineKeyboardButton("5️⃣", callback_data="5"),
         InlineKeyboardButton("6️⃣", callback_data="6")]
    ])

async def process_match_end(context, match_id, match, query):
    data = load_data()
    p1_id, p2_id = match["player1_id"], match["player2_id"]
    p1_score = match["scores"].get(p1_id, 0)
    p2_score = match["scores"].get(p2_id, 0)
    target = match.get("target", 0)
    bet = match.get("bet", 0)

    if match["batting"] == p1_id:
        p1_score += match["numbers"].get(p1_id, 0)
    else:
        p2_score += match["numbers"].get(p2_id, 0)

    winner_id = None
    if p1_score > p2_score:
        winner_id = p1_id
        result_text = f"🏆 {match['player1_name']} Wins!"
    elif p2_score > p1_score:
        winner_id = p2_id
        result_text = f"🏆 {match['player2_name']} Wins!"
    else:
        result_text = "🤝 It's a Tie!"

    if winner_id:
        data[winner_id]["coins"] += bet * 2 if bet else 50
        data[winner_id]["wins"] += 1
        result_text += f"\n💰 Earned: ₹{bet * 2 if bet else 50}"
    else:
        data[p1_id]["coins"] += bet
        data[p2_id]["coins"] += bet
        result_text += f"\n💸 Both players refunded ₹{bet}"

    save_data(data)

    final_text = (
        f"🎯 *Match Over!*\n\n"
        f"👤 {match['player1_name']}: {p1_score} runs\n"
        f"👤 {match['player2_name']}: {p2_score} runs\n\n"
        f"{result_text}\n\n"
        f"🔁 Use /pm to play again!"
    )

    await context.bot.edit_message_text(
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        text=final_text,
        parse_mode="Markdown"
    )

    matches = load_matches()
    matches.pop(match_id, None)
    save_matches(matches)

# Add to button_handler: game end check
# Replace after updating score logic

if match["status"] == "playing":
    # ... existing code ...
    if out:
        # Switch innings or end game
        if "target" not in match:
            # First innings over
            match["batting"], match["bowling"] = match["bowling"], match["batting"]
            match["scores"][match["batting"]] = 0
            match["target"] = match["scores"][match["bowling"]] + 1
            match["numbers"] = {}
            match["status"] = "playing"
            save_matches(matches)
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
            message_id=query.message.message_id,
                text=f"💥 OUT!\n\n"
                     f"👤 {match['bowling']} will now bat.\n"
                     f"🎯 Target: {match['target']} runs\n\n"
                     f"🏏 Let the 2nd innings begin!",
                reply_markup=get_keyboard()
          )
        else:
            # Second innings out, end match
            await process_match_end(context, match_id, match, query)
    else:
        # If target is set (2nd innings), check if surpassed
        if "target" in match and match["scores"][match["batting"]] >= match["target"]:
            await process_match_end(context, match_id, match, query)
        else:
            save_matches(matches)
            await context.bot.edit_message_text(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text=text,
                reply_markup=get_keyboard()
        )
def main():
    updater = Updater("YOUR_BOT_TOKEN_HERE", use_context=True)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("register", register))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("leaderboard", leaderboard))
    dp.add_handler(CommandHandler("add", add_coins))
    dp.add_handler(CommandHandler("pm", pm))

    # Button callback handler
    dp.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()

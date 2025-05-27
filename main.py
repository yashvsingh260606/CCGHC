# ======== PART 1 ========

import json
import time
import logging
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext
)

BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
admins = ["123456789"]  # Replace with real admin IDs

USERS_FILE = "users_data.json"
MATCHES_FILE = "matches_data.json"

users = {}
matches = {}

def load_data():
    global users, matches
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
    except:
        users = {}
    try:
        with open(MATCHES_FILE, "r") as f:
            matches = json.load(f)
    except:
        matches = {}

def save_data():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f, indent=2)

def get_user(uid):
    if uid not in users:
        users[uid] = {"coins": 1000, "wins": 0, "last_daily": 0}
        save_data()
    return users[uid]

def is_admin(uid):
    return str(uid) in admins

def number_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data='num_1'), InlineKeyboardButton("2", callback_data='num_2'), InlineKeyboardButton("3", callback_data='num_3')],
        [InlineKeyboardButton("4", callback_data='num_4'), InlineKeyboardButton("5", callback_data='num_5'), InlineKeyboardButton("6", callback_data='num_6')],
    ])

def current_time():
    return int(time.time())

def start(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    get_user(uid)
    update.message.reply_text(
        "Welcome to Hand Cricket Bot!\n\n"
        "/pm <bet> - Start PvP match\n"
        "/profile - Your stats\n"
        "/daily - Claim coins\n"
        "/leaderboard - Top users\n"
        "/help - All commands"
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "/pm <bet> - Start PvP match\n"
        "/profile - Your stats\n"
        "/daily - Claim coins\n"
        "/leaderboard - Top users\n"
        "/help - All commands"
    )

def profile(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    u = get_user(uid)
    update.message.reply_text(f"Coins: {u['coins']}\nWins: {u['wins']}")

def daily(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    now = current_time()
    if now - user['last_daily'] < 86400:
        update.message.reply_text("Already claimed today!")
        return
    user['coins'] += 500
    user['last_daily'] = now
    save_data()
    update.message.reply_text("You claimed 500 daily coins!")

def leaderboard(update: Update, context: CallbackContext):
    top = sorted(users.items(), key=lambda x: x[1]["coins"], reverse=True)[:10]
    text = "🏆 Leaderboard (Top 10 by Coins):\n\n"
    for i, (uid, udata) in enumerate(top, 1):
        try:
            name = context.bot.get_chat_member(update.effective_chat.id, int(uid)).user.first_name
        except:
            name = "User"
        text += f"{i}. {name} - {udata['coins']} coins\n"
    update.message.reply_text(text)

def add_coins(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    if not is_admin(uid):
        update.message.reply_text("Admins only!")
        return
    try:
        target = context.args[0]
        amount = int(context.args[1])
        get_user(target)["coins"] += amount
        save_data()
        update.message.reply_text("Coins added.")
    except:
        update.message.reply_text("Usage: /add <user_id> <coins>")
# ======== PART 2 ========

def pm(update: Update, context: CallbackContext):
    uid = str(update.effective_user.id)
    if not context.args or not context.args[0].isdigit():
        update.message.reply_text("Usage: /pm <bet>")
        return
    bet = int(context.args[0])
    user = get_user(uid)
    if user["coins"] < bet:
        update.message.reply_text("You don't have enough coins!")
        return
    match_id = str(update.message.message_id)
    matches[match_id] = {
        "bet": bet,
        "player1": uid,
        "player2": None,
        "status": "waiting",
        "msg_id": None,
        "chat_id": update.message.chat_id,
    }
    save_data()
    join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("Join", callback_data=f"join_{match_id}")]])
    msg = update.message.reply_text(f"{update.effective_user.first_name} started a match for {bet} coins.\nClick to join!", reply_markup=join_btn)
    matches[match_id]["msg_id"] = msg.message_id
    save_data()

def join_match_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data
    uid = str(query.from_user.id)
    if not data.startswith("join_"):
        return
    match_id = data.split("_")[1]
    match = matches.get(match_id)
    if not match or match["player2"] is not None:
        query.edit_message_text("Match no longer available.")
        return
    if uid == match["player1"]:
        query.answer("You can't join your own match.")
        return
    p1 = get_user(match["player1"])
    p2 = get_user(uid)
    if p2["coins"] < match["bet"]:
        query.answer("You don't have enough coins!")
        return
    match["player2"] = uid
    match["status"] = "toss"
    match["turn"] = match["player1"]
    match["batting"] = None
    match["innings"] = 1
    match["scores"] = {match["player1"]: 0, match["player2"]: 0}
    match["balls"] = 0
    match["target"] = None
    match["selected"] = {}
    save_data()
    context.bot.edit_message_text(
        f"Match joined!\n{query.from_user.first_name} vs {context.bot.get_chat(match['chat_id']).get_member(int(match['player1'])).user.first_name}\n\nToss time! {context.bot.get_chat(match['chat_id']).get_member(int(match['player1'])).user.first_name}, choose:",
        chat_id=match["chat_id"],
        message_id=match["msg_id"],
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Heads", callback_data=f"toss_H"), InlineKeyboardButton("Tails", callback_data=f"toss_T")]
        ])
    )

def toss_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    uid = str(query.from_user.id)
    data = query.data
    match_id = None
    for mid, m in matches.items():
        if m.get("status") == "toss" and m["player1"] == uid:
            match_id = mid
            break
    if not match_id:
        return
    choice = data.split("_")[1]
    result = "H" if time.time() % 2 < 1 else "T"
    match = matches[match_id]
    winner = match["player1"] if choice == result else match["player2"]
    match["batting"] = winner
    match["bowling"] = match["player1"] if winner == match["player2"] else match["player2"]
    match["status"] = "play"
    match["balls"] = 0
    match["selected"] = {}
    save_data()
    context.bot.edit_message_text(
        f"Toss result: {result}\n{context.bot.get_chat(match['chat_id']).get_member(int(winner)).user.first_name} won and will bat first.\n\nBatsman, choose a number:",
        chat_id=match["chat_id"],
        message_id=match["msg_id"],
        reply_markup=number_buttons()
    )

def handle_number(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    uid = str(query.from_user.id)
    num = int(query.data.split("_")[1])
    for match_id, m in matches.items():
        if m.get("status") == "play" and uid in [m["batting"], m["bowling"]]:
            match = m
            break
    else:
        return
    if uid in match["selected"]:
        return
    match["selected"][uid] = num
    if len(match["selected"]) == 1:
        waiting = match["bowling"] if uid == match["batting"] else match["batting"]
        context.bot.edit_message_reply_markup(
            chat_id=match["chat_id"],
            message_id=match["msg_id"],
            reply_markup=None
        )
        context.bot.send_message(match["chat_id"], f"{query.from_user.first_name} chose a number.\nWaiting for opponent...")
    else:
        bat = match["batting"]
        bowl = match["bowling"]
        bnum = match["selected"][bat]
        blnum = match["selected"][bowl]
        if bnum == blnum:
            text = f"{context.bot.get_chat(match['chat_id']).get_member(int(bat)).user.first_name} chose {bnum}, {context.bot.get_chat(match['chat_id']).get_member(int(bowl)).user.first_name} chose {blnum}\n\n**OUT!**"
            if match["innings"] == 1:
                match["innings"] = 2
                match["target"] = match["scores"][bat] + 1
                match["batting"], match["bowling"] = bowl, bat
                match["selected"] = {}
                match["balls"] = 0
                text += f"\n\nInnings over. Target: {match['target']}\nNow it's {context.bot.get_chat(match['chat_id']).get_member(int(bowl)).user.first_name}'s turn to bat."
            else:
                p1, p2 = match["player1"], match["player2"]
                s1, s2 = match["scores"][p1], match["scores"][p2]
                if s1 == s2:
                    text += "\n\nMatch tied!"
                else:
                    winner = p1 if s1 > s2 else p2
                    get_user(winner)["coins"] += match["bet"]
                    get_user(winner)["wins"] += 1
                    loser = p2 if winner == p1 else p1
                    get_user(loser)["coins"] -= match["bet"]
                    text += f"\n\n{context.bot.get_chat(match['chat_id']).get_member(int(winner)).user.first_name} wins the match!"
                del matches[match_id]
                save_data()
                context.bot.send_message(match["chat_id"], text)
                return
        else:
            match["scores"][bat] += bnum
            match["balls"] += 1
            text = f"{context.bot.get_chat(match['chat_id']).get_member(int(bat)).user.first_name} chose {bnum}, {context.bot.get_chat(match['chat_id']).get_member(int(bowl)).user.first_name} chose {blnum}\n\n{context.bot.get_chat(match['chat_id']).get_member(int(bat)).user.first_name} continues. Score: {match['scores'][bat]}"
        match["selected"] = {}
        save_data()
        context.bot.send_message(match["chat_id"], text)
        if match_id in matches:
            context.bot.send_message(match["chat_id"], "Next turn. Batsman, choose a number:", reply_markup=number_buttons())

def main():
    load_data()
    updater = Updater(BOT_TOKEN,use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("leaderboard", leaderboard))
    dp.add_handler(CommandHandler("add", add_coins))
    dp.add_handler(CommandHandler("pm", pm))

    dp.add_handler(CallbackQueryHandler(join_match_callback, pattern=r"^join_"))
    dp.add_handler(CallbackQueryHandler(toss_choice, pattern=r"^toss_"))
    dp.add_handler(CallbackQueryHandler(handle_number, pattern=r"^num_"))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

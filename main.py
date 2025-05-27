# Part 1: main.py
import json, time, random, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# Bot token
TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# Admin IDs
ADMINS = [123456789]

# Data files
USERS_FILE = "users.json"
MATCHES_FILE = "matches.json"

# Load/Save helpers
def load_json(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

users = load_json(USERS_FILE)
matches = load_json(MATCHES_FILE)

def save_all():
    save_json(USERS_FILE, users)
    save_json(MATCHES_FILE, matches)

# Utils
def get_user(uid):
    if str(uid) not in users:
        users[str(uid)] = {"coins": 100, "wins": 0, "last_daily": 0}
    return users[str(uid)]

def update_message(update, text, buttons=None):
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    return update.callback_query.message.edit_text(text, reply_markup=markup)

def get_buttons():
    return [[InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 4)],
            [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(4, 7)]]

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    get_user(uid)
    save_all()
    await update.message.reply_text(
        "Welcome to Hand Cricket Bot!\n\nCommands:\n"
        "/pm <bet> - Start PvP match\n"
        "/profile - View stats\n"
        "/daily - Claim daily coins\n"
        "/leaderboard - View top players\n"
        "/help - Command list\n"
    )

# /profile
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    await update.message.reply_text(
        f"Coins: ₹{u['coins']}\nWins: {u['wins']}"
    )

# /daily
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    now = int(time.time())
    if now - u['last_daily'] >= 86400:
        u['coins'] += 250
        u['last_daily'] = now
        save_all()
        await update.message.reply_text("You claimed ₹250 daily coins!")
    else:
        wait = 86400 - (now - u['last_daily'])
        await update.message.reply_text(f"Wait {wait//3600}h {(wait%3600)//60}m more.")

# /leaderboard
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(users.items(), key=lambda x: x[1]["coins"], reverse=True)[:10]
    msg = "Top Players (by coins):\n"
    for i, (uid, u) in enumerate(top, 1):
        name = (await context.bot.get_chat(uid)).first_name
        msg += f"{i}. {name}: ₹{u['coins']}\n"
    await update.message.reply_text(msg)

# /add for admin
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return await update.message.reply_text("Not allowed.")
    if len(context.args) != 2:
        return await update.message.reply_text("Usage: /add <user_id> <coins>")
    uid, coins = context.args
    try:
        coins = int(coins)
        get_user(uid)["coins"] += coins
        save_all()
        await update.message.reply_text(f"Added ₹{coins} to {uid}.")
    except:
        await update.message.reply_text("Error in input.")

# /help
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/pm <bet> - Start PvP match\n"
        "/profile - View stats\n"
        "/daily - Claim daily coins\n"
        "/leaderboard - View top players\n"
        "/help - Command list\n"
    )

# /pm command to start match
async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    if not context.args:
        return await update.message.reply_text("Usage: /pm <bet>")
    try:
        bet = int(context.args[0])
    except:
        return await update.message.reply_text("Bet must be a number.")
    u = get_user(uid)
    if u["coins"] < bet:
        return await update.message.reply_text("Not enough coins.")

    match_id = str(uid)
    if match_id in matches:
        return await update.message.reply_text("Match already exists.")

    matches[match_id] = {
        "bet": bet,
        "p1": uid,
        "p2": None,
        "turn": None,
        "innings": 1,
        "score": {uid: 0},
        "chosen": {},
        "target": None
    }
    save_all()
    join_btn = InlineKeyboardMarkup([[InlineKeyboardButton("Join Match", callback_data=f"join_{uid}")]])
    await update.message.reply_text(
        f"{name} has started a match with ₹{bet} coins!\nClick below to join.",
        reply_markup=join_btn
    )
# Part 2: game.py (continue from main.py)

async def handle_join(update: Update, context: ContextTypes.DEFAULT_TYPE, host_id: str):
    host = matches.get(host_id)
    if not host:
        return await update.callback_query.answer("Match not found", show_alert=True)

    uid = update.effective_user.id
    if str(uid) == host_id:
        return await update.callback_query.answer("You can't join your own match.", show_alert=True)

    if host["p2"]:
        return await update.callback_query.answer("Already joined.", show_alert=True)

    host["p2"] = uid
    matches[host_id]["turn"] = "toss"
    save_all()
    toss_msg = f"{context.bot_data.get('msg_id', '')}TOSS TIME!\n\n" \
               f"{context.bot.get_chat(host['p1']).result().first_name} vs {context.bot.get_chat(uid).result().first_name}\n\n" \
               f"{context.bot.get_chat(host['p1']).result().first_name}, choose Odd or Even"
    buttons = [
        [InlineKeyboardButton("Odd", callback_data=f"toss_odd")],
        [InlineKeyboardButton("Even", callback_data=f"toss_even")]
    ]
    await update_message(update, toss_msg, buttons)

async def handle_toss(update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
    uid = update.effective_user.id
    for mid, m in matches.items():
        if m.get("turn") == "toss" and uid == m["p1"]:
            m["toss_choice"] = choice
            m["turn"] = "toss_num"
            m["chosen"] = {}
            save_all()
            return await update_message(update,
                f"You chose {choice.upper()}. Now both players choose a number.",
                get_buttons()
            )
    await update.callback_query.answer("Invalid toss", show_alert=True)

async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE, num: str):
    uid = update.effective_user.id
    for mid, m in matches.items():
        if uid in [m["p1"], m["p2"]]:
            chosen = m["chosen"]
            chosen[str(uid)] = int(num)

            if m["turn"] == "toss_num":
                if len(chosen) < 2:
                    return await update_message(update,
                        f"{context.bot.get_chat(uid).result().first_name} chose a number.\nWaiting for other player...",
                        get_buttons()
                    )
                total = sum(chosen.values())
                odd_even = "odd" if total % 2 else "even"
                if odd_even == m["toss_choice"]:
                    m["batting"] = m["p1"]
                else:
                    m["batting"] = m["p2"]
                m["bowling"] = m["p2"] if m["batting"] == m["p1"] else m["p1"]
                m["turn"] = "play"
                m["chosen"] = {}
                save_all()
                return await update_message(update,
                    f"TOSS RESULT: Total = {total} ({odd_even.upper()})\n"
                    f"{context.bot.get_chat(m['batting']).result().first_name} will bat first.\n\n"
                    f"Let the game begin!\n"
                    f"{context.bot.get_chat(m['batting']).result().first_name} is batting.\n"
                    f"{context.bot.get_chat(m['bowling']).result().first_name} is bowling.\n"
                    f"Batsman, choose a number.",
                    get_buttons()
                )
            elif m["turn"] == "play":
                if len(chosen) < 2:
                    bname = context.bot.get_chat(m["batting"]).result().first_name
                    bowname = context.bot.get_chat(m["bowling"]).result().first_name
                    if str(uid) == str(m["batting"]):
                        return await update_message(update,
                            f"{bname} chose a number.\nNow it's {bowname}'s turn.",
                            get_buttons()
                        )
                    else:
                        return await update_message(update,
                            f"{bowname} chose a number.\nWaiting for {bname}'s choice.",
                            get_buttons()
                        )

                bat = m["batting"]
                bowl = m["bowling"]
                bat_name = context.bot.get_chat(bat).result().first_name
                bowl_name = context.bot.get_chat(bowl).result().first_name
                bat_num = m["chosen"][str(bat)]
                bowl_num = m["chosen"][str(bowl)]
                msg = f"{bat_name} chose {bat_num}, {bowl_name} chose {bowl_num}.\n"

                if bat_num == bowl_num:
                    msg += f"WICKET!\n{bat_name} is out.\n"
                    if m["innings"] == 1:
                        m["target"] = m["score"][bat] + 1
                        m["innings"] = 2
                        m["batting"], m["bowling"] = m["bowling"], m["batting"]
                        m["score"][m["batting"]] = 0
                        msg += f"Second Innings begins!\nTarget: {m['target']}\n"
                    else:
                        p1s = m["score"][m["p1"]]
                        p2s = m["score"][m["p2"]]
                        winner = m["p1"] if p1s > p2s else m["p2"] if p2s > p1s else None
                        if winner:
                            win_name = context.bot.get_chat(winner).result().first_name
                            msg += f"{win_name} wins!"
                            users[str(winner)]["coins"] += 2 * m["bet"]
                            users[str(winner)]["wins"] += 1
                        else:
                            msg += "It's a tie!"
                        del matches[mid]
                        save_all()
                        return await update_message(update, msg)

                else:
                    m["score"][bat] += bat_num
                    msg += f"{bat_name} continues! Score: {m['score'][bat]}\n"
                    if m["innings"] == 2 and m["score"][bat] >= m["target"]:
                        msg += f"{bat_name} reached the target!\n{bat_name} wins!"
                        users[str(bat)]["coins"] += 2 * m["bet"]
                        users[str(bat)]["wins"] += 1
                        del matches[mid]
                        save_all()
                        return await update_message(update, msg)

                m["chosen"] = {}
                save_all()
                return await update_message(update, msg, get_buttons())

# Callback handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data.startswith("join_"):
        await handle_join(update, context, data.split("_")[1])
    elif data.startswith("toss_"):
        await handle_toss(update, context, data.split("_")[1])
    elif data in ['1', '2', '3', '4', '5', '6']:
        await handle_number(update, context, data)

# Bot runner
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pm", pm))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

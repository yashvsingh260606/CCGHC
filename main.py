import json
import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from datetime import datetime, timedelta

TOKEN = '8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo'
DATA_FILE = 'users.json'
MATCHES_FILE = 'matches.json'
ADMINS = [123456789]  # Replace with your Telegram ID

logging.basicConfig(level=logging.INFO)

def load_data(file):
    return json.load(open(file)) if os.path.exists(file) else {}

def save_data(file, data):
    json.dump(data, open(file, 'w'), indent=2)

users = load_data(DATA_FILE)
matches = load_data(MATCHES_FILE)

def get_user(uid):
    if str(uid) not in users:
        users[str(uid)] = {"coins": 0, "wins": 0, "last_daily": "2000-01-01"}
    return users[str(uid)]

def save_all():
    save_data(DATA_FILE, users)
    save_data(MATCHES_FILE, matches)

def format_coins(c): return f"{c:,} coins"

def make_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)]
    ])

def help_text():
    return (
        "**Hand Cricket Bot Commands:**\n"
        "/start - Start & show help\n"
        "/register - Claim starting coins\n"
        "/pm <bet> - Start or join match\n"
        "/profile - Your coins & wins\n"
        "/leaderboard - Top players\n"
        "/daily - Get daily coins\n"
        "/add <uid> <coins> - (Admin) Add coins\n"
        "/help - Show commands"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to **Hand Cricket Bot!**\n" + help_text(), parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text(), parse_mode='Markdown')

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if user['coins'] == 0:
        user['coins'] += 1000
        await update.message.reply_text(f"Registered! You received 1,000 coins.")
        save_all()
    else:
        await update.message.reply_text("You're already registered!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    u = get_user(uid)
    await update.message.reply_text(
        f"**Your Profile**\nCoins: {format_coins(u['coins'])}\nWins: {u['wins']}",
        parse_mode='Markdown'
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(users.items(), key=lambda x: x[1]['coins'], reverse=True)[:10]
    msg = "**Top Players by Coins:**\n"
    for i, (uid, data) in enumerate(top, 1):
        name = await context.bot.get_chat(uid)
        msg += f"{i}. {name.first_name}: {format_coins(data['coins'])}, Wins: {data['wins']}\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    now = datetime.utcnow().date()
    last = datetime.strptime(user["last_daily"], "%Y-%m-%d").date()
    if now > last:
        user['coins'] += 500
        user['last_daily'] = now.isoformat()
        await update.message.reply_text("Daily reward claimed! +500 coins.")
        save_all()
    else:
        await update.message.reply_text("You've already claimed today's reward!")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return await update.message.reply_text("Only admins can use this.")
    try:
        uid, amt = context.args
        amt = int(amt)
        get_user(uid)['coins'] += amt
        save_all()
        await update.message.reply_text(f"Gave {amt} coins to {uid}")
    except:
        await update.message.reply_text("Usage: /add <user_id> <amount>")
async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    bet = int(context.args[0]) if context.args else 0
    if bet > user['coins']:
        return await update.message.reply_text("You don’t have enough coins.")
    match_id = f"{uid}_{random.randint(1000,9999)}"
    matches[match_id] = {
        "players": [uid],
        "bet": bet,
        "state": "waiting"
    }
    save_all()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join", callback_data=f"join_{match_id}")]])
    await update.message.reply_text(
        f"{update.effective_user.first_name} started a match.\nBet: {format_coins(bet)}\nClick to join!",
        reply_markup=keyboard
    )

async def join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = query.data.split("_")[1]
    match = matches.get(match_id)
    if not match or len(match['players']) > 1:
        return await query.edit_message_text("Match no longer available.")
    uid = str(query.from_user.id)
    if uid in match['players']:
        return
    p1, p2 = match['players'][0], uid
    get_user(p1); get_user(p2)
    if match['bet'] > users[p2]['coins']:
        return await query.edit_message_text("You don’t have enough coins to join.")
    match['players'].append(uid)
    match['turn'] = 'toss'
    match['msg_id'] = query.message.message_id
    match['chat_id'] = query.message.chat_id
    match['score'] = {p1: 0, p2: 0}
    match['wicket'] = {p1: 0, p2: 0}
    match['inputs'] = {}
    match['innings'] = 1
    match['batting'] = p1
    match['bowling'] = p2
    save_all()
    await query.edit_message_text("Toss Time! Choose Heads or Tails:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Heads", callback_data=f"toss_H_{match_id}"),
             InlineKeyboardButton("Tails", callback_data=f"toss_T_{match_id}")]
        ])
    )

async def toss_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice, match_id = query.data.split("_")[1:]
    match = matches.get(match_id)
    if not match or match['turn'] != 'toss':
        return
    player = str(query.from_user.id)
    toss_result = random.choice(['H', 'T'])
    win = player == match['players'][0] and choice == toss_result
    match['batting'], match['bowling'] = (player, match['players'][1]) if win else (match['players'][1], player)
    match['turn'] = 'input'
    match['inputs'] = {}
    save_all()
    await query.edit_message_text(
        f"Toss result: {'Heads' if toss_result=='H' else 'Tails'}\n"
        f"{'You won the toss!' if win else 'Opponent won the toss!'}\n\n"
        f"{context.bot.get_chat(match['batting']).first_name} will bat first.",
        reply_markup=make_keyboard()
    )

async def number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    num = int(query.data.split("_")[1])
    for m_id, m in matches.items():
        if m.get('turn') == 'input' and uid in m['players']:
            m['inputs'][uid] = num
            if len(m['inputs']) < 2:
                other = m['players'][0] if m['players'][1] == uid else m['players'][1]
                await query.edit_message_text(f"{query.from_user.first_name} chose a number.\nNow it's {context.bot.get_chat(other).first_name}'s turn.",
                    reply_markup=make_keyboard())
            else:
                bat, bowl = m['batting'], m['bowling']
                bnum, pnum = m['inputs'][bat], m['inputs'][bowl]
                if bnum == pnum:
                    m['wicket'][bat] += 1
                    out_text = f"WICKET! {context.bot.get_chat(bat).first_name} is out!"
                    if m['innings'] == 2:
                        winner = bat if m['score'][bat] > m['score'][bowl] else bowl
                        users[winner]['wins'] += 1
                        users[winner]['coins'] += m['bet'] * 2
                        save_all()
                        await query.edit_message_text(
                            f"{out_text}\n\n"
                            f"Final Scores:\n"
                            f"{context.bot.get_chat(bat).first_name}: {m['score'][bat]}\n"
                            f"{context.bot.get_chat(bowl).first_name}: {m['score'][bowl]}\n"
                            f"{context.bot.get_chat(winner).first_name} wins the match!"
                        )
                        matches.pop(m_id)
                        return
                    else:
                        m['innings'] = 2
                        m['batting'], m['bowling'] = m['bowling'], m['batting']
                        m['inputs'] = {}
                        m['turn'] = 'input'
                        await query.edit_message_text(f"{out_text}\nNow it's {context.bot.get_chat(m['batting']).first_name}'s turn to bat.",
                            reply_markup=make_keyboard())
                else:
                    m['score'][bat] += bnum
                    m['inputs'] = {}
                    await query.edit_message_text(
                        f"{context.bot.get_chat(bat).first_name} chose {bnum}.\n"
                        f"{context.bot.get_chat(bowl).first_name} chose {pnum}.\n"
                        f"Total: {m['score'][bat]} | Wickets: {m['wicket'][bat]}\n"
                        f"{context.bot.get_chat(bat).first_name} continues to bat.",
                        reply_markup=make_keyboard()
                    )
            save_all()
            return

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("register", register))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("leaderboard", leaderboard))
app.add_handler(CommandHandler("daily", daily))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("pm", pm))
app.add_handler(CallbackQueryHandler(join_match, pattern="^join_"))
app.add_handler(CallbackQueryHandler(toss_choice, pattern="^toss_"))
app.add_handler(CallbackQueryHandler(number_input, pattern="^num_"))

if __name__ == "__main__":
    print("Bot running...")
    app.run_polling()

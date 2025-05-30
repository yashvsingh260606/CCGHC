
import logging
import random
from datetime import datetime, timedelta

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
    filters,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_NAME = "CCG HandCricket"
COINS_EMOJI = "🪙"
ADMIN_IDS = {7361215114}  # Замените на ваши Telegram ID админов

USERS = {}  # user_id: {name, coins, wins, losses, registered, last_daily}
MATCHES = {}  # chat_id: match_data
LEADERBOARD_PAGE = {}  # user_id: 0 or 1 (coins/wins page)

# --- Вспомогательные функции ---


def get_username(user):
    return user.first_name or user.username or "Player"


def ensure_user(user):
    if user.id not in USERS:
        USERS[user.id] = {
            "name": get_username(user),
            "coins": 0,
            "wins": 0,
            "losses": 0,
            "registered": False,
            "last_daily": None,
        }


def profile_text(user_id):
    u = USERS[user_id]
    return (
        f"{u['name']}'s Profile -\n\n"
        f"Name : {u['name']}\n"
        f"ID : {user_id}\n"
        f"Purse : {u['coins']}{COINS_EMOJI}\n\n"
        f"Performance History :\n"
        f"Wins : {u['wins']}\n"
        f"Loss : {u['losses']}\n"
    )


def number_buttons():
    # Кнопки с числами 1-3 и 4-6 (2 ряда)
    buttons = [
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(1, 4)],
        [InlineKeyboardButton(str(i), callback_data=f"num_{i}") for i in range(4, 7)],
    ]
    return InlineKeyboardMarkup(buttons)


def join_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Join", callback_data="join_match")]])


def bat_bowl_buttons():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Bat 🏏", callback_data="choose_bat"),
                InlineKeyboardButton("Bowl ⚾", callback_data="choose_bowl"),
            ]
        ]
    )


def leaderboard_buttons(page):
    if page == 0:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("➡️ Wins Leaderboard", callback_data="leaderboard_right")]]
        )
    else:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Coins Leaderboard", callback_data="leaderboard_left")]]
        )


# --- Команды бота ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    await update.message.reply_text(
        f"Welcome to {BOT_NAME}, {USERS[user.id]['name']}! Use /register to get 4000 {COINS_EMOJI}."
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    u = USERS[user.id]
    if u["registered"]:
        await update.message.reply_text("You have already registered and got your reward.")
        return
    u["coins"] += 4000
    u["registered"] = True
    await update.message.reply_text(f"Registered! You received 4000 {COINS_EMOJI}.")


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    text = profile_text(user.id)
    await update.message.reply_text(text)


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    now = datetime.utcnow()
    last = USERS[user.id]["last_daily"]
    if last and (now - last) < timedelta(hours=24):
        rem = timedelta(hours=24) - (now - last)
        h, m = divmod(rem.seconds // 60, 60)
        await update.message.reply_text(f"Daily already claimed. Try again in {h}h {m}m.")
        return
    USERS[user.id]["coins"] += 2000
    USERS[user.id]["last_daily"] = now
    await update.message.reply_text(f"You received 2000 {COINS_EMOJI} as daily reward!")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - Welcome message\n"
        "/register - Register and get 4000 🪙\n"
        "/pm [bet] - Start a match; optional bet amount\n"
        "/profile - Show your profile\n"
        "/daily - Get daily 2000 🪙 reward\n"
        "/leaderboard - Show top 10 richest players\n"
    )
    await update.message.reply_text(text)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    LEADERBOARD_PAGE[user.id] = 0
    text = leaderboard_text(0)
    markup = leaderboard_buttons(0)
    await update.message.reply_text(text, reply_markup=markup)


def leaderboard_text(page):
    top = 10
    if page == 0:
        sorted_users = sorted(USERS.values(), key=lambda x: x["coins"], reverse=True)
        text = "🏆 Top 10 Richest Players by Coins:\n\n"
        for i, u in enumerate(sorted_users[:top], 1):
            text += f"{i}. {u['name']} - {u['coins']}{COINS_EMOJI}\n"
    else:
        sorted_users = sorted(USERS.values(), key=lambda x: x["wins"], reverse=True)
        text = "🏆 Top 10 Players by Wins:\n\n"
        for i, u in enumerate(sorted_users[:top], 1):
            text += f"{i}. {u['name']} - {u['wins']} Wins\n"
    return text


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
    text = leaderboard_text(page)
    markup = leaderboard_buttons(page)
    await query.edit_message_text(text=text, reply_markup=markup)


async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return
    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        await update.message.reply_text("Please provide valid user_id and amount.")
        return
    if target_id not in USERS:
        await update.message.reply_text("User not found.")
        return
    USERS[target_id]["coins"] += amount
    await update.message.reply_text(
        f"Added {amount}{COINS_EMOJI} to {USERS[target_id]['name']}."
    )


# --- Логика матча ---


async def pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    ensure_user(user)

    if chat_id in MATCHES:
        await update.message.reply_text("A match is already ongoing here. Wait it to finish.")
        return

    bet = 0
    if context.args:
        try:
            bet = int(context.args[0])
            if bet < 0:
                raise ValueError()
        except Exception:
            await update.message.reply_text("Invalid bet amount. Enter a positive number.")
            return

    if bet > 0 and USERS[user.id]["coins"] < bet:
        await update.message.reply_text(f"You don't have enough coins to bet {bet}{COINS_EMOJI}.")
        return

    # Создаем матч
    MATCHES[chat_id] = {
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
        "turn": None,
        "innings": 0,
        "target": None,
        "superball": False,
    }

    text = (
        f"🏏 Cricket game has been started!\n"
        f"Press Join below to play with {USERS[user.id]['name']}."
    )
    sent_message = await update.message.reply_text(text, reply_markup=join_button())
    MATCHES[chat_id]["message_id"] = sent_message.message_id


async def join_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    chat_id = query.message.chat_id

    if chat_id not in MATCHES:
        await query.answer("No active match.", show_alert=True)
        return

    match = MATCHES[chat_id]

    if match["state"] != "waiting_join":
        await query.answer("Match already started.", show_alert=True)
        return

    if user.id == match["inviter"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return

    ensure_user(user)
    bet = match["bet"]
    if bet > 0 and USERS[user.id]["coins"] < bet:
        await query.answer(f"You don't have enough coins to join this bet ({bet}{COINS_EMOJI}).", show_alert=True)
        return

    # Добавляем второго игрока
    match["players"].append(user.id)
    match["scores"][user.id] = 0

    # Снимаем ставки
    if bet > 0:
        USERS[match["inviter"]]["coins"] -= bet
        USERS[user.id]["coins"] -= bet

    match["state"] = "toss"
    match["message_id"] = query.message.message_id

    await query.answer("You joined the match! Starting toss...")
    await start_toss(update, context, match, query.message)


async def start_toss(update, context, match, message):
    inviter_name = USERS[match["inviter"]]["name"]
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Heads", callback_data="toss_heads"),
                InlineKeyboardButton("Tails", callback_data="toss_tails"),
            ]
        ]
    )
    text = f"Coin toss time!\n{inviter_name}, choose Heads or Tails to win the toss."
    await message.edit_text(text, reply_markup=keyboard)


async def toss_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    chat_id = query.message.chat_id

    if chat_id not in MATCHES:
        await query.answer("No active match.", show_alert=True)
        return

    match = MATCHES[chat_id]

    if match["state"] != "toss":
        await query.answer("Not in toss phase.", show_alert=True)
        return

    if user.id != match["inviter"]:
        await query.answer("Only the match inviter can choose toss.", show_alert=True)
        return

    choice = query.data.split("_")[1]
    coin_flip = random.choice(["heads", "tails"])

    if choice == coin_flip:
        toss_winner = match["inviter"]
        toss_loser = [p for p in match["players"] if p != toss_winner][0]
    else:
        toss_winner = [p for p in match["players"] if p != match["inviter"]][0]
        toss_loser = match["inviter"]

    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "bat_bowl"

    text = f"{USERS[toss_winner]['name']} won the toss!\n\n{USERS[toss_winner]['name']}, choose to Bat or Bowl first."
    await query.message.edit_text(text, reply_markup=bat_bowl_buttons())
    await query.answer()


async def bat_bowl_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    chat_id = query.message.chat_id

    if chat_id not in MATCHES:
        await query.answer("No active match.", show_alert=True)
        return

    match = MATCHES[chat_id]

    if match["state"] != "bat_bowl":
        await query.answer("Not in Bat/Bowl choice phase.", show_alert=True)
        return

    if user.id != match["toss_winner"]:
        await query.answer("Only toss winner can choose.", show_alert=True)
        return

    choice = query.data.split("_")[1]
    batting_first = choice == "bat"
    match["batting_first"] = batting_first

    if batting_first:
        match["batting_player"] = match["toss_winner"]
        match["bowling_player"] = match["toss_loser"]
    else:
        match["batting_player"] = match["toss_loser"]
        match["bowling_player"] = match["toss_winner"]

    match["state"] = "batting"
    match["over"] = 0.0
    match["wickets"] = 0
    match["batsman_choice"] = None
    match["bowler_choice"] = None
    match["turn"] = "batsman"
    match["innings"] = 1
    match["target"] = None
    match["superball"] = False

    text = (
        f"Match started!\n\n"
        f"Over: {match['over']:.1f}\n"
        f"🏏 Batter: {USERS[match['batting_player']]['name']}\n"
        f"⚾ Bowler: {USERS[match['bowling_player']]['name']}\n\n"
        f"{USERS[match['batting_player']]['name']}, choose your number to bat."
    )
    await query.message.edit_text(text, reply_markup=number_buttons())
    await query.answer()


async def number_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    chat_id = query.message.chat_id
    data = query.data

    if chat_id not in MATCHES:
        await query.answer("No active match.", show_alert=True)
        return

    match = MATCHES[chat_id]

    if match["state"] != "batting":
        await query.answer("Match not in batting phase.", show_alert=True)
        return

    if user.id not in match["players"]:
        await query.answer("You are not part of this match.", show_alert=True)
        return

    try:
        number = int(data.split("_")[1])
    except:
        await query.answer("Invalid number.", show_alert=True)
        return

    if number < 1 or number > 6:
        await query.answer("Choose a number between 1 and 6.", show_alert=True)
        return

    # Ход бэтсмена
    if match["turn"] == "batsman":
        if user.id != match["batting_player"]:
            await query.answer("It's batsman's turn.", show_alert=True)
            return
        if match["batsman_choice"] is not None:
            await query.answer("You already chose your number.", show_alert=True)
            return
        match["batsman_choice"] = number
        match["turn"] = "bowler"
        await query.answer("Batsman has chosen a number.")
        await query.message.edit_text(
            f"{USERS[match['batting_player']]['name']} chose the number.\n"
            f"Now {USERS[match['bowling_player']]['name']}, choose your bowling number.",
            reply_markup=number_buttons(),
        )
        return

    # Ход боулера
    if match["turn"] == "bowler":
        if user.id != match["bowling_player"]:
            await query.answer("It's bowler's turn.", show_alert=True)
            return
        if match["bowler_choice"] is not None:
            await query.answer("You already chose your number.", show_alert=True)
            return
        match["bowler_choice"] = number

        batsman = match["batting_player"]
        bowler = match["bowling_player"]
        b_choice = match["batsman_choice"]
        bw_choice = match["bowler_choice"]

        over = match["over"]
        wickets = match["wickets"]
        scores = match["scores"]

        # Обновляем овер
        # Добавляем 0.1 к оверу - 6 мячей в овер (0.6)
        decimal = round((over * 10) % 10)
        if decimal < 5:
            match["over"] += 0.1
        else:
            match["over"] = round(over) + 1.0

        text = (
            f"Over : {match['over']:.1f}\n\n"
            f"🏏 Batter : {USERS[batsman]['name']}\n"
            f"⚾ Bowler : {USERS[bowler]['name']}\n\n"
            f"{USERS[batsman]['name']} Bat {b_choice}\n"
            f"{USERS[bowler]['name']} Bowl {bw_choice}\n\n"
        )

        if b_choice == bw_choice:
            # Вылет
            match["wickets"] += 1
            text += f"Wicket! {USERS[batsman]['name']} is OUT!\n"
            if match["wickets"] >= 1:
                # Ваша логика: 1 wicket - innings over
                if match["innings"] == 1:
                    # Первый иннинг окончен
                    match["target"] = scores[batsman] + 1
                    match["innings"] = 2
                    match["wickets"] = 0
                    match["over"] = 0.0
                    # Меняем роли
                    match["batting_player"], match["bowling_player"] = (
                        match["bowling_player"],
                        match["batting_player"],
                    )
                    match["batsman_choice"] = None
                    match["bowler_choice"] = None
                    match["turn"] = "batsman"
                    match["state"] = "batting"

                    text += (
                        f"Over : {match['over']:.1f}\n\n"
                        f"🏏 Batter : {USERS[match['batting_player']]['name']}\n"
                        f"⚾ Bowler : {USERS[match['bowling_player']]['name']}\n\n"
                        f"Target : {match['target']}\n\n"
                        f"{USERS[match['batting_player']]['name']}, choose your number to bat."
                    )
                    await query.message.edit_text(text, reply_markup=number_buttons())
                    await query.answer()
                    return
                else:
                    # Второй иннинг окончен - матч завершён
                    await finish_match(update, context, match, text)
                    return
            else:
                # Продолжаем иннинг
                match["batsman_choice"] = None
                match["bowler_choice"] = None
                match["turn"] = "batsman"
                text += f"\n{USERS[batsman]['name']} выберите число для удара."
                await query.message.edit_text(text, reply_markup=number_buttons())
                await query.answer()
                return
        else:
            # Добавляем очки
            scores[batsman] += b_choice
            text += f"Total Score :\n{USERS[batsman]['name']} scored total of {scores[batsman]} Runs\n\n"

            # Проверяем цель во втором иннинге
            if match["innings"] == 2 and scores[batsman] >= match["target"]:
                text += f"Target achieved! {USERS[batsman]['name']} wins!\n"
                await finish_match(update, context, match, text)
                return

            match["batsman_choice"] = None
            match["bowler_choice"] = None
            match["turn"] = "batsman"

            text += f"Next Move :\n{USERS[batsman]['name']} Continue your Bat!"
            await query.message.edit_text(text, reply_markup=number_buttons())
            await query.answer()
            return


async def finish_match(update, context, match, text):
    chat_id = update.effective_chat.id
    scores = match["scores"]
    players = match["players"]
    bet = match["bet"]

    # Определяем победителя
    p1_score = scores[players[0]]
    p2_score = scores[players[1]]

    if p1_score > p2_score:
        winner = players[0]
        loser = players[1]
    elif p2_score > p1_score:
        winner = players[1]
        loser = players[0]
    else:
        # Ничья -> супербол
        match["state"] = "superball"
        match["superball"] = True
        match["batsman_choice"] = None
        match["bowler_choice"] = None
        match["turn"] = "batsman"
        text += "\nMatch tied! Starting Superball - one ball to decide winner.\n"
        text += f"{USERS[match['batting_player']]['name']} bat first, choose your number."
        await update.message.reply_text(text, reply_markup=number_buttons())
        return

    USERS[winner]["wins"] += 1
    USERS[loser]["losses"] += 1

    if bet > 0:
        USERS[winner]["coins"] += bet * 2

    text += f"\n\nMatch Over!\nWinner: {USERS[winner]['name']} 🏆"
    await update.callback_query.message.edit_text(text)

    if chat_id in MATCHES:
        del MATCHES[chat_id]


# --- Основная функция ---


def main():
    TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Замените на токен вашего бота

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("pm", pm_command))

    app.add_handler(CallbackQueryHandler(join_match_callback, pattern="^join_match$"))
    app.add_handler(CallbackQueryHandler(toss_choice_callback, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(bat_bowl_choice_callback, pattern="^choose_"))
    app.add_handler(CallbackQueryHandler(number_choice_callback, pattern="^num_"))
    app.add_handler(CallbackQueryHandler(leaderboard_pagination, pattern="^leaderboard_"))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
    

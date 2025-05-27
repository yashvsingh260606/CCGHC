import random
import json
import os
from datetime import datetime
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

DATA_FILE = "players_data.json"
matches = {}  # ongoing matches by chat_id
admins = [123456789]  # Replace with your Telegram user IDs


def load_data():
    if not os.path.isfile(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_today_date():
    return datetime.utcnow().date().isoformat()


def register_user(user):
    data = load_data()
    user_id = str(user.id)
    if user_id not in data:
        data[user_id] = {
            "id": user.id,
            "name": user.full_name,
            "coins": 1000,
            "registered_on": get_today_date(),
            "last_daily": None,
        }
        save_data(data)
    return data[user_id]


def update_coins(user_id, amount):
    data = load_data()
    uid = str(user_id)
    if uid in data:
        data[uid]["coins"] = data[uid].get("coins", 0) + amount
        save_data(data)
        return data[uid]["coins"]
    return None


def get_coins(user_id):
    data = load_data()
    uid = str(user_id)
    if uid in data:
        return data[uid].get("coins", 0)
    return 0


def can_claim_daily(user_id):
    data = load_data()
    uid = str(user_id)
    today = get_today_date()
    if uid in data:
        last = data[uid].get("last_daily")
        return last != today
    return True


def update_daily_claim(user_id):
    data = load_data()
    uid = str(user_id)
    today = get_today_date()
    if uid in data:
        data[uid]["last_daily"] = today
        save_data(data)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    text = (
        f"Welcome, {user.full_name}!\n"
        "This is the Hand Cricket PvP Bot.\n\n"
        "Commands:\n"
        "/register - Register yourself\n"
        "/profile - Show your profile\n"
        "/daily - Claim daily coins\n"
        "/start_pvp - Start a new match\n"
        "/leaderboard - Show top players\n"
        "Have fun!"
    )
    await update.message.reply_text(text)


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = register_user(user)
    await update.message.reply_text(
        f"Registered successfully!\n\nName: {user_data['name']}\nCoins: {user_data['coins']}"
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    if uid not in data:
        await update.message.reply_text(
            "You are not registered yet. Use /register to register."
        )
        return
    user_data = data[uid]
    text = (
        f"**Profile of {user_data['name']}**\n"
        f"ID: __{user_data['id']}__\n"
        f"Coins: **{user_data['coins']}**\n"
        f"Registered On: {user_data['registered_on']}\n"
        f"Last Daily Claim: {user_data['last_daily'] or 'Never'}"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    if not can_claim_daily(uid):
        await update.message.reply_text(
            "You have already claimed your daily coins today. Come back tomorrow!"
        )
        return
    coins_to_add = 500
    update_coins(uid, coins_to_add)
    update_daily_claim(uid)
    await update.message.reply_text(f"You claimed your daily {coins_to_add} coins!")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.message.reply_text("No data available for leaderboard.")
        return
    sorted_users = sorted(data.values(), key=lambda x: x.get("coins", 0), reverse=True)[
        :10
    ]
    text = "**Leaderboard - Top 10 Players by Coins:**\n"
    for i, user in enumerate(sorted_users, start=1):
        text += f"{i}. {user['name']} - **{user.get('coins', 0)}** coins\n"
    await update.message.reply_text(text, parse_mode="MarkdownV2")


async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in admins:
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
        await update.message.reply_text("User ID and amount must be integers.")
        return
    new_balance = update_coins(target_id, amount)
    if new_balance is None:
        await update.message.reply_text("User not found.")
    else:
        await update.message.reply_text(
            f"Added {amount} coins to user {target_id}. New balance: {new_balance}"
        )


async def start_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in matches:
        await update.message.reply_text(
            "A match is already ongoing in this chat. Please wait for it to finish."
        )
        return

    user = update.effective_user
    # Register player in match
    matches[chat_id] = {
        "players": [user],
        "state": "waiting_for_opponent",
    }
    await update.message.reply_text(
        f"{user.first_name} started a new match! Another player can join using /join_pvp."
    )


async def join_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    match = matches.get(chat_id)
    if not match:
        await update.message.reply_text("No match to join. Start one with /start_pvp.")
        return

    if len(match["players"]) >= 2:
        await update.message.reply_text("Match already has 2 players.")
        return

    if user.id == match["players"][0].id:
        await update.message.reply_text("You cannot join your own match.")
        return

    match["players"].append(user)
    match["state"] = "toss"
    await update.message.reply_text(
        f"{user.first_name} joined the match!\n"
        f"{match['players'][0].first_name}, you won the toss! Choose heads or tails:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Heads", callback_data="toss_heads"),
                    InlineKeyboardButton("Tails", callback_data="toss_tails"),
                ]
            ]
        ),
    )


async def handle_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "toss":
        await query.answer("No toss in progress.")
        return

    user = query.from_user
    if user.id != match["players"][0].id:
        await query.answer("Only the first player can choose toss side.")
        return

    choice = query.data.split("_")[1]  # 'heads' or 'tails'
    toss_result = random.choice(["heads", "tails"])
    match["toss_choice"] = choice
    match["toss_result"] = toss_result

    if choice == toss_result:
        match["toss_winner"] = match["players"][0]
        match["toss_loser"] = match["players"][1]
    else:
        match["toss_winner"] = match["players"][1]
        match["toss_loser"] = match["players"][0]

    match["state"] = "choose_play"

    await query.edit_message_text(
        f"Toss result: {toss_result.capitalize()}!\n"
        f"{match['toss_winner'].first_name} won the toss! Choose to Bat or Bowl:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Bat", callback_data="choose_bat"),
                    InlineKeyboardButton("Bowl", callback_data="choose_bowl"),
                ]
            ]
        ),
    )


# Add handler registrations here

def main():
    app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CommandHandler("join_pvp", join_pvp))

    app.add_handler(CallbackQueryHandler(handle_toss, pattern="^toss_"))
    # CallbackQueryHandlers for choose_play, shot selection will go here in Part 2

    app.run_polling()


if __name__ == "__main__":
    main()
    

# Continuing from Part 1

# Helper function to create buttons 1-6 in two rows
def create_shot_buttons():
    buttons = [
        InlineKeyboardButton("1", callback_data="shot_1"),
        InlineKeyboardButton("2", callback_data="shot_2"),
        InlineKeyboardButton("3", callback_data="shot_3"),
    ]
    buttons2 = [
        InlineKeyboardButton("4", callback_data="shot_4"),
        InlineKeyboardButton("5", callback_data="shot_5"),
        InlineKeyboardButton("6", callback_data="shot_6"),
    ]
    return InlineKeyboardMarkup([buttons, buttons2])


async def handle_choose_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "choose_play":
        await query.answer("No choice to make now.")
        return

    user = query.from_user
    if user.id != match["toss_winner"].id:
        await query.answer("Only toss winner can choose.")
        return

    choice = query.data.split("_")[1]  # bat or bowl

    # Assign batting and bowling players based on choice
    if choice == "bat":
        match["batting"] = match["toss_winner"]
        match["bowling"] = match["toss_loser"]
    else:
        match["batting"] = match["toss_loser"]
        match["bowling"] = match["toss_winner"]

    match["state"] = "batting"
    match["score"] = 0
    match["balls"] = 0
    match["batsman_choice"] = None
    match["bowler_choice"] = None

    await query.edit_message_text(
        f"{match['batting'].first_name} is batting now.\n"
        f"{match['bowling'].first_name} will bowl.\n\n"
        f"{match['batting'].first_name}, choose your shot!",
        reply_markup=create_shot_buttons(),
    )


async def handle_shot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    user = query.from_user
    match = matches.get(chat_id)

    if not match or match["state"] not in ["batting", "bowling"]:
        await query.answer("No active batting now.")
        return

    shot = int(query.data.split("_")[1])

    # Determine whose turn it is: batsman chooses first, then bowler
    if match["batsman_choice"] is None:
        # Must be batsman choosing
        if user.id != match["batting"].id:
            await query.answer("Wait for your turn.")
            return
        match["batsman_choice"] = shot
        await query.edit_message_text(
            f"{match['batting'].first_name} chose a number.\n"
            f"{match['bowling'].first_name}, your turn to bowl!",
            reply_markup=create_shot_buttons(),
        )
    elif match["bowler_choice"] is None:
        # Bowler turn to choose
        if user.id != match["bowling"].id:
            await query.answer("Wait for your turn.")
            return
        match["bowler_choice"] = shot

        # Both choices made, resolve
        batsman_num = match["batsman_choice"]
        bowler_num = match["bowler_choice"]

        # Calculate result
        if batsman_num == bowler_num:
            # OUT
            text = (
                f"Over: {match['balls']//6}.{match['balls']%6 + 1}\n\n"
                f"🏏 Batter: {match['batting'].first_name}\n"
                f"⚾ Bowler: {match['bowling'].first_name}\n\n"
                f"{match['batting'].first_name} chose {batsman_num}\n"
                f"{match['bowling'].first_name} chose {bowler_num}\n\n"
                f"**OUT!**\n"
                f"Total Score: {match['score']} runs\n\n"
                f"Game Over!"
            )
            match["state"] = "finished"
        else:
            # Runs scored
            match["score"] += batsman_num
            match["balls"] += 1
            text = (
                f"Over: {match['balls']//6}.{match['balls']%6}\n\n"
                f"🏏 Batter: {match['batting'].first_name}\n"
                f"⚾ Bowler: {match['bowling'].first_name}\n\n"
                f"{match['batting'].first_name} chose {batsman_num}\n"
                f"{match['bowling'].first_name} chose {bowler_num}\n\n"
                f"{match['batting'].first_name} scored {batsman_num} runs.\n"
                f"Total Score: {match['score']} runs\n\n"
                f"{match['batting'].first_name}, play your next shot!"
            )
            # Reset choices for next ball
            match["batsman_choice"] = None
            match["bowler_choice"] = None

        await query.edit_message_text(text, parse_mode="Markdown")
        # If not finished, send buttons again
        if match["state"] != "finished":
            await query.message.reply_text(
                f"{match['batting'].first_name}, choose your shot:",
                reply_markup=create_shot_buttons(),
            )
        else:
            # End match cleanup
            del matches[chat_id]


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Reimplemented here in case you want to call anytime
    data = load_data()
    if not data:
        await update.message.reply_text("No data available for leaderboard.")
        return
    sorted_users = sorted(data.values(), key=lambda x: x.get("coins", 0), reverse=True)[:10]
    text = "**Leaderboard - Top 10 Players by Coins:**\n"
    for i, user in enumerate(sorted_users, start=1):
        text += f"{i}. {user['name']} - **{user.get('coins', 0)}** coins\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# Add any other handlers for gameplay here as needed


def main():
    app = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("add", add_coins))
    app.add_handler(CommandHandler("start_pvp", start_pvp))
    app.add_handler(CommandHandler("join_pvp", join_pvp))

    app.add_handler(CallbackQueryHandler(handle_toss, pattern="^toss_"))
    app.add_handler(CallbackQueryHandler(handle_choose_play, pattern="^choose_"))
    app.add_handler(CallbackQueryHandler(handle_shot, pattern="^shot_"))

    app.run_polling()


if __name__ == "__main__":
    main()

# Part 1 of Hand Cricket Bot
# Remember to put your bot token in the BOT_TOKEN variable below

import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
import json
import os
import random

# ----- CONFIG -----
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"

# List of admin user IDs who can add coins
ADMINS = [123456789, 987654321]  # Replace with your admin Telegram user IDs

# File to save registered user data
DATA_FILE = "registered_users.json"


# ----- LOGGING SETUP -----
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# ----- GAME CONSTANTS -----
CHOOSING_BAT = 1
CHOOSING_BOWL = 2
PLAYING = 3

# Button layout: two rows
BUTTONS = [
    [InlineKeyboardButton("1", callback_data="1"),
     InlineKeyboardButton("2", callback_data="2"),
     InlineKeyboardButton("3", callback_data="3")],
    [InlineKeyboardButton("4", callback_data="4"),
     InlineKeyboardButton("5", callback_data="5"),
     InlineKeyboardButton("6", callback_data="6")],
]


# ----- USER DATA HANDLING -----
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_users(users):
    with open(DATA_FILE, "w") as f:
        json.dump(users, f, indent=4)


# ----- COMMANDS -----


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = load_users()
    uid = str(user.id)

    if uid not in users:
        # Register new user with default coins
        users[uid] = {
            "name": user.full_name,
            "coins": 100,  # Starting coins
        }
        save_users(users)
        text = (
            f"Welcome {user.full_name}!\n"
            "You have been registered and credited with 100 coins.\n"
            "Use /help to see all commands."
        )
    else:
        text = (
            f"Welcome back {user.full_name}!\n"
            "Use /help to see all commands."
        )

    # Send message with available commands button (just a "help" hint)
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands_text = (
        "/start - Register or welcome\n"
        "/profile - Show your coins and info\n"
        "/myteam - Show your current team (if implemented)\n"
        "/play - Start a hand cricket match with bot\n"
        "/add - Admin only: Add coins to a user\n"
        "/help - Show this help message\n"
    )
    await update.message.reply_text(commands_text)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users = load_users()
    uid = str(user.id)

    if uid not in users:
        await update.message.reply_text("You are not registered yet. Use /start to register.")
        return

    coins = users[uid]["coins"]
    text = (
        f"User: {user.full_name}\n"
        f"Coins: {coins}"
    )
    await update.message.reply_text(text)


async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMINS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return

    target_id, amount_str = args
    if not amount_str.isdigit():
        await update.message.reply_text("Please enter a valid number for amount.")
        return

    amount = int(amount_str)
    users = load_users()
    if target_id not in users:
        await update.message.reply_text("User ID not found in database.")
        return

    users[target_id]["coins"] += amount
    save_users(users)

    await update.message.reply_text(
        f"Added {amount} coins to user {users[target_id]['name']} (ID: {target_id})."
    )


# ----- GAME FLOW VARIABLES -----
games = {}  # Dict to keep ongoing games indexed by user id


# ----- GAME LOGIC FUNCTIONS -----


def get_initial_message(batsman_name, bowler_name, over=0, ball=0):
    return (
        f"Over : {over}.{ball}\n\n"
        f"🏏 Batter : {batsman_name}\n"
        f"⚾ Bowler : {bowler_name}\n\n"
        "Choose a number to bat (1-6):"
    )


def get_batsman_chosen_text(batsman_name, bowler_name):
    return (
        f"{batsman_name} chose their number.\n"
        f"Now it's {bowler_name}'s turn to bowl.\n"
        "Choose a number (1-6):"
    )


def get_reveal_text(
    over, ball, batsman_name, bowler_name, bat_num, bowl_num, is_out, total_score
):
    text = (
        f"Over : {over}.{ball}\n\n"
        f"🏏 Batter : {batsman_name}\n"
        f"⚾ Bowler : {bowler_name}\n\n"
        f"{batsman_name} Bat {bat_num}\n"
        f"{bowler_name} Bowl {bowl_num}\n\n"
    )

    if is_out:
        text += (
            f"{bowler_name} got {batsman_name} OUT!\n\n"
            f"{bowler_name} Sets a target of {total_score}\n\n"
            f"{batsman_name} will now Bat and {bowler_name} will now Bowl!"
        )
    else:
        text += (
            f"Total Score :\n"
            f"{batsman_name} Scored total of {total_score} Runs\n\n"
            f"Next Move :\n"
            f"{batsman_name} Continue your Bat!"
        )
    return text


# ----- PLAY COMMAND AND CALLBACK HANDLERS -----


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    # Starting a game vs bot (bot is bowler)
    batsman_name = user.full_name
    bowler_name = "BOT"

    games[uid] = {
        "batsman": uid,
        "bowler": "bot",
        "batsman_name": batsman_name,
        "bowler_name": bowler_name,
        "over": 0,
        "ball": 0,
        "total_score": 0,
        "batsman_choice": None,
        "bowler_choice": None,
        "is_batsman_turn": True,
        "message_id": None,
        "chat_id": update.effective_chat.id,
        "state": CHOOSING_BAT,
        "out": False,
    }

    text = get_initial_message(batsman_name, bowler_name)
    # Send the initial message with buttons (batting choices)
    msg = await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(BUTTONS),
    )
    games[uid]["message_id"] = msg.message_id


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    uid = user.id

    if uid not in games:
        await query.edit_message_text(
            "No ongoing game found. Use /play to start a new match."
        )
        return

    game = games[uid]

    chosen_num = int(query.data)

    # Batsman choosing
    if game["state"] == CHOOSING_BAT:
        game["batsman_choice"] = chosen_num
        game["state"] = CHOOSING_BOWL
        # Edit message: batsman chosen, now bowler turn (bot will bowl automatically)
        text = get_batsman_chosen_text(game["batsman_name"], game["bowler_name"])
        # For bot bowling, simulate a choice after short delay
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(BUTTONS),
        )

        # Simulate bot bowling choice
        import random
        bot_bowl = random.randint(1, 6)
        game["bowler_choice"] = bot_bowl

        # Process the ball after short delay (for natural flow)
        await process_ball(update, context, uid)
        return

    # Bowler choosing (if we extend for 2 player later)
    elif game["state"] == CHOOSING_BOWL:
        # For single player vs bot, this won't happen normally
        # But in case, handle it
        game["bowler_choice"] = chosen_num

        await process_ball(update, context, uid)
        return


async def process_ball(update, context, uid):
    import asyncio

    game = games[uid]

    bat = game["batsman_choice"]
    bowl = game["bowler_choice"]

    # Increment ball count
    game["ball"] += 1
    if game["ball"] > 5:
        game["ball"] = 0
        game["over"] += 1

    # Check out condition
    is_out = bat == bowl
    if is_out:
        game["out"] = True
    else:
        game["total_score"] += bat

    # Prepare the text to reveal both choices
    text = get_reveal_text(
        game["over"],
        game["ball"],
        game["batsman_name"],
        game["bowler_name"],
        bat,
        bowl,
        is_out,
        game["total_score"],
    )

    chat_id = game["chat_id"]
    message_id = game["message_id"]

    # Clear choices for next ball or end game
    game["batsman_choice"] = None
    game["bowler_choice"] = None

    # Edit the single game message with updated info
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=None if is_out else InlineKeyboardMarkup(BUTTONS),
    )

    if is_out:
        # End game: Remove game from dict after a pause
        await asyncio.sleep(3)
        del games[uid]
        await context.bot.send_message(chat_id=chat_id, text="Game Over! Use /play to start again.")
    else:
        # Continue batting: Wait for batsman choice again
        game["state"] = CHOOSING_BAT


# ----- SET COMMANDS FOR TELEGRAM SLASH (auto-suggest) -----


async def set_commands(application):
    commands = [
        BotCommand("start", "Register or welcome message"),
        BotCommand("help", "Show commands list"),
        BotCommand("profile", "Show your profile and coins"),
        BotCommand("play", "Start a hand cricket game"),
        BotCommand("add", "Admin only: Add coins to user"),
        BotCommand("myteam", "Show your team (if implemented)"),
    ]
    await application.bot.set_my_commands(commands)


# ----- MAIN FUNCTION -----

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("add", add_coins))
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Set commands for slash menu
    application.run_polling(
        on_startup=set_commands
    )


if __name__ == "__main__":
    main()
# ----- LEADERBOARD HANDLING -----

def load_leaderboard():
    users = load_users()
    leaderboard = [(uid, data["coins"]) for uid, data in users.items()]
    leaderboard.sort(key=lambda x: x[1], reverse=True)
    return leaderboard


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaderboard = load_leaderboard()
    if not leaderboard:
        await update.message.reply_text("No users registered yet.")
        return

    text = "🏆 Leaderboard (Top 10):\n\n"
    for idx, (uid, coins) in enumerate(leaderboard[:10], start=1):
        users = load_users()
        name = users.get(uid, {}).get("name", "Unknown")
        text += f"{idx}. {name}: {coins} coins\n"
    await update.message.reply_text(text)


# ----- /myteam placeholder -----

async def myteam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    users = load_users()
    if uid not in users:
        await update.message.reply_text("You are not registered yet. Use /start to register.")
        return

    text = (
        f"{user.full_name}, your team feature is coming soon!\n"
        "For now, focus on /play and enjoy the game."
    )
    await update.message.reply_text(text)


# ----- IMPROVED GAME LOGIC (continue from Part 1) -----

async def process_ball(update, context, uid):
    game = games[uid]

    bat = game["batsman_choice"]
    bowl = game["bowler_choice"]

    game["ball"] += 1
    if game["ball"] > 5:
        game["ball"] = 0
        game["over"] += 1

    is_out = bat == bowl
    if is_out:
        game["out"] = True
    else:
        game["total_score"] += bat

    text = get_reveal_text(
        game["over"],
        game["ball"],
        game["batsman_name"],
        game["bowler_name"],
        bat,
        bowl,
        is_out,
        game["total_score"],
    )

    chat_id = game["chat_id"]
    message_id = game["message_id"]

    game["batsman_choice"] = None
    game["bowler_choice"] = None

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=None if is_out else InlineKeyboardMarkup(BUTTONS),
    )

    if is_out:
        users = load_users()
        uid_str = str(uid)
        if uid_str in users:
            reward = game["total_score"] * 10
            users[uid_str]["coins"] += reward
            save_users(users)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Game Over! You earned {reward} coins.\nUse /play to start a new match.",
        )
        del games[uid]
    else:
        game["state"] = CHOOSING_BAT


# ----- RUN MAIN FUNCTION -----

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("add", add_coins))
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CommandHandler("myteam", myteam_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling(on_startup=set_commands)


if __name__ == "__main__":
    main()

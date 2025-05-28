import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import random
import json
import os
from enum import Enum

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    MessageHandler,
    Filters,
)

# ===== CONFIGURATION =====
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace with your bot token
ADMIN_IDS = [123456789]  # Replace with your Telegram ID
COIN_EMOJI = "🪙"
INITIAL_COINS = 4000
DAILY_REWARD = 2000
BET_MULTIPLIER = 2
# ===== END CONFIG =====

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Game states
class GameState(Enum):
    WAITING_FOR_JOIN = 1
    TOSS_CHOICE = 2
    TOSS_RESULT = 3
    BAT_OR_BOWL = 4
    BATTER_TURN = 5
    BOWLER_TURN = 6
    GAME_OVER = 7

# Database structure
class Database:
    def __init__(self):
        self.users: Dict[int, Dict] = {}
        self.active_games: Dict[str, Dict] = {}
        self.leaderboard_cache = {"coins": [], "wins": []}

    def register_user(self, user_id: int, name: str) -> bool:
        if user_id not in self.users:
            self.users[user_id] = {
                "name": name,
                "coins": INITIAL_COINS,
                "wins": 0,
                "losses": 0,
                "last_daily": None,
            }
            return True
        return False

    def get_user(self, user_id: int) -> Optional[Dict]:
        return self.users.get(user_id)

    def update_leaderboard(self):
        self.leaderboard_cache["coins"] = sorted(
            self.users.items(),
            key=lambda x: x[1]["coins"],
            reverse=True,
        )[:10]
        self.leaderboard_cache["wins"] = sorted(
            self.users.items(),
            key=lambda x: x[1]["wins"],
            reverse=True,
        )[:10]

# Initialize database
db = Database()

# ===== GAME LOGIC =====
def create_game(initiator_id: int, bet: int = 0) -> str:
    game_id = f"game_{random.randint(1000, 9999)}"
    db.active_games[game_id] = {
        "state": GameState.WAITING_FOR_JOIN,
        "initiator": initiator_id,
        "opponent": None,
        "bet": bet,
        "toss_choice": None,
        "toss_result": random.choice(["heads", "tails"]),
        "batting": None,
        "bowling": None,
        "score": 0,
        "current_balls": 0,
        "last_move": None,
    }
    return game_id

def handle_toss(update: Update, context: CallbackContext, game_id: str, choice: str):
    game = db.active_games[game_id]
    if game["toss_result"] == choice:
        winner = game["initiator"]
    else:
        winner = game["opponent"]
    
    game["toss_winner"] = winner
    game["state"] = GameState.BAT_OR_BOWL
    
    # Notify players
    winner_name = db.get_user(winner)["name"]
    context.bot.send_message(
        chat_id=game["initiator"],
        text=f"🎉 {winner_name} won the toss!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏏 Bat", callback_data=f"bat_{game_id}")],
            [InlineKeyboardButton("⚾ Bowl", callback_data=f"bowl_{game_id}")]
        ])
    )

# ===== COMMAND HANDLERS =====
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🏏 *Welcome to CCG HandCricket!*\n"
        "A fun PvP cricket game with coins and betting!\n\n"
        "🔹 /register - Get 4000 coins\n"
        "🔹 /pm - Start a match\n"
        "🔹 /profile - View stats\n"
        "🔹 /daily - Claim 2000 coins\n"
        "🔹 /leaderboard - Top players\n"
        "🔹 /help - All commands",
        parse_mode="Markdown"
    )

def register(update: Update, context: CallbackContext):
    user = update.effective_user
    if db.register_user(user.id, user.first_name):
        update.message.reply_text(
            f"✅ *Registration successful!*\n"
            f"You received *{INITIAL_COINS}{COIN_EMOJI}*",
            parse_mode="Markdown"
        )
    else:
        update.message.reply_text("⚠️ You are already registered!")

def pm(update: Update, context: CallbackContext):
    user = update.effective_user
    bet = int(context.args[0]) if context.args else 0
    
    if bet > 0:
        user_data = db.get_user(user.id)
        if user_data["coins"] < bet:
            update.message.reply_text("❌ Not enough coins!")
            return
    
    game_id = create_game(user.id, bet)
    update.message.reply_text(
        f"🏏 *Cricket match started!*\n"
        f"Bet: {bet}{COIN_EMOJI if bet > 0 else 'None'}\n\n"
        f"Press *Join* to play against {user.first_name}!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Join Match", callback_data=f"join_{game_id}")]
        ]),
        parse_mode="Markdown"
    )

# ... [Additional handlers for /profile, /daily, /leaderboard, /add, /help] ...

# ===== MAIN BOT SETUP =====
def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("register", register))
    dp.add_handler(CommandHandler("pm", pm))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("leaderboard", leaderboard))
    dp.add_handler(CommandHandler("add", add_coins))
    dp.add_handler(CommandHandler("help", help_command))

    # Callback handlers
    dp.add_handler(CallbackQueryHandler(join_game, pattern=r"^join_"))
    dp.add_handler(CallbackQueryHandler(handle_toss_choice, pattern=r"^(heads|tails)_"))
    dp.add_handler(CallbackQueryHandler(handle_bat_bowl, pattern=r"^(bat|bowl)_"))
    dp.add_handler(CallbackQueryHandler(handle_number, pattern=r"^num_[1-6]_"))
    dp.add_handler(CallbackQueryHandler(leaderboard_nav, pattern=r"^lb_(next|prev)"))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

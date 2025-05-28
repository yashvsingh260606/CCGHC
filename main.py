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
    filters,
)

# ===== CONFIGURATION =====
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"
ADMIN_IDS = [123456789]  # Your admin ID
COIN_EMOJI = "🪙"
INITIAL_COINS = 4000
DAILY_REWARD = 2000
BET_MULTIPLIER = 2
# ===== END CONFIG =====

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class GameState(Enum):
    WAITING = 1
    TOSS = 2
    PLAYING = 3
    COMPLETED = 4

class Database:
    def __init__(self):
        self.users = {}
        self.games = {}
        self.leaderboard = {"coins": [], "wins": []}
        self.load_data()

    def register_user(self, user_id: int, name: str) -> bool:
        if user_id not in self.users:
            self.users[user_id] = {
                "name": name,
                "coins": INITIAL_COINS,
                "wins": 0,
                "losses": 0,
                "last_daily": None
            }
            self.save_data()
            return True
        return False

    def create_game(self, initiator_id: int, bet: int = 0) -> str:
        game_id = f"game_{random.randint(1000,9999)}"
        self.games[game_id] = {
            "state": GameState.WAITING,
            "players": [initiator_id],
            "bet": bet,
            "toss_winner": None,
            "batsman": None,
            "bowler": None,
            "score": 0,
            "balls": 0
        }
        return game_id

    def update_leaderboard(self):
        self.leaderboard["coins"] = sorted(
            self.users.items(),
            key=lambda x: x[1]["coins"],
            reverse=True
        )[:10]
        self.leaderboard["wins"] = sorted(
            self.users.items(),
            key=lambda x: x[1]["wins"],
            reverse=True
        )[:10]

    def save_data(self):
        with open("data.json", "w") as f:
            json.dump({
                "users": self.users,
                "games": self.games
            }, f)

    def load_data(self):
        try:
            with open("data.json", "r") as f:
                data = json.load(f)
                self.users = data.get("users", {})
                self.games = data.get("games", {})
        except FileNotFoundError:
            pass

db = Database()

# ===== COMMAND HANDLERS =====
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🏏 Welcome to CCG HandCricket!\n"
        "Type /help for commands"
    )

def register(update: Update, context: CallbackContext):
    user = update.effective_user
    if db.register_user(user.id, user.first_name):
        update.message.reply_text(
            f"✅ Registered! You got {INITIAL_COINS}{COIN_EMOJI}"
        )
    else:
        update.message.reply_text("⚠️ Already registered!")

def pm(update: Update, context: CallbackContext):
    user = update.effective_user
    bet = int(context.args[0]) if context.args else 0
    
    if bet > 0:
        if db.users[user.id]["coins"] < bet:
            update.message.reply_text("❌ Not enough coins!")
            return
    
    game_id = db.create_game(user.id, bet)
    update.message.reply_text(
        f"🏏 Match started!\n"
        f"Bet: {bet}{COIN_EMOJI if bet > 0 else ''}\n\n"
        f"Click Join to play vs {user.first_name}!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Join", callback_data=f"join_{game_id}")]
        ])
    )

def profile(update: Update, context: CallbackContext):
    user = update.effective_user
    user_data = db.users.get(user.id)
    if not user_data:
        update.message.reply_text("⚠️ Register first with /register")
        return
    
    update.message.reply_text(
        f"👤 {user_data['name']}'s Profile\n\n"
        f"🆔 ID: {user.id}\n"
        f"💰 Purse: {user_data['coins']}{COIN_EMOJI}\n\n"
        f"📊 Performance:\n"
        f"✅ Wins: {user_data['wins']}\n"
        f"❌ Losses: {user_data['losses']}"
    )

def daily(update: Update, context: CallbackContext):
    user = update.effective_user
    user_data = db.users.get(user.id)
    
    if not user_data:
        update.message.reply_text("⚠️ Register first with /register")
        return
    
    last_claim = user_data.get("last_daily")
    if last_claim and (datetime.now() - last_claim) < timedelta(hours=24):
        update.message.reply_text("⏳ Come back tomorrow!")
        return
    
    user_data["coins"] += DAILY_REWARD
    user_data["last_daily"] = datetime.now().isoformat()
    db.save_data()
    
    update.message.reply_text(
        f"🎉 Daily reward claimed!\n"
        f"+{DAILY_REWARD}{COIN_EMOJI}\n"
        f"New balance: {user_data['coins']}{COIN_EMOJI}"
    )

def leaderboard(update: Update, context: CallbackContext):
    db.update_leaderboard()
    lb_text = "🏆 Top 10 by Coins:\n\n"
    for i, (user_id, data) in enumerate(db.leaderboard["coins"], 1):
        lb_text += f"{i}. {data['name']} - {data['coins']}{COIN_EMOJI}\n"
    
    update.message.reply_text(
        lb_text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ Coins", callback_data="lb_coins"),
                InlineKeyboardButton("Wins ➡️", callback_data="lb_wins")
            ]
        ])
    )

def add_coins(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        update.message.reply_text("❌ Admin only!")
        return
    
    if len(context.args) < 2:
        update.message.reply_text("Usage: /add [user_id] [amount]")
        return
    
    user_id = int(context.args[0])
    amount = int(context.args[1])
    
    if user_id not in db.users:
        update.message.reply_text("❌ User not found")
        return
    
    db.users[user_id]["coins"] += amount
    db.save_data()
    update.message.reply_text(
        f"✅ Added {amount}{COIN_EMOJI} to {db.users[user_id]['name']}"
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📜 CCG HandCricket Commands:\n\n"
        "🏏 /start - Welcome message\n"
        "💰 /register - Get 4000 coins\n"
        "🎮 /pm - Start a match\n"
        "🎮 /pm [amount] - Start bet match\n"
        "👤 /profile - Your stats\n"
        "🔄 /daily - Claim 2000 coins\n"
        "🏆 /leaderboard - Top players\n"
        "\nAdmin:\n"
        "➕ /add [id] [amount] - Give coins"
    )

# ===== GAME HANDLERS =====
def handle_join(update: Update, context: CallbackContext):
    query = update.callback_query
    game_id = query.data.split("_")[1]
    
    if game_id not in db.games:
        query.answer("❌ Game expired")
        return
    
    game = db.games[game_id]
    if len(game["players"]) >= 2:
        query.answer("❌ Game full")
        return
    
    game["players"].append(update.effective_user.id)
    game["state"] = GameState.TOSS
    
    # Notify both players
    p1_name = db.users[game["players"][0]]["name"]
    p2_name = db.users[game["players"][1]]["name"]
    
    context.bot.send_message(
        chat_id=game["players"][0],
        text=f"🎉 {p2_name} joined your match!\n\n"
             f"Choose heads or tails:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Heads", callback_data=f"heads_{game_id}")],
            [InlineKeyboardButton("Tails", callback_data=f"tails_{game_id}")]
        ])
    )
    
    query.answer("✅ Joined match!")
    query.edit_message_text(f"⚡ {p1_name} vs {p2_name}\nWaiting for toss...")

def handle_toss(update: Update, context: CallbackContext):
    query = update.callback_query
    choice, game_id = query.data.split("_")
    
    if game_id not in db.games:
        query.answer("❌ Game expired")
        return
    
    game = db.games[game_id]
    if game["state"] != GameState.TOSS:
        query.answer("❌ Invalid action")
        return
    
    # Determine toss winner
    toss_result = random.choice(["heads", "tails"])
    winner_idx = 0 if choice == toss_result else 1
    game["toss_winner"] = game["players"][winner_idx]
    game["state"] = GameState.PLAYING
    
    # Ask winner to choose bat/bowl
    winner_name = db.users[game["toss_winner"]]["name"]
    context.bot.send_message(
        chat_id=game["toss_winner"],
        text=f"🎉 You won the toss!\n\n"
             f"Choose to bat or bowl:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏏 Bat", callback_data=f"bat_{game_id}")],
            [InlineKeyboardButton("⚾ Bowl", callback_data=f"bowl_{game_id}")]
        ])
    )
    
    # Notify both players
    for player_id in game["players"]:
        if player_id != game["toss_winner"]:
            context.bot.send_message(
                chat_id=player_id,
                text=f"ℹ️ {winner_name} won the toss and is choosing..."
            )

def handle_bat_bowl(update: Update, context: CallbackContext):
    query = update.callback_query
    choice, game_id = query.data.split("_")
    
    if game_id not in db.games:
        query.answer("❌ Game expired")
        return
    
    game = db.games[game_id]
    if game["state"] != GameState.PLAYING:
        query.answer("❌ Invalid action")
        return
    
    # Set batting/bowling roles
    if choice == "bat":
        game["batsman"] = game["toss_winner"]
        game["bowler"] = game["players"][1] if game["players"][0] == game["toss_winner"] else game["players"][0]
    else:
        game["bowler"] = game["toss_winner"]
        game["batsman"] = game["players"][1] if game["players"][0] == game["toss_winner"] else game["players"][0]
    
    # Start the game
    batsman_name = db.users[game["batsman"]]["name"]
    bowler_name = db.users[game["bowler"]]["name"]
    
    for player_id in game["players"]:
        context.bot.send_message(
            chat_id=player_id,
            text=f"🏏 {batsman_name} is batting\n"
                 f"⚾ {bowler_name} is bowling\n\n"
                 f"Choose your number (1-6):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(1,4)],
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(4,7)]
            ])
        )
    
    query.answer()

def handle_number(update: Update, context: CallbackContext):
    query = update.callback_query
    num, game_id = query.data.split("_")[1:]
    num = int(num)
    
    if game_id not in db.games:
        query.answer("❌ Game expired")
        return
    
    game = db.games[game_id]
    player_id = update.effective_user.id
    
    # Store player's choice
    if player_id not in game:
        game[player_id] = {}
    
    game[player_id]["choice"] = num
    
    # Check if both players have chosen
    if all(p_id in game and "choice" in game[p_id] for p_id in game["players"]):
        resolve_round(game_id, context)
    
    query.answer(f"✅ You chose {num}")

def resolve_round(game_id: str, context: CallbackContext):
    game = db.games[game_id]
    batsman_choice = game[game["batsman"]]["choice"]
    bowler_choice = game[game["bowler"]]["choice"]
    
    batsman_name = db.users[game["batsman"]]["name"]
    bowler_name = db.users[game["bowler"]]["name"]
    
    # Determine outcome
    if batsman_choice == bowler_choice:
        # Batsman out
        game["state"] = GameState.COMPLETED
        winner = game["bowler"]
        loser = game["batsman"]
        
        # Update stats
        db.users[winner]["wins"] += 1
        db.users[loser]["losses"] += 1
        
        # Handle bet
        if game["bet"] > 0:
            db.users[winner]["coins"] += game["bet"] * BET_MULTIPLIER
            db.users[loser]["coins"] -= game["bet"]
        
        # Send result
        for player_id in game["players"]:
            context.bot.send_message(
                chat_id=player_id,
                text=f"🏏 {batsman_name} bat {batsman_choice}\n"
                     f"⚾ {bowler_name} bowl {bowler_choice}\n\n"
                     f"🎯 WICKET! {bowler_name} wins!\n"
                     f"💰 Reward: {game['bet'] * BET_MULTIPLIER if game['bet'] > 0 else 'None'}"
            )
    else:
        # Batsman scores
        game["score"] += batsman_choice
        game["balls"] += 1
        
        # Continue game
        for player_id in game["players"]:
            context.bot.send_message(
                chat_id=player_id,
                text=f"🏏 {batsman_name} bat {batsman_choice}\n"
                     f"⚾ {bowler_name} bowl {bowler_choice}\n\n"
                     f"📊 Score: {game['score']}\n"
                     f"🔢 Balls: {game['balls']}\n\n"
                     f"Next round!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(1,4)],
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(4,7)]
                ])
            )
        
        # Clear choices for next round
        del game[game["batsman"]]["choice"]
        del game[game["bowler"]]["choice"]

def handle_leaderboard(update: Update, context: CallbackContext):
    query = update.callback_query
    lb_type = query.data.split("_")[1]
    
    db.update_leaderboard()
    lb_data = db.leaderboard[lb_type]
    
    lb_text = f"🏆 Top 10 by {'Coins' if lb_type == 'coins' else 'Wins'}:\n\n"
    for i, (user_id, data) in enumerate(lb_data, 1):
        lb_text += f"{i}. {data['name']} - {data[lb_type]}{COIN_EMOJI if lb_type == 'coins' else ''}\n"
    
    query.edit_message_text(
        lb_text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ Coins", callback_data="lb_coins"),
                InlineKeyboardButton("Wins ➡️", callback_data="lb_wins")
            ]
        ])
    )
    query.answer()

# ===== MAIN =====
def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    # Commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("register", register))
    dp.add_handler(CommandHandler("pm", pm))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("daily", daily))
    dp.add_handler(CommandHandler("leaderboard", leaderboard))
    dp.add_handler(CommandHandler("add", add_coins))
    dp.add_handler(CommandHandler("help", help_command))

    # Callbacks
    dp.add_handler(CallbackQueryHandler(handle_join, pattern=r"^join_"))
    dp.add_handler(CallbackQueryHandler(handle_toss, pattern=r"^(heads|tails)_"))
    dp.add_handler(CallbackQueryHandler(handle_bat_bowl, pattern=r"^(bat|bowl)_"))
    dp.add_handler(CallbackQueryHandler(handle_number, pattern=r"^num_"))
    dp.add_handler(CallbackQueryHandler(handle_leaderboard, pattern=r"^lb_"))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

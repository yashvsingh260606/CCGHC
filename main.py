import logging
from typing import Dict, List
from datetime import datetime, timedelta
import random
import json
from enum import Enum
from threading import Lock
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ===== CONFIG =====
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace with your actual token
ADMIN_IDS = [123456789]  # Your Telegram ID
COIN_EMOJI = "🪙"
INITIAL_COINS = 4000
DAILY_REWARD = 2000
BET_MULTIPLIER = 2
DATA_FILE = Path("data/chcdata.json")
# ===== END CONFIG =====

# Ensure data directory exists
Path("data").mkdir(exist_ok=True)

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Game states
class GameState(Enum):
    WAITING = 1
    TOSS = 2
    PLAYING = 3
    COMPLETED = 4

# Database class
class Database:
    def __init__(self):
        self.lock = Lock()
        self.users = {}
        self.games = {}
        self.load_data()

    def register_user(self, user_id: int, name: str) -> bool:
        with self.lock:
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
        with self.lock:
            game_id = f"game_{random.randint(1000,9999)}"
            self.games[game_id] = {
                "state": GameState.WAITING,
                "players": [initiator_id],
                "bet": bet,
                "toss_winner": None,
                "batsman": None,
                "bowler": None,
                "score": 0,
                "balls": 0,
                "created_time": datetime.now().isoformat()
            }
            self.save_data()
        return game_id

    def save_data(self):
        with self.lock:
            try:
                with open(DATA_FILE, "w") as f:
                    json.dump({
                        "users": self.users,
                        "games": self.games
                    }, f, indent=4)
            except Exception as e:
                logger.error(f"Error saving data: {e}")

    def load_data(self):
        try:
            if DATA_FILE.exists():
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                    self.users = data.get("users", {})
                    self.games = data.get("games", {})
                    logger.info("Data loaded successfully")
            else:
                logger.info("No data file found - starting fresh")
        except json.JSONDecodeError:
            logger.warning("Corrupted data file - starting fresh")
            self.users = {}
            self.games = {}
        except Exception as e:
            logger.error(f"Error loading data: {e} - starting fresh")
            self.users = {}
            self.games = {}

db = Database()

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    await update.message.reply_text(
        "🏏 *Welcome to CCG HandCricket!*\n"
        "Type /help for commands",
        parse_mode="Markdown"
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register new user"""
    user = update.effective_user
    if db.register_user(user.id, user.first_name):
        await update.message.reply_text(
            f"✅ Registered! You got {INITIAL_COINS}{COIN_EMOJI}"
        )
    else:
        await update.message.reply_text("⚠️ Already registered!")

async def pm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new match"""
    user = update.effective_user
    
    if user.id not in db.users:
        await update.message.reply_text("⚠️ Register first with /register")
        return
    
    try:
        bet = int(context.args[0]) if context.args else 0
        if bet < 0:
            await update.message.reply_text("❌ Bet amount cannot be negative!")
            return
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number for bet!")
        return
    
    if bet > 0 and db.users[user.id]["coins"] < bet:
        await update.message.reply_text("❌ Not enough coins!")
        return
    
    game_id = db.create_game(user.id, bet)
    
    await update.message.reply_text(
        f"🏏 *Match started!*\n"
        f"Bet: {bet}{COIN_EMOJI if bet > 0 else ''}\n\n"
        f"Click Join to play vs {user.first_name}!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Join", callback_data=f"join_{game_id}")]
        ]),
        parse_mode="Markdown"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile"""
    user = update.effective_user
    if user.id not in db.users:
        await update.message.reply_text("⚠️ Register first with /register")
        return
    
    user_data = db.users[user.id]
    await update.message.reply_text(
        f"👤 *{user_data['name']}'s Profile*\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"💰 Purse: {user_data['coins']}{COIN_EMOJI}\n\n"
        f"📊 *Performance*\n"
        f"✅ Wins: {user_data['wins']}\n"
        f"❌ Losses: {user_data['losses']}",
        parse_mode="Markdown"
    )

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Claim daily reward"""
    user = update.effective_user
    if user.id not in db.users:
        await update.message.reply_text("⚠️ Register first with /register")
        return
    
    user_data = db.users[user.id]
    last_claim = user_data.get("last_daily")
    
    if last_claim and (datetime.now() - datetime.fromisoformat(last_claim)) < timedelta(hours=24):
        await update.message.reply_text("⏳ Come back tomorrow!")
        return
    
    user_data["coins"] += DAILY_REWARD
    user_data["last_daily"] = datetime.now().isoformat()
    db.save_data()
    
    await update.message.reply_text(
        f"🎉 Daily reward claimed!\n"
        f"+{DAILY_REWARD}{COIN_EMOJI}\n"
        f"New balance: {user_data['coins']}{COIN_EMOJI}"
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard"""
    coins_lb = sorted(db.users.values(), key=lambda x: x["coins"], reverse=True)[:10]
    
    text = "🏆 *Top 10 by Coins*\n\n"
    for i, user in enumerate(coins_lb, 1):
        text += f"{i}. {user['name']} - {user['coins']}{COIN_EMOJI}\n"
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Coins", callback_data="lb_coins"),
                InlineKeyboardButton("Wins", callback_data="lb_wins")
            ]
        ]),
        parse_mode="Markdown"
    )

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add coins"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin only!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /add [user_id] [amount]")
        return
    
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid numbers")
        return
    
    if user_id not in db.users:
        await update.message.reply_text("❌ User not found")
        return
    
    db.users[user_id]["coins"] += amount
    db.save_data()
    await update.message.reply_text(
        f"✅ Added {amount}{COIN_EMOJI} to {db.users[user_id]['name']}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    await update.message.reply_text(
        "📜 *CCG HandCricket Commands*\n\n"
        "🏏 /start - Welcome message\n"
        "💰 /register - Get 4000 coins\n"
        "🎮 /pm - Start a match\n"
        "🎮 /pm [amount] - Start bet match\n"
        "👤 /profile - Your stats\n"
        "🔄 /daily - Claim 2000 coins\n"
        "🏆 /leaderboard - Top players\n"
        "\nAdmin:\n"
        "➕ /add [id] [amount] - Give coins",
        parse_mode="Markdown"
    )

# ===== GAME HANDLERS =====
async def handle_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join game callback"""
    query = update.callback_query
    await query.answer()
    
    game_id = query.data.split("_")[1]
    if game_id not in db.games:
        await query.edit_message_text("❌ Game expired")
        return
    
    game = db.games[game_id]
    user = update.effective_user
    
    if user.id == game["players"][0]:
        await query.answer("❌ You can't join your own game!", show_alert=True)
        return
    
    if len(game["players"]) >= 2:
        await query.answer("❌ Game full", show_alert=True)
        return
    
    if user.id not in db.users:
        await query.answer("⚠️ Register first with /register", show_alert=True)
        return
    
    game["players"].append(user.id)
    game["state"] = GameState.TOSS
    
    p1 = db.users[game["players"][0]]["name"]
    p2 = db.users[user.id]["name"]
    
    await query.edit_message_text(
        f"⚡ {p1} vs {p2}\n"
        f"Bet: {game['bet']}{COIN_EMOJI if game['bet'] > 0 else ''}\n\n"
        f"Waiting for toss decision..."
    )
    
    await context.bot.send_message(
        chat_id=game["players"][0],
        text=f"🎉 {p2} joined your match!\n\nChoose:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Heads", callback_data=f"heads_{game_id}")],
            [InlineKeyboardButton("Tails", callback_data=f"tails_{game_id}")]
        ])
    )

async def handle_toss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle toss selection"""
    query = update.callback_query
    await query.answer()
    
    choice, game_id = query.data.split("_")
    if game_id not in db.games:
        await query.edit_message_text("❌ Game expired")
        return
    
    game = db.games[game_id]
    if game["state"] != GameState.TOSS:
        await query.answer("❌ Invalid action")
        return
    
    toss_result = random.choice(["heads", "tails"])
    winner_idx = 0 if choice == toss_result else 1
    game["toss_winner"] = game["players"][winner_idx]
    game["state"] = GameState.PLAYING
    
    winner_name = db.users[game["toss_winner"]]["name"]
    await context.bot.send_message(
        chat_id=game["toss_winner"],
        text=f"🎉 You won the toss!\n\nChoose:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏏 Bat", callback_data=f"bat_{game_id}")],
            [InlineKeyboardButton("⚾ Bowl", callback_data=f"bowl_{game_id}")]
        ])
    )
    
    other_id = game["players"][1] if winner_idx == 0 else game["players"][0]
    await context.bot.send_message(
        chat_id=other_id,
        text=f"ℹ️ {winner_name} won the toss and is choosing..."
    )

async def handle_bat_bowl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bat/bowl selection"""
    query = update.callback_query
    await query.answer()
    
    choice, game_id = query.data.split("_")
    if game_id not in db.games:
        await query.edit_message_text("❌ Game expired")
        return
    
    game = db.games[game_id]
    if game["state"] != GameState.PLAYING:
        await query.answer("❌ Invalid action")
        return
    
    if choice == "bat":
        game["batsman"] = game["toss_winner"]
        game["bowler"] = game["players"][1] if game["players"][0] == game["toss_winner"] else game["players"][0]
    else:
        game["bowler"] = game["toss_winner"]
        game["batsman"] = game["players"][1] if game["players"][0] == game["toss_winner"] else game["players"][0]
    
    batsman_name = db.users[game["batsman"]]["name"]
    bowler_name = db.users[game["bowler"]]["name"]
    
    for player_id in game["players"]:
        await context.bot.send_message(
            chat_id=player_id,
            text=f"🏏 {batsman_name} is batting\n"
                 f"⚾ {bowler_name} is bowling\n\n"
                 f"Choose your number:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(1,4)],
                [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(4,7)]
            ])
        )

async def handle_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle number selection during gameplay"""
    query = update.callback_query
    await query.answer()
    
    num, game_id = query.data.split("_")[1:]
    num = int(num)
    
    if game_id not in db.games:
        await query.edit_message_text("❌ Game expired")
        return
    
    if num < 1 or num > 6:
        await query.answer("❌ Please choose between 1-6")
        return
    
    game = db.games[game_id]
    player_id = update.effective_user.id
    
    if f"choice_{player_id}" not in game:
        game[f"choice_{player_id}"] = num
    
    if all(f"choice_{p_id}" in game for p_id in game["players"]):
        await resolve_round(game_id, context)

async def resolve_round(game_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Resolve a round of gameplay"""
    game = db.games[game_id]
    batsman_choice = game[f"choice_{game['batsman']}"]
    bowler_choice = game[f"choice_{game['bowler']}"]
    
    batsman_name = db.users[game["batsman"]]["name"]
    bowler_name = db.users[game["bowler"]]["name"]
    
    if batsman_choice == bowler_choice:
        game["state"] = GameState.COMPLETED
        game["completed_time"] = datetime.now().isoformat()
        winner = game["bowler"]
        loser = game["batsman"]
        
        db.users[winner]["wins"] += 1
        db.users[loser]["losses"] += 1
        
        if game["bet"] > 0:
            db.users[winner]["coins"] += game["bet"] * BET_MULTIPLIER
            db.users[loser]["coins"] -= game["bet"]
            db.save_data()
        
        for player_id in game["players"]:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"🏏 {batsman_name} chose {batsman_choice}\n"
                     f"⚾ {bowler_name} chose {bowler_choice}\n\n"
                     f"🎯 WICKET! {bowler_name} wins!\n"
                     f"💰 Reward: {game['bet'] * BET_MULTIPLIER if game['bet'] > 0 else 'None'}"
            )
    else:
        game["score"] += batsman_choice
        game["balls"] += 1
        
        del game[f"choice_{game['batsman']}"]
        del game[f"choice_{game['bowler']}"]
        
        for player_id in game["players"]:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"🏏 {batsman_name} chose {batsman_choice}\n"
                     f"⚾ {bowler_name} chose {bowler_choice}\n\n"
                     f"📊 Score: {game['score']}\n"
                     f"🔢 Balls: {game['balls']}\n\n"
                     f"Next round!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(1,4)],
                    [InlineKeyboardButton(str(i), callback_data=f"num_{i}_{game_id}") for i in range(4,7)]
                ])
            )

async def handle_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle leaderboard callback"""
    query = update.callback_query
    await query.answer()
    
    lb_type = query.data.split("_")[1]
    if lb_type == "coins":
        lb_data = sorted(db.users.values(), key=lambda x: x["coins"], reverse=True)[:10]
        title = "Coins"
    else:
        lb_data = sorted(db.users.values(), key=lambda x: x["wins"], reverse=True)[:10]
        title = "Wins"
    
    text = f"🏆 *Top 10 by {title}*\n\n"
    for i, user in enumerate(lb_data, 1):
        text += f"{i}. {user['name']} - {user[lb_type]}{COIN_EMOJI if lb_type == 'coins' else ''}\n"
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Coins", callback_data="lb_coins"),
                InlineKeyboardButton("Wins", callback_data="lb_wins")
            ]
        ]),
        parse_mode="Markdown"
    )

# ===== CLEANUP FUNCTIONS =====
async def cleanup_games(context: ContextTypes.DEFAULT_TYPE):
    """Clean up old games"""
    now = datetime.now()
    expired_games = []
    
    for game_id, game in db.games.items():
        if game["state"] == GameState.COMPLETED:
            if "completed_time" in game:
                if (now - datetime.fromisoformat(game["completed_time"])) > timedelta(hours=1):
                    expired_games.append(game_id)
        elif game["state"] == GameState.WAITING:
            if (now - datetime.fromisoformat(game["created_time"])) > timedelta(minutes=5):
                expired_games.append(game_id)
    
    for game_id in expired_games:
        del db.games[game_id]
    
    if expired_games:
        db.save_data()
        logger.info(f"Cleaned up {len(expired_games)} games")

async def periodic_save(context: ContextTypes.DEFAULT_TYPE):
    """Periodically save data"""
    db.save_data()
    logger.info("Periodic data save completed")

# ===== MAIN =====
def main():
    """Start the bot"""
    # Create Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("pm", pm))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("add", add_coins))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add callback handlers
    application.add_handler(CallbackQueryHandler(handle_join, pattern=r"^join_"))
    application.add_handler(CallbackQueryHandler(handle_toss, pattern=r"^(heads|tails)_"))
    application.add_handler(CallbackQueryHandler(handle_bat_bowl, pattern=r"^(bat|bowl)_"))
    application.add_handler(CallbackQueryHandler(handle_number, pattern=r"^num_"))
    application.add_handler(CallbackQueryHandler(handle_leaderboard, pattern=r"^lb_"))
    
    # Setup job queue if available
    try:
        if application.job_queue:
            application.job_queue.run_repeating(cleanup_games, interval=3600, first=10)
            application.job_queue.run_repeating(periodic_save, interval=300, first=60)
            logger.info("JobQueue initialized successfully")
    except Exception as e:
        logger.error(f"JobQueue setup failed: {e}")
    
    # Start the Bot
    logger.info("Bot starting...")
    application.run_polling()

if __name__ == "__main__":
    main()

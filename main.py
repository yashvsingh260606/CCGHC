import logging
import random
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from motor.motor_asyncio import AsyncIOMotorClient

# --- Configuration ---
# List of Telegram user IDs who are bot admins
 # Replace with your own Telegram user IDs
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace with your bot token
MONGO_URL = "mongodb://mongo:GhpHMiZizYnvJfKIQKxoDbRyzBCpqEyC@mainline.proxy.rlwy.net:54853"  # Replace with your MongoDB URI
# --- Configuration ---

# List of Telegram user IDs who are bot admins
# Replace with your own Telegram user IDs
BOT_ADMINS = [7361215114, 987654321]  # <--- Replace these with your Telegram user IDs
# --- MongoDB Setup ---
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client.handcricket
users_collection = db.users

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Data ---
USERS = {}  # user_id -> user dict
CCL_MATCHES = {}  # match_id -> match dict
USER_CCL_MATCH = {}  # user_id -> match_id or None
GROUP_CCL_MATCH = {}  # group_chat_id -> match_id or None

# --- Helper Functions ---

def get_username(user):
    return user.first_name or user.username or "Player"

def ensure_user(user):
    if user.id not in USERS:
        USERS[user.id] = {
            "user_id": user.id,
            "name": get_username(user),
            "coins": 0,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "registered": False,
            "last_daily": None,
            "achievements": [],  # <--- Add this line
        }
        USER_CCL_MATCH[user.id] = None
    else:
        # Ensure achievements field exists for old users
        if "achievements" not in USERS[user.id]:
            USERS[user.id]["achievements"] = []
            

async def save_user(user_id):
    try:
        user = USERS[user_id]
        await users_collection.update_one(
            {"user_id": user_id},
            {"$set": user},
            upsert=True,
        )
        logger.info(f"Saved user {user_id} to DB.")
    except Exception as e:
        logger.error(f"Error saving user {user_id}: {e}", exc_info=True)

async def load_users():
    try:
        cursor = users_collection.find({})
        async for user in cursor:
            user_id = user.get("user_id")
            USERS[user_id] = user
            USER_CCL_MATCH[user_id] = None
        logger.info("Users loaded from DB.")
    except Exception as e:
        logger.error(f"Error loading users: {e}", exc_info=True)

# --- Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    await update.message.reply_text(
        f"Welcome to HandCricket, {USERS[user.id]['name']}!\nUse /register to get 4000🪙 coins."
    )
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Replace with your actual bot admin check function or list
    if user_id not in BOT_ADMINS:
        await update.message.reply_text("This command is for bot admins only.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /remove <userid> <amount>")
        return

    try:
        target_user_id = int(args[0])
        amount = int(args[1])
        if amount <= 0:
            await update.message.reply_text("Amount must be positive.")
            return
    except ValueError:
        await update.message.reply_text("User ID and amount must be numbers.")
        return

    # Ensure target user exists in USERS, otherwise load from DB
    if target_user_id not in USERS:
        user_data = await users_collection.find_one({"user_id": target_user_id})
        if not user_data:
            await update.message.reply_text(f"User with ID {target_user_id} not found.")
            return
        USERS[target_user_id] = user_data

    current_coins = USERS[target_user_id].get("coins", 0)
    new_coins = max(0, current_coins - amount)
    USERS[target_user_id]["coins"] = new_coins

    # Save to MongoDB
    await users_collection.update_one(
        {"user_id": target_user_id},
        {"$set": {"coins": new_coins}},
        upsert=True,
    )

    await update.message.reply_text(
        f"✅ Removed {amount} coins from user {target_user_id}.\n"
        f"New balance: {new_coins}🪙"
    )
    
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    if USERS[user.id]["registered"]:
        await update.message.reply_text("You're already registered!")
        return
    USERS[user.id]["coins"] += 4000
    USERS[user.id]["registered"] = True
    await save_user(user.id)
    await update.message.reply_text("Registered! 4000🪙 added to your account.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    user_data = USERS[user.id]
    achievements = user_data.get("achievements", [])
    achievement_text = "\n".join([f"🏅 {a}" for a in achievements]) if achievements else "None"
    profile_text = (
        f"{user_data['name']}'s Profile\n\n"
        f"Name: {user_data['name']}\n"
        f"ID: {user.id}\n"
        f"Purse: {user_data.get('coins', 0)}🪙\n\n"
        f"Performance History:\n"
        f"Wins: {user_data.get('wins', 0)}\n"
        f"Losses: {user_data.get('losses', 0)}\n"
        f"Ties: {user_data.get('ties', 0)}\n\n"
        f"Achievements:\n{achievement_text}"
    )
    await update.message.reply_text(profile_text)
    
async def send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to send coins.")
        return
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Usage: /send <amount> (reply to user)")
        return
    amount = int(args[0])
    if amount <= 0:
        await update.message.reply_text("Please enter a positive amount.")
        return
    sender = USERS[user.id]
    if sender["coins"] < amount:
        await update.message.reply_text(f"You don't have enough coins to send {amount}🪙.")
        return
    receiver_user = update.message.reply_to_message.from_user
    ensure_user(receiver_user)
    receiver = USERS[receiver_user.id]
    sender["coins"] -= amount
    receiver["coins"] += amount
    await save_user(user.id)
    await save_user(receiver_user.id)
    await update.message.reply_text(
        f"✅ {user.first_name} sent {amount}🪙 to {receiver['name']}."
    )


from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import io

async def create_fiery_gold_profile_card(user_data, context):
    width, height = 700, 350
    left_w = 280
    right_w = width - left_w

    # --- Card Base ---
    card = Image.new("RGB", (width, height), (20, 20, 20))
    draw = ImageDraw.Draw(card)

    # --- Fiery Left Panel Gradient ---
    left_panel = Image.new("RGBA", (left_w, height), (0, 0, 0, 0))
    lp_draw = ImageDraw.Draw(left_panel)
    for y in range(height):
        # Multi-stop fiery gradient: black → red → orange → gold
        if y < height * 0.33:
            r = int(30 + (y / (height * 0.33)) * 100)
            g = int(20 + (y / (height * 0.33)) * 10)
            b = int(20 + (y / (height * 0.33)) * 20)
        elif y < height * 0.66:
            r = int(130 + ((y - height * 0.33) / (height * 0.33)) * 90)
            g = int(30 + ((y - height * 0.33) / (height * 0.33)) * 70)
            b = int(40 + ((y - height * 0.33) / (height * 0.33)) * 20)
        else:
            r = int(220 + ((y - height * 0.66) / (height * 0.34)) * 35)
            g = int(100 + ((y - height * 0.66) / (height * 0.34)) * 115)
            b = int(60 + ((y - height * 0.66) / (height * 0.34)) * 30)
        lp_draw.line([(0, y), (left_w, y)], fill=(r, g, b, 255))
    # Smooth, rounded right edge
    mask = Image.new("L", (left_w, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (left_w, height)], 60, fill=255)
    left_panel.putalpha(mask)
    card.paste(left_panel, (0, 0), left_panel)

    # --- Profile Picture (real or placeholder) ---
    avatar_radius = 60
    avatar_center = (left_w // 2, height // 2 - 20)
    profile_photo = await get_user_profile_photo(context, user_data["user_id"])
    avatar_img = Image.new("RGBA", (avatar_radius * 2, avatar_radius * 2), (0, 0, 0, 0))
    av_draw = ImageDraw.Draw(avatar_img)
    av_draw.ellipse((0, 0, avatar_radius * 2, avatar_radius * 2), fill=(255, 215, 0, 255))  # Gold ring

    if profile_photo:
        profile_photo = profile_photo.resize((avatar_radius * 2 - 12, avatar_radius * 2 - 12))
        mask = Image.new("L", (avatar_radius * 2 - 12, avatar_radius * 2 - 12), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, avatar_radius * 2 - 12, avatar_radius * 2 - 12), fill=255)
        profile_photo = ImageOps.fit(profile_photo, (avatar_radius * 2 - 12, avatar_radius * 2 - 12))
        avatar_img.paste(profile_photo, (6, 6), mask)
    else:
        av_draw.ellipse((6, 6, avatar_radius * 2 - 6, avatar_radius * 2 - 6), fill=(30, 30, 30, 255))
    card.paste(avatar_img, (avatar_center[0] - avatar_radius, avatar_center[1] - avatar_radius), avatar_img)

    # --- User name on left (fluorescent gold) ---
    try:
        name_font = ImageFont.truetype("arialbd.ttf", 22)
    except:
        name_font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), user_data['name'], font=name_font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((avatar_center[0] - w // 2, avatar_center[1] + avatar_radius + 10), user_data['name'], font=name_font, fill=(255, 255, 80))

    # --- Right Panel: Black with gold border and neon accent ---
    right_panel = Image.new("RGBA", (right_w, height), (30, 30, 30, 255))
    rp_draw = ImageDraw.Draw(right_panel)
    rp_mask = Image.new("L", (right_w, height), 0)
    ImageDraw.Draw(rp_mask).rounded_rectangle([(0, 0), (right_w, height)], 60, fill=255)
    right_panel.putalpha(rp_mask)
    card.paste(right_panel, (left_w, 0), right_panel)
    # Gold border
    draw.rounded_rectangle([(left_w, 0), (width, height)], 60, outline=(255, 215, 0), width=4)

    # --- Stats and Achievements (neon gold/orange) ---
    try:
        header_font = ImageFont.truetype("arialbd.ttf", 20)
        normal_font = ImageFont.truetype("arial.ttf", 16)
    except:
        header_font = normal_font = ImageFont.load_default()
    x0 = left_w + 40
    y0 = 60
    draw.text((x0, y0), "🏏 HandCricket Profile", font=header_font, fill=(255, 255, 80))
    y0 += 35
    draw.text((x0, y0), f"ID: {user_data['user_id']}", font=normal_font, fill=(255, 215, 0))
    y0 += 25
    draw.text((x0, y0), f"Coins: {user_data.get('coins', 0)} 🪙", font=normal_font, fill=(255, 255, 80))
    y0 += 25
    draw.text((x0, y0), f"Wins: {user_data.get('wins', 0)}", font=normal_font, fill=(255, 140, 0))
    y0 += 20
    draw.text((x0, y0), f"Losses: {user_data.get('losses', 0)}", font=normal_font, fill=(255, 80, 80))
    y0 += 20
    draw.text((x0, y0), f"Ties: {user_data.get('ties', 0)}", font=normal_font, fill=(80, 255, 255))
    y0 += 35
    draw.text((x0, y0), "Achievements:", font=header_font, fill=(255, 255, 80))
    y0 += 25
    achievements = user_data.get("achievements", [])
    if achievements:
        for i, ach in enumerate(achievements[:4]):
            draw.text((x0 + 15, y0 + i * 22), f"🏅 {ach}", font=normal_font, fill=(255, 215, 0))
    else:
        draw.text((x0 + 15, y0), "No achievements yet", font=normal_font, fill=(255, 255, 80))

    # Save to buffer
    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
    
    
    
    


async def profilecard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    user_data = USERS[user.id]
    buffer = await create_modern_profile_card(user_data)
    await update.message.reply_photo(
        photo=InputFile(buffer, filename="profile_card.png"),
        caption=f"🔥 {user_data['name']}'s HandCricket Card"
    )
    


    
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    user_data = USERS[user.id]
    now = datetime.utcnow()

    last_daily_str = user_data.get("last_daily")
    if last_daily_str:
        try:
            last_daily = datetime.fromisoformat(last_daily_str)
            if now - last_daily < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last_daily)
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                await update.message.reply_text(
                    f"⏳ You have already claimed your daily reward.\n"
                    f"Come back in {hours}h {minutes}m."
                )
                return
        except Exception:
            pass

    reward = 2000  # Fixed 2,000 coins daily reward
    user_data["coins"] = user_data.get("coins", 0) + reward
    user_data["last_daily"] = now.isoformat()
    await save_user(user.id)
    await update.message.reply_text(f"🎉 You received your daily reward of {reward}🪙!")

# --- Leaderboard ---

def leaderboard_markup(current="coins"):
    if current == "coins":
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Show Wins 🏆", callback_data="leaderboard_wins")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Show Coins 🪙", callback_data="leaderboard_coins")]
        ])

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    sorted_users = sorted(USERS.values(), key=lambda u: u.get("coins", 0), reverse=True)
    text = "🏆 Top 10 Players by Coins:\n\n"
    for i, u in enumerate(sorted_users[:10], 1):
        text += f"{i}. {u.get('name', 'Unknown')} - {u.get('coins', 0)} 🪙\n"
    await update.message.reply_text(text, reply_markup=leaderboard_markup("coins"))

async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if data == "leaderboard_coins":
        sorted_users = sorted(USERS.values(), key=lambda u: u.get("coins", 0), reverse=True)
        text = "🏆 Top 10 Players by Coins:\n\n"
        for i, u in enumerate(sorted_users[:10], 1):
            text += f"{i}. {u.get('name', 'Unknown')} - {u.get('coins', 0)} 🪙\n"
        markup = leaderboard_markup("coins")
    elif data == "leaderboard_wins":
        sorted_users = sorted(USERS.values(), key=lambda u: u.get("wins", 0), reverse=True)
        text = "🏆 Top 10 Players by Wins:\n\n"
        for i, u in enumerate(sorted_users[:10], 1):
            text += f"{i}. {u.get('name', 'Unknown')} - {u.get('wins', 0)} 🏆\n"
        markup = leaderboard_markup("wins")
    else:
        await query.answer()
        return
    await query.message.edit_text(text, reply_markup=markup)
    await query.answer()

async def addachievement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in BOT_ADMINS:
        await update.message.reply_text("This command is for bot admins only.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addachievement <userid> <achievement>")
        return

    try:
        target_user_id = int(context.args[0])
        achievement = " ".join(context.args[1:])
    except ValueError:
        await update.message.reply_text("User ID must be a number.")
        return

    # Ensure user is loaded
    if target_user_id not in USERS:
        user_data = await users_collection.find_one({"user_id": target_user_id})
        if not user_data:
            await update.message.reply_text(f"User with ID {target_user_id} not found.")
            return
        USERS[target_user_id] = user_data
        if "achievements" not in USERS[target_user_id]:
            USERS[target_user_id]["achievements"] = []

    if achievement in USERS[target_user_id]["achievements"]:
        await update.message.reply_text("User already has this achievement.")
        return

    USERS[target_user_id]["achievements"].append(achievement)
    await users_collection.update_one(
        {"user_id": target_user_id},
        {"$set": {"achievements": USERS[target_user_id]["achievements"]}},
        upsert=True,
    )
    await update.message.reply_text(f"Achievement added to user {target_user_id}.")

async def removeachievement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in BOT_ADMINS:
        await update.message.reply_text("This command is for bot admins only.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /removeachievement <userid> <achievement>")
        return

    try:
        target_user_id = int(context.args[0])
        achievement = " ".join(context.args[1:])
    except ValueError:
        await update.message.reply_text("User ID must be a number.")
        return

    # Ensure user is loaded
    if target_user_id not in USERS:
        user_data = await users_collection.find_one({"user_id": target_user_id})
        if not user_data:
            await update.message.reply_text(f"User with ID {target_user_id} not found.")
            return
        USERS[target_user_id] = user_data
        if "achievements" not in USERS[target_user_id]:
            USERS[target_user_id]["achievements"] = []

    if achievement not in USERS[target_user_id]["achievements"]:
        await update.message.reply_text("User does not have this achievement.")
        return

    USERS[target_user_id]["achievements"].remove(achievement)
    await users_collection.update_one(
        {"user_id": target_user_id},
        {"$set": {"achievements": USERS[target_user_id]["achievements"]}},
        upsert=True,
    )
    await update.message.reply_text(f"Achievement removed from user {target_user_id}.")



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 Available Commands:\n"
        "/start - Start the bot\n"
        "/register - Get free coins\n"
        "/profile - View your profile\n"
        "/send - Send coins (reply to user)\n"
        "/add - Admin: add coins\n"
        "/daily - Claim daily 2,000🪙 coins reward\n"
        "/leaderboard - View top players\n"
        "/ccl <bet amount> - Start a CCL match in group (bet optional)\n"
        "/endmatch - Group admin: end ongoing CCL match in group\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(help_text)
import asyncio
import logging
import random
import uuid

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ChatMemberStatus

# --- Constants ---

BOWLER_MAP = {
    "RS": "0",
    "Bouncer": "1",
    "Yorker": "2",
    "Short": "3",
    "Slower": "4",
    "Knuckle": "6"
}

BATSMAN_OPTIONS = {"0", "1", "2", "3", "4", "6"}

GIF_EVENTS = {"0", "4", "6", "out", "50", "100"}

CCL_GIFS = {
    "0": [
        "https://media4.giphy.com/media/v1.Y2lkPTZjMDliOTUybHM4N29ib3ZkY3JxNDhjbXlkeDAycnFtYWYyM3QxajF2eXltZ2Z4ayZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/QtipHdYxYopX3W6vMs/giphy.gif",
        "https://media1.giphy.com/media/v1.Y2lkPTZjMDliOTUydGc5bm4xeDVtZGlta2hsM3d2NHUxenhmcXZud2dlcnV3NDlpazl3MCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/gyBNklO4F4Rq9zFhth/giphy.gif",
        "https://media1.giphy.com/media/v1.Y2lkPTZjMDliOTUyeHR4NTQxeW5qaHA1eTd3NzZrbHEycTM0MDBoZm4yZDc4dXhpOGxqciZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/l3V0ux4nLuuUTXyi4/giphy.gif"
    ],
    "4": [
        "https://media0.giphy.com/media/3o7btXfjIjTcU64YdG/giphy.gif",
        "https://media2.giphy.com/media/v1.Y2lkPTZjMDliOTUydHFnNzlnMm93aXhvenBmcHNwY3ZzM2d6b3FqdzFjeDcwNmVrbzNiZyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/eFgMbxVJtn31Rbrbvi/giphy.gif"
    ],
    "6": [
        "https://media3.giphy.com/media/v1.Y2lkPTZjMDliOTUya3R1eHhuaW85Mno1OTlycmJ2OXFibnA5NW5qc3Vid3djbXZkMjZ0NyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3oKIPoelgPeRrfqKlO/giphy.gif",
        "https://media1.giphy.com/media/v1.Y2lkPTZjMDliOTUyMzZnZWg2YzI5ZmVyZDJ4dWFyNWQ4bWdqbzR0b25uZTc0bWt0b2xnNCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/l0Iy7FYtsLxCrcDcI/giphy.gif" ,
        "https://media4.giphy.com/media/pbhDFQQfXRX8CTmZ4O/giphy.gif" ,
        "https://media1.giphy.com/media/v1.Y2lkPTZjMDliOTUyeTk5bmZkbzBvamlkbWZrOWRraHJpanRtMGM1bGxyMXBwYzlweWc2ZSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/B8QjfpHopIzqEU4ER4/giphy.gif"
    ],
    "out": [
        "https://media3.giphy.com/media/Wq3WRGe9N5HkSqjITT/giphy.gif",
        "https://media3.giphy.com/media/v1.Y2lkPTZjMDliOTUyaTRnd3ZleGFxMzJsMXJzN3NrajgyNDFmMW83cTlhOW9vYXJkMXZhaSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LQosRo7lJKnOZLEItQ/giphy.gif"
    ],
    "50": [
        "https://media0.giphy.com/media/v1.Y2lkPTZjMDliOTUyYm5ueGVod2Z0MHcxNTF1dWVvY2EzOXo5bGxhcXdxMWFsOWl5Z3d6YyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/LRsCOm65R3NHVwqiml/giphy.gif",
        "https://media1.giphy.com/media/v1.Y2lkPTZjMDliOTUyZnh4anZnbW1nYjllamt3eWowMndlY3BvdHlyZDdxMGsybDRrOXhjZyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/kaSjUNmLgFEw6dyhOW/giphy.gif"
    ],
    "100": [
        "https://media3.giphy.com/media/v1.Y2lkPTZjMDliOTUya3EyMXE1dzY1dXE0Y3cwMDVzb2p6c3QxbTZ0MTR6aWdvY242ZnRzdyZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/l1ugo9PYts0eHIRDG/giphy.gif",
        "https://media2.giphy.com/media/v1.Y2lkPTZjMDliOTUydTF0OGE0YjlqNjk1OHUyZmZqdzAzNHFvazg1cmRlY2pzaWxieHg0OSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ZAvn9tMUUJ3XjII6ry/giphy.gif"
    ],
}

COMMENTARY = {
    "0": [
        "😶 Dot ball! Pressure builds...",
        "🎯 Tight delivery, no run.",
        "🛑 No run, good fielding!"
    ],
    "1": [
        "🏃 Quick single taken.",
        "👟 Running hard for one.",
        "⚡ One run added."
    ],
    "2": [
        "🏃‍♂️ Two runs!",
        "💨 Good running between wickets.",
        "🔥 Two runs scored."
    ],
    "3": [
        "🏃‍♂️ Three runs! Great running!",
        "💨 Three runs added.",
        "🔥 Three runs scored."
    ],
    "4": [
        "🔥 Cracking four! What a shot!",
        "💥 The ball races to the boundary!",
        "🏏 Beautiful timing for four runs!"
    ],
    "6": [
        "🚀 Massive six! Into the stands!",
        "🎉 What a smash! Six runs!",
        "🔥 Smoked it for a sixer! 🔥"
    ],
    "out": [
        "💥 Bowled him! What a delivery!",
        "😢 Caught out! End of the innings!",
        "🚫 Out! The crowd goes silent..."
    ],
    "50": [
        "🎉 Half-century! What a milestone!",
        "🏆 50 runs scored! Keep it up!",
        "🔥 Fifty up! Player is on fire!"
    ],
    "100": [
        "🏅 CENTURY! What a magnificent innings!",
        "🎊 100 runs! A true champion!",
        "🔥 Century scored! The crowd erupts!"
    ],
}

# --- Keyboards ---

def toss_keyboard(match_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Heads", callback_data=f"ccl_toss_{match_id}_heads"),
            InlineKeyboardButton("Tails", callback_data=f"ccl_toss_{match_id}_tails"),
        ]
    ])

def batbowl_keyboard(match_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Bat 🏏", callback_data=f"ccl_batbowl_{match_id}_bat"),
            InlineKeyboardButton("Bowl ⚾", callback_data=f"ccl_batbowl_{match_id}_bowl"),
        ]
    ])

def join_cancel_keyboard(match_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Join ✅", callback_data=f"ccl_join_{match_id}")],
        [InlineKeyboardButton("Cancel ❌", callback_data=f"ccl_cancel_{match_id}")]
    ])

# --- Utility to send random GIF and commentary ---

async def send_random_event_update(context, chat_id, event_key):
    commentary_list = COMMENTARY.get(event_key, [])
    commentary = random.choice(commentary_list) if commentary_list else ""

    if event_key in GIF_EVENTS:
        gif_list = CCL_GIFS.get(event_key, [])
        gif_url = random.choice(gif_list) if gif_list else None
        if gif_url:
            await context.bot.send_animation(
                chat_id=chat_id,
                animation=gif_url,
                caption=commentary
            )
            return

    if commentary:
        await context.bot.send_message(chat_id=chat_id, text=commentary)

# --- /ccl command with optional bet amount ---

async def ccl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    ensure_user(user)

    bet_amount = 0
    if context.args:
        try:
            bet_amount = int(context.args[0])
            if bet_amount < 0:
                await update.message.reply_text("Bet amount cannot be negative.")
                return
            if bet_amount > 0 and USERS[user.id]["coins"] < bet_amount:
                await update.message.reply_text(f"You don't have enough coins to bet {bet_amount}🪙.")
                return
        except ValueError:
            await update.message.reply_text("Invalid bet amount. Usage: /ccl [bet_amount]")
            return

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("CCL matches can only be started in groups.")
        return

    if GROUP_CCL_MATCH.get(chat.id):
        await update.message.reply_text("There is already an ongoing CCL match in this group.")
        return

    if USER_CCL_MATCH.get(user.id):
        await update.message.reply_text("You are already participating in a CCL match.")
        return

    match_id = str(uuid.uuid4())
    match = {
        "match_id": match_id,
        "group_id": chat.id,
        "initiator": user.id,
        "opponent": None,
        "state": "waiting_for_opponent",
        "toss_winner": None,
        "batting_user": None,
        "bowling_user": None,
        "balls": 0,
        "score": 0,
        "innings": 1,
        "target": None,
        "bat_choice": None,
        "bowl_choice": None,
        "half_century_announced": False,
        "century_announced": False,
        "bet_amount": bet_amount,
        "message_id": None,
    }
    CCL_MATCHES[match_id] = match
    USER_CCL_MATCH[user.id] = match_id
    GROUP_CCL_MATCH[chat.id] = match_id

    bet_text = f" with a bet of {bet_amount}🪙" if bet_amount > 0 else ""
    sent_msg = await update.message.reply_text(
        f"🏏 CCL Match started by {USERS[user.id]['name']}{bet_text}!\nWaiting for an opponent to join.",
        reply_markup=join_cancel_keyboard(match_id)
    )
    match["message_id"] = sent_msg.message_id

# --- Join, Cancel, Toss, Bat/Bowl choice callbacks ---

async def ccl_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)
    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "waiting_for_opponent":
        await query.answer("Match not available to join.", show_alert=True)
        return
    if user.id == match["initiator"]:
        await query.answer("You cannot join your own match.", show_alert=True)
        return
    if match["opponent"]:
        await query.answer("Match already has an opponent.", show_alert=True)
        return
    ensure_user(user)
    if USER_CCL_MATCH.get(user.id):
        await query.answer("You are already in a CCL match.", show_alert=True)
        return
    bet_amount = match.get("bet_amount", 0)
    if bet_amount > 0 and USERS[user.id]["coins"] < bet_amount:
        await query.answer(f"You don't have enough coins to join this {bet_amount}🪙 bet match.", show_alert=True)
        return

    match["opponent"] = user.id
    match["state"] = "toss"
    USER_CCL_MATCH[user.id] = match_id
    chat_id = match["group_id"]
    message_id = match["message_id"]
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"Match between {USERS[match['initiator']]['name']} and {USERS[user.id]['name']}!\n"
            f"{USERS[match['initiator']]['name']}, choose Heads or Tails for the toss."
        ),
        reply_markup=toss_keyboard(match_id)
    )
    await query.answer()

async def ccl_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id = query.data.split("_", 2)
    match = CCL_MATCHES.get(match_id)
    if not match:
        await query.answer("Match not found or already ended.", show_alert=True)
        return
    if user.id != match["initiator"]:
        await query.answer("Only the initiator can cancel the match.", show_alert=True)
        return
    chat_id = match["group_id"]
    message_id = match.get("message_id")
    USER_CCL_MATCH[match["initiator"]] = None
    if match.get("opponent"):
        USER_CCL_MATCH[match["opponent"]] = None
    GROUP_CCL_MATCH.pop(chat_id, None)
    CCL_MATCHES.pop(match_id, None)
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="The CCL match has been cancelled by the initiator."
        )
    await query.answer()

async def ccl_toss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id, choice = query.data.split("_", 3)
    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "toss":
        await query.answer("Invalid toss state.", show_alert=True)
        return
    if user.id != match["initiator"]:
        await query.answer("Only the initiator chooses toss.", show_alert=True)
        return
    coin_result = random.choice(["heads", "tails"])
    toss_winner = match["initiator"] if choice == coin_result else match["opponent"]
    toss_loser = match["opponent"] if toss_winner == match["initiator"] else match["initiator"]
    match["toss_winner"] = toss_winner
    match["toss_loser"] = toss_loser
    match["state"] = "bat_bowl_choice"
    chat_id = match["group_id"]
    message_id = match["message_id"]
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"The coin landed on {coin_result.capitalize()}!\n"
            f"{USERS[toss_winner]['name']} won the toss! Choose to Bat or Bowl first."
        ),
        reply_markup=batbowl_keyboard(match_id)
    )
    await query.answer()

async def ccl_batbowl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    _, _, match_id, choice = query.data.split("_", 3)
    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "bat_bowl_choice":
        await query.answer("Invalid state for Bat/Bowl choice.", show_alert=True)
        return
    if user.id != match["toss_winner"]:
        await query.answer("Only toss winner can choose.", show_alert=True)
        return
    if choice == "bat":
        match["batting_user"] = match["toss_winner"]
        match["bowling_user"] = match["toss_loser"]
    else:
        match["batting_user"] = match["toss_loser"]
        match["bowling_user"] = match["toss_winner"]
    match.update({
        "state": "awaiting_inputs",
        "balls": 0,
        "score": 0,
        "innings": 1,
        "target": None,
        "bat_choice": None,
        "bowl_choice": None,
        "half_century_announced": False,
        "century_announced": False,
    })
    chat_id = match["group_id"]
    message_id = match["message_id"]

    try:
        await context.bot.send_message(
            chat_id=match["batting_user"],
            text=(
                "🏏 You're batting! Send your shot number as text (0,1,2,3,4,6)."
            )
        )
        await context.bot.send_message(
            chat_id=match["bowling_user"],
            text=(
                "⚾ You're bowling! Send your delivery as text:\n"
                "RS, Bouncer, Yorker, Short, Slower, Knuckle"
            )
        )
    except Exception as e:
        logging.error(f"Error sending DM: {e}")

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=(
            f"Match started!\n"
            f"🏏 Batter: {USERS[match['batting_user']]['name']}\n"
            f"🧤 Bowler: {USERS[match['bowling_user']]['name']}\n\n"
            f"Both players have been sent instructions via DM."
        ),
        reply_markup=None
    )
    await query.answer()

# --- Batsman and Bowler text handlers (only accept private chat messages) ---

async def batsman_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return  # Ignore non-private chats
    user = update.effective_user
    text = update.message.text.strip()
    match_id = USER_CCL_MATCH.get(user.id)
    if not match_id:
        return
    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "awaiting_inputs":
        return
    if user.id != match["batting_user"]:
        return
    if text not in BATSMAN_OPTIONS:
        await update.message.reply_text("❌ Invalid shot! Please send one of: 0,1,2,3,4,6")
        return
    if match["bat_choice"] is not None:
        await update.message.reply_text("⚠️ You already sent your shot for this ball.")
        return
    match["bat_choice"] = text
    await update.message.reply_text(f"✅ You chose: {text}")
    await remind_both_players(context, match)
    await check_both_choices_and_process(context, match)

async def bowler_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return  # Ignore non-private chats
    user = update.effective_user
    text = update.message.text.strip()
    match_id = USER_CCL_MATCH.get(user.id)
    if not match_id:
        return
    match = CCL_MATCHES.get(match_id)
    if not match or match["state"] != "awaiting_inputs":
        return
    if user.id != match["bowling_user"]:
        return

    valid_deliveries = {k.lower(): k for k in BOWLER_MAP.keys()}
    if text.lower() not in valid_deliveries:
        await update.message.reply_text(
            "❌ Invalid delivery! Please send one of:\nRS, Bouncer, Yorker, Short, Slower, Knuckle"
        )
        return

    normalized_text = valid_deliveries[text.lower()]

    if match["bowl_choice"] is not None:
        await update.message.reply_text("⚠️ You already sent your delivery for this ball.")
        return

    match["bowl_choice"] = normalized_text
    await update.message.reply_text(f"✅ You chose: {normalized_text}")
    await remind_both_players(context, match)
    await check_both_choices_and_process(context, match)

async def remind_both_players(context: ContextTypes.DEFAULT_TYPE, match):
    try:
        if match["bat_choice"] is None:
            await context.bot.send_message(
                chat_id=match["batting_user"],
                text="🏏 Please send your shot number (0,1,2,3,4,6)."
            )
        if match["bowl_choice"] is None:
            await context.bot.send_message(
                chat_id=match["bowling_user"],
                text="⚾ Please send your delivery as one of:\nRS, Bouncer, Yorker, Short, Slower, Knuckle"
            )
    except Exception as e:
        logging.error(f"Error sending reminder DM: {e}")

async def check_both_choices_and_process(context: ContextTypes.DEFAULT_TYPE, match):
    if match["bat_choice"] is not None and match["bowl_choice"] is not None:
        await process_ball(context, match)

# --- Ball processing with delays and message flow ---

async def process_ball(context: ContextTypes.DEFAULT_TYPE, match):
    chat_id = match["group_id"]
    bat_num = match["bat_choice"]
    bowl_str = match["bowl_choice"]
    bowl_num = BOWLER_MAP[bowl_str]

    match["bat_choice"] = None
    match["bowl_choice"] = None

    match["balls"] += 1
    over = (match["balls"] - 1) // 6
    ball_in_over = (match["balls"] - 1) % 6 + 1

    is_out = (bowl_num == "2" and bat_num == "2") or (bowl_num == bat_num)

    # Message flow with delays:
    await context.bot.send_message(chat_id=chat_id, text=f"Over {over + 1}")
    await context.bot.send_message(chat_id=chat_id, text=f"Ball {ball_in_over}")
    await asyncio.sleep(4)

    await context.bot.send_message(chat_id=chat_id, text=f"{USERS[match['bowling_user']]['name']} bowls a {bowl_str} ball")
    await asyncio.sleep(4)

    if is_out:
        await send_random_event_update(context, chat_id, "out")
    else:
        runs = int(bat_num)
        match["score"] += runs
        await send_random_event_update(context, chat_id, bat_num)

    await context.bot.send_message(chat_id=chat_id, text=f"Current Score: {match['score']}")

    # Handle innings and match end
    if is_out:
        if match["innings"] == 1:
            match["target"] = match["score"] + 1
            match["innings"] = 2
            match["balls"] = 0
            match["score"] = 0
            match["batting_user"], match["bowling_user"] = match["bowling_user"], match["batting_user"]
            match["half_century_announced"] = False
            match["century_announced"] = False
            await context.bot.send_message(chat_id=chat_id, text=f"Innings break! Target for second innings: {match['target']}")
        else:
            # Tie check fix:
            if match["score"] == match["target"] - 1:
                await context.bot.send_message(chat_id=chat_id, text="🤝 The match is a tie!")
                USERS[match["batting_user"]]["ties"] += 1
                USERS[match["bowling_user"]]["ties"] += 1
                await save_user(match["batting_user"])
                await save_user(match["bowling_user"])
            elif match["score"] >= match["target"]:
                await finish_match(context, match, winner=match["batting_user"])
                return
            else:
                await finish_match(context, match, winner=match["bowling_user"])
                return
            USER_CCL_MATCH[match["batting_user"]] = None
            USER_CCL_MATCH[match["bowling_user"]] = None
            GROUP_CCL_MATCH.pop(chat_id, None)
            CCL_MATCHES.pop(match["match_id"], None)
            return
    else:
        if match["score"] >= 50 and not match["half_century_announced"]:
            match["half_century_announced"] = True
            await send_random_event_update(context, chat_id, "50")
            await context.bot.send_message(chat_id=chat_id, text="🎉 Half-century! Keep it up!")
        if match["score"] >= 100 and not match["century_announced"]:
            match["century_announced"] = True
            await send_random_event_update(context, chat_id, "100")
            await context.bot.send_message(chat_id=chat_id, text="🏆 Century! Amazing innings!")

        if match["innings"] == 2 and match["score"] >= match["target"]:
            await finish_match(context, match, winner=match["batting_user"])
            return

    try:
        await context.bot.send_message(
            chat_id=match["batting_user"],
            text="🏏 Send your shot number (0,1,2,3,4,6):"
        )
        await context.bot.send_message(
            chat_id=match["bowling_user"],
            text="⚾ Send your delivery as one of:\nRS, Bouncer, Yorker, Short, Slower, Knuckle"
        )
    except Exception as e:
        logging.error(f"Error sending DM prompts: {e}")

# --- Finish match and update stats ---
# --- Finish match and update stats ---

async def finish_match(context: ContextTypes.DEFAULT_TYPE, match, winner):
    chat_id = match["group_id"]
    initiator = match["initiator"]
    opponent = match["opponent"]
    loser = initiator if winner != initiator else opponent

    bet_amount = match.get("bet_amount", 0)

    USERS[winner]["wins"] += 1
    USERS[loser]["losses"] += 1

    if bet_amount > 0:
        USERS[winner]["coins"] += bet_amount
        USERS[loser]["coins"] -= bet_amount
        await context.bot.send_message(chat_id=chat_id, text=f"💰 {bet_amount}🪙 coins transferred to {USERS[winner]['name']} as bet winnings!")

    await save_user(winner)
    await save_user(loser)

    await context.bot.send_message(chat_id=chat_id, text=f"🏆 {USERS[winner]['name']} won the match! Congratulations! 🎉")

    USER_CCL_MATCH[initiator] = None
    USER_CCL_MATCH[opponent] = None
    GROUP_CCL_MATCH.pop(chat_id, None)
    CCL_MATCHES.pop(match["match_id"], None)

# --- /endmatch command for group admins ---

import logging

logger = logging.getLogger(__name__)

async def endmatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/endmatch command invoked by user {update.effective_user.id} in chat {update.effective_chat.id}")

    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("This command can only be used in groups.")
        return

    member = await context.bot.get_chat_member(chat.id, user.id)
    logger.info(f"User {user.id} status in chat {chat.id}: {member.status}")

    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ You must be a group admin to end the match.")
        return

    match_id = GROUP_CCL_MATCH.get(chat.id)
    if not match_id:
        await update.message.reply_text("No ongoing CCL match in this group.")
        return

    match = CCL_MATCHES.get(match_id)
    if not match:
        await update.message.reply_text("Match data not found.")
        return

    USER_CCL_MATCH[match["initiator"]] = None
    if match.get("opponent"):
        USER_CCL_MATCH[match["opponent"]] = None
    GROUP_CCL_MATCH.pop(chat.id, None)
    CCL_MATCHES.pop(match_id, None)

    await update.message.reply_text("The ongoing CCL match has been ended by a group admin.")
    
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --- Configuration ---
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"  # Replace with your actual Telegram bot token

logger = logging.getLogger(__name__)

# --- Import or define all handlers and functions from Parts 1 & 2 here ---
# For example:
# from your_module import (
#     start, register, profile, send, add,
#     leaderboard, leaderboard_callback, help_command,
#     ccl_command, ccl_join_callback, ccl_cancel_callback,
#     ccl_toss_callback, ccl_batbowl_callback,
#     batsman_text_handler, bowler_text_handler, endmatch,
#     load_users
# )

def register_handlers(application):
    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("send", send))
    
    application.add_handler(CommandHandler("daily", daily))  # Added daily handler
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern=r"^leaderboard_"))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("addachievement", addachievement))
    application.add_handler(CommandHandler("removeachievement", removeachievement))
    application.add_handler(CommandHandler("profilecard", profilecard))

    # CCL commands and callbacks
    application.add_handler(CommandHandler("ccl", ccl_command))
    application.add_handler(CallbackQueryHandler(ccl_join_callback, pattern=r"^ccl_join_"))
    application.add_handler(CallbackQueryHandler(ccl_cancel_callback, pattern=r"^ccl_cancel_"))
    application.add_handler(CallbackQueryHandler(ccl_toss_callback, pattern=r"^ccl_toss_"))
    application.add_handler(CallbackQueryHandler(ccl_batbowl_callback, pattern=r"^ccl_batbowl_"))

    # Message handlers for batsman and bowler inputs (only in private chats)
    application.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, batsman_text_handler), group=1
    )
    application.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, bowler_text_handler), group=2
    )

    # Admin command to end match (group admins allowed)
    application.add_handler(CommandHandler("endmatch", endmatch))

async def on_startup(app):
    await load_users()
    logger.info("Users loaded from database. Bot is ready.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    register_handlers(app)

    app.post_init = on_startup

    logger.info("Starting bot polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

    
   

import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- HARDCODE YOUR CREDENTIALS HERE ---
POSTGRES_URL = "${{ Postgres.DATABASE_URL }}"  # <-- Replace this with your Railway Postgres URL
BOT_TOKEN = "8198938492:AAFE0CxaXVeB8cpyphp7pSV98oiOKlf5Jwo"                  # <-- Replace this with your Telegram bot token

def get_connection():
    return psycopg2.connect(POSTGRES_URL)

def create_tables():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            name TEXT,
            coins INTEGER,
            wins INTEGER,
            losses INTEGER,
            last_daily BIGINT,
            registered BOOLEAN
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Use /register to create your profile."
    )

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (id, name, coins, wins, losses, last_daily, registered) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (id) DO NOTHING",
        (user.id, user.full_name, 100, 0, 0, 0, True)
    )
    conn.commit()
    cur.close()
    conn.close()
    await update.message.reply_text(
        f"Registered {user.full_name}! Use /profile to view your stats."
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, coins, wins, losses FROM users WHERE id=%s", (user.id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        name, coins, wins, losses = row
        await update.message.reply_text(
            f"👤 {name}\nCoins: {coins}\nWins: {wins}\nLosses: {losses}"
        )
    else:
        await update.message.reply_text(
            "You are not registered yet. Use /register first."
        )

async def main():
    create_tables()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
    

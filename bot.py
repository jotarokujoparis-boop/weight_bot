import os
import random
import time

import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# =========================
# НАСТРОЙКИ
# =========================

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

COOLDOWN = 30 * 60  # 30 минут


# =========================
# ПОДКЛЮЧЕНИЕ К БАЗЕ
# =========================

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            name TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 70,
            last_roll DOUBLE PRECISION NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


# =========================
# ПОЛУЧЕНИЕ / СОЗДАНИЕ ИГРОКА
# =========================

def get_user(user_id: int, name: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT weight, last_roll FROM users WHERE user_id = %s",
        (user_id,)
    )
    result = cur.fetchone()

    if result is None:
        cur.execute(
            """
            INSERT INTO users (user_id, name, weight, last_roll)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, name, 70, 0)
        )
        conn.commit()
        cur.close()
        conn.close()
        return 70.0, 0.0

    # обновляем имя на всякий случай
    cur.execute(
        "UPDATE users SET name = %s WHERE user_id = %s",
        (name, user_id)
    )
    conn.commit()

    weight = float(result["weight"])
    last_roll = float(result["last_roll"])

    cur.close()
    conn.close()
    return weight, last_roll


# =========================
# /roll
# =========================

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    weight, last_roll = get_user(user.id, user.first_name)
    current_time = time.time()

    time_passed = current_time - last_roll

    if time_passed < COOLDOWN:
        remaining = COOLDOWN - time_passed
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)

        print(f"[ROLL] {user.first_name} ({user.id}) — кулдаун, осталось {minutes}м {seconds}с")
        await update.message.reply_text(
            f"⏳ Ты уже крутил рулетку!\n\n"
            f"Следующий ролл через: {minutes} мин. {seconds} сек."
        )
        return


    gain = round(random.uniform(-5, 10.0), 1)
    new_weight = round(weight + gain, 1)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET weight = %s, last_roll = %s
        WHERE user_id = %s
        """,
        (new_weight, current_time, user.id)
    )
    conn.commit()
    cur.close()
    conn.close()

    print(f"[ROLL] {user.first_name} ({user.id}) — выпало {gain} кг | было {weight} → стало {new_weight}")

    await update.message.reply_text(
        f"🎲 {user.first_name}, тебе выпало: {gain:.1f} кг!\n\n"
        f"⚖️ Было: {weight:.1f} кг\n"
        f"📈 Стало: {new_weight:.1f} кг\n\n"
        f"⏳ Следующий ролл через 30 минут."
    )


# =========================
# /weight
# =========================

async def show_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    weight, _ = get_user(user.id, user.first_name)

    print(f"[WEIGHT] {user.first_name} ({user.id}) — текущий вес {weight} кг")

    await update.message.reply_text(
        f"⚖️ {user.first_name}, твой текущий вес: {weight:.1f} кг"
    )


# =========================
# /top
# =========================

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[TOP] {update.effective_user.first_name} ({update.effective_user.id}) запросил топ")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT name, weight
        FROM users
        ORDER BY weight DESC
        LIMIT 10
    """)
    users = cur.fetchall()

    cur.close()
    conn.close()

    if not users:
        await update.message.reply_text("🏆 Пока никто не зарегистрирован.")
        return

    text = "🏆 ТОП-10 ПО ВЕСУ\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for index, row in enumerate(users):
        name = row["name"]
        weight = float(row["weight"])

        if index < 3:
            place = medals[index]
        else:
            place = f"{index + 1}."

        text += f"{place} {name} — {weight:.1f} кг\n"



    await update.message.reply_text(text)

# =========================
# /reset
# =========================

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET weight = 70, last_roll = 0
        WHERE user_id = %s
        """,
        (user.id,)
    )
    conn.commit()
    cur.close()
    conn.close()

    print(f"[RESET] {user.first_name} ({user.id}) сбросил вес")

    await update.message.reply_text(
        f"♻️ {user.first_name}, твой вес сброшен на 70.0 кг.\n"
        f"Кулдаун тоже сброшен."
    )


# =========================
# ЗАПУСК
# =========================

def main():
    if not TOKEN or not DATABASE_URL:
        raise ValueError("Не заданы BOT_TOKEN или DATABASE_URL")

    init_db()  # создаём таблицу при запуске

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("weight", show_weight))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("reset", reset))

    print("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
import logging
import os
import psycopg2
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

API_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)

# 🔐 ADMIN (faqat ID orqali)
ADMINS = [123456789]

def is_admin(user_id):
    return user_id in ADMINS

# 🗄 DB CONNECT
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    name TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS money (
    user_id BIGINT,
    naqd BIGINT DEFAULT 0,
    karta BIGINT DEFAULT 0
)
""")
conn.commit()

# 🔘 BUTTON
kb = ReplyKeyboardMarkup(resize_keyboard=True)
kb.add("➕ Pul qo‘shish")
kb.add("📊 Hisob", "🏆 Reyting", "📈 Grafik")

user_state = {}

# 🚀 START (ism so‘raydi)
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Sizga ruxsat yo‘q")
        return
    
    cur.execute("SELECT * FROM users WHERE user_id=%s", (message.from_user.id,))
    if not cur.fetchone():
        await message.answer("👤 Ismingizni kiriting:")
        user_state[message.from_user.id] = "name"
    else:
        await message.answer("Xush kelibsiz!", reply_markup=kb)

@dp.message_handler(lambda m: m.from_user.id in user_state and user_state[m.from_user.id]=="name")
async def save_name(message: types.Message):
    cur.execute("INSERT INTO users VALUES (%s,%s)", (message.from_user.id, message.text))
    cur.execute("INSERT INTO money(user_id) VALUES (%s)", (message.from_user.id,))
    conn.commit()

    user_state.pop(message.from_user.id)
    await message.answer("✅ Saqlandi", reply_markup=kb)

# ➕ PUL QO‘SHISH
@dp.message_handler(lambda m: m.text == "➕ Pul qo‘shish")
async def add_start(message: types.Message):
    user_state[message.from_user.id] = "amount"
    await message.answer("💵 Summani yozing:")

@dp.message_handler(lambda m: m.from_user.id in user_state and user_state[m.from_user.id]=="amount")
async def get_amount(message: types.Message):
    try:
        user_state[message.from_user.id] = int(message.text)

        kb2 = ReplyKeyboardMarkup(resize_keyboard=True)
        kb2.add("💵 Naqd", "💳 Karta")

        await message.answer("Turini tanlang:", reply_markup=kb2)
    except:
        await message.answer("❌ Son yoz")

@dp.message_handler(lambda m: m.text in ["💵 Naqd", "💳 Karta"])
async def save_money(message: types.Message):
    if message.from_user.id not in user_state:
        return
    
    amount = user_state[message.from_user.id]
    field = "naqd" if "Naqd" in message.text else "karta"

    cur.execute(f"UPDATE money SET {field} = {field} + %s WHERE user_id=%s",
                (amount, message.from_user.id))
    conn.commit()

    user_state.pop(message.from_user.id)

    await message.answer("✅ Qo‘shildi", reply_markup=kb)

# 📊 HISOB
@dp.message_handler(lambda m: m.text == "📊 Hisob")
async def stats(message: types.Message):
    cur.execute("""
    SELECT u.name, m.naqd, m.karta, (m.naqd+m.karta) as total
    FROM users u JOIN money m ON u.user_id=m.user_id
    """)
    rows = cur.fetchall()

    text = "📊 HISOB:\n\n"
    total = 0

    for name, naqd, karta, t in rows:
        total += t
        text += f"👤 {name}\n💵 {naqd} | 💳 {karta} | 🔹 {t}\n\n"

    text += f"💰 UMUMIY: {total}"

    await message.answer(text)

# 🏆 REYTING
@dp.message_handler(lambda m: m.text == "🏆 Reyting")
async def rating(message: types.Message):
    cur.execute("""
    SELECT u.name, (m.naqd+m.karta) as total
    FROM users u JOIN money m ON u.user_id=m.user_id
    ORDER BY total DESC
    """)
    rows = cur.fetchall()

    text = "🏆 REYTING:\n\n"
    for i, (name, total) in enumerate(rows, 1):
        text += f"{i}. {name} — {total}\n"

    await message.answer(text)

# 📈 GRAFIK
@dp.message_handler(lambda m: m.text == "📈 Grafik")
async def chart(message: types.Message):
    cur.execute("""
    SELECT u.name, (m.naqd+m.karta)
    FROM users u JOIN money m ON u.user_id=m.user_id
    """)
    rows = cur.fetchall()

    names = [r[0] for r in rows]
    values = [r[1] for r in rows]

    plt.figure(figsize=(8,5))
    plt.bar(names, values)
    plt.title("Pul yig‘ilishi (Saudiya sayohati)")
    plt.xticks(rotation=30)

    plt.savefig("chart.png")
    plt.close()

    await message.answer_photo(open("chart.png","rb"))

# RUN
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

import logging
import os
import psycopg2
import matplotlib.pyplot as plt
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

API_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

# 🔐 Admin va ruxsatli foydalanuvchilar
ADMINS = [6734269605, 7652431781]          # adminlar ID
PERMITTED_USERS = [7652431781, 5914041389, 5479874937, 7652431781, 6734269605] # pul qo‘sha oladiganlar

# 🗄 DB
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

# Table yaratish
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    name TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS money (
    user_id BIGINT PRIMARY KEY,
    naqd BIGINT DEFAULT 0,
    karta BIGINT DEFAULT 0
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS limits (
    total BIGINT
)
""")
conn.commit()

# Tugmalar
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("➕ Pul qo‘shish", "📊 Hisob")
main_kb.add("🏆 Reyting", "📈 Grafik", "💰 Qolgan limit")

user_state = {}

# ----- START -----
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in PERMITTED_USERS + ADMINS:
        await message.answer("❌ Sizda ruxsat yo‘q")
        return

    # Ism so‘rash
    cur.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    if not cur.fetchone():
        await message.answer("👤 Ismingizni kiriting:")
        user_state[user_id] = "name"
        return

    # Tugmalar tayyorlash
    kb = main_kb
    await message.answer("Xush kelibsiz!", reply_markup=kb)

    # Admin panel
    if user_id in ADMINS:
        admin_kb = InlineKeyboardMarkup(row_width=1)
        admin_kb.add(
            InlineKeyboardButton("➕ Foydalanuvchi qo‘shish", callback_data="add_user"),
            InlineKeyboardButton("💰 Limit o‘rnatish", callback_data="set_limit"),
            InlineKeyboardButton("📊 Jami pul", callback_data="total_money")
        )
        await message.answer("🔹 Admin panel:", reply_markup=admin_kb)

# ----- NAME SAVE -----
@dp.message_handler(lambda m: m.from_user.id in user_state and user_state[m.from_user.id]=="name")
async def save_name(message: types.Message):
    cur.execute("INSERT INTO users VALUES (%s,%s)", (message.from_user.id, message.text))
    cur.execute("INSERT INTO money(user_id) VALUES (%s)", (message.from_user.id,))
    conn.commit()
    user_state.pop(message.from_user.id)
    await message.answer("✅ Saqlandi", reply_markup=main_kb)

# ----- ADMIN SET LIMIT -----
@dp.message_handler(commands=['setlimit'])
async def set_limit_cmd(message: types.Message):
    if message.from_user.id not in ADMINS:
        await message.answer("❌ Siz admin emassiz")
        return
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.answer("❌ Format: /setlimit 5000000")
            return
        limit = int(args[1])
        cur.execute("SELECT * FROM limits")
        if cur.fetchone():
            cur.execute("UPDATE limits SET total=%s", (limit,))
        else:
            cur.execute("INSERT INTO limits(total) VALUES (%s)", (limit,))
        conn.commit()
        await message.answer(f"✅ Limit o‘rnatildi: {limit}")
    except:
        await message.answer("❌ Faqat son yozing. Misol: /setlimit 5000000")

# ----- PUL QO‘SHISH -----
def get_remaining():
    cur.execute("SELECT total FROM limits")
    row = cur.fetchone()
    total_limit = row[0] if row else None
    if not total_limit:
        return None, None
    cur.execute("SELECT SUM(naqd+karta) FROM money")
    current_total = cur.fetchone()[0] or 0
    remaining = total_limit - current_total
    return total_limit, remaining

@dp.message_handler(lambda m: m.text=="➕ Pul qo‘shish")
async def add_start(message: types.Message):
    if message.from_user.id not in PERMITTED_USERS:
        await message.answer("❌ Siz pul qo‘sha olmaysiz")
        return
    # Limitni tekshirish
    _, remaining = get_remaining()
    if remaining == 0:
        await message.answer("⚠️ Limitga yetildi! Pul qo‘shish mumkin emas")
        return
    user_state[message.from_user.id] = "amount"
    await message.answer("💵 Summani yozing:")

@dp.message_handler(lambda m: m.from_user.id in user_state and user_state[m.from_user.id]=="amount")
async def get_amount(message: types.Message):
    try:
        amount = int(message.text)
        user_state[message.from_user.id] = amount
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("💵 Naqd", "💳 Karta")
        await message.answer("Turini tanlang:", reply_markup=kb)
    except:
        await message.answer("❌ Faqat son yozing")

@dp.message_handler(lambda m: m.text in ["💵 Naqd", "💳 Karta"])
async def save_money(message: types.Message):
    if message.from_user.id not in user_state:
        return
    amount = user_state[message.from_user.id]
    field = "naqd" if "Naqd" in message.text else "karta"

    # Limitni tekshirish
    total_limit, remaining = get_remaining()
    if total_limit is not None and amount > remaining:
        await message.answer(f"⚠️ Siz {remaining} dan ko‘p qo‘sha olmaysiz!")
        return

    cur.execute(f"UPDATE money SET {field} = {field} + %s WHERE user_id=%s", (amount, message.from_user.id))
    conn.commit()
    user_state.pop(message.from_user.id)

    # Adminlarga xabar
    cur.execute("SELECT name FROM users WHERE user_id=%s", (message.from_user.id,))
    user_name = cur.fetchone()[0]
    for admin_id in ADMINS:
        if admin_id != message.from_user.id:
            await bot.send_message(admin_id, f"👤 {user_name} {amount} qo‘shdi ({field})")

    # Qolgan limitni ko‘rsatish
    _, remaining = get_remaining()
    await message.answer(f"✅ Qo‘shildi: {amount} ({field})\n💰 Qolgan limit: {remaining}", reply_markup=main_kb)

# ----- HISOB -----
@dp.message_handler(lambda m: m.text=="📊 Hisob")
async def stats(message: types.Message):
    cur.execute("SELECT u.name, m.naqd, m.karta, (m.naqd+m.karta) as total FROM users u JOIN money m ON u.user_id=m.user_id")
    rows = cur.fetchall()
    text = "📊 HISOB:\n\n"
    total = 0
    for name, naqd, karta, t in rows:
        total += t
        text += f"👤 {name}\n💵 {naqd} | 💳 {karta} | 🔹 {t}\n\n"
    text += f"💰 UMUMIY: {total}"
    await message.answer(text)

# ----- REYTING + GRAFIK -----
@dp.message_handler(lambda m: m.text=="🏆 Reyting")
async def rating(message: types.Message):
    cur.execute("SELECT u.name, m.naqd, m.karta FROM users u JOIN money m ON u.user_id=m.user_id ORDER BY (m.naqd+m.karta) DESC")
    rows = cur.fetchall()
    names = [r[0] for r in rows]
    naqd_vals = [r[1] for r in rows]
    karta_vals = [r[2] for r in rows]
    plt.figure(figsize=(8,5))
    plt.bar(names, naqd_vals, label='Naqd', color='skyblue')
    plt.bar(names, karta_vals, bottom=naqd_vals, label='Karta', color='orange')
    plt.title("Pul qo‘shganlar (Naqd/Karta)")
    plt.xticks(rotation=30)
    plt.legend()
    plt.tight_layout()
    plt.savefig("chart.png")
    plt.close()
    text = "🏆 REYTING:\n\n"
    for i, r in enumerate(rows,1):
        total = r[1]+r[2]
        text += f"{i}. {r[0]} — {total} (💵{r[1]} | 💳{r[2]})\n"
    await message.answer(text)
    await message.answer_photo(open("chart.png","rb"))

# ----- GRAFIK -----
@dp.message_handler(lambda m: m.text=="📈 Grafik")
async def chart(message: types.Message):
    cur.execute("SELECT u.name, m.naqd, m.karta FROM users u JOIN money m ON u.user_id=m.user_id")
    rows = cur.fetchall()
    names = [r[0] for r in rows]
    naqd_vals = [r[1] for r in rows]
    karta_vals = [r[2] for r in rows]
    plt.figure(figsize=(8,5))
    plt.bar(names, naqd_vals, label='Naqd', color='skyblue')
    plt.bar(names, karta_vals, bottom=naqd_vals, label='Karta', color='orange')
    plt.title("Pul qo‘shganlar (Naqd/Karta)")
    plt.xticks(rotation=30)
    plt.legend()
    plt.tight_layout()
    plt.savefig("chart.png")
    plt.close()
    await message.answer_photo(open("chart.png","rb"))

# ----- QOLGAN LIMIT -----
@dp.message_handler(lambda m: m.text=="💰 Qolgan limit")
async def remaining_limit(message: types.Message):
    total_limit, remaining = get_remaining()
    if total_limit is None:
        await message.answer("❌ Limit hali belgilanmagan")
        return
    await message.answer(f"💰 Qolgan limit: {remaining}")

# ----- ADMIN CALLBACKS -----
@dp.callback_query_handler(lambda c: c.data in ["add_user","set_limit","total_money"])
async def process_admin_callback(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("❌ Siz admin emassiz", show_alert=True)
        return

    if callback.data == "add_user":
        await bot.send_message(callback.from_user.id, "Foydalanuvchi ID sini kiriting: /adduser 123456789")
    elif callback.data == "set_limit":
        await bot.send_message(callback.from_user.id, "Limitni kiriting: /setlimit 5000000")
    elif callback.data == "total_money":
        cur.execute("SELECT SUM(naqd+karta) FROM money")
        total = cur.fetchone()[0] or 0
        await bot.send_message(callback.from_user.id, f"💰 Jami yig‘ilgan pul: {total}")
    await callback.answer()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

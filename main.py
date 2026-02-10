import os
import telebot
from telebot import types
import math
import threading
import random
import time
import sqlite3

from dotenv import load_dotenv
load_dotenv()

API_TOKEN = os.environ.get("TELEGRAM_API_TOKEN")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "/Ibrahim2189/ly")
DATABASE_NAME = "bot_db.sqlite3"

# إعداد قاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة
def db_connection():
    return sqlite3.connect(DATABASE_NAME)

def initialize_db():
    conn = db_connection()
    cursor = conn.cursor()
    # جدول المستخدمين
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        role TEXT,
        gender TEXT,
        balance REAL DEFAULT 0,
        ratings TEXT DEFAULT '',
        admin INTEGER DEFAULT 0
    )
    """)
    # حالة السائق
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS driver_status (
        driver_id INTEGER PRIMARY KEY,
        status TEXT,
        lat REAL,
        lon REAL
    )
    """)
    # الرحلات
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        passenger_id INTEGER,
        passenger_name TEXT,
        gender TEXT,
        start_lat REAL,
        start_lon REAL,
        destination TEXT,
        price REAL,
        driver_id INTEGER
    )
    """)
    conn.commit()
    conn.close()

initialize_db()

bot = telebot.TeleBot(API_TOKEN)

# =================== وظائف مساعدة ===================

def get_user(telegram_id):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, username, role, gender, balance, ratings, admin FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        ratings = list(map(int, filter(None, row[5].split(','))))
        return {
            "telegram_id": row[0],
            "username": row[1],
            "role": row[2],
            "gender": row[3],
            "balance": row[4],
            "ratings": ratings,
            "admin": bool(row[6])
        }
    return None

def set_user(telegram_id, username, role, gender=None, balance=0, admin=0):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO users (telegram_id, username, role, gender, balance, admin)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (telegram_id, username, role, gender, balance, admin))
    conn.commit()
    conn.close()

def update_user_field(telegram_id, field, value):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET {field} = ? WHERE telegram_id = ?", (value, telegram_id))
    conn.commit()
    conn.close()

def add_rating(driver_id, rating):
    user = get_user(driver_id)
    ratings = user["ratings"] if user else []
    ratings.append(rating)
    update_user_field(driver_id, "ratings", ",".join(map(str, ratings)))

def get_driver_status(driver_id):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, lat, lon FROM driver_status WHERE driver_id = ?", (driver_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"status": row[0], "location": (row[1], row[2])}
    return None

def set_driver_status(driver_id, status, lat=None, lon=None):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO driver_status (driver_id, status, lat, lon)
        VALUES (?, ?, ?, ?)
    """, (driver_id, status, lat, lon))
    conn.commit()
    conn.close()

def get_all_available_drivers(gender, min_balance):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.driver_id, d.lat, d.lon FROM driver_status d
        JOIN users u ON d.driver_id = u.telegram_id
        WHERE d.status = 'متوفر' AND u.gender = ? AND u.balance >= ?
    """, (gender, min_balance))
    drivers = cur.fetchall()
    conn.close()
    return drivers

def get_trip_for_driver(driver_id):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, passenger_id FROM trips WHERE driver_id = ?", (driver_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"trip_id": row[0], "passenger_id": row[1]}
    return None

def remove_trip(trip_id):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
    conn.commit()
    conn.close()

def get_trips():
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips")
    trips = cur.fetchall()
    conn.close()
    return trips

def get_trip_by_passenger(passenger_id):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE passenger_id = ?", (passenger_id,))
    trip = cur.fetchone()
    conn.close()
    return trip

def add_trip(trip):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trips (passenger_id, passenger_name, gender, start_lat, start_lon, destination, price, driver_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trip["passenger_id"], trip["passenger_name"], trip["gender"],
        trip["start"][0], trip["start"][1], trip["destination"], trip["price"], trip.get("driver_id")
    ))
    conn.commit()
    conn.close()

def update_trip_driver(trip_id, driver_id):
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE trips SET driver_id = ? WHERE id = ?", (driver_id, trip_id))
    conn.commit()
    conn.close()

def get_user_by_username(username):
    username = username.lstrip('@').lower()
    conn = db_connection()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id, username, role, gender, balance, ratings FROM users WHERE LOWER(username) = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if row:
        ratings = list(map(int, filter(None, row[5].split(','))))
        return {
            "telegram_id": row[0],
            "username": row[1],
            "role": row[2],
            "gender": row[3],
            "balance": row[4],
            "ratings": ratings
        }
    return None

def distance(loc1, loc2):
    lat1, lon1 = loc1
    lat2, lon2 = loc2
    return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)

def gps_update_loop(driver_id):
    while True:
        status_obj = get_driver_status(driver_id)
        if not status_obj or status_obj["status"] != "متوفر":
            break
        lat, lon = status_obj["location"]
        lat += random.uniform(-0.0005, 0.0005)
        lon += random.uniform(-0.0005, 0.0005)
        set_driver_status(driver_id, "متوفر", lat, lon)
        time.sleep(5)

# =================== البوت ===================

@bot.message_handler(commands=['start'])
def start(message):
    telegram_id = message.from_user.id
    username = message.from_user.username or ""
    user = get_user(telegram_id)
    if user:
        bot.send_message(message.chat.id, f"مرحبا {username}! أنت مسجل كـ {user['role']}")
        show_menu(message, user['role'])
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('سائق 🚖', 'راكب 🧍', 'أدمن 🔑')
        bot.send_message(message.chat.id, "اختر دورك:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ['سائق 🚖','راكب 🧍','أدمن 🔑'])
def set_role(message):
    telegram_id = message.from_user.id
    username = message.from_user.username or ""
    role = message.text.split()[0]
    if role == "أدمن":
        msg = bot.send_message(message.chat.id, "ادخل الأمر السري للأدمن:")
        bot.register_next_step_handler(msg, check_admin_password)
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('ذكر 👨', 'أنثى 👩')
        msg = bot.send_message(message.chat.id, "اختر جنسك:", reply_markup=markup)
        bot.register_next_step_handler(msg, set_gender, role, username)

def check_admin_password(message):
    telegram_id = message.from_user.id
    username = message.from_user.username or ""
    if message.text == ADMIN_PASSWORD:
        # الأدمن من ID ويخزن كـ admin=1
        set_user(telegram_id, username, "أدمن", admin=1)
        bot.send_message(message.chat.id, "✅ تم تسجيلك كأدمن!")
        show_menu(message, "أدمن")
    else:
        bot.send_message(message.chat.id, "❌ كلمة السر خاطئة! لا يمكنك الدخول كأدمن.")

def set_gender(message, role, username):
    gender = message.text.split()[0]
    telegram_id = message.from_user.id
    if gender not in ["ذكر", "أنثى"]:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('ذكر 👨', 'أنثى 👩')
        msg = bot.send_message(message.chat.id, "اختر جنس صالح:", reply_markup=markup)
        bot.register_next_step_handler(msg, set_gender, role, username)
        return
    initial_balance = 10 if role == "سائق" else 0
    set_user(telegram_id, username, role, gender, initial_balance)
    if role == "سائق":
        bot.send_message(message.chat.id, "🎉 مرحبا بك كسائق جديد!\nلقد تم منحك 10 دينار هدية كمكافأة تسجيل.")
    bot.send_message(message.chat.id, f"تم تسجيلك كـ {role} وجنسك {gender}")
    show_menu(message, role)

def show_menu(message, role):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if role == 'سائق':
        markup.add('متوفر ✅', 'مشغول ⛔', 'عرض الرصيد 💰', 'شحن رصيد 📲')
        bot.send_message(message.chat.id, "اختر حالتك أو اعرض رصيدك:", reply_markup=markup)
    elif role == 'راكب':
        markup.add('طلب رحلة 🛺')
        bot.send_message(message.chat.id, "اختر ما تريد:", reply_markup=markup)
    elif role == 'أدمن':
        markup.add('عرض بيانات مستخدم 👤', 'إضافة رصيد ➕', 'خصم رصيد ➖')
        bot.send_message(message.chat.id, "قائمة الأدمن:", reply_markup=markup)

@bot.message_handler(func=lambda message: get_user(message.from_user.id) and get_user(message.from_user.id).get("role") == 'سائق')
def driver_actions(message):
    telegram_id = message.from_user.id
    text = message.text
    user = get_user(telegram_id)
    if not user:
        return
    if text == 'متوفر ✅':
        lat = random.uniform(32, 33)
        lon = random.uniform(13, 15)
        set_driver_status(telegram_id, 'متوفر', lat, lon)
        bot.send_message(message.chat.id, "📍 أنت الآن متوفر! يتم تحديث موقعك تلقائيًا.")
        threading.Thread(target=gps_update_loop, args=(telegram_id,), daemon=True).start()
    elif text == 'مشغول ⛔':
        set_driver_status(telegram_id, 'مشغول')
        bot.send_message(message.chat.id, "⛔ أنت الآن مشغول.")
    elif text == 'عرض الرصيد 💰':
        bot.send_message(message.chat.id, f"💵 رصيدك الحالي: {user['balance']} دينار")
    elif text == 'شحن رصيد 📲':
        bot.send_message(message.chat.id, "🔗 للتواصل شحن الرصيد عبر واتساب: https://wa.me/218923128567")
    elif text in ['/قبول ✅','/رفض ❌']:
        handle_trip_response(telegram_id, text)
    elif text.startswith('تم استلام الراكب 🚶'):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('تم توصيل الراكب 🏁')
        bot.send_message(message.chat.id, "اضغط عند توصيل الراكب:", reply_markup=markup)
    elif text.startswith('تم توصيل الراكب 🏁'):
        trip = get_trip_for_driver(telegram_id)
        if trip:
            new_balance = float(user["balance"]) - 2
            update_user_field(telegram_id, "balance", new_balance)
            bot.send_message(message.chat.id, f"✅ تم خصم 2 دينار كعمولة.\n💵 رصيدك الحالي: {new_balance} دينار")
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('1⭐','2⭐','3⭐','4⭐','5⭐')
            bot.send_message(trip["passenger_id"], "🔔 تم انتهاء الرحلة! الرجاء تقييم السائق:", reply_markup=markup)
            bot.register_next_step_handler_by_chat_id(trip["passenger_id"], lambda msg: store_rating(telegram_id, msg))
            remove_trip(trip["trip_id"])
            show_menu(message, 'سائق')
    else:
        show_menu(message, 'سائق')

def store_rating(driver_id, message):
    try:
        rating = int(message.text[0])
        if rating<1 or rating>5: raise ValueError
    except:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('1⭐','2⭐','3⭐','4⭐','5⭐')
        msg = bot.send_message(message.chat.id, "ادخل رقم صالح من 1 إلى 5:", reply_markup=markup)
        bot.register_next_step_handler(msg, lambda m: store_rating(driver_id, m))
        return
    add_rating(driver_id, rating)
    user = get_user(driver_id)
    avg = sum(user["ratings"])/len(user["ratings"]) if user["ratings"] else 0
    bot.send_message(message.chat.id, f"شكراً لتقييمك! ⭐ متوسط تقييم السائق: {avg:.1f}")
    bot.send_message(driver_id, f"🔔 تم تقييمك: {rating}⭐\n⭐ متوسط تقييمك الآن: {avg:.1f}")

@bot.message_handler(func=lambda message: get_user(message.from_user.id) and get_user(message.from_user.id).get("role") == 'راكب')
def passenger_actions(message):
    telegram_id = message.from_user.id
    text = message.text
    if text == 'طلب رحلة 🛺':
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton('أرسل موقعي 📍', request_location=True))
        bot.send_message(message.chat.id, "شارك موقعك لتحديد موقع الانطلاق:", reply_markup=markup)
    else:
        show_menu(message, 'راكب')

@bot.message_handler(content_types=['location'])
def location_handler(message):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    if not user or user['role'] != 'راكب':
        return
    location = (message.location.latitude, message.location.longitude)
    msg = bot.send_message(message.chat.id, "أدخل الوجهة (نص):")
    bot.register_next_step_handler(msg, get_destination_with_location, location)

def get_destination_with_location(message, start_location):
    telegram_id = message.from_user.id
    msg = bot.send_message(message.chat.id, "أدخل السعر بالأرقام:")
    bot.register_next_step_handler(msg, get_price_with_location, start_location, message.text)

def get_price_with_location(message, start_location, destination):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    try:
        price = float(message.text)
    except:
        msg = bot.send_message(message.chat.id, "ادخل رقم صالح للسعر:")
        bot.register_next_step_handler(msg, get_price_with_location, start_location, destination)
        return
    trip = {
        "passenger_id": telegram_id,
        "passenger_name": message.from_user.first_name,
        "gender": user["gender"],
        "start": start_location,
        "destination": destination,
        "price": price,
        "driver_id": None
    }
    add_trip(trip)
    bot.send_message(message.chat.id, "🛺 تم ارسال الرحلة! في انتظار أقرب سائق متاح ومتوافق.")
    assign_driver(trip)

def assign_driver(trip):
    min_dist = float('inf')
    selected_driver = None
    drivers = get_all_available_drivers(trip["gender"], 2)
    for driver in drivers:
        driver_id, lat, lon = driver
        d = distance((lat, lon), trip["start"])
        if d < min_dist:
            min_dist = d
            selected_driver = driver_id
    if selected_driver:
        # ضبط السائق في الرحلة
        conn = db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE trips SET driver_id = ? WHERE passenger_id = ?
        """, (selected_driver, trip["passenger_id"]))
        conn.commit()
        conn.close()
        lat, lon = trip["start"]
        link = f"https://www.google.com/maps?q={lat},{lon}"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('/قبول ✅','/رفض ❌')
        bot.send_message(selected_driver, f"🚨 رحلة جديدة:\nالراكب: {trip['passenger_name']}\nالموقع: {link}\nالوجهة: {trip['destination']}\nالسعر: {trip['price']} دينار", reply_markup=markup)
    else:
        bot.send_message(trip["passenger_id"], "❌ لا يوجد سائق متوفر حاليًا، حاول لاحقًا.")

def handle_trip_response(driver_id, response):
    trip = get_trip_for_driver(driver_id)
    if not trip:
        bot.send_message(driver_id, "❌ لا توجد رحلة لتتعامل معها.")
        return
    if response == '/قبول ✅':
        bot.send_message(driver_id, "✅ لقد قبلت الرحلة! سيتم تحديث الرصيد بعد انتهاء الرحلة.")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('تم استلام الراكب 🚶')
        bot.send_message(driver_id, "اضغط عند استلام الراكب:", reply_markup=markup)
        passenger_id = trip["passenger_id"]
        user = get_user(driver_id)
        bot.send_message(passenger_id, f"🚖 سائق {user['gender']} قبل الرحلة وسيصل إليك قريبًا.")
    elif response == '/رفض ❌':
        bot.send_message(driver_id, "❌ لقد رفضت الرحلة.")
        conn = db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE trips SET driver_id = NULL WHERE id = ?", (trip["trip_id"],))
        conn.commit()
        conn.close()
        assign_driver({
            "passenger_id": trip["passenger_id"],
            "passenger_name": "",
            "gender": "",
            "start": (0,0),
            "destination": "",
            "price": 0
        })

@bot.message_handler(func=lambda message: get_user(message.from_user.id) and get_user(message.from_user.id).get("role") == 'أدمن')
def admin_actions(message):
    user = get_user(message.from_user.id)
    if not user or not user.get("admin"):
        bot.send_message(message.chat.id, "ليس لديك صلاحية الأدمن.")
        return
    text = message.text
    if text == 'عرض بيانات مستخدم 👤':
        msg = bot.send_message(message.chat.id, "ادخل @username:")
        bot.register_next_step_handler(msg, admin_show_user)
    elif text == 'إضافة رصيد ➕':
        msg = bot.send_message(message.chat.id, "ادخل @username للسائق:")
        bot.register_next_step_handler(msg, admin_add_balance)
    elif text == 'خصم رصيد ➖':
        msg = bot.send_message(message.chat.id, "ادخل @username للسائق:")
        bot.register_next_step_handler(msg, admin_subtract_balance)
    else:
        show_menu(message, 'أدمن')

def admin_show_user(message):
    username = message.text.strip().lstrip('@').lower()
    user = get_user_by_username(username)
    if user:
        balance = user.get("balance", 0)
        avg = sum(user.get("ratings", []))/len(user.get("ratings", [])) if user.get("ratings") else 0
        bot.send_message(message.chat.id, f"👤 بيانات المستخدم:\nدور: {user['role']}\nجنس: {user.get('gender', 'غير محدد')}\nرصيد: {balance}\nمتوسط تقييم: {avg:.1f}")
    else:
        bot.send_message(message.chat.id, "❌ المستخدم غير موجود بالـ username.")
    show_menu(message, 'أدمن')

def admin_add_balance(message):
    username = message.text.strip().lstrip('@').lower()
    user = get_user_by_username(username)
    if user:
        msg = bot.send_message(message.chat.id, "ادخل قيمة الرصيد المراد إضافتها:")
        bot.register_next_step_handler(msg, lambda m: admin_add_balance_value(user["telegram_id"], m))
    else:
        bot.send_message(message.chat.id, "❌ المستخدم غير موجود بالـ username.")
        show_menu(message, 'أدمن')

def admin_add_balance_value(user_id, message):
    try:
        amount = float(message.text)
        user = get_user(user_id)
        new_balance = float(user["balance"]) + amount
        update_user_field(user_id, "balance", new_balance)
        bot.send_message(user_id, f"💰 تم إضافة {amount} دينار لرصيدك. الرصيد الجديد: {new_balance}")
        bot.send_message(message.chat.id, f"✅ تم إضافة {amount} دينار للمستخدم. الرصيد الجديد: {new_balance}")
    except:
        bot.send_message(message.chat.id, "❌ قيمة غير صالحة.")
    show_menu(message, 'أدمن')

def admin_subtract_balance(message):
    username = message.text.strip().lstrip('@').lower()
    user = get_user_by_username(username)
    if user:
        msg = bot.send_message(message.chat.id, "ادخل قيمة الرصيد المراد خصمها:")
        bot.register_next_step_handler(msg, lambda m: admin_subtract_balance_value(user["telegram_id"], m))
    else:
        bot.send_message(message.chat.id, "❌ المستخدم غير موجود بالـ username.")
        show_menu(message, 'أدمن')

def admin_subtract_balance_value(user_id, message):
    try:
        amount = float(message.text)
        user = get_user(user_id)
        new_balance = float(user["balance"]) - amount
        update_user_field(user_id, "balance", new_balance)
        bot.send_message(user_id, f"💸 تم خصم {amount} دينار من رصيدك. الرصيد الجديد: {new_balance}")
        bot.send_message(message.chat.id, f"✅ تم خصم {amount} دينار من المستخدم. الرصيد الجديد: {new_balance}")
    except:
        bot.send_message(message.chat.id, "❌ قيمة غير صالحة.")
    show_menu(message, 'أدمن')

bot.infinity_polling()
import asyncio
import logging
import os
import io
import re
import sys

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.filters.state import StateFilter
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile, InputMediaPhoto)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties

from barcode import Code128
from barcode.writer import ImageWriter

logging.basicConfig(level=logging.INFO)

API_TOKEN = '7738742994:AAF2IcZJRjBzd1KnfpDpxeF1tyf-bNq7jkA'
OWNER_ID = 958096246, 688755430
ADMINS = {958096246, 688755430}

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

class AddAktsiya(StatesGroup):
    waiting_for_title = State()
    waiting_for_desc = State()

class AddVacancy(StatesGroup):
    waiting_for_position = State()
    waiting_for_location = State()

class Registration(StatesGroup):
    waiting_for_phone = State()
    waiting_for_name = State()

class Order(StatesGroup):
    choosing_branch = State()

aktsii = []
vacancies = []
user_feedback_waiting = set()
registered_users = {}
show_aktsii = True  # [cfg]
show_vacancies = True  # [cfg]

#-----------------------------------------------------------

def update_config_flag(key: str, value: bool):
    file_path = sys.argv[0]  # текущий скрипт
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = rf"{key}\s*=\s*(True|False)\s*# \[cfg\]"
    new_line = f"{key} = {value}  # [cfg]"
    new_content = re.sub(pattern, new_line, content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

#-----------------------------------------------------------

def get_user_keyboard():
    global show_aktsii, show_vacancies
    row1 = [KeyboardButton(text="📖 Меню")]
   # if show_aktsii:
    #    row1.append(KeyboardButton(text="🔥 Акції та знижки"))
    #if show_vacancies:
     #   row1.append(KeyboardButton(text="📄 Вакансії"))
    keyboard = [
        row1,
        [KeyboardButton(text="😎 Ми Онлайн"), KeyboardButton(text="📍 Знайти нас")],
        [KeyboardButton(text="💌 Відгук і Пропозиція"), KeyboardButton(text="📞 Замовити")]
    ]

    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=keyboard)

def get_admin_keyboard():
    base_kb = get_user_keyboard()  # каждый раз пересоздаёт
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[*base_kb.keyboard, [KeyboardButton(text="🔧 Адмін-панель")]]
    )

#-----------------------------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in registered_users:
        kb = get_admin_keyboard() if user_id in ADMINS else get_user_keyboard()
        await message.answer(
            f"👋 З поверненням, {registered_users[user_id]['name']}!",
            reply_markup=kb
        )
        return

    kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True,
        keyboard=[
            [KeyboardButton(text="📱 Надати номер телефону", request_contact=True)]
        ]
    )
    await message.answer("Щоб продовжити, поділіться номером телефону:", reply_markup=kb)
    await state.set_state(Registration.waiting_for_phone)

@dp.message(Registration.waiting_for_phone, F.contact)
async def handle_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await message.answer("Дякуємо! Тепер введіть ваше ім'я:")
    await state.set_state(Registration.waiting_for_name)

@dp.message(Registration.waiting_for_name)
async def handle_name(message: Message, state: FSMContext):
    data = await state.get_data()
    name = message.text.strip()
    telegram_id = message.from_user.id

    registered_users[telegram_id] = {
        "name": name,
        "phone": data["phone"]
    }

    await bot.send_message(
        OWNER_ID,
        f"🚨 <b>НОВИЙ КЛІЄНТ</b> 🚨\n"
        f"👤 Ім’я: <b>{name}</b>\n"
        f"📱 Телефон: +<b>{data['phone']}</b>\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n"
        f"💬 @{message.from_user.username or 'немає username'}\n\n"
    )

    kb = get_admin_keyboard() if telegram_id in ADMINS else get_user_keyboard()
    await message.answer("✅ Ви зареєстровані!", reply_markup=kb)
    await state.clear()

#-----------------------------------------------------------

@dp.message(F.text == "🔧 Адмін-панель")
async def admin_panel_handler(message: Message):
    if message.from_user.id not in ADMINS:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="➕ Додати акцію"), KeyboardButton(text="➕ Додати вакансію")],
        [KeyboardButton(text="❌ Видалити акцію"), KeyboardButton(text="❌ Видалити вакансію")],
        [KeyboardButton(text="🟢 Показувати акції"), KeyboardButton(text="🟢 Показувати вакансії")],
        [KeyboardButton(text="🔴 Сховати акції"), KeyboardButton(text="🔴 Сховати вакансії")],
        [KeyboardButton(text="⬅️ Назад до меню")]
    ])
    await message.answer("🔧 Адмін-панель активна. Виберіть дію:", reply_markup=kb)

@dp.message(F.text == "➕ Додати акцію")
async def add_aktsiya_start(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.set_state(AddAktsiya.waiting_for_title)
    await message.answer("🛒 Напишіть, на який товар хочете додати акцію:")

@dp.message(AddAktsiya.waiting_for_title)
async def add_aktsiya_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddAktsiya.waiting_for_desc)
    await message.answer("🕒 Напишіть термін дії акції:")

@dp.message(AddAktsiya.waiting_for_desc)
async def add_aktsiya_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    aktsii.append({"title": data["title"], "desc": message.text})
    await message.answer("✅ Акцію додано!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "❌ Видалити акцію")
async def delete_aktsiya_list(message: Message):
    if message.from_user.id != OWNER_ID or not aktsii:
        await message.answer("❌ Акцій для видалення немає.")
        return
    msg = "\n".join([f"{i+1}. {a['title']} ({a['desc']})" for i, a in enumerate(aktsii)])
    await message.answer("🗑️ Виберіть номер акції для видалення:\n\n" + msg)

@dp.message(F.text == "❌ Видалити вакансію")
async def delete_vacancy_list(message: Message):
    if message.from_user.id != OWNER_ID or not vacancies:
        await message.answer("❌ Вакансій для видалення немає.")
        return
    msg = "\n".join([f"{i+1}. {v['title']} ({v['place']})" for i, v in enumerate(vacancies)])
    await message.answer("🗑️ Виберіть номер вакансії для видалення:\n\n" + msg)

@dp.message(lambda msg: msg.text.isdigit())
async def handle_delete_index(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    index = int(message.text) - 1
    if 0 <= index < len(aktsii):
        removed = aktsii.pop(index)
        await message.answer(f"✅ Акцію '{removed['title']}' видалено.")
    elif 0 <= index < len(vacancies):
        removed = vacancies.pop(index)
        await message.answer(f"✅ Вакансію '{removed['title']}' видалено.")
    else:
        await message.answer("❌ Неправильний номер.")

@dp.message(F.text == "➕ Додати вакансію")
async def add_vacancy_start(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.set_state(AddVacancy.waiting_for_position)
    await message.answer("👤 На яку посаду хочете взяти людину? Опишіть також вимоги:")

@dp.message(AddVacancy.waiting_for_position)
async def add_vacancy_position(message: Message, state: FSMContext):
    await state.update_data(position=message.text)
    await state.set_state(AddVacancy.waiting_for_location)
    await message.answer("📍 Вкажіть адресу (локацію) для цієї вакансії:")

@dp.message(AddVacancy.waiting_for_location)
async def add_vacancy_location(message: Message, state: FSMContext):
    data = await state.get_data()
    vacancies.append({"title": data["position"], "place": message.text})
    await message.answer("✅ Вакансію додано!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.text == "⬅️ Назад до меню")
async def back_to_menu(message: Message):
    kb = get_admin_keyboard() if message.from_user.id in ADMINS else get_user_keyboard()
    await message.answer("⬇️ Меню доступних функцій:", reply_markup=kb)

#-----------------------------------------------------------

@dp.message(F.text == "📖 Меню")
async def show_menu_categories(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍣 Ролли", callback_data="menu_rolls")],
            [InlineKeyboardButton(text="🍤 Гарячі ролли", callback_data="menu_hot")],
            [InlineKeyboardButton(text="🍱 Сети", callback_data="menu_sets")],
            [InlineKeyboardButton(text="🍜 Кухня", callback_data="menu_kitchen")],
            [InlineKeyboardButton(text="🍸 Напої", callback_data="menu_other")]
        ]
    )
    await message.answer("Оберіть категорію меню:", reply_markup=kb)

user_last_messages = {}

async def delete_previous_messages(user_id: int, chat_id: int):
    if user_id in user_last_messages:
        for message_id in user_last_messages[user_id]:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
        user_last_messages[user_id] = []

@dp.message(F.text == "📖 Меню")
async def show_menu_categories(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🍣 Ролли", callback_data="menu_rolls")],
        [types.InlineKeyboardButton(text="🍤 Гарячі ролли", callback_data="menu_hot")],
        [types.InlineKeyboardButton(text="🍱 Сети", callback_data="menu_sets")],
        [types.InlineKeyboardButton(text="🍜 Кухня", callback_data="menu_kitchen")],
        [types.InlineKeyboardButton(text="🍸 Напої", callback_data="menu_other")]
    ])
    await message.answer("Оберіть категорію меню:", reply_markup=kb)

@dp.callback_query(F.data == "menu_rolls")
async def menu_rolls_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    await delete_previous_messages(user_id, chat_id)

    text_msg = await callback.message.answer("🍣 Ролли меню:")
    photos = [
        InputMediaPhoto(media=FSInputFile("menu_images/menu_rolls1.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_rolls2.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_rolls3.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_rolls4.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_rolls5.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_rolls6.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_rolls7.jpg"))
    ]
    media_msgs = await callback.message.answer_media_group(media=photos)
    user_last_messages[user_id] = [text_msg.message_id] + [m.message_id for m in media_msgs]

    await callback.answer()

@dp.callback_query(F.data == "menu_hot")
async def menu_hot_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    await delete_previous_messages(user_id, chat_id)

    text_msg = await callback.message.answer("🍤 Гарячі ролли:")
    photos = [
        InputMediaPhoto(media=FSInputFile("menu_images/menu_hot1.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_hot2.jpg"))
    ]
    media_msgs = await callback.message.answer_media_group(media=photos)
    user_last_messages[user_id] = [text_msg.message_id] + [m.message_id for m in media_msgs]

    await callback.answer()

@dp.callback_query(F.data == "menu_sets")
async def menu_sets_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    await delete_previous_messages(user_id, chat_id)

    text_msg = await callback.message.answer("🍱 Сети:")
    photos = [
        InputMediaPhoto(media=FSInputFile("menu_images/menu_sets1.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_sets2.jpg"))
    ]
    media_msgs = await callback.message.answer_media_group(media=photos)
    user_last_messages[user_id] = [text_msg.message_id] + [m.message_id for m in media_msgs]

    await callback.answer()

@dp.callback_query(F.data == "menu_kitchen")
async def menu_kitchen_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    await delete_previous_messages(user_id, chat_id)

    text_msg = await callback.message.answer("🍜 Кухня:")
    photos = [
        InputMediaPhoto(media=FSInputFile("menu_images/menu_kitchen1.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_kitchen2.jpg")),
        InputMediaPhoto(media=FSInputFile("menu_images/menu_kitchen3.jpg"))
    ]
    media_msgs = await callback.message.answer_media_group(media=photos)
    user_last_messages[user_id] = [text_msg.message_id] + [m.message_id for m in media_msgs]

    await callback.answer()

@dp.callback_query(F.data == "menu_other")
async def menu_other_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    await delete_previous_messages(user_id, chat_id)

    text_msg = await callback.message.answer("🍸 Напої:")
    photos = [
        InputMediaPhoto(media=FSInputFile("menu_images/menu_other.jpg"))
    ]
    media_msgs = await callback.message.answer_media_group(media=photos)
    user_last_messages[user_id] = [text_msg.message_id] + [m.message_id for m in media_msgs]

    await callback.answer()

@dp.callback_query(F.data.startswith("menu_"))
async def handle_menu_category(callback: types.CallbackQuery):
    category = callback.data.replace("menu_", "")
    try:
        await callback.message.answer_photo(
            photo=FSInputFile(f"menu_images/{category}.jpg"),
            caption=f"<b>{category.title()}</b>\nСмачні страви для вас 🥢",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await callback.message.answer(
            f"📦 Розділ <b>{category.title()}</b> наразі оновлюється...",
            parse_mode=ParseMode.HTML
        )
    await callback.answer()

@dp.message(F.text == "🧾 Ваша картка")
async def card_handler(message: Message):
    try:
        telegram_id = message.from_user.id
        user = registered_users.get(telegram_id)

        if not user:
            await message.answer("❌ Ви ще не зареєстровані.")
            return

        user_id = str(telegram_id)
        name = user.get("name", "—")
        phone = user.get("phone", "—")
        bonus = 0.00  # заглушка, позже можно заменить логикой SkyService

        writer_options = {
            'module_width': 0.2,
            'module_height': 10.0,
            'font_size': 8,
            'quiet_zone': 1.0
        }

        barcode_image = io.BytesIO()
        Code128(user_id, writer=ImageWriter()).write(barcode_image, options=writer_options)
        barcode_image.seek(0)

        filename = f"barcode_{user_id}.png"
        with open(filename, "wb") as f:
            f.write(barcode_image.read())

        photo_file = FSInputFile(filename)
        caption = (
            f"<b>📇 Інформація про картку покупця:</b>\n"
            f"👤 <b>Ім’я:</b> {name}\n"
            f"📱 <b>Телефон:</b> {phone}\n"
            f"🆔 <b>ID:</b> {user_id}\n"
            f"💰 <b>Бонуси:</b> {bonus:.2f} грн\n\n"
            "<b>📦 Останнє придбання:</b>\n"
            "🗓️ <b>Дата:</b> –\n"
            "💳 <b>Сума:</b> 0.00 грн\n"
            "💳 <b>Оплата:</b> –"
        )
        await message.answer_photo(photo=photo_file, caption=caption)
        os.remove(filename)
    except Exception as e:
        await message.answer(f"❌ Помилка при генерації картки: {e}")

@dp.message(F.text == "🔥 Акції та знижки")
async def discounts_handler(message: Message):
    if aktsii:
        text = "\n\n".join([
            f"🛍️ Акції: <b>{item['title']}</b>\n💸 Дійсно: {item['desc']}"
            for item in aktsii
        ])
    else:
        text = "Поки що немає акцій."
    await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "📄 Вакансії")
async def vacancies_handler(message: Message):
    if not show_vacancies:
        return
    if not vacancies:
        await message.answer("Наразі немає вакансій.")
    else:
        text = "\n\n".join([
            f"🏢 <b>{v['place']}</b>\n📌 Позиція: {v['title']}"
            for v in vacancies
        ])
        await message.answer(text, parse_mode=ParseMode.HTML)

@dp.message(F.text == "😎 Ми Онлайн")
async def online_handler(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telegram", url="https://t.me/+EiNhYfYSNL42Y2Ri")],
        [InlineKeyboardButton(text="Instagram", url="https://instagram.com/sushi._samurai777?igshid=YmMyMTA2M2Y=")],
        [InlineKeyboardButton(text="Viber", url="https://invite.viber.com/?g2=AQB0MS57NNfrFk84TNP2gqbdnK%2FWhDHdWwN7Vf4stXdEEoE9NG%2BTiAius6YYIDBb")]
    ])
    await message.answer("Ми онлайн тут:", reply_markup=kb)

@dp.message(F.text == "📍 Знайти нас")
async def choose_location(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
                text="📍 Вокзальна 26Б",
                url="https://maps.app.goo.gl/4UEaeHhixM3bqFhcA")],
        [InlineKeyboardButton(
                text="📍 Київська 102",
                url="https://maps.app.goo.gl/GFwkJ58peZTDzRgV8")]
    ])
    await message.answer(
        "Оберіть Samurai, який хочете знайти на мапі:",
        reply_markup=kb)

@dp.message(F.text == "📞 Замовити")
async def choose_order_point(message: types.Message, state: FSMContext):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📍 Вокзальна 26Б", callback_data="choose_branch_vokzalna")],
        [types.InlineKeyboardButton(text="📍 Київська 102", callback_data="choose_branch_kyivska")],
        #[types.InlineKeyboardButton(text="⬅️ Назад до меню", callback_data="back_to_menu")]
    ])
    await message.answer("Оберіть Samurai, в якому хочете зробити замовлення:", reply_markup=kb)
    await state.set_state(Order.choosing_branch)

@dp.callback_query(F.data == "choose_branch_vokzalna")
async def show_vokzalna_numbers(callback: types.CallbackQuery, state: FSMContext):
    text = (
        "📞 <b>Номери для замовлення (Вокзальна 26Б):</b>\n\n"
        "📱 +38 (068) 088 10 79\n"
        "📱 +38 (093) 730 20 24\n\n"
        "Скопіюйте номер, щоб викликати 📲"
    )
    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "choose_branch_kyivska")
async def show_kyivska_numbers(callback: types.CallbackQuery, state: FSMContext):
    text = (
        "📞 <b>Номер для замовлення (Київська 102):</b>\n"
        "📱 <a href='tel:+380939566263'>+38 (093) 956 62 63</a>\n\n"
        "Скопіюйте номер, щоб викликати 📲"
    )
    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "back_to_order_points")
async def back_to_order_points(callback: types.CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Вокзальна 26Б", callback_data="choose_branch_vokzalna")],
        [InlineKeyboardButton(text="📍 Київська 102", callback_data="choose_branch_kyivska")]
    ])
    await callback.message.edit_text("Оберіть точку, з якої хочете зробити замовлення:", reply_markup=kb)
    await state.set_state(Order.choosing_branch)
    await callback.answer()

@dp.message(F.text == "💌 Відгук і Пропозиція")
async def feedback_handler(message: Message):
    user_feedback_waiting.add(message.from_user.id)
    await message.answer("✍️ Напишіть ваш відгук або подяку. Ми обов'язково це врахуємо!")

@dp.message()
async def catch_feedback(message: Message):
    if message.from_user.id in user_feedback_waiting:
        user_feedback_waiting.remove(message.from_user.id)

        user_data = registered_users.get(message.from_user.id)

        if not user_data:
            await message.answer("❌ Ви ще не зареєстровані.")
            return

        name = user_data.get("name", "—")
        phone = user_data.get("phone", "—")

        await bot.send_message(
            OWNER_ID,
            f"📩 <b>Новий відгук</b>\n"
            f"👤 <b>Ім’я:</b> {name}\n"
            f"📱 <b>Телефон:</b> +{phone}\n"
            f"💬 @{message.from_user.username or 'без username'}\n"
            f"🆔 <code>{message.from_user.id}</code>\n\n"
            f"<b>✉️ Відгук:</b>\n{message.text}",
            parse_mode=ParseMode.HTML
        )
        await message.answer("✅ Дякуємо! Ваш відгук надіслано адміністрації.")

#-----------------------------------------------------------

@dp.message(F.text == "🔴 Сховати акції")
async def hide_aktsii(message: Message):
    global show_aktsii
    show_aktsii = False
    update_config_flag("show_aktsii", False)
    await message.answer("❌ Кнопка 'Акції' схована", reply_markup=get_admin_keyboard())

@dp.message(F.text == "🟢 Показувати акції")
async def show_aktsii_on(message: Message):
    global show_aktsii
    show_aktsii = True
    update_config_flag("show_aktsii", True)
    await message.answer("✅ Кнопка 'Акції' показується", reply_markup=get_admin_keyboard())

@dp.message(F.text == "🔴 Сховати вакансії")
async def hide_vacancies(message: Message):
    global show_vacancies
    show_vacancies = False
    update_config_flag("show_vacancies", False)
    await message.answer("❌ Кнопка 'Вакансії' схована", reply_markup=get_admin_keyboard())

@dp.message(F.text == "🟢 Показувати вакансії")
async def show_vacancies_on(message: Message):
    global show_vacancies
    show_vacancies = True
    update_config_flag("show_vacancies", True)
    await message.answer("✅ Кнопка 'Вакансії' показується", reply_markup=get_admin_keyboard())

#-----------------------------------------------------------

@dp.message(Command(commands=["stop"]))
async def stop_handler(message: Message):
    await message.answer("👋 Дякуємо, що завітали! До нових зустрічей")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())

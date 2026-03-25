import os
import asyncio
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

# --- Настройка прокси (если нужен) ---
# Раскомментируйте, если используете прокси
# PROXY_URL = "socks5://127.0.0.1:1080"  # или http://proxy:port

token = os.getenv("BOT_TOKEN")
if not token or token == "your_bot_token_here":
    print("❌ Ошибка: не указан BOT_TOKEN в .env")
    exit(1)

# Создаём бота и диспетчер
bot = Bot(token=token)  # если нужен прокси: Bot(token=token, proxy=PROXY_URL)
dp = Dispatcher(storage=MemoryStorage())

# --- База данных ---
def init_db():
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            task_type TEXT NOT NULL,
            teacher TEXT NOT NULL,
            deadline TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    conn.close()

def add_task(user_id, subject, task_type, teacher, deadline):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks (user_id, subject, task_type, teacher, deadline)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, subject, task_type, teacher, deadline))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def get_tasks(user_id, status="active"):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, subject, task_type, teacher, deadline
        FROM tasks
        WHERE user_id = ? AND status = ?
        ORDER BY deadline ASC
    """, (user_id, status))
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def complete_task(task_id, user_id):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks SET status = 'completed'
        WHERE id = ? AND user_id = ?
    """, (task_id, user_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def delete_task(task_id, user_id):
    conn = sqlite3.connect("tasks.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

# --- FSM для добавления задачи ---
class AddTaskState(StatesGroup):
    subject = State()
    task_type = State()
    teacher = State()
    deadline = State()

# --- Клавиатуры ---
def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить задачу", callback_data="add")],
            [InlineKeyboardButton(text="📋 Мои задачи", callback_data="list")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
        ]
    )

# --- Обработчики команд ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот для управления учебными задачами.\n\n"
        "Что я умею:\n"
        "✅ Добавлять задачи\n"
        "✅ Показывать список задач\n"
        "✅ Отмечать задачи выполненными\n"
        "✅ Удалять задачи\n\n"
        "Используй кнопки ниже 👇",
        reply_markup=main_keyboard()
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 **Как пользоваться ботом:**\n\n"
        "**Добавить задачу:**\n"
        "1. Нажми 'Добавить задачу'\n"
        "2. Введи название предмета\n"
        "3. Введи тип работы\n"
        "4. Введи ФИО преподавателя\n"
        "5. Введи дату в формате ДД.ММ.ГГГГ\n\n"
        "**Мои задачи:**\n"
        "Показывает список всех активных задач\n\n"
        "**Выполнить задачу:**\n"
        "Выбери задачу из списка и нажми '✅ Выполнено'",
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data == "help")
async def callback_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "📖 **Как пользоваться ботом:**\n\n"
        "**Добавить задачу:**\n"
        "1. Нажми 'Добавить задачу'\n"
        "2. Введи название предмета\n"
        "3. Введи тип работы\n"
        "4. Введи ФИО преподавателя\n"
        "5. Введи дату в формате ДД.ММ.ГГГГ\n\n"
        "**Мои задачи:**\n"
        "Показывает список всех активных задач\n\n"
        "**Выполнить задачу:**\n"
        "Выбери задачу из списка и нажми '✅ Выполнено'",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@dp.callback_query(lambda c: c.data == "add")
async def callback_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddTaskState.subject)
    await callback.message.edit_text(
        "📖 Введите название предмета:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
        )
    )

@dp.message(AddTaskState.subject)
async def process_subject(message: types.Message, state: FSMContext):
    await state.update_data(subject=message.text)
    await state.set_state(AddTaskState.task_type)
    await message.answer(
        "📝 Введите тип работы (лабораторная, курсовая, реферат):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
        )
    )

@dp.message(AddTaskState.task_type)
async def process_task_type(message: types.Message, state: FSMContext):
    await state.update_data(task_type=message.text)
    await state.set_state(AddTaskState.teacher)
    await message.answer(
        "👨‍🏫 Введите ФИО преподавателя:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
        )
    )

@dp.message(AddTaskState.teacher)
async def process_teacher(message: types.Message, state: FSMContext):
    await state.update_data(teacher=message.text)
    await state.set_state(AddTaskState.deadline)
    await message.answer(
        "📅 Введите дату сдачи в формате ДД.ММ.ГГГГ (например: 25.12.2024):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
        )
    )

@dp.message(AddTaskState.deadline)
async def process_deadline(message: types.Message, state: FSMContext):
    try:
        deadline = datetime.strptime(message.text, "%d.%m.%Y")
        deadline_formatted = deadline.strftime("%Y-%m-%d")
        data = await state.get_data()
        add_task(
            user_id=message.from_user.id,
            subject=data["subject"],
            task_type=data["task_type"],
            teacher=data["teacher"],
            deadline=deadline_formatted
        )
        await state.clear()
        await message.answer(
            f"✅ Задача добавлена!\n\n"
            f"📖 {data['subject']}\n"
            f"📝 {data['task_type']}\n"
            f"👨‍🏫 {data['teacher']}\n"
            f"📅 {message.text}\n\n"
            f"Что дальше?",
            reply_markup=main_keyboard()
        )
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты! Используйте ДД.ММ.ГГГГ.\nПопробуйте ещё раз:"
        )

@dp.callback_query(lambda c: c.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "❌ Операция отменена.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(lambda c: c.data == "list")
async def callback_list(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    tasks = get_tasks(user_id)

    if not tasks:
        await callback.message.edit_text(
            "📭 У вас нет активных задач.",
            reply_markup=main_keyboard()
        )
        return

    keyboard = []
    for task in tasks:
        task_id, subject, task_type, teacher, deadline = task
        deadline_str = datetime.strptime(deadline, "%Y-%m-%d").strftime("%d.%m.%Y")
        button_text = f"📚 {subject} - {task_type} (до {deadline_str})"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"view_{task_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="menu")])

    await callback.message.edit_text(
        f"📋 **Ваши задачи ({len(tasks)} шт.):**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@dp.callback_query(lambda c: c.data.startswith("view_"))
async def callback_view(callback: CallbackQuery):
    await callback.answer()
    task_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    tasks = get_tasks(user_id)
    task = next((t for t in tasks if t[0] == task_id), None)

    if not task:
        await callback.message.edit_text(
            "❌ Задача не найдена.",
            reply_markup=main_keyboard()
        )
        return

    task_id, subject, task_type, teacher, deadline = task
    deadline_str = datetime.strptime(deadline, "%Y-%m-%d").strftime("%d.%m.%Y")

    text = (
        f"📋 **Информация о задаче**\n\n"
        f"📖 **Предмет:** {subject}\n"
        f"📝 **Тип:** {task_type}\n"
        f"👨‍🏫 **Преподаватель:** {teacher}\n"
        f"📅 **Дедлайн:** {deadline_str}\n"
    )

    # Проверяем статус дедлайна
    deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
    today = datetime.now().date()
    if deadline_date < today:
        text += "\n⚠️ **ПРОСРОЧЕНО!**"
    elif deadline_date == today:
        text += "\n⚠️ **СЕГОДНЯ!**"
    elif (deadline_date - today).days <= 3:
        text += f"\n⚠️ Осталось {(deadline_date - today).days} дня(ей)"

    keyboard = [
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"complete_{task_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_{task_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="list")]
    ]
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@dp.callback_query(lambda c: c.data.startswith("complete_"))
async def callback_complete(callback: CallbackQuery):
    await callback.answer()
    task_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    if complete_task(task_id, user_id):
        await callback.message.edit_text(
            "✅ Задача выполнена! 🎉",
            reply_markup=main_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось отметить задачу.",
            reply_markup=main_keyboard()
        )

@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def callback_delete(callback: CallbackQuery):
    await callback.answer()
    task_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    if delete_task(task_id, user_id):
        await callback.message.edit_text(
            "🗑️ Задача удалена.",
            reply_markup=main_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось удалить задачу.",
            reply_markup=main_keyboard()
        )

@dp.callback_query(lambda c: c.data == "menu")
async def callback_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_keyboard()
    )

# --- Запуск ---
async def main():
    init_db()
    print("🤖 Бот запущен (aiogram)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
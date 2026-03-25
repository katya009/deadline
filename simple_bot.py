import os
import sqlite3
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    
    # Создаем таблицу задач
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            task_type TEXT NOT NULL,
            teacher TEXT NOT NULL,
            deadline TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# Функции для работы с БД
def add_task(user_id, subject, task_type, teacher, deadline):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (user_id, subject, task_type, teacher, deadline)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, subject, task_type, teacher, deadline))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def get_tasks(user_id, status='active'):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, subject, task_type, teacher, deadline
        FROM tasks
        WHERE user_id = ? AND status = ?
        ORDER BY deadline ASC
    ''', (user_id, status))
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def complete_task(task_id, user_id):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE tasks
        SET status = 'completed'
        WHERE id = ? AND user_id = ?
    ''', (task_id, user_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

def delete_task(task_id, user_id):
    conn = sqlite3.connect('tasks.db')
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM tasks
        WHERE id = ? AND user_id = ?
    ''', (task_id, user_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0

# Клавиатуры
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Добавить задачу", callback_data="add")],
        [InlineKeyboardButton("📋 Мои задачи", callback_data="list")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение"""
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я простой бот для управления учебными задачами.\n\n"
        "Что я умею:\n"
        "✅ Добавлять задачи\n"
        "✅ Показывать список задач\n"
        "✅ Отмечать задачи выполненными\n"
        "✅ Удалять задачи\n\n"
        "Используй кнопки ниже 👇"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    help_text = (
        "📖 **Как пользоваться ботом:**\n\n"
        "**Добавить задачу:**\n"
        "1. Нажми 'Добавить задачу'\n"
        "2. Введи название предмета\n"
        "3. Введи тип работы (лаба, курсовая и т.д.)\n"
        "4. Введи ФИО преподавателя\n"
        "5. Введи дату в формате ДД.ММ.ГГГГ\n\n"
        "**Мои задачи:**\n"
        "Показывает список всех активных задач\n\n"
        "**Выполнить задачу:**\n"
        "Выбери задачу из списка и нажми '✅ Выполнено'\n\n"
        "**Удалить задачу:**\n"
        "Выбери задачу из списка и нажми '🗑️ Удалить'"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(help_text, parse_mode='Markdown')

# Состояния для добавления задачи
ADD_SUBJECT, ADD_TYPE, ADD_TEACHER, ADD_DEADLINE = range(4)

async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление задачи"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['new_task'] = {}
    
    await query.edit_message_text(
        "📖 Введите название предмета:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])
    )
    return ADD_SUBJECT

async def add_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить предмет"""
    context.user_data['new_task']['subject'] = update.message.text
    
    await update.message.reply_text(
        "📝 Введите тип работы (лабораторная, курсовая, реферат):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])
    )
    return ADD_TYPE

async def add_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить тип работы"""
    context.user_data['new_task']['task_type'] = update.message.text
    
    await update.message.reply_text(
        "👨‍🏫 Введите ФИО преподавателя:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])
    )
    return ADD_TEACHER

async def add_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить преподавателя"""
    context.user_data['new_task']['teacher'] = update.message.text
    
    await update.message.reply_text(
        "📅 Введите дату сдачи в формате ДД.ММ.ГГГГ (например: 25.12.2024):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]])
    )
    return ADD_DEADLINE

async def add_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить дату и сохранить задачу"""
    user_id = update.effective_user.id
    deadline_str = update.message.text
    
    try:
        # Проверяем формат даты
        deadline = datetime.strptime(deadline_str, '%d.%m.%Y')
        deadline_formatted = deadline.strftime('%Y-%m-%d')
        
        # Сохраняем задачу
        task_data = context.user_data['new_task']
        task_id = add_task(
            user_id,
            task_data['subject'],
            task_data['task_type'],
            task_data['teacher'],
            deadline_formatted
        )
        
        await update.message.reply_text(
            f"✅ Задача добавлена!\n\n"
            f"📖 {task_data['subject']}\n"
            f"📝 {task_data['task_type']}\n"
            f"👨‍🏫 {task_data['teacher']}\n"
            f"📅 {deadline_str}\n\n"
            f"Что дальше?",
            reply_markup=main_keyboard()
        )
        
        # Очищаем данные
        context.user_data.clear()
        return -1
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты!\n"
            "Используйте формат ДД.ММ.ГГГГ (например: 25.12.2024)\n"
            "Попробуйте еще раз:"
        )
        return ADD_DEADLINE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    
    await query.edit_message_text(
        "❌ Операция отменена.\n\nЧто хотите сделать?",
        reply_markup=main_keyboard()
    )
    return -1

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список задач"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    tasks = get_tasks(user_id)
    
    if not tasks:
        await query.edit_message_text(
            "📭 У вас нет активных задач.\n\n"
            "Добавьте новую задачу, нажав на кнопку ниже.",
            reply_markup=main_keyboard()
        )
        return
    
    # Создаем клавиатуру со списком задач
    keyboard = []
    for task in tasks:
        task_id = task[0]
        subject = task[1]
        task_type = task[2]
        deadline = datetime.strptime(task[4], '%Y-%m-%d').strftime('%d.%m.%Y')
        button_text = f"📚 {subject} - {task_type} (до {deadline})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_{task_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="menu")])
    
    await query.edit_message_text(
        f"📋 **Ваши задачи ({len(tasks)} шт.):**\n\n"
        "Нажмите на задачу для управления",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def view_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать детали задачи"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    context.user_data['current_task'] = task_id
    
    tasks = get_tasks(query.from_user.id)
    task = None
    for t in tasks:
        if t[0] == task_id:
            task = t
            break
    
    if not task:
        await query.edit_message_text(
            "❌ Задача не найдена",
            reply_markup=main_keyboard()
        )
        return
    
    deadline = datetime.strptime(task[4], '%Y-%m-%d').strftime('%d.%m.%Y')
    
    task_text = (
        f"📋 **Информация о задаче**\n\n"
        f"📖 **Предмет:** {task[1]}\n"
        f"📝 **Тип:** {task[2]}\n"
        f"👨‍🏫 **Преподаватель:** {task[3]}\n"
        f"📅 **Дедлайн:** {deadline}\n"
    )
    
    # Проверяем статус
    deadline_date = datetime.strptime(task[4], '%Y-%m-%d').date()
    today = datetime.now().date()
    
    if deadline_date < today:
        task_text += "\n⚠️ **ПРОСРОЧЕНО!**"
    elif deadline_date == today:
        task_text += "\n⚠️ **СЕГОДНЯ!**"
    elif (deadline_date - today).days <= 3:
        task_text += f"\n⚠️ Осталось {(deadline_date - today).days} дня(ей)"
    
    keyboard = [
        [InlineKeyboardButton("✅ Отметить выполненной", callback_data=f"complete_{task_id}")],
        [InlineKeyboardButton("🗑️ Удалить задачу", callback_data=f"delete_{task_id}")],
        [InlineKeyboardButton("🔙 Назад к списку", callback_data="list")]
    ]
    
    await query.edit_message_text(
        task_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def complete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметить задачу как выполненную"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    if complete_task(task_id, user_id):
        await query.edit_message_text(
            "✅ Задача отмечена как выполненная!\n\n"
            "Отличная работа! Так держать! 🎉",
            reply_markup=main_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ Не удалось отметить задачу",
            reply_markup=main_keyboard()
        )

async def delete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить задачу"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    if delete_task(task_id, user_id):
        await query.edit_message_text(
            "🗑️ Задача удалена!",
            reply_markup=main_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ Не удалось удалить задачу",
            reply_markup=main_keyboard()
        )

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться в главное меню"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Главное меню:",
        reply_markup=main_keyboard()
    )

# Основная функция
def main():
    """Запуск бота"""
    # Инициализируем базу данных
    init_db()
    
    # Получаем токен
    token = os.getenv('BOT_TOKEN')
    if not token or token == 'your_bot_token_here':
        print("❌ Ошибка: Не установлен BOT_TOKEN в файле .env")
        print("Получите токен у @BotFather и добавьте его в файл .env")
        print("Пример: BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Conversation для добавления задачи
    from telegram.ext import ConversationHandler
    add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_task_start, pattern='^add$')],
        states={
            ADD_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_subject)],
            ADD_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_type)],
            ADD_TEACHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_teacher)],
            ADD_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_deadline)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern='^cancel$')]
    )
    
    application.add_handler(add_conv)
    application.add_handler(CallbackQueryHandler(list_tasks, pattern='^list$'))
    application.add_handler(CallbackQueryHandler(view_task, pattern='^view_\\d+$'))
    application.add_handler(CallbackQueryHandler(complete_task_handler, pattern='^complete_\\d+$'))
    application.add_handler(CallbackQueryHandler(delete_task_handler, pattern='^delete_\\d+$'))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^menu$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    
    print("=" * 50)
    print("🤖 Простой бот для управления задачами запущен!")
    print("=" * 50)
    print("✅ Бот готов к работе")
    print("📱 Найдите бота в Telegram и нажмите /start")
    print("🛑 Для остановки нажмите Ctrl+C")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
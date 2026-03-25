import os
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
SUBJECT, WORK_TYPE, TEACHER, DEADLINE, FILE, COMMENT, CONFIRM = range(7)

# Инициализация планировщика
scheduler = AsyncIOScheduler()

# Глобальная переменная для application
application = None

class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = "database/tasks.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Получение соединения с БД"""
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        """Инициализация базы данных"""
        # Создаем папку database если её нет
        os.makedirs("database", exist_ok=True)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица задач
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    work_type TEXT NOT NULL,
                    teacher TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    file_path TEXT,
                    comment TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            conn.commit()
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Добавление пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()
    
    def add_task(self, user_id: int, subject: str, work_type: str, teacher: str, 
                 deadline: str, file_path: str = None, comment: str = None) -> int:
        """Добавление задачи"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tasks (user_id, subject, work_type, teacher, deadline, file_path, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, subject, work_type, teacher, deadline, file_path, comment))
            conn.commit()
            return cursor.lastrowid
    
    def get_active_tasks(self, user_id: int) -> List[Tuple]:
        """Получение активных задач пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, subject, work_type, teacher, deadline, file_path, comment
                FROM tasks
                WHERE user_id = ? AND status = 'active'
                ORDER BY deadline ASC
            ''', (user_id,))
            return cursor.fetchall()
    
    def get_task_by_id(self, task_id: int, user_id: int) -> Optional[Tuple]:
        """Получение задачи по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, subject, work_type, teacher, deadline, file_path, comment
                FROM tasks
                WHERE id = ? AND user_id = ? AND status = 'active'
            ''', (task_id, user_id))
            return cursor.fetchone()
    
    def complete_task(self, task_id: int, user_id: int) -> bool:
        """Отметка задачи как выполненной"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tasks
                SET status = 'completed'
                WHERE id = ? AND user_id = ? AND status = 'active'
            ''', (task_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_task(self, task_id: int, user_id: int) -> bool:
        """Удаление задачи"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM tasks
                WHERE id = ? AND user_id = ?
            ''', (task_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_tasks_by_deadline(self, days: int) -> List[Tuple]:
        """Получение задач с дедлайном через указанное количество дней"""
        target_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, subject, work_type, teacher, deadline, comment
                FROM tasks
                WHERE status = 'active' AND deadline = ?
            ''', (target_date,))
            return cursor.fetchall()
    
    def get_overdue_tasks(self) -> List[Tuple]:
        """Получение просроченных задач"""
        today = datetime.now().strftime('%Y-%m-%d')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, subject, work_type, teacher, deadline, comment
                FROM tasks
                WHERE status = 'active' AND deadline < ?
            ''', (today,))
            return cursor.fetchall()
    
    def update_task(self, task_id: int, user_id: int, field: str, value: str) -> bool:
        """Обновление поля задачи"""
        allowed_fields = ['subject', 'work_type', 'teacher', 'deadline', 'comment']
        if field not in allowed_fields:
            return False
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE tasks
                SET {field} = ?
                WHERE id = ? AND user_id = ? AND status = 'active'
            ''', (value, task_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

# Инициализация базы данных
db = Database()

# Временное хранилище данных при добавлении задачи
user_data = {}

# Клавиатуры
def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить задачу", callback_data="add_task")],
        [InlineKeyboardButton("📋 Список задач", callback_data="list_tasks")],
        [InlineKeyboardButton("✏️ Редактировать задачу", callback_data="edit_task")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    """Клавиатура с кнопкой отмены"""
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]
    return InlineKeyboardMarkup(keyboard)

def get_task_list_keyboard(tasks: List[Tuple]):
    """Клавиатура со списком задач"""
    keyboard = []
    for task in tasks:
        task_id = task[0]
        subject = task[1]
        deadline = datetime.strptime(task[4], '%Y-%m-%d').strftime('%d.%m.%Y')
        button_text = f"📚 {subject} - {deadline}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"task_{task_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_task_actions_keyboard(task_id: int):
    """Клавиатура действий с задачей"""
    keyboard = [
        [InlineKeyboardButton("✅ Отметить выполненной", callback_data=f"complete_{task_id}")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{task_id}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{task_id}")],
        [InlineKeyboardButton("🔙 Назад к списку", callback_data="list_tasks")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_edit_options_keyboard(task_id: int):
    """Клавиатура выбора поля для редактирования"""
    keyboard = [
        [InlineKeyboardButton("📖 Предмет", callback_data=f"edit_field_{task_id}_subject")],
        [InlineKeyboardButton("📝 Тип работы", callback_data=f"edit_field_{task_id}_work_type")],
        [InlineKeyboardButton("👨‍🏫 Преподаватель", callback_data=f"edit_field_{task_id}_teacher")],
        [InlineKeyboardButton("📅 Дедлайн", callback_data=f"edit_field_{task_id}_deadline")],
        [InlineKeyboardButton("💬 Комментарий", callback_data=f"edit_field_{task_id}_comment")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"task_{task_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Добавляем пользователя в БД
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для управления дедлайнами и академическими долгами.\n\n"
        "Я умею:\n"
        "✅ Добавлять задачи с дедлайнами\n"
        "✅ Показывать список всех задач\n"
        "✅ Напоминать о приближающихся дедлайнах\n"
        "✅ Отмечать задачи выполненными\n"
        "✅ Редактировать и удалять задачи\n\n"
        "Используй кнопки ниже для навигации 👇"
    )
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📖 **Помощь по боту**\n\n"
        "**Добавление задачи:**\n"
        "1. Нажми '➕ Добавить задачу'\n"
        "2. Введи название предмета\n"
        "3. Выбери/введи тип работы\n"
        "4. Введи ФИО преподавателя\n"
        "5. Введи дату в формате ДД.ММ.ГГГГ\n"
        "6. При необходимости прикрепи файл\n"
        "7. Добавь комментарий\n"
        "8. Подтверди создание задачи\n\n"
        "**Управление задачами:**\n"
        "• 📋 Список задач - просмотр всех активных задач\n"
        "• ✅ Отметить выполненной - задача удаляется из списка\n"
        "• ✏️ Редактировать - изменить любые данные задачи\n"
        "• 🗑️ Удалить - полностью удалить задачу\n\n"
        "**Напоминания:**\n"
        "Бот автоматически напоминает о дедлайнах за 3 дня и за 1 день до сдачи, а также ежедневно при просрочке."
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )
    else:
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard()
        )

async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления задачи"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data[user_id] = {}
    
    await query.edit_message_text(
        "📖 Введите название предмета:",
        reply_markup=get_cancel_keyboard()
    )
    return SUBJECT

async def add_task_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение названия предмета"""
    user_id = update.effective_user.id
    subject = update.message.text
    
    user_data[user_id]['subject'] = subject
    
    await update.message.reply_text(
        "📝 Введите тип работы (лабораторная, курсовая, реферат и т.д.):",
        reply_markup=get_cancel_keyboard()
    )
    return WORK_TYPE

async def add_task_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение типа работы"""
    user_id = update.effective_user.id
    work_type = update.message.text
    
    user_data[user_id]['work_type'] = work_type
    
    await update.message.reply_text(
        "👨‍🏫 Введите ФИО преподавателя:",
        reply_markup=get_cancel_keyboard()
    )
    return TEACHER

async def add_task_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ФИО преподавателя"""
    user_id = update.effective_user.id
    teacher = update.message.text
    
    user_data[user_id]['teacher'] = teacher
    
    await update.message.reply_text(
        "📅 Введите дату сдачи в формате ДД.ММ.ГГГГ (например: 25.12.2024):",
        reply_markup=get_cancel_keyboard()
    )
    return DEADLINE

async def add_task_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение даты дедлайна"""
    user_id = update.effective_user.id
    deadline_str = update.message.text
    
    # Проверка формата даты
    try:
        deadline = datetime.strptime(deadline_str, '%d.%m.%Y')
        user_data[user_id]['deadline'] = deadline.strftime('%Y-%m-%d')
        
        await update.message.reply_text(
            "📎 Хотите прикрепить файл?\n\n"
            "Отправьте файл или нажмите 'Пропустить'",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_file")]
            ])
        )
        return FILE
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ\n"
            "Попробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return DEADLINE

async def add_task_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение файла"""
    user_id = update.effective_user.id
    
    # Создаем папку uploads если её нет
    os.makedirs("uploads", exist_ok=True)
    
    if update.message.document:
        # Сохраняем файл
        document = update.message.document
        file = await document.get_file()
        
        # Создаем имя файла
        file_name = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{document.file_name}"
        file_path = f"uploads/{file_name}"
        
        await file.download_to_drive(file_path)
        user_data[user_id]['file_path'] = file_path
    
    await update.message.reply_text(
        "💬 Добавьте комментарий к задаче (или нажмите 'Пропустить'):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_comment")]
        ])
    )
    return COMMENT

async def add_task_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение комментария"""
    user_id = update.effective_user.id
    comment = update.message.text
    
    user_data[user_id]['comment'] = comment
    
    # Показываем подтверждение
    return await show_confirmation(update, context)

async def skip_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропуск прикрепления файла"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data[user_id]['file_path'] = None
    
    await query.edit_message_text(
        "💬 Добавьте комментарий к задаче (или нажмите 'Пропустить'):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip_comment")]
        ])
    )
    return COMMENT

async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропуск добавления комментария"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data[user_id]['comment'] = None
    
    # Показываем подтверждение
    return await show_confirmation(update, context)

async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ подтверждения создания задачи"""
    if isinstance(update, Update) and update.callback_query:
        user_id = update.callback_query.from_user.id
        query = update.callback_query
        message_func = query.edit_message_text
    else:
        user_id = update.effective_user.id
        message_func = update.message.reply_text
    
    data = user_data[user_id]
    
    confirmation_text = (
        "📋 **Проверьте данные задачи:**\n\n"
        f"📖 Предмет: {data['subject']}\n"
        f"📝 Тип работы: {data['work_type']}\n"
        f"👨‍🏫 Преподаватель: {data['teacher']}\n"
        f"📅 Дедлайн: {datetime.strptime(data['deadline'], '%Y-%m-%d').strftime('%d.%m.%Y')}\n"
    )
    
    if data.get('comment'):
        confirmation_text += f"💬 Комментарий: {data['comment']}\n"
    if data.get('file_path'):
        confirmation_text += f"📎 Файл: прикреплен\n"
    
    confirmation_text += "\nВсе верно?"
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, сохранить", callback_data="confirm_save")],
        [InlineKeyboardButton("❌ Нет, изменить задачу", callback_data="cancel")]
    ]
    
    await message_func(
        confirmation_text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

async def confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение задачи"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = user_data[user_id]
    
    # Сохраняем задачу в БД
    task_id = db.add_task(
        user_id=user_id,
        subject=data['subject'],
        work_type=data['work_type'],
        teacher=data['teacher'],
        deadline=data['deadline'],
        file_path=data.get('file_path'),
        comment=data.get('comment')
    )
    
    # Очищаем временные данные
    del user_data[user_id]
    
    await query.edit_message_text(
        "✅ Задача успешно добавлена!\n\n"
        "Что хотите сделать дальше?",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        # Очищаем временные данные
        user_id = query.from_user.id
        if user_id in user_data:
            del user_data[user_id]
        
        await query.edit_message_text(
            "Операция отменена.\n\n"
            "Что хотите сделать?",
            reply_markup=get_main_keyboard()
        )
    else:
        user_id = update.effective_user.id
        if user_id in user_data:
            del user_data[user_id]
        
        await update.message.reply_text(
            "Операция отменена.\n\n"
            "Что хотите сделать?",
            reply_markup=get_main_keyboard()
        )
    return ConversationHandler.END

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ списка задач"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    tasks = db.get_active_tasks(user_id)
    
    if not tasks:
        await query.edit_message_text(
            "📭 У вас нет активных задач.\n\n"
            "Добавьте новую задачу, нажав на кнопку ниже.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Группируем задачи по предметам
    tasks_by_subject = {}
    for task in tasks:
        subject = task[1]
        if subject not in tasks_by_subject:
            tasks_by_subject[subject] = []
        tasks_by_subject[subject].append(task)
    
    message = "📋 **Ваши задачи:**\n\n"
    for subject, subject_tasks in tasks_by_subject.items():
        message += f"📚 *{subject}*\n"
        for task in subject_tasks:
            deadline = datetime.strptime(task[4], '%Y-%m-%d').strftime('%d.%m.%Y')
            message += f"   • {task[2]} - до {deadline}\n"
        message += "\n"
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_task_list_keyboard(tasks)
    )

async def show_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ детальной информации о задаче"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    task = db.get_task_by_id(task_id, user_id)
    
    if not task:
        await query.edit_message_text(
            "❌ Задача не найдена.",
            reply_markup=get_main_keyboard()
        )
        return
    
    deadline = datetime.strptime(task[4], '%Y-%m-%d').strftime('%d.%m.%Y')
    
    message = (
        f"📋 **Карточка задачи**\n\n"
        f"📖 **Предмет:** {task[1]}\n"
        f"📝 **Тип работы:** {task[2]}\n"
        f"👨‍🏫 **Преподаватель:** {task[3]}\n"
        f"📅 **Дедлайн:** {deadline}\n"
    )
    
    if task[6]:  # comment
        message += f"💬 **Комментарий:** {task[6]}\n"
    
    # Проверяем статус дедлайна
    deadline_date = datetime.strptime(task[4], '%Y-%m-%d').date()
    today = datetime.now().date()
    
    if deadline_date < today:
        message += "\n⚠️ **Дедлайн просрочен!**"
    elif deadline_date == today:
        message += "\n⚠️ **Дедлайн сегодня!**"
    elif (deadline_date - today).days <= 3:
        message += f"\n⚠️ **Осталось {(deadline_date - today).days} дня(ей)!**"
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=get_task_actions_keyboard(task_id)
    )

async def complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отметка задачи как выполненной"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    if db.complete_task(task_id, user_id):
        await query.edit_message_text(
            "✅ Задача отмечена как выполненная!\n\n"
            "Что хотите сделать дальше?",
            reply_markup=get_main_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ Не удалось отметить задачу.",
            reply_markup=get_main_keyboard()
        )

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление задачи"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    if db.delete_task(task_id, user_id):
        await query.edit_message_text(
            "🗑️ Задача удалена!\n\n"
            "Что хотите сделать дальше?",
            reply_markup=get_main_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ Не удалось удалить задачу.",
            reply_markup=get_main_keyboard()
        )

async def edit_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало редактирования задачи"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    tasks = db.get_active_tasks(user_id)
    
    if not tasks:
        await query.edit_message_text(
            "📭 У вас нет активных задач для редактирования.",
            reply_markup=get_main_keyboard()
        )
        return
    
    await query.edit_message_text(
        "Выберите задачу для редактирования:",
        reply_markup=get_task_list_keyboard(tasks)
    )

async def edit_task_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор поля для редактирования"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    context.user_data['editing_task_id'] = task_id
    
    await query.edit_message_text(
        "Что вы хотите изменить?",
        reply_markup=get_edit_options_keyboard(task_id)
    )

async def edit_task_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование поля"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    task_id = int(parts[2])
    field = parts[3]
    
    context.user_data['editing_field'] = field
    context.user_data['editing_task_id'] = task_id
    
    field_names = {
        'subject': 'название предмета',
        'work_type': 'тип работы',
        'teacher': 'ФИО преподавателя',
        'deadline': 'дату дедлайна (в формате ДД.ММ.ГГГГ)',
        'comment': 'комментарий'
    }
    
    await query.edit_message_text(
        f"Введите новое значение для поля '{field_names[field]}':",
        reply_markup=get_cancel_keyboard()
    )
    return 1  # Состояние редактирования

async def save_edited_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение отредактированного поля"""
    user_id = update.effective_user.id
    task_id = context.user_data.get('editing_task_id')
    field = context.user_data.get('editing_field')
    new_value = update.message.text
    
    if field == 'deadline':
        try:
            deadline = datetime.strptime(new_value, '%d.%m.%Y')
            new_value = deadline.strftime('%Y-%m-%d')
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ",
                reply_markup=get_cancel_keyboard()
            )
            return 1
    
    if db.update_task(task_id, user_id, field, new_value):
        await update.message.reply_text(
            "✅ Поле успешно обновлено!",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось обновить поле.",
            reply_markup=get_main_keyboard()
        )
    
    # Очищаем временные данные
    context.user_data.clear()
    return ConversationHandler.END

# Функции для напоминаний
async def send_reminders():
    """Отправка напоминаний о дедлайнах"""
    global application
    
    if not application:
        return
    
    # Задачи за 3 дня
    tasks_3_days = db.get_tasks_by_deadline(3)
    for task in tasks_3_days:
        await send_reminder(task, "за 3 дня")
    
    # Задачи за 1 день
    tasks_1_day = db.get_tasks_by_deadline(1)
    for task in tasks_1_day:
        await send_reminder(task, "завтра")
    
    # Просроченные задачи
    overdue_tasks = db.get_overdue_tasks()
    for task in overdue_tasks:
        await send_reminder(task, "просрочена")

async def send_reminder(task: Tuple, reminder_type: str):
    """Отправка напоминания пользователю"""
    global application
    
    task_id, user_id, subject, work_type, teacher, deadline, comment = task
    deadline_date = datetime.strptime(deadline, '%Y-%m-%d').strftime('%d.%m.%Y')
    
    message = (
        f"⏰ **Напоминание о дедлайне!**\n\n"
        f"📖 {subject}\n"
        f"📝 {work_type}\n"
        f"👨‍🏫 {teacher}\n"
        f"📅 Дедлайн: {deadline_date}\n"
    )
    
    if comment:
        message += f"💬 {comment}\n"
    
    message += f"\n⚠️ Задача {reminder_type}!"
    
    try:
        await application.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания пользователю {user_id}: {e}")

# Основная функция
def main():
    """Запуск бота"""
    global application
    
    # Проверяем наличие токена
    token = os.getenv('BOT_TOKEN')
    if not token or token == 'your_bot_token_here':
        print("❌ Ошибка: Не установлен BOT_TOKEN в файле .env")
        print("Получите токен у @BotFather и добавьте его в файл .env")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Создаем ConversationHandler для добавления задачи
    add_task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_task_start, pattern='^add_task$')],
        states={
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_subject)],
            WORK_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_work_type)],
            TEACHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_teacher)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_deadline)],
            FILE: [
                MessageHandler(filters.Document.ALL, add_task_file),
                CallbackQueryHandler(skip_file, pattern='^skip_file$')
            ],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_comment),
                CallbackQueryHandler(skip_comment, pattern='^skip_comment$')
            ],
            CONFIRM: [CallbackQueryHandler(confirm_save, pattern='^confirm_save$')]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(cancel, pattern='^cancel$')
        ]
    )
    
    # Создаем ConversationHandler для редактирования задачи
    edit_task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_task_start, pattern='^edit_task$')],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_field)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(cancel, pattern='^cancel$')
        ]
    )
    
    # Добавляем обработчики
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(add_task_conv)
    application.add_handler(edit_task_conv)
    application.add_handler(CallbackQueryHandler(list_tasks, pattern='^list_tasks$'))
    application.add_handler(CallbackQueryHandler(show_task, pattern='^task_\\d+$'))
    application.add_handler(CallbackQueryHandler(complete_task, pattern='^complete_\\d+$'))
    application.add_handler(CallbackQueryHandler(delete_task, pattern='^delete_\\d+$'))
    application.add_handler(CallbackQueryHandler(edit_task_select, pattern='^edit_\\d+$'))
    application.add_handler(CallbackQueryHandler(edit_task_field, pattern='^edit_field_\\d+_\\w+$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(cancel, pattern='^back_to_menu$'))
    
    # Запускаем планировщик
    scheduler.add_job(send_reminders, 'cron', hour=9, minute=0)
    scheduler.start()
    
    print("🤖 Бот запущен и готов к работе!")
    print("Нажмите Ctrl+C для остановки")
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
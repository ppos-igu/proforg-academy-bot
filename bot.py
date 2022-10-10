import logging
from aiogram import Bot, Dispatcher, executor, types
import settings
import modules


log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] - %(asctime)s - %(message)s")
token = settings.D_TOKEN if settings.DEBUG else settings.R_TOKEN
bot = Bot(token=token)
dp = Dispatcher(bot)
sql = modules.sqlmanager.Sql()


async def get_tasks(message: types.Message):
    all_task = sql.select(f"SELECT TASK_ID FROM tasks", 0)
    completed_tasks = sql.select(f"SELECT task FROM user_{message.from_user.id}", 0)
    available_tasks = [task[0] for task in all_task if task not in completed_tasks]

    user_id = sql.select(f"SELECT USER_ID FROM users WHERE TG_ID={message.from_user.id}")[0]
    buttons = []
    for task in available_tasks:
        title = sql.select(f"SELECT title FROM tasks WHERE TASK_ID={task}")[0]
        buttons.append({'text': title,'callback': f'settask;{user_id};{task};0'})
    return buttons


@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    if sql.select(f"SELECT USER_ID FROM users WHERE TG_ID={message.from_user.id}") is None:
        sql.update(f'INSERT INTO users(TG_ID) VALUES({message.from_user.id});')
        sql.create_table(f"user_{message.from_user.id}", """
            task INT PRIMARY KEY, 
            score INT
        """)
    await message.answer("Привет, я бот, разработанный для академии профоргов", reply_markup=modules.markup.reply(['Выбрать задание']))


@dp.message_handler(lambda message: message.text == 'Выбрать задание')
async def choose_task(message: types.Message):
    tasks = await get_tasks(message)
    if tasks is None:
        await message.answer('Больше нет доступных заданий!')
        return
    await message.answer('Выберите задание', reply_markup=modules.markup.inline(tasks))


@dp.message_handler(content_types=["photo"])
async def verify_task(message: types.Message): 
    if sql.select(f"SELECT current_task FROM users WHERE TG_ID={message.from_user.id}")[0] is None:
        await message.answer('Нужно выбрать задание нажав на кнопку под полем ввода сообщений!')
        return 
    
    await message.answer('Перекидываем фото...')
    user_id, task_id = sql.select(f"SELECT USER_ID, current_task FROM users WHERE TG_ID={message.from_user.id}")

    buttons = modules.markup.inline([{'text': '⭐️'*value,'callback': f'rate;{user_id};{task_id};{value}'} for value in range(1, 6)])

    await bot.send_photo(596546865, message.photo[-1].file_id, 
        caption=f"Ответ по заданию {task_id}",
        reply_markup=buttons)
    log.info(f'Recieve photo: {message.from_user.id} -> 596546865')


@dp.callback_query_handler()
async def callback_check(callback: types.CallbackQuery):
    await bot.edit_message_reply_markup(callback.message.chat.id, callback.message.message_id)

    action, user_id, task_id, value =  callback.data.split(';')
    user_id, task_id, value = int(user_id), int(task_id), int(value)

    if action == 'rate':
        tg_id = sql.select(f"SELECT TG_ID FROM users WHERE USER_ID={user_id}")[0]
        user_table = f"user_{tg_id}"
        sql.update(f"INSERT INTO {user_table}(task, score) VALUES({task_id}, {value});")
        sql.update(f"UPDATE {user_table} SET score={value} WHERE task={task_id}")
        sql.update(f"UPDATE users SET score=score+{value} WHERE USER_ID={user_id}")

        await bot.send_message(tg_id, f'Вам начисленно {value} баллов!')

    if action == 'settask':
        task_title = sql.select(f"SELECT title FROM tasks WHERE TASK_ID={task_id}")[0]

        await callback.message.answer(f'Вы выбрали {task_title} в качестве активного задания!')
        sql.update(f'UPDATE users SET current_task={task_id} WHERE USER_ID={user_id}')


if __name__ == '__main__':
    sql.create_table("users", """
        USER_ID INTEGER PRIMARY KEY AUTOINCREMENT, 
        TG_ID INT, 
        current_task INT, 
        score INT DEFAULT 0 NOT NULL
    """)
    sql.create_table("tasks", """
        TASK_ID INTEGER PRIMARY KEY AUTOINCREMENT, 
        title TEXT, 
        description TEXT
    """)
    if sql.select("SELECT * FROM tasks") is None:
        import sqlite3

        db = sqlite3.connect('data.db')
        cur = db.cursor()
        cur.executemany("INSERT INTO tasks(title, description) VALUES(?, ?);", settings.TASKS)
        db.commit()

    executor.start_polling(dp)
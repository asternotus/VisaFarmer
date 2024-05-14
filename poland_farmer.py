import time
import asyncio
from threading import Thread
from io import BytesIO
from playwright.async_api import async_playwright
from python_anticaptcha import AnticaptchaClient, ImageToTextTask
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.ext import Job

# Введите ваш ключ API антикапчи и токен Телеграм-бота
api_key = '8af32078ec97f18af3fdedbd5a057fdc'
bot_token = '6167216566:AAFAmhKsPXGEs6eGQc4jAyHSfiaogVI3ue8'

captcha_solver = AnticaptchaClient(api_key)
repeat_interval = 60

def solve_captcha(captcha_image):
    task = ImageToTextTask(fp=BytesIO(captcha_image))
    job = captcha_solver.createTask(task)
    job.join()
    return job.get_captcha_text()

async def get_screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        url = 'https://secure.e-konsulat.gov.pl/placowki/82/karta-polaka/wizyty/weryfikacja-obrazkowa'
        await page.goto(url)
        
        try:
            await page.wait_for_selector("//img[@alt='Weryfikacja obrazkowa']", timeout=30000)
            captcha_image_element = await page.query_selector("//img[@alt='Weryfikacja obrazkowa']")
            captcha_image = await captcha_image_element.screenshot()

            captcha_text = solve_captcha(captcha_image)
            captcha_input = await page.query_selector('//*[@id="mat-input-0"]')
            await captcha_input.fill(captcha_text)
        except Exception as e:
            print(f"Error during captcha processing: {e}")

        await page.wait_for_selector("//button[contains(., 'Dalej')]", timeout=10000)
        button = await page.query_selector("//button[contains(., 'Dalej')]")
        await button.click()

        await page.click('//*[@id="mat-select-0"]')
        await page.click('//*[@id="mat-option-0"]')

        await page.click('//*[@id="mat-select-2"]')
        await page.click('//*[@id="mat-option-9"]')

        await page.click('//*[@id="mat-select-4"]')
        await page.click('//*[@id="mat-option-1"]')

        await page.wait_for_timeout(3000)

        screenshot = await page.screenshot()
        await browser.close()
        
        return screenshot

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Привет! Отправь мне /screenshot, и я сделаю скриншот сайта после выполнения действий.')
    
def stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    context.user_data.pop(chat_id, None)
    update.message.reply_text("Остановлено")

def run_async_task(coroutine, *args, **kwargs):
    asyncio.run(coroutine(*args, **kwargs))

# Измените функцию send_screenshot на асинхронную и переименуйте ее
async def send_screenshot_async(context: CallbackContext) -> None:
    chat_id = context.job.context
    context.bot.send_message(chat_id, 'Получаю скриншот...')
    max_attempts = 3
    success = False
    
    for attempt in range(max_attempts):
        try:
            screenshot_image = await get_screenshot()
            context.bot.send_photo(chat_id, photo=InputFile(BytesIO(screenshot_image), 'screenshot.png'))
            success = True
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)  # Ждем некоторое время перед следующей попыткой

    if not success:
        context.bot.send_message(chat_id, "Я не справился с капчей :( Извините, введите команду /screenshot, чтобы попробовать ещё раз")

    # Запуск повторного вызова через указанный интервал
    context.job_queue.run_once(lambda ctx: Thread(target=run_async_task, args=(send_screenshot_async, ctx)).start(), repeat_interval, context=chat_id)


# Создайте новую синхронную функцию send_screenshot
def send_screenshot(context: CallbackContext) -> None:
    Thread(target=run_async_task, args=(send_screenshot_async, context)).start()

# Измените вызов в функции start_screenshot_job
def start_screenshot_job(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    
    # Проверка на существующую задачу для этого пользователя
    for job in context.job_queue.get_jobs_by_name(str(chat_id)):
        if job.context == chat_id:
            update.message.reply_text("Задача уже запущена. Используйте /stop для остановки.")
            return
        
    context.job_queue.run_once(lambda ctx: Thread(target=run_async_task, args=(send_screenshot_async, ctx)).start(), 0, context=chat_id)


def main() -> None:
    updater = Updater(bot_token)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("screenshot", start_screenshot_job))

    updater.start_polling()  # Запуск бота

    updater.idle()  # Ожидание остановки бота (например, при получении сигнала завершения работы)

if __name__ == '__main__':
    main()

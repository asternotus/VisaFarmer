import time
import asyncio
import logging
from threading import Thread
from io import BytesIO
from playwright.async_api import async_playwright
from python_anticaptcha import AnticaptchaClient, ImageToTextTask
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.ext import Job

# Set up logging to both file and console
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("bot_log.log"),
                        logging.StreamHandler()
                    ])

# Enter your AntiCaptcha API key and Telegram bot token
api_key = '8af32078ec97f18af3fdedbd5a057fdc'
bot_token = '6167216566:AAFAmhKsPXGEs6eGQc4jAyHSfiaogVI3ue8'

captcha_solver = AnticaptchaClient(api_key)
repeat_interval = 300
current_interval = repeat_interval  # Add this line to store the current interval

def solve_captcha(captcha_image):
    logging.info("Starting to solve captcha...")
    task = ImageToTextTask(fp=BytesIO(captcha_image))
    job = captcha_solver.createTask(task)
    job.join()
    captcha_text = job.get_captcha_text()
    logging.info(f"Captcha solved: {captcha_text}")
    return captcha_text

async def get_screenshot():
    logging.info("Launching Playwright browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        logging.info("Browser launched.")
        context = await browser.new_context()
        page = await context.new_page()
        
        url = 'https://secure.e-konsulat.gov.pl/placowki/82/karta-polaka/wizyty/weryfikacja-obrazkowa'
        logging.info(f"Navigating to page: {url}")
        await page.goto(url)
        
        try:
            logging.info("Waiting for captcha element...")
            await page.wait_for_selector("//img[@alt='Weryfikacja obrazkowa']", timeout=30000)
            captcha_image_element = await page.query_selector("//img[@alt='Weryfikacja obrazkowa']")
            logging.info("Captcha element found, taking screenshot...")
            captcha_image = await captcha_image_element.screenshot()
            captcha_text = solve_captcha(captcha_image)
            logging.info(f"Filling captcha: {captcha_text}")
            captcha_input = await page.query_selector('//*[@id="mat-input-0"]')
            await captcha_input.fill(captcha_text)
        except Exception as e:
            logging.error(f"Error during captcha processing: {e}")

        logging.info("Waiting for 'Dalej' button...")
        await page.wait_for_selector("//button[contains(., 'Dalej')]", timeout=10000)
        button = await page.query_selector("//button[contains(., 'Dalej')]")
        await button.click()

        logging.info("Filling forms...")
        await page.click('//*[@id="mat-select-0"]')
        await page.click('//*[@id="mat-option-0"]')
        await page.click('//*[@id="mat-select-2"]')
        await page.click('//*[@id="mat-option-9"]')
        await page.click('//*[@id="mat-select-4"]')
        await page.click('//*[@id="mat-option-1"]')

        logging.info("Waiting 3 seconds before taking a screenshot...")
        await page.wait_for_timeout(3000)

        logging.info("Taking screenshot...")
        screenshot = await page.screenshot()
        await browser.close()
        logging.info("Browser closed.")
        
        return screenshot

def start(update: Update, context: CallbackContext) -> None:
    logging.info(f"Received /start command from user {update.message.chat_id}")
    update.message.reply_text('Hello! Send me /screenshot and I will take a screenshot of the website after performing the actions.')
    
def stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    logging.info(f"Received /stop command from user {chat_id}")
    context.user_data.pop(chat_id, None)
    global current_interval
    current_interval = 99999999  # Set a very large interval to effectively stop the job
    update.message.reply_text("Stopped")

def run_async_task(coroutine, *args, **kwargs):
    logging.info("Running async task...")
    asyncio.run(coroutine(*args, **kwargs))

async def send_screenshot_async(context: CallbackContext) -> None:
    chat_id = context.job.context
    logging.info(f"Starting screenshot process for user {chat_id}")
    context.bot.send_message(chat_id, 'Получаю скриншот...')
    max_attempts = 3
    success = False
    
    for attempt in range(max_attempts):
        try:
            logging.info(f"Attempt {attempt + 1} of {max_attempts}")
            screenshot_image = await get_screenshot()
            context.bot.send_photo(chat_id, photo=InputFile(BytesIO(screenshot_image), 'screenshot.png'))
            success = True
            logging.info("Screenshot sent successfully.")
            break
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(5)  # Wait for a while before the next attempt

    if not success:
        logging.error("Failed to get screenshot after multiple attempts.")
        context.bot.send_message(chat_id, "Сори, я не решил капчу :( Попробую ещё раз")

    logging.info("Scheduling next attempt")
    global current_interval
    context.job_queue.run_once(lambda ctx: Thread(target=run_async_task, args=(send_screenshot_async, ctx)).start(), current_interval, context=chat_id)

def send_screenshot(context: CallbackContext) -> None:
    logging.info(f"Starting send_screenshot function for user {context.job.context}")
    Thread(target=run_async_task, args=(send_screenshot_async, context)).start()

def start_screenshot_job(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    logging.info(f"Received /screenshot command from user {chat_id}")
    
    # Check for existing job for this user
    for job in context.job_queue.get_jobs_by_name(str(chat_id)):
        if job.context == chat_id:
            logging.info("Job already running for this user.")
            update.message.reply_text("A job is already running. Use /stop to stop it.")
            return
    
    global current_interval
    current_interval = repeat_interval  # Reset to the original interval
    
    logging.info("Starting new job to get screenshot.")
    context.job_queue.run_once(lambda ctx: Thread(target=run_async_task, args=(send_screenshot_async, ctx)).start(), 0, context=chat_id)

def main() -> None:
    logging.info("Starting bot...")
    updater = Updater(bot_token)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("screenshot", start_screenshot_job))

    logging.info("Starting long-polling...")
    updater.start_polling()  # Start the bot

    logging.info("Bot started and waiting for commands.")
    updater.idle()  # Wait for the bot to stop (e.g., on receiving a termination signal)
    logging.info("Bot stopped.")

if __name__ == '__main__':
    main()

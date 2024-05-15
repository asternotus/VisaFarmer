import time
import asyncio
from threading import Thread
from io import BytesIO
from playwright.async_api import async_playwright
from python_anticaptcha import AnticaptchaClient, ImageToTextTask
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram.ext import Job

# Enter your AntiCaptcha API key and Telegram bot token
api_key = '8af32078ec97f18af3fdedbd5a057fdc'
bot_token = '6167216566:AAFAmhKsPXGEs6eGQc4jAyHSfiaogVI3ue8'

captcha_solver = AnticaptchaClient(api_key)
repeat_interval = 60

def solve_captcha(captcha_image):
    print("Starting to solve captcha...")
    task = ImageToTextTask(fp=BytesIO(captcha_image))
    job = captcha_solver.createTask(task)
    job.join()
    captcha_text = job.get_captcha_text()
    print(f"Captcha solved: {captcha_text}")
    return captcha_text

async def get_screenshot():
    print("Launching Playwright browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        print("Browser launched.")
        context = await browser.new_context()
        page = await context.new_page()
        
        url = 'https://secure.e-konsulat.gov.pl/placowki/82/karta-polaka/wizyty/weryfikacja-obrazkowa'
        print(f"Navigating to page: {url}")
        await page.goto(url)
        
        try:
            print("Waiting for captcha element...")
            await page.wait_for_selector("//img[@alt='Weryfikacja obrazkowa']", timeout=30000)
            captcha_image_element = await page.query_selector("//img[@alt='Weryfikacja obrazkowa']")
            print("Captcha element found, taking screenshot...")
            captcha_image = await captcha_image_element.screenshot()
            captcha_text = solve_captcha(captcha_image)
            print(f"Filling captcha: {captcha_text}")
            captcha_input = await page.query_selector('//*[@id="mat-input-0"]')
            await captcha_input.fill(captcha_text)
        except Exception as e:
            print(f"Error during captcha processing: {e}")

        print("Waiting for 'Dalej' button...")
        await page.wait_for_selector("//button[contains(., 'Dalej')]", timeout=10000)
        button = await page.query_selector("//button[contains(., 'Dalej')]")
        await button.click()

        print("Filling forms...")
        await page.click('//*[@id="mat-select-0"]')
        await page.click('//*[@id="mat-option-0"]')
        await page.click('//*[@id="mat-select-2"]')
        await page.click('//*[@id="mat-option-9"]')
        await page.click('//*[@id="mat-select-4"]')
        await page.click('//*[@id="mat-option-1"]')

        print("Waiting 3 seconds before taking a screenshot...")
        await page.wait_for_timeout(3000)

        print("Taking screenshot...")
        screenshot = await page.screenshot()
        await browser.close()
        print("Browser closed.")
        
        return screenshot

def start(update: Update, context: CallbackContext) -> None:
    print(f"Received /start command from user {update.message.chat_id}")
    update.message.reply_text('Hello! Send me /screenshot and I will take a screenshot of the website after performing the actions.')
    
def stop(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    print(f"Received /stop command from user {chat_id}")
    context.user_data.pop(chat_id, None)
    update.message.reply_text("Stopped")

def run_async_task(coroutine, *args, **kwargs):
    print("Running async task...")
    asyncio.run(coroutine(*args, **kwargs))

async def send_screenshot_async(context: CallbackContext) -> None:
    chat_id = context.job.context
    print(f"Starting screenshot process for user {chat_id}")
    context.bot.send_message(chat_id, 'Getting screenshot...')
    max_attempts = 3
    success = False
    
    for attempt in range(max_attempts):
        try:
            print(f"Attempt {attempt + 1} of {max_attempts}")
            screenshot_image = await get_screenshot()
            context.bot.send_photo(chat_id, photo=InputFile(BytesIO(screenshot_image), 'screenshot.png'))
            success = True
            print("Screenshot sent successfully.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)  # Wait for a while before the next attempt

    if not success:
        print("Failed to get screenshot after multiple attempts.")
        context.bot.send_message(chat_id, "I couldn't solve the captcha :( Please enter the /screenshot command to try again")

    print("Scheduling next attempt")
    context.job_queue.run_once(lambda ctx: Thread(target=run_async_task, args=(send_screenshot_async, ctx)).start(), repeat_interval, context=chat_id)

def send_screenshot(context: CallbackContext) -> None:
    print(f"Starting send_screenshot function for user {context.job.context}")
    Thread(target=run_async_task, args=(send_screenshot_async, context)).start()

def start_screenshot_job(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    print(f"Received /screenshot command from user {chat_id}")
    
    # Check for existing job for this user
    for job in context.job_queue.get_jobs_by_name(str(chat_id)):
        if job.context == chat_id:
            print("Job already running for this user.")
            update.message.reply_text("A job is already running. Use /stop to stop it.")
            return
        
    print("Starting new job to get screenshot.")
    context.job_queue.run_once(lambda ctx: Thread(target=run_async_task, args=(send_screenshot_async, ctx)).start(), 0, context=chat_id)

def main() -> None:
    print("Starting bot...")
    updater = Updater(bot_token)

    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stop", stop))
    dispatcher.add_handler(CommandHandler("screenshot", start_screenshot_job))

    print("Starting long-polling...")
    updater.start_polling()  # Start the bot

    print("Bot started and waiting for commands.")
    updater.idle()  # Wait for the bot to stop (e.g., on receiving a termination signal)
    print("Bot stopped.")

if __name__ == '__main__':
    main()

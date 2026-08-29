from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import random

TARGET_URL = "https://eit-portal.vercel.app"

def bot_attack():
    print("=" * 50)
    print("   AETHERCEPT — BOT SIMULATOR")
    print("=" * 50)

    # Browser setup
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')  # background mein chalana ho toh uncomment karo
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        print("\n🤖 Bot Starting...")
        driver.get(TARGET_URL)
        time.sleep(2)

        for i in range(30):
            print(f"\n--- Attack Round {i+1} ---")

            # Page refresh
            driver.get(TARGET_URL)
            time.sleep(0.5)

            # Saare links/buttons dhundo aur click karo
            try:
                buttons = driver.find_elements(By.TAG_NAME, 'button')
                links = driver.find_elements(By.TAG_NAME, 'a')
                all_clickable = buttons + links

                if all_clickable:
                    # Random element click karo
                    element = random.choice(all_clickable)
                    element_text = element.text.strip() or "unnamed"
                    driver.execute_script("arguments[0].click();", element)
                    print(f"   Clicked: {element_text}")
                    time.sleep(0.3)  # bot speed — inhuman fast

            except Exception as e:
                print(f"   Click failed: {e}")

            # Back to main page
            driver.get(TARGET_URL)
            time.sleep(0.2)

        print("\n" + "=" * 50)
        print("   ATTACK COMPLETE ✅")
        print("=" * 50)

    finally:
        driver.quit()

if __name__ == "__main__":
    bot_attack()
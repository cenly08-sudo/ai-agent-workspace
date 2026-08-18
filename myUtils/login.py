import asyncio
import sqlite3

from playwright.async_api import async_playwright

from myUtils.auth import check_cookie
from utils.base_social_media import set_init_script
import uuid
from pathlib import Path
from conf import BASE_DIR, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH

# 缁熶竴鑾峰彇娴忚鍣ㄥ惎鍔ㄩ厤缃紙闃查鎺?寮曞叆鏈湴娴忚鍣級
def get_browser_options():
    options = {
        'headless': LOCAL_CHROME_HEADLESS,
        'args': [
            '--disable-blink-features=AutomationControlled',  # 鏍稿績闃茬埇灞忚斀锛氬幓鎺?window.navigator.webdriver 鏍囩
            '--lang=zh-CN',
            '--disable-infobars',
            '--start-maximized'
        ]
    }
    # 濡傛灉鐢ㄦ埛鍦?conf.py 閲岄厤缃簡鏈湴 Chrome锛屽氨鐢ㄦ湰鍦扮殑锛岃繖鏍锋垚鍔熺巼鏋侀珮
    if LOCAL_CHROME_PATH:
        options['executable_path'] = LOCAL_CHROME_PATH

    return options

# 鎶栭煶鐧诲綍
async def douyin_cookie_gen(id,status_queue):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 妫€鏌ユ槸鍚︽槸涓绘鏋剁殑鍙樺寲
        if page.url != original_url:
            url_changed_event.set()
    async with async_playwright() as playwright:
        options = get_browser_options()
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        original_url = page.url
        img_locator = page.get_by_role("img", name="浜岀淮鐮?)
        # 鑾峰彇 src 灞炴€у€?
        src = await img_locator.get_attribute("src")
        print("鉁?鍥剧墖鍦板潃:", src)
        status_queue.put(src)
        # 鐩戝惉椤甸潰鐨?'framenavigated' 浜嬩欢锛屽彧鍏虫敞涓绘鏋剁殑鍙樺寲
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)
        try:
            # 绛夊緟 URL 鍙樺寲鎴栬秴鏃?
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 鏈€澶氱瓑寰?200 绉?
            print("鐩戝惉椤甸潰璺宠浆鎴愬姛")
        except asyncio.TimeoutError:
            print("鐩戝惉椤甸潰璺宠浆瓒呮椂")
            await page.close()
            await context.close()
            await browser.close()
            status_queue.put("500")
            return None
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 纭繚cookiesFile鐩綍瀛樺湪
        cookies_dir = Path(BASE_DIR, "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(3, f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()
        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO user_info (type, filePath, userName, status)
                                VALUES (?, ?, ?, ?)
                                ''', (3, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("鉁?鐢ㄦ埛鐘舵€佸凡璁板綍")
        status_queue.put("200")


# 瑙嗛鍙风櫥褰?
async def get_tencent_cookie(id,status_queue):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 妫€鏌ユ槸鍚︽槸涓绘鏋剁殑鍙樺寲
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': LOCAL_CHROME_HEADLESS,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        # Pause the page, and start recording manually.
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        original_url = page.url

        # 鐩戝惉椤甸潰鐨?'framenavigated' 浜嬩欢锛屽彧鍏虫敞涓绘鏋剁殑鍙樺寲
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        # 绛夊緟 iframe 鍑虹幇锛堟渶澶氱瓑 60 绉掞級
        iframe_locator = page.frame_locator("iframe").first

        # 鑾峰彇 iframe 涓殑绗竴涓?img 鍏冪礌
        img_locator = iframe_locator.get_by_role("img").first

        # 鑾峰彇 src 灞炴€у€?
        src = await img_locator.get_attribute("src")
        print("鉁?鍥剧墖鍦板潃:", src)
        status_queue.put(src)

        try:
            # 绛夊緟 URL 鍙樺寲鎴栬秴鏃?
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 鏈€澶氱瓑寰?200 绉?
            print("鐩戝惉椤甸潰璺宠浆鎴愬姛")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("鐩戝惉椤甸潰璺宠浆瓒呮椂")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 纭繚cookiesFile鐩綍瀛樺湪
        cookies_dir = Path(BASE_DIR, "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(2,f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO user_info (type, filePath, userName, status)
                                VALUES (?, ?, ?, ?)
                                ''', (2, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("鉁?鐢ㄦ埛鐘舵€佸凡璁板綍")
        status_queue.put("200")

# 蹇墜鐧诲綍
async def get_ks_cookie(id,status_queue):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 妫€鏌ユ槸鍚︽槸涓绘鏋剁殑鍙樺寲
        if page.url != original_url:
            url_changed_event.set()
    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': LOCAL_CHROME_HEADLESS,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://cp.kuaishou.com")

        # 瀹氫綅骞剁偣鍑烩€滅珛鍗崇櫥褰曗€濇寜閽紙绫诲瀷涓?link锛?
        await page.get_by_role("link", name="绔嬪嵆鐧诲綍").click()
        await page.get_by_text("鎵爜鐧诲綍").click()
        img_locator = page.get_by_role("img", name="qrcode")
        # 鑾峰彇 src 灞炴€у€?
        src = await img_locator.get_attribute("src")
        original_url = page.url
        print("鉁?鍥剧墖鍦板潃:", src)
        status_queue.put(src)
        # 鐩戝惉椤甸潰鐨?'framenavigated' 浜嬩欢锛屽彧鍏虫敞涓绘鏋剁殑鍙樺寲
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        try:
            # 绛夊緟 URL 鍙樺寲鎴栬秴鏃?
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 鏈€澶氱瓑寰?200 绉?
            print("鐩戝惉椤甸潰璺宠浆鎴愬姛")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("鐩戝惉椤甸潰璺宠浆瓒呮椂")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 纭繚cookiesFile鐩綍瀛樺湪
        cookies_dir = Path(BASE_DIR, "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(4, f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                        INSERT INTO user_info (type, filePath, userName, status)
                                        VALUES (?, ?, ?, ?)
                                        ''', (4, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("鉁?鐢ㄦ埛鐘舵€佸凡璁板綍")
        status_queue.put("200")

# 灏忕孩涔︾櫥褰?
async def xiaohongshu_cookie_gen(id,status_queue):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        # 妫€鏌ユ槸鍚︽槸涓绘鏋剁殑鍙樺寲
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': LOCAL_CHROME_HEADLESS,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.xiaohongshu.com/")
        await page.locator('img.css-wemwzq').click()

        img_locator = page.get_by_role("img").nth(2)
        # 鑾峰彇 src 灞炴€у€?
        src = await img_locator.get_attribute("src")
        original_url = page.url
        print("鉁?鍥剧墖鍦板潃:", src)
        status_queue.put(src)
        # 鐩戝惉椤甸潰鐨?'framenavigated' 浜嬩欢锛屽彧鍏虫敞涓绘鏋剁殑鍙樺寲
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        try:
            # 绛夊緟 URL 鍙樺寲鎴栬秴鏃?
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 鏈€澶氱瓑寰?200 绉?
            print("鐩戝惉椤甸潰璺宠浆鎴愬姛")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("鐩戝惉椤甸潰璺宠浆瓒呮椂")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 纭繚cookiesFile鐩綍瀛樺湪
        cookies_dir = Path(BASE_DIR, "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(1, f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO user_info (type, filePath, userName, status)
                           VALUES (?, ?, ?, ?)
                           ''', (1, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("鉁?鐢ㄦ埛鐘舵€佸凡璁板綍")
        status_queue.put("200")

# a = asyncio.run(xiaohongshu_cookie_gen(4,None))
# print(a)


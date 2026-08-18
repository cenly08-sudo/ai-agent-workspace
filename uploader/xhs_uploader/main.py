import configparser
import json
import pathlib
from time import sleep

import requests
from playwright.sync_api import sync_playwright

from conf import BASE_DIR, XHS_SERVER, LOCAL_CHROME_HEADLESS

config = configparser.RawConfigParser()
config.read('accounts.ini')


def sign_local(uri, data=None, a1="", web_session=""):
    for _ in range(10):
        try:
            with sync_playwright() as playwright:
                stealth_js_path = pathlib.Path(BASE_DIR, "utils/stealth.min.js")
                chromium = playwright.chromium

                # 濡傛灉涓€鐩村け璐ュ彲灏濊瘯璁剧疆鎴?False 璁╁叾鎵撳紑娴忚鍣紝閫傚綋娣诲姞 sleep 鍙煡鐪嬫祻瑙堝櫒鐘舵€?
                browser = chromium.launch(headless=LOCAL_CHROME_HEADLESS)

                browser_context = browser.new_context()
                browser_context.add_init_script(path=stealth_js_path)
                context_page = browser_context.new_page()
                context_page.goto("https://www.xiaohongshu.com")
                browser_context.add_cookies([
                    {'name': 'a1', 'value': a1, 'domain': ".xiaohongshu.com", 'path': "/"}]
                )
                context_page.reload()
                # 杩欎釜鍦版柟璁剧疆瀹屾祻瑙堝櫒 cookie 涔嬪悗锛屽鏋滆繖鍎夸笉 sleep 涓€涓嬬鍚嶈幏鍙栧氨澶辫触浜嗭紝濡傛灉缁忓父澶辫触璇疯缃暱涓€鐐硅瘯璇?
                sleep(2)
                encrypt_params = context_page.evaluate("([url, data]) => window._webmsxyw(url, data)", [uri, data])
                return {
                    "x-s": encrypt_params["X-s"],
                    "x-t": str(encrypt_params["X-t"])
                }
        except Exception:
            # 杩欏効鏈夋椂浼氬嚭鐜?window._webmsxyw is not a function 鎴栨湭鐭ヨ烦杞敊璇紝鍥犳鍔犱竴涓け璐ラ噸璇曡洞
            pass
    raise Exception("閲嶈瘯浜嗚繖涔堝娆¤繕鏄棤娉曠鍚嶆垚鍔燂紝瀵勫瘎瀵?)


def sign(uri, data=None, a1="", web_session=""):
    # 濉啓鑷繁鐨?flask 绛惧悕鏈嶅姟绔彛鍦板潃
    res = requests.post(f"{XHS_SERVER}/sign",
                        json={"uri": uri, "data": data, "a1": a1, "web_session": web_session})
    signs = res.json()
    return {
        "x-s": signs["x-s"],
        "x-t": signs["x-t"]
    }


def beauty_print(data: dict):
    print(json.dumps(data, ensure_ascii=False, indent=2))


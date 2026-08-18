# -*- coding: utf-8 -*-
from datetime import datetime

import asyncio
import inspect
import os
import sys
from pathlib import Path

from patchright.async_api import Page
from patchright.async_api import Playwright
from patchright.async_api import async_playwright

from conf import BASE_DIR, DEBUG_MODE, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from uploader.base_video import BaseVideoUploader
from utils.base_social_media import set_init_script
from utils.login_qrcode import build_login_qrcode_path
from utils.login_qrcode import decode_qrcode_from_path
from utils.login_qrcode import print_terminal_qrcode
from utils.login_qrcode import remove_qrcode_file
from utils.login_qrcode import save_data_url_image
from utils.log import douyin_logger

DOUYIN_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
DOUYIN_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


async def _emit_qrcode_callback(qrcode_callback, payload: dict):
    if not qrcode_callback:
        return

    callback_result = qrcode_callback(payload)
    if inspect.isawaitable(callback_result):
        await callback_result


def _build_login_result(success: bool, status: str, message: str, account_file: str, qrcode: dict | None = None, current_url: str = "") -> dict:
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "qrcode": qrcode,
        "current_url": current_url,
    }


async def _read_verify_code(code_file: str) -> str:
    if os.path.exists(code_file):
        with open(code_file, encoding="utf-8") as file_obj:
            return file_obj.read().strip()

    if not sys.stdin or not sys.stdin.isatty():
        return ""

    try:
        return (await asyncio.to_thread(input, "璇疯緭鍏ユ姈闊崇煭淇￠獙璇佺爜锛堢洿鎺ュ洖杞﹀彲绋嶅悗閲嶈瘯锛? ")).strip()
    except (EOFError, OSError):
        return ""


async def cookie_auth(account_file):
    # 鎶栭煶鏃犲ご浼氭挒鍙嶇埇澧欌啋content/upload 璺崇櫥褰曗啋璇垽 cookie 澶辨晥锛堥棿姝囨€э級銆傛牎楠屽繀椤绘湁澶淬€?
    # 鍗充究鏈夊ご锛岄〉闈㈡參/鐬椂璺宠浆浠嶄細璁?wait_for_url(绮剧‘URL,5s) 璇垽鈫掗噸璇?娆?瀹芥澗鍒ゅ畾(URL鍚?content/upload 涓旀棤鐧诲綍鏂囨)銆?
    # 鍏佽 linux server 鐢ㄦ埛閫氳繃 env var 寮哄埗鏃犲ご: DOUYIN_COOKIE_AUTH_HEADLESS=true
    use_headless = os.environ.get("DOUYIN_COOKIE_AUTH_HEADLESS", "").lower() in ("1", "true", "yes")
    launch_kwargs = {"headless": use_headless, "channel": "chrome", "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"]}
    for _attempt in range(3):
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(**launch_kwargs)
            try:
                context = await browser.new_context(storage_state=account_file)
                context = await set_init_script(context)
                page = await context.new_page()
                await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(2500)  # 绛夐〉闈㈢ǔ瀹氾紝閬垮厤鐬椂璺宠浆璇垽
                has_login = await page.get_by_text("手机号登录").count() or await page.get_by_text("扫码登录").count()
                if "content/upload" in page.url and not has_login:
                    return True
            except Exception:
                pass
            finally:
                await browser.close()
    return False


async def douyin_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless: bool = LOCAL_CHROME_HEADLESS, cdp_url: str | None = None):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            result = _build_login_result(False, "cookie_invalid", "cookie文件不存在或已失效", account_file)
            return result if return_detail else False
        douyin_logger.info(_msg("🥹", "cookie 失效了,准备打开浏览器重新登录"))
        result = await douyin_cookie_gen(account_file, qrcode_callback=qrcode_callback, headless=headless, cdp_url=cdp_url)
        return result if return_detail else result["success"]

    result = _build_login_result(True, "cookie_valid", "cookie鏈夋晥", account_file)
    return result if return_detail else True


async def _extract_douyin_qrcode_src(page: Page) -> str:
    # 绛?SPA 鍔犺浇瀹屾垚锛堜笉鍙瓑"扫码登录"鏂囧瓧锛屽惁鍒欐姈闊虫參鍔犺浇鏃?30s 灏辫秴鏃讹級銆?
    # 缁?domcontentloaded 鍚庤冻澶熸椂闂磋瀹㈡埛绔?JS 娉ㄥ叆鐧诲綍鍗°€?
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    scan_login_tab = page.get_by_text("扫码登录", exact=True).first
    # attached 鐘舵€侊細DOM 閲屽嚭鐜板嵆鍙紝涓嶈姹?visible/娓叉煋瀹屾暣锛岄伩鍏?race
    await scan_login_tab.wait_for(state="attached", timeout=60000)

    # 鏂扮増鎶栭煶鍒涗綔鑰呬腑蹇?(single_tab + animate_qrcode_container) 涓嶅啀鐢?aria-label="浜岀淮鐮?銆?
    # 鎸変紭鍏堢骇鍏滃簳澶氫釜 selector锛岃嚦灏戜竴涓兘鍛戒腑鍗冲彲銆?
    qrcode_selectors = [
        'div#animate_qrcode_container img[src^="data:image"]',
        'div[class*="animate_qrcode_container"] img[src^="data:image"]',
        'div[class*="scan_qrcode_login_content"] img[src^="data:image"]',
        'img[aria-label="浜岀淮鐮?]',
    ]
    last_err: Exception | None = None
    for sel in qrcode_selectors:
        qrcode_img = page.locator(sel).first
        try:
            await qrcode_img.wait_for(state="attached", timeout=10000)
        except Exception as e:
            last_err = e
            continue
        src = await qrcode_img.get_attribute("src")
        if src:
            return src
        last_err = RuntimeError(f"selector {sel} 鍛戒腑浣?src 涓虹┖")

    raise RuntimeError(f"鏈幏鍙栧埌鎶栭煶鐧诲綍浜岀淮鐮佸湴鍧€ (last_err={last_err})")


async def _save_douyin_qrcode(page: Page, account_file: str, previous_qrcode_path: Path | None = None, qrcode_callback=None) -> dict:
    # 鎻愬彇浜岀淮鐮?src 浠呬负浜嗕繚瀛?缁堢鏄剧ず锛涘畾浣嶄笉鍒版椂涓嶈嚧鍛解€斺€旀湁澶存祻瑙堝櫒閲屼簩缁寸爜鍙锛岀洿鎺ユ壂鐮佸嵆鍙?
    try:
        qrcode_src = await _extract_douyin_qrcode_src(page)
    except Exception as exc:
        douyin_logger.warning(_msg("❌", f"娌″畾浣嶅埌浜岀淮鐮佸厓绱狅紙{str(exc)[:50]}锛夆€斺€旇鐩存帴鍦ㄥ脊鍑虹殑娴忚鍣ㄩ噷鎵爜锛屽皬浜虹户缁瓑鐧诲綍璺宠浆"))
        return {"image_path": "", "image_data_url": ""}
    qrcode_path = save_data_url_image(qrcode_src, build_login_qrcode_path(account_file))
    if previous_qrcode_path and previous_qrcode_path != qrcode_path:
        if remove_qrcode_file(previous_qrcode_path):
            douyin_logger.info(_msg("馃Ч", f"涓存椂浜岀淮鐮佹枃浠跺凡娓呯悊: {previous_qrcode_path}"))
    douyin_logger.info(_msg("\u2705", f"二维码已经准备好啦,已保存到: {qrcode_path}"))
    qrcode_content = decode_qrcode_from_path(qrcode_path)
    if qrcode_content:
        print_terminal_qrcode(qrcode_content, qrcode_path, "鎶栭煶APP")
    else:
        douyin_logger.warning(_msg("❌", f"缁堢娌℃硶瀹屾暣鏄剧ず浜岀淮鐮侊紝璇锋墦寮€ {qrcode_path} 鎵爜"))
    qrcode_info = {
        "image_path": str(qrcode_path),
        "image_data_url": qrcode_src,
    }
    await _emit_qrcode_callback(qrcode_callback, qrcode_info)
    return qrcode_info


async def _is_douyin_login_completed(page: Page) -> bool:
    # 鐧诲綍鍚庝細璺冲埌 creator-micro 涓嬩换鎰忛〉锛坔ome/content 绛夛級锛涚櫥褰曢〉鏄?creator.douyin.com/ 鏍硅矾寰?
    if "creator.douyin.com/creator-micro" not in page.url:
        return False

    login_markers = [
        page.get_by_text("扫码登录", exact=True).first,
        page.get_by_text("手机号登录", exact=True).first,
        page.get_by_text("二维码失效", exact=True).first,
        page.get_by_role("img", name="二维码").first,
    ]

    for marker in login_markers:
        if not await marker.count():
            continue
        try:
            if await marker.is_visible():
                return False
        except Exception:
            continue

    return True


async def _wait_for_douyin_login(page: Page, account_file: str, qrcode_info: dict, qrcode_callback=None, poll_interval: int = 3, max_checks: int = 100) -> dict:
    qrcode_path = Path(qrcode_info["image_path"]) if qrcode_info.get("image_path") else None
    original_url = page.url
    saw_2fa = False
    for _ in range(max_checks):
        if await _is_douyin_login_completed(page):
            douyin_logger.info(_msg("馃コ", f"鎵爜鎴愬姛锛屽凡缁忚烦杞埌鐧诲綍鍚庨〉闈? {page.url}"))
            return _build_login_result(True, "success", "鎶栭煶扫码登录鎴愬姛", account_file, qrcode_info, page.url)

        # URL 鍙樺寲 + sessionid 鏈埌浣?鈫?浜岄獙娴佺▼锛岀户缁瓑
        if page.url != original_url and not await _is_douyin_login_completed(page):
            sms_input = page.locator('input[placeholder*="楠岃瘉鐮?], input[type="tel"], input[placeholder*="鐭俊"], input[placeholder*="鎵嬫満鍙?]')
            if await sms_input.count() > 0:
                if not saw_2fa:
                    douyin_logger.warning(_msg("鈿狅笍", f"妫€娴嬪埌鎶栭煶鐭俊/瀹夊叏浜屾楠岃瘉锛岃鍦ㄥ脊鍑虹殑娴忚鍣ㄤ腑鎵嬪姩杈撳叆銆傜瓑寰?sessionid ({i}/{max_checks})"))
                    saw_2fa = True
            await asyncio.sleep(poll_interval)
            continue

        expired_box = page.get_by_text("二维码失效", exact=True).locator("..").first
        if await expired_box.count() and await expired_box.is_visible():
            douyin_logger.warning(_msg("❌", "浜岀淮鐮佸け鏁堜簡锛屽皬浜洪┈涓婂幓鍒锋柊"))
            await expired_box.click()
            await asyncio.sleep(1)
            qrcode_info = await _save_douyin_qrcode(page, account_file, qrcode_path, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"]) if qrcode_info.get("image_path") else None

        await asyncio.sleep(poll_interval)

    return _build_login_result(False, "timeout", "绛夊緟鎶栭煶扫码登录瓒呮椂", account_file, qrcode_info, page.url)


async def douyin_cookie_gen(
    account_file,
    qrcode_callback=None,
    poll_interval: int = 2,
    max_checks: int = 60,
    headless: bool = LOCAL_CHROME_HEADLESS,
    cdp_url: str | None = None,
):
    async with async_playwright() as playwright:
        if cdp_url:
            browser = await playwright.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            should_close_context = False
        else:
            browser = await playwright.chromium.launch(headless=headless, channel="chromium")
            context = await browser.new_context()
            should_close_context = True
        context = await set_init_script(context)
        qrcode_path = None
        result = _build_login_result(False, "failed", "鎶栭煶鐧诲綍澶辫触", account_file)
        try:
            page = await context.new_page()
            await page.goto("https://creator.douyin.com/")
            qrcode_info = await _save_douyin_qrcode(page, account_file, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"]) if qrcode_info.get("image_path") else None
            douyin_logger.info(_msg("馃", "璇锋壂鐮侊紝灏忎汉姝ｅ湪鑰愬績绛夊緟鐧诲綍瀹屾垚"))
            result = await _wait_for_douyin_login(
                page,
                account_file,
                qrcode_info,
                qrcode_callback=qrcode_callback,
                poll_interval=poll_interval,
                max_checks=max_checks,
            )
            if result["success"]:
                await asyncio.sleep(2)
                await context.storage_state(path=account_file)
                if not await cookie_auth(account_file):
                    result = _build_login_result(
                        False,
                        "cookie_invalid",
                        "鎶栭煶鎵爜娴佺▼缁撴潫锛屼絾 cookie 鏍￠獙澶辫触",
                        account_file,
                        qrcode_info,
                        page.url,
                    )
        except Exception as exc:
            result = _build_login_result(False, "failed", str(exc), account_file, current_url=page.url if "page" in locals() else "")
        finally:
            if remove_qrcode_file(qrcode_path):
                douyin_logger.info(_msg("馃Ч", f"涓存椂浜岀淮鐮佹枃浠跺凡娓呯悊: {qrcode_path}"))
            if not result["success"]:
                douyin_logger.error(_msg("馃槩", f"鐧诲綍澶辫触: {result['message']}"))
            if should_close_context:
                await context.close()
            await browser.close()
        return result


class DouYinBaseUploader(BaseVideoUploader):
    def __init__(
        self,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.publish_date = publish_date
        self.account_file = account_file
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.date_format = "%Y骞?m鏈?d鏃?%H:%M"
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = headless

    async def validate_base_args(self):
        if not os.path.exists(self.account_file):
            raise RuntimeError(f"cookie鏂囦欢涓嶅瓨鍦紝璇峰厛瀹屾垚鎶栭煶鐧诲綍: {self.account_file}")
        if not await cookie_auth(self.account_file):
            raise RuntimeError(f"cookie鏂囦欢宸插け鏁堬紝璇峰厛瀹屾垚鎶栭煶鐧诲綍: {self.account_file}")
        if self.publish_strategy not in {DOUYIN_PUBLISH_STRATEGY_IMMEDIATE, DOUYIN_PUBLISH_STRATEGY_SCHEDULED}:
            raise ValueError(f"涓嶆敮鎸佺殑鍙戝竷绛栫暐: {self.publish_strategy}")

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0

    async def set_schedule_time_douyin(self, page, publish_date):
        label_element = page.locator(" param($match) $match.Value.Replace('"', '\"') )")
        await label_element.click()
        await asyncio.sleep(1)
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")

        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="鏃ユ湡鍜屾椂闂?]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)

    async def fill_title_and_description(self, page: Page, title: str, description: str, tags: list[str] | None = None):
        # 2026-06 鎶栭煶鍙戝竷椤?DOM锛氭爣棰?input[placeholder*=濉啓浣滃搧鏍囬]锛屾弿杩?div.zone-container[contenteditable]
        # version_2(post/video) 鍙戝竷椤佃绛夎棰戜笂浼犲畬鎵嶆覆鏌撹〃鍗曪紙瀹炴祴绾?40s锛夛紝鏁呯瓑寰呰秴鏃剁粰鍒?120s
        title_input = page.locator('input[placeholder*="濉啓浣滃搧鏍囬"]').first
        await title_input.wait_for(state="visible", timeout=120000)
        await title_input.fill(title[:30])

        description_editor = page.locator('div.zone-container[contenteditable="true"]').first
        await description_editor.wait_for(state="visible", timeout=120000)
        await description_editor.click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")

        for tag in tags or []:
            await page.keyboard.type(" #" + tag)
            await page.keyboard.press("Space")
        await page.keyboard.press("Escape")  # 鏀惰捣璇濋涓嬫媺锛岄伩鍏嶆诞灞傛嫤鎴悗缁偣鍑?

    async def set_location(self, page: Page, location: str = ""):
        if not location:
            return
        await page.locator('div.semi-select span:has-text("杈撳叆鍦扮悊浣嶇疆")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def handle_product_dialog(self, page: Page, product_title: str):
        await page.wait_for_timeout(2000)
        await page.wait_for_selector('input[placeholder="璇疯緭鍏ュ晢鍝佺煭鏍囬"]', timeout=10000)
        short_title_input = page.locator('input[placeholder="璇疯緭鍏ュ晢鍝佺煭鏍囬"]')
        if not await short_title_input.count():
            douyin_logger.error(_msg("❌", "没找到商品短标题输入框"))
            return False

        product_title = product_title[:10]
        await short_title_input.fill(product_title)
        await page.wait_for_timeout(1000)

        finish_button = page.locator('button:has-text("瀹屾垚缂栬緫")')
        if "disabled" not in await finish_button.get_attribute("class"):
            await finish_button.click()
            douyin_logger.debug(_msg("馃コ", "宸茬偣鍑烩€滃畬鎴愮紪杈戔€濇寜閽?))
            await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
            return True

        douyin_logger.error(_msg("❌", "鈥滃畬鎴愮紪杈戔€濇寜閽槸鐏扮殑锛屽皬浜哄厛鎶婂脊绐楀叧鎺?))
        cancel_button = page.locator('button:has-text("鍙栨秷")')
        if await cancel_button.count():
            await cancel_button.click()
        else:
            close_button = page.locator(".semi-modal-close")
            await close_button.click()
        await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
        return False

    async def set_product_link(self, page: Page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector("text=娣诲姞鏍囩", timeout=10000)
            dropdown = page.get_by_text("娣诲姞鏍囩").locator("..").locator("..").locator("..").locator(".semi-select").first
            if not await dropdown.count():
                douyin_logger.error(_msg("❌", "娌℃壘鍒版爣绛句笅鎷夋"))
                return False
            douyin_logger.debug(_msg("馃", "鎵惧埌鏍囩涓嬫媺妗嗭紝灏忎汉鍑嗗閫夋嫨鈥滆喘鐗╄溅鈥?))
            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text(" param($match) $match.Value.Replace('"', '\"') )
            douyin_logger.debug(_msg("馃コ", "宸茬粡閫変腑鈥滆喘鐗╄溅鈥?))

            await page.wait_for_selector('input[placeholder="绮樿创鍟嗗搧閾炬帴"]', timeout=5000)
            input_field = page.locator('input[placeholder="绮樿创鍟嗗搧閾炬帴"]')
            await input_field.fill(product_link)
            douyin_logger.debug(_msg("馃敆", f"鍟嗗搧閾炬帴宸茬粡濉ソ浜? {product_link}"))

            add_button = page.locator('span:has-text("娣诲姞閾炬帴")')
            button_class = await add_button.get_attribute("class")
            if "disable" in button_class:
                douyin_logger.error(_msg("❌", "鈥滄坊鍔犻摼鎺モ€濇寜閽幇鍦ㄧ偣涓嶄簡"))
                return False
            await add_button.click()
            douyin_logger.debug(_msg("馃コ", "宸茬偣鍑烩€滄坊鍔犻摼鎺モ€濇寜閽?))

            await page.wait_for_timeout(2000)
            error_modal = page.locator("text=鏈悳绱㈠埌瀵瑰簲鍟嗗搧")
            if await error_modal.count():
                confirm_button = page.locator('button:has-text("纭畾")')
                await confirm_button.click()
                douyin_logger.error(_msg("馃槩", "杩欎釜鍟嗗搧閾炬帴鏃犳晥"))
                return False

            if not await self.handle_product_dialog(page, product_title):
                return False

            douyin_logger.debug(_msg("馃コ", "鍟嗗搧閾炬帴璁剧疆濂戒簡"))
            return True
        except Exception as e:
            douyin_logger.error(_msg("馃槩", f"璁剧疆鍟嗗搧閾炬帴鏃跺嚭閿? {str(e)}"))
            return False

    async def set_self_declaration(self, page: Page, declaration: str) -> bool:
        """鎸夎皟鐢ㄦ柟缁欏嚭鐨勫钩鍙板師鏂囬€夋嫨鑷富澹版槑锛涘け璐ヨ繑鍥?False銆?""
        try:
            # 鍙戝竷椤靛簳閮ㄣ€岃嚜涓诲０鏄庛€嶈锛屾湭閫夋椂鏄剧ず鍗犱綅鏂囨銆岃閫夋嫨鑷富澹版槑銆?
            entry = page.get_by_text("璇烽€夋嫨鑷富澹版槑").first
            await entry.wait_for(state="visible", timeout=6000)
            await entry.click()

            # 寮圭獥鏍囬銆屽浣滃搧鍐呭娣诲姞澹版槑銆?
            dialog = page.locator(".semi-modal-content").filter(has_text="瀵逛綔鍝佸唴瀹规坊鍔犲０鏄?).first
            await dialog.wait_for(state="visible", timeout=6000)

            # 鍗曢€夐」锛歋emi 鐨勬枃瀛楁槸 .semi-radio-addon锛堝父甯?pointer-events:none锛岀洿鎺ョ偣浼氬崱 30s 瓒呮椂锛夛紝
            # 瑕佺偣鍙氦浜掔殑 .semi-radio 澶栧眰锛涙壘涓嶅埌澶栧眰鍐嶉€€鍥?force 寮哄埗鐐规枃瀛椼€俥xact 閬垮厤璇懡涓瑙堛€屼綔鑰呭０鏄庯細鈥︺€嶃€?
            option = dialog.locator(".semi-radio").filter(has_text=declaration).first
            if await option.count():
                await option.click(timeout=6000)
            else:
                await dialog.get_by_text(declaration, exact=True).first.click(timeout=6000, force=True)
            await dialog.get_by_role("button", name="纭畾").click(timeout=6000)
            await dialog.wait_for(state="hidden", timeout=6000)
            douyin_logger.info(_msg("馃Ь", f"鑷富澹版槑宸查€夋嫨銆寋declaration}銆?))
            return True
        except Exception as exc:
            douyin_logger.warning(_msg("馃Ь", f"鑷富澹版槑璁剧疆澶辫触锛歿exc}"))
            return False

    async def select_bgm(self, page: Page, bgm_name: str) -> bool:
        """涓哄浘鏂囧彂甯冮€夋嫨 BGM锛氬彲閫夊寮哄姛鑳斤紝鎼滅储鏃犵粨鏋滄垨寮傚父鍧囪烦杩囦笉涓柇鍙戝竷銆?""
        try:
            # 鐐瑰嚮銆岄€夋嫨闊充箰銆嶆寜閽?
            music_entry = page.locator('text="閫夋嫨闊充箰"').nth(1)
            if not await music_entry.count():
                music_entry = page.locator('text="閫夋嫨闊充箰"').first
            await music_entry.wait_for(state="visible", timeout=10000)
            await music_entry.click()

            # 绛夊緟渚ц竟鏍忓嚭鐜板苟鎼滅储
            sidesheet = page.locator(".semi-sidesheet-content").first
            await sidesheet.wait_for(state="visible", timeout=8000)
            search_input = sidesheet.locator('input.semi-input[placeholder="鎼滅储闊充箰"]').first
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill(bgm_name)
            await search_input.press("Enter")

            # 绛夊緟鎼滅储缁撴灉
            await asyncio.sleep(2)
            first_card = sidesheet.locator(".card-container-tmocjc").first
            try:
                await first_card.wait_for(state="visible", timeout=8000)
            except Exception:
                douyin_logger.warning(_msg("馃幍", f"闊充箰銆寋bgm_name}銆嶆悳绱㈢粨鏋滀负绌猴紝灏忎汉璺宠繃"))
                await self._close_music_sidesheet(page)
                return False

            # 鎵撳嵃鎵惧埌鐨勯煶涔愬悕绉?
            try:
                song_name_el = first_card.locator(".song-name-oRge4d").first
                if await song_name_el.count():
                    song_name = await song_name_el.inner_text()
                    douyin_logger.info(_msg("馃幍", f"灏忎汉鎵惧埌浜? {song_name}"))
            except Exception:
                pass

            # JS 鐐瑰嚮銆屼娇鐢ㄣ€嶏紙鎸夐挳 visibility:hidden锛屾櫘閫?click 鏃犳晥锛?
            apply_btn = first_card.locator(".apply-btn-LUPP0D").first
            await apply_btn.evaluate(" param($match) $match.Value.Replace('"', '\"') )")
            douyin_logger.info(_msg("馃コ", f"BGM銆寋bgm_name}銆嶅凡搴旂敤"))

            # 绛夊緟渚ц竟鏍忓叧闂紝瓒呮椂鍒欐墜鍔ㄥ叧闂?
            try:
                await sidesheet.wait_for(state="hidden", timeout=5000)
            except Exception:
                await self._close_music_sidesheet(page)

            return True
        except Exception as exc:
            douyin_logger.warning(_msg("馃幍", f"娣诲姞 BGM 鏃跺嚭閿欙紝璺宠繃璇ユ楠ょ户缁彂甯冿細{exc}"))
            try:
                await self._close_music_sidesheet(page)
            except Exception:
                pass
            return False

    async def _close_music_sidesheet(self, page: Page) -> None:
        try:
            close_btn = page.locator(".semi-sidesheet-close").first
            if await close_btn.count() and await close_btn.is_visible():
                await close_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass


class DouYinVideo(DouYinBaseUploader):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime | int,
        account_file,
        thumbnail_landscape_path=None,
        productLink="",
        productTitle="",
        thumbnail_portrait_path=None,
        desc: str | None = None,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
        declaration: str | None = None,
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
        )
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.thumbnail_landscape_path = thumbnail_landscape_path
        self.thumbnail_portrait_path = thumbnail_portrait_path
        self.productLink = productLink
        self.productTitle = productTitle
        self.desc = desc or ""
        self.declaration = declaration.strip() if declaration and declaration.strip() else None

    async def apply_self_declaration(self, page: Page) -> None:
        if not self.declaration:
            return
        if not await self.set_self_declaration(page, self.declaration):
            raise RuntimeError(f"鑷富澹版槑銆寋self.declaration}銆嶈缃け璐ワ紝鎷掔粷缁х画鍙戝竷")

    async def _submit_sms_verify_code(self, page: Page, sms_input, code: str, code_file: str) -> bool:
        douyin_logger.info(_msg("鉁嶏笍", f"宸茶幏鍙栭獙璇佺爜锛屽噯澶囧～鍏? {code}"))
        await sms_input.click()
        await sms_input.fill(code)
        douyin_logger.info(_msg("鉁?, "楠岃瘉鐮佸凡濉叆杈撳叆妗?))
        await page.wait_for_timeout(500)

        verify_btn = page.locator('div.uc-ui-verify_sms-verify_button:has-text("楠岃瘉")').first
        if await verify_btn.count() and await verify_btn.is_visible():
            try:
                await verify_btn.click(force=True)
                douyin_logger.success(_msg("鉁?, "宸茬偣鍑汇€岄獙璇併€嶆寜閽?(force)"))
            except Exception:
                await page.eval_on_selector('div.uc-ui-verify_sms-verify_button', 'el => el.click()')
                douyin_logger.success(_msg("鉁?, "宸茬偣鍑汇€岄獙璇併€嶆寜閽?(JS)"))
        else:
            verify_by_text = page.get_by_text("楠岃瘉", exact=True).first
            if await verify_by_text.count():
                await verify_by_text.click(force=True)
                douyin_logger.success(_msg("鉁?, "宸茬偣鍑汇€岄獙璇併€嶆寜閽?(text)"))
            else:
                douyin_logger.warning(_msg("鈿狅笍", "鏈壘鍒伴獙璇佹寜閽紝灏濊瘯鎸塃nter"))
                await page.keyboard.press("Enter")

        if os.path.exists(code_file):
            os.remove(code_file)
            douyin_logger.info(_msg("馃Ч", "楠岃瘉鐮佹枃浠跺凡娓呯悊"))

        await page.wait_for_timeout(3000)
        douyin_logger.info(_msg("馃攧", "楠岃瘉鐮佸鐞嗗畬鎴愶紝缁х画鍙戝竷娴佺▼"))
        return True

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("瑙嗛妯″紡涓嬶紝title 鏄繀椤荤殑")

        self.file_path = str(self.validate_video_file(self.file_path))
        if self.thumbnail_landscape_path:
            self.thumbnail_landscape_path = str(self.validate_image_file(self.thumbnail_landscape_path))
        if self.thumbnail_portrait_path:
            self.thumbnail_portrait_path = str(self.validate_image_file(self.thumbnail_portrait_path))

    async def handle_upload_error(self, page):
        douyin_logger.warning(_msg("❌", "瑙嗛涓婁紶鎽斾簡涓€璺わ紝灏忎汉椹笂閲嶆柊涓婁紶"))
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def handle_auto_video_cover(self, page):
        if await page.get_by_text(" param($match) $match.Value.Replace('"', '\"') ):
            douyin_logger.info(_msg("馃", "鍙戝竷鍓嶈繕寰楀厛鎶婂皝闈㈠紕濂?))
            recommend_cover = page.locator('[class^="recommendCover-"]').first
            if await recommend_cover.count():
                douyin_logger.info(_msg("馃弮", "灏忎汉鍘婚€夌涓€涓帹鑽愬皝闈?))
                try:
                    await recommend_cover.click()
                    await asyncio.sleep(1)
                    confirm_text = "鏄惁纭搴旂敤姝ゅ皝闈紵"
                    if await page.get_by_text(confirm_text).first.is_visible():
                        douyin_logger.info(_msg("馃獰", f"寮瑰嚭纭妗嗕簡: {confirm_text}"))
                        await page.get_by_role("button", name="纭畾").click()
                        douyin_logger.info(_msg("馃コ", "鎺ㄨ崘灏侀潰宸茬粡搴旂敤"))
                        await asyncio.sleep(1)
                    douyin_logger.info(_msg("馃コ", "灏侀潰閫夋嫨娴佺▼瀹屾垚"))
                    return True
                except Exception as e:
                    douyin_logger.warning(_msg("❌", f"鎺ㄨ崘灏侀潰娌￠€夋垚鍔? {e}"))
        return False

    async def set_thumbnail(self, page: Page):
        if not self.thumbnail_landscape_path and not self.thumbnail_portrait_path:
            return

        douyin_logger.info(_msg("馃弮", "灏忎汉姝ｅ湪璁剧疆瑙嗛灏侀潰"))
        # 鍏堟竻鎺?shepherd 鏂版墜寮曞娴眰锛屽惁鍒欏畠浼氭嫤鎴€滈€夋嫨灏侀潰鈥濈偣鍑诲鑷村脊绐楁墦涓嶅紑
        await page.evaluate(
            "() => { document.querySelectorAll('.shepherd-element, .shepherd-modal-overlay-container, [class*=\"mention-wrapper\"]').forEach(e => e.remove()); }"
        )
        await page.get_by_text("閫夋嫨灏侀潰", exact=True).first.click(force=True)
        cover_locator_str = 'div.dy-creator-content-modal'
        cover_locator = page.locator(cover_locator_str).first
        await page.wait_for_selector(cover_locator_str, timeout=20000)

        await page.wait_for_timeout(1500)
        # version_2 灏侀潰寮圭獥鏈?4 涓殣钘?file input锛?
        #   [0]/[1] 宸︿晶鈥淎I鐢熸垚鍙傝€冨浘鈥濅笂浼?鏇挎崲锛孾2]/[3] 鎵嶆槸鈥滀笂浼犲皝闈⑩€?鏇挎崲銆?
        # 鏃т唬鐮佺敤 .first 浼犲埌浜?AI 鍙傝€冨浘锛堜笉浼氭垚涓哄皝闈級鈫?杩欏氨鏄€滀紶浜嗗嵈娌″皝闈⑩€濈殑鏍瑰洜銆?
        # 鍙?input.semi-upload-hidden-input 鐨勭 2 涓紙nth(1)锛夛紝鍗崇湡姝ｇ殑灏侀潰涓婁紶杈撳叆銆?
        cover_upload = cover_locator.locator("input.semi-upload-hidden-input").nth(1)

        if self.thumbnail_portrait_path:
            # 寮圭獥榛樿灏卞湪鈥滆缃珫灏侀潰鈥濋〉锛涢槻寰℃€х偣涓€涓?tab锛堝凡婵€娲诲垯蹇界暐锛?
            try:
                await cover_locator.get_by_text(" param($match) $match.Value.Replace('"', '\"') )
            douyin_logger.info(_msg("✅, "绔栫増灏侀潰宸蹭笂浼犲埌棰勮"))
        elif self.thumbnail_landscape_path:
            try:
                await cover_locator.get_by_text(" param($match) $match.Value.Replace('"', '\"') )
            douyin_logger.info(_msg("✅, "妯増灏侀潰宸蹭笂浼犲埌棰勮"))

        # 鐐圭孩鑹蹭富鎸夐挳鈥滃畬鎴愨€濆簲鐢ㄥ皝闈紙exact 閬垮厤璇腑鈥滃畬鎴愮紪杈戔€濓級
        await cover_locator.get_by_role("button", name="瀹屾垚", exact=True).first.click()
        douyin_logger.info(_msg("馃コ", "瑙嗛灏侀潰璁剧疆瀹屾垚"))
        await cover_locator.wait_for(state="detached", timeout=20000)

    async def upload(self, playwright: Playwright) -> None:
        douyin_logger.info(_msg("馃", "灏忎汉鍏堟鏌?cookie銆佽棰戞枃浠躲€佸皝闈㈠拰鍙戝竷鏃堕棿"))
        await self.validate_upload_args()
        douyin_logger.info(_msg("馃コ", "涓婁紶鍓嶆鏌ラ€氳繃"))

        browser = await playwright.chromium.launch(headless=self.headless, channel="chromium")
        context = await browser.new_context(
            storage_state=f"{self.account_file}",
            permissions=["geolocation"],
        )
        context = await set_init_script(context)

        page = await context.new_page()
        await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until="domcontentloaded", timeout=90000)
        douyin_logger.info(_msg("馃弮", f"灏忎汉寮€濮嬫惉杩愯棰? {self.title}.mp4"))
        douyin_logger.info(_msg("馃Л", "灏忎汉姝ｅ湪璧跺線涓婁紶涓婚〉"))
        await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=90000)
        # wait_for_url 瀹屾垚鏃朵笂浼犻〉鍙兘灏氭湭娓叉煋鍑烘枃浠?input锛堝疄娴嬪伓鍙戯級锛屽厛绛夊畠鎸傝浇鍐?set_input_files
        await page.wait_for_selector("div[class^='container'] input", state="attached", timeout=60000)
        await page.locator("div[class^='container'] input").set_input_files(self.file_path)

        while True:
            try:
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page",
                    timeout=3000,
                )
                douyin_logger.info(_msg("馃コ", "宸茬粡杩涘叆 version_1 鍙戝竷椤甸潰"))
                break
            except Exception:
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                        timeout=3000,
                    )
                    douyin_logger.info(_msg("馃コ", "宸茬粡杩涘叆 version_2 鍙戝竷椤甸潰"))
                    break
                except Exception:
                    douyin_logger.debug(_msg("馃", "杩樻病杩涘埌瑙嗛鍙戝竷椤甸潰锛屽皬浜虹户缁瓑涓€浼?))
                    await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        douyin_logger.info(_msg("鉁嶏笍", "灏忎汉寮€濮嬪～鏍囬銆佹弿杩板拰璇濋"))
        await self.fill_title_and_description(page, self.title, self.desc or self.title, self.tags)
        douyin_logger.info(_msg("馃彿锔?, f"灏忎汉涓€鍏辫创浜?{len(self.tags)} 涓瘽棰?))

        while True:
            try:
                number = await page.locator('[class^="long-card"] div:has-text("閲嶆柊涓婁紶")').count()
                if number > 0:
                    douyin_logger.success(_msg("馃コ", "瑙嗛宸茬粡浼犲畬鍟?))
                    break
                douyin_logger.info(_msg("馃弮", "灏忎汉姝ｅ湪鍔姏涓婁紶瑙嗛"))
                await asyncio.sleep(2)
                if await page.locator('div.progress-div > div:has-text("涓婁紶澶辫触")').count():
                    douyin_logger.error(_msg("❌", "妫€娴嬪埌涓婁紶澶辫触锛屽皬浜哄噯澶囬噸璇?))
                    await self.handle_upload_error(page)
            except Exception:
                douyin_logger.debug(_msg("馃", "灏忎汉杩樺湪绛夎棰戜笂浼犲畬鎴?))
                await asyncio.sleep(2)

        if self.productLink and self.productTitle:
            douyin_logger.info(_msg("馃洅", "灏忎汉姝ｅ湪璁剧疆鍟嗗搧閾炬帴"))
            await self.set_product_link(page, self.productLink, self.productTitle)
            douyin_logger.info(_msg("馃コ", "鍟嗗搧閾炬帴璁剧疆瀹屾垚"))

        await self.set_thumbnail(page)

        try:
            await self.apply_self_declaration(page)
        except Exception:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
            raise

        third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        if await page.locator(third_part_element).count():
            if "semi-switch-checked" not in await page.eval_on_selector(third_part_element, "div => div.className"):
                await page.locator(third_part_element).locator("input.semi-switch-native-control").click()

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        sms_prompt_logged = False
        while True:
            try:
                # 绉婚櫎浼氭嫤鎴彂甯冩寜閽偣鍑荤殑鏂版墜寮曞/璇濋涓嬫媺娴眰
                await page.evaluate(
                    "() => { document.querySelectorAll('.shepherd-element, .shepherd-modal-overlay-container, [class*=\"mention-wrapper\"]').forEach(e => e.remove()); }"
                )
                # 妫€娴嬪苟澶勭悊鐭俊楠岃瘉鐮佸脊绐?
                sms_input = page.locator('input[placeholder*="楠岃瘉鐮?], input[type="tel"], input[placeholder*="鐭俊"], input[placeholder*="鎵嬫満鍙?]').first
                if await sms_input.count() and await sms_input.is_visible():
                    douyin_logger.warning(_msg("馃摫", "妫€娴嬪埌鐭俊楠岃瘉鐮佸脊绐?))
                    # 鐐瑰嚮銆岃幏鍙栭獙璇佺爜銆嶆寜閽紙浠呴娆★級
                    get_code_btn = page.get_by_text(" param($match) $match.Value.Replace('"', '\"') )
                        douyin_logger.info(_msg("馃摛", "宸茬偣鍑汇€岃幏鍙栭獙璇佺爜銆嶏紝璇锋煡鐪嬫墜鏈虹煭淇?))
                    code_file = os.path.join(BASE_DIR, "verify_code.txt")
                    code = await _read_verify_code(code_file)
                    if code:
                        sms_prompt_logged = False
                        await self._submit_sms_verify_code(page, sms_input, code, code_file)
                    elif not sms_prompt_logged:
                        douyin_logger.warning(_msg("鈴?, f"绛夊緟楠岃瘉鐮佽緭鍏ワ紱鍙湪浜や簰缁堢鐩存帴杈撳叆锛屾垨鍐欏叆鏂囦欢: {code_file}"))
                        sms_prompt_logged = True
                publish_button = page.get_by_role("button", name="鍙戝竷", exact=True)
                if await publish_button.count():
                    await publish_button.click(force=True)
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/manage**",
                    timeout=3000,
                )
                douyin_logger.success(_msg("馃コ", "瑙嗛鍙戝竷鎴愬姛锛屽皬浜哄紑蹇冩敹宸?))
                break
            except Exception:
                await self.handle_auto_video_cover(page)
                douyin_logger.info(_msg("馃弮", "灏忎汉姝ｅ湪鍐插埡鍙戝竷瑙嗛"))
                if self.debug:
                    await page.screenshot(full_page=True)
                await asyncio.sleep(0.5)

        await context.storage_state(path=self.account_file)
        douyin_logger.success(_msg("馃コ", "cookie 鏇存柊瀹屾瘯"))
        await asyncio.sleep(2)
        await context.close()
        await browser.close()

    async def douyin_upload_video(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)

    async def main(self):
        await self.douyin_upload_video()


class DouYinNote(DouYinBaseUploader):
    def __init__(
        self,
        image_paths,
        note,
        tags,
        publish_date: datetime | int,
        account_file,
        title: str | None = None,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
        bgm: str = "",
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
        )
        self.image_paths = image_paths
        self.note = note or ""
        self.title = title or (self.note[:30] if self.note else "")
        self.tags = tags or []
        self.bgm = bgm or ""

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("鍥炬枃妯″紡涓嬶紝title 鏄繀椤荤殑")

        if len(self.title) > 20:
            raise ValueError(f"鏍囬涓嶈兘瓒呰繃20瀛楃锛屽綋鍓? {len(self.title)}瀛楃")

        if not self.image_paths:
            raise ValueError("鍥炬枃妯″紡涓嬶紝鍥剧墖鏄繀椤荤殑")

        if isinstance(self.image_paths, (str, Path)):
            self.image_paths = [self.image_paths]

        if len(self.image_paths) > 35:
            raise ValueError(" param($match) $match.Value.Replace('"', '\"') ) if self.note else 0
        if note_len > 1000:
            raise ValueError(f"姝ｆ枃涓嶈兘瓒呰繃1000瀛楃锛屽綋鍓? {note_len}瀛楃")

        normalized_image_paths = []
        for image_path in self.image_paths:
            normalized_image_paths.append(str(self.validate_image_file(image_path)))
        self.image_paths = normalized_image_paths

    async def upload_note_content(self, page: Page) -> None:
        douyin_logger.info(_msg("馃弮", f"灏忎汉寮€濮嬫惉杩愬浘鏂囷紝鍏?{len(self.image_paths)} 寮犲浘鐗?))
        douyin_logger.info(_msg("馃攢", "灏忎汉姝ｅ湪鍒囨崲鍒板浘鏂囧彂甯?))
        await page.get_by_text("鍙戝竷鍥炬枃", exact=True).click()
        await page.wait_for_timeout(1000)

        douyin_logger.info(_msg("馃摛", "灏忎汉姝ｅ湪涓婁紶鍥剧墖"))
        await page.locator("div[class^='container'] input[accept*='image']").set_input_files(self.image_paths)

        while True:
            try:
                await page.wait_for_url(
                    "**/creator-micro/content/post/image?**",
                    timeout=3000,
                )
                douyin_logger.info(_msg("馃コ", "宸茬粡杩涘叆鍥炬枃鍙戝竷椤甸潰"))
                break
            except Exception:
                douyin_logger.debug(_msg("馃", "灏忎汉杩樺湪绛夊浘鐗囦笂浼犲畬鎴?))
                await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        douyin_logger.info(_msg("鉁嶏笍", "灏忎汉寮€濮嬪～鏍囬銆佹弿杩板拰璇濋"))
        await self.fill_title_and_description(page, self.title, self.note, self.tags)
        title_len = len(self.title) if self.title else 0
        tags_text = " ".join(f"#{t}" for t in self.tags) if self.tags else ""
        desc_and_tags_len = len(self.note or "") + (len(tags_text) + 2 if self.tags else 0)
        douyin_logger.info(_msg("馃摑", f"鏍囬鎬诲瓧鏁? {title_len}锛屾弿杩?璇濋鎬诲瓧鏁? {desc_and_tags_len}"))
        douyin_logger.info(_msg("馃彿锔?, f"灏忎汉涓€鍏辫创浜?{len(self.tags)} 涓瘽棰?))

        if self.bgm:
            await self.select_bgm(page, self.bgm)

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        while True:
            try:
                publish_button = page.get_by_role("button", name="鍙戝竷", exact=True)
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url(
                    "**/creator-micro/content/manage?enter_from=publish**",
                    timeout=3000,
                )
                douyin_logger.success(_msg("馃コ", "鍥炬枃鍙戝竷鎴愬姛锛屽皬浜哄紑蹇冩敹宸?))
                break
            except Exception:
                douyin_logger.info(_msg("馃弮", "灏忎汉姝ｅ湪鍐插埡鍙戝竷鍥炬枃"))
                await asyncio.sleep(0.5)

    async def upload(self, playwright: Playwright) -> None:
        douyin_logger.info(_msg("馃", "灏忎汉鍏堟鏌?cookie銆佸浘鐗囧拰鍙戝竷鏃堕棿"))
        await self.validate_upload_args()
        douyin_logger.info(_msg("馃コ", "鍥炬枃涓婁紶鍓嶆鏌ラ€氳繃"))

        browser = await playwright.chromium.launch(headless=self.headless, channel="chromium")
        context = await browser.new_context(
            storage_state=f"{self.account_file}",
            permissions=["geolocation"],
        )
        context = await set_init_script(context)

        upload_success = False
        try:
            page = await context.new_page()
            await page.goto("https://creator.douyin.com/creator-micro/content/upload", wait_until="domcontentloaded", timeout=90000)
            douyin_logger.info(_msg("馃Л", "灏忎汉姝ｅ湪璧跺線鍥炬枃鍙戝竷椤?))
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=90000)

            await self.upload_note_content(page)
            upload_success = True
        finally:
            if upload_success:
                await context.storage_state(path=self.account_file)
                douyin_logger.success(_msg("馃コ", "cookie 鏇存柊瀹屾瘯"))
                await asyncio.sleep(2)
            await context.close()
            await browser.close()

    async def douyin_upload_note(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


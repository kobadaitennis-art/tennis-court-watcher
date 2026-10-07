import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "latest.json"
STATE = DATA / "state.json"

URL = "https://k5.p-kashikan.jp/urayasu-city/"


async def click_facility_search(page):
    # 前回成功した複数方式
    for word in [
        "施設の空きを見る",
        "施設 の空きを見る",
        "施設毎の空き状況",
        "施設の空き",
    ]:
        loc = page.get_by_text(word, exact=False)

        for i in range(await loc.count()):
            try:
                item = loc.nth(i)

                if await item.is_visible():
                    await item.click(timeout=8000)
                    return True
            except Exception:
                pass

    # リンクから探す
    links = page.locator("a")

    for i in range(await links.count()):
        try:
            link = links.nth(i)
            text = (await link.inner_text()).strip()
            href = await link.get_attribute("href") or ""

            if "空き" in text or "facility" in href.lower():
                await link.click(timeout=8000)
                return True
        except Exception:
            pass

    return False


async def main():
    DATA.mkdir(exist_ok=True)

    errors = []
    controls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1400, "height": 1200},
        )

        page = await context.new_page()

        try:
            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(5000)

            if not await click_facility_search(page):
                raise RuntimeError(
                    "施設の空きを見るへ移動できません"
                )

            await page.wait_for_timeout(4000)

            elements = page.locator(
                "input, button, select, option, label, a"
            )

            count = await elements.count()

            for i in range(min(count, 1000)):
                el = elements.nth(i)

                try:
                    info = await el.evaluate(
                        """
                        (e) => ({
                            tag: e.tagName,
                            text:
                                (e.innerText ||
                                 e.textContent ||
                                 '').trim(),
                            id:
                                e.id || null,
                            name:
                                e.getAttribute('name'),
                            type:
                                e.getAttribute('type'),
                            value:
                                e.getAttribute('value'),
                            href:
                                e.getAttribute('href'),
                            for_attr:
                                e.getAttribute('for'),
                            placeholder:
                                e.getAttribute(
                                    'placeholder'
                                ),
                            checked:
                                e.checked === true,
                            disabled:
                                e.disabled === true
                        })
                        """
                    )

                    # 空データは除外
                    if any([
                        info.get("text"),
                        info.get("id"),
                        info.get("name"),
                        info.get("value"),
                        info.get("href"),
                    ]):
                        controls.append(info)

                except Exception:
                    pass

            body = await page.locator(
                "body"
            ).inner_text()

            print(
                json.dumps(
                    controls,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        except Exception as e:
            errors.append(
                f"浦安市: {type(e).__name__}: {e}"
            )

            body = ""

        finally:
            await browser.close()

    payload = {
        "checked_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "mode":
            "urayasu_controls_diagnostic",

        "new_or_reopened": [],

        "current": {},

        "errors": errors,

        "page_text":
            body[:20000],

        "controls":
            controls,
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 既存状態はまだ変更しない
    if not STATE.exists():
        STATE.write_text(
            json.dumps(
                {"current": {}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print("FINAL RESULT")
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

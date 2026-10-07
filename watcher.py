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

TARGET_FACILITIES = [
    "運動公園テニスコート",
    "中央公園テニスコート",
    "美浜運動公園テニスコート",
    "高洲中央公園テニスコート",
    "高洲テニスコート",
    "美浜テニスコート",
    "舞浜テニスコート",
    "高洲南テニスコート",
]


async def dump_controls(page, label):
    print("\n" + "=" * 80)
    print(f"DEBUG: {label}")
    print("=" * 80)

    print("URL:", page.url)
    print("TITLE:", await page.title())

    body = await page.locator("body").inner_text()
    print("\nBODY:")
    print(body[:20000])

    print("\nCHECKBOX / RADIO:")
    controls = page.locator('input[type="checkbox"], input[type="radio"]')
    for i in range(min(await controls.count(), 300)):
        el = controls.nth(i)
        try:
            print(
                i,
                "type=", await el.get_attribute("type"),
                "id=", await el.get_attribute("id"),
                "name=", await el.get_attribute("name"),
                "value=", await el.get_attribute("value"),
                "checked=", await el.is_checked(),
            )
        except Exception:
            pass

    print("\nLABELS:")
    labels = page.locator("label")
    for i in range(min(await labels.count(), 300)):
        try:
            txt = (await labels.nth(i).inner_text()).strip()
            if txt:
                print(i, repr(txt),
                      "for=", await labels.nth(i).get_attribute("for"))
        except Exception:
            pass

    print("\nBUTTONS:")
    buttons = page.locator("button")
    for i in range(min(await buttons.count(), 200)):
        try:
            txt = (await buttons.nth(i).inner_text()).strip()
            print(i, repr(txt))
        except Exception:
            pass


async def click_text(page, text):
    loc = page.get_by_text(text, exact=False)
    count = await loc.count()

    print(f"SEARCH TEXT {text!r}: count={count}")

    if count:
        for i in range(count):
            candidate = loc.nth(i)
            try:
                if await candidate.is_visible():
                    print("CLICK:", repr(await candidate.inner_text()))
                    await candidate.click(timeout=10000)
                    return True
            except Exception as e:
                print("CLICK FAILED:", e)

    return False


async def main():
    DATA.mkdir(exist_ok=True)

    errors = []
    diagnostics = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1400, "height": 1200},
        )

        page = await context.new_page()

        try:
            print("=== URAYASU START ===")

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(2500)

            if not await click_text(page, "施設の空きを見る"):
                raise RuntimeError(
                    "施設の空きを見る をクリックできません"
                )

            await page.wait_for_timeout(3000)

            await dump_controls(
                page,
                "FACILITY SEARCH PAGE",
            )

            #
            # 1. 「テニス」を選択
            #
            print("\n>>> テニスを選択")

            tennis = page.get_by_text(
                "テニス",
                exact=True,
            )

            tennis_count = await tennis.count()
            print("tennis count =", tennis_count)

            tennis_clicked = False

            for i in range(tennis_count):
                try:
                    item = tennis.nth(i)

                    if await item.is_visible():
                        print(
                            "tennis candidate:",
                            await item.evaluate(
                                "(e) => e.outerHTML"
                            ),
                        )

                        await item.click(
                            timeout=10000
                        )

                        tennis_clicked = True
                        print("テニスクリック成功")
                        break

                except Exception as e:
                    print(
                        "tennis click error:",
                        e,
                    )

            if not tennis_clicked:
                print(
                    "テニス文字を直接クリックできませんでした"
                )

            await page.wait_for_timeout(2500)

            await dump_controls(
                page,
                "AFTER TENNIS CLICK",
            )

            #
            # 2. 対象施設を探す
            #
            print("\n>>> 対象施設を確認")

            body = await page.locator(
                "body"
            ).inner_text()

            found = []

            for facility in TARGET_FACILITIES:
                if facility in body:
                    found.append(facility)
                    print(
                        "FOUND FACILITY:",
                        facility,
                    )
                else:
                    print(
                        "NOT FOUND:",
                        facility,
                    )

            diagnostics.append(
                {
                    "step": "facility_detection",
                    "found": found,
                }
            )

            #
            # 3. 施設をクリックしてみる
            #
            print("\n>>> 施設選択テスト")

            selected = []

            for facility in TARGET_FACILITIES:
                loc = page.get_by_text(
                    facility,
                    exact=False,
                )

                count = await loc.count()

                print(
                    facility,
                    "count=",
                    count,
                )

                if not count:
                    continue

                for i in range(count):
                    try:
                        item = loc.nth(i)

                        if not await item.is_visible():
                            continue

                        html = await item.evaluate(
                            "(e) => e.outerHTML"
                        )

                        print(
                            "FACILITY HTML:",
                            html,
                        )

                        await item.click(
                            timeout=5000
                        )

                        selected.append(
                            facility
                        )

                        print(
                            "SELECTED:",
                            facility,
                        )

                        break

                    except Exception as e:
                        print(
                            "facility click error:",
                            facility,
                            e,
                        )

            await page.wait_for_timeout(2500)

            await dump_controls(
                page,
                "AFTER FACILITY SELECTION",
            )

            #
            # 4. 検索ボタンを調査
            #
            print("\n>>> 検索ボタン候補")

            search_words = [
                "検索",
                "次へ",
                "表示",
                "空き状況",
            ]

            search_candidates = []

            for word in search_words:
                loc = page.get_by_text(
                    word,
                    exact=True,
                )

                count = await loc.count()

                print(
                    word,
                    "count=",
                    count,
                )

                for i in range(count):
                    try:
                        el = loc.nth(i)

                        if await el.is_visible():
                            html = await el.evaluate(
                                "(e) => e.outerHTML"
                            )

                            search_candidates.append(
                                {
                                    "word": word,
                                    "html": html,
                                }
                            )

                            print(
                                "SEARCH CANDIDATE:",
                                word,
                                html,
                            )

                    except Exception:
                        pass

            diagnostics.append(
                {
                    "step": "selection",
                    "selected": selected,
                    "search_candidates":
                        search_candidates,
                }
            )

            #
            # 最終画面のHTML構造も取得
            #
            html = await page.content()

            print("\nHTML EXCERPT:")
            print(html[:30000])

        except Exception as e:
            error = (
                f"浦安市: "
                f"{type(e).__name__}: {e}"
            )

            errors.append(error)

            print("\nERROR:")
            print(error)

            try:
                await dump_controls(
                    page,
                    "ERROR PAGE",
                )
            except Exception:
                pass

        finally:
            await browser.close()

    payload = {
        "checked_at":
            datetime.now()
            .astimezone()
            .isoformat(),
        "mode":
            "urayasu_selector_diagnostic",
        "new_or_reopened": [],
        "current": {},
        "errors": errors,
        "diagnostics": diagnostics,
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 診断中は既存stateを壊さない
    if not STATE.exists():
        STATE.write_text(
            json.dumps(
                {"current": {}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print("\n" + "=" * 80)
    print("FINAL RESULT")
    print("=" * 80)

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

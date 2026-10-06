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


async def dump_page(page, label):
    print("\n" + "=" * 80)
    print(f"DEBUG STEP: {label}")
    print("=" * 80)

    print("URL:")
    print(page.url)

    print("\nTITLE:")
    print(await page.title())

    print("\nBODY TEXT:")
    try:
        body = await page.locator("body").inner_text()
        print(body[:15000])
    except Exception as e:
        print(f"BODY ERROR: {e}")

    print("\nLINKS:")
    try:
        links = await page.locator("a").all()
        for i, link in enumerate(links[:200]):
            try:
                text = (await link.inner_text()).strip().replace("\n", " ")
                href = await link.get_attribute("href")
                print(f"[A {i}] text={text!r} href={href!r}")
            except Exception:
                pass
    except Exception as e:
        print(f"LINK ERROR: {e}")

    print("\nBUTTONS:")
    try:
        buttons = await page.locator("button").all()
        for i, button in enumerate(buttons[:200]):
            try:
                text = (await button.inner_text()).strip().replace("\n", " ")
                print(f"[BUTTON {i}] text={text!r}")
            except Exception:
                pass
    except Exception as e:
        print(f"BUTTON ERROR: {e}")

    print("\nINPUTS:")
    try:
        inputs = await page.locator("input").all()
        for i, inp in enumerate(inputs[:200]):
            try:
                print(
                    f"[INPUT {i}] "
                    f"type={await inp.get_attribute('type')!r} "
                    f"name={await inp.get_attribute('name')!r} "
                    f"value={await inp.get_attribute('value')!r} "
                    f"placeholder={await inp.get_attribute('placeholder')!r}"
                )
            except Exception:
                pass
    except Exception as e:
        print(f"INPUT ERROR: {e}")

    print("\nSELECTS:")
    try:
        selects = await page.locator("select").all()
        for i, select in enumerate(selects[:100]):
            try:
                print(
                    f"[SELECT {i}] "
                    f"name={await select.get_attribute('name')!r} "
                    f"id={await select.get_attribute('id')!r}"
                )
            except Exception:
                pass
    except Exception as e:
        print(f"SELECT ERROR: {e}")


async def main():
    DATA.mkdir(exist_ok=True)

    errors = []
    diagnostics = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1400, "height": 1000},
        )

        page = await context.new_page()

        try:
            print("浦安市公共施設予約システムへ接続します")
            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(3000)

            await dump_page(page, "TOP PAGE")

            top_url = page.url

            print("\n>>> 「施設の空きを見る」を探します")

            candidates = [
                page.get_by_text("施設の空きを見る", exact=False),
                page.get_by_text("施設 の空きを見る", exact=False),
                page.get_by_text("施設毎の空き状況", exact=False),
            ]

            clicked = False

            for locator in candidates:
                try:
                    count = await locator.count()
                    print(f"候補 count={count}")

                    if count > 0:
                        target = locator.first

                        print("クリック候補:")
                        try:
                            print(await target.inner_text())
                        except Exception:
                            pass

                        await target.click(timeout=10000)
                        clicked = True
                        print("クリック成功")
                        break

                except Exception as e:
                    print(f"クリック候補失敗: {e}")

            if not clicked:
                raise RuntimeError(
                    "「施設の空きを見る」をクリックできませんでした"
                )

            try:
                await page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=15000,
                )
            except Exception:
                pass

            await page.wait_for_timeout(4000)

            await dump_page(page, "AFTER FACILITY SEARCH CLICK")

            diagnostics.append(
                {
                    "step": "facility_search",
                    "top_url": top_url,
                    "result_url": page.url,
                    "title": await page.title(),
                    "body_excerpt": (
                        await page.locator("body").inner_text()
                    )[:5000],
                }
            )

            # 次画面にテニス関連の文字があるか調査
            body = await page.locator("body").inner_text()

            tennis_words = [
                line.strip()
                for line in body.splitlines()
                if "テニス" in line
            ]

            print("\n" + "=" * 80)
            print("TENNIS RELATED TEXT")
            print("=" * 80)

            if tennis_words:
                for line in tennis_words[:200]:
                    print(line)
            else:
                print("この画面には「テニス」という文字は見つかりませんでした")

            diagnostics.append(
                {
                    "step": "tennis_text",
                    "matches": tennis_words[:200],
                }
            )

        except Exception as e:
            error = f"浦安市: {type(e).__name__}: {e}"
            errors.append(error)
            print("\nERROR:")
            print(error)

            try:
                await dump_page(page, "ERROR PAGE")
            except Exception:
                pass

        finally:
            await browser.close()

    payload = {
        "checked_at": datetime.now().astimezone().isoformat(),
        "mode": "urayasu_diagnostic",
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

    # 調査中なので既存の空き状態は変更しない
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

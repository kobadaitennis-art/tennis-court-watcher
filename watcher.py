import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "latest.json"

URL = "https://k5.p-kashikan.jp/urayasu-city/"


async def click_text(page, text):
    loc = page.get_by_text(text, exact=True)

    for i in range(await loc.count()):
        try:
            el = loc.nth(i)

            if await el.is_visible():
                await el.click(
                    timeout=10000,
                    no_wait_after=True,
                )
                return True

        except Exception:
            pass

    return False


async def main():
    DATA.mkdir(exist_ok=True)

    errors = []
    result = {}

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={
                "width": 1400,
                "height": 1600,
            },
        )

        page = await context.new_page()

        try:
            # 1. トップページ
            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(3000)

            print("STEP 1 TOP")
            print(
                (
                    await page.locator("body")
                    .inner_text()
                )[:10000]
            )

            # 2. 空き状況の確認
            ok = await click_text(
                page,
                "空き状況の確認",
            )

            if not ok:
                # 表記違い対策
                ok = await click_text(
                    page,
                    "施設の空きを見る",
                )

            if not ok:
                raise RuntimeError(
                    "空き状況の確認を押せません"
                )

            await page.wait_for_timeout(3000)

            print("STEP 2 VACANCY PAGE")
            print("URL:", page.url)

            # 3. 目的で検索
            ok = await click_text(
                page,
                "目的で検索",
            )

            if not ok:
                # onclick が判明しているので予備
                purpose = page.locator(
                    'a[onclick*="srch_mkt"]'
                )

                if await purpose.count():
                    await purpose.first.click(
                        timeout=10000,
                        no_wait_after=True,
                    )
                    ok = True

            if not ok:
                raise RuntimeError(
                    "目的で検索を押せません"
                )

            await page.wait_for_timeout(3000)

            print("STEP 3 PURPOSE SEARCH")
            print("URL:", page.url)

            # 4. テニス
            tennis = page.locator(
                'input[name="condition_chk[61][]"]'
                '[value="01"]'
            )

            if await tennis.count():

                await tennis.first.check()

            else:
                ok = await click_text(
                    page,
                    "テニス",
                )

                if not ok:
                    raise RuntimeError(
                        "テニスを選択できません"
                    )

            await page.wait_for_timeout(1000)

            print("STEP 4 TENNIS SELECTED")

            # 5. 検索
            search_buttons = page.locator(
                'button[name="searchBtn"],'
                'input[name="searchBtn"]'
            )

            clicked = False

            for i in range(
                await search_buttons.count()
            ):
                try:
                    b = search_buttons.nth(i)

                    if await b.is_visible():

                        await b.click(
                            timeout=10000,
                            no_wait_after=True,
                        )

                        clicked = True
                        break

                except Exception:
                    pass

            if not clicked:

                ok = await click_text(
                    page,
                    "検索",
                )

                if not ok:
                    raise RuntimeError(
                        "検索を押せません"
                    )

            await page.wait_for_timeout(6000)

            # 6. 結果取得
            body = await page.locator(
                "body"
            ).inner_text()

            print("STEP 5 RESULT")
            print("URL:", page.url)
            print(body[:50000])

            # 表をそのまま保存
            tables = []

            table_loc = page.locator("table")

            for t in range(
                await table_loc.count()
            ):

                table = table_loc.nth(t)

                rows = []

                trs = table.locator("tr")

                for r in range(
                    await trs.count()
                ):

                    cells = (
                        trs.nth(r)
                        .locator("th, td")
                    )

                    row = []

                    for c in range(
                        await cells.count()
                    ):

                        cell = cells.nth(c)

                        try:
                            row.append({
                                "text":
                                    (
                                        await cell
                                        .inner_text()
                                    ).strip(),

                                "html":
                                    (
                                        await cell
                                        .inner_html()
                                    )[:2000],
                            })

                        except Exception:
                            pass

                    if row:
                        rows.append(row)

                if rows:
                    tables.append(rows)

            result = {
                "url": page.url,
                "page_text": body[:50000],
                "tables": tables,
            }

        except Exception as e:

            errors.append(
                "浦安市: "
                + type(e).__name__
                + ": "
                + str(e)
            )

            print("ERROR:", errors[-1])

        finally:
            await browser.close()

    payload = {
        "checked_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "mode":
            "urayasu_simple_4step",

        "errors":
            errors,

        "result":
            result,
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

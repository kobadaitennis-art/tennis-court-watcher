import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "latest.json"

URL = "https://k5.p-kashikan.jp/urayasu-city/"
TARGET_DATE = "2026/10/10"
TARGET_DAY = "10"


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
        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1400, "height": 1600},
        )

        page = await context.new_page()

        try:
            # 1. トップページ
            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(2500)

            print("STEP 1: TOP")

            # 2. 空き状況の確認
            ok = await click_text(
                page,
                "空き状況の確認",
            )

            if not ok:
                ok = await click_text(
                    page,
                    "施設の空きを見る",
                )

            if not ok:
                raise RuntimeError(
                    "空き状況の確認を押せません"
                )

            await page.wait_for_timeout(2500)

            print("STEP 2: VACANCY")

            # 3. 目的で検索
            ok = await click_text(
                page,
                "目的で検索",
            )

            if not ok:
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

            await page.wait_for_timeout(2500)

            print("STEP 3: PURPOSE SEARCH")

            # 4. 画面に表示されているカレンダーから
            #    10/10 の「10」を直接選択
            days = page.get_by_text(
                TARGET_DAY,
                exact=True,
            )

            print(
                "10 candidates:",
                await days.count(),
            )

            date_selected = False

            for i in range(await days.count()):
                try:
                    el = days.nth(i)

                    if not await el.is_visible():
                        continue

                    info = await el.evaluate(
                        """
                        e => ({
                            tag: e.tagName,
                            text: e.innerText,
                            html: e.outerHTML,
                            parent:
                                e.parentElement
                                ? e.parentElement.outerHTML
                                : ""
                        })
                        """
                    )

                    print(
                        "DATE CANDIDATE:",
                        json.dumps(
                            info,
                            ensure_ascii=False,
                        )[:5000]
                    )

                    # カレンダー内にある10を優先
                    in_table = await el.evaluate(
                        """
                        e => !!e.closest('table')
                        """
                    )

                    if not in_table:
                        continue

                    try:
                        await el.click(
                            timeout=10000,
                            no_wait_after=True,
                        )

                        date_selected = True
                        print(
                            "DATE SELECTED:",
                            TARGET_DATE,
                        )
                        break

                    except Exception:
                        # 親要素がクリック対象の場合
                        parent = el.locator("..")

                        await parent.click(
                            timeout=10000,
                            no_wait_after=True,
                        )

                        date_selected = True
                        print(
                            "DATE SELECTED VIA PARENT:",
                            TARGET_DATE,
                        )
                        break

                except Exception as e:
                    print(
                        "DATE ERROR:",
                        str(e),
                    )

            if not date_selected:
                raise RuntimeError(
                    "10/10を選択できません"
                )

            await page.wait_for_timeout(2000)

            # 5. テニスを選択
            tennis = page.locator(
                'input[name="condition_chk[61][]"]'
                '[value="01"]'
            )

            tennis_selected = False

            if await tennis.count():
                try:
                    await tennis.first.check(
                        force=True
                    )
                    tennis_selected = True
                except Exception:
                    pass

            if not tennis_selected:
                tennis_selected = await click_text(
                    page,
                    "テニス",
                )

            if not tennis_selected:
                raise RuntimeError(
                    "テニスを選択できません"
                )

            print("STEP 5: TENNIS")

            await page.wait_for_timeout(1000)

            # 6. 検索
            search_buttons = page.locator(
                'button[name="searchBtn"], '
                'input[name="searchBtn"]'
            )

            searched = False

            for i in range(
                await search_buttons.count()
            ):
                try:
                    button = search_buttons.nth(i)

                    if await button.is_visible():
                        await button.click(
                            timeout=10000,
                            no_wait_after=True,
                        )
                        searched = True
                        break

                except Exception:
                    pass

            if not searched:
                searched = await click_text(
                    page,
                    "検索",
                )

            if not searched:
                raise RuntimeError(
                    "検索を押せません"
                )

            await page.wait_for_timeout(5000)

            print("STEP 6: SEARCH COMPLETE")

            # 7. 検索結果
            body = await page.locator(
                "body"
            ).inner_text()

            print(body[:50000])

            # 全テーブルを保存
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
                                "text": (
                                    await cell.inner_text()
                                ).strip(),
                                "html": (
                                    await cell.inner_html()
                                )[:1500],
                            })
                        except Exception:
                            pass

                    if row:
                        rows.append(row)

                if rows:
                    tables.append(rows)

            # ○ / 〇 / ● の数も確認
            open_cells = []

            cells = page.locator("td")

            for i in range(
                await cells.count()
            ):
                try:
                    cell = cells.nth(i)

                    text = (
                        await cell.inner_text()
                    ).strip()

                    if text in ("○", "〇", "●"):
                        open_cells.append({
                            "text": text,
                            "html": (
                                await cell.inner_html()
                            )[:1500],
                        })

                except Exception:
                    pass

            print(
                "OPEN COUNT:",
                len(open_cells),
            )

            result = {
                "target_date": TARGET_DATE,
                "url": page.url,
                "open_count": len(open_cells),
                "open_cells": open_cells,
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

            print(
                "ERROR:",
                errors[-1],
            )

        finally:
            await browser.close()

    payload = {
        "checked_at": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),
        "mode": "urayasu_direct_calendar_test",
        "target_date": TARGET_DATE,
        "errors": errors,
        "result": result,
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

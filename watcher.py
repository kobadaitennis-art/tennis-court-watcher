import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "latest.json"

URL = "https://k5.p-kashikan.jp/urayasu-city/"

# 今回のテスト日
TARGET_DATE = "2026/10/10"


async def click_visible_text(page, text):
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

            # ==================================
            # 1. トップ
            # ==================================

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(3000)

            print("STEP 1 TOP")

            # ==================================
            # 2. 空き状況の確認
            # ==================================

            ok = await click_visible_text(
                page,
                "空き状況の確認",
            )

            if not ok:
                ok = await click_visible_text(
                    page,
                    "施設の空きを見る",
                )

            if not ok:
                raise RuntimeError(
                    "空き状況の確認を押せません"
                )

            await page.wait_for_timeout(3000)

            print("STEP 2 VACANCY")

            # ==================================
            # 3. 目的で検索
            # ==================================

            ok = await click_visible_text(
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

            await page.wait_for_timeout(3000)

            print("STEP 3 PURPOSE")

            # ==================================
            # 4. カレンダーを開く
            # ==================================

            calendar = page.get_by_text(
                "カレンダーを開く",
                exact=False,
            )

            opened = False

            for i in range(
                await calendar.count()
            ):
                try:

                    el = calendar.nth(i)

                    if await el.is_visible():

                        await el.click(
                            timeout=10000,
                            no_wait_after=True,
                        )

                        opened = True
                        break

                except Exception:
                    pass

            if not opened:
                raise RuntimeError(
                    "カレンダーを開けません"
                )

            await page.wait_for_timeout(2000)

            print("STEP 4 CALENDAR OPEN")

            # ==================================
            # 5. 10/10を選択
            # ==================================

            target_day = "10"

            day_candidates = page.get_by_text(
                target_day,
                exact=True,
            )

            print(
                "DAY CANDIDATES:",
                await day_candidates.count()
            )

            selected = False

            for i in range(
                await day_candidates.count()
            ):

                try:

                    el = day_candidates.nth(i)

                    if not await el.is_visible():
                        continue

                    html = await el.evaluate(
                        "(e) => e.outerHTML"
                    )

                    print(
                        "DAY HTML:",
                        html
                    )

                    # カレンダー内のクリック可能な10を優先
                    clickable = await el.evaluate(
                        """
                        (e) => {
                            const tag =
                                e.tagName.toLowerCase();

                            return (
                                tag === 'a' ||
                                tag === 'button' ||
                                !!e.onclick ||
                                !!e.closest('a') ||
                                !!e.closest('button')
                            );
                        }
                        """
                    )

                    if clickable:

                        await el.click(
                            timeout=10000,
                            no_wait_after=True,
                        )

                        selected = True
                        break

                except Exception as e:

                    print(
                        "DAY CLICK ERROR:",
                        e
                    )

            if not selected:

                # 日付リンク等の属性から探す
                candidates = page.locator(
                    'a, button, input'
                )

                for i in range(
                    await candidates.count()
                ):

                    try:

                        el = candidates.nth(i)

                        if not await el.is_visible():
                            continue

                        info = await el.evaluate(
                            """
                            (e) => ({
                                text:
                                    (e.innerText ||
                                     e.value ||
                                     '').trim(),
                                href:
                                    e.getAttribute('href') || '',
                                onclick:
                                    e.getAttribute('onclick') || '',
                                value:
                                    e.getAttribute('value') || ''
                            })
                            """
                        )

                        blob = json.dumps(
                            info,
                            ensure_ascii=False,
                        )

                        if (
                            "2026/10/10" in blob
                            or "20261010" in blob
                            or "2026-10-10" in blob
                        ):

                            print(
                                "DATE CONTROL:",
                                info
                            )

                            await el.click(
                                timeout=10000,
                                no_wait_after=True,
                            )

                            selected = True
                            break

                    except Exception:
                        pass

            if not selected:
                raise RuntimeError(
                    "2026/10/10を選択できません"
                )

            await page.wait_for_timeout(2500)

            print(
                "STEP 5 DATE SELECTED:",
                TARGET_DATE
            )

            # ==================================
            # 6. テニス選択
            # ==================================

            tennis = page.locator(
                'input[name="condition_chk[61][]"]'
                '[value="01"]'
            )

            if await tennis.count():

                await tennis.first.check()

            else:

                ok = await click_visible_text(
                    page,
                    "テニス",
                )

                if not ok:
                    raise RuntimeError(
                        "テニスを選択できません"
                    )

            await page.wait_for_timeout(1000)

            print("STEP 6 TENNIS")

            # ==================================
            # 7. 検索
            # ==================================

            search_buttons = page.locator(
                'button[name="searchBtn"],'
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

                searched = await click_visible_text(
                    page,
                    "検索",
                )

            if not searched:
                raise RuntimeError(
                    "検索できません"
                )

            await page.wait_for_timeout(6000)

            print("STEP 7 SEARCH COMPLETE")

            # ==================================
            # 8. 結果画面取得
            # ==================================

            body = await page.locator(
                "body"
            ).inner_text()

            print(body[:50000])

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

            # ==================================
            # 9. ○を数える
            # ==================================

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

                    if text in [
                        "○",
                        "〇",
                        "●",
                    ]:

                        open_cells.append({
                            "text": text,
                            "html":
                                (
                                    await cell
                                    .inner_html()
                                )[:2000],
                        })

                except Exception:
                    pass

            print(
                "OPEN CELLS:",
                len(open_cells)
            )

            result = {
                "target_date":
                    TARGET_DATE,

                "url":
                    page.url,

                "page_text":
                    body[:50000],

                "tables":
                    tables,

                "open_cells":
                    open_cells,

                "open_count":
                    len(open_cells),
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
                errors[-1]
            )

        finally:

            await browser.close()

    payload = {

        "checked_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "mode":
            "urayasu_calendar_test",

        "target_date":
            TARGET_DATE,

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

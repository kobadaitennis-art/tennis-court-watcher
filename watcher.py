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

            # 2. 空き状況ページへ
            start = page.get_by_text(
                "施設の空きを見る",
                exact=False,
            )

            clicked = False

            for i in range(await start.count()):
                try:
                    el = start.nth(i)
                    if await el.is_visible():
                        await el.click(
                            timeout=10000,
                            no_wait_after=True,
                        )
                        clicked = True
                        break
                except Exception:
                    pass

            if not clicked:
                raise RuntimeError(
                    "施設の空きを見るを開けません"
                )

            await page.wait_for_timeout(3000)

            # 3. 「目的で検索」タブへ
            purpose = page.locator(
                'a[onclick*="srch_mkt"]'
            )

            if not await purpose.count():
                raise RuntimeError(
                    "目的で検索タブが見つかりません"
                )

            await purpose.first.click(
                timeout=10000,
                no_wait_after=True,
            )

            await page.wait_for_timeout(3000)

            print("PURPOSE PAGE:", page.url)

            print(
                (
                    await page.locator("body").inner_text()
                )[:20000]
            )

            # 4. テニスのcheckboxを直接特定
            tennis = page.locator(
                'input[name="condition_chk[61][]"][value="01"]'
            )

            if not await tennis.count():
                # ページ構造が違う場合の予備
                labels = page.locator("label")

                found = False

                for i in range(await labels.count()):
                    label = labels.nth(i)

                    try:
                        text = (
                            await label.inner_text()
                        ).strip()

                        if text == "テニス":
                            await label.click()
                            found = True
                            break
                    except Exception:
                        pass

                if not found:
                    raise RuntimeError(
                        "テニスを選択できません"
                    )

            else:
                await tennis.first.check()

            print("TENNIS SELECTED")

            # 5. 現在の日付情報
            use_date = await page.locator(
                'input[name="UseDate"]'
            ).get_attribute("value")

            print("USE DATE:", use_date)

            # 6. 検索ボタン
            search = page.locator(
                'button[name="searchBtn"]'
            )

            visible = None

            for i in range(await search.count()):
                b = search.nth(i)

                try:
                    if await b.is_visible():
                        visible = b
                        break
                except Exception:
                    pass

            if visible is None:
                raise RuntimeError(
                    "検索ボタンが見つかりません"
                )

            # 検索実行
            await visible.click(
                timeout=10000,
                no_wait_after=True,
            )

            await page.wait_for_timeout(6000)

            # 7. 結果画面
            body = await page.locator(
                "body"
            ).inner_text()

            print("RESULT URL:", page.url)
            print(body[:50000])

            # 8. 全テーブル取得
            tables = []

            table_loc = page.locator("table")
            table_count = await table_loc.count()

            print("TABLE COUNT:", table_count)

            for t in range(table_count):
                table = table_loc.nth(t)
                rows = []

                trs = table.locator("tr")

                for r in range(await trs.count()):
                    tr = trs.nth(r)

                    cells = tr.locator(
                        "th, td"
                    )

                    row = []

                    for c in range(await cells.count()):
                        cell = cells.nth(c)

                        try:
                            row.append({
                                "text": (
                                    await cell.inner_text()
                                ).strip(),

                                "html": (
                                    await cell.inner_html()
                                )[:3000],

                                "class": (
                                    await cell.get_attribute(
                                        "class"
                                    )
                                ),
                            })

                        except Exception:
                            pass

                    if row:
                        rows.append(row)

                if rows:
                    tables.append(rows)

            # 9. 空き枠らしいセルを抽出
            availability = []

            cells = page.locator("td")

            for i in range(await cells.count()):
                cell = cells.nth(i)

                try:
                    text = (
                        await cell.inner_text()
                    ).strip()

                    html = await cell.inner_html()

                    cls = await cell.get_attribute(
                        "class"
                    )

                    # ○・△・×・受付などを含むセル
                    if (
                        text
                        or "href" in html
                        or "onclick" in html
                    ):
                        if (
                            text in [
                                "○",
                                "〇",
                                "△",
                                "×",
                            ]
                            or "空" in text
                            or "受付" in text
                            or "reserve" in html.lower()
                            or "yoyaku" in html.lower()
                        ):
                            availability.append({
                                "text": text,
                                "class": cls,
                                "html": html[:3000],
                            })

                except Exception:
                    pass

            result = {
                "use_date": use_date,
                "url": page.url,
                "page_text": body[:50000],
                "table_count": table_count,
                "tables": tables,
                "availability": availability,
            }

        except Exception as e:
            errors.append(
                f"浦安市: {type(e).__name__}: {e}"
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
            "urayasu_purpose_tennis_result",

        "new_or_reopened": [],

        "current": {},

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

    if not STATE.exists():
        STATE.write_text(
            json.dumps(
                {"current": {}},
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

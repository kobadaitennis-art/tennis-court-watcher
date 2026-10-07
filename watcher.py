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


async def open_search(page):
    await page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.wait_for_timeout(4000)

    # 「施設の空きを見る」へ移動
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
                    await page.wait_for_timeout(4000)
                    return
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
                await page.wait_for_timeout(4000)
                return

        except Exception:
            pass

    raise RuntimeError(
        "施設空き状況画面へ移動できません"
    )


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
                "height": 1200,
            },
        )

        page = await context.new_page()

        try:
            await open_search(page)

            print("SEARCH PAGE:", page.url)

            #
            # 運動公園テニスコートを選択
            #
            facility = page.locator("#scd025")

            if await facility.count() == 0:
                raise RuntimeError(
                    "scd025 が見つかりません"
                )

            await facility.check()

            print(
                "FACILITY CHECKED:",
                await facility.is_checked(),
            )

            #
            # 現在選択されている日付を確認
            #
            use_date = await page.locator(
                'input[name="UseDate"]'
            ).get_attribute("value")

            print(
                "USE DATE:",
                use_date,
            )

            #
            # 検索実行
            #
            search_button = page.locator(
                'button[name="searchBtn"]'
            )

            if await search_button.count() == 0:
                raise RuntimeError(
                    "検索ボタンが見つかりません"
                )

            print("CLICK SEARCH")

            await search_button.click()

            try:
                await page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=15000,
                )
            except Exception:
                pass

            await page.wait_for_timeout(5000)

            #
            # 結果画面取得
            #
            body = await page.locator(
                "body"
            ).inner_text()

            print(
                "\nRESULT URL:",
                page.url,
            )

            print(
                "\nRESULT BODY:"
            )

            print(
                body[:30000]
            )

            #
            # テーブルを解析
            #
            tables = []

            table_loc = page.locator("table")

            table_count = await table_loc.count()

            print(
                "\nTABLE COUNT:",
                table_count,
            )

            for t in range(table_count):

                table = table_loc.nth(t)

                rows = []

                row_loc = table.locator("tr")

                for r in range(
                    await row_loc.count()
                ):

                    row = row_loc.nth(r)

                    cells = row.locator(
                        "th, td"
                    )

                    values = []

                    for c in range(
                        await cells.count()
                    ):
                        try:
                            txt = (
                                await cells.nth(c)
                                .inner_text()
                            ).strip()

                            values.append(txt)

                        except Exception:
                            values.append("")

                    if values:
                        rows.append(values)

                if rows:
                    tables.append(rows)

            #
            # リンク・ボタンも保存
            #
            clickables = []

            elements = page.locator(
                "a, button, input"
            )

            for i in range(
                min(
                    await elements.count(),
                    1000,
                )
            ):

                el = elements.nth(i)

                try:
                    info = await el.evaluate(
                        """
                        (e) => ({
                            tag: e.tagName,
                            text:
                                (e.innerText ||
                                 e.value ||
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
                            title:
                                e.getAttribute('title')
                        })
                        """
                    )

                    clickables.append(info)

                except Exception:
                    pass

            result = {
                "facility":
                    "運動公園テニスコート",

                "facility_code":
                    "025",

                "use_date":
                    use_date,

                "result_url":
                    page.url,

                "page_text":
                    body[:30000],

                "tables":
                    tables,

                "clickables":
                    clickables,
            }

        except Exception as e:

            error = (
                f"浦安市: "
                f"{type(e).__name__}: {e}"
            )

            errors.append(error)

            print(
                "ERROR:",
                error,
            )

        finally:
            await browser.close()

    payload = {
        "checked_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "mode":
            "urayasu_real_search_test",

        "new_or_reopened": [],

        "current": {},

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

    # まだ本番stateは変更しない
    if not STATE.exists():
        STATE.write_text(
            json.dumps(
                {"current": {}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print("\nFINAL RESULT")

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

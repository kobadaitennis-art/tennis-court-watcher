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
            viewport={"width": 1400, "height": 1400},
        )

        page = await context.new_page()

        try:
            # -------------------------
            # トップページ
            # -------------------------
            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(4000)

            # -------------------------
            # 「施設の空きを見る」へ
            # -------------------------
            moved = False

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
                            moved = True
                            break
                    except Exception:
                        pass

                if moved:
                    break

            if not moved:
                raise RuntimeError(
                    "空き状況画面へ移動できません"
                )

            await page.wait_for_timeout(4000)

            print("SEARCH PAGE:", page.url)

            # -------------------------
            # 「テニス」のチェックボックスを特定
            # -------------------------
            tennis_label = page.get_by_text(
                "テニス",
                exact=True,
            )

            tennis_found = False

            for i in range(await tennis_label.count()):
                label = tennis_label.nth(i)

                try:
                    if not await label.is_visible():
                        continue

                    # labelの近くにあるcheckboxを探す
                    parent = label.locator("xpath=..")

                    checkbox = parent.locator(
                        'input[type="checkbox"]'
                    )

                    if await checkbox.count():
                        await checkbox.first.check()
                        tennis_found = True
                        print("TENNIS CHECKED")
                        break

                    # label自体をクリック
                    await label.click()
                    tennis_found = True
                    print("TENNIS LABEL CLICKED")
                    break

                except Exception:
                    pass

            if not tennis_found:
                # 既知の目的チェック群から試す
                checks = page.locator(
                    'input[type="checkbox"][name^="condition_chk"]'
                )

                print(
                    "CONDITION CHECKBOXES:",
                    await checks.count(),
                )

                # HTMLを保存して後で判定
                for i in range(await checks.count()):
                    el = checks.nth(i)

                    print(
                        i,
                        await el.get_attribute("name"),
                        await el.get_attribute("value"),
                    )

                raise RuntimeError(
                    "テニスのチェックボックスを特定できません"
                )

            await page.wait_for_timeout(1000)

            # -------------------------
            # 検索
            # -------------------------
            search = page.locator(
                'button[name="searchBtn"]'
            )

            visible_search = None

            for i in range(await search.count()):
                candidate = search.nth(i)

                if await candidate.is_visible():
                    visible_search = candidate
                    break

            if visible_search is None:
                raise RuntimeError(
                    "表示中の検索ボタンが見つかりません"
                )

            # navigationとclickを同時待機
            try:
                async with page.expect_navigation(
                    timeout=20000
                ):
                    await visible_search.click(
                        timeout=10000
                    )
            except Exception:
                # SPA/JS遷移の場合もあるので続行
                pass

            await page.wait_for_timeout(6000)

            # -------------------------
            # 結果画面
            # -------------------------
            body = await page.locator(
                "body"
            ).inner_text()

            print("RESULT URL:", page.url)
            print(body[:40000])

            # -------------------------
            # 全table取得
            # -------------------------
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

                    cells = tr.locator("th, td")
                    values = []

                    for c in range(await cells.count()):
                        cell = cells.nth(c)

                        try:
                            text = (
                                await cell.inner_text()
                            ).strip()

                            html = await cell.inner_html()

                            values.append({
                                "text": text,
                                "html": html[:2000],
                            })

                        except Exception:
                            pass

                    if values:
                        rows.append(values)

                if rows:
                    tables.append(rows)

            # -------------------------
            # ○ / × / 空き関連要素
            # -------------------------
            availability_elements = []

            all_cells = page.locator(
                "td, th, a, button"
            )

            for i in range(
                min(await all_cells.count(), 3000)
            ):
                el = all_cells.nth(i)

                try:
                    text = (
                        await el.inner_text()
                    ).strip()

                    if (
                        text in ["○", "〇", "×", "△"]
                        or "空き" in text
                    ):
                        info = await el.evaluate(
                            """
                            (e) => ({
                                tag: e.tagName,
                                text:
                                    (e.innerText || '')
                                    .trim(),
                                className:
                                    e.className || '',
                                href:
                                    e.getAttribute('href'),
                                html:
                                    e.outerHTML.slice(
                                        0, 2000
                                    )
                            })
                            """
                        )

                        availability_elements.append(
                            info
                        )

                except Exception:
                    pass

            result = {
                "url": page.url,
                "page_text": body[:40000],
                "table_count": table_count,
                "tables": tables,
                "availability_elements":
                    availability_elements,
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
            "urayasu_tennis_all_facilities_test",

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

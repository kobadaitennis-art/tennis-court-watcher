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
            # -----------------------------
            # 1. トップページ
            # -----------------------------
            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(4000)

            # -----------------------------
            # 2. 空き状況画面へ
            # -----------------------------
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

            # -----------------------------
            # 3. テニスを選択
            # -----------------------------
            tennis = page.get_by_text(
                "テニス",
                exact=True,
            )

            tennis_clicked = False

            for i in range(await tennis.count()):
                try:
                    el = tennis.nth(i)

                    if not await el.is_visible():
                        continue

                    await el.click(timeout=8000)
                    tennis_clicked = True
                    break

                except Exception:
                    pass

            if not tennis_clicked:
                raise RuntimeError(
                    "テニスを選択できません"
                )

            await page.wait_for_timeout(1000)

            # -----------------------------
            # 4. 表示中の検索ボタン
            # -----------------------------
            buttons = page.locator(
                'button[name="searchBtn"]'
            )

            search_button = None

            for i in range(await buttons.count()):
                b = buttons.nth(i)

                try:
                    if await b.is_visible():
                        search_button = b
                        break
                except Exception:
                    pass

            if search_button is None:
                raise RuntimeError(
                    "検索ボタンが見つかりません"
                )

            await search_button.click(
                timeout=10000,
                no_wait_after=True,
            )

            await page.wait_for_timeout(5000)

            print(
                "AFTER TENNIS SEARCH:",
                page.url,
            )

            # -----------------------------
            # 5. 現在のフォーム構造を取得
            # -----------------------------
            forms = []

            form_loc = page.locator("form")

            for i in range(await form_loc.count()):
                form = form_loc.nth(i)

                try:
                    forms.append(
                        await form.evaluate(
                            """
                            (e) => ({
                                action:
                                    e.getAttribute('action'),
                                method:
                                    e.getAttribute('method'),
                                html:
                                    e.outerHTML.slice(
                                        0, 30000
                                    )
                            })
                            """
                        )
                    )
                except Exception:
                    pass

            # -----------------------------
            # 6. 8施設の入力情報
            # -----------------------------
            facilities = []

            radios = page.locator(
                'input[name="ShisetsuCode"]'
            )

            for i in range(await radios.count()):
                radio = radios.nth(i)

                try:
                    rid = await radio.get_attribute("id")

                    label_text = ""

                    if rid:
                        label = page.locator(
                            f'label[for="{rid}"]'
                        )

                        if await label.count():
                            label_text = (
                                await label.first.inner_text()
                            ).strip()

                    if "テニスコート" in label_text:
                        facilities.append({
                            "id": rid,
                            "value":
                                await radio.get_attribute(
                                    "value"
                                ),
                            "name": label_text,
                        })

                except Exception:
                    pass

            print(
                "TENNIS FACILITIES:",
                json.dumps(
                    facilities,
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            # -----------------------------
            # 7. リンク・ボタン・onclick取得
            # -----------------------------
            controls = []

            elems = page.locator(
                "a, button, input"
            )

            for i in range(
                min(await elems.count(), 1500)
            ):
                el = elems.nth(i)

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
                            onclick:
                                e.getAttribute('onclick'),
                            className:
                                e.className || ''
                        })
                        """
                    )

                    controls.append(info)

                except Exception:
                    pass

            # -----------------------------
            # 8. もし既に結果表なら取得
            # -----------------------------
            tables = []

            table_loc = page.locator("table")

            for t in range(await table_loc.count()):
                table = table_loc.nth(t)
                rows = []

                trs = table.locator("tr")

                for r in range(await trs.count()):
                    tr = trs.nth(r)
                    cells = tr.locator("th, td")

                    values = []

                    for c in range(await cells.count()):
                        try:
                            cell = cells.nth(c)

                            values.append({
                                "text":
                                    (
                                        await cell.inner_text()
                                    ).strip(),

                                "html":
                                    (
                                        await cell.inner_html()
                                    )[:3000],
                            })

                        except Exception:
                            pass

                    if values:
                        rows.append(values)

                if rows:
                    tables.append(rows)

            body = await page.locator(
                "body"
            ).inner_text()

            result = {
                "url": page.url,
                "page_text": body[:40000],
                "facilities": facilities,
                "forms": forms,
                "controls": controls,
                "tables": tables,
            }

        except Exception as e:
            errors.append(
                f"浦安市: {type(e).__name__}: {e}"
            )

            print(
                "ERROR:",
                errors[-1],
            )

        finally:
            await browser.close()

    payload = {
        "checked_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "mode":
            "urayasu_purpose_result_diagnostic",

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

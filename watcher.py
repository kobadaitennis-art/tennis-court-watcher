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


async def dump_page(page, label):
    print("\n" + "=" * 80)
    print("DEBUG:", label)
    print("=" * 80)

    print("URL:", page.url)
    print("TITLE:", await page.title())

    try:
        body = await page.locator("body").inner_text()
        print("\nBODY:")
        print(body[:20000])
    except Exception as e:
        print("BODY ERROR:", e)

    print("\nCLICKABLE ELEMENTS:")

    loc = page.locator("a, button, [role='button']")

    count = await loc.count()

    for i in range(min(count, 300)):
        el = loc.nth(i)

        try:
            txt = (
                await el.inner_text()
            ).strip().replace("\n", " ")

            href = await el.get_attribute("href")

            if txt or href:
                print(
                    i,
                    "text=",
                    repr(txt),
                    "href=",
                    repr(href),
                )
        except Exception:
            pass


async def open_facility_search(page):
    print("\n>>> 施設空き検索への移動開始")

    #
    # 方法1: テキスト
    #
    candidates = [
        "施設の空きを見る",
        "施設 の空きを見る",
        "施設毎の空き状況",
        "施設の空き",
    ]

    for word in candidates:
        try:
            loc = page.get_by_text(
                word,
                exact=False,
            )

            count = await loc.count()

            print(
                "TEXT",
                repr(word),
                "count=",
                count,
            )

            for i in range(count):
                item = loc.nth(i)

                try:
                    if not await item.is_visible():
                        continue

                    print(
                        "TEXT CLICK TRY:",
                        await item.evaluate(
                            "(e) => e.outerHTML"
                        ),
                    )

                    await item.click(
                        timeout=8000,
                    )

                    print(
                        "TEXT CLICK SUCCESS"
                    )

                    return True

                except Exception as e:
                    print(
                        "TEXT CLICK ERROR:",
                        e,
                    )

        except Exception as e:
            print(
                "TEXT SEARCH ERROR:",
                e,
            )

    #
    # 方法2: リンクを全部調べる
    #
    print("\n>>> リンクから検索")

    links = page.locator("a")

    count = await links.count()

    for i in range(count):
        link = links.nth(i)

        try:
            text = (
                await link.inner_text()
            ).strip()

            href = await link.get_attribute(
                "href"
            )

            combined = (
                (text or "")
                + " "
                + (href or "")
            )

            if (
                "空き" in combined
                or "facility" in combined.lower()
            ):
                print(
                    "LINK CANDIDATE:",
                    repr(text),
                    repr(href),
                )

                try:
                    await link.click(
                        timeout=8000
                    )

                    print(
                        "LINK CLICK SUCCESS"
                    )

                    return True

                except Exception as e:
                    print(
                        "LINK CLICK ERROR:",
                        e,
                    )

        except Exception:
            pass

    #
    # 方法3: JSで文字列を含む要素を探索
    #
    print("\n>>> JavaScript探索")

    result = await page.evaluate(
        """
        () => {
            const all =
                Array.from(
                    document.querySelectorAll('*')
                );

            const matches = [];

            for (const el of all) {
                const text =
                    (el.innerText || '').trim();

                if (
                    text === '施設の空きを見る'
                    || text.includes(
                        '施設の空きを見る'
                    )
                ) {
                    matches.push({
                        tag: el.tagName,
                        text: text.slice(0, 200),
                        html:
                            el.outerHTML.slice(
                                0,
                                1000
                            )
                    });
                }
            }

            return matches.slice(0, 30);
        }
        """
    )

    print(
        "JS MATCHES:",
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
    )

    #
    # 方法4: locatorから親要素をクリック
    #
    try:
        text_loc = page.get_by_text(
            "施設の空きを見る",
            exact=False,
        )

        count = await text_loc.count()

        for i in range(count):
            item = text_loc.nth(i)

            for level in range(1, 5):
                try:
                    parent = item.locator(
                        "/.." * level
                    )

                    html = await parent.evaluate(
                        "(e) => e.outerHTML"
                    )

                    print(
                        "PARENT TRY",
                        level,
                        html[:1000],
                    )

                    await parent.click(
                        timeout=5000,
                    )

                    print(
                        "PARENT CLICK SUCCESS"
                    )

                    return True

                except Exception:
                    pass

    except Exception:
        pass

    return False


async def dump_search_controls(page):
    print("\n" + "=" * 80)
    print("SEARCH SCREEN CONTROLS")
    print("=" * 80)

    controls = page.locator(
        "input, button, select, label, a"
    )

    count = await controls.count()

    for i in range(min(count, 500)):
        el = controls.nth(i)

        try:
            tag = await el.evaluate(
                "(e) => e.tagName"
            )

            text = (
                await el.inner_text()
            ).strip().replace("\n", " ")

            attrs = await el.evaluate(
                """
                (e) => ({
                    id: e.id || null,
                    name:
                        e.getAttribute('name'),
                    type:
                        e.getAttribute('type'),
                    value:
                        e.getAttribute('value'),
                    href:
                        e.getAttribute('href'),
                    forAttr:
                        e.getAttribute('for'),
                    checked:
                        e.checked === true
                })
                """
            )

            if (
                text
                or attrs["id"]
                or attrs["name"]
                or attrs["value"]
            ):
                print(
                    i,
                    tag,
                    repr(text),
                    attrs,
                )

        except Exception:
            pass


async def main():
    DATA.mkdir(exist_ok=True)

    errors = []
    diagnostics = []

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
            print(
                "=== URAYASU START ==="
            )

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await page.wait_for_timeout(
                5000
            )

            await dump_page(
                page,
                "TOP PAGE",
            )

            moved = await open_facility_search(
                page
            )

            if not moved:
                raise RuntimeError(
                    "施設空き検索画面へ"
                    "移動できませんでした"
                )

            try:
                await page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=15000,
                )
            except Exception:
                pass

            await page.wait_for_timeout(
                4000
            )

            print(
                "\n>>> 移動後URL:",
                page.url,
            )

            await dump_page(
                page,
                "AFTER FACILITY SEARCH",
            )

            await dump_search_controls(
                page
            )

            body = await page.locator(
                "body"
            ).inner_text()

            found = []

            for facility in TARGET_FACILITIES:
                if facility in body:
                    found.append(facility)
                    print(
                        "FOUND:",
                        facility,
                    )

            tennis_lines = [
                line.strip()
                for line in body.splitlines()
                if "テニス" in line
            ]

            print(
                "\nTENNIS LINES:"
            )

            for line in tennis_lines[:200]:
                print(line)

            diagnostics.append(
                {
                    "step":
                        "facility_search_opened",
                    "url":
                        page.url,
                    "facilities_found":
                        found,
                    "tennis_lines":
                        tennis_lines[:200],
                }
            )

        except Exception as e:

            error = (
                "浦安市: "
                + type(e).__name__
                + ": "
                + str(e)
            )

            errors.append(error)

            print("\nERROR:")
            print(error)

            try:
                await dump_page(
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
            "urayasu_navigation_diagnostic",

        "new_or_reopened": [],

        "current": {},

        "errors":
            errors,

        "diagnostics":
            diagnostics,
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
        "\nFINAL RESULT:"
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

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
DATA = ROOT / "data"
STATE_FILE = DATA / "state.json"
OUT_FILE = DATA / "latest.json"

URL = "https://k5.p-kashikan.jp/urayasu-city/"
JST = ZoneInfo("Asia/Tokyo")

FACILITIES = [
    "運動公園テニスコート",
    "中央公園テニスコート",
    "美浜運動公園テニスコート",
    "高洲中央公園テニスコート",
    "高洲テニスコート",
    "美浜テニスコート",
    "舞浜テニスコート",
    "高洲南テニスコート",
]


def load_state():
    if not STATE_FILE.exists():
        return {"urayasu": {}}

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        if "urayasu" not in data:
            data["urayasu"] = {}

        return data

    except Exception:
        return {"urayasu": {}}


def slot_key(slot):
    return "|".join([
        slot["date"],
        slot["facility"],
        slot["court"],
        slot["time"],
    ])


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


async def open_purpose_search(page):
    await page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    await page.wait_for_timeout(2000)

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

    await page.wait_for_timeout(2000)

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

    await page.wait_for_timeout(2000)


async def select_date(page, target_date):
    day_text = str(target_date.day)

    candidates = page.get_by_text(
        day_text,
        exact=True,
    )

    for i in range(await candidates.count()):
        try:
            el = candidates.nth(i)

            if not await el.is_visible():
                continue

            in_table = await el.evaluate(
                "e => !!e.closest('table')"
            )

            if not in_table:
                continue

            try:
                await el.click(
                    timeout=10000,
                    no_wait_after=True,
                )
                return

            except Exception:
                parent = el.locator("..")

                await parent.click(
                    timeout=10000,
                    no_wait_after=True,
                )
                return

        except Exception:
            pass

    raise RuntimeError(
        f"{target_date.isoformat()}を選択できません"
    )


async def select_tennis(page):
    tennis = page.locator(
        'input[name="condition_chk[61][]"]'
        '[value="01"]'
    )

    if await tennis.count():
        try:
            await tennis.first.check(force=True)
            return
        except Exception:
            pass

    if await click_text(page, "テニス"):
        return

    raise RuntimeError(
        "テニスを選択できません"
    )


async def search(page):
    buttons = page.locator(
        'button[name="searchBtn"], '
        'input[name="searchBtn"]'
    )

    for i in range(await buttons.count()):
        try:
            button = buttons.nth(i)

            if await button.is_visible():
                await button.click(
                    timeout=10000,
                    no_wait_after=True,
                )

                await page.wait_for_timeout(4000)
                return

        except Exception:
            pass

    if await click_text(page, "検索"):
        await page.wait_for_timeout(4000)
        return

    raise RuntimeError(
        "検索を押せません"
    )


async def parse_available_slots(
    page,
    target_date,
):
    slots = []

    tables = page.locator("table")

    current_facility = None

    for t in range(await tables.count()):
        table = tables.nth(t)

        try:
            table_text = (
                await table.inner_text()
            ).strip()
        except Exception:
            continue

        # どの施設の表か判定
        facility = None

        for name in FACILITIES:
            if name in table_text:
                facility = name
                break

        if facility:
            current_facility = facility

        if current_facility is None:
            continue

        rows = table.locator("tr")

        headers = []

        for r in range(await rows.count()):
            row = rows.nth(r)

            cells = row.locator("th, td")

            texts = []

            for c in range(await cells.count()):
                try:
                    text = (
                        await cells
                        .nth(c)
                        .inner_text()
                    ).strip()
                except Exception:
                    text = ""

                texts.append(text)

            if not texts:
                continue

            # 時刻ヘッダー
            if texts[0] == "施設":
                headers = texts[1:]
                continue

            if not headers:
                continue

            court = texts[0]

            # A面などの行だけ
            if "面" not in court:
                continue

            values = texts[1:]

            for index, value in enumerate(values):
                if index >= len(headers):
                    break

                # 実際の空き記号だけ
                if value not in (
                    "○",
                    "〇",
                    "●",
                ):
                    continue

                start = headers[index]

                if not start.isdigit():
                    continue

                start_hour = int(start)

                # 次のヘッダーを終了時間として使用
                if index + 1 < len(headers):
                    end = headers[index + 1]
                else:
                    end = str(start_hour + 1)

                slots.append({
                    "date":
                        target_date.isoformat(),

                    "weekday":
                        [
                            "月",
                            "火",
                            "水",
                            "木",
                            "金",
                            "土",
                            "日",
                        ][target_date.weekday()],

                    "municipality":
                        "浦安市",

                    "facility":
                        current_facility,

                    "court":
                        court,

                    "time":
                        f"{start}:00-{end}:00",

                    "symbol":
                        value,
                })

    return slots


async def check_date(
    browser,
    target_date,
):
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
        await open_purpose_search(page)

        await select_date(
            page,
            target_date,
        )

        await page.wait_for_timeout(1000)

        await select_tennis(page)

        await page.wait_for_timeout(500)

        await search(page)

        body = await page.locator(
            "body"
        ).inner_text()

        expected = (
            f"{target_date.year}"
            f"(令和 "
        )

        date_text = (
            f"{target_date.month}月"
            f"{target_date.day}日"
        )

        if date_text not in body:
            raise RuntimeError(
                "検索結果の日付を確認できません"
            )

        slots = await parse_available_slots(
            page,
            target_date,
        )

        print(
            target_date.isoformat(),
            "AVAILABLE:",
            len(slots),
        )

        return slots

    finally:
        await context.close()


async def main():
    DATA.mkdir(exist_ok=True)

    now = datetime.now(JST)
    today = now.date()

    # 今日〜7日先
    all_dates = [
        today + timedelta(days=i)
        for i in range(8)
    ]

    # まず土日のみ
    target_dates = [
        d
        for d in all_dates
        if d.weekday() >= 5
    ]

    print(
        "TARGET DATES:",
        [
            d.isoformat()
            for d in target_dates
        ],
    )

    previous_state = load_state()

    previous_urayasu = (
        previous_state
        .get("urayasu", {})
    )

    current_slots = {}
    errors = []
    checked_dates = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True
        )

        try:
            for target_date in target_dates:
                try:
                    slots = await check_date(
                        browser,
                        target_date,
                    )

                    checked_dates.append(
                        target_date.isoformat()
                    )

                    for slot in slots:
                        current_slots[
                            slot_key(slot)
                        ] = slot

                except Exception as e:
                    error = (
                        "浦安市 "
                        + target_date.isoformat()
                        + ": "
                        + type(e).__name__
                        + ": "
                        + str(e)
                    )

                    errors.append(error)

                    print("ERROR:", error)

        finally:
            await browser.close()

    # ----------------------------------
    # 新規 / 再出現した空き
    # ----------------------------------

    new_or_reopened = []

    for key, slot in current_slots.items():
        if key not in previous_urayasu:
            new_or_reopened.append(slot)

    # ----------------------------------
    # 状態保存
    #
    # 全対象日の確認に成功した時だけ
    # 浦安の状態を置き換える。
    #
    # 失敗時に「空きが消えた」と
    # 誤判定しないため。
    # ----------------------------------

    all_success = (
        len(errors) == 0
        and len(checked_dates)
        == len(target_dates)
    )

    new_state = previous_state.copy()

    if all_success:
        new_state["urayasu"] = (
            current_slots
        )

        STATE_FILE.write_text(
            json.dumps(
                new_state,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # ----------------------------------
    # latest.json
    # ----------------------------------

    payload = {
        "checked_at":
            now.isoformat(),

        "mode":
            "urayasu_production",

        "range": {
            "from":
                today.isoformat(),

            "to":
                (
                    today
                    + timedelta(days=7)
                ).isoformat(),
        },

        "target_dates": [
            d.isoformat()
            for d in target_dates
        ],

        "checked_dates":
            checked_dates,

        "success":
            all_success,

        "errors":
            errors,

        "available_count":
            len(current_slots),

        "new_or_reopened_count":
            len(new_or_reopened),

        "new_or_reopened":
            new_or_reopened,

        "current":
            list(
                current_slots.values()
            ),
    }

    OUT_FILE.write_text(
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

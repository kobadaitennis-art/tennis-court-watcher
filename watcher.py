"""Public read-only court watcher. Never click vacancy cells or reservation controls."""
import asyncio
import calendar
import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent
DATA = ROOT / 'data'
JST = ZoneInfo('Asia/Tokyo')
URLS = {
    'urayasu': 'https://k5.p-kashikan.jp/urayasu-city/',
    'katsushika': 'https://rsv.shisetsu.city.katsushika.lg.jp/katsushika/web/index.jsp',
}
NAMES = {'urayasu': '浦安市', 'katsushika': '葛飾区'}
URAYASU = dict(zip([
    '運動公園テニスコート', '中央公園テニスコート', '美浜運動公園テニスコート',
    '高洲中央公園テニスコート', '高洲テニスコート', '美浜テニスコート',
    '舞浜テニスコート', '高洲南テニスコート',
], ['ABCDEFGH', 'ABCDEF', 'AB', 'AB', 'ABCD', 'AB', 'AB', 'AB']))
KATSUSHIKA = [
    '奥戸総スポテニス・野球場', '水元総スポテニス', '東金町テニスコート', '渋江公園',
    '小菅東スポーツ公園', '上千葉公園運動場', 'にいじゅくみらい公園', '東新小岩野球・テニス・会議室',
]
KATSUSHIKA_COURTS = dict(zip(KATSUSHIKA, ['ABC','AB','ABCDEF','ABCDEF','ABCDE','ABC','ABC','ABCDEFGH']))
JP_HOLIDAYS = holidays.Japan(language='ja')


def holiday_name(d):
    return JP_HOLIDAYS.get(d)


def target_dates(today, days):
    return [d for i in range(days + 1) if (d := today + timedelta(days=i)).weekday() >= 5 or holiday_name(d)]


def next_month(d):
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def norm(s):
    return unicodedata.normalize('NFKC', s).strip()


def court_name(s):
    m = re.search(r'([A-Z])(?:面|ハード|オムニ)', norm(s))
    if not m:
        raise ValueError(f'Unknown court: {s}')
    return m[1] + '面'


def make_slot(city, d, facility, court, start, end):
    if not re.fullmatch(r'\d{2}:\d{2}', start) or not re.fullmatch(r'\d{2}:\d{2}', end) or start >= end:
        raise ValueError(f'Invalid time: {start}-{end}')
    return {'date': d.isoformat(), 'weekday': '月火水木金土日'[d.weekday()], 'holiday': holiday_name(d),
            'municipality': NAMES[city], 'facility': facility, 'court': court_name(court),
            'start': start, 'end': end, 'time': f'{start}-{end}', 'url': URLS[city]}


def slot_key(s):
    # Canonical normalization also migrates legacy full-width court names/unpadded hours.
    time = s['time']
    parts = time.split('-')
    parts = [f'{int(p.split(":")[0]):02}:{int(p.split(":")[1]):02}' for p in parts]
    return '|'.join([s['municipality'], s['date'], s['facility'], court_name(s['court']), '-'.join(parts)])


URAYASU_DOM = r"""() => {
 const areas = Array.from(document.querySelectorAll('.koma-area'));
 return areas.map(area => {
   const facility = area.querySelector('h3')?.textContent.trim();
   let headers = null; const rows = [];
   for (const table of area.querySelectorAll('table.koma-table')) {
     for (const row of table.rows) {
       const cells = Array.from(row.cells);
       if (cells[0]?.textContent.trim() === '施設') {
         headers = cells.slice(1).map(c => ({text:c.textContent.trim(), x:c.getBoundingClientRect().x}));
       } else if (cells[0]?.classList.contains('name')) {
         rows.push({court:cells[0].textContent.trim(), headers, cells:cells.slice(1).map(c=>({
           text:c.textContent.trim(), x:c.getBoundingClientRect().x, right:c.getBoundingClientRect().right
         }))});
       }
     }
   }
   return {facility, rows};
 });
}"""


def parse_urayasu(areas, d):
    result = []
    found = {}
    for area in areas:
        f = area['facility']
        if f not in URAYASU or f in found:
            raise ValueError(f'Unexpected/duplicate facility: {f}')
        courts = []
        for row in area['rows']:
            court = court_name(row['court']); courts.append(court)
            headers = row['headers']
            if not headers or len(headers) < 2:
                raise ValueError('Missing hour headers')
            hours = [int(h['text']) for h in headers]
            if hours != list(range(hours[0], hours[-1]+1)):
                raise ValueError('Nonconsecutive hour headers')
            # Rows use separate tables and 99px cells for two 49px hour columns.
            # Match actual rendered boundaries; never infer one hour per vacancy cell.
            previous_end = headers[0]['x']
            for cell in row['cells']:
                if abs(cell['x']-previous_end) > 2:
                    raise ValueError('Gap in court row')
                previous_end = cell['right']
                if not cell['text']:
                    if abs(cell['x'] - headers[-1]['x']) > 2:
                        raise ValueError('Blank status inside operating hours')
                    continue  # trailing padding after last time boundary
                if cell['text'] not in ('●', '〇', '○', '×', '-', '休館'):
                    raise ValueError(f'Unknown availability symbol: {cell["text"]}')
                start = min(headers, key=lambda h: abs(h['x']-cell['x']))
                end = min(headers, key=lambda h: abs(h['x']-cell['right']))
                if abs(start['x']-cell['x']) > 2 or abs(end['x']-cell['right']) > 2:
                    raise ValueError('Time boundary does not match header')
                if int(start['text']) >= int(end['text']):
                    raise ValueError('Invalid time span')
                if cell['text'] in ('●', '〇', '○'):
                    result.append(make_slot('urayasu', d, f, court, f'{int(start["text"]):02}:00', f'{int(end["text"]):02}:00'))
            if abs(previous_end - row['cells'][0]['x']) < 1:
                raise ValueError('Empty court row')
        expected = {c+'面' for c in URAYASU[f]}
        if len(courts) != len(expected) or set(courts) != expected:
            raise ValueError(f'Incomplete courts at {f}: {courts}')
        found[f] = courts
    if set(found) != set(URAYASU):
        raise ValueError(f'Missing facilities: {set(URAYASU)-set(found)}')
    return result, found


KATSUSHIKA_DOM = r"""() => Array.from(document.querySelectorAll('table.akitablelist')).map(t =>
 Array.from(t.rows).map(r => Array.from(r.cells).map(c=>({text:c.textContent.trim(), colspan:c.colSpan,
   images:Array.from(c.querySelectorAll('img')).map(i=>({alt:i.alt, src:i.getAttribute('src')}))}))))"""


def parse_katsushika(tables, d, facility):
    if len(tables) != 1 or len(tables[0]) < 2:
        raise ValueError('Missing/ambiguous day table')
    rows = tables[0]; header = rows[0]
    if norm(header[0]['text']).replace('\n', '').replace(' ', '') != f'{d.year}年{d.month}月{d.day}日':
        raise ValueError('Wrong year/month/day in result')
    times = []
    for c in header[1:]:
        m = re.search(r'(\d{3,4})-(\d{3,4})', norm(c['text']))
        if not m:
            raise ValueError('Missing explicit start/end time')
        def hhmm(s):
            s = s.zfill(4)
            if int(s[:2]) > 23 or int(s[2:]) > 59:
                raise ValueError('Invalid HHMM')
            return s[:2]+':'+s[2:]
        times.append((hhmm(m[1]), hhmm(m[2])))
    slots, courts = [], []
    for row in rows[1:]:
        if 'テニス' not in norm(row[0]['text']):
            continue
        court = court_name(row[0]['text']); courts.append(court)
        if len(row) != len(header) or any(c['colspan'] != 1 for c in row):
            raise ValueError('Court columns do not match times')
        for cell, (start, end) in zip(row[1:], times):
            if not cell['images']:
                raise ValueError('Missing cell status image')
            if any(i['alt'] == '空き' for i in cell['images']):
                slots.append(make_slot('katsushika', d, facility, court, start, end))
    expected = {c+'面' for c in KATSUSHIKA_COURTS[facility]}
    if set(courts) != expected or len(courts) != len(expected):
        raise ValueError('Missing/duplicate tennis courts')
    return slots, courts


async def click_link(page, name):
    await page.get_by_role('link', name=name, exact=True).click(timeout=20000)


async def wait_k(page, text):
    await page.get_by_text(text, exact=False).first.wait_for(state='visible', timeout=30000)


async def check_urayasu(browser, d):
    context = await browser.new_context(locale='ja-JP', timezone_id='Asia/Tokyo', viewport={'width':1400,'height':1600})
    page = await context.new_page()
    try:
        await page.goto(URLS['urayasu'], wait_until='domcontentloaded', timeout=60000)
        await page.get_by_role('link', name=re.compile(r'目的.*から探す')).click()
        await page.get_by_role('radio', name='テニス', exact=True).wait_for()
        month = page.locator('.month-cal-head')
        if f'{d.year}' not in await month.inner_text() or f'{d.month}月' not in await month.inner_text():
            await page.get_by_role('link', name=f'{d.month}月', exact=True).click()
            await page.wait_for_function('(m) => document.querySelector(".month-cal-head")?.textContent.includes(m)', arg=f'{d.month}月')
        await page.locator(f'#day-{d.day} a').click()
        await page.get_by_role('radio', name='テニス', exact=True).check()
        await page.get_by_role('checkbox', name='対象施設の一覧から選択', exact=True).uncheck()
        await page.get_by_role('button', name=re.compile('検索')).click()
        await page.locator('.koma-area').first.wait_for(timeout=30000)
        await page.get_by_role('heading', name='高洲南テニスコート', exact=True).wait_for(timeout=30000)
        headings = await page.locator('h3').all_text_contents()
        if not any(re.search(rf'{d.year}.*{d.month}月{d.day}日', s) for s in headings):
            raise ValueError('Wrong date in search result')
        body = await page.locator('body').inner_text()
        if not ('受付期間外' in body and '予約済' in body and '空き' in body):
            raise ValueError('Availability legend missing')
        return parse_urayasu(await page.evaluate(URAYASU_DOM), d)
    finally:
        await context.close()


async def open_katsushika(page):
    await page.goto(URLS['katsushika'], wait_until='domcontentloaded', timeout=60000)
    await click_link(page, '施設の空き状況')
    await click_link(page, '利用目的から')
    await click_link(page, '屋外スポーツ')
    await click_link(page, 'テニス')
    await page.get_by_role('link', name=KATSUSHIKA[-1], exact=True).wait_for(timeout=30000)
    for name in KATSUSHIKA:
        if await page.get_by_role('link', name=name, exact=True).count() != 1:
            raise ValueError(f'Missing facility {name}')
    await click_link(page, KATSUSHIKA[0])
    await page.locator('#selectBldCd').wait_for(timeout=30000)
    await page.get_by_role('link', name='次の月', exact=True).wait_for(timeout=30000)


async def month_view(page, facility, y, m):
    await page.locator('#selectBldCd').select_option(label=facility)
    # The monthly facility selector requires an explicit redisplay link.
    await page.locator('a[href*="gRsvWTransInstSrchInstAction"]').click()
    await page.get_by_role('link', name=facility, exact=True).wait_for(timeout=30000)
    await page.get_by_role('link', name='次の月', exact=True).wait_for(timeout=30000)
    for _ in range(3):
        text = await page.locator('body').inner_text()
        if f'{y}年{m}月' in text:
            return
        match = re.search(r'(\d{4})年(\d{1,2})月', text)
        if not match:
            raise ValueError('Month caption missing')
        current = (int(match[1]), int(match[2]))
        await click_link(page, '次の月' if current < (y,m) else '前の月')
        await page.get_by_role('link', name='次の月', exact=True).wait_for(timeout=30000)
        await page.wait_for_function('(s)=>document.body.innerText.includes(s)', arg=f'{y}年{m}月', timeout=30000)
    raise ValueError('Cannot select target month')


async def month_status(page, d):
    # Read the exact calendar cell; image alt/href date disambiguates today and other days.
    return await page.evaluate(r"""(d) => {
      for (const a of document.querySelectorAll('a[href*="selectDay"]')) {
        const h=a.getAttribute('href'); const nums=h.match(/,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*;?$/);
        if(nums && Number(nums[1])===d[0] && Number(nums[2])===d[1] && Number(nums[3])===d[2]) {
          return {status:a.querySelector('img')?.alt || a.textContent.trim(), href:h};
        }
      }
      const table=Array.from(document.querySelectorAll('table')).find(t=>t.caption && t.caption.textContent.includes('空き状況'));
      if(!table) return null;
      for(const td of table.querySelectorAll('td')) {
        const t=td.textContent.trim();
        if(t===d[2]+'日' || (d[3] && t==='本日')) return {status:td.querySelector('img')?.alt, href:null};
      }
      return null;
    }""", [d.year, d.month, d.day, d==datetime.now(JST).date()])


async def check_katsushika(browser, dates):
    slots, coverage, errors = [], [], []
    context = await browser.new_context(locale='ja-JP', timezone_id='Asia/Tokyo')
    page = await context.new_page()
    try:
        try:
            await open_katsushika(page)
        except Exception as e:
            return [], [], [f'葛飾区 initial search: {type(e).__name__}: {e}']
        for facility in KATSUSHIKA:
            for y,m in sorted({(d.year,d.month) for d in dates}):
                try:
                    await month_view(page, facility, y,m)
                    for d in [d for d in dates if (d.year,d.month)==(y,m)]:
                        status = await month_status(page, d)
                        if not status or status['status'] not in ('全て空き','一部空き','予約あり','受付期間外','休館日','保守日','悪天候'):
                            raise ValueError(f'Unknown monthly status: {d} {status}')
                        day_slots=[]; courts=[]
                        if status['status'] in ('全て空き','一部空き'):
                            # Locator comes from observed calendar href, not a generated action.
                            link = page.locator('a[href='+json.dumps(status['href'])+']')
                            await link.click()
                            await page.locator('table.akitablelist').wait_for(timeout=30000)
                            await page.get_by_role('link', name=facility, exact=True).wait_for(timeout=30000)
                            selected = await page.locator('#selectBldCd option:checked').inner_text()
                            if selected.strip()!=facility:
                                raise ValueError('Wrong facility in daily result')
                            day_slots,courts=parse_katsushika(await page.evaluate(KATSUSHIKA_DOM), d, facility)
                            await click_link(page,'もどる')
                            await page.get_by_role('link',name='次の月',exact=True).wait_for(timeout=30000)
                        slots.extend(day_slots)
                        coverage.append({'city':'katsushika','date':d.isoformat(),'facility':facility,'courts':courts,'monthly_status':status['status']})
                except Exception as e:
                    errors.append(f'葛飾区 {facility} {y}-{m}: {type(e).__name__}: {e}')
                    # Recover public search for other facilities; never reset their previous availability.
                    try:
                        await open_katsushika(page)
                    except Exception as recovery:
                        errors.append(f'葛飾区 search recovery: {recovery}')
                        return slots,coverage,errors
        return slots,coverage,errors
    finally:
        await context.close()


def load_state():
    p=DATA/'state.json'
    if not p.exists():
        return {'version':3,'slots':{}}
    state=json.loads(p.read_text(encoding='utf-8'))  # corrupt state must fail, never re-notify everything
    if state.get('version')==3:
        return state
    migrated={}
    for city in URLS:
        for s in state.get(city,{}).values():
            s.setdefault('municipality',NAMES[city])
            migrated[slot_key(s)]={'slot':s,'available':True,'notified':True}
    return {'version':3,'slots':migrated}


def update_state(state, slots, coverage):
    records=state.setdefault('slots',{})
    scopes={(c['city'],c['date'],c['facility']) for c in coverage}
    current={slot_key(s):s for s in slots}
    for key,record in records.items():
        s=record['slot']; city=next((c for c,n in NAMES.items() if n==s['municipality']),None)
        if (city,s['date'],s['facility']) in scopes and key not in current:
            record['available']=False
    new=[]
    for key,s in current.items():
        record=records.get(key)
        if record is None or not record.get('available',False) or not record.get('notified',False):
            new.append(s)
            records[key]={'slot':s,'available':True,'notified':False,'generation':(record or {}).get('generation',0) + (1 if record is None or not record.get('available',False) else 0)}
        else:
            record['slot']=s
    return new


def build_notification(slots):
    if not slots: return ''
    lines=['🎾 テニスコートの新規・再公開の空き','', '| 日付・曜日 | 自治体 | 施設 | 面 | 時間 |', '|---|---|---|---|---|']
    for s in sorted(slots,key=slot_key):
        holiday=f'・祝 {s["holiday"]}' if s.get('holiday') else ''
        lines.append(f'| {s["date"]}（{s["weekday"]}{holiday}） | {s["municipality"]} | {s["facility"]} | {s["court"]} | {s["time"]} |')
    lines.extend(['',f'[葛飾区予約サイト]({URLS["katsushika"]}) ／ [浦安市予約サイト]({URLS["urayasu"]})',
                  '', '通知後に埋まる可能性があります。予約前に空き状況を再確認してください。'])
    return '\n'.join(lines)


async def main():
    DATA.mkdir(exist_ok=True)
    now=datetime.now(JST); today=now.date()
    dates={'urayasu':target_dates(today,7),'katsushika':target_dates(today,(next_month(today)-today).days)}
    state=load_state(); slots=[]; coverage=[]; errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        try:
            for d in dates['urayasu']:
                try:
                    found,courts=await check_urayasu(browser,d)
                    slots.extend(found)
                    coverage.extend({'city':'urayasu','date':d.isoformat(),'facility':f,'courts':cs} for f,cs in courts.items())
                except Exception as e:
                    errors.append(f'浦安市 {d}: {type(e).__name__}: {e}')
            if 7 <= now.hour < 24:
                found,checked,failures=await check_katsushika(browser,dates['katsushika'])
                slots.extend(found);coverage.extend(checked);errors.extend(failures)
            else:
                errors.append('葛飾区は公開システム稼働時間外（7時〜24時）。状態は保持。')
        finally:
            await browser.close()
    # Never notify a same-day session which has already started.
    slots=[s for s in slots if datetime.fromisoformat(s['date']+'T'+s['start']).replace(tzinfo=JST)>now]
    new=update_state(state,slots,coverage)
    payload={'checked_at':now.isoformat(),'mode':'both_cities_v3','success':not errors,'errors':errors,
             'target_dates':{c:[d.isoformat() for d in ds] for c,ds in dates.items()},'coverage':coverage,
             'available_count':len(slots),'current':slots,'new_or_reopened':new,'new_or_reopened_count':len(new),
             'notification':build_notification(new)}
    # Commit only after issue delivery succeeds. Partial successes are valid; failed scopes remain intact.
    (DATA/'pending-state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    (DATA/'latest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (DATA/'notification.txt').write_text(payload['notification'],encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))


if __name__=='__main__':
    asyncio.run(main())

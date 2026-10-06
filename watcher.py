import asyncio,json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
R=Path(__file__).parent; OUT=R/'data/latest.json'; STATE=R/'data/state.json'
SITES={
 '葛飾区':'https://rsv.shisetsu.city.katsushika.lg.jp/katsushika/web/index.jsp',
 '浦安市':'https://k5.p-kashikan.jp/urayasu-city/'
}
async def main():
 errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(headless=True)
  for city,url in SITES.items():
   page=await b.new_page()
   try:
    await page.goto(url,wait_until='domcontentloaded',timeout=30000)
    body=await page.locator('body').inner_text()
    if len(body)<50: raise RuntimeError('公開ページを正常取得できません')
    # 初版は誤通知防止のため取得確認のみ。初回Actionsログを基に施設/面/時間の
    # セレクタを確定し、空き抽出を有効化する。
    errors.append(f'{city}: 接続成功。空き抽出セレクタは初回ログ確認後に確定します')
   except Exception as e: errors.append(f'{city}: {e}')
   finally: await page.close()
  await b.close()
 payload={'checked_at':datetime.now().astimezone().isoformat(),'new_or_reopened':[],'current':{},'errors':errors}
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 STATE.write_text(json.dumps({'current':{}},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(payload,ensure_ascii=False,indent=2))
asyncio.run(main())

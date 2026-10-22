import asyncio, sys, pathlib
from playwright.async_api import async_playwright
SRC=pathlib.Path(__file__).parent; OUT=pathlib.Path('/workspace/torob-ux/mockups-v2'); OUT.mkdir(parents=True,exist_ok=True)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--allow-file-access-from-files'])
        pg=await b.new_page(viewport={'width':390,'height':844},device_scale_factor=2)
        for f in sorted(SRC.glob('0*.html')):
            await pg.goto(f.as_uri()); await pg.evaluate('document.fonts.ready'); await pg.wait_for_timeout(200)
            fam=await pg.evaluate("document.fonts.check('16px Vazirmatn')")
            # overflow check: elements whose content overflows horizontally
            ov=await pg.evaluate("""[...document.querySelectorAll('.scroll *')].filter(e=>e.scrollWidth>e.clientWidth+1 && getComputedStyle(e).overflow!=='visible' && !e.classList.contains('steps')).map(e=>e.className+':'+e.textContent.slice(0,30))""")
            await pg.screenshot(path=str(OUT/(f.stem+'.png')))
            print(f.stem,fam,ov[:5])
        await b.close()
asyncio.run(main())

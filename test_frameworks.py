from playwright.sync_api import sync_playwright
import os

BASE_URL = "http://localhost:5000"
SCREENSHOTS = "C:/Users/eiwen/Documents/prisma-journal/test_screenshots"

os.makedirs(SCREENSHOTS, exist_ok=True)

results = []

def log(msg, status="ok"):
    symbol = "PASS" if status == "ok" else ("FAIL" if status == "fail" else "INFO")
    print(f"[{symbol}] {msg}")
    results.append({"msg": msg, "status": status})

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # 1. Navigate to /frameworks
    log("Navigating to /frameworks", "info")
    resp = page.goto(f"{BASE_URL}/frameworks")
    page.wait_for_load_state("networkidle")

    if resp and resp.status == 200:
        log("GET /frameworks -> 200 OK")
    else:
        log(f"GET /frameworks -> {resp.status if resp else 'no response'}", "fail")

    page.screenshot(path=f"{SCREENSHOTS}/01_initial.png", full_page=True)
    log("Screenshot saved: 01_initial.png", "info")

    # 2. Page title
    title = page.title()
    log(f"Page title: '{title}'", "info")
    if "framework" in title.lower():
        log("Title mentions 'Framework'")
    else:
        log(f"Title does not mention 'Framework': '{title}'", "fail")

    # 3. Framework cards
    cards = page.locator(".fw-card")
    card_count = cards.count()
    if card_count > 0:
        log(f"Found {card_count} framework card(s)")
    else:
        log("No .fw-card elements found", "fail")

    # 4. Category filter buttons
    filter_btns = page.locator(".cat-filter-btn")
    btn_count = filter_btns.count()
    if btn_count > 0:
        labels = [filter_btns.nth(i).text_content().strip() for i in range(min(btn_count, 8))]
        log(f"Found {btn_count} filter button(s): {labels}")
    else:
        log("No .cat-filter-btn elements found", "fail")

    # 5. Click a non-"All" filter
    if btn_count > 1:
        second_btn = filter_btns.nth(1)
        label = second_btn.text_content().strip()
        second_btn.click()
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SCREENSHOTS}/02_filter_{label}.png", full_page=True)
        visible = page.locator(".fw-card").filter(has=page.locator(":visible")).count()
        log(f"After filter '{label}': cards in DOM = {page.locator('.fw-card').count()}", "info")

        # Reset to All
        filter_btns.first.click()
        page.wait_for_timeout(300)
        log("Reset to 'All' filter", "info")

    # 6. Expand questions on first card (look for any expand/toggle button)
    toggles = page.locator("button, a").filter(has_text="question").all()
    if not toggles:
        toggles = page.locator("[class*='toggle'], [class*='expand'], [class*='preview']").all()

    if toggles:
        toggles[0].click()
        page.wait_for_timeout(400)
        page.screenshot(path=f"{SCREENSHOTS}/03_expanded.png", full_page=True)
        log("Clicked expand toggle, screenshot: 03_expanded.png", "info")
        open_previews = page.locator(".fw-questions-preview.open").count()
        if open_previews > 0:
            log(f"Questions preview opened ({open_previews} open)")
        else:
            log("Questions preview may not have opened (no .open class found)", "info")
    else:
        log("No expand/toggle buttons found for questions", "info")

    # 7. Sidebar nav link
    nav_texts = [page.locator("nav a, .sidebar a").nth(i).text_content().strip()
                 for i in range(page.locator("nav a, .sidebar a").count())]
    log(f"Nav links: {nav_texts}", "info")
    if any("framework" in t.lower() for t in nav_texts):
        log("Sidebar has 'Frameworks' link")
    else:
        log("No 'Frameworks' nav link in sidebar", "fail")

    # 8. Console errors
    if console_errors:
        log(f"JS console errors: {console_errors}", "fail")
    else:
        log("No JS console errors")

    # 9. Mobile viewport
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{BASE_URL}/frameworks")
    page.wait_for_load_state("networkidle")
    page.screenshot(path=f"{SCREENSHOTS}/04_mobile.png", full_page=True)
    mobile_cards = page.locator(".fw-card").count()
    if mobile_cards > 0:
        log(f"Mobile (390px): {mobile_cards} cards rendered")
    else:
        log("Mobile: no cards found", "fail")

    browser.close()

print("\n" + "="*50)
print("SUMMARY")
print("="*50)
passes = sum(1 for r in results if r["status"] == "ok")
fails  = sum(1 for r in results if r["status"] == "fail")
infos  = sum(1 for r in results if r["status"] == "info")
print(f"PASS: {passes}  FAIL: {fails}  INFO: {infos}")
if fails:
    print("\nFailed checks:")
    for r in results:
        if r["status"] == "fail":
            print(f"  - {r['msg']}")
print(f"\nScreenshots saved to: {SCREENSHOTS}")

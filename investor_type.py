import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

def fetch_investor_type_data(page):
    """ดึงข้อมูลสรุปประเภทนักลงทุนทั้งตลาด SET (หุ้น) และ TFEX"""
    set_data = {
        "นักลงทุนสถาบัน": "-",
        "บัญชีบริษัทหลักทรัพย์": "-",
        "นักลงทุนต่างชาติ": "-",
        "นักลงทุนภายในประเทศ": "-"
    }
    tfex_data = {
        "นักลงทุนสถาบัน": {},
        "นักลงทุนต่างชาติ": {},
        "บัญชีบริษัทหลักทรัพย์": {},
        "นักลงทุนภายในประเทศ": {}
    }

    # 1. ดึงข้อมูลตลาด SET (หุ้น)
    print("กำลังดึงข้อมูลประเภทนักลงทุน SET...")
    try:
        page.goto("https://www.settrade.com/th/equities/market-data/investor-type", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        rows = page.locator("table tbody tr").all()
        for r in rows:
            txt = r.inner_text()
            nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?', txt)
            if nums:
                net_val = nums[-1] # ค่า Net อยู่ท้ายแถว
                if "สถาบัน" in txt: set_data["นักลงทุนสถาบัน"] = net_val
                elif "บริษัทหลักทรัพย์" in txt or "บล." in txt: set_data["บัญชีบริษัทหลักทรัพย์"] = net_val
                elif "ต่างชาติ" in txt or "ต่างประเทศ" in txt: set_data["นักลงทุนต่างชาติ"] = net_val
                elif "ในประเทศ" in txt or "ทั่วไป" in txt: set_data["นักลงทุนภายในประเทศ"] = net_val
    except Exception as e:
        print(f"Error SET Investor Type: {e}")

    # 2. ดึงข้อมูลตลาด TFEX
    print("กำลังดึงข้อมูลประเภทนักลงทุน TFEX...")
    try:
        page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        rows = page.locator("table tbody tr").all()
        for r in rows:
            cells = [c.text_content().strip() for c in r.locator("td, th").all()]
            if len(cells) >= 4:
                cat_name = cells[0]
                if any(k in cat_name for k in ["Futures", "Options", "Equity"]):
                    tfex_data["นักลงทุนสถาบัน"][cat_name] = cells[1]
                    tfex_data["นักลงทุนต่างชาติ"][cat_name] = cells[2]
                    tfex_data["นักลงทุนภายในประเทศ"][cat_name] = cells[3]
    except Exception as e:
        print(f"Error TFEX Investor Type: {e}")

    return set_data, tfex_data

def format_investor_message(set_data, tfex_data):
    """จัดรูปแบบข้อความที่จะส่งเข้า LINE"""
    groups = [
        ("🌐 **นักลงทุนต่างชาติ**", "นักลงทุนต่างชาติ"),
        ("🏦 **นักลงทุนสถาบัน**", "นักลงทุนสถาบัน"),
        ("💼 **บัญชีบริษัทหลักทรัพย์**", "บัญชีบริษัทหลักทรัพย์"),
        ("👤 **นักลงทุนภายในประเทศ**", "นักลงทุนภายในประเทศ")
    ]
    investor_lines = []
    for title, group_key in groups:
        lines = [title]
        set_net = set_data.get(group_key, "-")
        lines.append(f"• Equity Index: {set_net}")
        tfex_group = tfex_data.get(group_key, {})
        for cat in ["Equity Index Futures", "Single Stock Futures", "Currency Futures", "Equity Index Call Options", "Equity Index Put Options"]:
            val = tfex_group.get(cat, "-")
            lines.append(f"• {cat}: {val}")
        investor_lines.append("\n".join(lines))
        
    return "👥 **สรุปมูลค่าการซื้อขายตามประเภทนักลงทุน**\n\n" + "\n\n".join(investor_lines)

def send_line_message(message):
    """ส่งข้อความเข้า LINE"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}]
    }
    res = requests.post(url, headers=headers, json=payload)
    print(f"--- LINE API RESULT --- Status: {res.status_code}")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        set_data, tfex_data = fetch_investor_type_data(page)
        msg = format_investor_message(set_data, tfex_data)
        
        browser.close()

        send_line_message(msg)
        print("ส่งสรุปประเภทนักลงทุนเข้า LINE สำเร็จ!")

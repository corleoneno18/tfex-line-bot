import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

def format_number_with_sign(val_str):
    """แปลงตัวเลขให้มีเครื่องหมาย + นำหน้าหากเป็นค่าบวก"""
    if not val_str or val_str == "-":
        return "-"
    # ตัดเครื่องหมาย + เดิมออกก่อนเพื่อนำมาวิเคราะห์
    clean_val = val_str.replace("+", "").replace(",", "").strip()
    try:
        num = int(clean_val)
        if num > 0:
            return f"+{num:,}"
        else:
            return f"{num:,}"
    except ValueError:
        return val_str

def fetch_investor_type_data(page):
    """ดึงข้อมูลประเภทนักลงทุน TFEX จากตารางบนเว็บ Settrade"""
    tfex_data = {
        "นักลงทุนสถาบัน": {},
        "นักลงทุนต่างชาติ": {},
        "นักลงทุนภายในประเทศ": {}
    }

    print("กำลังดึงข้อมูลประเภทนักลงทุน TFEX...")
    try:
        page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="domcontentloaded", timeout=30000)
        
        # เลื่อนหน้าจอลงมาเพื่อให้คอมโพเนนต์เริ่มโหลด
        page.evaluate("window.scrollBy(0, 300)")
        time.sleep(5)
        
        rows = page.locator("table tbody tr").all()
        for r in rows:
            text = r.text_content().strip()
            cleaned_text = " ".join(text.split())
            
            categories = [
                "Equity Index Futures",
                "Single Stock Futures",
                "Currency Futures",
                "Equity Index Call Options",
                "Equity Index Put Options"
            ]
            
            for cat in categories:
                if cat in cleaned_text:
                    nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*', cleaned_text)
                    if len(nums) >= 3:
                        # ใส่ฟังก์ชันจัดรูปแบบเครื่องหมาย + / - ให้ครบทุกกลุ่ม
                        tfex_data["นักลงทุนสถาบัน"][cat] = format_number_with_sign(nums[0])
                        tfex_data["นักลงทุนต่างชาติ"][cat] = format_number_with_sign(nums[1])
                        tfex_data["นักลงทุนภายในประเทศ"][cat] = format_number_with_sign(nums[2])

    except Exception as e:
        print(f"Error TFEX Investor Type: {e}")

    return tfex_data

def format_investor_message(tfex_data):
    """จัดรูปแบบข้อความ แสดงเฉพาะ ต่างชาติ, สถาบัน, และในประเทศ"""
    groups = [
        ("🌐 **นักลงทุนต่างชาติ**", "นักลงทุนต่างชาติ"),
        ("🏦 **นักลงทุนสถาบัน**", "นักลงทุนสถาบัน"),
        ("👤 **นักลงทุนภายในประเทศ**", "นักลงทุนภายในประเทศ")
    ]
    
    categories = [
        "Equity Index Futures",
        "Single Stock Futures",
        "Currency Futures",
        "Equity Index Call Options",
        "Equity Index Put Options"
    ]
    
    investor_lines = []
    for title, group_key in groups:
        lines = [title]
        tfex_group = tfex_data.get(group_key, {})
        for cat in categories:
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

        tfex_data = fetch_investor_type_data(page)
        msg = format_investor_message(tfex_data)
        
        browser.close()

        send_line_message(msg)
        print("ส่งสรุปประเภทนักลงทุนเข้า LINE สำเร็จ!")

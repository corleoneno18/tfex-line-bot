import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

def format_number_with_sign(val_str):
    """แปลงตัวเลขให้มีเครื่องหมาย + นำหน้าหากเป็นค่าบวก"""
    if not val_str or val_str == "-":
        return "-"
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
    """ดึงยอดสุทธิประเภทนักลงทุน TFEX จากตาราง Settrade"""
    tfex_data = {
        "นักลงทุนต่างชาติ": {},
        "นักลงทุนสถาบัน": {},
        "นักลงทุนภายในประเทศ": {}
    }

    print("กำลังดึงข้อมูลประเภทนักลงทุน TFEX...")
    try:
        page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        
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
                    # ในตาราง TFEX แต่ละแถวจะมี 9 ตัวเลข:
                    # [0]: สถาบัน ซื้อ, [1]: สถาบัน ขาย, [2]: สถาบัน สุทธิ
                    # [3]: ต่างชาติ ซื้อ, [4]: ต่างชาติ ขาย, [5]: ต่างชาติ สุทธิ
                    # [6]: ในประเทศ ซื้อ, [7]: ในประเทศ ขาย, [8]: ในประเทศ สุทธิ
                    nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*|-', cleaned_text)
                    if len(nums) >= 9:
                        tfex_data["นักลงทุนสถาบัน"][cat] = format_number_with_sign(nums[2])
                        tfex_data["นักลงทุนต่างชาติ"][cat] = format_number_with_sign(nums[5])
                        tfex_data["นักลงทุนภายในประเทศ"][cat] = format_number_with_sign(nums[8])

    except Exception as e:
        print(f"Error TFEX Investor Type: {e}")

    return tfex_data

def format_investor_message(tfex_data):
    """จัดรูปแบบข้อความ TFEX แยกตามประเภทนักลงทุน (3 กลุ่มหลัก)"""
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
        
    return "👥 **สรุปมูลค่าการซื้อขายตามประเภทนักลงทุน (TFEX)**\n\n" + "\n\n".join(investor_lines)

def send_line_message(message):
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
        print("ส่งสรุปประเภทนักลงทุน TFEX เข้า LINE สำเร็จ!")

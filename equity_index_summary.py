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
        num = float(clean_val)
        if num > 0:
            return f"+{num:,.2f}"
        else:
            return f"{num:,.2f}"
    except ValueError:
        return val_str

def fetch_equity_index_data(page):
    """ดึงข้อมูลมูลค่าการซื้อขายตามกลุ่มนักลงทุนตลาดหุ้น (SET)"""
    equity_data = {}

    print("กำลังดึงข้อมูลมูลค่าการซื้อขายตลาดหุ้น (SET)...")
    try:
        # ไปที่หน้าสรุปมูลค่าการซื้อขายตามกลุ่มนักลงทุน SET โดยตรง
        page.goto("https://www.settrade.com/th/equities/market-data/investor-type", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        
        # ดึงแถวในตารางหลัก
        rows = page.locator("table tbody tr").all()
        for r in rows:
            text = r.text_content().strip()
            cleaned_text = " ".join(text.split())
            
            mapping = {
                "สถาบันในประเทศ": "สถาบัน",
                "บัญชีบริษัทหลักทรัพย์": "บัญชี บล.",
                "นักลงทุนต่างประเทศ": "ต่างชาติ",
                "นักลงทุนทั่วไปในประเทศ": "ในประเทศ"
            }
            
            for key_th, key_name in mapping.items():
                if key_th in cleaned_text:
                    # ดึงตัวเลขทั้งหมดในแถว (คอลัมน์สุทธิอยู่ตำแหน่งสุดท้าย)
                    nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-', cleaned_text)
                    if nums:
                        net_val = nums[-1]  # ยอดสุทธิ (ล้านบาท)
                        equity_data[key_name] = format_number_with_sign(net_val)

    except Exception as e:
        print(f"Error Equity Index: {e}")

    return equity_data

def format_equity_message(equity_data):
    """จัดรูปแบบข้อความสรุป SET"""
    msg = (
        "📊 **สรุปมูลค่าการซื้อขายตามกลุ่มนักลงทุน (SET)**\n\n"
        f"🌐 **นักลงทุนต่างชาติ**: {equity_data.get('ต่างชาติ', '-')} ลบ.\n"
        f"🏦 **นักลงทุนสถาบัน**: {equity_data.get('สถาบัน', '-')} ลบ.\n"
        f"👤 **นักลงทุนภายในประเทศ**: {equity_data.get('ในประเทศ', '-')} ลบ.\n"
        f"💼 **บัญชีบริษัทหลักทรัพย์**: {equity_data.get('บัญชี บล.', '-')} ลบ."
    )
    return msg

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

        equity_data = fetch_equity_index_data(page)
        msg = format_equity_message(equity_data)
        
        browser.close()

        send_line_message(msg)
        print("ส่งสรุป SET เข้า LINE สำเร็จ!")

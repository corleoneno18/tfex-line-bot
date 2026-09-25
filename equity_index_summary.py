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
            return f"+{num:,.2f}" if "." in clean_val else f"+{int(num):,}"
        else:
            return f"{num:,.2f}" if "." in clean_val else f"{int(num):,}"
    except ValueError:
        return val_str

def fetch_equity_index_data(page):
    """ดึงข้อมูลประเภทนักลงทุนเฉพาะ Equity Index (SET)"""
    equity_data = {}

    print("กำลังดึงข้อมูล Equity Index...")
    try:
        page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="domcontentloaded", timeout=30000)
        page.evaluate("window.scrollBy(0, 300)")
        time.sleep(5)
        
        rows = page.locator("table tbody tr").all()
        for r in rows:
            text = r.text_content().strip()
            cleaned_text = " ".join(text.split())
            
            if "Equity Index" in cleaned_text and "Futures" not in cleaned_text:
                nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-', cleaned_text)
                if len(nums) >= 4:
                    equity_data["สถาบัน"] = format_number_with_sign(nums[0])
                    equity_data["บัญชี บล."] = format_number_with_sign(nums[1])
                    equity_data["ต่างชาติ"] = format_number_with_sign(nums[2])
                    equity_data["ในประเทศ"] = format_number_with_sign(nums[3])
                elif len(nums) == 3:
                    equity_data["สถาบัน"] = format_number_with_sign(nums[0])
                    equity_data["ต่างชาติ"] = format_number_with_sign(nums[1])
                    equity_data["ในประเทศ"] = format_number_with_sign(nums[2])
    except Exception as e:
        print(f"Error Equity Index: {e}")

    return equity_data

def format_equity_message(equity_data):
    """จัดรูปแบบข้อความสรุป Equity Index"""
    msg = (
        "📊 **สรุปมูลค่าการซื้อขาย Equity Index**\n\n"
        f"🌐 **นักลงทุนต่างชาติ**: {equity_data.get('ต่างชาติ', '-')}\n"
        f"🏦 **นักลงทุนสถาบัน**: {equity_data.get('สถาบัน', '-')}\n"
        f"👤 **นักลงทุนภายในประเทศ**: {equity_data.get('ในประเทศ', '-')}\n"
        f"💼 **บัญชีบริษัทหลักทรัพย์**: {equity_data.get('บัญชี บล.', '-')}"
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
        print("ส่งสรุป Equity Index เข้า LINE สำเร็จ!")

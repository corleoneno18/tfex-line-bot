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
    except (ValueError, TypeError):
        return val_str

def fetch_equity_index_data():
    """ดึงข้อมูลมูลค่าการซื้อขายตามกลุ่มนักลงทุนตลาดหุ้น (SET)"""
    equity_data = {}

    print("กำลังดึงข้อมูลมูลค่าการซื้อขายตลาดหุ้น (SET)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            # ไปหน้าประเภทนักลงทุนของ SET
            page.goto("https://www.settrade.com/th/equities/market-data/investor-type", wait_until="domcontentloaded", timeout=45000)
            
            # รอ 5 วินาทีให้สคริปต์หน้าเว็บทำงาน
            time.sleep(5)
            
            # หากมี Cookie Banner หรือ Modal ให้ยอมรับ/ปิด
            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass
            
            # เลื่อนหน้าจอลงมาเล็กน้อยเพื่อ Trigger Lazy Loading
            page.evaluate("window.scrollBy(0, 300)")
            time.sleep(3)

            # ค้นหาตาราง
            rows = page.locator("table tr").all()
            
            mapping = {
                "สถาบันในประเทศ": "นักลงทุนสถาบัน",
                "บัญชีบริษัทหลักทรัพย์": "บัญชีบริษัทหลักทรัพย์",
                "นักลงทุนต่างประเทศ": "นักลงทุนต่างชาติ",
                "นักลงทุนทั่วไปในประเทศ": "นักลงทุนภายในประเทศ"
            }
            
            for r in rows:
                text = r.text_content().strip()
                cleaned_text = " ".join(text.split())
                
                for key_th, key_name in mapping.items():
                    if key_th in cleaned_text:
                        # ดึงตัวเลขทั้งหมดในแถว
                        nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-', cleaned_text)
                        if nums:
                            # ยอดสุทธิอยู่ตัวเลขสุดท้ายของแถว
                            net_val = nums[-1]
                            equity_data[key_name] = format_number_with_sign(net_val)

        except Exception as e:
            print(f"Playwright Error: {e}")
        finally:
            browser.close()

    return equity_data

def format_equity_message(equity_data):
    """จัดรูปแบบข้อความสรุป SET (ไม่มี ** เครื่องหมายตัวหนา)"""
    msg = (
        "📊 สรุปมูลค่าการซื้อขายตามกลุ่มนักลงทุน (SET)\n\n"
        f"🌐 นักลงทุนต่างชาติ: {equity_data.get('นักลงทุนต่างชาติ', '-')} ลบ.\n"
        f"🏦 นักลงทุนสถาบัน: {equity_data.get('นักลงทุนสถาบัน', '-')} ลบ.\n"
        f"👤 นักลงทุนภายในประเทศ: {equity_data.get('นักลงทุนภายในประเทศ', '-')} ลบ.\n"
        f"💼 บัญชีบริษัทหลักทรัพย์: {equity_data.get('บัญชีบริษัทหลักทรัพย์', '-')} ลบ."
    )
    return msg

def send_line_message(message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        print("กรุณาตั้งค่า LINE_CHANNEL_ACCESS_TOKEN และ LINE_USER_ID")
        return
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
    data = fetch_equity_index_data()
    msg = format_equity_message(data)
    send_line_message(msg)

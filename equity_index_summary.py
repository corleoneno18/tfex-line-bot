import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

def format_number_with_sign(val_str):
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
            page.goto("https://www.settrade.com/th/equities/market-data/historical-report/investor-type", wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)
            
            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass
            
            rows = page.locator("tr").all()
            for r in rows:
                row_text = " ".join(r.text_content().split())
                
                # ตรวจจับแถวกลุ่มนักลงทุน
                matched_key = None
                if "สถาบันในประเทศ" in row_text or "สถาบัน" in row_text:
                    matched_key = "นักลงทุนสถาบัน"
                elif "บัญชีบริษัทหลักทรัพย์" in row_text or "หลักทรัพย์" in row_text:
                    matched_key = "บัญชีบริษัทหลักทรัพย์"
                elif "นักลงทุนต่างประเทศ" in row_text or "ต่างชาติ" in row_text:
                    matched_key = "นักลงทุนต่างชาติ"
                elif "นักลงทุนทั่วไปในประเทศ" in row_text or "ภายในประเทศ" in row_text:
                    matched_key = "นักลงทุนภายในประเทศ"
                
                if matched_key:
                    # ดึง td ทั้งหมดในแถวนั้นเพื่อหาคอลัมน์สุทธิรายวัน
                    tds = r.locator("td").all()
                    if len(tds) >= 5:
                        # คอลัมน์ที่ 5 (index 4) คือ ยอดสุทธิรายวัน
                        daily_net_text = tds[4].text_content().strip()
                        equity_data[matched_key] = format_number_with_sign(daily_net_text)
                    else:
                        # สำรองกรณีดึง td ไม่ได้ ใช้ regex ดึงตัวเลขกลุ่มแรกๆ (สุทธิรายวันคือตัวเลขที่ 5 ของแถว)
                        nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-', row_text)
                        if len(nums) >= 5:
                            equity_data[matched_key] = format_number_with_sign(nums[4])

        except Exception as e:
            print(f"Playwright SET Error: {e}")
        finally:
            browser.close()

    return equity_data

def format_equity_message(equity_data):
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

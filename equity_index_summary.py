import os
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

            # ตรวจสอบว่าเลือก Tab 'SET' อยู่
            try:
                set_tab = page.locator("button:has-text('SET'), a:has-text('SET')").first
                if set_tab.is_visible():
                    set_tab.click()
                    time.sleep(2)
            except Exception:
                pass

            # หาตำแหน่งคอลัมน์ "สุทธิ" ของกลุ่ม "รายวัน"
            target_col_index = -1
            header_rows = page.locator("table thead tr").all()
            
            if len(header_rows) >= 2:
                # แถวล่างสุดของ Header จะมีคำว่า "สุทธิ" ซ้ำกันหลายช่วง (รายวัน, รายเดือน, ต้นปี)
                bottom_headers = header_rows[-1].locator("th, td").all()
                net_count = 0
                for idx, h in enumerate(bottom_headers):
                    text = h.text_content().strip()
                    if "สุทธิ" in text:
                        net_count += 1
                        if net_count == 1: # สุทธิอันแรก = สุทธิรายวัน
                            target_col_index = idx
                            break

            # หากระหา Index ไม่เจอ ให้ใช้ Default index สำรอง
            if target_col_index == -1:
                target_col_index = 4

            # ดึงข้อมูลจาก Body ตาม Index ที่ระบุ
            rows = page.locator("table tbody tr").all()
            for r in rows:
                tds = r.locator("td").all()
                if len(tds) > target_col_index:
                    investor_type = tds[0].text_content().strip()
                    daily_net_val = tds[target_col_index].text_content().strip()
                    formatted_val = format_number_with_sign(daily_net_val)
                    
                    if "สถาบัน" in investor_type:
                        equity_data["นักลงทุนสถาบัน"] = formatted_val
                    elif "หลักทรัพย์" in investor_type:
                        equity_data["บัญชีบริษัทหลักทรัพย์"] = formatted_val
                    elif "ต่างประเทศ" in investor_type or "ต่างชาติ" in investor_type:
                        equity_data["นักลงทุนต่างชาติ"] = formatted_val
                    elif "ทั่วไปในประเทศ" in investor_type or "ภายในประเทศ" in investor_type:
                        equity_data["นักลงทุนภายในประเทศ"] = formatted_val

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

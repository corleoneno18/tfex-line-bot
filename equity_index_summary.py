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
    
    # 1. พยายามยิงดึงจาก SET API โดยตรงก่อน (ไวและไม่ติด Browser Timeout)
    api_urls = [
        "https://api.settrade.com/api/market/investor-type/set",
        "https://api.settrade.com/api/set/investor-type"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.settrade.com/"
    }
    
    for url in api_urls:
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                items = data.get("data", []) if isinstance(data.get("data"), list) else data.get("investorTypes", [])
                for item in items:
                    name = item.get("investorTypeName", "") or item.get("name", "")
                    net = item.get("netBuySell", 0) or item.get("netValue", 0)
                    
                    if "ต่างชาติ" in name or "ต่างประเทศ" in name:
                        equity_data["นักลงทุนต่างชาติ"] = format_number_with_sign(str(net))
                    elif "สถาบัน" in name:
                        equity_data["นักลงทุนสถาบัน"] = format_number_with_sign(str(net))
                    elif "ส่วนบุคคล" in name or "ภายในประเทศ" in name or "รายย่อย" in name:
                        equity_data["นักลงทุนภายในประเทศ"] = format_number_with_sign(str(net))
                    elif "บัญชีบริษัทหลักทรัพย์" in name or "บล." in name:
                        equity_data["บัญชีบริษัทหลักทรัพย์"] = format_number_with_sign(str(net))
                
                if len(equity_data) >= 4:
                    print("ดึงข้อมูล SET ผ่าน API สำเร็จ")
                    return equity_data
        except Exception:
            pass

    # 2. Fallback: ใช้ Playwright ดึงจาก URL historical-report
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            # ใช้ domcontentloaded เพื่อป้องกัน timeout จาก networkidle
            page.goto("https://www.settrade.com/th/equities/market-data/historical-report/investor-type", wait_until="domcontentloaded", timeout=45000)
            time.sleep(6)
            
            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass
            
            rows = page.locator("tr").all()
            for r in rows:
                row_text = " ".join(r.text_content().split())
                nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-', row_text)
                if not nums:
                    continue
                
                val = format_number_with_sign(nums[-1])
                if "ต่างชาติ" in row_text or "ต่างประเทศ" in row_text:
                    equity_data["นักลงทุนต่างชาติ"] = val
                elif "สถาบัน" in row_text:
                    equity_data["นักลงทุนสถาบัน"] = val
                elif "ภายในประเทศ" in row_text or "ส่วนบุคคล" in row_text or "รายย่อย" in row_text:
                    equity_data["นักลงทุนภายในประเทศ"] = val
                elif "บัญชีบริษัทหลักทรัพย์" in row_text or "หลักทรัพย์" in row_text:
                    equity_data["บัญชีบริษัทหลักทรัพย์"] = val

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

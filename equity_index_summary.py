import os
import requests

def format_number_with_sign(val):
    """แปลงตัวเลขให้มีเครื่องหมาย + นำหน้าหากเป็นค่าบวก"""
    if val is None:
        return "-"
    try:
        num = float(val)
        if num > 0:
            return f"+{num:,.2f}"
        else:
            return f"{num:,.2f}"
    except (ValueError, TypeError):
        return str(val)

def fetch_equity_index_data():
    """ดึงข้อมูลการซื้อขายแยกตามกลุ่มนักลงทุน SET จาก API"""
    equity_data = {}
    
    # URL API ของ Settrade สำหรับสถิติรายกลุ่มนักลงทุน SET
    url = "https://api.settrade.com/api/set/equity/investor-type"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.settrade.com/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            # โครงสร้าง JSON ของ Settrade มักจะมีรายการนักลงทุน
            # ตัวอย่างคีย์: investorType, netValue (ล้านบาท)
            items = data.get("investorTypes", data if isinstance(data, list) else [])
            
            mapping = {
                "INSTITUTION": "สถาบัน",
                "PROPRIETARY": "บัญชี บล.",
                "FOREIGN": "ต่างชาติ",
                "INDIVIDUAL": "ในประเทศ",
                "สถาบันในประเทศ": "สถาบัน",
                "บัญชีบริษัทหลักทรัพย์": "บัญชี บล.",
                "นักลงทุนต่างประเทศ": "ต่างชาติ",
                "นักลงทุนทั่วไปในประเทศ": "ในประเทศ"
            }
            
            for item in items:
                name = item.get("investorTypeName", item.get("name", ""))
                net_val = item.get("netValue", item.get("net", None))
                
                for key_th, key_name in mapping.items():
                    if key_th in name:
                        equity_data[key_name] = format_number_with_sign(net_val)
                        
    except Exception as e:
        print(f"Error fetching SET API: {e}")

    # หาก API หลักเปลี่ยน Endpoint ให้สำรองด้วย Playwright แบบรอ Element โหลดจริง
    if not equity_data:
        print("API ไม่ตอบสนอง สลับไปใช้ Playwright สแครปข้อมูล...")
        equity_data = fetch_equity_via_playwright()

    return equity_data

def fetch_equity_via_playwright():
    from playwright.sync_api import sync_playwright
    import time
    import re
    
    equity_data = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("https://www.settrade.com/th/equities/market-data/investor-type", timeout=60000)
            # รอจนกว่าตารางจะมีข้อมูลตัวเลขโผล่ขึ้นมาจริงๆ
            page.wait_for_selector("table tbody tr td", timeout=15000)
            time.sleep(3)
            
            rows = page.locator("table tbody tr").all()
            mapping = {
                "สถาบันในประเทศ": "สถาบัน",
                "บัญชีบริษัทหลักทรัพย์": "บัญชี บล.",
                "นักลงทุนต่างประเทศ": "ต่างชาติ",
                "นักลงทุนทั่วไปในประเทศ": "ในประเทศ"
            }
            
            for r in rows:
                text = " ".join(r.text_content().split())
                for key_th, key_name in mapping.items():
                    if key_th in text:
                        nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-', text)
                        if nums:
                            equity_data[key_name] = format_number_with_sign(nums[-1])
        except Exception as e:
            print(f"Playwright Fallback Error: {e}")
        finally:
            browser.close()
    return equity_data

def format_equity_message(equity_data):
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

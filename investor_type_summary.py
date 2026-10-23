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
        num = int(float(clean_val))
        if num > 0:
            return f"+{num:,}"
        else:
            return f"{num:,}"
    except (ValueError, TypeError):
        return val_str

def fetch_investor_type_data():
    tfex_data = {
        "นักลงทุนต่างชาติ": {},
        "นักลงทุนสถาบัน": {},
        "นักลงทุนภายในประเทศ": {}
    }
    overview_data = {
        "Call": "-",
        "Put": "-"
    }

    print("กำลังดึงข้อมูลประเภทนักลงทุนและ Total Options TFEX...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # 1. ดึงข้อมูลหน้า Investor Type ปกติ
        try:
            page.goto("https://www.settrade.com/th/derivatives/market-data/investor-type", wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            
            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass

            page.evaluate("window.scrollBy(0, 400)")
            time.sleep(2)

            rows = page.locator("tr").all()
            categories = [
                "Equity Index Futures",
                "Single Stock Futures",
                "Currency Futures",
                "Equity Index Call Options",
                "Equity Index Put Options"
            ]
            
            for r in rows:
                text = r.text_content().strip()
                cleaned_text = " ".join(text.split())
                
                for cat in categories:
                    if cat in cleaned_text:
                        nums = re.findall(r'[-+]?\d{1,3}(?:,\d{3})*|-', cleaned_text)
                        if len(nums) >= 9:
                            tfex_data["นักลงทุนสถาบัน"][cat] = format_number_with_sign(nums[2])
                            tfex_data["นักลงทุนต่างชาติ"][cat] = format_number_with_sign(nums[5])
                            tfex_data["นักลงทุนภายในประเทศ"][cat] = format_number_with_sign(nums[8])
        except Exception as e:
            print(f"Error TFEX Investor Type: {e}")

        # 2. ดึงข้อมูลหน้า Overview โดยใช้ Locator เจาะจงแถว Call และ Put ภายใต้ Equity Index โดยตรง
        try:
            page.goto("https://www.settrade.com/th/derivatives/overview", wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            
            try:
                page.click("button:has-text('ยอมรับ')", timeout=3000)
            except Exception:
                pass

            # เลื่อนหน้าจอลงมาเล็กน้อยเพื่อให้ตารางเรนเดอร์ครบถ้วน
            page.evaluate("window.scrollBy(0, 300)")
            time.sleep(2)

            # ค้นหาทุกแถวในตารางเพื่อดึงตัวเลข Open Interest (ช่องขวาสุด) ของ Call และ Put
            rows = page.locator("tr, div").all()
            for r in rows:
                txt = " ".join(r.text_content().split())
                # เช็คแถวที่เป็น Call ของ Equity Index
                if "Call" in txt and "Put / Call" not in txt and "Options" not in txt:
                    tds = r.locator("td").all()
                    if len(tds) >= 2:
                        val = tds[-1].text_content().strip()
                        if val and val != "-":
                            overview_data["Call"] = val
                # เช็คแถวที่เป็น Put ของ Equity Index
                elif "Put" in txt and "Put / Call" not in txt and "Options" not in txt:
                    tds = r.locator("td").all()
                    if len(tds) >= 2:
                        val = tds[-1].text_content().strip()
                        if val and val != "-":
                            overview_data["Put"] = val

        except Exception as e:
            print(f"Error TFEX Overview Options: {e}")
        finally:
            browser.close()

    return tfex_data, overview_data

def format_investor_message(tfex_data, overview_data):
    groups = [
        ("🌐 นักลงทุนต่างชาติ", "นักลงทุนต่างชาติ"),
        ("🏦 นักลงทุนสถาบัน", "นักลงทุนสถาบัน"),
        ("👤 นักลงทุนภายในประเทศ", "นักลงทุนภายในประเทศ")
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
        
    msg = "👥 สรุปมูลค่าการซื้อขายตามประเภทนักลงทุน (TFEX)\n\n" + "\n\n".join(investor_lines)
    msg += f"\n\n📈 Total Options (Equity Index)\n• Call: {overview_data.get('Call', '-')}\n• Put: {overview_data.get('Put', '-')}"
    
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
    tfex_data, overview_data = fetch_investor_type_data()
    msg = format_investor_message(tfex_data, overview_data)
    send_line_message(msg)

import os
import re
import time
import requests
from datetime import datetime
from google import genai
from playwright.sync_api import sync_playwright

def get_all_s50_symbols(page):
    """1. ดึงรายชื่อสัญญาทั้งหมดจากหน้าตารางรวม"""
    list_url = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    print("กำลังดึงรายชื่อสัญญา SET50 ทั้งหมด...")
    page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("table", timeout=30000)
    time.sleep(3)
    
    text_content = page.locator("body").inner_text()
    symbols = list(dict.fromkeys(re.findall(r'S50[A-Z0-9]+', text_content)))
    print(f"พบสัญญา SET50 ทั้งหมด {len(symbols)} รายการ: {symbols}")
    return symbols

def parse_thai_date_to_datetime(date_str):
    """แปลงข้อความวันแบบไทย เช่น '29 ก.ย. 2569' เป็น datetime object เพื่อใช้นับวันคงเหลือ"""
    thai_months = {
        "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
        "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12
    }
    try:
        parts = date_str.strip().split()
        if len(parts) == 3:
            day = int(parts[0])
            month = thai_months.get(parts[1], 1)
            year = int(parts[2]) - 543  # แปลง พ.ศ. เป็น ค.ศ.
            return datetime(year, month, day)
    except Exception as e:
        print(f"แปลงวันที่ไม่ได้ ({date_str}): {e}")
    return None

def get_symbol_overview_data(page, symbol):
    """2. เข้าหน้า Overview ของแต่ละสัญญาเพื่อแกะค่าตัวเลขและวันหมดอายุ"""
    quote_url = f"https://www.settrade.com/th/derivatives/quote/{symbol}/overview"
    print(f"กำลังดึงข้อมูลหน้า Overview ของ {symbol}...")
    
    try:
        page.goto(quote_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3) # รอให้ตัวเลข dynamic โหลดครบ
        
        body_text = page.locator("body").inner_text()
        
        # ฟังก์ชันช่วยค้นหาตัวเลขด้วย Regex
        def extract_val(pattern, text, default="-"):
            m = re.search(pattern, text)
            return m.group(1).strip() if m else default

        # แกะค่าตัวเลขจากโครงสร้างข้อความหน้า Overview
        last = extract_val(r'([0-9\,\.]+)\s*[\+\-]\d+', body_text)
        change_pct = extract_val(r'([\+\-][0-9\,\.]+\s*\([\+\-][0-9\,\.]%\))', body_text)
        high = extract_val(r'ราคาสูงสุด\s*([0-9\,\.]+)', body_text)
        low = extract_val(r'ราคาต่ำสุด\s*([0-9\,\.]+)', body_text)
        avg = extract_val(r'ราคาเฉลี่ย\s*([0-9\,\.]+)', body_text)
        open_p = extract_val(r'ราคาเปิด\s*([0-9\,\.]+)', body_text)
        vol = extract_val(r'ปริมาณ\s*\(สัญญา\)\s*([0-9\,]+)', body_text)
        oi = extract_val(r'สถานะคงค้าง\s*\(สัญญา\)\s*([0-9\,]+)', body_text)
        
        # ดึงวันซื้อขายวันสุดท้าย (เช่น '29 ก.ย. 2569')
        last_trading_day = extract_val(r'วันซื้อขายวันสุดท้าย\s*([\d]+\s+[ก-ฮ\.]+\s+[\d]+)', body_text)
        
        # คำนวณวันคงเหลือ
        remaining_days_str = "-"
        if last_trading_day != "-":
            expire_date = parse_thai_date_to_datetime(last_trading_day)
            if expire_date:
                today = datetime.now()
                delta = (expire_date.date() - today.date()).days
                remaining_days_str = f"{delta} วัน" if delta >= 0 else "หมดอายุแล้ว"

        # แปลงตัวเลข ปริมาณ และ OI สำหรับคำนวณผลรวมและการเรียงลำดับ
        vol_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
        oi_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0

        return {
            "symbol": symbol,
            "last_trading_day": last_trading_day,
            "remaining_days": remaining_days_str,
            "last": last,
            "change_pct": change_pct,
            "high": high,
            "low": low,
            "avg": avg,
            "open": open_p,
            "vol": vol,
            "oi": oi,
            "vol_num": vol_num,
            "oi_num": oi_num
        }
    except Exception as e:
        print(f"ไม่สามารถดึงข้อมูลของ {symbol} ได้: {e}")
        return None

def fetch_all_data():
    """3. บริหารการดึงข้อมูลทีละตัวจนครบ"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        symbols = get_all_s50_symbols(page)
        if not symbols:
            browser.close()
            return None, 0, 0
            
        results = []
        total_vol = 0
        total_oi = 0
        
        for sym in symbols:
            data = get_symbol_overview_data(page, sym)
            if data:
                results.append(data)
                total_vol += data["vol_num"]
                total_oi += data["oi_num"]
                
        browser.close()
        return results, total_vol, total_oi

def format_line_message(results, total_vol, total_oi):
    """4. จัดเรียงลำดับตาม OI (มากไปน้อย) และเพิ่มวันซื้อขายวันสุดท้าย/วันคงเหลือ"""
    results_sorted = sorted(results, key=lambda x: x["oi_num"], reverse=True)
    
    lines = []
    for item in results_sorted:
        lines.append(
            f"📌 **[{item['symbol']}]**\n"
            f"• วันซื้อขายวันสุดท้าย: {item['last_trading_day']}\n"
            f"• วันคงเหลือ: {item['remaining_days']}\n"
            f"• ราคาล่าสุด: {item['last']} {item['change_pct']}\n"
            f"• ราคาเปิด: {item['open']}\n"
            f"• ราคาสูงสุด: {item['high']}\n"
            f"• ราคาต่ำสุด: {item['low']}\n"
            f"• ราคาเฉลี่ย: {item['avg']}\n"
            f"• ปริมาณ (สัญญา): {item['vol']}\n"
            f"• สถานะคงค้าง (OI): {item['oi']}"
        )
        
    summary_text = "\n\n".join(lines)
    summary_text += f"\n\n📊 **สรุปรวม SET50 Futures ทั้งหมด**\n• ปริมาณการซื้อขายรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม (OI): {total_oi:,} สัญญา"
    return summary_text

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
        "messages": [
            {
                "type": "text",
                "text": f"📊 สรุป SET50 Futures วันนี้ (เรียงตาม OI สูงสุด):\n\n{message}"
            }
        ]
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"--- LINE API RESULT ---")
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")
    print(f"----------------------")

if __name__ == "__main__":
    try:
        results, total_vol, total_oi = fetch_all_data()
        if results:
            message = format_line_message(results, total_vol, total_oi)
            send_line_message(message)
            print("ส่งข้อมูลเข้า LINE สำเร็จเรียบร้อย!")
        else:
            print("ไม่สามารถดึงข้อมูลได้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")

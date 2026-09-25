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

def parse_thai_month_year(expiry_text):
    """
    แปลงข้อความเช่น 'ก.ย. 2569' หรือ '29 ก.ย. 2569' ให้เป็นวันที่สุดท้ายของเดือนนั้นๆ
    เพื่อใช้นับวันคงเหลืออย่างแม่นยำ
    """
    thai_months = {
        "ม.ค.": (1, 31), "ก.พ.": (2, 28), "มี.ค.": (3, 31), "เม.ย.": (4, 30),
        "พ.ค.": (5, 31), "มิ.ย.": (6, 30), "ก.ค.": (7, 31), "ส.ค.": (8, 31),
        "ก.ย.": (9, 30), "ต.ค.": (10, 31), "พ.ย.": (11, 30), "ธ.ค.": (12, 31)
    }
    try:
        # หากระบุวันด้วย เช่น '29 ก.ย. 2569'
        m_day = re.search(r'(\d+)\s+([ก-ฮ\.]+)\s+(\d{4})', expiry_text)
        if m_day:
            d = int(m_day.group(1))
            m = thai_months.get(m_day.group(2), (1, 31))[0]
            y = int(m_day.group(3)) - 543
            return datetime(y, m, d)

        # หากระบุเป็นเดือน เช่น 'ก.ย. 2569'
        m_m = re.search(r'([ก-ฮ\.]+)\s+(\d{4})', expiry_text)
        if m_m:
            m_str = m_m.group(1)
            y = int(m_m.group(2)) - 543
            m_info = thai_months.get(m_str, (1, 30))
            m = m_info[0]
            d = m_info[1] # ใช้วันสุดท้ายของเดือนเป็นวันหมดอายุสัญญา
            return datetime(y, m, d)
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการแปลงวันที่ ({expiry_text}): {e}")
    return None

def get_symbol_overview_data(page, symbol):
    """2. เข้าหน้า Overview ของแต่ละสัญญาเพื่อแกะค่าตัวเลขและวันหมดอายุ"""
    quote_url = f"https://www.settrade.com/th/derivatives/quote/{symbol}/overview"
    print(f"กำลังดึงข้อมูลหน้า Overview ของ {symbol}...")
    
    try:
        page.goto(quote_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3) # รอให้ตัวเลข dynamic โหลดครบ
        
        body_text = page.locator("body").inner_text()
        
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
        
        # ดึงข้อความเดือนหมดอายุ / วันซื้อขายวันสุดท้าย (เช่น 'ก.ย. 2569')
        expiry_info = extract_val(r'เดือนหมดอายุ:\s*([ก-ฮ\.\s\d]+)', body_text)
        if expiry_info == "-":
            expiry_info = extract_val(r'วันซื้อขายวันสุดท้าย\s*([\d\s[ก-ฮ\.]+\d+)', body_text)
            
        # คำนวณวันคงเหลือ
        remaining_days_str = "-"
        if expiry_info != "-":
            expire_date = parse_thai_month_year(expiry_info)
            if expire_date:
                today = datetime.now()
                delta = (expire_date.date() - today.date()).days
                remaining_days_str = f"{delta} วัน" if delta >= 0 else "หมดอายุแล้ว"

        vol_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
        oi_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0

        return {
            "symbol": symbol,
            "expiry_info": expiry_info,
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
    """4. จัดเรียงลำดับตาม OI (มากไปน้อย) และจัดข้อความ"""
    results_sorted = sorted(results, key=lambda x: x["oi_num"], reverse=True)
    
    lines = []
    for item in results_sorted:
        lines.append(
            f"📌 **[{item['symbol']}]**\n"
            f"• เดือนหมดอายุ: {item['expiry_info']}\n"
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

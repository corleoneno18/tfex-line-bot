import os
import re
import time
import calendar
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# รหัสเดือนของ TFEX
MONTH_MAP = {
    'F': 1,  # ม.ค.
    'G': 2,  # ก.พ.
    'H': 3,  # มี.ค.
    'J': 4,  # เม.ย.
    'K': 5,  # พ.ค.
    'M': 6,  # มิ.ย.
    'N': 7,  # ก.ค.
    'Q': 8,  # ส.ค.
    'U': 9,  # ก.ย.
    'V': 10, # ต.ค.
    'X': 11, # พ.ย.
    'Z': 12  # ธ.ค.
}

def get_last_trading_day(symbol):
    """
    คำนวณวันทำการก่อนวันสุดท้ายของเดือน จากชื่อสัญญา (เช่น S50U26, S50M27)
    """
    match = re.match(r'S50([A-Z])(\d{2})', symbol)
    if not match:
        return None
    
    month_code, year_code = match.groups()
    month = MONTH_MAP.get(month_code)
    if not month:
        return None
    
    year = 2000 + int(year_code)
    
    # หาวันที่สุดท้ายของเดือน
    _, last_day = calendar.monthrange(year, month)
    dt = datetime(year, month, last_day)
    
    # หาวันทำการสุดท้าย (ถ้าเป็น ส.-อา. ให้ถอยกลับมาวันศุกร์)
    while dt.weekday() >= 5: # 5 = เสาร์, 6 = อาทิตย์
        dt -= timedelta(days=1)
        
    # ถอยลงมาอีก 1 วันทำการ เพื่อให้เป็น "วันทำการก่อนวันสุดท้าย"
    dt -= timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
        
    return dt

def calculate_remaining_days(symbol):
    """คำนวณจำนวนวันคงเหลือจากวันปัจจุบัน ไปจนถึงวันทำการก่อนวันสุดท้าย"""
    last_trade_dt = get_last_trading_day(symbol)
    if not last_trade_dt:
        return "-"
    
    today = datetime.now().date()
    target_date = last_trade_dt.date()
    
    delta = (target_date - today).days
    if delta < 0:
        return "หมดอายุแล้ว"
    return f"{delta} วัน"

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

def get_symbol_overview_data(page, symbol):
    """2. เข้าหน้า Overview ของแต่ละสัญญาเพื่อแกะค่าตัวเลข"""
    quote_url = f"https://www.settrade.com/th/derivatives/quote/{symbol}/overview"
    print(f"กำลังดึงข้อมูลหน้า Overview ของ {symbol}...")
    
    try:
        page.goto(quote_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3) # รอให้ตัวเลข dynamic โหลดครบ
        
        body_text = page.locator("body").inner_text()
        
        def extract_val(pattern, text, default="-"):
            m = re.search(pattern, text)
            return m.group(1).strip() if m else default

        # แกะค่าตัวเลขราคาและปริมาณ
        last = extract_val(r'([0-9\,\.]+)\s*[\+\-]\d+', body_text)
        change_pct = extract_val(r'([\+\-][0-9\,\.]+\s*\([\+\-][0-9\,\.]%\))', body_text)
        high = extract_val(r'ราคาสูงสุด\s*([0-9\,\.]+)', body_text)
        low = extract_val(r'ราคาต่ำสุด\s*([0-9\,\.]+)', body_text)
        avg = extract_val(r'ราคาเฉลี่ย\s*([0-9\,\.]+)', body_text)
        open_p = extract_val(r'ราคาเปิด\s*([0-9\,\.]+)', body_text)
        vol = extract_val(r'ปริมาณ\s*\(สัญญา\)\s*([0-9\,]+)', body_text)
        oi = extract_val(r'สถานะคงค้าง\s*\(สัญญา\)\s*([0-9\,]+)', body_text)
        
        # คำนวณวันคงเหลือจาก Symbol โดยตรง
        remaining_days_str = calculate_remaining_days(symbol)

        vol_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
        oi_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0

        return {
            "symbol": symbol,
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
    """4. จัดเรียงลำดับตาม OI (มากไปน้อย) และจัดข้อความแสดงเฉพาะวันคงเหลือ"""
    results_sorted = sorted(results, key=lambda x: x["oi_num"], reverse=True)
    
    lines = []
    for item in results_sorted:
        lines.append(
            f"📌 **[{item['symbol']}]**\n"
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

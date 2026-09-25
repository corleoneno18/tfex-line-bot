import os
import re
import time
import requests
from google import genai
from playwright.sync_api import sync_playwright

def get_tfex_data_via_playwright():
    """เปิดหน้าเว็บ Settrade ผ่าน Headless Browser เพื่อรอตาราง Render สมบูรณ์"""
    url = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    print("กำลังเปิดเบราว์เซอร์เพื่อดึงข้อมูลตาราง TFEX...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_selector("table", timeout=15000)
            time.sleep(3)
            
            content = page.locator("body").inner_text()
            browser.close()
            print("ดึงข้อมูลจากหน้าเว็บสำเร็จ!")
            return content
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงหน้าเว็บ: {e}")
            browser.close()
            return None

def fallback_parse_text(raw_text):
    """ฟังก์ชันสกัดข้อมูลด้วย Regex กรณี Gemini API ไม่พร้อมใช้งาน"""
    print("สลับมาใช้ระบบ Direct Regex Extractor...")
    pattern = r'(S50[A-Z0-9]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+%?)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+([\d,]+)\s+([\d,]+)'
    matches = re.findall(pattern, raw_text)
    
    if not matches:
        # หากค้นหาแพทเทิร์นตารางแบบละเอียดไม่เจอ ให้ส่งข้อความแจ้งเตือนพร้อมข้อมูลบางส่วน
        return "ไม่สามารถประมวลผลรูปแบบตารางได้ในขณะนี้"
        
    lines = []
    total_vol = 0
    total_oi = 0
    
    for m in matches:
        symbol, last, chg, pct, open_p, high, low, avg_p, vol, oi = m
        vol_num = int(vol.replace(',', '')) if vol.replace(',', '').isdigit() else 0
        oi_num = int(oi.replace(',', '')) if oi.replace(',', '').isdigit() else 0
        total_vol += vol_num
        total_oi += oi_num
        
        lines.append(
            f"📌 [{symbol}]\n"
            f"• ราคาล่าสุด: {last}\n"
            f"• เปลี่ยนแปลง: {chg} ({pct})\n"
            f"• สูงสุด / ต่ำสุด: {high} / {low}\n"
            f"• ราคาเปิด / เฉลี่ย: {open_p} / {avg_p}\n"
            f"• ปริมาณ (สัญญา): {vol}\n"
            f"• สถานะคงค้าง (OI): {oi}\n"
        )
        
    summary_text = "\n".join(lines)
    summary_text += f"\n📊 **รวม SET50 Futures**\n• ปริมาณรวม: {total_vol:,} สัญญา\n• สถานะคงค้างรวม: {total_oi:,} สัญญา"
    return summary_text

def summarize_with_gemini(raw_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    จากข้อความหน้าเว็บ Settrade TFEX ด้านล่างนี้ ให้สกัดข้อมูลตารางราคาของ SET50 Futures ทุก Series ทั้งหมดที่มี (เช่น S50U26, S50Z26 ฯลฯ)
    แล้วจัดรูปแบบสรุปเป็นข้อความอ่านง่ายสำหรับส่งเข้า LINE ดังนี้:

    📌 [ชื่อย่อสัญญา]
    • ราคาล่าสุด: 
    • เปลี่ยนแปลง: (พร้อม %)
    • สูงสุด / ต่ำสุด: 
    • ราคาเปิด / เฉลี่ย: 
    • ปริมาณ (สัญญา): 
    • สถานะคงค้าง (OI): 

    พร้อมสรุปผลรวม ปริมาณสัญญา และ สถานะคงค้าง ทั้งหมดท้ายข้อความด้วย

    ข้อมูลจากหน้าเว็บ:
    {raw_text[:12000]}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"กำลังเรียก Gemini API ครั้งที่ {attempt + 1}...")
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            print("Gemini ประมวลผลสำเร็จ!")
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg or "UNAVAILABLE" in err_msg:
                wait_time = (attempt + 1) * 5
                print(f"เซิร์ฟเวอร์หนาแน่น (503) รอ {wait_time} วินาที...")
                time.sleep(wait_time)
            else:
                print(f"เกิดข้อผิดพลาดกับ Gemini: {err_msg}")
                break
                
    print("Gemini API ไม่พร้อมใช้งาน สลับไปใช้ Fallback Extractor...")
    return fallback_parse_text(raw_text)

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
                "text": f"📊 สรุป SET50 Futures วันนี้:\n\n{message}"
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
        raw_content = get_tfex_data_via_playwright()
        if raw_content:
            summary = summarize_with_gemini(raw_content)
            send_line_message(summary)
            print("ทำงานสำเร็จ!")
        else:
            print("ไม่สามารถดึงข้อมูลจากหน้าเว็บได้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")

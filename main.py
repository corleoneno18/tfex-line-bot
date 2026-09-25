import os
import re
import time
import requests
from google import genai
from playwright.sync_api import sync_playwright

def get_tfex_data_via_playwright():
    """เปิดหน้าเว็บ Settrade ผ่าน Playwright เพื่อดึงทั้ง innerText และ HTML"""
    url = "https://www.settrade.com/th/derivatives/market-data/trading-quotation-by-series"
    print("กำลังเปิดเบราว์เซอร์เพื่อดึงข้อมูลตาราง TFEX...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            print("กำลังรอโหลดตารางราคา...")
            page.wait_for_selector("table", timeout=30000)
            time.sleep(5)  # รอให้ข้อมูลตัวเลข Render ครบ
            
            # ดึงข้อความและ HTML
            text_content = page.locator("body").inner_text()
            html_content = page.content()
            browser.close()
            print("ดึงข้อมูลจากหน้าเว็บสำเร็จ!")
            return text_content, html_content
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงหน้าเว็บ: {e}")
            browser.close()
            return None, None

def fallback_parse_content(text_content, html_content):
    """ฟังก์ชันสกัดข้อมูลสำรอง กรณี Gemini API ไม่พร้อมใช้งาน"""
    print("สลับมาใช้ระบบ Fallback Extractor...")
    
    # 1. ลองใช้ Regex แบบยืดหยุ่นหาจาก Text Content
    symbols = re.findall(r'S50[A-Z0-9]+', text_content)
    unique_symbols = list(dict.fromkeys(symbols))  # กรองตัวซ้ำ
    
    if unique_symbols:
        lines = []
        for sym in unique_symbols:
            # ค้นหาบรรทัดที่มีชื่อสัญลักษณ์
            pattern = re.escape(sym) + r'[\s\S]{1,100}'
            match = re.search(pattern, text_content)
            if match:
                snippet = match.group(0).replace('\n', ' ')
                lines.append(f"📌 [{sym}]\n• ข้อมูล: {snippet[:80]}...")
        
        if lines:
            return "\n\n".join(lines)

    return "ระบบไม่สามารถดึงข้อมูลตารางได้ กรุณาตรวจสอบหน้าเว็บ Settrade อีกครั้ง"

def summarize_with_gemini(raw_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    จากข้อความหน้าเว็บ Settrade TFEX ด้านล่างนี้ ให้สกัดข้อมูลตารางราคาของ SET50 Futures ทุก Series ทั้งหมดที่มี (เช่น S50U26, S50Z26, S50H27 ฯลฯ)
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
    {raw_text[:15000]}
    """
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"กำลังเรียก Gemini API ครั้งที่ {attempt + 1}...")
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            if response.text and "📌" in response.text:
                print("Gemini ประมวลผลสำเร็จ!")
                return response.text
            elif response.text:
                print("Gemini ตอบกลับแต่รูปแบบไม่สมบูรณ์ กำลังลองใหม่...")
        except Exception as e:
            err_msg = str(e)
            print(f"ข้อผิดพลาดจาก Gemini: {err_msg}")
            
        wait_time = (attempt + 1) * 3
        print(f"รอ {wait_time} วินาที ก่อนลองใหม่...")
        time.sleep(wait_time)
                
    print("Gemini API ไม่พร้อมใช้งาน สลับไปใช้ Fallback Extractor...")
    return None

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
        text_content, html_content = get_tfex_data_via_playwright()
        if text_content:
            summary = summarize_with_gemini(text_content)
            if not summary:
                summary = fallback_parse_content(text_content, html_content)
            
            send_line_message(summary)
            print("ทำงานสำเร็จ!")
        else:
            print("ไม่สามารถดึงข้อมูลจากหน้าเว็บได้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")

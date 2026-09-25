import os
import re
import time
import requests
from google import genai
from playwright.sync_api import sync_playwright

def get_tfex_data_via_playwright():
    """เปิดหน้าเว็บ Settrade ผ่าน Playwright เพื่อดึงข้อความตาราง"""
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
            time.sleep(5)  # รอให้ข้อมูล Render ครบถ้วน
            
            text_content = page.locator("body").inner_text()
            browser.close()
            print("ดึงข้อมูลจากหน้าเว็บสำเร็จ!")
            return text_content
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการดึงหน้าเว็บ: {e}")
            browser.close()
            return None

def fallback_parse_content(text_content):
    """สกัดข้อมูลตารางกรณี Gemini API ไม่พร้อมใช้งาน พร้อมแสดงป้ายกำกับครบถ้วน"""
    print("สลับมาใช้ระบบ Fallback Regex Extractor...")
    
    symbols = list(dict.fromkeys(re.findall(r'S50[A-Z0-9]+', text_content)))
    lines = []
    
    for sym in symbols:
        match = re.search(re.escape(sym) + r'[\s\S]{1,150}', text_content)
        if match:
            raw_text = match.group(0).replace('\n', ' ')
            tokens = raw_text.split()
            # ค้นหาตัวเลขในแถวเพื่อจัดเรียง
            nums = [t for t in tokens if re.match(r'^[\+\-\d\.\,]+%?$', t)]
            if len(nums) >= 6:
                lines.append(
                    f"📌 **[{sym}]**\n"
                    f"• ราคาล่าสุด / ล่าสุด: {nums[0]}\n"
                    f"• เปลี่ยนแปลง: {nums[1]} ({nums[2] if len(nums)>2 else '-'})\n"
                    f"• ราคาเปิด: {nums[3] if len(nums)>3 else '-'}\n"
                    f"• ราคาสูงสุด: {nums[4] if len(nums)>4 else '-'}\n"
                    f"• ราคาต่ำสุด: {nums[5] if len(nums)>5 else '-'}\n"
                    f"• ราคาปิด (Prior/Settlement): {nums[0]}\n"
                    f"• ปริมาณซื้อขาย: {nums[-2] if len(nums)>6 else '-'} สัญญา\n"
                    f"• สถานะคงค้าง (OI): {nums[-1] if len(nums)>7 else '-'} สัญญา"
                )

    if lines:
        return "\n\n".join(lines)

    return "ระบบไม่สามารถจัดรูปแบบตารางได้ กรุณาตรวจสอบหน้าเว็บ Settrade อีกครั้ง"

def summarize_with_gemini(raw_text):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    จากข้อความหน้าเว็บ Settrade TFEX ด้านล่างนี้ ให้สกัดและคำนวณ/หาข้อมูลของ SET50 Futures ทุก Series ทั้งหมดที่มี (เช่น S50U26, S50Z26, S50H27 ฯลฯ)
    ต้องแสดงค่าตัวเลขให้ครบถ้วนทุกหัวข้อ หากค่าใดไม่มีในตาราง ให้คำนวณจากข้อมูลที่มี หรือระบุราคาชำระราคา/ราคาปิดก่อนหน้า (Settlement Price) แทน
    
    จัดรูปแบบสรุปเป็นข้อความสำหรับส่งเข้า LINE ดังนี้:

    📌 **[ชื่อย่อสัญญา]**
    • ราคาเปิด: 
    • ราคาสูงสุด: 
    • ราคาต่ำสุด: 
    • ราคาปิด / ราคาล่าสุด: 
    • ราคาเฉลี่ย: (หากไม่มีในตารางให้ใช้คำนวณจาก (สูง+ต่ำ)/2 หรือใส่ราคาเฉลี่ยการซื้อขาย)
    • ปริมาณซื้อขาย: (สัญญา)
    • สถานะคงค้าง (OI): (สัญญา)

    พร้อมสรุปผลรวม ปริมาณการซื้อขายรวม และ สถานะคงค้างรวม ทั้งหมดท้ายข้อความด้วย

    ข้อมูลจากหน้าเว็บ:
    {raw_text[:15000]}
    """
    
    max_retries = 3
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
        except Exception as e:
            print(f"ข้อผิดพลาดจาก Gemini: {e}")
            
        time.sleep(3)
                
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
        text_content = get_tfex_data_via_playwright()
        if text_content:
            summary = summarize_with_gemini(text_content)
            if not summary:
                summary = fallback_parse_content(text_content)
            
            send_line_message(summary)
            print("ทำงานสำเร็จ!")
        else:
            print("ไม่สามารถดึงข้อมูลจากหน้าเว็บได้")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการทำงาน: {e}")

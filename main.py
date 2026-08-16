import os
import json
import requests
import base64
import io
import textwrap
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont

# --- 1. CONFIGURATION ---
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
IMG_BB_KEY = os.getenv("IMG_BB_KEY")
PINTEREST_TOKEN = os.getenv("PINTEREST_TOKEN")
DESTINATION_LINK = "https://t.co/P9xneAMW1k"

genai.configure(api_key=GEMINI_API_KEY)

# --- 2. HELPER FUNCTIONS ---

def generate_pins_with_ai(keyword):
    """Uses Free Gemini API to generate 3 highly SEO-optimized pin variations"""
    prompt = f"""
    Act as an expert Pinterest SEO Manager. 
    I need 3 highly engaging, viral Pinterest pins for the trending keyword: "{keyword}".
    
    SEO RULES:
    1. The exact keyword "{keyword}" MUST appear in the Title.
    2. The exact keyword "{keyword}" MUST appear in the first 20 words of the Description.
    3. Add 3-5 highly relevant hashtags at the end of the description.
    4. The "image_text" must be a punchy, 2-4 word version of the keyword that looks good on an image.
    
    Return ONLY a valid JSON array of objects. No markdown formatting like ```json.
    Each object must have: "title" (max 60 chars), "description" (max 300 chars), "image_text" (max 4 words).
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        text = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(text)
    except Exception as e:
        print(f"Error generating AI content for {keyword}: {e}")
        return []

def get_or_create_board(board_name):
    """Checks if a board exists, creates it if it doesn't, returns Board ID"""
    headers = {"Authorization": f"Bearer {PINTEREST_TOKEN}"}
    
    try:
        res = requests.get("https://api.pinterest.com/v5/boards", headers=headers)
        if res.status_code == 200:
            boards = res.json().get('items', [])
            for board in boards:
                if board['name'].lower() == board_name.lower():
                    return board['id']
    except Exception as e:
        print(f"Error fetching boards: {e}")

    print(f"Creating new board: {board_name}")
    payload = {"name": board_name, "description": f"Trending ideas and inspiration for {board_name}."}
    try:
        res = requests.post("https://api.pinterest.com/v5/boards", headers=headers, json=payload)
        if res.status_code == 201:
            return res.json()['id']
        else:
            print(f"Failed to create board: {res.status_code} - {res.text}")
            return None
    except Exception as e:
        print(f"Error creating board: {e}")
        return None

def create_pin_image(image_text, keyword):
    """Creates a 1000x1500 Pinterest image with SEO text"""
    # Aesthetic gradient-like background using solid colors
    img = Image.new('RGB', (1000, 1500), color=(250, 245, 235)) 
    draw = ImageDraw.Draw(img)
    
    font = ImageFont.load_default()

    # Draw Main Image Text (Big & Bold)
    lines = textwrap.wrap(image_text.upper(), width=10)
    y_text = 600
    for line in lines:
        draw.text((103, y_text + 3), line, font=font, fill=(210, 200, 190), align="center") # Shadow
        draw.text((100, y_text), line, font=font, fill=(40, 40, 40), align="center")
        y_text += 90

    # Draw Keyword at the bottom for extra SEO context visually
    draw.text((100, 1350), f"Trending: {keyword.title()}", font=font, fill=(120, 120, 120))

    img_byte_array = io.BytesIO()
    img.save(img_byte_array, format='PNG')
    img_byte_array.seek(0)
    return img_byte_array

def upload_to_imgbb(image_bytes):
    """Uploads image to free ImgBB API"""
    url = "https://api.imgbb.com/1/upload"
    payload = {
        "key": IMG_BB_KEY,
        "image": base64.b64encode(image_bytes.read()).decode('utf-8')
    }
    try:
        res = requests.post(url, data=payload)
        res.raise_for_status()
        return res.json()['data']['url']
    except Exception as e:
        print(f"Error uploading to ImgBB: {e}")
        return None

def post_to_pinterest(board_id, title, description, image_url):
    """Posts to Pinterest Official API with your affiliate link"""
    url = "https://api.pinterest.com/v5/pins"
    headers = {
        "Authorization": f"Bearer {PINTEREST_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "link": DESTINATION_LINK, 
        "media_source": {
            "source_type": "image_url",
            "url": image_url
        }
    }
    try:
        res = requests.post(url, headers=headers, json=data)
        if res.status_code == 201:
            return True
        else:
            print(f"Pinterest API Error: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"Error posting to Pinterest: {e}")
        return False

# --- 3. MAIN EXECUTION ---
def main():
    try:
        with open('trends.json', 'r') as f:
            trends = json.load(f)
    except FileNotFoundError:
        print("trends.json not found!")
        return

    # Find ALL pending trends (Since we run this once a week on Friday)
    pending_trends = [t for t in trends if t.get('status') == 'pending']
    
    if not pending_trends:
        print("✅ No pending trends this week! All done.")
        return

    print(f"🚀 Found {len(pending_trends)} pending trends to process...")

    for target_trend in pending_trends:
        keyword = target_trend['keyword']
        print(f"\n--- Processing: {keyword} ---")
        
        # 1. Get or Create Board
        board_id = get_or_create_board(keyword.title())
        if not board_id:
            print("Skipping due to board error.")
            continue

        # 2. Generate SEO Ideas
        pin_ideas = generate_pins_with_ai(keyword)
        if not pin_ideas:
            continue

        success_count = 0
        for idea in pin_ideas[:3]: # Post 3 pins per trend
            # 3. Create Image
            image_bytes = create_pin_image(idea.get('image_text', keyword), keyword)
            
            # 4. Host Image
            image_url = upload_to_imgbb(image_bytes)
            if not image_url:
                continue
                
            # 5. Post to Pinterest
            if post_to_pinterest(board_id, idea.get('title', keyword), idea.get('description', ''), image_url):
                print(f"✅ Posted: {idea.get('title')}")
                success_count += 1

        # If successful, mark as done so it doesn't run again next week
        if success_count > 0:
            target_trend['status'] = 'done'

    # Save database with updated statuses
    with open('trends.json', 'w') as f:
        json.dump(trends, f, indent=4)
    print("\nDatabase updated. See you next Friday!")

if __name__ == "__main__":
    main()

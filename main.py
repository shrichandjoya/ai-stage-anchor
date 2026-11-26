import os
import sys
import json
import time
import asyncio
import urllib.parse
import subprocess
import feedparser
import requests
import edge_tts
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")

MODE = sys.argv[1] if len(sys.argv) > 1 else "motivation"
BASE_VIDEO_MOTIVATION = "motivation.mp4"
HISTORY_FILE = "history.txt"
STATE_FILE = "tg_state.txt"

def get_history():
    if not os.path.exists(HISTORY_FILE):
        return ""
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return "".join(f.readlines()[-30:])

def save_history(topic_line):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(topic_line.strip() + "\n")

def check_telegram_topic():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None
    last_id = 0
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            val = f.read().strip()
            if val.isdigit():
                last_id = int(val)

    url = "https://api." + "telegram.org" + f"/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_id + 1}"
    try:
        res = requests.get(url, timeout=15).json()
        for item in res.get("result", []):
            upd_id = item["update_id"]
            with open(STATE_FILE, "w") as f:
                f.write(str(upd_id))
            msg = item.get("message", {})
            if str(msg.get("chat", {}).get("id")) == str(TELEGRAM_CHAT_ID):
                text = msg.get("text", "").strip()
                if text.startswith("/video"):
                    topic = text.replace("/video", "", 1).strip()
                    if topic:
                        return topic
                elif text and not text.startswith("/"):
                    return text
    except Exception as e:
        print("Telegram check error:", e)
    return None

def fetch_trending_news():
    rss_urls = [
    "https://news.google." + "com/rss?hl=hi&gl=IN&ceid=IN:hi",
    "https://news.google." + "com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFZxYUdjU0FtVnVHZ0pWVXlnQVAB?hl=en-IN&gl=IN:en"
    ]
    headlines = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                headlines.append(entry.title)
        except Exception:
            pass
    return "\n".join(headlines)
def generate_content_data(custom_topic=None):
    client = genai.Client(api_key=GEMINI_API_KEY)
    past_topics = get_history()

    if MODE == "motivation" and not custom_topic:
        prompt = f"""
        Ek viral 35-40 second ka Hindi/Hinglish motivational dialogue ya dil ko chhu lene wali shayari likho (YouTube Shorts aur Instagram Reels ke liye).
        Rules:
        1. Pehle 3 second mein ek strong hook ho.
        2. Ghise-pite quotes mat likho. Real-life struggle, silent mehnat, ya self-respect par deep baat likho.
        3. Aakhiri line ek punch ya sawal ho jisse log comment karein.
        4. Koi bracket ya emoji script ke andar mat likho, sirf bolne wale shabd likho (75-90 shabd).
        5. In purane topics ko repeat mat karna: {past_topics}

        Sirf valid JSON format mein jawab do:
        {{
            "topic_summary": "Chhota topic naam",
            "title": "Viral Hindi/Hinglish YouTube Shorts Title with #shorts",
            "description": "Short description aur 5 trending hashtags",
            "script": "Bolne wali poori script"
        }}
        """
    else:
        topic_instruction = f"Is khaas topic par video banao: '{custom_topic}'" if custom_topic else f"Niche di gayi trending news mein se sabse garam current topic chuno:\n{fetch_trending_news()}"
        prompt = f"""
        Tum ek top Hindi Documentary aur Current Affairs Shorts creator ho.
        {topic_instruction}

        Is topic ki poori backstory ke saath (kab shuru hua, kya bhumika rahi, aur ab aage kya) ek 35-45 second ki documentary script likho.
        Script ko 5 chhote scenes mein baanto. Har scene ke liye ek detailed English visual prompt do jisse us scene ki realistic documentary picture ban sake (vertical 9:16 style).

        Rules:
        1. Script balanced aur factual ho, bolne mein natural lage (total 80-95 shabd).
        2. Script mein koi bracket ya emoji mat daalna.
        3. Aakhiri scene mein audience se ek opinion sawal puchho.
        4. Purane topics repeat mat karna: {past_topics}

        Sirf valid JSON format mein jawab do:
        {{
            "topic_summary": "Chhota topic naam",
            "title": "Viral Hindi Documentary Shorts Title with #shorts",
            "description": "Short description aur 5 trending hashtags",
            "scenes": [
                {{"narration": "Scene 1 ki Hindi line", "image_prompt": "Detailed realistic cinematic photo prompt in English for scene 1"}},
                {{"narration": "Scene 2 ki Hindi line", "image_prompt": "Detailed realistic cinematic photo prompt in English for scene 2"}},
                {{"narration": "Scene 3 ki Hindi line", "image_prompt": "Detailed realistic cinematic photo prompt in English for scene 3"}},
                {{"narration": "Scene 4 ki Hindi line", "image_prompt": "Detailed realistic cinematic photo prompt in English for scene 4"}},
                {{"narration": "Scene 5 ki Hindi line", "image_prompt": "Detailed realistic cinematic photo prompt in English for scene 5"}}
            ]
        }}
        """

    raw_text = None
    available_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"]

    for model_name in available_models:
        for attempt in range(3):
            try:
                res = client.models.generate_content(model=model_name, contents=prompt)
                if res and res.text:
                    raw_text = res.text.strip()
                    break
            except Exception as e:
                print(f"Model {model_name} attempt {attempt+1} busy: {e}")
                time.sleep(5)
        if raw_text:
            break

    if not raw_text:
        print("Gemini busy, using Pollinations AI fallback...")
        try:
            fb = requests.post(
                "https://text." + "pollinations.ai/",
                json={"messages": [{"role": "user", "content": prompt}]},
                timeout=45
            )
            if fb.status_code == 200 and fb.text.strip():
                raw_text = fb.text.strip()
        except Exception as e:
            print("Pollinations fallback error:", e)

    if raw_text:
        start_idx = raw_text.find("{")
        end_idx = raw_text.rfind("}")
        if start_idx != -1 and end_idx != -1:
            try:
                return json.loads(raw_text[start_idx:end_idx + 1])
            except Exception as e:
                print("JSON parse error:", e)

    if MODE == "motivation" and not custom_topic:
        return {
            "topic_summary": "Silent Grind & Self Respect",
            "title": "खामोशी से मेहनत करो, शोर तुम्हारी कामयाबी मचाएगी 🔥 #shorts",
            "description": "Khamoshi se apni mehnat jaari rakho! #motivation #hindi #shorts #success #mindset",
            "script": "जब तुम अकेले मेहनत करते हो तो दुनिया हंसती है। लेकिन याद रखना, सबसे बड़ा बदला किसी से लड़ना नहीं बल्कि खुद को इतना कामयाब बनाना है कि लोग तुम्हारा वक्त मांगें। आज जो दर्द सह रहे हो, कल वही तुम्हारी सबसे बड़ी ताकत बनेगा। क्या तुम आज अपने सपनों के लिए लड़ने को तैयार हो?"
        }
    return {
        "topic_summary": "India Global Rise",
        "title": "दुनिया भर में क्यों बढ़ रही है भारत की ताकत? जानिए पूरा सच 🇮🇳 #shorts",
        "description": "Bharat ki badhti taqat ki poori kahani! #india #news #documentary #shorts #trending",
        "scenes": [
            {"narration": "आज पूरी दुनिया की नजरें भारत की तेजी से बढ़ती ताकत पर टिकी हैं।", "image_prompt": "Futuristic India skyline at sunrise dramatic documentary style"},
            {"narration": "पिछले कुछ सालों में तकनीक, स्पेस और अर्थव्यवस्था में भारत ने ऐतिहासिक छलांग लगाई है।", "image_prompt": "Indian space rocket launch dramatic cinematic lighting"},
            {"narration": "चाहे डिजिटल क्रांति हो या ग्लोबल डिप्लोमेसी, हर मंच पर भारत की आवाज मजबूत हुई है।", "image_prompt": "World leaders summit diplomatic meeting dramatic documentary"},
            {"narration": "आने वाले दशक में भारत दुनिया की तीसरी सबसे बड़ी अर्थव्यवस्था बनने की राह पर है।", "image_prompt": "Modern Indian metro city and financial hub night view"},
            {"narration": "आपके हिसाब से भारत की सबसे बड़ी ताकत क्या है? कमेंट में जरूर बताएं।", "image_prompt": "Indian national flag waving proudly in golden sunlight"}
        ]
    }

async def create_voiceover(script_text, output_audio):
    clean_text = script_text.replace("...", " — ").replace("।", "। ")
    communicate = edge_tts.Communicate(
        clean_text,
        voice="hi-IN-AnanyaNeural",
        rate="-5%",
        pitch="+2Hz"
    )
    await communicate.save(output_audio)

def get_duration(media_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", media_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return float(result.stdout)
def build_lipsync_video(script_text, final_output="final_short.mp4"):
    asyncio.run(create_voiceover(script_text, "voice.mp3"))
    duration = get_duration("voice.mp3")

    if not os.path.exists(BASE_VIDEO_MOTIVATION):
        raise FileNotFoundError(f"'{BASE_VIDEO_MOTIVATION}' repo mein nahi mili!")

    looped_vid = "looped_base.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", BASE_VIDEO_MOTIVATION,
        "-t", str(duration + 0.3), "-vf", "scale=720:1280,fps=25",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", looped_vid
    ], check=True)

    try:
        if not os.path.exists("Wav2Lip"):
            subprocess.run(["git", "clone", "https://github." + "com/Rudrabha/Wav2Lip.git"], check=True)
            os.makedirs("Wav2Lip/checkpoints", exist_ok=True)
            os.makedirs("Wav2Lip/face_detection/detection/sfd", exist_ok=True)
            subprocess.run([
                "wget", "-q",
                "https://" + "huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth",
                "-O", "Wav2Lip/checkpoints/wav2lip_gan.pth"
            ], check=True)
            subprocess.run([
                "wget", "-q",
                "https://www.adrianbulat." + "com/downloads/python-fan/s3fd-619a316812.pth",
                "-O", "Wav2Lip/face_detection/detection/sfd/s3fd.pth"
            ], check=True)

        subprocess.run(["ffmpeg", "-y", "-i", "voice.mp3", "-ar", "16000", "-ac", "1", "voice.wav"], check=True)
        subprocess.run([
            "python", "Wav2Lip/inference.py",
            "--checkpoint_path", "Wav2Lip/checkpoints/wav2lip_gan.pth",
            "--face", looped_vid,
            "--audio", "voice.wav",
            "--pads", "0", "15", "0", "0",
            "--nosmooth",
            "--outfile", final_output
        ], check=True)

        if os.path.exists(final_output):
            print("Real Lip-Sync Video Generated!")
            return final_output
    except Exception as e:
        print("Local Wav2Lip error:", e)

    subprocess.run([
        "ffmpeg", "-y", "-i", looped_vid, "-i", "voice.mp3",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", final_output
    ], check=True)
    return final_output

def download_scene_image(prompt, img_path):
    encoded = urllib.parse.quote(f"{prompt}, photorealistic documentary style, dramatic lighting, 8k, no text")
    url = "https://image." + "pollinations.ai/prompt/" + f"{encoded}?width=720&height=1280&nologo=true"
    for _ in range(3):
        try:
            res = requests.get(url, timeout=45)
            if res.status_code == 200 and len(res.content) > 5000:
                with open(img_path, "wb") as f:
                    f.write(res.content)
                return True
        except Exception:
            pass
    return False

def build_documentary_video(scenes, final_output="final_short.mp4"):
    clip_files = []
    for idx, scene in enumerate(scenes):
        audio_file, img_file, clip_file = f"scene_{idx}.mp3", f"scene_{idx}.jpg", f"clip_{idx}.mp4"
        asyncio.run(create_voiceover(scene["narration"], audio_file))
        dur = get_duration(audio_file)

        if not download_scene_image(scene["image_prompt"], img_file):
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x111827:s=720x1280:d=1", "-frames:v", "1", img_file], check=True)

        frames = int((dur + 0.2) * 25)
        zoom_filter = f"scale=1440:2560,zoompan=z='min(zoom+0.0015,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=720x1280,fps=25"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", img_file, "-i", audio_file,
            "-vf", zoom_filter, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip_file
        ], check=True)
        clip_files.append(clip_file)

    with open("concat_list.txt", "w") as f:
        for cf in clip_files:
            f.write(f"file '{cf}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c:v", "libx264", "-c:a", "aac", final_output], check=True)
    return final_output

def upload_to_youtube(video_file, title, description, is_doc=False):
    if not YOUTUBE_TOKEN_JSON:
        return None
    try:
        token_data = json.loads(YOUTUBE_TOKEN_JSON)
        if "client_id" not in token_data or "client_secret" not in token_data:
            print("Skipping YouTube upload: client_id/client_secret missing in token.")
            return None
        creds = Credentials.from_authorized_user_info(token_data)
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {
                "title": title[:99],
                "description": description,
                "tags": ["shorts", "hindi", "news", "documentary", "motivation", "india"],
                "categoryId": "25" if is_doc else "22"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        }
        media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype="video/mp4")
        response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        return "https://www.youtube." + f"com/shorts/{response.get('id')}"
    except Exception as e:
        print("YouTube upload skipped due to error:", e)
        return None

def send_to_telegram(video_file, title, yt_link):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    clean_token = TELEGRAM_BOT_TOKEN.strip()
    clean_chat_id = TELEGRAM_CHAT_ID.strip()
    caption = f"🎬 New Video Ready!\n\nTitle: {title}\nYouTube: {yt_link or 'Ready for Reels'}"
    url = "https://api." + "telegram.org" + "/bot" + clean_token + "/sendVideo"
    with open(video_file, "rb") as vf:
        res = requests.post(url, data={"chat_id": clean_chat_id, "caption": caption}, files={"video": vf})
        print("Telegram response:", res.status_code, res.text)

if __name__ == "__main__":
    custom_topic = None
    if MODE == "telegram_check":
        custom_topic = check_telegram_topic()
        if not custom_topic:
            print("No new Telegram topic found. Staying alive!")
            sys.exit(0)
        requests.post("https://api." + "telegram.org/bot" + f"{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": f"⏳ Topic mil gaya: '{custom_topic}'\nVideo ban rahi hai..."})
    is_documentary = (MODE != "motivation") or (custom_topic is not None)
    data = generate_content_data(custom_topic)
    final_vid = build_documentary_video(data["scenes"]) if is_documentary else build_lipsync_video(data["script"])
    yt_url = upload_to_youtube(final_vid, data["title"], data["description"], is_documentary)
    send_to_telegram(final_vid, data["title"], yt_url)
    save_history(f"[{'TG' if custom_topic else MODE}] {data['topic_summary']}")

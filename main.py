import os
import sys
import json
import asyncio
import urllib.parse
import subprocess
import feedparser
import requests
import edge_tts
from google import genai
from gradio_client import Client, handle_file
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN")
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

    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_id + 1}"
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
        "https://google.com",
        "https://google.com"
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

    response = None
    for model_name in ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-2.0-flash"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                break
            except Exception as e:
                print(f"Model {model_name} attempt {attempt+1} busy: {e}")
                import time
                time.sleep(5)
        if response:
            break
    if not response:
        raise RuntimeError("All Gemini models are currently busy, will retry on next schedule.")

    raw_text = response.text.strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:-3].strip()
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:-3].strip()
    return json.loads(raw_text)

async def create_voiceover(script_text, output_audio):
    communicate = edge_tts.Communicate(script_text, "hi-IN-SwaraNeural", rate="+2%")
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
        "-t", str(duration + 0.5), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", looped_vid
    ], check=True)

    spaces = ["TMElyralab/MuseTalk", "fffiloni/SadTalker", "camenduru/Wav2Lip"]
    for space in spaces:
        try:
            client = Client(space, token=HF_TOKEN if HF_TOKEN else None)
            if "MuseTalk" in space:
                result = client.predict(audio_path=handle_file("voice.mp3"), video_path=handle_file(looped_vid), bbox_shift=0, api_name="/inference")
            else:
                result = client.predict(handle_file(looped_vid), handle_file("voice.mp3"), api_name="/predict")

            synced_file = result[0] if isinstance(result, (list, tuple)) else result
            if isinstance(synced_file, dict) and "video" in synced_file:
                synced_file = synced_file["video"]

            subprocess.run([
                "ffmpeg", "-y", "-i", synced_file, "-i", "voice.mp3",
                "-c:v", "libx264", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0", "-shortest", final_output
            ], check=True)
            return final_output
        except Exception as e:
            print(f"Server {space} failed: {e}")

    subprocess.run(["ffmpeg", "-y", "-i", looped_vid, "-i", "voice.mp3", "-c:v", "libx264", "-c:a", "aac", "-shortest", final_output], check=True)
    return final_output

def download_scene_image(prompt, img_path):
    encoded = urllib.parse.quote(f"{prompt}, photorealistic documentary style, dramatic lighting, 8k, no text")
    url = f"https://pollinations.ai{encoded}?width=720&height=1280&nologo=true"
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
        creds = Credentials.from_authorized_user_info(json.loads(YOUTUBE_TOKEN_JSON))
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
        return f"https://youtube.com{response.get('id')}"
    except Exception as e:
        print("YouTube upload skipped/error:", e)
        return None

def send_to_telegram(video_file, title, yt_link):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    caption = f"🎬 *New Video Ready!*\n\n*Title:* {title}\n*YouTube:* {yt_link or 'Uploaded'}"
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open(video_file, "rb") as vf:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}, files={"video": vf})

if __name__ == "__main__":
    custom_topic = None
    if MODE == "telegram_check":
        custom_topic = check_telegram_topic()
        if not custom_topic:
            print("No new Telegram topic found. Staying alive!")
            sys.exit(0)
        requests.post(f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": f"⏳ Topic mil gaya: '{custom_topic}'\nVideo ban rahi hai..."})

    is_documentary = (MODE != "motivation") or (custom_topic is not None)
    data = generate_content_data(custom_topic)
    final_vid = build_documentary_video(data["scenes"]) if is_documentary else build_lipsync_video(data["script"])
    yt_url = upload_to_youtube(final_vid, data["title"], data["description"], is_documentary)
    send_to_telegram(final_vid, data["title"], yt_url)
    save_history(f"[{'TG' if custom_topic else MODE}] {data['topic_summary']}")

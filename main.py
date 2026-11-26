import os
import sys
import json
import time
import urllib.parse
import subprocess
import feedparser
import requests
import soundfile as sf
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")

MODE = sys.argv if len(sys.argv) > 1 else "motivation"
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
        topic_instruction = "Ek viral 35 second ka Hindi motivational dialogue ya dil ko chhu lene wali shayari likho. Har scene ke liye visual prompt mein ek confident Indian young woman stage par mic ke saamne bolti hui (vertical 9:16) dikhao."
    elif custom_topic:
        topic_instruction = f"Is khaas topic par poori backstory ke saath 35-40 second ki documentary script likho: '{custom_topic}'"
    else:
        topic_instruction = f"Niche di gayi trending news mein se sabse garam current topic (rajniti, desh-duniya, sports) chuno aur poori backstory ke saath 35-40 second ki script likho:\n{fetch_trending_news()}"

    prompt = f"""
    Tum ek top Hindi YouTube Shorts creator ho.
    {topic_instruction}

    Script ko 5 chhote scenes mein baanto (total 75-85 Hindi shabd). Har scene ke liye ek detailed English video prompt do (vertical 9:16 realistic style).
    Rules:
    1. Script bolne mein bilkul natural aur emotional lage, koi bracket ya emoji mat daalna.
    2. Aakhiri scene mein audience se ek sawal puchho.
    3. Purane topics repeat mat karna: {past_topics}

    Sirf valid JSON format mein jawab do:
    {{
        "topic_summary": "Chhota topic naam",
        "title": "Viral Hindi YouTube Shorts Title with #shorts",
        "description": "Short description aur 5 trending hashtags",
        "scenes": [
            {{"narration": "Scene 1 Hindi line", "video_prompt": "English realistic video prompt for scene 1"}},
            {{"narration": "Scene 2 Hindi line", "video_prompt": "English realistic video prompt for scene 2"}},
            {{"narration": "Scene 3 Hindi line", "video_prompt": "English realistic video prompt for scene 3"}},
            {{"narration": "Scene 4 Hindi line", "video_prompt": "English realistic video prompt for scene 4"}},
            {{"narration": "Scene 5 Hindi line", "video_prompt": "English realistic video prompt for scene 5"}}
        ]
    }}
    """

    raw_text = None
    for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"]:
        for _ in range(2):
            try:
                res = client.models.generate_content(model=model_name, contents=prompt)
                if res and res.text:
                    raw_text = res.text.strip()
                    break
            except Exception as e:
                print(f"Model {model_name} busy: {e}")
                time.sleep(3)
        if raw_text:
            break

    if not raw_text:
        try:
            fb = requests.post("https://text." + "pollinations.ai/", json={"messages": [{"role": "user", "content": prompt}]}, timeout=45)
            if fb.status_code == 200:
                raw_text = fb.text.strip()
        except Exception:
            pass

    if raw_text:
        s_idx, e_idx = raw_text.find("{"), raw_text.rfind("}")
        if s_idx != -1 and e_idx != -1:
            try:
                return json.loads(raw_text[s_idx:e_idx + 1])
            except Exception:
                pass

    return {
        "topic_summary": "Silent Grind & Success",
        "title": "खामोशी से मेहनत करो, शोर तुम्हारी कामयाबी मचाएगी 🔥 #shorts",
        "description": "Apne sapno ke liye khamoshi se mehnat karo! #motivation #hindi #shorts #success",
        "scenes": [
            {"narration": "जब तुम अकेले मेहनत करते हो तो दुनिया तुम पर हंसती है।", "video_prompt": "Confident Indian young woman speaking passionately on a modern stage with warm spotlight"},
            {"narration": "हर रात की खामोश मेहनत एक दिन तुम्हारी पहचान बन जाती है।", "video_prompt": "Close up of young Indian woman on stage gesturing naturally while speaking"},
            {"narration": "याद रखना सबसे बड़ा बदला किसी से लड़ना नहीं होता।", "video_prompt": "Indian female speaker on stage with blurred audience lights in background"},
            {"narration": "बल्कि खुद को इतना कामयाब बनाना है कि लोग तुम्हारा वक्त मांगें।", "video_prompt": "Inspiring young Indian woman smiling confidently on stage"},
            {"narration": "क्या तुम आज अपने सपनों के लिए लड़ने को तैयार हो?", "video_prompt": "Dramatic stage lighting on young Indian female motivational speaker"}
        ]
    }

def create_real_girl_voice(text, output_mp3):
    try:
        from kokoro_onnx import Kokoro
        if not os.path.exists("kokoro-v1.0.onnx"):
            subprocess.run(["wget", "-q", "https://github." + "com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"], check=True)
            subprocess.run(["wget", "-q", "https://github." + "com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"], check=True)
        kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
        samples, sample_rate = kokoro.create(text, voice="hf_alpha", speed=0.95, lang="hi")
        sf.write("temp_kokoro.wav", samples, sample_rate)
        subprocess.run(["ffmpeg", "-y", "-i", "temp_kokoro.wav", "-ar", "44100", output_mp3], check=True)
        if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
            print("Kokoro Real Indian Female Voice generated!")
            return
    except Exception as e:
        print("Kokoro fallback to gTTS:", e)

    from gtts import gTTS
    tts = gTTS(text=text, lang="hi", tld="co.in", slow=False)
    tts.save("temp_gtts.mp3")
    subprocess.run(["ffmpeg", "-y", "-i", "temp_gtts.mp3", "-af", "asetrate=24000*1.03,aresample=24000,atempo=0.98", output_mp3], check=True)

def get_duration(media_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", media_path]
    return float(subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout)
def fetch_ai_video_clip(prompt, out_mp4):
    encoded = urllib.parse.quote(f"{prompt}, realistic 4k vertical video, cinematic lighting, smooth motion")
    # Free AI Video endpoint with automatic AI Image + Zoom fallback
    vid_url = "https://video." + "pollinations.ai/prompt/" + f"{encoded}?width=720&height=1280&nologo=true"
    try:
        res = requests.get(vid_url, timeout=60)
        if res.status_code == 200 and len(res.content) > 20000:
            with open(out_mp4, "wb") as f:
                f.write(res.content)
            return True
    except Exception as e:
        print("AI Video clip fallback to cinematic motion:", e)
    return False

def build_full_ai_video(scenes, final_output="final_short.mp4"):
    clip_files = []
    for idx, scene in enumerate(scenes):
        audio_f, raw_vid_f, img_f, clip_f = f"s_{idx}.mp3", f"raw_{idx}.mp4", f"img_{idx}.jpg", f"clip_{idx}.mp4"
        create_real_girl_voice(scene["narration"], audio_f)
        dur = get_duration(audio_f)

        if fetch_ai_video_clip(scene["video_prompt"], raw_vid_f):
            subprocess.run([
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", raw_vid_f, "-i", audio_f,
                "-t", str(dur), "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=25",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip_f
            ], check=True)
        else:
            img_url = "https://image." + "pollinations.ai/prompt/" + urllib.parse.quote(f"{scene['video_prompt']}, photorealistic 8k vertical") + "?width=720&height=1280&nologo=true"
            r = requests.get(img_url, timeout=45)
            with open(img_f, "wb") as f:
                f.write(r.content)
            frames = int((dur + 0.2) * 25)
            zoom_filter = f"scale=1440:2560,zoompan=z='min(zoom+0.0015,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=720x1280,fps=25"
            subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", img_f, "-i", audio_f,
                "-vf", zoom_filter, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip_f
            ], check=True)
        clip_files.append(clip_f)

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
            return None
        creds = Credentials.from_authorized_user_info(token_data)
        youtube = build("youtube", "v3", credentials=creds)
        body = {
            "snippet": {
                "title": title[:99],
                "description": description,
                "tags": ["shorts", "hindi", "news", "motivation", "india"],
                "categoryId": "25" if is_doc else "22"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        }
        media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype="video/mp4")
        response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        return "https://www.youtube." + f"com/shorts/{response.get('id')}"
    except Exception as e:
        print("YouTube upload skipped:", e)
        return None

def send_to_telegram(video_file, title, yt_link):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    clean_token = TELEGRAM_BOT_TOKEN.strip()
    clean_chat_id = TELEGRAM_CHAT_ID.strip()
    caption = f"🎬 New AI Video Ready!\n\nTitle: {title}\nYouTube: {yt_link or 'Ready for Reels'}"
    url = "https://api." + "telegram.org" + "/bot" + clean_token + "/sendVideo"
    with open(video_file, "rb") as vf:
        requests.post(url, data={"chat_id": clean_chat_id, "caption": caption}, files={"video": vf})

if __name__ == "__main__":
    custom_topic = None
    if MODE == "telegram_check":
        custom_topic = check_telegram_topic()
        if not custom_topic:
            print("No new Telegram topic. Alive!")
            sys.exit(0)
        requests.post("https://api." + "telegram.org/bot" + f"{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": f"⏳ Topic mil gaya: '{custom_topic}'\nVideo ban rahi hai..."})

    is_doc = (MODE != "motivation") or (custom_topic is not None)
    data = generate_content_data(custom_topic)
    final_vid = build_full_ai_video(data["scenes"], "final_short.mp4")
    yt_url = upload_to_youtube(final_vid, data["title"], data["description"], is_doc)
    send_to_telegram(final_vid, data["title"], yt_url)
    save_history(f"[{'TG' if custom_topic else MODE}] {data['topic_summary']}")

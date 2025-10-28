import streamlit as st
from google import genai
import base64, json, requests
import streamlit.components.v1 as components

# ===============================
# 設定
# ===============================
SYSTEM_PROMPT = """
あなたは教育的な目的を持つAIアシスタントです。
ユーザーの質問に対して3つのルールに従って応答してください。
1️⃣ 知識・定義は直接答える。
2️⃣ 思考・計算問題は答えを教えず、解法のヒントのみ。
3️⃣ 途中式を見せられた場合は正誤を判定し、優しく導く。
"""
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"

API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# ===============================
# アバター
# ===============================
def show_avatar():
    try:
        img_close = base64.b64encode(open("yukki-close.jpg", "rb").read()).decode("utf-8")
        img_open = base64.b64encode(open("yukki-open.jpg", "rb").read()).decode("utf-8")
    except Exception:
        st.warning("⚠️ yukki-close.jpg / yukki-open.jpg が見つかりません。")
        return

    components.html(f"""
    <style>
      .avatar {{ width: 280px; height: 280px; border-radius: 16px; border: 2px solid #f0a; object-fit: contain; }}
    </style>
    <div style="text-align:center;">
      <img id="avatar" src="data:image/jpeg;base64,{img_close}" class="avatar">
    </div>
    <script>
      let talkingInterval=null;
      function startTalking(){{
        const img=document.getElementById('avatar');
        let toggle=false;
        talkingInterval=setInterval(()=>{{
          img.src=toggle?"data:image/jpeg;base64,{img_open}":"data:image/jpeg;base64,{img_close}";
          toggle=!toggle;
        }},160);
      }}
      function stopTalking(){{
        clearInterval(talkingInterval);
        document.getElementById('avatar').src="data:image/jpeg;base64,{img_close}";
      }}
      window.startTalking=startTalking;
      window.stopTalking=stopTalking;
    </script>
    """, height=340)

# ===============================
# 音声生成＋再生
# ===============================
def play_tts(text):
    if not API_KEY:
        return
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}},
        "model": TTS_MODEL
    }
    res = requests.post(f"{TTS_API_URL}?key={API_KEY}",
                        headers={"Content-Type": "application/json"},
                        data=json.dumps(payload))
    data = res.json()
    try:
        audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        st.session_state.audio_to_play = audio_b64
    except Exception:
        st.error("TTS生成に失敗しました")
        st.json(data)

# ===============================
# ページ構成
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")
st.title("🎀 ユッキー（Vtuber風 AI アシスタント）")

show_avatar()

# ===============================
# 音声入力ボタン（安全方式）
# ===============================
st.subheader("🎙 音声入力")

components.html("""
<div>
  <button onclick="startRec()" style="padding:10px 20px;border:none;background:#ff69b4;color:white;border-radius:8px;">🎧 話す</button>
  <p id="mic-status">マイク停止中</p>
</div>
<script>
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang = 'ja-JP';
  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript;
    document.getElementById("mic-status").innerText = "✅ " + text;
    const params = new URLSearchParams(window.location.search);
    params.set("speech", text);
    window.location.search = params.toString();
  };
}
function startRec(){
  document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
  recognition.start();
}
</script>
""", height=130)

# ===============================
# クエリパラメータで音声入力を受け取る
# ===============================
query_params = st.experimental_get_query_params()
speech_text = query_params.get("speech", [""])[0]

# ===============================
# チャット
# ===============================
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY)
if "chat" not in st.session_state:
    config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    st.session_state.chat = st.session_state.client.chats.create(model="gemini-2.5-flash", config=config)
if "messages" not in st.session_state:
    st.session_state.messages = []

prompt = st.chat_input("質問を入力してください...", value=speech_text)

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ユッキーが考え中..."):
            resp = st.session_state.chat.send_message(prompt)
            text = resp.text
            st.markdown(text)
            play_tts(text)
            st.session_state.messages.append({"role": "assistant", "content": text})

# ===============================
# 音声再生＋口パク
# ===============================
if "audio_to_play" in st.session_state and st.session_state.audio_to_play:
    components.html(f"""
    <script>
      if(window.startTalking) window.startTalking();
      const audioData="{st.session_state.audio_to_play}";
      const audio = new Audio("data:audio/wav;base64,"+audioData);
      audio.onended=()=>{{ if(window.stopTalking) window.stopTalking(); }};
      audio.play();
    </script>
    """, height=0)
    st.session_state.audio_to_play = None

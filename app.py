import streamlit as st
from google import genai
import base64, json, time, requests
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
API_KEY = st.secrets["GEMINI_API_KEY"]

# ===============================
# アバター口パクHTML注入
# ===============================
def show_avatar():
    img_close = base64.b64encode(open("yukki-close.jpg", "rb").read()).decode("utf-8")
    img_open = base64.b64encode(open("yukki-open.jpg", "rb").read()).decode("utf-8")

    components.html(f"""
    <style>
    .avatar {{
        width: 280px;
        height: 280px;
        border-radius: 16px;
        border: 2px solid #f0a;
        object-fit: contain;
    }}
    </style>
    <div style="text-align:center;">
      <img id="avatar" src="data:image/png;base64,{img_close}" class="avatar">
    </div>

    <script>
    let talkingInterval = null;
    function startTalking() {{
        const avatar = document.getElementById('avatar');
        let toggle = false;
        if (talkingInterval) clearInterval(talkingInterval);
        talkingInterval = setInterval(() => {{
            avatar.src = toggle
              ? "data:image/png;base64,{img_open}"
              : "data:image/png;base64,{img_close}";
            toggle = !toggle;
        }}, 160); // ← パクパク速度（ms）
    }}
    function stopTalking() {{
        clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar');
        avatar.src = "data:image/png;base64,{img_close}";
    }}
    </script>
    """, height=340)

# ===============================
# 音声再生＋口パク制御
# ===============================
def play_tts_with_lip(text):
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}
        },
        "model": TTS_MODEL
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
    result = response.json()

    try:
        audio_data = result["contents"][0]["parts"][0]["inlineData"]["data"]
    except Exception as e:
        st.error("❌ 音声データ取得失敗")
        st.json(result)
        return

    audio_bytes = base64.b64decode(audio_data)

    # 🎬 JavaScript で口パク開始・停止
    components.html("""
    <script>
    if (window.startTalking) startTalking();
    setTimeout(() => { if (window.stopTalking) stopTalking(); }, 7000);
    </script>
    """, height=0)

    st.audio(audio_bytes, format="audio/wav")

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー（口パク対応）", layout="wide")
st.title("🎀 ユッキー（Vtuber風）")

show_avatar()

if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY)
if "chat" not in st.session_state:
    config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    st.session_state.chat = st.session_state.client.chats.create(model="gemini-2.5-flash", config=config)
if "messages" not in st.session_state:
    st.session_state.messages = []

# ===============================
# 音声認識ボタン（ブラウザ標準API）
# ===============================
components.html("""
<script>
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP';
    recognition.continuous = false;
    recognition.interimResults = false;

    function startRec() {
        document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
        recognition.start();
    }

    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        document.getElementById("mic-status").innerText = "✅ " + text;
        const chatInput = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (chatInput) {
            chatInput.value = text;
            chatInput.dispatchEvent(new Event('input', { bubbles: true }));
            const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
            chatInput.dispatchEvent(enterEvent);
        }
    };

    recognition.onerror = (e) => {
        document.getElementById("mic-status").innerText = "⚠️ " + e.error;
    };
} else {
    document.write("このブラウザは音声認識に対応していません。");
}
</script>
<button onclick="startRec()">🎙 話す</button>
<p id="mic-status">マイク停止中</p>
""", height=130)

# ===============================
# チャットUI
# ===============================
for msg in st.session_state.messages:
    avatar = "🧑" if msg["role"] == "user" else "yukki-close.jpg"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="yukki-close.jpg"):
        with st.spinner("ユッキーが考え中..."):
            response = st.session_state.chat.send_message(prompt)
            text = response.text
            st.markdown(text)
            play_tts_with_lip(text)
            st.session_state.messages.append({"role": "assistant", "content": text})

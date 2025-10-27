import streamlit as st
from google import genai
import base64, json, requests
import streamlit.components.v1 as components
import os

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
try:
    API_KEY = st.secrets["GEMINI_API_KEY"] 
except:
    API_KEY = ""

# ===============================
# アバター画像取得 (キャッシュ)
# ===============================
@st.cache_data
def get_avatar_images():
    base_names = ["yukki-close", "yukki-open"]
    extensions = [".jpg", ".jpeg"]
    loaded_images = {}
    data_uri_prefix = ""

    for base in base_names:
        for ext in extensions:
            file_name = base + ext
            try:
                with open(file_name, "rb") as f:
                    loaded_images[base] = base64.b64encode(f.read()).decode("utf-8")
                    data_uri_prefix = f"data:image/{'jpeg' if ext in ['.jpg', '.jpeg'] else 'png'};base64,"
                    break
            except FileNotFoundError:
                continue

    if "yukki-close" in loaded_images and "yukki-open" in loaded_images:
        return loaded_images["yukki-close"], loaded_images["yukki-open"], data_uri_prefix, True
    else:
        # サイドバーに警告を表示
        st.sidebar.warning("⚠️ アバター画像ファイルが見つかりません。")
        placeholder_svg = base64.b64encode(
            f"""<svg width="280" height="280" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="20" fill="#a00" font-family="sans-serif">❌画像なし</text></svg>""".encode('utf-8')
        ).decode("utf-8")
        return placeholder_svg, placeholder_svg, "data:image/svg+xml;base64,", False

# ===============================
# 音声再生＋口パク制御
# ===============================
def play_tts_with_lip(text):
    if not API_KEY:
        return
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"]},
        "model": TTS_MODEL
    }
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        result = response.json()
        audio_data_base64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except Exception as e:
        st.error(f"❌ 音声データ取得に失敗しました。詳細: {e}")
        return

    # st.sidebar にスクリプトを注入
    st.sidebar.markdown(f"""
    <script>
    if (window.startTalking) window.startTalking();
    const audio = new Audio('data:audio/wav;base64,{audio_data_base64}');
    audio.autoplay = true;
    audio.onended = () => {{ if (window.stopTalking) window.stopTalking(); }};
    audio.play().catch(e => {{
        console.error("Audio playback failed:", e);
        if (window.stopTalking) window.stopTalking(); 
    }});
    </script>
    """, unsafe_allow_html=True)

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")

# --- サイドバーにアバターと関連要素を配置 ---
with st.sidebar:
    img_close_base64, img_open_base64, data_uri_prefix, has_images = get_avatar_images()

    # アバターと口パク用のCSSとHTML
    st.markdown(f"""
    <style>
    /* サイドバーの中央にアバターを配置 */
    .st-emotion-cache-1y4p8pa {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
    }}
    .avatar {{
        width: 280px;
        height: 280px;
        border-radius: 16px;
        border: 2px solid #f0a;
        object-fit: cover;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }}
    </style>

    <img id="avatar" src="{data_uri_prefix}{img_close_base64}" class="avatar">

    <script>
    const imgCloseBase64 = "{data_uri_prefix}{img_close_base64}";
    const imgOpenBase64 = "{data_uri_prefix}{img_open_base64}";
    let talkingInterval = null;

    window.startTalking = function() {{
        const avatar = document.getElementById('avatar');
        if ({'true' if has_images else 'false'}) {{ 
            let toggle = false;
            if (talkingInterval) clearInterval(talkingInterval);
            talkingInterval = setInterval(() => {{
                avatar.src = toggle ? imgOpenBase64 : imgCloseBase64;
                toggle = !toggle;
            }}, 160);
        }}
    }}
    window.stopTalking = function() {{
        if (talkingInterval) clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar');
        if ({'true' if has_images else 'false'}) {{
            avatar.src = imgCloseBase64;
        }}
    }}
    </script>
    """, unsafe_allow_html=True)


# --- メインコンテンツ ---
st.title("🎀 ユッキー（Vtuber風AIアシスタント）")

# Geminiクライアントとチャットセッションの初期化
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None
if "chat" not in st.session_state:
    if st.session_state.client:
        config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
        st.session_state.chat = st.session_state.client.chats.create(model="gemini-2.5-flash", config=config)
    else:
        st.session_state.chat = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# 音声認識ボタン
st.subheader("音声入力")
components.html("""
<div id="mic-container">
    <button onclick="window.parent.startRec()">🎙 話す</button>
    <p id="mic-status">マイク停止中</p>
</div>
<script>
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP';
    recognition.continuous = false;
    window.parent.startRec = () => {
        document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
        recognition.start();
    };
    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        document.getElementById("mic-status").innerText = "✅ " + text;
        window.parent.postMessage({type: 'SET_CHAT_INPUT', text: text}, '*');
    };
    recognition.onerror = (e) => { document.getElementById("mic-status").innerText = "⚠️ エラー: " + e.error; };
    recognition.onend = () => { if (document.getElementById("mic-status").innerText.startsWith("🎧")) document.getElementById("mic-status").innerText = "マイク停止中"; }
} else {
    document.getElementById("mic-container").innerHTML = "このブラウザは音声認識に対応していません。";
}
</script>
""", height=130)

# チャットUI
st.subheader("ユッキーとの会話履歴")
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])

# --- チャット入力と処理 ---
if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    if st.session_state.chat:
        response = st.session_state.chat.send_message(prompt)
        text = response.text
        st.session_state.messages.append({"role": "assistant", "content": text})
        play_tts_with_lip(text)
    else:
        st.session_state.messages.append({"role": "assistant", "content": "APIキーが設定されていないため、お答えできません。"})
    st.rerun()

# --- 音声認識からチャット入力へテキストを転送するJavaScript ---
components.html("""
<script>
window.addEventListener('message', event => {
    if (event.data.type === 'SET_CHAT_INPUT') {
        const chatInput = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (chatInput) {
            chatInput.value = event.data.text;
            chatInput.dispatchEvent(new Event('input', { bubbles: true }));
            const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, keyCode: 13 });
            chatInput.dispatchEvent(enterEvent);
        }
    }
});
</script>
""", height=0)
import streamlit as st
from google import genai
import base64, json, requests
import streamlit.components.v1 as components
import os
import uuid

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
        st.sidebar.warning("⚠️ アバター画像ファイルが見つかりません。")
        placeholder_svg = base64.b64encode(
            f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="20" fill="#a00" font-family="sans-serif">❌画像なし</text></svg>""".encode('utf-8')
        ).decode("utf-8")
        return placeholder_svg, placeholder_svg, "data:image/svg+xml;base64,", False

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")

# --- セッションステートの初期化 ---
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
if "run_id" not in st.session_state:
    st.session_state.run_id = str(uuid.uuid4())


# --- サイドバーにアバターと口パク用JSを配置 ---
with st.sidebar:
    img_close_base64, img_open_base64, data_uri_prefix, has_images = get_avatar_images()

    st.markdown(f"""
    <style>
    section[data-testid="stSidebar"] {{
        width: 450px !important;
        background-color: #FFFFFF !important;
    }}
    .main {{
        background-color: #FFFFFF !important;
    }}
    .st-emotion-cache-1y4p8pa {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
    }}
    .avatar {{
        width: 400px;
        height: 400px;
        border-radius: 16px;
        object-fit: cover;
    }}
    </style>

    <img id="avatar" src="{data_uri_prefix}{img_close_base64}" class="avatar">

    <script>
    const imgCloseBase64 = "{data_uri_prefix}{img_close_base64}";
    const imgOpenBase64 = "{data_uri_prefix}{img_open_base64}";
    let talkingInterval = null;

    // グローバルスコープに関数を公開
    window.startTalking = function() {{
        const avatar = document.getElementById('avatar');
        if (!avatar || !{'true' if has_images else 'false'}) return;
        let toggle = false;
        if (talkingInterval) clearInterval(talkingInterval);
        talkingInterval = setInterval(() => {{
            avatar.src = toggle ? imgOpenBase64 : imgCloseBase64;
            toggle = !toggle;
        }}, 160);
    }}
    window.stopTalking = function() {{
        if (talkingInterval) clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar');
        if (avatar && {'true' if has_images else 'false'}) {{
            avatar.src = imgCloseBase64;
        }}
    }}
    </script>
    """, unsafe_allow_html=True)

# --- メインコンテンツ ---
st.title("🎀 ユッキー")

# 音声認識ボタン
st.subheader("音声入力")
components.html("""
<div id="mic-container">
    <button onclick="startRec()">🎙 話す</button>
    <p id="mic-status">マイク停止中</p>
</div>
<script>
function startRec() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        document.getElementById("mic-container").innerHTML = "このブラウザは音声認識に対応していません。";
        return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP';
    recognition.continuous = false;
    
    document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
    recognition.start();

    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        document.getElementById("mic-status").innerText = "✅ " + text;
        // Streamlitにテキストを送信
        window.parent.Streamlit.setComponentValue(text);
    };
    recognition.onerror = (e) => { document.getElementById("mic-status").innerText = "⚠️ エラー: " + e.error; };
    recognition.onend = () => { if (document.getElementById("mic-status").innerText.startsWith("🎧")) document.getElementById("mic-status").innerText = "マイク停止中"; }
}
</script>
""", height=130)

# チャットUIのコンテナ
st.subheader("ユッキーとの会話履歴")
chat_container = st.container()

# 過去のメッセージを表示
with chat_container:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
            st.markdown(msg["content"])

# --- 入力処理 ---
# 音声入力とテキスト入力を統合
prompt = st.chat_input("質問を入力してください...")
voice_prompt = components.get_component_value()

if voice_prompt:
    prompt = voice_prompt

if prompt:
    # ユーザーメッセージをUIに即時反映
    with chat_container:
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)
    
    st.session_state.messages.append({"role": "user", "content": prompt})

    # AI応答と音声再生
    if st.session_state.chat:
        response = st.session_state.chat.send_message(prompt)
        text = response.text
        st.session_state.messages.append({"role": "assistant", "content": text})

        # 音声データを取得
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"]},
            "model": TTS_MODEL
        }
        headers = {'Content-Type': 'application/json'}
        try:
            tts_response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            tts_response.raise_for_status()
            result = tts_response.json()
            audio_data_base64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]

            # JavaScriptでAIの応答と音声再生を処理
            components.html(f"""
            <script>
            (function() {{
                // 1. サイドバーの口パク開始
                const sidebarWindow = window.parent.document.querySelector('iframe[title="stSidebar"]').contentWindow;
                sidebarWindow.startTalking();

                // 2. 音声再生
                const audio = new Audio('data:audio/wav;base64,{audio_data_base64}');
                audio.autoplay = true;
                audio.onended = () => {{
                    sidebarWindow.stopTalking();
                }};
                audio.play().catch(e => {{
                    console.error("Audio playback failed:", e);
                    sidebarWindow.stopTalking();
                }});

                // 3. AIのチャットメッセージをUIに追加
                // この部分はStreamlitの再実行に任せるため、ここでは何もしない
            }})();
            </script>
            """, height=0)
            
            # 応答が完了したら一度だけ再実行してUIを確定させる
            st.rerun()

        except Exception as e:
            st.error(f"❌ 音声データ取得または再生に失敗しました。詳細: {e}")
            st.rerun()
    else:
        st.session_state.messages.append({"role": "assistant", "content": "APIキーが設定されていないため、お答えできません。"})
        st.rerun()
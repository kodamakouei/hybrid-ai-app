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
MAX_RETRIES = 5
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    API_KEY = ""

# -----------------------------------------------------
# --- 共通設定 ---
# -----------------------------------------------------

def generate_and_store_tts(text):
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
        st.session_state.audio_to_play = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except Exception as e:
        st.error(f"❌ 音声データ取得に失敗しました。詳細: {e}")

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
if st.session_state.audio_to_play:
    st.sidebar.markdown(f"""
    <script>
    if (window.startTalking) window.startTalking();
    const audio = new Audio('data:audio/wav;base64,{st.session_state.audio_to_play}');
    audio.autoplay = true;
    audio.onended = () => {{ if (window.stopTalking) window.stopTalking(); }};
    audio.play().catch(e => {{
        if (window.stopTalking) window.stopTalking();
    }});
    </script>
    """, unsafe_allow_html=True)
    st.session_state.audio_to_play = None

# --- サイドバーにアバターと関連要素を配置 ---
with st.sidebar:
    img_close_base64, img_open_base64, data_uri_prefix, has_images = get_avatar_images()
    st.markdown(f"""
    <style>
    section[data-testid="stSidebar"] {{ width: 450px !important; background-color: #FFFFFF !important; }}
    .main {{ background-color: #FFFFFF !important; }}
    .avatar {{ width: 400px; height: 400px; border-radius: 16px; object-fit: cover; display: block; margin: 0 auto; }}
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
            talkingInterval = setInterval(() => {{ avatar.src = toggle ? imgOpenBase64 : imgCloseBase64; toggle = !toggle; }}, 160);
        }}
    }}
    window.stopTalking = function() {{
        if (talkingInterval) clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar');
        if ({'true' if has_images else 'false'}) {{ avatar.src = imgCloseBase64; }}
    }}
    </script>
    """, unsafe_allow_html=True)

# -----------------------------------------------------
# --- 音声を自動再生するための関数 ---
# -----------------------------------------------------
@st.cache_data
def base64_to_audio_url(base64_data, sample_rate):
    js_code = f"""
    <script>
        function base64ToArrayBuffer(base64) {{
            const binary_string = window.atob(base64);
            const len = binary_string.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {{
                bytes[i] = binary_string.charCodeAt(i);
            }}
            return bytes.buffer;
        }}

        function pcmToWav(pcmData, sampleRate) {{
            const numChannels = 1;
            const bitsPerSample = 16;
            const bytesPerSample = bitsPerSample / 8;
            const blockAlign = numChannels * bytesPerSample;
            const byteRate = sampleRate * blockAlign;
            const dataSize = pcmData.byteLength;
            const buffer = new ArrayBuffer(44 + dataSize);
            const view = new DataView(buffer);
            let offset = 0;

            writeString(view, offset, 'RIFF'); offset += 4;
            view.setUint32(offset, 36 + dataSize, true); offset += 4;
            writeString(view, offset, 'WAVE'); offset += 4;
            writeString(view, offset, 'fmt '); offset += 4;
            view.setUint32(offset, 16, true); offset += 4;
            view.setUint16(offset, 1, true); offset += 2;
            view.setUint16(offset, numChannels, true); offset += 2;
            view.setUint32(offset, sampleRate, true); offset += 4;
            view.setUint32(offset, byteRate, true); offset += 4;
            view.setUint16(offset, blockAlign, true); offset += 2;
            view.setUint16(offset, bitsPerSample, true); offset += 2;
            writeString(view, offset, 'data'); offset += 4;
            view.setUint32(offset, dataSize, true); offset += 4;

            const pcm16 = new Int16Array(pcmData);
            for (let i = 0; i < pcm16.length; i++) {{
                view.setInt16(offset, pcm16[i], true);
                offset += 2;
            }}
            return new Blob([buffer], {{ type: 'audio/wav' }});
        }}

        function writeString(view, offset, string) {{
            for (let i = 0; i < string.length; i++) {{
                view.setUint8(offset + i, string.charCodeAt(i));
            }}
        }}

        const pcmData = base64ToArrayBuffer('{base64_data}');
        const wavBlob = pcmToWav(pcmData, {sample_rate});
        const audioUrl = URL.createObjectURL(wavBlob);
        const audio = new Audio(audioUrl);
        audio.play().catch(e => console.log("Audio autoplay failed:", e));
    </script>
    """
    components.html(js_code, height=0, width=0)

def generate_and_play_tts(text):
    """Gemini TTSで音声生成＋自動再生"""
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}},
        },
        "model": TTS_MODEL,
    }

    headers = {'Content-Type': 'application/json'}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            candidate = result.get('candidates', [{}])[0]
            part = candidate.get('content', {}).get('parts', [{}])[0]
            audio_data = part.get('inlineData', {})
            if audio_data and audio_data.get('data'):
                mime_type = audio_data.get('mimeType', 'audio/L16;rate=24000')
                try:
                    sample_rate = int(mime_type.split('rate=')[1])
                except IndexError:
                    sample_rate = 24000
                base64_to_audio_url(audio_data['data'], sample_rate)
                return True
            st.error("音声データを取得できませんでした。")
            return False
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            st.error(f"APIエラー: {e}")
            return False
        except Exception as e:
            st.error(f"予期せぬエラー: {e}")
            return False
    return False

# -----------------------------------------------------
# --- 音声入力UI（Web Speech API） ---
# -----------------------------------------------------
def speech_to_text_ui():
    """
    Web Speech APIによる音声入力ボタン。
    """
    st.markdown("### 🎙️ 音声で質問する")
    html_code = """
    <script>
    let recognizing = false;
    let recognition;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = 'ja-JP';
        recognition.interimResults = false;
        recognition.continuous = false;

        function startRecognition() {
            if (!recognizing) {
                recognizing = true;
                recognition.start();
                document.getElementById('mic-status').innerText = '🎧 聴き取り中...';
            } else {
                recognizing = false;
                recognition.stop();
                document.getElementById('mic-status').innerText = 'マイク停止中';
            }
        }

        recognition.onresult = function(event) {
            const transcript = event.results[0][0].transcript;
            const streamlitInput = window.parent.document.querySelector('input[data-testid="stChatInput"]');
            if (streamlitInput) {
                streamlitInput.value = transcript;
                const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
                streamlitInput.dispatchEvent(enterEvent);
            }
            document.getElementById('mic-status').innerText = '✅ 認識完了: ' + transcript;
        };

        recognition.onerror = function(event) {
            document.getElementById('mic-status').innerText = '⚠️ エラー: ' + event.error;
        };
    } else {
        document.getElementById('mic-status').innerText = 'このブラウザは音声認識をサポートしていません。';
    }
    </script>

    <button onclick="startRecognition()">🎤 話す / 停止</button>
    <p id="mic-status">マイク停止中</p>
    """
    components.html(html_code, height=120)

# --- メインコンテンツ ---
st.title("🎀 ユッキー")

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

# チャット履歴
st.subheader("ユッキーとの会話履歴")
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "yukki-icon.jpg"):
        st.markdown(msg["content"])

# --- チャット入力と処理 ---
if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    if st.session_state.chat:
        response = st.session_state.chat.send_message(prompt)
        text = response.text
        st.session_state.messages.append({"role": "assistant", "content": text})
        generate_and_store_tts(text)  # ここを変更
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
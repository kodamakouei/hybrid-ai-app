import streamlit as st
from google import genai
import base64, json, requests
import streamlit.components.v1 as components
import os
import time

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
SIDEBAR_FIXED_WIDTH = "450px"

# --- APIキーの読み込み ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except (KeyError, AttributeError):
    API_KEY = ""

# ===============================
# 音声データ生成とSession State保存（リトライロジック含む）
# ===============================
def generate_and_store_tts(text):
    """Gemini TTSで音声生成し、base64データをst.session_state.audio_to_playに保存する"""
    if not API_KEY:
        st.session_state.audio_to_play = None
        return
    
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
            audio_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            st.session_state.audio_to_play = audio_data
            return
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"API Error (HTTP {response.status_code}) or final attempt failed: {e}")
            break
        except Exception as e:
            print(f"Error generating TTS: {e}")
            break
    st.session_state.audio_to_play = None

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")

# --- グローバルCSSの適用 ---
st.markdown(f"""
<style>
header {{ visibility: hidden; }}
[data-testid="stSidebarContent"] > div:first-child {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
}}
[data-testid="stSidebarContent"] {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
    min-width: {SIDEBAR_FIXED_WIDTH} !important;
    max-width: {SIDEBAR_FIXED_WIDTH} !important;
}}
[data-testid="stSidebarCollapseButton"] {{
    display: none !important;
}}
</style>
""", unsafe_allow_html=True)

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
if "audio_to_play" not in st.session_state:
    st.session_state.audio_to_play = None

# --- サイドバーに動画アバターを配置 ---
with st.sidebar:
    video_file = "yukki-lipsync.mp4"  # 口パク動画ファイル名
    if os.path.exists(video_file):
        with open(video_file, "rb") as f:
            video_base64 = base64.b64encode(f.read()).decode("utf-8")
        video_tag = f"""
        <video id="yukki_video" width="400" height="400" style="border-radius:16px;display:block;margin:0 auto;" preload="auto">
            <source src="data:video/mp4;base64,{video_base64}" type="video/mp4">
            このブラウザは動画タグに対応していません。
        </video>
        """
    else:
        video_tag = "<div style='width:400px;height:400px;background:#eee;text-align:center;line-height:400px;'>動画ファイルがありません</div>"
    st.markdown(video_tag, unsafe_allow_html=True)

    # 音声再生と動画再生を同時に制御
    if st.session_state.audio_to_play and os.path.exists(video_file):
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
        function writeString(view, offset, string) {{
            for (let i = 0; i < string.length; i++) {{
                view.setUint8(offset + i, string.charCodeAt(i));
            }}
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

        const base64AudioData = '{st.session_state.audio_to_play}';
        const sampleRate = 24000;
        const pcmData = base64ToArrayBuffer(base64AudioData);
        const wavBlob = pcmToWav(pcmData, sampleRate);
        const audioUrl = URL.createObjectURL(wavBlob);

        const audio = new Audio(audioUrl);
        const video = document.getElementById('yukki_video');
        if (video) {{
            video.currentTime = 0;
            video.play();
        }}
        audio.autoplay = true;
        audio.onended = () => {{
            if (video) video.pause();
            URL.revokeObjectURL(audioUrl);
        }};
        audio.play().catch(e => {{
            if (video) video.pause();
            URL.revokeObjectURL(audioUrl);
        }});
        </script>
        """
        components.html(js_code, height=0, width=0)
        st.session_state.audio_to_play = None

# --- メインコンテンツ ---
st.title("🎀 ユッキー（Vtuber風AIアシスタント）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")

# 音声認識ボタンとチャット履歴の表示
st.subheader("音声入力")
components.html("""
<div id="mic-container" style="padding: 10px 0;">
    <button onclick="window.parent.startRec()"
            style="background-color: #ff69b4; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        🎙 話す
    </button>
    <p id="mic-status" style="margin-top: 10px;">マイク停止中</p>
</div>
<script>
function sendTextToStreamlit(text) {
    window.parent.postMessage({
        type: 'SET_CHAT_INPUT',
        text: text
    }, '*');
}
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP';
    recognition.continuous = false;
    recognition.interimResults = false;
    window.parent.startRec = () => {
        document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
        recognition.start();
    };
    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        document.getElementById("mic-status").innerText = "✅ " + text;
        sendTextToStreamlit(text);
    };
    recognition.onerror = (e) => {
        document.getElementById("mic-status").innerText = "⚠️ エラー: " + e.error;
    };
    recognition.onend = () => {
        if (document.getElementById("mic-status").innerText.startsWith("🎧")) {
            document.getElementById("mic-status").innerText = "マイク停止中";
        }
    };
} else {
    document.getElementById("mic-container").innerHTML = "このブラウザは音声認識に対応していません。";
}
</script>
""", height=130)

st.subheader("ユッキーとの会話履歴")
for msg in st.session_state.messages:
    avatar_icon = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])

# --- チャット入力と処理 ---
if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ユッキーが思考中..."):
            if st.session_state.chat:
                try:
                    response = st.session_state.chat.send_message(prompt)
                    text = response.text
                    st.markdown(text)
                    generate_and_store_tts(text)
                    st.session_state.messages.append({"role": "assistant", "content": text})
                except Exception as e:
                    error_msg = f"APIエラーが発生しました: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
            else:
                st.session_state.messages.append({"role": "assistant", "content": "APIキーが設定されていないため、お答えできません。"})
    st.rerun()

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
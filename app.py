import streamlit as st
from google import genai
import base64, json, requests
import streamlit.components.v1 as components
import os
import time
from PIL import Image
import io
import fitz  # PyMuPDF

# ===============================
# 設定
# ===============================
SYSTEM_PROMPT = """
あなたは教育的な目的を持つ AI アシスタントです。
ユーザーの質問に対して以下のルールに従ってできるだけかみ砕いてわかりやすく応答してく
ださい。
1⃣知識・定義直接答えます。
2⃣思考・計算問題答えは教えず、解法のヒントのみを示します。
3⃣途中式正誤を判定し、優しく導きます。
4⃣専門用語ステップごとに区切り、専門用語について知っているか確認します。知らなかっ
た場合は、小学生にもわかるように、図や擬音などの表現、例となる面白い文を積極的に使っ
てその場で説明します。
5⃣説明は砕けた会話口調でお願いします。
6⃣いきなりステップを全部出さないでください。「ここで、～～について知っていますか？」
のところでいったん表示するのをやめてください。
7⃣専門用語や途中の過程の分からない部分について説明されたときは、できるだけ詳しく説明
してください。だからと言ってその説明を聞いている人に読むのを飽きさせてしまうような説
明はやめてください。
"""
# --- 共通設定 ---
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
# アバター画像取得 (キャッシュ)
# ===============================
@st.cache_data
def get_avatar_image():
    base_name = "yukki-static"
    extensions = [".jpg", ".jpeg", ".png"]
    loaded_image = None
    data_uri_prefix = ""
    for ext in extensions:
        file_name = base_name + ext
        if os.path.exists(file_name):
            with open(file_name, "rb") as f:
                loaded_image = base64.b64encode(f.read()).decode("utf-8")
                data_uri_prefix = f"data:image/{'jpeg' if ext in ['.jpg', '.jpeg'] else 'png'};base64,"
                break
    if loaded_image:
        return loaded_image, data_uri_prefix, True
    else:
        placeholder_svg = base64.b64encode(
            f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-size="28" fill="#a00" font-family="sans-serif">❌画像なし</text><text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" font-size="20" fill="#a00" font-family="sans-serif">{base_name}.jpg/jpeg/png</text></svg>""".encode('utf-8')
        ).decode("utf-8")
        return placeholder_svg, "data:image/svg+xml;base64,", False

# ===============================
# 音声データ生成
# ===============================
def generate_and_store_tts(text):
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
            st.session_state.audio_to_play = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
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
[data-testid="stSidebarContent"] > div:first-child {{ width: {SIDEBAR_FIXED_WIDTH} !important; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; }}
.avatar {{ width: 400px; height: 400px; border-radius: 16px; object-fit: cover; margin: 0 auto; }}
[data-testid="stSidebarContent"] {{ width: {SIDEBAR_FIXED_WIDTH} !important; min-width: {SIDEBAR_FIXED_WIDTH} !important; max-width: {SIDEBAR_FIXED_WIDTH} !important; }}
[data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
section[data-testid="stSidebar"] {{ width: {SIDEBAR_FIXED_WIDTH} !important; min-width: {SIDEBAR_FIXED_WIDTH} !important; max-width: {SIDEBAR_FIXED_WIDTH} !important; background-color: #FFFFFF !important; }}
.main {{ background-color: #FFFFFF !important; }}
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
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None

# --- サイドバー ---
with st.sidebar:
    img_base64, data_uri_prefix, has_image = get_avatar_image()
    if not has_image:
        st.warning("⚠️ アバター画像(yukki-static.jpg/png)が見つかりません。")
    st.markdown(f'<img id="avatar" src="{data_uri_prefix}{img_base64}" class="avatar">', unsafe_allow_html=True)

# --- 音声再生 ---
if st.session_state.audio_to_play:
    js_code = f"""
    <script>
        function base64ToArrayBuffer(base64) {{ const binary_string = window.atob(base64); const len = binary_string.length; const bytes = new Uint8Array(len); for (let i = 0; i < len; i++) {{ bytes[i] = binary_string.charCodeAt(i); }} return bytes.buffer; }}
        function writeString(view, offset, string) {{ for (let i = 0; i < string.length; i++) {{ view.setUint8(offset + i, string.charCodeAt(i)); }} }}
        function pcmToWav(pcmData, sampleRate) {{ const numChannels = 1; const bitsPerSample = 16; const bytesPerSample = bitsPerSample / 8; const blockAlign = numChannels * bytesPerSample; const byteRate = sampleRate * blockAlign; const dataSize = pcmData.byteLength; const buffer = new ArrayBuffer(44 + dataSize); const view = new DataView(buffer); let offset = 0; writeString(view, offset, 'RIFF'); offset += 4; view.setUint32(offset, 36 + dataSize, true); offset += 4; writeString(view, offset, 'WAVE'); offset += 4; writeString(view, offset, 'fmt '); offset += 4; view.setUint32(offset, 16, true); offset += 4; view.setUint16(offset, 1, true); offset += 2; view.setUint16(offset, numChannels, true); offset += 2; view.setUint32(offset, sampleRate, true); offset += 4; view.setUint32(offset, byteRate, true); offset += 4; view.setUint16(offset, blockAlign, true); offset += 2; view.setUint16(offset, bitsPerSample, true); offset += 2; writeString(view, offset, 'data'); offset += 4; view.setUint32(offset, dataSize, true); offset += 4; const pcm16 = new Int16Array(pcmData); for (let i = 0; i < pcm16.length; i++) {{ view.setInt16(offset, pcm16[i], true); offset += 2; }} return new Blob([buffer], {{ type: 'audio/wav' }}); }}
        const base64AudioData = '{st.session_state.audio_to_play}'; const sampleRate = 24000; const pcmData = base64ToArrayBuffer(base64AudioData); const wavBlob = pcmToWav(pcmData, sampleRate); const audioUrl = URL.createObjectURL(wavBlob); const audio = new Audio(audioUrl); audio.autoplay = true; audio.onended = () => {{ URL.revokeObjectURL(audioUrl); }}; audio.play().catch(e => console.error("Audio playback failed:", e));
    </script>
    """
    components.html(js_code, height=0, width=0)
    st.session_state.audio_to_play = None

# --- メインコンテンツ ---
st.title("🎀 ユッキー（疑似教師）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")

# ファイルアップローダー
uploaded_file = st.file_uploader(
    "画像やPDFをアップロードして質問できます",
    type=['png', 'jpg', 'jpeg', 'pdf'],
    help="ここに画像やPDFファイルをドラッグ＆ドロップしてください。"
)
if uploaded_file:
    st.session_state.uploaded_file = uploaded_file

# ファイルプレビュー
if st.session_state.uploaded_file:
    file_type = st.session_state.uploaded_file.type
    if "pdf" in file_type:
        st.info(f"📄 PDF「{st.session_state.uploaded_file.name}」がアップロードされました。")
    else:
        st.image(st.session_state.uploaded_file, caption="アップロードされた画像", width=300)

# 音声認識ボタン
st.subheader("音声入力")
components.html("""
<div id="mic-container" style="padding: 10px 0;"><button onclick="window.parent.startRec()" style="background-color: #ff69b4; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">🎙 話す</button><p id="mic-status" style="margin-top: 10px;">マイク停止中</p></div>
<script>
function sendTextToStreamlit(text) { window.parent.postMessage({ type: 'SET_CHAT_INPUT', text: text }, '*'); }
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
    const recognition = new SpeechRecognition(); recognition.lang = 'ja-JP'; recognition.continuous = false; recognition.interimResults = false;
    window.parent.startRec = () => { document.getElementById("mic-status").innerText = "🎧 聴き取り中..."; recognition.start(); };
    recognition.onresult = (event) => { const text = event.results[0][0].transcript; document.getElementById("mic-status").innerText = "✅ " + text; sendTextToStreamlit(text); };
    recognition.onerror = (e) => { document.getElementById("mic-status").innerText = "⚠️ エラー: " + e.error; };
    recognition.onend = () => { if (document.getElementById("mic-status").innerText.startsWith("🎧")) { document.getElementById("mic-status").innerText = "マイク停止中"; } };
} else { document.getElementById("mic-container").innerHTML = "このブラウザは音声認識に対応していません。"; }
</script>
""", height=130)

# チャット履歴の表示
st.subheader("ユッキーとの会話履歴")
for msg in st.session_state.messages:
    avatar_icon = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])

# チャット入力とAI応答生成
if prompt := st.chat_input("質問を入力してください..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ユッキーが思考中..."):
            if st.session_state.chat:
                try:
                    content_parts = [prompt]
                    if st.session_state.uploaded_file:
                        file_bytes = st.session_state.uploaded_file.getvalue()
                        file_type = st.session_state.uploaded_file.type
                        if "pdf" in file_type:
                            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                            for page_num in range(len(pdf_doc)):
                                page = pdf_doc.load_page(page_num)
                                pix = page.get_pixmap()
                                img_bytes = pix.tobytes("png")
                                content_parts.append(Image.open(io.BytesIO(img_bytes)))
                        else:
                            content_parts.append(Image.open(io.BytesIO(file_bytes)))
                        
                        # ★★★ 使用後にファイルをセッションからクリア ★★★
                        st.session_state.uploaded_file = None

                    response = st.session_state.chat.send_message(content_parts)
                    text = response.text
                    st.markdown(text)
                    generate_and_store_tts(text)
                    st.session_state.messages.append({"role": "assistant", "content": text})

                except Exception as e:
                    error_msg = f"APIエラーが発生しました: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
            else:
                error_msg = "APIキーが設定されていないため、お答えできません。"
                st.warning(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    st.rerun()

# 音声認識からチャット入力への転送
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
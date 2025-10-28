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
# --- 共通設定 ---
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5
# ★お客様が指定したCSSに合わせて設定を調整
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
        # アバターがない場合のプレースホルダーSVG
        placeholder_svg = base64.b64encode(
            f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-size="28" fill="#a00" font-family="sans-serif">❌画像なし</text><text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" font-size="20" fill="#a00" font-family="sans-serif">yukki-close/open.jpg/jpeg</text></svg>""".encode('utf-8')
        ).decode("utf-8")
        return placeholder_svg, placeholder_svg, "data:image/svg+xml;base64,", False
 
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
            # 音声データをst.session_stateに保存
            st.session_state.audio_to_play = audio_data
            return
 
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            # 最終試行または他のエラー
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
 
# --- グローバルCSSの適用 (レイアウト崩れを防ぐため、最低限の調整のみ残す) ---
st.markdown(f"""
<style>
/* Streamlitのヘッダー/トップバーを非表示にする（任意） */
header {{ visibility: hidden; }}
 
/* ★★★ レイアウト変更CSSの削除 ★★★
.stApp に対する margin-left の設定を削除し、Streamlitのデフォルトレイアウトに依存させる。
*/
 
/* サイドバー内のアバターを中央に配置するためのCSS (お客様のコードを維持し、一部整理) */
[data-testid="stSidebarContent"] > div:first-child {{
    width: 450px !important;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
}}
.avatar {{
    width: 400px;
    height: 400px;
    border-radius: 16px;
    object-fit: cover;
    /* お客様が以前指定されたCSSを維持 */
    margin: 0 auto;
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
 
# --- サイドバーにアバターと関連要素を配置 ---
with st.sidebar:
    img_close_base64, img_open_base64, data_uri_prefix, has_images = get_avatar_images()
   
    # 画像がなければ警告を表示
    if not has_images:
        st.warning("⚠️ アバター画像ファイル（yukki-close.jpg/jpeg, yukki-open.jpg/jpeg）が見つかりません。")
 
    # お客様が提示されたサイドバーのレイアウトCSSとアバターを描画
    st.markdown(f"""
    <style>
    /* ★★★ お客様が「完璧」と指定されたCSSを再度ここに配置 ★★★ */
    section[data-testid="stSidebar"] {{
        width: 450px !important;
        min-width: {SIDEBAR_FIXED_WIDTH} !important;
        max-width: {SIDEBAR_FIXED_WIDTH} !important;
        background-color: #FFFFFF !important;
    }}
    .main {{ background-color: #FFFFFF !important; }}
    .st-emotion-cache-1y4p8pa {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
    }}
    .avatar {{ width: 400px; height: 400px; border-radius: 16px; object-fit: cover; }}
    </style>
    <img id="avatar" src="{data_uri_prefix}{img_close_base64}" class="avatar">
   
    <script>
    const imgCloseBase64 = "{data_uri_prefix}{img_close_base64}";
    const imgOpenBase64 = "{data_uri_prefix}{img_open_base64}";
    let talkingInterval = null;
   
    window.startTalking = function() {{
        const avatar = document.getElementById('avatar');
        if ({'true' if has_images else 'false'} && avatar) {{
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
        if ({'true' if has_images else 'false'} && avatar) {{
            avatar.src = imgCloseBase64;
        }}
    }}
    </script>
    """, unsafe_allow_html=True)
 
# --- 音声再生トリガーをサイドバーに追加（口パク制御とWAV変換ロジックを統合） ---
if st.session_state.audio_to_play:
    # WAV変換ヘルパー関数を定義したJavaScriptコードを挿入
    js_code = f"""
    <script>
        // --- PCM to WAV Utility Functions ---
        function base64ToArrayBuffer(base64) {{
            const binary_string = window.atob(base64);
            const len = binary_string.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {{ bytes[i] = binary_string.charCodeAt(i); }}
            return bytes.buffer;
        }}
        function writeString(view, offset, string) {{
            for (let i = 0; i < string.length; i++) {{ view.setUint8(offset + i, string.charCodeAt(i)); }}
        }}
        function pcmToWav(pcmData, sampleRate) {{
            const numChannels = 1; const bitsPerSample = 16;
            const bytesPerSample = bitsPerSample / 8; const blockAlign = numChannels * bytesPerSample;
            const byteRate = sampleRate * blockAlign; const dataSize = pcmData.byteLength;
            const buffer = new ArrayBuffer(44 + dataSize); const view = new DataView(buffer); let offset = 0;
 
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
            for (let i = 0; i < pcm16.length; i++) {{ view.setInt16(offset, pcm16[i], true); offset += 2; }}
            return new Blob([buffer], {{ type: 'audio/wav' }});
        }}
 
        // --- 再生ロジック ---
        const base64AudioData = '{st.session_state.audio_to_play}';
        const sampleRate = 24000; // Gemini TTSのデフォルトPCMレート
       
        if (window.startTalking) window.startTalking();
       
        const pcmData = base64ToArrayBuffer(base64AudioData);
        const wavBlob = pcmToWav(pcmData, sampleRate);
        const audioUrl = URL.createObjectURL(wavBlob);
       
        const audio = new Audio(audioUrl);
        audio.autoplay = true;
 
        audio.onended = () => {{ if (window.stopTalking) window.stopTalking(); }};
        audio.play().catch(e => {{
            console.error("Audio playback failed:", e);
            if (window.stopTalking) window.stopTalking();
        }});
    </script>
    """
    components.html(js_code, height=0, width=0)
    # 再生トリガー実行後、データをクリア
    st.session_state.audio_to_play = None
 
# --- メインコンテンツ ---
st.title("🎀 ユッキー")
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
// Streamlitのチャット入力欄にテキストを送信する関数
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
   
    // グローバルな認識開始関数 (Streamlit側から呼び出される)
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
    # 1. ユーザーメッセージを追加・表示
    st.session_state.messages.append({"role": "user", "content": prompt})
   
    # 2. アシスタントの応答を取得・表示
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ユッキーが思考中..."):
            if st.session_state.chat:
                try:
                    # Gemini API呼び出し
                    response = st.session_state.chat.send_message(prompt)
                    text = response.text
                   
                    # 応答テキストを表示
                    st.markdown(text)
                   
                    # 3. 音声データを生成してセッションステートに保存
                    generate_and_store_tts(text)
                   
                    # 4. メッセージを履歴に追加
                    st.session_state.messages.append({"role": "assistant", "content": text})
 
                except Exception as e:
                    error_msg = f"APIエラーが発生しました: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
            else:
                st.session_state.messages.append({"role": "assistant", "content": "APIキーが設定されていないため、お答えできません。"})
   
    # Rerunを実行し、UIを更新
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
 
 
 
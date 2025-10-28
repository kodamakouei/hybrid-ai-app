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
# 【画像が見つからない場合、エラーメッセージを返す】
# ===============================
@st.cache_data
def get_avatar_images():
    base_names = {"close": "yukki-close", "open": "yukki-open"}
    extensions = [".jpg", ".jpeg"]
    loaded_images = {}
    data_uri_prefix = ""
    error_message = "" # エラーメッセージ格納用

    for key, base in base_names.items():
        found = False
        for ext in extensions:
            file_name = base + ext
            try:
                # ユーザーがファイルをアップロードしていることを確認するため、OSレベルの存在チェック
                if os.path.exists(file_name):
                    with open(file_name, "rb") as f:
                        loaded_images[key] = base64.b64encode(f.read()).decode("utf-8")
                        # 最初にロードできた拡張子でmimeTypeを設定
                        if not data_uri_prefix:
                            data_uri_prefix = f"data:image/{'jpeg' if ext in ['.jpg', '.jpeg'] else 'png'};base64,"
                        found = True
                        break # 拡張子が見つかったら次へ
            except Exception as e:
                # ファイルの読み込み自体でエラー（パーミッションなど）が発生した場合
                error_message += f"Error loading {file_name}: {e}\n"
                found = False
                
        if not found:
            # 見つからなかったファイル名を出力
            error_message += f"'{base}.(jpg/jpeg)'が見つかりませんでした。ファイル名を確認してください。\n"
            
    # close画像とopen画像の両方が揃っているかチェック
    if "close" not in loaded_images or "open" not in loaded_images:
        # 両方揃っていない場合、口パクを無効にする
        return None, None, None, error_message, False
    
    # 全て揃っていてエラーがない場合
    return loaded_images["close"], loaded_images["open"], data_uri_prefix, None, True
 
# ===============================
# 音声データ生成とSession State保存（リトライロジック含む）
# ===============================
def generate_and_store_tts(text):
    """Gemini TTSで音声生成し、base64データをst.session_state.audio_to_playに保存する"""
    if not API_KEY:
        st.session_state.audio_to_play = None
        st.error("⚠️ APIキーが設定されていません。音声生成はスキップされました。")
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
            # TTS APIには遅延があるため、リトライと指数バックオフを適用
            response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
 
            # 結果から音声データを取り出す
            audio_data = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            st.session_state.audio_to_play = audio_data
            return
 
        except requests.exceptions.HTTPError as e:
            if response.status_code in [429, 503] and attempt < MAX_RETRIES - 1:
                print(f"TTS API Rate Limit/Service Unavailable. Retrying in {2 ** attempt}s...")
                time.sleep(2 ** attempt)
                continue
            # 最終試行または他のエラー
            print(f"TTS API Error (HTTP {response.status_code}) or final attempt failed: {e}")
            st.error(f"TTS音声生成に失敗しました: HTTP {response.status_code}")
            break
        except Exception as e:
            print(f"Error generating TTS (Non-HTTP): {e}")
            st.error(f"TTS音声生成に失敗しました: {e}")
            break
            
    st.session_state.audio_to_play = None
 
# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー", layout="wide")
 
# --- グローバルCSSの適用 ---
st.markdown(f"""
<style>
/* Streamlitのヘッダー/トップバーを非表示にする（任意） */
header {{ visibility: hidden; }}
 
/* stSidebarContent直下の要素のwidthを修正 */
[data-testid="stSidebarContent"] > div:first-child {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
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
    margin: 0 auto;
    border: 3px solid #ff69b4; 
    box-shadow: 0 0 15px rgba(255, 105, 180, 0.5);
}}
/* stSidebarContentにも幅を適用し、確実に固定 */
[data-testid="stSidebarContent"] {{
    width: {SIDEBAR_FIXED_WIDTH} !important;
    min-width: {SIDEBAR_FIXED_WIDTH} !important;
    max-width: {SIDEBAR_FIXED_WIDTH} !important;
    overflow-y: auto; /* エラーメッセージ表示のためスクロールを許可 */
}}

/* サイドバーの開閉ボタン（<<マーク）を非表示にする */
[data-testid="stSidebarCollapseButton"] {{
    display: none !important;
}}

/* サイドバーの横スクロールバーを非表示にする */
section[data-testid="stSidebar"] {{
    overflow-x: hidden !important;
    width: {SIDEBAR_FIXED_WIDTH} !important; 
    min-width: {SIDEBAR_FIXED_WIDTH} !important;
    max-width: {SIDEBAR_FIXED_WIDTH} !important;
    background-color: #f8e7ff !important; 
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
    # 画像のデータURIを取得
    img_close_base64, img_open_base64, data_uri_prefix, error_msg, has_images = get_avatar_images()
    
    # 画像が揃っていない場合、エラーメッセージを表示
    if not has_images and error_msg:
        st.error(f"🚨画像ロードエラー:\n{error_msg}")
        
    # 画像表示のための初期設定
    display_img_base64 = img_close_base64 if has_images else "R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==" # 透明GIF
    display_data_uri_prefix = data_uri_prefix if data_uri_prefix else "data:image/gif;base64,"
    
    # 画像の表示と口パク制御JS関数の埋め込み
    st.markdown(f"""
    <img id="avatar" src="{display_data_uri_prefix}{display_img_base64}" class="avatar">
    
    <script>
    // 口パク制御用のJavaScript
    const imagesAvailable = {'true' if has_images else 'false'};
    const imgCloseBase64 = "{data_uri_prefix}{img_close_base64}" || "{display_data_uri_prefix}{display_img_base64}";
    const imgOpenBase64 = "{data_uri_prefix}{img_open_base64}" || "{display_data_uri_prefix}{display_img_base64}";
    let talkingInterval = null;
    
    // 口パクを開始する関数
    window.startTalking = function() {{
        // 画像が揃っている場合のみ口パクを実行
        if (imagesAvailable) {{
            const avatar = document.getElementById('avatar');
            if (!avatar) return;

            let toggle = false;
            if (talkingInterval) clearInterval(talkingInterval);
            // 160msごとに画像を切り替え
            talkingInterval = setInterval(() => {{
                avatar.src = toggle ? imgOpenBase64 : imgCloseBase64;
                toggle = !toggle;
            }}, 160); 
        }}
    }}
    
    // 口パクを停止する関数
    window.stopTalking = function() {{
        // インターバルを停止
        if (talkingInterval) clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar');
        // 画像が揃っている場合のみ、口閉じ画像に戻す
        if (imagesAvailable && avatar) {{
            avatar.src = imgCloseBase64;
        }}
        // 揃っていない場合は何もしない（ダミー画像に切り替わらないように）
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
        
        // window.startTalkingが存在するか確認してから呼び出す
        if (window.startTalking) {{
            console.log("Starting Lip Sync...");
            window.startTalking();
        }}
        
        const pcmData = base64ToArrayBuffer(base64AudioData);
        const wavBlob = pcmToWav(pcmData, sampleRate);
        const audioUrl = URL.createObjectURL(wavBlob);
        
        const audio = new Audio(audioUrl);
        audio.autoplay = true;
 
        audio.onended = () => {{ 
            console.log("Stopping Lip Sync...");
            // window.stopTalkingが存在するか確認してから呼び出す
            if (window.stopTalking) window.stopTalking(); 
            // URLを解放
            URL.revokeObjectURL(audioUrl);
        }};
        audio.play().catch(e => {{
            console.error("Audio playback failed (check console for MIME type error):", e);
            // エラー時も口パク停止
            if (window.stopTalking) window.stopTalking();
            URL.revokeObjectURL(audioUrl);
        }});
    </script>
    """
    # height=0, width=0のカスタムコンポーネントでスクリプトを実行
    components.html(js_code, height=0, width=0)
    # 再生トリガー実行後、データをクリア
    st.session_state.audio_to_play = None
 
# --- メインコンテンツ ---
st.title("🎀 ユッキー（Vtuber風AIアシスタント）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")
 
# 音声認識ボタンとチャット履歴の表示
st.subheader("音声入力")
# StreamlitのIFrame内で親のStreamlitアプリにメッセージを送信するためのJSを含む
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

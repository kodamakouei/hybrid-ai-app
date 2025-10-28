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
あなたは、教育的な目的を持つAIアシスタントです。ユーザーの質問に対し、以下の厳格な3つのルールに従って応答してください。

【応答ルール1：事実・知識の質問（直接回答）】
質問が、**確定した事実**、**固有名詞**、**定義**、**単純な知識**を尋ねるものである場合、**その答えを直接、かつ簡潔な名詞または名詞句で回答してください**。

【応答ルール2：計算・思考・問題解決の質問（解法ガイド）】
質問が、**計算**、**分析**、**プログラミング**、**論理的な思考**を尋ねるものである場合、**最終的な答えや途中式は絶対に教えないでください**。代わりに、ユーザーが次に取るべき**最初の、最も重要な解法のステップ**や**必要な公式のヒント**を教えることで、ユーザーの自習を促してください。

【応答ルール3：途中式の判定（採点モード）】
ユーザーが「この途中式は正しいか？」という形で**具体的な式や手順**を提示した場合、あなたは**教師としてその式が正しいか間違っているかを判断**し、優しくフィードバックしてください。
"""

# --- 共通設定 ---
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"
MAX_RETRIES = 5
# サイドバーの幅をこの値に合わせて調整 (画面幅の約1/4に設定)
SIDEBAR_WIDTH = "25%" # 修正点: 33%から25%に変更

# --- APIキーの読み込み ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    API_KEY = ""
    st.warning("⚠️ APIキーが設定されていません。音声機能は動作しません。")


# ===============================
# アバター画像取得 (キャッシュ)
# ===============================
@st.cache_data
def get_avatar_images():
    # ユーザーがアップロードしたファイルを想定したファイル名
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
        # 画像がない場合のプレースホルダー
        placeholder_svg = base64.b64encode(
            f"""<svg width="400" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-size="28" fill="#a00" font-family="sans-serif">❌画像なし</text><text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" font-size="20" fill="#a00" font-family="sans-serif">yukki-close/open.jpg/jpeg</text></svg>""".encode('utf-8')
        ).decode("utf-8")
        return placeholder_svg, placeholder_svg, "data:image/svg+xml;base64,", False

# ===============================
# 音声生成と再生（appp.pyのロジックを統合）
# ===============================
def generate_and_play_tts(text):
    """Gemini TTSで音声生成＋自動再生（口パク制御付き）"""
    if not API_KEY:
        st.error("APIキーが設定されていないため、音声生成はスキップされました。")
        return False
        
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
                base64_data = audio_data['data']
                mime_type = audio_data.get('mimeType', 'audio/L16;rate=24000')
                try:
                    sample_rate = int(mime_type.split('rate=')[1])
                except IndexError:
                    sample_rate = 24000
                
                # JavaScriptでPCMをWAVに変換し、再生と口パク制御を行う
                js_code = f"""
                <script>
                    // PCM to WAV, base64 utility functions (from appp.py logic)
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

                    // Playback and Lip Sync Control
                    if (window.startTalking) window.startTalking();
                    const pcmData = base64ToArrayBuffer('{base64_data}');
                    const wavBlob = pcmToWav(pcmData, {sample_rate});
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
                # 音声の再生と口パク制御をJavaScriptで実行
                components.html(js_code, height=0, width=0)
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

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー（Vtuber風AIアシスタント）", layout="wide")

# --- グローバルCSSの適用 ---
# StreamlitのデフォルトCSSをオーバーライドし、サイドバーとメインコンテンツのレイアウトを調整
st.markdown(f"""
<style>
/* Streamlitのヘッダー/トップバーを非表示にする（任意） */
header {{ visibility: hidden; }}

/* サイドバーの幅と固定位置を設定 */
section[data-testid="stSidebar"] {{ 
    width: {SIDEBAR_WIDTH} !important; 
    min-width: {SIDEBAR_WIDTH} !important;
    max-width: {SIDEBAR_WIDTH} !important; 
    background-color: #FFFFFF !important; 
    height: 100vh;
    padding-top: 20px;
    box-shadow: 2px 0 5px rgba(0,0,0,0.1);
    z-index: 1000;
    
    /* 変更点: サイドバーを固定する */
    position: fixed; 
    left: 0;
    top: 0; 
}}

/* メインコンテンツのコンテナにサイドバーの幅だけ左マージンを設定し、横に並ぶようにする */
/* stAppのラッパーを調整 */
.stApp {{
    /* Streamlitのメインコンテンツのラッパー */
    /* 変更点: サイドバーの幅（%）に合わせてマージンを設定 */
    margin-left: {SIDEBAR_WIDTH}; 
    padding-left: 1rem; /* 必要に応じて調整 */
    padding-right: 1rem;
    padding-top: 1rem;
}}

/* アバターを中央に配置 */
/* st-emotion-cache-vk3ypz は新しいStreamlitのSidebar内のコンテナ */
[data-testid="stSidebarContent"] > div:first-child {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding-top: 50px;
}}
.avatar {{ 
    /* サイドバーの幅に合わせてアバターの最大幅を調整 */
    max-width: 90%; 
    height: auto; 
    border-radius: 16px; 
    object-fit: cover; 
    border: 5px solid #ff69b4; 
    box-shadow: 0 4px 10px rgba(255,105,180,0.5); 
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

# --- サイドバーにアバターと関連要素を配置（レイアウト維持） ---
with st.sidebar:
    img_close_base64, img_open_base64, data_uri_prefix, has_images = get_avatar_images()
    
    # HTML/JSによるアバターの描画と口パク制御関数の定義
    st.markdown(f"""
    <img id="avatar" src="{data_uri_prefix}{img_close_base64}" class="avatar">
    
    <script>
    // Base64データをJavaScript変数として定義
    const imgCloseBase64 = "{data_uri_prefix}{img_close_base64}";
    const imgOpenBase64 = "{data_uri_prefix}{img_open_base64}";
    let talkingInterval = null;
    
    // グローバルな口パク開始関数
    window.startTalking = function() {{
        // window.parent.document.getElementById('avatar') ではなく、
        // Streamlitのコンポーネント内で直接要素を取得するように変更（安全のため）
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
    
    // グローバルな口パク停止関数
    window.stopTalking = function() {{
        if (talkingInterval) clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar'); 
        if ({'true' if has_images else 'false'} && avatar) {{ 
            avatar.src = imgCloseBase64; 
        }}
    }}
    </script>
    """, unsafe_allow_html=True)

    # サイドバー内に音声入力UIを配置
    st.subheader("音声入力")
    components.html("""
    <div id="mic-container" style="padding: 10px 0;">
        <button onclick="window.parent.startRec()" 
                style="background-color: #ff69b4; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 16px;">
            🎙 話す
        </button>
        <p id="mic-status" style="margin-top: 10px;">マイク停止中</p>
    </div>
    <script>
    // Streamlitのチャット入力欄にテキストを送信する関数
    function sendTextToStreamlit(text) {
        // Streamlitのiframeの親ウィンドウに対してメッセージを送信
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
        
        // グローバルな認識開始関数
        window.parent.startRec = () => {
            document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
            recognition.start();
        };
        
        recognition.onresult = (event) => {
            const text = event.results[0][0].transcript;
            document.getElementById("mic-status").innerText = "✅ " + text;
            sendTextToStreamlit(text); // 認識結果をStreamlitへ送信
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
    """, height=200)


# --- メインコンテンツ ---
st.title("🎀 ユッキー（Vtuber風AIアシスタント）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")

# --- チャット履歴の表示 ---
st.subheader("ユッキーとの会話履歴")
for msg in st.session_state.messages:
    # app.pyのサイドバーアバターを使うため、メインコンテンツのアイコンはシンプルに
    avatar_icon = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])

# --- ユーザー入力と処理 ---
if prompt := st.chat_input("質問を入力してください..."):
    # 1. ユーザーメッセージを追加・表示
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # 2. アシスタントの応答を取得
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ユッキーが思考中..."):
            if st.session_state.chat:
                try:
                    # Gemini API呼び出し
                    response = st.session_state.chat.send_message(prompt)
                    text = response.text
                    
                    # 応答テキストを表示
                    st.markdown(text)
                    
                    # 3. 音声生成と再生（口パク制御もこの中で実行される）
                    generate_and_play_tts(text)
                    
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

# --- 音声認識からチャット入力へテキストを転送するJavaScript（メインコンテンツ側） ---
# Streamlitのチャット入力欄はカスタムコンポーネントの外にあるため、PostMessageでテキストを渡す
components.html("""
<script>
window.addEventListener('message', event => {
    // 別のiframe (サイドバー内の音声認識) からのメッセージか確認
    if (event.data.type === 'SET_CHAT_INPUT') {
        const chatInput = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (chatInput) {
            chatInput.value = event.data.text;
            chatInput.dispatchEvent(new Event('input', { bubbles: true }));
            // Enterキーイベントを発生させてメッセージを送信
            const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, keyCode: 13 });
            chatInput.dispatchEvent(enterEvent);
        }
    }
});
</script>
""", height=0)

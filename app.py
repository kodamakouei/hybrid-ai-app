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
# NOTE: APIキーはStreamlitのst.secretsから取得することを想定しています。
API_KEY = st.secrets["GEMINI_API_KEY"] 

# ===============================
# アバター表示（口パク付き）
# ===============================
def show_avatar():
    # ★実行環境に yukki-close.jpg と yukki-open.jpg が必要です
    
    img_close_base64 = None
    img_open_base64 = None
    
    # 画像ファイルの存在確認とBase64変換
    try:
        with open("yukki-close.jpg", "rb") as f:
            img_close_base64 = base64.b64encode(f.read()).decode("utf-8")
        with open("yukki-open.jpg", "rb") as f:
            img_open_base64 = base64.b64encode(f.read()).decode("utf-8")
        has_images = True
    except FileNotFoundError:
        has_images = False
        # 画像がない場合はダミー画像を使用
        # プレースホルダーのBase64データURI
        img_close_base64 = "data:image/svg+xml;base64," + base64.b64encode(
            f"""<svg width="280" height="280" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8e7ff"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="24" fill="#a00" font-family="sans-serif">❌画像が見つかりません</text><text x="50%" y="65%" dominant-baseline="middle" text-anchor="middle" font-size="16" fill="#a00" font-family="sans-serif">yukki-close.jpg / yukki-open.jpg</text></svg>""".encode('utf-8')
        ).decode("utf-8")
        # 開口画像は閉口画像と同じで固定
        img_open_base64 = img_close_base64
        # st.warning("⚠️ アバター画像ファイルが見つかりません。プレースホルダーを表示します。", icon="🖼️")
        # st.toast()はUIに残りすぎるため、代わりにコメントアウトしました。


    # StreamlitにHTML/JSを埋め込み（口パク制御）
    # .avatar-container の CSS を強化します
    components.html(f"""
    <style>
    /* アバターを配置するコンテナのスタイル */
    .avatar-container {{
        /* 画面左上に固定 (Fixed Positioning) */
        position: fixed !important; /* 強制的に固定 */
        top: 60px !important; /* Streamlitヘッダーを考慮して調整 */
        left: 20px !important; /* 左端から20px */
        width: 300px;
        z-index: 100; /* 他の要素より手前に表示 */
        text-align: center;
        /* 背景色を追加して、スクロール時にチャットと重なるのを防ぐ */
        background: white; 
        padding: 10px;
        border-radius: 16px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }}
    .avatar {{
        width: 280px;
        height: 280px;
        border-radius: 16px;
        border: 2px solid #f0a;
        object-fit: cover;
    }}
    </style>
    <div class="avatar-container">
      <img id="avatar" src="{img_close_base64}" class="avatar">
    </div>

    <script>
    // 口パク開始関数
    let talkingInterval = null;
    function startTalking() {{
        const avatar = document.getElementById('avatar');
        // 画像がある場合のみ口パクを実行
        if ({'true' if has_images else 'false'}) {{ 
            let toggle = false;
            if (talkingInterval) clearInterval(talkingInterval);
            talkingInterval = setInterval(() => {{
                avatar.src = toggle
                ? "data:image/jpeg;base64,{img_open_base64}" // 口が開いた画像
                : "data:image/jpeg;base64,{img_close_base64}"; // 口が閉じた画像
                toggle = !toggle;
            }}, 160);
        }}
    }}
    // 口パク停止関数
    function stopTalking() {{
        clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar');
        // 画像がある場合のみ閉口画像に戻す
        if ({'true' if has_images else 'false'}) {{
            avatar.src = "data:image/jpeg;base64,{img_close_base64}";
        }}
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
    
    MAX_RETRIES = 5
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()
            break
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                import time
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                st.error(f"❌ 音声データ取得に失敗しました。詳細: {e}")
                return

    try:
        audio_data_base64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except Exception:
        st.error("❌ 音声データ取得失敗: APIレスポンス構造が予期されたものではありません。")
        return

    html_audio_player = f"""
    <script>
    if (window.startTalking) startTalking();
    
    const audio = new Audio();
    audio.src = 'data:audio/wav;base64,{audio_data_base64}'; 
    audio.autoplay = true;

    audio.onended = function() {{
        if (window.stopTalking) stopTalking();
    }};
    
    audio.play().catch(e => {{
        console.error("Audio playback failed (usually due to autoplay policy):", e);
        if (window.stopTalking) stopTalking(); 
    }});

    const container = document.createElement('div');
    container.style.display = 'none';
    container.appendChild(audio);
    document.body.appendChild(container);
    </script>
    """
    components.html(html_audio_player, height=0, width=0)

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー（口パク対応）", layout="wide")
st.title("🎀 ユッキー（Vtuber風AIアシスタント）")

# ====================================================================
# 【固定アバター】アバターを画面左上に固定表示
# ====================================================================
show_avatar()

# ====================================================================
# 【CSS注入】メインコンテンツ（チャット履歴、音声入力など）を右側にオフセット
# ====================================================================
st.markdown("""
<style>
/* Streamlitのメインコンテンツの左側マージンを設定し、アバターと重ならないように右側にオフセット */
.main > div {{
    /* Streamlitの内部コンテナ（.main > div）にマージンを設定してコンテンツ全体を右に移動 */
    padding-left: 350px !important; /* アバターの幅(300px)より少し大きく */
}}
/* チャット入力フィールドの親コンテナにも同様にオフセットを適用 */
.stChatInput > div {{
    margin-left: 330px; 
    width: calc(100% - 330px);
}}
/* ユーザーのチャット入力欄自体を右側エリアに合わせる */
div[data-testid="stChatInputContainer"] {{
    position: fixed; /* 常に画面下に固定 */
    bottom: 0px;
    left: 330px; /* アバターの幅を避ける */
    right: 0px;
    z-index: 1000;
    background: white;
    padding: 10px 20px 10px 10px;
    box-shadow: 0 -2px 5px rgba(0,0,0,0.05);
}}
</style>
""", unsafe_allow_html=True)


# Geminiクライアントとチャットセッションの初期化
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY)
if "chat" not in st.session_state:
    config = {"system_instruction": SYSTEM_PROMPT, "temperature": 0.2}
    st.session_state.chat = st.session_state.client.chats.create(model="gemini-2.5-flash", config=config)
if "messages" not in st.session_state:
    st.session_state.messages = []


# ====================================================================
# 【右側コンテンツ】アバターの固定領域を避けるためのオフセット空間
# ====================================================================
# アバターの高さ+タイトル分、下にオフセットするためのダミー要素 (右側エリアの先頭に配置)
st.markdown("<div style='height: 380px;'></div>", unsafe_allow_html=True)


# ===============================
# 音声認識ボタン（右側エリアに配置）
# ===============================
st.subheader("音声入力")
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
        document.getElementById("mic-status").innerText = "⚠️ エラー: " + e.error;
    };

    recognition.onend = () => {
        if (document.getElementById("mic-status").innerText.startsWith("🎧")) {
            document.getElementById("mic-status").innerText = "マイク停止中";
        }
    }
} else {
    document.write("このブラウザは音声認識に対応していません。");
}
</script>
<button onclick="startRec()">🎙 話す</button>
<p id="mic-status">マイク停止中</p>
""", height=130)


# ===============================
# チャットUI（右側エリアに配置）
# ===============================
st.subheader("ユッキーとの会話履歴")
# 過去のメッセージを表示
for msg in st.session_state.messages:
    avatar = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ユーザーからの新しい入力
if prompt := st.chat_input("質問を入力してください..."):
    # ユーザーメッセージをセッションに追加し、表示
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    # アシスタントの応答
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("ユッキーが考え中..."):
            # Geminiにメッセージを送信
            response = st.session_state.chat.send_message(prompt)
            text = response.text
            
            # テキストを表示
            st.markdown(text)
            
            # 音声再生と口パク制御
            play_tts_with_lip(text)
            
            # アシスタントのメッセージをセッションに追加
            st.session_state.messages.append({"role": "assistant", "content": text})

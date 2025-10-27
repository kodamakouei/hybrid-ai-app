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
    if not (os.path.exists("yukki-close.jpg") and os.path.exists("yukki-open.jpg")):
        # 画像ファイルがない場合はエラーメッセージを表示して停止
        st.error("❌ yukki-close.jpg と yukki-open.jpg が同じフォルダにありません。")
        st.stop()

    # base64に変換してHTML/JSに埋め込む
    with open("yukki-close.jpg", "rb") as f:
        img_close = base64.b64encode(f.read()).decode("utf-8")
    with open("yukki-open.jpg", "rb") as f:
        img_open = base64.b64encode(f.read()).decode("utf-8")

    # StreamlitにHTML/JSを埋め込み（口パク制御）
    components.html(f"""
    <style>
    .avatar {{
        width: 280px;
        height: 280px;
        border-radius: 16px;
        border: 2px solid #f0a;
        object-fit: cover;
    }}
    </style>
    <div style="text-align:center;">
      <img id="avatar" src="data:image/jpeg;base64,{img_close}" class="avatar">
    </div>

    <script>
    // 口パク開始関数
    let talkingInterval = null;
    function startTalking() {{
        const avatar = document.getElementById('avatar');
        let toggle = false;
        if (talkingInterval) clearInterval(talkingInterval);
        talkingInterval = setInterval(() => {{
            avatar.src = toggle
              ? "data:image/jpeg;base64,{img_open}" // 口が開いた画像
              : "data:image/jpeg;base64,{img_close}"; // 口が閉じた画像
            toggle = !toggle;
        }}, 160); // パクパク速度（ミリ秒）
    }}
    // 口パク停止関数
    function stopTalking() {{
        clearInterval(talkingInterval);
        const avatar = document.getElementById('avatar');
        avatar.src = "data:image/jpeg;base64,{img_close}";
    }}
    </script>
    """, height=340)

# ===============================
# 音声再生＋口パク制御 (修正済み)
# ===============================
def play_tts_with_lip(text):
    # Gemini TTS APIへのペイロード構築
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}
        },
        "model": TTS_MODEL
    }
    
    headers = {'Content-Type': 'application/json'}
    
    # 指数バックオフ付きのAPI呼び出し
    MAX_RETRIES = 5
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
            response.raise_for_status() # HTTPエラーを確認
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
        # resultからbase64エンコードされたオーディオデータを抽出 (デコードせずそのまま使用)
        audio_data_base64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except Exception:
        st.error("❌ 音声データ取得失敗: APIレスポンス構造が予期されたものではありません。")
        return

    # 🎬 JavaScriptで口パクアニメーション制御と自動再生
    # st.audioを使わず、HTML/JSで <audio autoplay> を生成し、onendedで口パクを停止させる
    html_audio_player = f"""
    <script>
    // window.startTalkingとwindow.stopTalkingはshow_avatar()で定義されています
    if (window.startTalking) startTalking();
    
    // Audioオブジェクトを生成し、Base64データURIを設定
    const audio = new Audio();
    // TTS APIはPCM16を返すため、ここでは 'audio/wav' としてBase64データを扱います
    audio.src = 'data:audio/wav;base64,{audio_data_base64}'; 
    audio.autoplay = true;

    // 音声再生が終了したら口パクを停止
    audio.onended = function() {{
        if (window.stopTalking) stopTalking();
    }};
    
    // 自動再生を試みる (ブラウザのポリシーでブロックされる可能性がある)
    audio.play().catch(e => {{
        console.error("Audio playback failed (usually due to autoplay policy):", e);
        // 再生に失敗した場合でも、口パクを停止させる
        if (window.stopTalking) stopTalking(); 
    }});

    // Streamlitのコンポーネントとしてオーディオを再生させるため、
    // UIからは見えない位置にオーディオ要素を一時的に挿入 (ただし、自動再生の回避策として機能しない場合もあります)
    const container = document.createElement('div');
    container.style.display = 'none';
    container.appendChild(audio);
    document.body.appendChild(container);
    </script>
    """
    # components.htmlでオーディオ再生と口パク制御を同時に行う
    # height=0, width=0に設定することで、このコンポーネント自体を非表示にします
    components.html(html_audio_player, height=0, width=0)

# ===============================
# Streamlit UI
# ===============================
st.set_page_config(page_title="ユッキー（口パク対応）", layout="wide")
st.title("🎀 ユッキー（Vtuber風AIアシスタント）")

# アバターの表示とJS関数の埋め込み
show_avatar()

# Geminiクライアントとチャットセッションの初期化
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
# HTML/JSでブラウザのSpeechRecognition APIを使い、結果をStreamlitのチャット入力欄に注入する
components.html("""
<script>
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;

if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'ja-JP'; // 日本語を設定
    recognition.continuous = false;
    recognition.interimResults = false;

    // 認識開始ボタンのクリックハンドラ
    function startRec() {
        document.getElementById("mic-status").innerText = "🎧 聴き取り中...";
        recognition.start();
    }

    // 認識結果が出たときのハンドラ
    recognition.onresult = (event) => {
        const text = event.results[0][0].transcript;
        document.getElementById("mic-status").innerText = "✅ " + text;
        
        // Streamlitのチャット入力エリアを探してテキストを注入
        const chatInput = window.parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
        if (chatInput) {
            chatInput.value = text;
            chatInput.dispatchEvent(new Event('input', { bubbles: true })); // inputイベントを発火
            
            // エンターキーイベントを発火させて送信をシミュレート
            const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
            chatInput.dispatchEvent(enterEvent);
        }
    };

    // 認識エラー時のハンドラ
    recognition.onerror = (e) => {
        document.getElementById("mic-status").innerText = "⚠️ エラー: " + e.error;
    };

    // 認識が終了した時のハンドラ（続けて認識する場合はここでrecognition.start()を呼ぶ）
    recognition.onend = () => {
        if (document.getElementById("mic-status").innerText.startsWith("🎧")) {
            document.getElementById("mic-status").innerText = "マイク停止中";
        }
    }
} else {
    // 対応していないブラウザの場合
    document.write("このブラウザは音声認識に対応していません。");
}
</script>
<button onclick="startRec()">🎙 話す</button>
<p id="mic-status">マイク停止中</p>
""", height=130)

# ===============================
# チャットUI
# ===============================
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

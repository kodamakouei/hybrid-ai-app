import streamlit as st
from google import genai
import base64
import json
import requests
import streamlit.components.v1 as components
import os
import time
from google.genai.types import Part
# =========================================
#  システムプロンプト（元のまま）
# =========================================
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

# =========================================
# APIキー読み込み
# =========================================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""

# =========================================
# TTS（音声生成）関数
# =========================================
def generate_and_store_tts(text):
    """
    TTSモデルの互換性チェックのため、モデル名を変更し、エラーログを強化
    """
    if not text:
        return None

    try:
        client = genai.Client(api_key=API_KEY)

        # ★モデル名をメインチャットと同じ安定版に変更 (互換性確認のため)
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=[text],
            config={
                # ★ audio_config はそのまま残し、動作するか確認
                "audio_config": {
                    "voice_name": "ja-JP-Neural2-B",
                    "speaking_rate": 1.05
                }
            }
        )

        audio_data = None
        for part in response.parts:
            # safety_ratings や blocked がないか確認
            if hasattr(part, "safety_ratings") and part.safety_ratings:
                print(f"安全性チェックにより応答がブロックされました: {part.safety_ratings}")
                return None
                
            if hasattr(part, "data") and part.data:
                audio_data = part.data
                break

        if not audio_data:
            print("音声パートが見つかりませんでした。全応答パーツ:")
            print(response.parts) # すべてのパーツを出力して、TTSのバイトデータが含まれているか確認
            return None

        audio_bytes = audio_data
        audio_dir = "generated_audio"
        os.makedirs(audio_dir, exist_ok=True)
        audio_path = os.path.join(
            audio_dir,
            f"tts_{int(time.time())}.wav"
        )

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        print("TTS 音声生成成功:", audio_path)
        return audio_path

    except Exception as e:
        # ★エラー発生時の詳細なログを出力
        print("TTS生成中にエラーが発生しました。詳細:")
        print(f"エラー種別: {type(e).__name__}")
        print(f"エラーメッセージ: {e}")
        return None


# =========================================
# Streamlit UI 設定
# =========================================
st.set_page_config(
    page_title="ユッキー",
    layout="wide"   # ★サイドバーが無い前提で全幅使用
)

# ---- セッション初期化 ----
if "client" not in st.session_state:
    st.session_state.client = genai.Client(api_key=API_KEY) if API_KEY else None

if "chat" not in st.session_state:
    if st.session_state.client:
        config = {
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.2
        }
        st.session_state.chat = st.session_state.client.chats.create(
            model="gemini-2.5-flash",
            config=config
        )
    else:
        st.session_state.chat = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "audio_to_play" not in st.session_state:
    st.session_state.audio_to_play = None


# =========================================
# メイン画面 UI
# =========================================
st.title("🎀 ユッキー（疑似教師）")
st.caption("知識は答え、思考は解法ガイドのみを返します。")

# ---------- 画像アップロード ----------
st.subheader("画像を送って質問する")

uploaded_image = st.file_uploader("画像をアップロードしてみよう", type=["jpg", "jpeg", "png"])

if uploaded_image:
    st.image(uploaded_image, caption="アップロードされた画像", width=300)
    uploaded_bytes = uploaded_image.read()
else:
    uploaded_bytes = None

# ---------- ユーザー音声入力 UI（Web Audio API） ----------
components.html("""
<script>
function startVoiceRecognition() {
    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = "ja-JP";
    recognition.onresult = function(event) {
        const text = event.results[0][0].transcript;
        window.parent.postMessage({type: 'stt-result', text: text}, '*');
    };
    recognition.start();
}
</script>

<button onclick="startVoiceRecognition()" style="
    background-color:#ff8dc7;
    border:none;
    padding:12px 18px;
    border-radius:8px;
    color:white;
    font-size:16px;
    cursor:pointer;
    margin-bottom:10px;
">
🎤 音声で話す
</button>
""", height=80)

# ---------- 音声で認識したテキストの受信 ----------
components.html("""
<script>
window.addEventListener("message", (event) => {
    if (event.data.type === "stt-result") {
        const text = event.data.text;
        window.parent.postMessage({ type: "streamlit:setChatInputValue", value: text }, "*");
        window.parent.postMessage({ type: "streamlit:focusChatInput" }, "*");
    }
});
</script>
""", height=0)

# ---------- チャット履歴 ----------
st.subheader("ユッキーとの会話履歴")

for msg in st.session_state.messages:
    avatar_icon = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        st.markdown(msg["content"])

# ---------- テキストチャット入力 ----------
if prompt := st.chat_input("質問を入力してください…"):
    
    # 履歴へ追加 (ユーザー)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Geminiへのメッセージ内容を構築するためのリスト
    contents_to_send = []
    
    # 1. テキストプロンプトを追加
    contents_to_send.append(prompt) 
    
    # 2. 画像データがあれば追加
    if uploaded_image and uploaded_bytes:
        
        # ★★★ 修正ポイント: Part.from_bytes() を使って画像データを明示的に Part オブジェクトに変換する ★★★
        try:
            image_part = Part.from_bytes(
                data=uploaded_bytes,
                mime_type=uploaded_image.type
            )
            contents_to_send.append(image_part)
        except Exception as e:
            # Part変換エラーログ
            print(f"画像データのPart変換中にエラーが発生しました: {e}")
            
    # ---- Gemini へ送信 ----
    if st.session_state.chat:
        
        # message_content は常に contents_to_send リスト全体
        message_content = contents_to_send 
        
        try:
            # 修正後のロジック: リストには (str または Part) の組み合わせが含まれる
            response = st.session_state.chat.send_message(message_content)
        except Exception as e:
            # 送信時のエラーをキャッチし、ログに出力
            response_text = f"Gemini API送信エラー: {type(e).__name__} - {e}"
            print(response_text)
            
        else:
            response_text = response.text if hasattr(response, "text") else str(response)
    else:
        response_text = "APIキーが設定されていないため応答できません。"

    # 履歴に追加 (アシスタント)
    st.session_state.messages.append({"role": "assistant", "content": response_text})

    # TTS生成
    audio_path = generate_and_store_tts(response_text)
    if audio_path:
        st.session_state.audio_to_play = audio_path
        
    # Streamlitの再実行 (st.rerun) 前に、次の入力のために画像の状態をリセットすることが重要
    # Streamlitのライフサイクルにより、ファイルアップローダーの状態は維持されないため、
    # このロジックはデバッグ目的で残しますが、根本的には st.chat_input の再実行を防ぐために st.rerun が必要です。

    # ★★★ 追記: Geminiチャットのセッションをリセットし、エラーの原因となる再利用を防ぐ ★★★
    # ただし、これは既存の会話履歴が失われる副作用があるため、推奨はできません。
    # 代わりに、簡潔なテキストメッセージの場合にのみ履歴を追加し、rerun後は画像がリセットされることを確認します。

    # 画像がアップロードされていた場合、次回再実行時に画像が再送信されるのを防ぐための処置
    if uploaded_image:
        uploaded_image = None # uploaded_imageの参照をリセット

    st.rerun()
# ---------- 音声再生 ----------
if st.session_state.audio_to_play:
    st.audio(st.session_state.audio_to_play, format="audio/wav")

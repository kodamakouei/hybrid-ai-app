import streamlit as st
from streamlit_mic_recorder import mic_recorder
import google.generativeai as genai
import base64
import requests
import json
import io
# st.audio()でraw PCMデータを使用する際にbase64からデコードするために必要
import numpy as np
import scipy.io.wavfile as wavfile


# ===================== 設定 =====================
SYSTEM_PROMPT = """
あなたは教育的なAIアシスタント「ユッキー」です。
・事実の質問には簡潔に答えること。
・思考や計算問題はヒントのみを教えること。
・ユーザーが成長できるように、優しく導くこと。
"""

USER_AVATAR = "🧑" # ユーザーアイコン
AI_AVATAR = "yukki-icon.jpg" # AIアイコン

# 音声合成モデル (Gemini TTS)
TTS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Kore"

# 音声→テキスト用エンドポイント（Whisper互換）
# Note: Canvas環境のGemini APIキーはBearerトークンとして機能しないため、このSTT_URLの認証は外部APIを使用している場合のみ有効です。
# Streamlit Mic Recorderが返すオーディオフォーマットに合わせるため、ここではSTTのロジックは最小限に留めます。
STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/whisper-1:transcribe"

# ===================== APIキー =====================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("❌ Streamlit Secrets に GEMINI_API_KEY が設定されていません。")
    st.stop()

# ===================== TTS（音声生成） =====================
def play_tts(text: str):
    """Gemini TTSで音声を生成し、WAVに変換して再生"""
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}
        },
        "model": TTS_MODEL
    }
    headers = {"Content-Type": "application/json"}
    # API Keyをクエリパラメータとして渡す
    r = requests.post(f"{TTS_API_URL}?key={API_KEY}", headers=headers, data=json.dumps(payload))
    result = r.json()

    try:
        # TTS APIはraw PCMデータを返す
        audio_data_base64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        pcm_bytes = base64.b64decode(audio_data_base64)
        
        # PCM (Int16) をNumPy配列に変換
        pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
        
        # WAVファイルとしてメモリに書き込み (サンプリングレートはTTSモデルのデフォルト24000Hzを使用)
        wav_io = io.BytesIO()
        wavfile.write(wav_io, 24000, pcm_array)
        wav_io.seek(0)
        
        # Streamlitのst.audioで再生
        st.audio(wav_io, format="audio/wav")

    except Exception as e:
        st.warning(f"音声再生に失敗しました。APIからの応答を確認してください: {e}")

# ===================== Streamlit UI =====================
st.set_page_config(page_title="ユッキー", layout="wide")

# ★★★ 修正箇所 1: アバターサイズと配置のためのカスタムCSSを注入 ★★★
st.markdown("""
<style>
/* ---------------------------------------------------- */
/* 共通設定: アバターコンテナのサイズと配置 */
/* ---------------------------------------------------- */

/* アバターコンテナのセレクタ (st-emotion-cache-1f1f2x2) */
/* 注: このセレクタはAIとユーザーの両方に適用されるため、両方のアバターサイズが500pxになります。 */
div[data-testid="stChatMessage"] .st-emotion-cache-1f1f2x2 {
    width: 500px !important; /* 500pxに拡大 */
    height: 500px !important; /* 500pxに拡大 */
    /* 垂直方向の中央揃えは全アバターに適用 */
    align-items: center; 
    
    /* ユーザーアバター（絵文字）を大きく見せるための調整 */
    font-size: 300px !important; /* 500pxのコンテナに合わせて調整 */
    
    /* デフォルトの水平配置（左寄せ/右寄せ）を尊重するため、初期値を設定 */
    justify-content: initial; 
}

/* Chat Message Avatar Image (User and Assistant) - 画像のサイズ固定 */
div[data-testid="stChatMessage"] img {
    width: 500px !important; /* 500pxに拡大 */
    height: 500px !important; /* 500pxに拡大 */
    min-width: 500px !important; /* 500pxに拡大 */
    min-height: 500px !important; /* 500pxに拡大 */
    object-fit: cover !important; /* 画像を中央に配置し、枠に収まるようにする */
}
/* ---------------------------------------------------- */
/* ユーザーの右寄せはStreamlitのデフォルト動作で維持されます。 */
/* ---------------------------------------------------- */
</style>
""", unsafe_allow_html=True)
# ★★★ 修正箇所 1 終了 ★★★

st.title("ユッキー 🎀")
st.caption("音声でも文字でも質問できるAIだよ。思考系問題はヒントだけね💕")

# Geminiチャットモデル初期化
# Chat History for the assistant response will be stored in st.session_state.chat
if "chat_session" not in st.session_state:
    try:
        genai.configure(api_key=API_KEY)
        model_chat = genai.GenerativeModel("gemini-2.5-flash")
        st.session_state.chat_session = model_chat.start_chat(history=[
            # システムプロンプトを履歴の最初のメッセージとして設定
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]}
        ])
    except Exception as e:
        st.error(f"Geminiモデルの初期化に失敗しました: {e}")
        st.stop()


# ★★★ 履歴の再表示ロジック（重要） ★★★
# st.session_state.chat_sessionから履歴を取得し、UIに表示する
st.markdown("### 💬 これまでの会話")
for message in st.session_state.chat_session.get_history():
    # システムプロンプトは表示しない
    if message.role == 'user' and message.parts[0].text == SYSTEM_PROMPT:
        continue
    
    # roleをStreamlitの 'user'/'assistant' に変換
    role = "user" if message.role == "user" else "assistant"
    avatar = USER_AVATAR if role == "user" else AI_AVATAR
    
    with st.chat_message(role, avatar=avatar):
        # 履歴の内容を表示
        st.markdown(message.parts[0].text)


# ===================== 音声入力 =====================
st.markdown("### 🎙️ 音声で質問する")

audio_data = mic_recorder(
    start_prompt="🎤 話す",
    stop_prompt="🛑 停止",
    just_once=True,
    use_container_width=True,
    key="mic_recorder_key"
)

if audio_data:
    # 認識された音声データを表示（デバッグ用）
    # st.audio(audio_data["bytes"]) # この行はコメントアウトまたは削除してもOK
    st.info("🧠 音声認識中...")

    # ==== Whisper API呼び出し（multipart/form-data） ====
    # Streamlit Cloudの環境で外部APIの認証を通すのは難しいですが、ここではユーザー提供のロジックを踏襲
    # Note: このSTT認証ロジックは、CanvasのAPIキーでは動作しない可能性が高いです。
    headers = {"Authorization": f"Bearer {API_KEY}"}
    files = {
        "file": ("audio.webm", audio_data["bytes"], "audio/webm")
    }

    try:
        r = requests.post(STT_URL, headers=headers, files=files)
        r.raise_for_status() # HTTPエラーをチェック

        result = r.json()
        prompt = result.get("text", "").strip()

        if prompt:
            st.success(f"🗣️ 認識結果: {prompt}")

            # ユーザーメッセージを履歴に追加
            st.session_state.chat_session.send_message(prompt)
            with st.chat_message("user", avatar=USER_AVATAR):
                st.markdown(prompt)

            # ==== Geminiチャット応答 ====
            with st.spinner("ユッキーが考え中..."):
                response = st.session_state.chat_session.send_message(prompt)
                answer = response.text.strip()
                
                # ★★★ 修正箇所 2: アバター適用 (音声入力応答) ★★★
                with st.chat_message("assistant", avatar=AI_AVATAR):
                    st.markdown(answer)
                    play_tts(answer)
                # ★★★ 修正箇所 2 終了 ★★★

        else:
            st.warning("音声からテキストを認識できませんでした。もう一度お話しください。")
            
    except requests.exceptions.RequestException as e:
        st.error(f"音声認識API呼び出しエラーが発生しました: {e}")
    except Exception as e:
        st.error(f"音声処理中に予期せぬエラーが発生しました: {e}")


# ===================== テキスト入力 =====================
prompt_text = st.chat_input("✍️ 質問を入力してください（または上で話しかけてね）", key="text_input_key")

if prompt_text:
    
    # ユーザーメッセージを履歴に追加・表示
    st.session_state.chat_session.send_message(prompt_text)
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt_text)

    # ==== Geminiチャット応答 ====
    with st.spinner("ユッキーが考え中..."):
        response = st.session_state.chat_session.send_message(prompt_text)
        answer = response.text.strip()
        
        # ★★★ 修正箇所 3: アバター適用 (テキスト入力応答) ★★★
        with st.chat_message("assistant", avatar=AI_AVATAR):
            st.markdown(answer)
            play_tts(answer)
        # ★★★ 修正箇所 3 終了 ★★★

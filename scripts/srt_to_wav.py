#!/usr/bin/env python3
import io
import os
import wave
import pysrt
import pyopenjtalk
import requests
from pydub import AudioSegment
from piper import PiperVoice
from tap import Tap
from typing import Literal
from functools import partial


class Args(Tap):
    input_srt: str
    output_wav: str
    model_file: str = None
    config_file: str = None
    lang: Literal["ja", "en", "openai"] = "en"

def synthesize_text_piper(voice: PiperVoice, text, length_scale=0.75):
    """
    PiperVoice を使ってテキストから音声合成し、
    合成結果の WAV データを pydub.AudioSegment として返す。
    """
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)       # モノラル
        w.setsampwidth(2)       # 16bit
        w.setframerate(22050)   # サンプルレート（必要に応じて調整）
        voice.synthesize(text, w, length_scale=length_scale)
    buf.seek(0)
    segment = AudioSegment.from_file(buf, format="wav")
    return segment

def synthesize_text_openjtalk(text, speed=1.25):
    """
    pyopenjtalk を使って日本語テキストから音声合成し、
    合成結果の WAV データを pydub.AudioSegment として返す。
    """
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)       # モノラル 
        w.setsampwidth(2)       # 16bit
        # pyopenjtalk.tts は (wave_data, sample_rate) を返す
        x, sr = pyopenjtalk.tts(text, speed=speed)
        w.setframerate(sr)      # 実際のサンプルレートを設定
        w.writeframes(x.astype('int16').tobytes())
    buf.seek(0)
    segment = AudioSegment.from_file(buf, format="wav")
    return segment

def synthesize_text_openai(text, api_key):
    """
    OpenAI の TTS API を使ってテキストから音声合成し、
    合成結果の WAV データを pydub.AudioSegment として返す。
    "voice" は固定で "fable" とする。
    """
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "tts-1",
        "input": text,
        "voice": "fable",
        "response_format": "wav",
        "speed": 1.25
    }
    response = requests.post("https://api.openai.com/v1/audio/speech", headers=headers, json=data)
    response.raise_for_status()
    audio = b""
    for chunk in response.iter_content(chunk_size=1024*1024):
        audio += chunk
    segment = AudioSegment.from_file(io.BytesIO(audio), format="wav")
    return segment

def main(args: Args):
    if not os.path.exists(args.input_srt):
        print(f"入力ファイル {args.input_srt} が見つかりません。")
        return
    
    # TTSモードに応じた合成関数の切り替え
    if args.lang.lower() == "ja":
        tts_func = lambda text: synthesize_text_openjtalk(text, speed=1.25)
        print("日本語 (openjtalk) モードで合成します。")
    elif args.lang.lower() == "openai":
        tts_func = lambda text: synthesize_text_openai(text, api_key=os.getenv("OPENAI_API_KEY"))
        print("OpenAI TTS モードで合成します。")
    else:  # "en" などのPiperVoiceモード
        if not args.model_file:
            raise ValueError("PiperVoiceモードでは --model_file が必須です。")
        # config_file はオプション
        if args.config_file:
            voice = PiperVoice.load(args.model_file, args.config_file)
        else:
            voice = PiperVoice.load(args.model_file)
        tts_func = lambda text: synthesize_text_piper(voice, text, length_scale=0.75)

        print("PiperVoice モードで合成します。")

    # pysrt を用いて SRT ファイルをパース（字幕ブロックを取得）
    subs = pysrt.open(args.input_srt, encoding="utf-8")
    if len(subs) == 0:
        print("SRT ファイルから字幕が見つかりませんでした。")
        return

    # 出力全体の長さは、最後の字幕ブロックの終了時刻（ミリ秒）とする
    total_duration_ms = subs[-1].end.ordinal
    # 無音の AudioSegment を作成
    output_audio = AudioSegment.silent(duration=total_duration_ms)

    # 各字幕ブロックを処理する
    for i, sub in enumerate(subs):
        start_ms = sub.start.ordinal
        # 次の字幕ブロックがある場合は、allowed_duration を次の開始時刻との差とする
        if i < len(subs) - 1:
            allowed_duration = subs[i+1].start.ordinal - start_ms
        else:
            allowed_duration = sub.end.ordinal - start_ms
        
        # テキストを1行の文字列にまとめる（改行はスペースに置換）
        text = sub.text.replace('\n', ' ').strip()
        if not text:
            continue
        
        # TTS 合成
        synthesized = tts_func(text)
        # 合成された音声が許容時間を超える場合はトリミング
        if len(synthesized) > allowed_duration:
            synthesized = synthesized[:allowed_duration]
        
        # 発話が終わったら、次の発話開始まで無音になるよう、前の発話部分を置換する
        output_audio = output_audio[:start_ms] + synthesized + output_audio[start_ms+len(synthesized):]

    # 出力WAVファイルにエクスポート
    output_audio.export(args.output_wav, format="wav")
    print(f"音声合成結果を {args.output_wav} に保存しました。")

if __name__ == "__main__":
    args = Args().parse_args()
    main(args)

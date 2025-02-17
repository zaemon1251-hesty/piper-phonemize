#!/usr/bin/env python3
import deepl
import os
import io
import wave
import pysrt
import pyopenjtalk

from pydub import AudioSegment
from piper import PiperVoice
from tap import Tap
from typing import Literal
from functools import partial


DEEPL_API_KEY = os.environ.get('DEEPL_API_KEY')
translator = deepl.Translator(DEEPL_API_KEY)

# tapにする
class Args(Tap):
    model_file: str
    config_file: str = None
    input_srt: str
    output_wav: str
    lang: Literal["ja", "en"] = "en"


def preprocess_srt(subs: pysrt.SubRipFile):
    """
    deeplで英語を全て日本語にしておく
    """
    for sub in subs:
        sub.text = translator.translate_text(sub.text, target_lang="JA").text
    
    subs.save(args.input_srt)
    return subs

def synthesize_text(voice: PiperVoice, text):
    """
    PiperVoice を使ってテキストから音声合成し、
    合成結果の WAV データを pydub.AudioSegment として返す
    """
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)      # モノラル
        w.setsampwidth(2)      # 16bit (2 bytes)
        w.setframerate(22050)  # サンプルレート（必要に応じて調整）
        voice.synthesize(text, w, length_scale=0.75)
    buf.seek(0)
    segment = AudioSegment.from_file(buf, format="wav")
    return segment

def syntesize_text_openjtalk(text):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)      # モノラル
        w.setsampwidth(2)      # 16bit
        w.setframerate(22050)  # サンプルレート（必要に応じて調整）
        # pyopenjtalk.tts は (wave_data, sample_rate) を返す
        x, sr = pyopenjtalk.tts(text, speed=1.25)
        w.setframerate(sr) #  (22050のままになるはずだけど、一応)サンプルレート上書き
        w.writeframes(x.astype('int16').tobytes())
    buf.seek(0)
    segment = AudioSegment.from_file(buf, format="wav")
    return segment

def main(args: Args):
    # PiperVoice のモデルを、config_file を指定してロード
    voice = PiperVoice.load(args.model_file, args.config_file)

    # pysrt を用いて SRT ファイルをパース（字幕ブロックを取得）
    subs = pysrt.open(args.input_srt, encoding="utf-8")
    if len(subs) == 0:
        print("SRT ファイルから字幕が見つかりませんでした。")
        return
    
    func_syn = synthesize_text
    if args.lang == "ja":
        subs = preprocess_srt(subs)
        func_syn = syntesize_text_openjtalk
        print("Ja mode")
    else:
        func_syn = partial(synthesize_text, voice=voice)
        print("En mode")

    # 出力全体の長さは、最後の字幕ブロックの終了時刻（ミリ秒）とする
    total_duration_ms = subs[-1].end.ordinal
    # 無音の AudioSegment を作成
    output_audio = AudioSegment.silent(duration=total_duration_ms)

    # 各字幕ブロックを順次処理
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
        
        # テキストから音声を合成
        synthesized = func_syn(text)
        # 合成された音声が許容時間を超える場合はトリミング
        if len(synthesized) > allowed_duration:
            synthesized = synthesized[:allowed_duration]
        
        # 出力音声の該当部分を置き換える（無音部分を合成音声で上書き）
        output_audio = output_audio[:start_ms] + synthesized + output_audio[start_ms+len(synthesized):]

    # 出力WAVファイルにエクスポート
    output_audio.export(args.output_wav, format="wav")
    print(f"音声合成結果を {args.output_wav} に保存しました。")

if __name__ == "__main__":
    args = Args().parse_args()
    main(args)
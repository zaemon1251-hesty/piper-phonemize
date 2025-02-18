#!/bin/bash
# run_piper_from_srt.sh

export DYLD_LIBRARY_PATH="/Users/heste/piper-phonemize/install/lib/"

base_dir=/Users/heste/workspace/soccernet/sn-providing/outputs/demo-step2

# base_dir 以下の任意のサブディレクトリから commentary.srt を再帰的に探す
srt_files=("$base_dir"/**/commentary-full-en.srt)


# モデルファイルのパス
model_file="download/en_GB-northern_english_male-medium.onnx"

# 各 commentary.srt に対して処理を実行
for srt_file in "${srt_files[@]}"; do
    echo "Processing SRT: $srt_file"
    # SRT ファイルと同じディレクトリに WAV ファイルを生成（ファイル名は commentary.wav）
    srt_dir=$(dirname "$srt_file")
    wav_file="$srt_dir/commentary-full-en.wav"
    
    # Python スクリプトを呼び出して音声合成を実行
    /Users/heste/piper-phonemize/venv/bin/python3 scripts/srt_to_wav.py \
        --model_file "$model_file" \
        --input_srt "$srt_file" \
        --output_wav "$wav_file" \
        --config_file download/en_GB-northern_english_male-medium.onnx.json
done

echo "All done."
# R1 复跑入口

从仓库根目录执行，使用项目 Python 依赖、`jsonschema`、Noto CJK、FFmpeg 和 Chromium。工具目录来自本次审阅包或 GitHub。旧 48 cue 审阅 ZIP 解包到 `output/director-v1.0.2-visual-test/result`。同时保留该目录下的 ZIP 原件，复用校验读取它和已发布 SHA-256。

```bash
review=output/director-v1.0.2-visual-r1
old=output/director-v1.0.2-visual-test/result
base=b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb
runtime=67a8cc6740c521675f71c6c733997e429681c3a2
git fetch origin editorial/gpt-2015 ops/wf-02r1-2015-visual
mkdir -p "$review"/{inputs,runtime,result}
git archive "$runtime" src/chinext_v6 tools/render_editorial_preview.py \
  editorial/2015/releases/v1.0.1/director_timeline.schema.json \
  | tar -x -C "$review/runtime"
git archive "$base" editorial/2015/HANDOFF_TO_CODEX.md \
  editorial/2015/director/GPT_VISUAL_DECISIONS_V1.0.2.md \
  editorial/2015/director/EVENT_CLOCK_REGISTER_V1.0.2.json \
  editorial/2015/director/compiled/v1.0.2 docs/production/PROJECT-DASHBOARD.md \
  | tar -x -C "$review/inputs"
prior=editorial/2015/director/visual-tests/v1.0.2
git show "$base:$prior/candidate.json" > "$review/inputs/baseline_candidate.json"
git show "$base:$prior/manifest.json" > "$review/inputs/baseline_manifest.json"
git show "$base:$prior/execution_receipt.json" > "$review/inputs/baseline_receipt.json"
python3 -B "$review/work/prepare_r1.py" --runtime-root "$review/runtime" \
  --inputs "$review/inputs" --old-result "$old" --output "$review/result"
python3 -B "$review/work/record_r1_inputs.py" --root "$review"
python3 -B "$review/work/render_visual.py" --runtime-root "$review/runtime" \
  --candidate "$review/result/candidate.json" --legacy-dir "$review/result/legacy" \
  --out "$review/result" --all-blocks --pmi-stills --workers 4
python3 -B "$review/work/make_review_media.py" --result "$review/result" \
  --block B01-B02 --block B16-B18
python3 -B "$review/work/record_r1_inputs.py" --root "$review" --verify
python3 -B "$review/work/check_b08_reuse.py" --runtime "$review/runtime" \
  --result "$review/result" --baseline "$old"
python3 -B "$review/work/qa_visual.py" --result "$review/result" \
  --out "$review/result/independent_visual_qa.json"
python3 -B "$review/work/r1_motion_audit.py" --baseline-result "$old" \
  --result "$review/result" --out "$review/result/r1_motion_audit.json"
python3 -B "$review/work/compare_r1_media.py" --old "$old" --new "$review/result"
```

`--all-blocks` 指两段待重新编码的视频。B08–B10 的 44 秒既有视频经摘要核对后复用。实际播放记录可用 `node "$review/work/review_playback.mjs" <phone-390.mp4> <交付目录> <秒数>` 生成。浏览器 viewport 为 390×694，实播按 1×，逐帧运算和自动播放各自记录。

# 2026-04-02 PR Merge and Validation Record

## PRs merged and pushed in this batch

- `#837` `fix: update google-generativeai version for response_modalities support`
- `#835` `fix: add missing pydub dependency to requirements.txt`
- `#850` `feat: support reading subtitle position from config file`
- `#838` `feat: add MiniMax as LLM provider`
- `#811` `refactor: optimize codebase for better performance and reliability`
- `#848` `feat: support GPU acceleration for faster-whisper in Docker`
- `#843` `feat: Add Upload-Post integration for cross-posting to TikTok/Instagram`

## Mainline commits after the merge

- TTS and subtitle fix baseline commit: `953a6c0` `fix: restore edge tts synthesis and readable subtitles`
- Current mainline commit: `1f8a746`

## Validation conclusions at merge time

### Passed

- `#837`
  - Imports correctly after the dependency upgrade
  - `google-generativeai==0.8.6` is now in effect
- `#835`
  - `pydub==0.25.1` is now in effect
- `#850`
  - `subtitle_position` and `custom_position` can be read from the config file
- `#838`
  - MiniMax provider is wired up correctly
  - Validated `_generate_response` via mocked calls
- `#811`
  - Mainline imports are fine
  - Sampled unit tests pass
- `#848`
  - `docker compose -f docker-compose.yml -f docker-compose.gpu.yml config` parses correctly
- `#843`
  - Upload-Post service import and mocked upload calls pass
  - When stacked with the earlier PRs, the only conflict was a configuration section in `config.example.toml`, which was resolved manually by keeping both sides

### Rejected and closed

- `#852`
  - Restores audio, but breaks the subtitle pipeline and removes Gemini logic that is still called from the WebUI
- `#787`
  - Does not address the current `403` scenario
- `#841`
  - Conflicts with the current mainline TTS/subtitle fixes, and the benefits are already covered by smaller PRs
- `#824`
  - The ModelsLab path produces audio but the subtitle pipeline fails, so no usable SRT is produced
- `#840`
  - Adds `video_source="ai"` on the backend, but the WebUI still does not support that value, so the end-to-end flow is unusable
- `#826`
  - Conflicts with the current mainline `voice.py` and dependency changes; did not pass merge validation
- `#751`
- `#749`
- `#742`
- `#705`
  - The four PRs above are all `DIRTY` against the current mainline and did not pass merge validation

## Smoke-test record

### Services restart

- API: `http://127.0.0.1:8080/docs`
- WebUI: `http://127.0.0.1:8501`

### First end-to-end video task

- Task ID: `ced0b190-dd72-489c-b978-2761740933db`
- Result: failed
- Conclusion:
  - The API defaults `video_transition_mode` to `null`
  - During video concatenation, `app/services/video.py` accesses `video_transition_mode.value` directly
  - This caused the task thread to exit with an exception, leaving the task at `state=4, progress=75`

### Second end-to-end video task

- Task ID: `8b2a0e6e-b3e6-44ab-a1b4-1865a0b4788d`
- Submission:
  - `POST /api/v1/videos`
  - Used the local asset `/Users/harry/Projects/Python/VideoGenAI/test/resources/1.png`
  - Explicitly set `video_transition_mode="FadeIn"`
- Result: success
- Task state: `state=1, progress=100`

### Second task output

- Audio: `/Users/harry/Projects/Python/VideoGenAI/storage/tasks/8b2a0e6e-b3e6-44ab-a1b4-1865a0b4788d/audio.mp3`
  - Duration: `8.952s`
  - Size: `53712 bytes`
- Concatenated video: `/Users/harry/Projects/Python/VideoGenAI/storage/tasks/8b2a0e6e-b3e6-44ab-a1b4-1865a0b4788d/combined-1.mp4`
  - Duration: `9.000s`
  - Size: `177666 bytes`
- Final video: `/Users/harry/Projects/Python/VideoGenAI/storage/tasks/8b2a0e6e-b3e6-44ab-a1b4-1865a0b4788d/final-1.mp4`
  - Duration: `9.000s`
  - Size: `352810 bytes`
- Subtitles: `/Users/harry/Projects/Python/VideoGenAI/storage/tasks/8b2a0e6e-b3e6-44ab-a1b4-1865a0b4788d/subtitle.srt`

### Subtitle sample from the second task

Original captured output (Chinese script used in the test run). English gloss:
"This is a complete smoke test after the main-branch merge / we need to confirm
that voice / subtitles and the final video can all be generated normally."

```srt
1
00:00:00,100 --> 00:00:03,300
这是一次主线合并后的完整冒烟测试

2
00:00:03,875 --> 00:00:05,350
我们要确认语音

3
00:00:05,575 --> 00:00:08,375
字幕和视频成片都能正常生成
```

(Subtitle text is shown verbatim as it was produced by the run; English translation: "This is a full smoke test after the mainline merge / We want to confirm that voice / subtitles, and the final video are all generated correctly".)

## Risks still worth tracking

- `#843` was only validated with mocks; it has not yet been run end-to-end against a real Upload-Post API key.
- `#848` was only validated by parsing the Docker GPU configuration; it has not yet been run on real GPU hardware.
- When the API defaults `video_transition_mode` to `null`, full video tasks still carry a regression risk.

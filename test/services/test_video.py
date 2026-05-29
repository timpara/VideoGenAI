import unittest
import os
import shutil
import sys
import tempfile
import types
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from moviepy import (
    VideoFileClip,
)

# add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app.config import config
from app.controllers.manager.base_manager import TaskQueueFullError
from app.controllers.manager.memory_manager import InMemoryTaskManager
from app.controllers.v1 import video as video_controller
from app.models import const
from app.models.schema import MaterialInfo
from app.services import state as sm
from app.services import video as vd
from app.utils import utils

resources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources")


class _FakeRequest:
    def __init__(self):
        self.headers = {"x-task-id": "test-request"}


class TestSecurityControls(unittest.TestCase):
    def setUp(self):
        self.original_app_config = dict(config.app)

    def tearDown(self):
        config.app.clear()
        config.app.update(self.original_app_config)

    def test_task_query_returns_relative_task_url_without_mutating_state(self):
        """
        When endpoint is not explicitly configured, the task query API must
        not build an absolute URL from the Host header, and must not write
        the display URL back into the task state, otherwise queries from
        different hosts would pollute each other's results.
        """
        task_id = "security-task-url"
        task_dir = utils.task_dir(task_id)
        video_path = os.path.join(task_dir, "final-1.mp4")
        Path(video_path).write_bytes(b"fake-video")
        config.app["endpoint"] = ""

        try:
            sm.state.update_task(
                task_id,
                state=const.TASK_STATE_COMPLETE,
                videos=[video_path],
                combined_videos=[video_path],
            )

            response = video_controller.get_task(_FakeRequest(), task_id=task_id)

            self.assertEqual(
                response["data"]["videos"], [f"/tasks/{task_id}/final-1.mp4"]
            )
            self.assertEqual(sm.state.get_task(task_id)["videos"], [video_path])
        finally:
            sm.state.delete_task(task_id)
            shutil.rmtree(task_dir, ignore_errors=True)

    def test_in_memory_task_manager_rejects_when_queue_is_full(self):
        """
        Once the concurrency budget is exhausted, the waiting queue must
        have a hard ceiling. Here we force tasks into the queue with
        ``max_concurrent_tasks=0`` to verify that exceeding
        ``max_queued_tasks`` rejects further enqueue attempts.
        """
        manager = InMemoryTaskManager(max_concurrent_tasks=0, max_queued_tasks=1)

        manager.add_task(lambda: None)

        with self.assertRaises(TaskQueueFullError):
            manager.add_task(lambda: None)


class TestVideoService(unittest.TestCase):
    def setUp(self):
        self.test_img_path = os.path.join(resources_dir, "1.png")

    def tearDown(self):
        pass

    def test_preprocess_video(self):
        if not os.path.exists(self.test_img_path):
            self.fail(f"test image not found: {self.test_img_path}")

        local_videos_dir = utils.storage_dir("local_videos", create=True)
        safe_img_path = os.path.join(local_videos_dir, "test-preprocess-1.png")
        shutil.copy2(self.test_img_path, safe_img_path)

        # test preprocess_video function
        m = MaterialInfo()
        m.url = os.path.basename(safe_img_path)
        m.provider = "local"
        print(m)

        try:
            materials = vd.preprocess_video([m], clip_duration=4)
            print(materials)

            # verify result
            self.assertIsNotNone(materials)
            self.assertEqual(len(materials), 1)
            self.assertTrue(materials[0].url.endswith(".mp4"))

            # moviepy get video info
            clip = VideoFileClip(materials[0].url)
            try:
                print(clip)
            finally:
                clip.close()

            # clean generated test video file
            if os.path.exists(materials[0].url):
                os.remove(materials[0].url)
        finally:
            if os.path.exists(safe_img_path):
                os.remove(safe_img_path)

    def test_preprocess_video_rejects_material_outside_local_videos(self):
        """
        Local material paths come from API parameters, so arbitrary absolute
        paths must not be allowed into MoviePy. This verifies that paths
        outside the ``local_videos`` allowlist directory are skipped to
        prevent arbitrary file reads.
        """
        m = MaterialInfo(provider="local", url=self.test_img_path)

        materials = vd.preprocess_video([m], clip_duration=4)

        self.assertEqual(materials, [])

    def test_get_bgm_file_accepts_song_directory_filename(self):
        """
        The BGM list API now exposes only the filename. When generating a
        video, the code must safely resolve the filename back into the
        ``resource/songs`` allowlist directory so normal usage still works.
        """
        song_dir = utils.song_dir()
        bgm_path = os.path.join(song_dir, "test-safe-bgm.mp3")
        Path(bgm_path).write_bytes(b"fake-mp3")

        try:
            self.assertEqual(vd.get_bgm_file(bgm_file="test-safe-bgm.mp3"), bgm_path)
        finally:
            if os.path.exists(bgm_path):
                os.remove(bgm_path)

    def test_get_bgm_file_rejects_path_outside_song_directory(self):
        """
        A user-supplied ``bgm_file`` must not be opened directly as a local
        path, otherwise arbitrary system files could be read. Even when an
        external file exists, it must be rejected because it sits outside
        the songs directory.
        """
        with tempfile.NamedTemporaryFile(suffix=".mp3") as temp_bgm:
            self.assertEqual(vd.get_bgm_file(bgm_file=temp_bgm.name), "")

    def test_get_ffmpeg_binary_uses_configured_env_path(self):
        """When ffmpeg is explicitly configured, that path must take priority."""
        with patch.dict(
            os.environ, {"IMAGEIO_FFMPEG_EXE": "/tmp/custom-ffmpeg"}, clear=True
        ):
            self.assertEqual(vd.get_ffmpeg_binary(), "/tmp/custom-ffmpeg")

    def test_get_ffmpeg_binary_falls_back_to_imageio_ffmpeg(self):
        """
        On the Windows portable bundle, the system PATH may not contain
        ffmpeg, but moviepy's dependency ``imageio-ffmpeg`` usually ships an
        executable. This verifies that fallback path works.
        """
        fake_imageio_ffmpeg = types.SimpleNamespace(
            get_ffmpeg_exe=lambda: "/tmp/bundled-ffmpeg"
        )

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(vd.shutil, "which", return_value=None),
            patch.dict(sys.modules, {"imageio_ffmpeg": fake_imageio_ffmpeg}),
        ):
            self.assertEqual(vd.get_ffmpeg_binary(), "/tmp/bundled-ffmpeg")

    def test_open_video_clip_quietly_suppresses_moviepy_stdout(self):
        """
        MoviePy 2.1.x's ``FFMPEG_VideoReader`` prints metadata and the
        ffmpeg command directly to stdout. The service layer should suppress
        this dependency noise so users do not misread ``audio_found: False``
        as the final video lacking audio.
        """
        video_path = os.path.join(resources_dir, "1.png.mp4")
        if not os.path.exists(video_path):
            self.fail(f"test video not found: {video_path}")

        stdout = StringIO()
        with redirect_stdout(stdout):
            clip = vd._open_video_clip_quietly(video_path)

        try:
            self.assertEqual(stdout.getvalue(), "")
            self.assertIsNone(clip.audio)
            self.assertGreater(clip.duration, 0)
        finally:
            vd.close_clip(clip)

    def test_combine_videos_closes_audio_clip_when_duration_read_fails(self):
        """
        ``combine_videos()`` only needs to read the narration audio
        duration. Even when reading the duration raises an exception, the
        ``AudioFileClip`` must still be closed to avoid leaking the file
        handle.
        """

        class _FakeAudioReader:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class _BrokenAudioClip:
            def __init__(self):
                self.reader = _FakeAudioReader()

            @property
            def duration(self):
                raise RuntimeError("failed to read duration")

        fake_audio_clip = _BrokenAudioClip()

        with patch.object(vd, "AudioFileClip", return_value=fake_audio_clip):
            with self.assertRaises(RuntimeError):
                vd.combine_videos(
                    combined_video_path="/tmp/unused-combined.mp4",
                    video_paths=[],
                    audio_file="/tmp/unused-audio.mp3",
                )

        self.assertTrue(fake_audio_clip.reader.closed)

    def test_combine_videos_handles_none_transition_mode(self):
        """
        Ensure `combine_videos` safely handles
        `video_transition_mode=None`.
        """

        class _FakeAudioClip:
            @property
            def duration(self):
                return 10.0

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            combined_video_path = os.path.join(temp_dir, "combined.mp4")
            audio_file = os.path.join(temp_dir, "audio.mp3")

            with patch.object(vd, "AudioFileClip", return_value=_FakeAudioClip()):
                # Use empty video_paths to avoid heavy video processing while
                # still exercising transition mode normalization logic.
                result = vd.combine_videos(
                    combined_video_path=combined_video_path,
                    video_paths=[],
                    audio_file=audio_file,
                    video_transition_mode=None,
                )
                self.assertEqual(result, combined_video_path)

    def test_wrap_text(self):
        """test text wrapping function"""
        try:
            font_path = os.path.join(utils.font_dir(), "STHeitiMedium.ttc")
            if not os.path.exists(font_path):
                self.fail(f"font file not found: {font_path}")

            # test english text wrapping
            test_text_en = (
                "This is a test text for wrapping long sentences in english language"
            )

            wrapped_text_en, text_height_en = vd.wrap_text(
                text=test_text_en, max_width=300, font=font_path, fontsize=30
            )
            print(wrapped_text_en, text_height_en)
            # verify text is wrapped
            self.assertIn("\n", wrapped_text_en)

            # test chinese text wrapping
            test_text_zh = (
                "这是一段用来测试中文长句换行的文本内容，应该会根据宽度限制进行换行处理"
            )
            wrapped_text_zh, text_height_zh = vd.wrap_text(
                text=test_text_zh, max_width=300, font=font_path, fontsize=30
            )
            print(wrapped_text_zh, text_height_zh)
            # verify chinese text is wrapped
            self.assertIn("\n", wrapped_text_zh)
        except Exception as e:
            self.fail(f"test wrap_text failed: {str(e)}")


if __name__ == "__main__":
    unittest.main()

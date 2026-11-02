# Media Embed

- **video_crf** — quality of auto-converted video (lower = better/larger, higher = smaller/faster). 30–38 is a good range; default 34.
- **youtube_privacy_mode** — `true` uses `youtube-nocookie.com`. Default `false` uses `youtube.com`, which lets more videos embed (nocookie refuses some).

Why conversion happens: Anki's card webview can't decode H.264/MP4 or AAC/M4A (black video / no sound). On attach, those are converted once to AV1 WebM / Ogg Vorbis, which the webview plays inline. WebM, VP9/AV1, MP3, Ogg, WAV and FLAC are embedded as-is.

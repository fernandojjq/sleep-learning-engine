"""CustomTkinter-based dark-mode desktop studio."""

from __future__ import annotations

import threading
import tkinter as tk
import traceback
from pathlib import Path

import customtkinter as ctk

from ..config import (
    AIProvider,
    AmbientMode,
    AppSettings,
    OutputPreset,
    PROVIDER_PRESETS,
    ProjectPaths,
    TTSBackend,
    load_settings,
    save_settings,
)
from ..core import SleeplensError, run_render
from ..core.state import RenderEvent, RenderStage, RenderStatus
from ..utils.logging import configure_logging, get_logger

log = get_logger()


# --------------------------------------------------------------- palette

PALETTE = {
    "bg": "#0B0D12",
    "panel": "#11141B",
    "panel_alt": "#161A22",
    "border": "#1F2430",
    "text": "#E5E7EB",
    "muted": "#9CA3AF",
    "accent": "#7C3AED",
    "accent_alt": "#22D3EE",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "progress": "#00FF00",
}


# --------------------------------------------------------------- launch


def launch(paths: ProjectPaths) -> None:
    """Start the desktop studio."""
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    settings = load_settings(paths.config_file)
    app = StudioApp(settings, paths)
    app.mainloop()


# --------------------------------------------------------------- widgets


class StudioApp(ctk.CTk):
    """The main application window."""

    def __init__(self, settings: AppSettings, paths: ProjectPaths) -> None:
        super().__init__()
        self.settings = settings
        self.paths = paths
        self._job_thread: threading.Thread | None = None
        self._cancel_flag = threading.Event()

        self.title("Sleeplens · Sleep Learning Video Studio")
        self.geometry("1180x820")
        self.minsize(1024, 720)
        self.configure(fg_color=PALETTE["bg"])

        self._build_layout()
        self._hydrate_from_settings()

    # ------------------------------------------------------------- layout
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, fg_color=PALETTE["panel"], corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        sidebar.grid_rowconfigure(4, weight=1)
        self._build_sidebar(sidebar)

        main = ctk.CTkFrame(self, fg_color=PALETTE["bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)
        self._build_main(main)

    def _build_sidebar(self, parent: ctk.CTkFrame) -> None:
        header = ctk.CTkLabel(
            parent,
            text="SLEEPLENS",
            font=("Inter", 22, "bold"),
            text_color=PALETTE["text"],
        )
        header.grid(row=0, column=0, padx=24, pady=(28, 4), sticky="w")
        subheader = ctk.CTkLabel(
            parent,
            text="Sleep Learning Video Studio",
            font=("Inter", 12),
            text_color=PALETTE["muted"],
        )
        subheader.grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")

        self.nav_indicator = ctk.CTkLabel(
            parent,
            text="",
            font=("Inter", 12, "bold"),
            text_color=PALETTE["accent_alt"],
        )
        self.nav_indicator.grid(row=2, column=0, padx=24, pady=(0, 12), sticky="w")

        self.status_label = ctk.CTkLabel(
            parent,
            text="Ready.",
            font=("Inter", 12),
            text_color=PALETTE["muted"],
            wraplength=260,
            justify="left",
        )
        self.status_label.grid(row=5, column=0, padx=24, pady=(0, 24), sticky="swe")

        self.render_button = ctk.CTkButton(
            parent,
            text="Render video",
            font=("Inter", 14, "bold"),
            fg_color=PALETTE["accent"],
            hover_color="#6D28D9",
            height=44,
            corner_radius=10,
            command=self._on_render_clicked,
        )
        self.render_button.grid(row=6, column=0, padx=24, pady=(0, 12), sticky="ew")

        self.cancel_button = ctk.CTkButton(
            parent,
            text="Cancel",
            font=("Inter", 13),
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["border"],
            text_color=PALETTE["text"],
            height=36,
            corner_radius=8,
            state="disabled",
            command=self._on_cancel_clicked,
        )
        self.cancel_button.grid(row=7, column=0, padx=24, pady=(0, 24), sticky="ew")

    def _build_main(self, parent: ctk.CTkFrame) -> None:
        self.tabs = ctk.CTkTabview(
            parent,
            fg_color=PALETTE["panel"],
            segmented_button_fg_color=PALETTE["panel_alt"],
            segmented_button_selected_color=PALETTE["accent"],
            segmented_button_selected_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        )
        self.tabs.grid(row=0, column=0, sticky="nsew")
        self.tabs.add("Topic")
        self.tabs.add("Provider")
        self.tabs.add("Visuals")
        self.tabs.add("Audio")
        self.tabs.add("Render")

        self._build_topic_tab(self.tabs.tab("Topic"))
        self._build_provider_tab(self.tabs.tab("Provider"))
        self._build_visual_tab(self.tabs.tab("Visuals"))
        self._build_audio_tab(self.tabs.tab("Audio"))
        self._build_render_tab(self.tabs.tab("Render"))

    # ----------------------------------------------------------- tab: topic
    def _build_topic_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="Topic",
            font=("Inter", 18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        self.topic_text = ctk.CTkTextbox(
            parent,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            border_width=1,
            font=("Inter", 13),
            wrap="word",
        )
        self.topic_text.grid(row=1, column=0, padx=20, pady=8, sticky="nsew")

        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.grid(row=2, column=0, padx=20, pady=(8, 20), sticky="ew")
        controls.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(controls, text="Language", text_color=PALETTE["muted"]).grid(
            row=0, column=0, padx=8, sticky="w"
        )
        self.language_var = tk.StringVar(value="en")
        ctk.CTkOptionMenu(
            controls,
            values=["en", "es", "pt", "fr", "de", "it", "ja", "zh"],
            variable=self.language_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=1, column=0, padx=8, pady=4, sticky="ew")

        ctk.CTkLabel(controls, text="Target word count", text_color=PALETTE["muted"]).grid(
            row=0, column=1, padx=8, sticky="w"
        )
        self.wordcount_var = tk.StringVar(value="4500")
        ctk.CTkEntry(
            controls,
            textvariable=self.wordcount_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
        ).grid(row=1, column=1, padx=8, pady=4, sticky="ew")

        ctk.CTkLabel(controls, text="Pause between paragraphs (s)", text_color=PALETTE["muted"]).grid(
            row=0, column=2, padx=8, sticky="w"
        )
        self.pause_var = tk.StringVar(value="1.8")
        ctk.CTkEntry(
            controls,
            textvariable=self.pause_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
        ).grid(row=1, column=2, padx=8, pady=4, sticky="ew")

        script_row = ctk.CTkFrame(parent, fg_color="transparent")
        script_row.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        script_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(script_row, text="Or load a script file", text_color=PALETTE["muted"]).grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        self.script_path_var = tk.StringVar()
        ctk.CTkEntry(
            script_row,
            textvariable=self.script_path_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            placeholder_text="path/to/script.txt (optional)",
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            script_row,
            text="Browse…",
            width=96,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["border"],
            text_color=PALETTE["text"],
            command=self._browse_script,
        ).grid(row=0, column=2, padx=(8, 0))

    # ---------------------------------------------------------- tab: provider
    def _build_provider_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="AI Provider",
            font=("Inter", 18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        preset_labels = [p.label for p in PROVIDER_PRESETS]
        self.provider_label_var = tk.StringVar(value=preset_labels[0])
        ctk.CTkOptionMenu(
            parent,
            values=preset_labels,
            variable=self.provider_label_var,
            command=self._on_provider_changed,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=1, column=0, padx=20, pady=4, sticky="ew")

        self.provider_notes = ctk.CTkLabel(
            parent,
            text="",
            text_color=PALETTE["muted"],
            justify="left",
            wraplength=700,
        )
        self.provider_notes.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="w")

        form = ctk.CTkFrame(parent, fg_color="transparent")
        form.grid(row=3, column=0, padx=20, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        self.base_url_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.temperature_var = tk.StringVar(value="0.7")
        self.max_tokens_var = tk.StringVar(value="4096")
        self.max_retries_var = tk.StringVar(value="6")
        self.timeout_var = tk.StringVar(value="120")

        for row, (label, var) in enumerate(
            [
                ("Base URL", self.base_url_var),
                ("API key", self.api_key_var),
                ("Model", self.model_var),
                ("Temperature", self.temperature_var),
                ("Max tokens", self.max_tokens_var),
                ("Max retries", self.max_retries_var),
                ("Request timeout (s)", self.timeout_var),
            ]
        ):
            ctk.CTkLabel(form, text=label, text_color=PALETTE["muted"]).grid(
                row=row, column=0, padx=8, pady=6, sticky="w"
            )
            ctk.CTkEntry(
                form,
                textvariable=var,
                fg_color=PALETTE["panel_alt"],
                text_color=PALETTE["text"],
                border_color=PALETTE["border"],
                show="•" if label == "API key" else "",
            ).grid(row=row, column=1, padx=8, pady=6, sticky="ew")

        models_row = ctk.CTkFrame(parent, fg_color="transparent")
        models_row.grid(row=4, column=0, padx=20, pady=(4, 20), sticky="ew")
        ctk.CTkButton(
            models_row,
            text="Load model list",
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["border"],
            text_color=PALETTE["text"],
            command=self._on_load_models,
        ).pack(side="left")
        self.models_label = ctk.CTkLabel(
            models_row, text="(no model list fetched yet)", text_color=PALETTE["muted"]
        )
        self.models_label.pack(side="left", padx=12)

    # ----------------------------------------------------------- tab: visuals
    def _build_visual_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="Background",
            font=("Inter", 18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

        img_row = ctk.CTkFrame(parent, fg_color="transparent")
        img_row.grid(row=1, column=0, padx=20, pady=4, sticky="ew")
        img_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(img_row, text="Image", text_color=PALETTE["muted"], width=90).grid(
            row=0, column=0, padx=8, sticky="w"
        )
        self.bg_image_var = tk.StringVar()
        ctk.CTkEntry(
            img_row,
            textvariable=self.bg_image_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            placeholder_text="path/to/background.png (or leave empty)",
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            img_row, text="Browse…", width=96, command=lambda: self._browse_file(self.bg_image_var, "image")
        ).grid(row=0, column=2, padx=(8, 0))

        vid_row = ctk.CTkFrame(parent, fg_color="transparent")
        vid_row.grid(row=2, column=0, padx=20, pady=4, sticky="ew")
        vid_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(vid_row, text="Video loop", text_color=PALETTE["muted"], width=90).grid(
            row=0, column=0, padx=8, sticky="w"
        )
        self.bg_video_var = tk.StringVar()
        ctk.CTkEntry(
            vid_row,
            textvariable=self.bg_video_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            placeholder_text="path/to/background.mp4 (optional, will loop)",
        ).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            vid_row, text="Browse…", width=96, command=lambda: self._browse_file(self.bg_video_var, "video")
        ).grid(row=0, column=2, padx=(8, 0))

        note = ctk.CTkLabel(
            parent,
            text=(
                "Tip: drop your favourite royalty-free clips into "
                "assets/visuals/. If both fields are empty, a dark, sleep-friendly "
                "backdrop is generated automatically."
            ),
            text_color=PALETTE["muted"],
            justify="left",
            wraplength=720,
        )
        note.grid(row=3, column=0, padx=20, pady=12, sticky="w")

        ctk.CTkLabel(parent, text="Drop files here", text_color=PALETTE["muted"]).grid(
            row=4, column=0, padx=20, pady=(20, 0), sticky="w"
        )
        drop_zone = ctk.CTkFrame(
            parent,
            fg_color=PALETTE["panel_alt"],
            border_color=PALETTE["border"],
            border_width=2,
            corner_radius=12,
            height=140,
        )
        drop_zone.grid(row=5, column=0, padx=20, pady=8, sticky="nsew")
        drop_zone.grid_propagate(False)
        ctk.CTkLabel(
            drop_zone,
            text="Drag an image or video here to use it as the background.\n"
            "Supported: PNG, JPG, WEBP, MP4, MOV, MKV, WEBM",
            text_color=PALETTE["muted"],
            justify="center",
        ).place(relx=0.5, rely=0.5, anchor="center")

        # Optional: try to enable drag-and-drop (only when tkinterdnd2 is installed).
        self._enable_dnd(drop_zone)

    def _enable_dnd(self, frame: ctk.CTkFrame) -> None:
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore[import-not-found]
        except ImportError:
            return
        try:
            self.tk.call("tk", "scaling", 1.0)
            # CustomTkinter's CTkFrame inherits from tk.Frame, so it can act as a drop target.
            frame.drop_target_register(DND_FILES)
            frame.dnd_bind("<<Drop>>", lambda event: self._on_drop(event))
        except Exception:  # noqa: BLE001
            log.debug("Drag-and-drop not enabled in this environment.")

    def _on_drop(self, event) -> None:
        try:
            from tkinterdnd2 import TkinterDnD  # type: ignore[import-not-found]

            data = event.data
            if isinstance(data, str):
                path_str = data.strip("{}")
            else:
                path_str = data[0].strip("{}") if data else ""
            path = Path(path_str)
            suffix = path.suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
                self.bg_image_var.set(str(path))
            elif suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
                self.bg_video_var.set(str(path))
            else:
                self.status_label.configure(text=f"Unrecognized dropped file: {path.name}")
        except Exception as exc:  # noqa: BLE001
            log.warning("Drop handler failed: {}", exc)

    # ------------------------------------------------------------- tab: audio
    def _build_audio_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            parent, text="Text-to-speech", font=("Inter", 18, "bold"), text_color=PALETTE["text"]
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 8), sticky="w")

        self.tts_backend_var = tk.StringVar(value=TTSBackend.EDGE.value)
        ctk.CTkOptionMenu(
            parent,
            values=[b.value for b in TTSBackend],
            variable=self.tts_backend_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=1, column=0, padx=20, pady=4, sticky="ew")

        self.tts_voice_var = tk.StringVar(value="en-US-AriaNeural")
        ctk.CTkEntry(
            parent,
            textvariable=self.tts_voice_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            placeholder_text="Edge voice id (e.g. en-US-AriaNeural)",
        ).grid(row=1, column=1, padx=20, pady=4, sticky="ew")

        tts_row = ctk.CTkFrame(parent, fg_color="transparent")
        tts_row.grid(row=2, column=0, columnspan=2, padx=20, pady=4, sticky="ew")
        tts_row.grid_columnconfigure((0, 1), weight=1)
        self.tts_rate_var = tk.StringVar(value="-5%")
        ctk.CTkEntry(tts_row, textvariable=self.tts_rate_var, placeholder_text="rate (e.g. -10%)").grid(
            row=0, column=0, padx=8, pady=4, sticky="ew"
        )
        self.tts_pitch_var = tk.StringVar(value="-2Hz")
        ctk.CTkEntry(tts_row, textvariable=self.tts_pitch_var, placeholder_text="pitch (e.g. -2Hz)").grid(
            row=0, column=1, padx=8, pady=4, sticky="ew"
        )

        ctk.CTkLabel(
            parent, text="Ambient bed", font=("Inter", 18, "bold"), text_color=PALETTE["text"]
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=(20, 8), sticky="w")

        self.ambient_mode_var = tk.StringVar(value=AmbientMode.AUTO.value)
        ctk.CTkOptionMenu(
            parent,
            values=[m.value for m in AmbientMode],
            variable=self.ambient_mode_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=4, column=0, padx=20, pady=4, sticky="ew")

        ambient_row = ctk.CTkFrame(parent, fg_color="transparent")
        ambient_row.grid(row=4, column=1, padx=20, pady=4, sticky="ew")
        ambient_row.grid_columnconfigure((0, 1), weight=1)
        self.ambient_volume_var = tk.StringVar(value="0.18")
        ctk.CTkEntry(ambient_row, textvariable=self.ambient_volume_var, placeholder_text="bed volume (0-1)").grid(
            row=0, column=0, padx=8, pady=4, sticky="ew"
        )
        self.ambient_duck_var = tk.StringVar(value="12")
        ctk.CTkEntry(ambient_row, textvariable=self.ambient_duck_var, placeholder_text="duck amount (dB)").grid(
            row=0, column=1, padx=8, pady=4, sticky="ew"
        )

        ctk.CTkLabel(
            parent,
            text=(
                "Drop royalty-free loops (rain, lofi, alpha waves…) into "
                "assets/ambient/. The studio picks the best match for your script."
            ),
            text_color=PALETTE["muted"],
            justify="left",
            wraplength=720,
        ).grid(row=5, column=0, columnspan=2, padx=20, pady=12, sticky="w")

    # ------------------------------------------------------------- tab: render
    def _build_render_tab(self, parent: ctk.CTkFrame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            parent, text="Output", font=("Inter", 18, "bold"), text_color=PALETTE["text"]
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 8), sticky="w")

        self.preset_var = tk.StringVar(value=OutputPreset.SLEEP_720P.value)
        ctk.CTkOptionMenu(
            parent,
            values=[p.value for p in OutputPreset],
            variable=self.preset_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=1, column=0, padx=20, pady=4, sticky="ew")

        self.hw_var = tk.StringVar(value="auto")
        ctk.CTkOptionMenu(
            parent,
            values=["auto", "nvenc", "qsv", "amf", "libx264"],
            variable=self.hw_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=1, column=1, padx=20, pady=4, sticky="ew")

        size_row = ctk.CTkFrame(parent, fg_color="transparent")
        size_row.grid(row=2, column=0, columnspan=2, padx=20, pady=4, sticky="ew")
        size_row.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.fps_var = tk.StringVar(value="24")
        self.threads_var = tk.StringVar(value="0")
        self.bar_height_var = tk.StringVar(value="6")
        self.bar_position_var = tk.StringVar(value="bottom")
        ctk.CTkEntry(size_row, textvariable=self.fps_var, placeholder_text="fps").grid(
            row=0, column=0, padx=8, pady=4, sticky="ew"
        )
        ctk.CTkEntry(size_row, textvariable=self.threads_var, placeholder_text="threads (0=auto)").grid(
            row=0, column=1, padx=8, pady=4, sticky="ew"
        )
        ctk.CTkEntry(size_row, textvariable=self.bar_height_var, placeholder_text="bar height (px)").grid(
            row=0, column=2, padx=8, pady=4, sticky="ew"
        )
        ctk.CTkOptionMenu(
            size_row,
            values=["top", "bottom"],
            variable=self.bar_position_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            text_color=PALETTE["text"],
        ).grid(row=0, column=3, padx=8, pady=4, sticky="ew")

        ctk.CTkLabel(
            parent,
            text="The green progress bar (#00FF00) advances frame-by-frame so it always matches the timeline.",
            text_color=PALETTE["muted"],
            wraplength=720,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=12, sticky="w")

        self.progress = ctk.CTkProgressBar(
            parent,
            fg_color=PALETTE["panel_alt"],
            progress_color=PALETTE["progress"],
            height=10,
        )
        self.progress.set(0)
        self.progress.grid(row=4, column=0, columnspan=2, padx=20, pady=(0, 12), sticky="ew")

        self.log_box = ctk.CTkTextbox(
            parent,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            border_width=1,
            font=("JetBrains Mono", 11),
            height=200,
        )
        self.log_box.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="nsew")
        parent.grid_rowconfigure(5, weight=1)
        self.log_box.configure(state="disabled")

    # -------------------------------------------------------------- hydration
    def _hydrate_from_settings(self) -> None:
        s = self.settings
        preset_idx = 0
        for i, p in enumerate(PROVIDER_PRESETS):
            if p.id == s.provider_id:
                preset_idx = i
                break
        self.provider_label_var.set(PROVIDER_PRESETS[preset_idx].label)
        self._on_provider_changed(PROVIDER_PRESETS[preset_idx].label)
        self.base_url_var.set(s.base_url)
        self.model_var.set(s.model)
        self.temperature_var.set(str(s.temperature))
        self.max_tokens_var.set(str(s.max_tokens))
        self.max_retries_var.set(str(s.max_retries))
        self.timeout_var.set(str(s.request_timeout))
        self.topic_text.insert("1.0", s.script_topic)
        self.script_path_var.set(s.script_file)
        self.bg_image_var.set(s.background_image)
        self.bg_video_var.set(s.background_video)
        self.wordcount_var.set(str(s.target_word_count))
        self.pause_var.set(str(s.pause_between_paragraphs))
        self.language_var.set(s.language)
        self.tts_backend_var.set(s.tts_backend.value)
        self.tts_voice_var.set(s.tts_voice)
        self.tts_rate_var.set(s.tts_rate)
        self.tts_pitch_var.set(s.tts_pitch)
        self.ambient_mode_var.set(s.ambient_mode.value)
        self.ambient_volume_var.set(str(s.ambient_volume))
        self.ambient_duck_var.set(str(s.ambient_duck_db))
        self.preset_var.set(s.output_preset.value)
        self.hw_var.set(s.hardware_accel)
        self.fps_var.set(str(s.video_fps))
        self.threads_var.set(str(s.render_threads))
        self.bar_height_var.set(str(s.progress_bar_height))
        self.bar_position_var.set(s.progress_bar_position)

    def _collect_settings(self) -> AppSettings:
        s = AppSettings(**self.settings.__dict__)
        preset = self._current_preset()
        s.provider_id = preset.id
        s.base_url = self.base_url_var.get().strip() or preset.base_url
        s.model = self.model_var.get().strip() or preset.default_model
        s.api_key = self.api_key_var.get().strip()
        try:
            s.temperature = float(self.temperature_var.get() or "0.7")
            s.max_tokens = int(self.max_tokens_var.get() or "4096")
            s.max_retries = int(self.max_retries_var.get() or "6")
            s.request_timeout = float(self.timeout_var.get() or "120")
            s.target_word_count = int(self.wordcount_var.get() or "4500")
            s.pause_between_paragraphs = float(self.pause_var.get() or "1.8")
            s.ambient_volume = float(self.ambient_volume_var.get() or "0.18")
            s.ambient_duck_db = float(self.ambient_duck_var.get() or "12")
            s.video_fps = int(self.fps_var.get() or "24")
            s.render_threads = int(self.threads_var.get() or "0")
            s.progress_bar_height = int(self.bar_height_var.get() or "6")
        except ValueError as exc:
            raise SleeplensError(f"Invalid number in form: {exc}") from exc
        s.script_topic = self.topic_text.get("1.0", "end").strip()
        s.script_file = self.script_path_var.get().strip()
        s.background_image = self.bg_image_var.get().strip()
        s.background_video = self.bg_video_var.get().strip()
        s.language = self.language_var.get().strip() or "en"
        s.tts_backend = TTSBackend(self.tts_backend_var.get())
        s.tts_voice = self.tts_voice_var.get().strip() or "en-US-AriaNeural"
        s.tts_rate = self.tts_rate_var.get().strip() or "-5%"
        s.tts_pitch = self.tts_pitch_var.get().strip() or "-2Hz"
        s.ambient_mode = AmbientMode(self.ambient_mode_var.get())
        s.output_preset = OutputPreset(self.preset_var.get())
        s.hardware_accel = self.hw_var.get()
        s.progress_bar_position = self.bar_position_var.get()
        return s

    def _current_preset(self):
        label = self.provider_label_var.get()
        for p in PROVIDER_PRESETS:
            if p.label == label:
                return p
        return PROVIDER_PRESETS[0]

    # ------------------------------------------------------------ handlers
    def _on_provider_changed(self, label: str) -> None:
        preset = next((p for p in PROVIDER_PRESETS if p.label == label), PROVIDER_PRESETS[0])
        self.base_url_var.set(preset.base_url)
        self.model_var.set(preset.default_model)
        self.provider_notes.configure(text=preset.notes or f"Provider: {preset.provider.value}")

    def _on_load_models(self) -> None:
        s = self._collect_settings()
        from .ai.connector import AIConnector
        from .core import ProviderError

        try:
            connector = AIConnector(
                base_url=s.base_url,
                api_key=s.api_key,
                model=s.model,
                timeout=s.request_timeout,
                max_retries=1,
            )
            models = connector.list_models()
            connector.close()
        except ProviderError as exc:
            self.models_label.configure(text=f"Error: {exc}")
            return
        if not models:
            self.models_label.configure(text="(provider returned no model list)")
            return
        display = ", ".join(models[:5]) + ("…" if len(models) > 5 else "")
        self.models_label.configure(text=f"Found {len(models)} models: {display}")
        if not self.model_var.get() and models:
            self.model_var.set(models[0])

    def _browse_script(self) -> None:
        path = ctk.filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if path:
            self.script_path_var.set(path)

    def _browse_file(self, var: tk.StringVar, kind: str) -> None:
        if kind == "image":
            types = [("Images", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All", "*.*")]
        else:
            types = [("Video", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v"), ("All", "*.*")]
        path = ctk.filedialog.askopenfilename(filetypes=types)
        if path:
            var.set(path)

    def _on_render_clicked(self) -> None:
        if self._job_thread and self._job_thread.is_alive():
            return
        try:
            settings = self._collect_settings()
        except SleeplensError as exc:
            self.status_label.configure(text=str(exc), text_color=PALETTE["danger"])
            return
        if not settings.script_topic and not settings.script_file:
            self.status_label.configure(
                text="Add a topic or load a script before rendering.",
                text_color=PALETTE["warning"],
            )
            return
        self.settings = settings
        save_settings(self.paths.config_file, settings)
        self._cancel_flag.clear()
        self.render_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_label.configure(text="Rendering…", text_color=PALETTE["accent_alt"])
        self.progress.set(0)
        self._append_log("Starting render…")

        thread = threading.Thread(target=self._run_job, args=(settings,), daemon=True)
        thread.start()
        self._job_thread = thread

    def _run_job(self, settings: AppSettings) -> None:
        configure_logging(self.paths, level="INFO")
        try:
            result = run_render(
                settings,
                self.paths,
                on_progress=self._on_job_event,
                cancel=self._cancel_flag.is_set,
            )
            self.after(0, lambda: self._on_job_done(result))
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            self.after(0, lambda: self._on_job_failed(exc, tb))

    def _on_job_event(self, event: RenderEvent) -> None:
        self.after(0, lambda: self._apply_event(event))

    def _apply_event(self, event: RenderEvent) -> None:
        self._append_log(f"[{event.stage.value}] {event.message}")
        stage_weights = {
            RenderStage.SCRIPT: 0.10,
            RenderStage.VOICE: 0.35,
            RenderStage.TIMING: 0.45,
            RenderStage.AMBIENT: 0.50,
            RenderStage.MIX: 0.60,
            RenderStage.VISUAL: 0.70,
            RenderStage.ENCODE: 0.95,
            RenderStage.DONE: 1.0,
        }
        self.progress.set(stage_weights.get(event.stage, self.progress.get()))
        self.status_label.configure(text=event.message, text_color=PALETTE["text"])

    def _on_job_done(self, result) -> None:
        self.progress.set(1.0)
        self._append_log(f"Done. Saved to {result.output_path}.")
        self.status_label.configure(
            text=f"Saved to {result.output_path.name}",
            text_color=PALETTE["success"],
        )
        self.render_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.nav_indicator.configure(text="Render complete")

    def _on_job_failed(self, exc: BaseException, tb: str) -> None:
        log.error("Render failed: {}\n{}", exc, tb)
        self._append_log(f"FAILED: {exc}")
        self.status_label.configure(text=f"Failed: {exc}", text_color=PALETTE["danger"])
        self.render_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.nav_indicator.configure(text="Render failed")

    def _on_cancel_clicked(self) -> None:
        if not (self._job_thread and self._job_thread.is_alive()):
            return
        self._cancel_flag.set()
        self._append_log("Cancellation requested…")
        self.status_label.configure(text="Cancelling…", text_color=PALETTE["warning"])

    def _append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


__all__ = ["launch"]

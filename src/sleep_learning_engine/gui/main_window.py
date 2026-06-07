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
from ..core.pipeline import build_connector
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


# ---------------------------------------------------------- voice catalog

# Curated Edge TTS voices, grouped by language. Each entry is
# (voice_id, human_label). The dropdown uses the human label and
# stores the voice id back into the settings.
VOICE_CATALOG: dict[str, list[tuple[str, str]]] = {
    "English (US)": [
        ("en-US-AriaNeural", "Aria — warm, conversational female [top pick]"),
        ("en-US-BrianNeural", "Brian — deep, resonant male [top pick]"),
        ("en-US-EmmaNeural", "Emma — soft, breathy female"),
        ("en-US-GuyNeural", "Guy — casual, warm male"),
        ("en-US-JennyNeural", "Jenny — friendly, clear female"),
        ("en-US-AndrewNeural", "Andrew — mature, audiobook male"),
        ("en-US-MichelleNeural", "Michelle — young, bright female"),
        ("en-US-RogerNeural", "Roger — older, dignified male"),
    ],
    "English (UK)": [
        ("en-GB-SoniaNeural", "Sonia — mature British female"),
        ("en-GB-RyanNeural", "Ryan — warm British male [top pick]"),
        ("en-GB-LibbyNeural", "Libby — young British female"),
        ("en-GB-ThomasNeural", "Thomas — deep British male"),
    ],
    "English (AU / CA / IN / IE)": [
        ("en-AU-NatashaNeural", "Natasha — calm Australian female"),
        ("en-AU-WilliamNeural", "William — mature Australian male"),
        ("en-CA-ClaraNeural", "Clara — calm Canadian female"),
        ("en-IN-NeerjaNeural", "Neerja — soft Indian-accent female"),
        ("en-IE-EmilyNeural", "Emily — soft Irish-accent female"),
    ],
    "Spanish (ES / MX / AR)": [
        ("es-ES-ElviraNeural", "Elvira — Spain Spanish female"),
        ("es-ES-LauraNeural", "Laura — Spain Spanish female (calm)"),
        ("es-MX-DaliaNeural", "Dalia — Mexican Spanish female"),
        ("es-MX-JorgeNeural", "Jorge — Mexican Spanish male"),
        ("es-AR-ElenaNeural", "Elena — Argentinian Spanish female"),
    ],
    "French (FR / CA)": [
        ("fr-FR-DeniseNeural", "Denise — French female"),
        ("fr-FR-HenriNeural", "Henri — French male"),
        ("fr-CA-SylvieNeural", "Sylvie — Canadian French female"),
    ],
    "German": [
        ("de-DE-KatjaNeural", "Katja — German female"),
        ("de-DE-ConradNeural", "Conrad — German male"),
    ],
    "Italian": [
        ("it-IT-ElsaNeural", "Elsa — Italian female"),
        ("it-IT-DiegoNeural", "Diego — Italian male"),
        ("it-IT-IsabellaNeural", "Isabella — Italian female (warm)"),
    ],
    "Portuguese (BR / PT)": [
        ("pt-BR-FranciscaNeural", "Francisca — Brazilian female"),
        ("pt-BR-AntonioNeural", "Antonio — Brazilian male"),
        ("pt-PT-RaquelNeural", "Raquel — European Portuguese female"),
    ],
    "Japanese": [
        ("ja-JP-NanamiNeural", "Nanami — Japanese female"),
        ("ja-JP-KeitaNeural", "Keita — Japanese male"),
    ],
    "Chinese (CN / HK / TW)": [
        ("zh-CN-XiaoxiaoNeural", "Xiaoxiao — Mandarin female"),
        ("zh-CN-YunyangNeural", "Yunyang — Mandarin male"),
        ("zh-HK-HiuMaanNeural", "HiuMaan — Cantonese female"),
        ("zh-TW-HsiaoChenNeural", "HsiaoChen — Taiwanese Mandarin female"),
    ],
    "Other": [
        ("it-IT-GiuseppeNeural", "Giuseppe — Italian male"),
        ("ko-KR-SunHiNeural", "SunHi — Korean female"),
        ("ko-KR-InJoonNeural", "InJoon — Korean male"),
        ("nl-NL-ColetteNeural", "Colette — Dutch female"),
        ("pl-PL-ZofiaNeural", "Zofia — Polish female"),
        ("ru-RU-SvetlanaNeural", "Svetlana — Russian female"),
        ("tr-TR-EmelNeural", "Emel — Turkish female"),
    ],
}

# Flat list of (label, voice_id) for the dropdown, with the voice_id as
# the storage value.
VOICE_OPTIONS: list[str] = [
    label for _group, voices in VOICE_CATALOG.items() for _vid, label in voices
]
VOICE_LABEL_TO_ID: dict[str, str] = {
    label: vid for _group, voices in VOICE_CATALOG.items() for vid, label in voices
}
VOICE_ID_TO_LABEL: dict[str, str] = {vid: label for label, vid in VOICE_LABEL_TO_ID.items()}
# A separator marker so the dropdown can visually group entries.
_VOICE_GROUP_ORDER: list[str] = list(VOICE_CATALOG.keys())


def _voice_options_with_groups() -> list[str]:
    """Build a list of options with group headers as the first entries.

    CustomTkinter's dropdown doesn't render headers natively, so we use
    a leading em-dash separator string. The leading underscores keep
    groups at the top of the list.
    """
    return VOICE_OPTIONS


# ------------------------------------------------------ model catalog per provider

# Curated chat-completions models per provider, REFRESHED FROM THE
# REAL /v1/models RESPONSE on 2026-06-06. The first entry is the
# default; the last entry is "Custom..." which surfaces a text
# field where the user can type any model id.
MODEL_CATALOG: dict[str, list[str]] = {
    # Verified against https://integrate.api.nvidia.com/v1/models
    "nvidia_nim_deepseek": [
        # DeepSeek family (the real ids as advertised by the API).
        "deepseek-ai/deepseek-v4-flash",
        "deepseek-ai/deepseek-v4-pro",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
        # Meta Llama family.
        "meta/llama-4-maverick-17b-128e-instruct",
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.1-70b-instruct",
        "meta/llama-3.1-8b-instruct",
        "meta/llama-3.2-11b-vision-instruct",
        "meta/llama-3.2-90b-vision-instruct",
        # NVIDIA Nemotron family.
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/nemotron-3-nano-30b-a3b",
        "nvidia/nemotron-4-340b-instruct",
        "nvidia/llama-3.3-nemotron-super-49b-v1",
        "nvidia/llama-3.1-nemotron-70b-instruct",
        "nvidia/llama-3.1-nemotron-ultra-253b-v1",
        # Mistral family.
        "mistralai/mistral-large-3-675b-instruct-2512",
        "mistralai/mistral-small-4-119b-2603",
        "mistralai/mistral-large-2-instruct",
        "mistralai/mistral-nemotron",
        "mistralai/mixtral-8x22b-v0.1",
        # Qwen family.
        "qwen/qwen3.5-397b-a17b",
        "qwen/qwen3.5-122b-a10b",
        "qwen/qwen3-coder-480b-a35b-instruct",
        "qwen/qwen3-next-80b-a3b-instruct",
        # Google Gemma.
        "google/gemma-4-31b-it",
        "google/gemma-3-12b-it",
        # Microsoft Phi.
        "microsoft/phi-4-mini-instruct",
        "microsoft/phi-3.5-moe-instruct",
        # OpenAI open-source.
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        # Moonshot Kimi.
        "moonshotai/kimi-k2.6",
        "Custom...",
    ],
    "openai_gpt": [
        "gpt-5.5",
        "gpt-5.5-instant",
        "gpt-5.4",
        "gpt-5.3-instant",
        "gpt-5",
        "gpt-5-mini",
        "o3",
        "o4-mini",
        "Custom...",
    ],
    "anthropic_proxy": [
        "claude-opus-4-8",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "Custom...",
    ],
    "ollama_local": [
        "llama4-scout",
        "llama3.3",
        "llama3.2",
        "llama3.1",
        "qwen3",
        "qwen2.5",
        "gemma4",
        "gemma3",
        "phi-4",
        "mistral",
        "Custom...",
    ],
    "lmstudio_local": [
        "local-model",
        "Custom...",
    ],
    "custom": [
        "Custom...",
    ],
}


# Default system prompt for the script writer. Surfaced in the GUI as
# the value of the "System prompt" text box; the user can edit it.
DEFAULT_SYSTEM_PROMPT = (
    "You are a senior scriptwriter who specialises in calm, hypnotic "
    "narration designed to be listened to as someone falls asleep. "
    "Write in short, soothing sentences. Use a warm, second-person voice. "
    "Avoid dramatic tension, jump scares, or stressful imagery. Weave in "
    "gentle repetition. Insert clear paragraph breaks every two to three "
    "sentences so the narrator can breathe."
)


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

        self.title("Sleep Learning Engine · Sleep Learning Video Studio")
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
            text="SLEEP_LEARNING_ENGINE",
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
        subheader.grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        # ---- Stage tracker: shows the current high-level state. ----
        self.stage_label = ctk.CTkLabel(
            parent,
            text="Configure a script or topic, then hit Render.",
            font=("Inter", 12),
            text_color=PALETTE["muted"],
            wraplength=260,
            justify="left",
        )
        self.stage_label.grid(row=2, column=0, padx=24, pady=(0, 6), sticky="w")

        # ---- Where the last MP4 landed (or empty if none yet). ----
        self.last_output_label = ctk.CTkLabel(
            parent,
            text="",
            font=("Inter", 11),
            text_color=PALETTE["text"],
            wraplength=260,
            justify="left",
        )
        self.last_output_label.grid(row=3, column=0, padx=24, pady=(0, 4), sticky="w")

        # ---- Status line (errors, warnings, in-flight). ----
        self.status_label = ctk.CTkLabel(
            parent,
            text="",
            font=("Inter", 12),
            text_color=PALETTE["muted"],
            wraplength=260,
            justify="left",
        )
        self.status_label.grid(row=5, column=0, padx=24, pady=(0, 12), sticky="swe")

        # ---- Primary actions (stacked, equal width). ----
        self.render_button = ctk.CTkButton(
            parent,
            text="Render full video",
            font=("Inter", 14, "bold"),
            fg_color=PALETTE["accent"],
            hover_color="#6D28D9",
            height=44,
            corner_radius=10,
            command=self._on_render_clicked,
        )
        self.render_button.grid(row=6, column=0, padx=24, pady=(0, 8), sticky="ew")

        self.script_button = ctk.CTkButton(
            parent,
            text="Generate script only",
            font=("Inter", 13),
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["border"],
            text_color=PALETTE["text"],
            height=36,
            corner_radius=8,
            command=self._on_generate_script_only,
        )
        self.script_button.grid(row=7, column=0, padx=24, pady=(0, 6), sticky="ew")

        self.save_button = ctk.CTkButton(
            parent,
            text="Save settings (API key, model, etc.)",
            font=("Inter", 12),
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["border"],
            text_color=PALETTE["text"],
            height=32,
            corner_radius=8,
            command=self._on_save_clicked,
        )
        self.save_button.grid(row=8, column=0, padx=24, pady=(0, 6), sticky="ew")

        self.cancel_button = ctk.CTkButton(
            parent,
            text="Cancel",
            font=("Inter", 12),
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["danger"],
            text_color=PALETTE["text"],
            height=32,
            corner_radius=8,
            state="disabled",
            command=self._on_cancel_clicked,
        )
        self.cancel_button.grid(row=9, column=0, padx=24, pady=(0, 20), sticky="ew")

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
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(99, weight=1)

        ctk.CTkLabel(
            parent,
            text="AI Provider",
            font=("Inter", 18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 8), sticky="w")

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
        ).grid(row=1, column=0, columnspan=2, padx=20, pady=4, sticky="ew")

        self.provider_notes = ctk.CTkLabel(
            parent,
            text="",
            text_color=PALETTE["muted"],
            justify="left",
            wraplength=700,
        )
        self.provider_notes.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 16), sticky="w")

        form = ctk.CTkFrame(parent, fg_color="transparent")
        form.grid(row=3, column=0, columnspan=2, padx=20, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        self.base_url_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.model_label_var = tk.StringVar()
        self.temperature_var = tk.StringVar(value="0.7")
        self.max_tokens_var = tk.StringVar(value="4096")
        self.max_retries_var = tk.StringVar(value="6")
        self.timeout_var = tk.StringVar(value="120")

        # Form rows for non-model fields.
        for row, (label, var) in enumerate(
            [
                ("Base URL", self.base_url_var),
                ("API key", self.api_key_var),
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

        # Model row: a dropdown of curated common models for the current
        # provider, plus a "Custom..." text field for anything else.
        model_row = 99  # placeholder; we'll lay this out explicitly below
        ctk.CTkLabel(parent, text="Model", text_color=PALETTE["muted"]).grid(
            row=4, column=0, padx=20, pady=(12, 0), sticky="w"
        )
        ctk.CTkLabel(parent, text="Custom model id", text_color=PALETTE["muted"]).grid(
            row=4, column=1, padx=20, pady=(12, 0), sticky="w"
        )
        self.model_dropdown = ctk.CTkOptionMenu(
            parent,
            values=MODEL_CATALOG.get(PROVIDER_PRESETS[0].id, ["Custom..."]),
            variable=self.model_label_var,
            command=lambda _v: self._on_model_dropdown_changed(),
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        )
        self.model_dropdown.grid(row=5, column=0, padx=20, pady=4, sticky="ew")
        # The storage of the actual model id the connector will use.
        self.model_var = tk.StringVar()
        self.custom_model_var = tk.StringVar()
        self.custom_model_entry = ctk.CTkEntry(
            parent,
            textvariable=self.custom_model_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            placeholder_text="or type any model id here (see hint below)",
        )
        self.custom_model_entry.grid(row=5, column=1, padx=20, pady=4, sticky="ew")
        self.custom_model_entry.bind("<FocusOut>", lambda _e: self._on_model_dropdown_changed())

        # Where to find model ids. We point users at two sources:
        #   1. The "Load model list" button below, which fetches from
        #      the provider's /v1/models endpoint and merges the result
        #      into the dropdown.
        #   2. The provider's own catalog page, listed per provider.
        # This hint stays visible at all times so nobody wonders.
        self.model_hint_label = ctk.CTkLabel(
            parent,
            text=(
                "Where to find a custom model id:\n"
                "  1. Click 'Load model list from provider' (fetches /v1/models and\n"
                "     merges it into the dropdown above).\n"
                "  2. Or grab one from the provider's catalog:\n"
                "       NVIDIA NIM  -> https://build.nvidia.com/models\n"
                "       OpenAI      -> https://platform.openai.com/docs/models\n"
                "       Anthropic   -> https://docs.anthropic.com/en/docs/about-claude/models\n"
                "       Ollama      -> https://ollama.com/library (use the tag, e.g. llama3.1)\n"
                "       LM Studio   -> whatever the local server exposes"
            ),
            text_color=PALETTE["muted"],
            wraplength=700,
            justify="left",
        )
        self.model_hint_label.grid(
            row=6, column=0, columnspan=2, padx=20, pady=(4, 8), sticky="w"
        )

        models_row = ctk.CTkFrame(parent, fg_color="transparent")
        models_row.grid(row=7, column=0, columnspan=2, padx=20, pady=(4, 12), sticky="ew")
        ctk.CTkButton(
            models_row,
            text="Load model list from provider",
            fg_color=PALETTE["accent"],
            hover_color="#6D28D9",
            text_color=PALETTE["text"],
            command=self._on_load_models,
        ).pack(side="left")
        self.models_label = ctk.CTkLabel(
            models_row, text="(no list fetched yet)", text_color=PALETTE["muted"]
        )
        self.models_label.pack(side="left", padx=12)

        # ---- Advanced: editable system prompt ----
        self.advanced_visible = tk.BooleanVar(value=False)
        adv_toggle = ctk.CTkButton(
            parent,
            text="Show advanced (system prompt)",
            command=self._toggle_advanced,
            fg_color=PALETTE["panel_alt"],
            hover_color=PALETTE["border"],
            text_color=PALETTE["text"],
            height=32,
        )
        adv_toggle.grid(row=7, column=0, columnspan=2, padx=20, pady=(8, 4), sticky="ew")
        self._advanced_toggle_button = adv_toggle

        adv_help = ctk.CTkLabel(
            parent,
            text=(
                "The system prompt tells the AI how to write your script. "
                "Leave it empty to use the built-in default (audio-only teacher: "
                "explains everything in words, no 'as you can see', ends with a recap "
                "of key takeaways, no relaxation framing). "
                "Edit it if you want a different tone, length, or persona."
            ),
            text_color=PALETTE["muted"],
            wraplength=700,
            justify="left",
        )
        self.advanced_help_label = adv_help
        self.system_prompt_text = ctk.CTkTextbox(
            parent,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            border_width=1,
            font=("Inter", 12),
            wrap="word",
            height=160,
        )
        # Hidden by default.
        adv_help.grid_remove()
        self.system_prompt_text.grid_remove()

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

        # TTS backend. Only Edge is wired up; other entries are
        # reserved for future engines and show a clear note in the
        # voice section when chosen.
        self.tts_backend_var = tk.StringVar(value=TTSBackend.EDGE.value)
        backend_labels = []
        for b in TTSBackend:
            if b is TTSBackend.EDGE:
                backend_labels.append(b.value)
            else:
                backend_labels.append(f"{b.value} (coming soon)")
        self.tts_backend_dropdown = ctk.CTkOptionMenu(
            parent,
            values=backend_labels,
            variable=self.tts_backend_var,
            command=lambda _v: self._on_tts_backend_changed(),
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        )
        self.tts_backend_dropdown.grid(row=1, column=0, padx=20, pady=4, sticky="ew")

        # The actual storage value is always one of the TTSBackend
        # enum members. We strip the " (coming soon)" suffix from the
        # displayed value before parsing.
        self.tts_backend_value_var = tk.StringVar(value=TTSBackend.EDGE.value)

        # ---- Voice selector (populated based on backend) ----
        self.voice_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.voice_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=(8, 0), sticky="ew")
        self.voice_frame.grid_columnconfigure(0, weight=1)
        self.voice_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.voice_frame, text="Voice", text_color=PALETTE["muted"]).grid(
            row=0, column=0, padx=0, pady=(0, 4), sticky="w"
        )
        ctk.CTkLabel(self.voice_frame, text="Or type a custom id", text_color=PALETTE["muted"]).grid(
            row=0, column=1, padx=0, pady=(0, 4), sticky="w"
        )

        # Default voice catalog: all 46 Edge voices + "Custom...".
        self._edge_voice_options = _voice_options_with_groups() + ["Custom..."]
        self.tts_voice_label_var = tk.StringVar(
            value=VOICE_ID_TO_LABEL.get("en-US-AriaNeural", "")
        )
        self.tts_voice_dropdown = ctk.CTkOptionMenu(
            self.voice_frame,
            values=self._edge_voice_options,
            variable=self.tts_voice_label_var,
            command=lambda _v: self._on_voice_changed(),
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        )
        self.tts_voice_dropdown.grid(row=1, column=0, padx=4, pady=4, sticky="ew")

        self.custom_voice_var = tk.StringVar(value="en-US-AriaNeural")
        self.custom_voice_entry = ctk.CTkEntry(
            self.voice_frame,
            textvariable=self.custom_voice_var,
            fg_color=PALETTE["panel_alt"],
            text_color=PALETTE["text"],
            border_color=PALETTE["border"],
            placeholder_text="custom Edge voice id (e.g. en-US-AriaNeural)",
        )
        self.custom_voice_entry.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        self.custom_voice_entry.grid_remove()

        # The actual storage: the voice id.
        self.tts_voice_var = tk.StringVar(value="en-US-AriaNeural")

        # Voice note: explains which backend is active and what is supported.
        self.voice_note = ctk.CTkLabel(
            parent,
            text=(
                "Active backend: Edge TTS (free, no key). "
                "All 46 voices below are available."
            ),
            text_color=PALETTE["muted"],
            wraplength=720,
            justify="left",
        )
        self.voice_note.grid(row=3, column=0, columnspan=2, padx=20, pady=(0, 8), sticky="w")

        # ---- Rate / pitch / ambient ----
        tts_row = ctk.CTkFrame(parent, fg_color="transparent")
        tts_row.grid(row=4, column=0, columnspan=2, padx=20, pady=4, sticky="ew")
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
            parent,
            text="Ambient bed",
            font=("Inter", 18, "bold"),
            text_color=PALETTE["text"],
        ).grid(row=5, column=0, columnspan=2, padx=20, pady=(20, 8), sticky="w")

        self.ambient_mode_var = tk.StringVar(value=AmbientMode.AUTO.value)
        ctk.CTkOptionMenu(
            parent,
            values=[m.value for m in AmbientMode],
            variable=self.ambient_mode_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=6, column=0, padx=20, pady=4, sticky="ew")

        ambient_row = ctk.CTkFrame(parent, fg_color="transparent")
        ambient_row.grid(row=6, column=1, padx=20, pady=4, sticky="ew")
        ambient_row.grid_columnconfigure((0, 1), weight=1)
        self.ambient_volume_var = tk.StringVar(value="0.18")
        ctk.CTkEntry(
            ambient_row, textvariable=self.ambient_volume_var, placeholder_text="bed volume (0-1)"
        ).grid(row=0, column=0, padx=8, pady=4, sticky="ew")
        self.ambient_duck_var = tk.StringVar(value="12")
        ctk.CTkEntry(
            ambient_row, textvariable=self.ambient_duck_var, placeholder_text="duck amount (dB)"
        ).grid(row=0, column=1, padx=8, pady=4, sticky="ew")

        ctk.CTkLabel(
            parent,
            text=(
                "Drop royalty-free loops (rain, lofi, alpha waves...) into "
                "assets/ambient/. The studio picks the best match for your script."
            ),
            text_color=PALETTE["muted"],
            justify="left",
            wraplength=720,
        ).grid(row=7, column=0, columnspan=2, padx=20, pady=12, sticky="w")

        # Initial state for the voice selector.
        self._on_tts_backend_changed()

        tts_row = ctk.CTkFrame(parent, fg_color="transparent")
        tts_row.grid(row=4, column=0, columnspan=2, padx=20, pady=4, sticky="ew")
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
        ).grid(row=5, column=0, columnspan=2, padx=20, pady=(20, 8), sticky="w")

        self.ambient_mode_var = tk.StringVar(value=AmbientMode.AUTO.value)
        ctk.CTkOptionMenu(
            parent,
            values=[m.value for m in AmbientMode],
            variable=self.ambient_mode_var,
            fg_color=PALETTE["panel_alt"],
            button_color=PALETTE["accent"],
            button_hover_color="#6D28D9",
            text_color=PALETTE["text"],
        ).grid(row=6, column=0, padx=20, pady=4, sticky="ew")

        ambient_row = ctk.CTkFrame(parent, fg_color="transparent")
        ambient_row.grid(row=6, column=1, padx=20, pady=4, sticky="ew")
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
                "Drop royalty-free loops (rain, lofi, alpha waves...) into "
                "assets/ambient/. The studio picks the best match for your script."
            ),
            text_color=PALETTE["muted"],
            justify="left",
            wraplength=720,
        ).grid(row=7, column=0, columnspan=2, padx=20, pady=12, sticky="w")

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
        # Wire the model dropdown for the selected provider.
        curated = MODEL_CATALOG.get(PROVIDER_PRESETS[preset_idx].id, ["Custom..."])
        if s.model and s.model not in curated:
            curated = [s.model] + curated
        self.model_dropdown.configure(values=curated)
        self.model_label_var.set(s.model if s.model in curated else "Custom...")
        self.custom_model_var.set(s.model)
        self._on_provider_changed(PROVIDER_PRESETS[preset_idx].label)
        self.base_url_var.set(s.base_url)
        self.api_key_var.set(s.api_key)
        self.temperature_var.set(str(s.temperature))
        self.max_tokens_var.set(str(s.max_tokens))
        self.max_retries_var.set(str(s.max_retries))
        self.timeout_var.set(str(s.request_timeout))
        # System prompt: empty means use the built-in default.
        self.system_prompt_text.insert("1.0", s.system_prompt)
        self.topic_text.insert("1.0", s.script_topic)
        self.script_path_var.set(s.script_file)
        self.bg_image_var.set(s.background_image)
        self.bg_video_var.set(s.background_video)
        self.wordcount_var.set(str(s.target_word_count))
        self.pause_var.set(str(s.pause_between_paragraphs))
        self.language_var.set(s.language)
        self.tts_backend_var.set(s.tts_backend.value)
        # Voice: pick the matching label, or fall back to the raw id
        # (which becomes "Custom..." in the dropdown).
        voice_label = VOICE_ID_TO_LABEL.get(s.tts_voice)
        if voice_label:
            self.tts_voice_label_var.set(voice_label)
            self.tts_voice_var.set(s.tts_voice)
            self.custom_voice_entry.grid_remove()
        else:
            self.tts_voice_label_var.set("Custom...")
            self.custom_voice_var.set(s.tts_voice)
            self.tts_voice_var.set(s.tts_voice)
            self.custom_voice_entry.grid()
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
        # Model: dropdown value or custom text field.
        dropdown_value = self.model_label_var.get().strip()
        if dropdown_value == "Custom...":
            s.model = self.custom_model_var.get().strip() or preset.default_model
        else:
            s.model = dropdown_value or preset.default_model
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
        # Voice: dropdown value maps to voice id, Custom... uses the text field.
        voice_label = self.tts_voice_label_var.get().strip()
        if voice_label == "Custom...":
            s.tts_voice = self.custom_voice_var.get().strip() or "en-US-AriaNeural"
        else:
            s.tts_voice = VOICE_LABEL_TO_ID.get(voice_label, voice_label) or "en-US-AriaNeural"
        s.tts_rate = self.tts_rate_var.get().strip() or "-5%"
        s.tts_pitch = self.tts_pitch_var.get().strip() or "-2Hz"
        s.ambient_mode = AmbientMode(self.ambient_mode_var.get())
        s.output_preset = OutputPreset(self.preset_var.get())
        s.hardware_accel = self.hw_var.get()
        s.progress_bar_position = self.bar_position_var.get()
        # System prompt: empty means use the built-in default.
        s.system_prompt = self.system_prompt_text.get("1.0", "end").strip()
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
        # Refresh the model dropdown for the new provider. Each provider
        # has its own curated list, so the dropdown MUST change. We
        # also re-set the variable explicitly because some CTk versions
        # do not refresh the displayed text after `configure(values=...)`.
        curated = list(MODEL_CATALOG.get(preset.id, ["Custom..."]))
        previous = self.model_var.get().strip() if hasattr(self, "model_var") else ""
        # Always reset to the new provider's default unless the previous
        # model is genuinely available in the new provider's list. The
        # "same model for all providers" behaviour the user reported is
        # fixed here by clearing cross-provider carry-over.
        if previous and previous in curated and "/" in previous:
            chosen = previous
        else:
            chosen = curated[0] if curated else "Custom..."
        try:
            self.model_dropdown.configure(values=curated)
        except Exception:  # noqa: BLE001
            pass
        self.model_label_var.set(chosen)
        if chosen == "Custom...":
            self.custom_model_var.set(preset.default_model)
            self.model_var.set(preset.default_model)
        else:
            self.custom_model_var.set("")
            self.model_var.set(chosen)
        self.provider_notes.configure(text=preset.notes or f"Provider: {preset.provider.value}")

    def _on_load_models(self) -> None:
        """Ask the current provider for its model list and merge it in."""
        from ..ai.connector import AIConnector
        from ..core.exceptions import ProviderError

        s = self._collect_settings()
        try:
            connector = AIConnector(
                base_url=s.base_url,
                api_key=s.api_key,
                model=s.model or "list-models",
                timeout=s.request_timeout,
                max_retries=1,
            )
            models = connector.list_models()
            connector.close()
        except ProviderError as exc:
            self.models_label.configure(text=f"Error: {exc}")
            return
        except Exception as exc:  # noqa: BLE001 - network/auth errors are common
            self.models_label.configure(text=f"Network/auth error: {exc}")
            return

        if not models:
            self.models_label.configure(
                text="(provider returned an empty list - your endpoint may not expose /models)"
            )
            return

        # Build a merged option list: curated + provider list, deduped,
        # "Custom..." always at the end so the user can type their own.
        curated = list(MODEL_CATALOG.get(self._current_preset().id, []))
        merged: list[str] = []
        seen: set[str] = set()
        for m in curated + models:
            if m == "Custom...":
                continue
            if m in seen:
                continue
            seen.add(m)
            merged.append(m)
        merged.append("Custom...")

        try:
            self.model_dropdown.configure(values=merged)
        except Exception:  # noqa: BLE001
            # Some CTk versions don't expose configure on OptionMenu.
            pass

        # Make the success feedback very visible: green text, larger
        # weight, and a one-line preview of the first few models so the
        # user knows exactly what was loaded.
        preview = ", ".join(models[:6]) + ("..." if len(models) > 6 else "")
        self.models_label.configure(
            text=f"Loaded {len(models)} models from provider: {preview}",
            text_color=PALETTE["success"],
        )
        self.status_label.configure(
            text=f"Model list refreshed: {len(models)} models now available in the dropdown.",
            text_color=PALETTE["success"],
        )

        # If the current value is not in the merged list, leave it; the
        # user can still type a custom id in the right-hand field.

    def _on_model_dropdown_changed(self) -> None:
        """Sync the dropdown choice into ``self.model_var``.

        "Custom..." puts whatever is in the right-hand field into play.
        """
        choice = self.model_label_var.get()
        if choice == "Custom...":
            self.model_var.set(self.custom_model_var.get().strip())
        else:
            self.model_var.set(choice)

    def _on_voice_changed(self) -> None:
        """Sync the dropdown choice into ``self.tts_voice_var``.

        "Custom..." reveals the text field and uses whatever the user
        typed as the voice id.
        """
        label = self.tts_voice_label_var.get()
        if label == "Custom...":
            self.custom_voice_entry.grid()
            self.tts_voice_var.set(self.custom_voice_var.get().strip())
        else:
            self.custom_voice_entry.grid_remove()
            self.tts_voice_var.set(VOICE_LABEL_TO_ID.get(label, label))

    def _on_tts_backend_changed(self) -> None:
        """React to a TTS backend switch: enable the right voices, or lock the panel.

        Today only Edge TTS is wired up. The other backends are
        reserved for future engines and are shown with a "(coming
        soon)" suffix in the dropdown. When the user picks one of
        them, we hide the voice selector and explain why; when they
        switch back to Edge, we restore the curated Edge voice list.
        """
        display = self.tts_backend_var.get()
        # Strip the "(coming soon)" marker that the dropdown shows, so
        # the value we store matches the TTSBackend enum.
        if " (coming soon)" in display:
            backend_value = display.split(" (coming soon)")[0].strip()
        else:
            backend_value = display.strip()
        self.tts_backend_value_var.set(backend_value)

        if backend_value == TTSBackend.EDGE.value:
            # Restore the Edge voice catalog.
            try:
                self.tts_voice_dropdown.configure(values=self._edge_voice_options, state="normal")
            except Exception:  # noqa: BLE001
                pass
            self.custom_voice_entry.configure(state="normal")
            # If the current label is not a known Edge voice (e.g. we
            # previously hid everything), default back to Aria.
            if self.tts_voice_label_var.get() not in self._edge_voice_options:
                self.tts_voice_label_var.set(
                    VOICE_ID_TO_LABEL.get("en-US-AriaNeural", self._edge_voice_options[0])
                )
            self.voice_note.configure(
                text=(
                    "Active backend: Edge TTS (free, no key). "
                    "All 46 curated voices are available."
                ),
                text_color=PALETTE["muted"],
            )
        else:
            # Lock the voice selector and explain why.
            placeholder = "(voice selection disabled for this backend)"
            try:
                self.tts_voice_dropdown.configure(values=[placeholder], state="disabled")
            except Exception:  # noqa: BLE001
                pass
            self.custom_voice_entry.configure(state="disabled")
            self.tts_voice_label_var.set(placeholder)
            self.voice_note.configure(
                text=(
                    f"Backend '{backend_value}' is reserved for a future release. "
                    "Switch back to 'edge' to pick a voice. The render will use "
                    "the default voice (en-US-AriaNeural) until then."
                ),
                text_color=PALETTE["warning"],
            )

    def _toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_help_label.grid_remove()
            self.system_prompt_text.grid_remove()
            self._advanced_toggle_button.configure(text="Show advanced (system prompt)")
            self.advanced_visible.set(False)
        else:
            self.advanced_help_label.grid(
                row=8, column=0, columnspan=2, padx=20, pady=(8, 0), sticky="w"
            )
            self.system_prompt_text.grid(
                row=9, column=0, columnspan=2, padx=20, pady=4, sticky="nsew"
            )
            self._advanced_toggle_button.configure(text="Hide advanced")
            self.advanced_visible.set(True)

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

    def _on_save_clicked(self) -> None:
        """Persist all current form values to .sleep_learning_engine.toml without rendering."""
        try:
            settings = self._collect_settings()
        except SleeplensError as exc:
            self.status_label.configure(text=str(exc), text_color=PALETTE["danger"])
            return
        self.settings = settings
        save_settings(self.paths.config_file, settings)
        # Tell the user exactly what was persisted, and whether the
        # API key is in fact present. Empty keys are a common source
        # of 'why is nothing working' confusion.
        key_state = "set" if settings.api_key.strip() else "EMPTY (rendering will fail)"
        self.status_label.configure(
            text=(
                f"Settings saved. Provider: {settings.provider_id}, "
                f"Model: {settings.model}, API key: {key_state}. "
                f"Path: {self.paths.config_file}"
            ),
            text_color=PALETTE["success"] if settings.api_key.strip() else PALETTE["warning"],
        )
        self.stage_label.configure(text="Idle. Open the app again to confirm the key loaded.")

    def _on_generate_script_only(self) -> None:
        """Run just the script-generation step and save the result to a .txt."""
        if self._job_thread and self._job_thread.is_alive():
            return
        try:
            settings = self._collect_settings()
        except SleeplensError as exc:
            self.status_label.configure(text=str(exc), text_color=PALETTE["danger"])
            return
        if not settings.script_topic.strip():
            self.status_label.configure(
                text="Add a topic in the Topic tab before generating a script.",
                text_color=PALETTE["warning"],
            )
            return
        if settings.script_file.strip():
            self.status_label.configure(
                text="You loaded a script file. Clear it to generate a new one from the topic.",
                text_color=PALETTE["warning"],
            )
            return

        self.settings = settings
        save_settings(self.paths.config_file, settings)
        self._cancel_flag.clear()
        self._set_action_buttons(running=True, allow_cancel=True)
        self.status_label.configure(text="Generating script…", text_color=PALETTE["accent_alt"])
        self.progress.set(0)
        self._append_log("Starting script generation…")

        thread = threading.Thread(
            target=self._run_script_only_job, args=(settings,), daemon=True
        )
        thread.start()
        self._job_thread = thread

    def _run_script_only_job(self, settings: AppSettings) -> None:
        """Background worker: talk to the provider, save the script, surface errors."""
        from ..ai.connector import AIConnector
        from ..ai.script_writer import ScriptWriter
        from ..core import ProviderError, SleeplensError

        configure_logging(self.paths, level="INFO")
        connector = build_connector(settings)

        # Forward every text delta to the GUI log box. We use a thread-
        # safe queue to cross the worker -> UI thread boundary because
        # CustomTkinter widgets must only be touched from the main
        # thread.
        import queue
        chunk_q: "queue.Queue[str | None]" = queue.Queue()

        def push_chunk(delta: str) -> None:
            chunk_q.put(delta)

        def flush_chunks_to_log() -> None:
            try:
                while True:
                    delta = chunk_q.get_nowait()
                    if delta is None:
                        return
                    self._append_log(delta)
            except Exception:  # noqa: BLE001
                pass

        # Periodically drain the queue from the GUI thread.
        self._start_chunk_pump(flush_chunks_to_log)

        try:
            writer = ScriptWriter(connector)
            script = writer.write(
                topic=settings.script_topic,
                target_word_count=settings.target_word_count,
                language=settings.language,
                system_prompt=settings.system_prompt or None,
                on_chunk=push_chunk,
            )
            stem = "".join(c if c.isalnum() or c in " -_" else "" for c in script.title).strip()[:40] or "script"
            target = self.paths.output_dir / f"{stem}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            script.to_file(target)
            # Capture the locals as default args so the closure binds
            # the value, not the name. (otherwise the lambda runs after
            # the except block has already exited and ``target`` /
            # ``script`` are out of scope).
            self.after(0, lambda t=target, s=script: self._on_script_done(t, s))
        except (ProviderError, SleeplensError) as exc:
            # Friendly hint for the 404 that the user actually hit:
            # the default model id is rejected by the provider, usually
            # because (a) the API key is wrong, or (b) the model id was
            # renamed. We surface both possibilities.
            friendly = self._explain_provider_error(exc, settings)
            self.after(0, lambda msg=friendly: self._on_job_failed_simple(msg))
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            self.after(0, lambda e=exc, t=tb: self._on_job_failed(e, t))
        finally:
            try:
                connector.close()
            except Exception:  # noqa: BLE001
                pass
            self._stop_chunk_pump()

    _chunk_pump_after_id: str | None = None

    def _start_chunk_pump(self, flush) -> None:
        """Start a periodic GUI-thread drain of streamed chunks.

        Calling this from a background worker wires up a 60ms tick on
        the main thread that pulls every queued chunk into the log box
        via ``self._append_log``. Streaming gives the user live
        feedback while a 284B MoE model boots up; without it the GUI
        sits silently for 30-60 seconds and looks frozen.
        """
        def _tick() -> None:
            flush()
            # Re-schedule until the pump is explicitly stopped.
            self._chunk_pump_after_id = self.after(60, _tick)

        # Cancel any previous pump first.
        self._stop_chunk_pump()
        self._chunk_pump_after_id = self.after(60, _tick)

    def _stop_chunk_pump(self) -> None:
        if self._chunk_pump_after_id is not None:
            try:
                self.after_cancel(self._chunk_pump_after_id)
            except Exception:  # noqa: BLE001
                pass
            self._chunk_pump_after_id = None

    def _on_script_done(self, path: Path, script) -> None:
        self.progress.set(0.25)
        self._append_log(
            f"Script ready: {len(script.paragraphs)} paragraphs, {script.word_count} words -> {path}"
        )
        self.status_label.configure(
            text=f"Script saved: {path.name}. Review it, then hit Render full video.",
            text_color=PALETTE["success"],
        )
        self.last_output_label.configure(text=f"Latest script:\n{path}")
        # Pre-fill the script path so a re-render uses it directly.
        self.script_path_var.set(str(path))
        self.script_topic_text_empty()
        self._set_action_buttons(running=False, allow_cancel=False)

    def script_topic_text_empty(self) -> None:
        """After generating, clear the topic field so the next render uses the saved .txt."""
        # Don't auto-clear: the user might want to re-roll the script.
        # We just point them at the file in the status line.
        pass

    def _set_action_buttons(self, *, running: bool, allow_cancel: bool) -> None:
        if running:
            self.render_button.configure(state="disabled")
            self.script_button.configure(state="disabled")
            self.save_button.configure(state="disabled")
        else:
            self.render_button.configure(state="normal")
            self.script_button.configure(state="normal")
            self.save_button.configure(state="normal")
        if allow_cancel:
            self.cancel_button.configure(state="normal")
        else:
            self.cancel_button.configure(state="disabled")

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
        self._set_action_buttons(running=True, allow_cancel=True)
        self.status_label.configure(text="Rendering full video…", text_color=PALETTE["accent_alt"])
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
            # Bind ``result`` as a default arg so the closure captures
            # the value (not the name) and survives until after() fires.
            self.after(0, lambda r=result: self._on_job_done(r))
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            self.after(0, lambda e=exc, t=tb: self._on_job_failed(e, t))

    def _explain_provider_error(self, exc: BaseException, settings: AppSettings) -> str:
        """Turn a provider exception into a user-actionable hint.

        The most common failure modes (in order):
          1. No API key set (we still try; provider returns 401 or 404).
          2. Model id was renamed by the provider (404 with body).
          3. Network / DNS / firewall.
        """
        msg = str(exc)
        preset = next((p for p in PROVIDER_PRESETS if p.id == settings.provider_id), None)
        provider_label = preset.label if preset else settings.provider_id
        if "404" in msg:
            return (
                f"Provider '{provider_label}' returned 404 for model "
                f"'{settings.model}'. "
                "Two most common causes:\n"
                "  - You have not set an API key in the Provider tab.\n"
                "  - The model id was renamed by the provider.\n"
                "Try clicking 'Load model list from provider' to pick a "
                "currently-available model, or check the catalog URL "
                "listed in the Model row hint."
            )
        if "401" in msg or "403" in msg or "Authentication" in msg:
            return (
                f"Provider '{provider_label}' rejected the API key. "
                "Open the Provider tab and re-paste your key, or check "
                "that it has the right scopes."
            )
        return f"Provider error: {msg}"

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
        # Show the current pipeline stage in the sidebar so the user
        # always knows what is happening.
        self.stage_label.configure(text=f"Stage: {event.stage.value} — {event.message}")
        self.status_label.configure(text="", text_color=PALETTE["muted"])

    def _on_job_done(self, result) -> None:
        self.progress.set(1.0)
        self._append_log(f"Done. Saved to {result.output_path}.")
        self.status_label.configure(
            text=f"Done. Saved to {result.output_path.name} ({result.duration_seconds / 60:.1f} min).",
            text_color=PALETTE["success"],
        )
        self.last_output_label.configure(text=f"Latest video:\n{result.output_path}")
        self.stage_label.configure(text="Idle. Configure another topic or hit Render again.")
        self._set_action_buttons(running=False, allow_cancel=False)

    def _on_job_failed(self, exc: BaseException, tb: str) -> None:
        log.error("Render failed: {}\n{}", exc, tb)
        self._append_log(f"FAILED: {exc}")
        if tb:
            self._append_log(tb.strip().splitlines()[-1] if tb.strip() else "")
        # Use the friendlier explanation when available, but fall back
        # to the raw exception text if anything goes wrong here.
        try:
            friendly = self._explain_provider_error(exc, self.settings)
        except Exception:  # noqa: BLE001
            friendly = f"Failed: {exc}"
        self.status_label.configure(text=friendly, text_color=PALETTE["danger"])
        self.stage_label.configure(text="Last run failed. See log for details.")
        self._set_action_buttons(running=False, allow_cancel=False)

    def _on_job_failed_simple(self, message: str) -> None:
        """Like _on_job_failed but takes a pre-built message string.

        Used by the script-only path when we already have a user-facing
        explanation that does not need to be re-interpreted.
        """
        log.error("Job failed: {}", message)
        self._append_log(f"FAILED: {message}")
        self.status_label.configure(text=message, text_color=PALETTE["danger"])
        self.stage_label.configure(text="Last run failed. See log for details.")
        self._set_action_buttons(running=False, allow_cancel=False)

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

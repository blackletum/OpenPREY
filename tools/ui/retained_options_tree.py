"""The retained Options page's tree (docs/dev/prey-ui-visual-design.md
section 12.5, "Options"): its four top tabs, their side tabs and, on each
page, two columns of rows under inline section headings.

The stock page (guis/mainmenu/mainmenu_options.guifragment) still holds the
retail tree for `ui_retained 0`; this tree is the retained page's own and
adds openPR06's settings to it. Each row names what it changes:

- `bind(command, label)`: a binding row. The rows' commands, in tree order,
  are PREY_CONTROLS_BINDINGS in src/framework/Session_menu.cpp.
- `toggle(cvar, label)`: No or Yes (`inverted` for a "skip" setting, Yes or No).
- `choice(cvar, label, choices, values)`: one of a language list's options.
- `slider(cvar, label, low, high, step)`.
- `verb(key, label)`: a row the session acts on (OPTION_VERBS in the
  generator), with the stock row's choices or range.
- `size(label, width_cvar, height_cvar)`: two number fields.
- `detect()`: the Quality Preset's Detect box (two slots).
- `heading(key)`: a section heading, one slot.
- `either(section, row, section, row)`: two rows in one slot, each shown in
  its section (the Audio page's software and OpenAL rows).

A setting's kind (Boolean, number or text) follows its CVar's declared type;
the engine's list of settings a page may change (FindPlayerSetting in
src/ui/UserInterfaceRetained.cpp) must hold each with the same bounds, and
the generator checks that it does.

Language keys #str_1221xx and #str_1222xx are openPR06's
(content/basepr/pak0/strings/*_openpr06.lang); the rest are retail Prey's."""
from __future__ import annotations

NO_YES, YES_NO = "#str_20152", "#str_20297"


def bind(command: str, label: str) -> dict:
    return {"kind": "bind", "bind": command, "label": label}


def toggle(cvar: str, label: str, *, inverted: bool = False, kind: str = "boolean") -> dict:
    return {"kind": "choice", "cvar": cvar, "label": label, "choices": YES_NO if inverted else NO_YES,
            "values": None, "type": kind}


def choice(cvar: str, label: str, choices: str, values: list, *, kind: str = "number") -> dict:
    return {"kind": "choice", "cvar": cvar, "label": label, "choices": choices, "values": None if values is None else [str(v) for v in values], "type": kind}


def slider(cvar: str, label: str, low: float, high: float, step: float) -> dict:
    return {"kind": "slider", "cvar": cvar, "label": label, "low": low, "high": high, "step": step, "type": "number"}


def verb(key: str, label: str, *, choices: str | None = None, values: list | None = None, low: float = 0, high: float = 1,
         step: float = 0.05, slide: bool = False) -> dict:
    if slide:
        return {"kind": "slider", "cvar": key, "label": label, "low": low, "high": high, "step": step}
    return {"kind": "choice", "cvar": key, "label": label, "choices": choices, "values": values}


def size(label: str, width: str, height: str) -> dict:
    return {"kind": "size", "label": label, "fields": [{"cvar": width}, {"cvar": height}]}


def detect() -> dict:
    return {"kind": "detect", "label": "#str_41177", "button": "#str_41178"}


def heading(key: str) -> dict:
    return {"kind": "heading", "key": key}


def either(*pairs) -> dict:
    """Rows sharing a slot: (section, row) pairs."""
    return {"kind": "either", "rows": list(pairs)}


def side(key: str, left: list, right: list, *, name: str, apply: bool = False) -> dict:
    return {"key": key, "name": name, "columns": [left, right], "apply": apply}


# ------------------------------------------------------------------ Controls

CONTROLS = [
    side("#str_20211", name="movement", left=[
        heading("#str_20211"),
        bind("_forward", "#str_20214"), bind("_back", "#str_20215"), bind("_moveLeft", "#str_20216"),
        bind("_moveRight", "#str_20217"), bind("_moveUp", "#str_20218"), bind("_moveDown", "#str_20219"),
        bind("_speed", "#str_122103"), bind("_strafe", "#str_20220"),
    ], right=[
        heading("#str_20236"),
        bind("_left", "#str_20237"), bind("_right", "#str_20238"), bind("_lookUp", "#str_20239"),
        bind("_lookDown", "#str_20240"), bind("_mlook", "#str_20241"), bind("_impulse18", "#str_20242"),
    ]),
    side("#str_20229", name="combat", left=[
        heading("#str_20229"),
        bind("_attack", "#str_20230"), bind("_attackAlt", "#str_20231"), bind("_impulse15", "#str_20232"),
        bind("_impulse14", "#str_20233"), bind("_zoom", "#str_20243"), bind("_impulse25", "#str_122232"),
        bind("_weaponWheel", "#str_122316"),
        heading("#str_122102"),
        bind("_impulse16", "#str_20234"), bind("_impulse54", "#str_20235"),
    ], right=[
        heading("#str_20221"),
        bind("_impulse1", "#str_20222"), bind("_impulse2", "#str_20223"), bind("_impulse3", "#str_20224"),
        bind("_impulse4", "#str_20228"), bind("_impulse5", "#str_20225"), bind("_impulse6", "#str_20226"),
        bind("_impulse7", "#str_20227"),
    ]),
    side("#str_20244", name="system", left=[
        heading("#str_20244"),
        bind("savegame quick", "#str_20245"), bind("loadgame quick", "#str_20246"), bind("screenshot", "#str_20247"),
    ], right=[
        heading("#str_20338"),
        bind("clientMessageMode", "#str_20249"), bind("clientMessageMode 1", "#str_20250"), bind("_impulse20", "#str_20251"),
        bind("_impulse22", "#str_20252"), bind("_impulse17", "#str_20253"), bind("_impulse28", "#str_20254"),
        bind("_impulse29", "#str_20255"), bind("_impulse19", "#str_20256"),
    ]),
    side("#str_122100", name="mouse", left=[
        heading("#str_122104"),
        toggle("in_freeLook", "#str_20277"),
        choice("m_pitch", "#str_20274", NO_YES, ["0.022", "-0.022"], kind="string"),
        toggle("in_toggleZoom", "#str_20279"),
        heading("#str_122100"),
        slider("sensitivity", "#str_20276", 1, 30, 0.5),
        slider("m_smooth", "#str_20275", 1, 8, 1),
        heading("#str_122107"),
        toggle("in_alwaysRun", "#str_122112"),
        toggle("in_toggleCrouch", "#str_122113"),
    ], right=[
        heading("#str_122106"),
        slider("cl_mouseAccel", "#str_122108", 0, 5, 0.1),
        slider("cl_mouseAccelOffset", "#str_122109", 0, 50, 1),
        slider("cl_mouseAccelPower", "#str_122110", 1, 8, 0.5),
        slider("cl_mouseSensCap", "#str_122111", 0, 100, 1),
    ]),
    side("#str_122101", name="controller", left=[
        heading("#str_122115"),
        toggle("in_joystick", "#str_122116"),
        choice("in_joystickSouthpaw", "#str_122117", "#str_122118", [0, 1]),
        slider("in_joystickDeadZone", "#str_122119", 0, 0.5, 0.01),
        slider("in_joystickLookSensitivity", "#str_122120", 0.1, 4, 0.05),
        slider("in_joystickLookCurve", "#str_122121", 1, 3, 0.05),
        slider("in_joystickMoveCurve", "#str_122122", 1, 3, 0.05),
        toggle("in_joystickInvertLook", "#str_122123"),
        heading("#str_122138"),
        choice("in_promptStyle", "#str_122124", "#str_122125", [0, 1, 2, 3, 4, 5]),
        choice("in_swapConfirmBack", "#str_122126", "#str_122127", [0, 1, 2]),
    ], right=[
        heading("#str_122128"),
        slider("in_joystickTriggerThreshold", "#str_122129", 0.05, 1, 0.05),
        toggle("in_joystickRumble", "#str_122130"),
        slider("in_joystickRumbleScale", "#str_122131", 0, 2, 0.05),
        heading("#str_122132"),
        toggle("in_gyro", "#str_122133"),
        slider("in_gyroSensitivity", "#str_122134", 0, 8, 0.1),
        choice("in_touchpadMode", "#str_122135", "#str_122136", [0, 1, 2, 3]),
        slider("in_touchpadSensitivity", "#str_122137", 0, 8, 0.1),
    ]),
    {"key": "#str_20258", "name": "profiles", "profiles": True},
]

# -------------------------------------------------------------- Game Options

GAME = [
    side("#str_122139", name="general", left=[
        heading("#str_122140"),
        toggle("g_useDDA", "#str_41097"),
        toggle("ui_autoSwitch", "#str_122141"),
        heading("#str_122142"),
        slider("g_fov", "#str_122143", 70, 130, 1),
        slider("cl_gunfov", "#str_122144", 0, 130, 1),
        toggle("cl_gunfov_adjust", "#str_122145", kind="number"),
        toggle("ui_showGun", "#str_20266"),
        toggle("g_showPlayerShadow", "#str_122146"),
    ], right=[
        heading("#str_122147"),
        toggle("g_decals", "#str_20264"),
        toggle("g_bloodEffects", "#str_122148"),
        toggle("g_ragdollDecals", "#str_122149"),
        toggle("g_showBrass", "#str_122150"),
        toggle("g_muzzleFlash", "#str_122151"),
        toggle("g_projectileLights", "#str_122152"),
        toggle("com_profanity", "#str_41002"),
    ]),
    side("#str_122153", name="hud", left=[
        heading("#str_122153"),
        toggle("g_showHud", "#str_20265"),
        toggle("g_tips", "#str_122154"),
        choice("com_showFPS", "#str_122155", "#str_122156", [0, 1, 2]),
        heading("#str_20268"),
        choice("g_crosshair", "#str_20268", "#str_20269", list(range(9))),
    ], right=[
        heading("#str_20249"),
        slider("ui_chatScale", "#str_122157", 0.75, 2, 0.05),
        slider("ui_chatLines", "#str_122158", 2, 16, 1),
        slider("ui_chatAlpha", "#str_122159", 0, 1, 0.05),
        slider("ui_chatTime", "#str_122160", 0, 30, 1),
        heading("#str_122316"),
        slider("ui_weaponWheelOffset", "#str_122317", -40, 40, 1),
        slider("in_weaponWheelSensitivity", "#str_122318", 0.25, 16, 0.25),
    ]),
    side("#str_122161", name="access", left=[
        heading("#str_20267"),
        toggle("g_subtitles", "#str_20267"),
        toggle("ui_subtitleUntranscribed", "#str_122162"),
        heading("#str_122163"),
        toggle("g_doubleVision", "#str_122164"),
        toggle("r_underwater", "#str_122165"),
    ], right=[
        heading("#str_122169"),
        toggle("ui_retainedReducedMotion", "#str_122166"),
        toggle("ui_retainedOpaqueBacking", "#str_122167"),
        slider("gui_textBackground", "#str_122168", 0, 1, 0.05),
    ]),
    side("#str_122177", name="system", left=[
        heading("#str_122177"),
        toggle("ui_menuScene", "#str_122170"),
        toggle("con_allowConsole", "#str_122173", kind="number"),
        choice("r_screenshotFormat", "#str_122174", "#str_122175", [0, 1]),
    ], right=[
        heading("#str_122176"),
        toggle("com_skipLogoVideos", "#str_122171"),
        toggle("com_updateCheck", "#str_122172"),
    ]),
]

# --------------------------------------------------------------------- Video

VIDEO = [
    side("#str_122027", name="display", apply=True, left=[
        heading("#str_122194"),
        choice("r_renderApi", "#str_122042", "#str_122043", ["best", "gl", "vulkan"], kind="string"),
        verb("r_screen", "#str_122029"),
        verb("display_mode_choice", "#str_20287"),
        verb("r_fullscreen", "#str_20289", choices=NO_YES),
        choice("r_fullscreenDesktop", "#str_122030", "#str_122031", ["1", "0"], kind="boolean"),
        toggle("r_borderless", "#str_122032"),
        verb("r_displayRefresh", "#str_122033"),
        toggle("r_multiScreen", "#str_122036", kind="number"),
        size("#str_122037", "r_windowWidth", "r_windowHeight"),
        size("#str_122038", "r_customWidth", "r_customHeight"),
    ], right=[
        heading("#str_122195"),
        toggle("r_swapInterval", "#str_20303", kind="number"),
        verb("com_maxfps", "#str_122034"),
        choice("r_screenFraction", "#str_122039", "#str_122060", [10, 25, 50, 75, 85, 100, 125, 150, 200]),
        choice("r_resolutionScaleMode", "#str_122196", "#str_122197", [0, 1, 2, 3]),
        slider("r_resolutionScaleSharpness", "#str_122198", 0, 1.5, 0.05),
        heading("#str_122199"),
        slider("r_brightness", "#str_20290", 0.5, 2, 0.1),
        slider("r_gamma", "#str_20291", 0.5, 2, 0.1),
    ]),
    side("#str_122178", name="quality", apply=True, left=[
        detect(),
        verb("com_performancePreset", "#str_122025"),
        heading("#str_122179"),
        toggle("r_skipNewAmbient", "#str_20296", inverted=True),
        choice("r_shaderLevel", "#str_20298", "#str_20299", [0, 1, 2, 3]),
        toggle("r_shadows", "#str_20300"),
        toggle("r_useShadowMap", "#str_122040"),
        choice("r_shadowMapSize", "#str_122180", "#str_122181", [512, 1024, 2048, 4096]),
        choice("r_shadowMapFilterMode", "#str_122182", "#str_122183", [0, 1, 2]),
    ], right=[
        heading("#str_122184"),
        toggle("r_skipSpecular", "#str_20301", inverted=True),
        toggle("r_skipBump", "#str_20302", inverted=True),
        toggle("r_correctspecular", "#str_20306"),
        toggle("r_normalizebumpmap", "#str_20307"),
        choice("r_skipGlowOverlay", "#str_20308", YES_NO, None, kind="string"),
        choice("image_anisotropy", "#str_41180", "#str_20305", [1, 2, 4, 8, 16]),
        toggle("r_softParticles", "#str_122185"),
        toggle("r_useFastSkinning", "#str_41072", inverted=True),
    ]),
    side("#str_122003", name="post", apply=True, left=[
        heading("#str_122186"),
        choice("r_multiSamples", "#str_122007", "#str_122023", [0, 2, 4, 8, 16]),
        toggle("r_msaaAlphaToCoverage", "#str_122014"),
        choice("r_postAA", "#str_122008", "#str_122024", [0, 1, 2, 3, 4]),
        choice("r_temporalAA", "#str_122187", "#str_122188", [0, 1, 2]),
        heading("#str_122189"),
        toggle("r_ssao", "#str_122009"),
        slider("r_ssaoRadius", "#str_122015", 4, 256, 4),
        slider("r_ssaoIntensity", "#str_122016", 0, 4, 0.05),
    ], right=[
        heading("#str_122190"),
        toggle("r_bloom", "#str_122010"),
        slider("r_bloomIntensity", "#str_122011", 0, 2, 0.05),
        slider("r_bloomRadius", "#str_122017", 0.1, 8, 0.05),
        slider("r_bloomThreshold", "#str_122191", 0, 4, 0.05),
        toggle("r_hdrToneMap", "#str_122012"),
        slider("r_hdrExposure", "#str_122013", 0.25, 3, 0.05),
        slider("r_hdrWhitePoint", "#str_122018", 1, 16, 0.25),
        slider("r_hdrSaturation", "#str_122019", 0, 2, 0.05),
        slider("r_hdrContrast", "#str_122020", 0.5, 3, 0.05),
    ]),
    side("#str_122004", name="effects", apply=True, left=[
        heading("#str_122041"),
        toggle("r_motionBlur", "#str_122041"),
        slider("r_motionBlurStrength", "#str_122192", 0, 2, 0.05),
        heading("#str_122002"),
        toggle("r_crt", "#str_122002"),
        slider("r_crtAmount", "#str_122021", 0, 1, 0.05),
        slider("r_crtChromatic", "#str_122231", 0, 0.35, 0.01),
    ], right=[
        heading("#str_122193"),
        slider("r_glowStrength", "#str_122230", 0, 4, 0.05),
        heading("#str_122314"),
        toggle("r_depthOfField", "#str_122314"),
        slider("r_depthOfFieldRadius", "#str_122315", 0, 32, 1),
    ]),
]

# --------------------------------------------------------------------- Audio

AUDIO = [
    side(None, name="audio", left=[
        heading("#str_20314"),
        verb("s_volume_dB", "#str_41132", slide=True, low=0, high=1, step=0.05),
        verb("s_musicvolume_dB", "#str_41133", slide=True, low=0, high=1, step=0.05),
        slider("s_dialogueVolume", "#str_122200", 0, 1, 0.05),
        toggle("g_levelloadmusic", "#str_20315"),
        heading("#str_122201"),
        verb("s_useOpenAL", "#str_20312", choices="#str_20313", values=["0", "1"]),
        either(("software", verb("s_numberOfSpeakers", "#str_20317", choices="#str_122215", values=["0", "2", "6"])),
               ("openal", verb("s_deviceName", "#str_20321"))),
        either(("software", toggle("s_reverse", "#str_20319")),
               ("openal", verb("s_useEAXReverb", "#str_20322", choices="#str_20323", values=["1", "0"]))),
    ], right=[
        heading("#str_122202"),
        toggle("s_useEAXOcclusion", "#str_122203"),
        toggle("s_airAbsorption", "#str_122204"),
        toggle("s_outputLimiter", "#str_122205"),
        toggle("s_muteUnfocused", "#str_122206"),
    ]),
]

# The top tabs: label, sides.
TABS = [("#str_20210", CONTROLS), ("#str_20262", GAME), ("#str_20280", VIDEO), ("#str_20310", AUDIO)]


def rows(tree=TABS):
    """Every row of the tree, either's rows included, in order."""
    for _, sides in tree:
        for page in sides:
            for column in page.get("columns", ()):
                for row in column:
                    if row["kind"] == "either":
                        yield from (inner for _, inner in row["rows"])
                    else:
                        yield row


def bindings(tree=TABS) -> list[str]:
    return [row["bind"] for row in rows(tree) if row["kind"] == "bind"]

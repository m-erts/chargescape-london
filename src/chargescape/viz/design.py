"""Design tokens shared by every generated page (maps, slides, project page).

Source of truth: DESIGN.md in the repository root (Vercel system). Rules applied here:

* Monochrome palette with one accent. Background, foreground, border and surface values are taken
  from DESIGN.md. Muted text on the light theme is darkened from the documented neutral to pass
  WCAG AA at small sizes; the neutral itself is kept for non-text marks.
* Shape: one corner-radius system, all sharp (radius 0), for cells, frames, tables and controls.
* Motion: 150 ms state transitions only. Slide changes and map toggles are never animated.
* Geist and Geist Mono are vendored in docs/vendor (SIL Open Font License), no font CDN.
"""

from __future__ import annotations

FONT_DIR = "geist-1.4.2"
SANS = '"Geist","Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
MONO = '"Geist Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'

LIGHT = {
    "bg": "#FFFFFF",
    "fg": "#111111",
    "muted": "#666666",
    "neutral": "#888888",
    "border": "#EAEAEA",
    "surface": "#FAFAFA",
    "accent": "#0070F3",
    "r1": "#F2F2F2",
    "r2": "#D9D9D9",
    "r3": "#B3B3B3",
    "r4": "#858585",
    "r5": "#4D4D4D",
    "r6": "#111111",
}
DARK = {
    "bg": "#000000",
    "fg": "#EDEDED",
    "muted": "#888888",
    "neutral": "#888888",
    "border": "#333333",
    "surface": "#0A0A0A",
    "accent": "#0070F3",
    "r1": "#1A1A1A",
    "r2": "#333333",
    "r3": "#555555",
    "r4": "#808080",
    "r5": "#B3B3B3",
    "r6": "#EDEDED",
}


def _vars(tokens: dict[str, str]) -> str:
    return "".join(f"--{k}:{v};" for k, v in tokens.items())


def tokens_css(vendor_prefix: str) -> str:
    """@font-face, colour tokens for both themes and the base reset. `vendor_prefix` is the relative
    path from the page to docs/vendor."""
    f = f"{vendor_prefix}/{FONT_DIR}"
    return f"""
@font-face{{font-family:"Geist";src:url("{f}/Geist-Variable.woff2") format("woff2");font-weight:100 900;font-display:swap}}
@font-face{{font-family:"Geist Mono";src:url("{f}/GeistMono-Variable.woff2") format("woff2");font-weight:100 900;font-display:swap}}
:root{{color-scheme:light;{_vars(LIGHT)}--radius:0px;--ease-out:cubic-bezier(0.23,1,0.32,1);--z-map-ui:10;--z-bar:20}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;{_vars(DARK)}}}}}
:root[data-theme="dark"]{{color-scheme:dark;{_vars(DARK)}}}
*,*::before,*::after{{box-sizing:border-box}}
html,body{{margin:0;background:var(--bg);color:var(--fg)}}
body{{font-family:{SANS};-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
.mono,code,kbd,td.num,th.num{{font-family:{MONO};font-variant-numeric:tabular-nums}}
a{{color:inherit;text-decoration:underline;text-decoration-color:var(--neutral);text-underline-offset:0.2em;transition:text-decoration-color 150ms ease}}
@media (hover:hover) and (pointer:fine){{a:hover{{text-decoration-color:var(--fg)}}}}
a:focus-visible,button:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
@media (prefers-reduced-motion:reduce){{*,*::before,*::after{{transition-duration:0.01ms !important;animation-duration:0.01ms !important}}}}
"""


# Runs before first paint: explicit ?theme= wins, then the stored choice, then the system setting.
THEME_BOOT_JS = """(function(){var t=new URLSearchParams(location.search).get('theme');
if(t!=='dark'&&t!=='light'){try{t=localStorage.getItem('cs-theme')}catch(e){t=null}}
if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);})();
function csIsDark(){var a=document.documentElement.getAttribute('data-theme');
return a?a==='dark':matchMedia('(prefers-color-scheme: dark)').matches;}
function csToken(n){return getComputedStyle(document.documentElement).getPropertyValue('--'+n).trim();}"""

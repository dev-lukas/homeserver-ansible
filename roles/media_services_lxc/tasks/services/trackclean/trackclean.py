#!/usr/bin/env python3
"""Normalise the audio/subtitle tracks of MKV files for Jellyfin.

Keeps the wanted languages, one subtitle per language and kind (full/forced),
sets language, forced, hearing-impaired and default flags, and clears track
titles so Jellyfin builds uniform labels from the flags.

  trackclean.py SRC DST                       Sonarr/Radarr "Import Using Script"
  trackclean.py batch [--apply] PATH...        existing library (dry run by default)
  trackclean.py show FILE                      print the plan for one file
"""
import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler

# "org" is the original language reported by Sonarr/Radarr.
PROFILES = {
    "standard": {
        "audio": ["ger", "org", "eng"],
        "default_audio": ["ger", "org", "eng"],
        "subs": ["ger", "eng"],
        "sub_formats": ["srt", "ass", "vtt", "pgs", "vobsub"],
    },
    "anime": {
        "audio": ["org", "jpn", "ger", "eng"],
        "default_audio": ["org", "jpn"],
        "subs": ["ger", "eng"],
        "sub_formats": ["ass", "srt", "vtt", "pgs", "vobsub"],
    },
}

# Matroska legacy codes are ISO 639-2/B; normalise T codes and 639-1 to them.
T_TO_B = {
    "deu": "ger", "fra": "fre", "zho": "chi", "ces": "cze", "nld": "dut", "ell": "gre",
    "ron": "rum", "fas": "per", "msa": "may", "isl": "ice", "hye": "arm", "eus": "baq",
    "mya": "bur", "kat": "geo", "mkd": "mac", "mri": "mao", "sqi": "alb", "slk": "slo",
    "bod": "tib", "cym": "wel",
}
ISO1 = {
    "de": "ger", "en": "eng", "ja": "jpn", "fr": "fre", "es": "spa", "it": "ita",
    "ko": "kor", "zh": "chi", "pt": "por", "ru": "rus", "nl": "dut", "pl": "pol",
    "sv": "swe", "da": "dan", "no": "nor", "nb": "nor", "fi": "fin", "tr": "tur",
    "cs": "cze", "hu": "hun", "el": "gre", "he": "heb", "ar": "ara", "hi": "hin",
    "th": "tha", "vi": "vie", "id": "ind", "uk": "ukr", "ro": "rum", "lv": "lav",
}
# Sonarr/Radarr API language names -> ISO 639-2/B.
ARR_NAMES = {
    "english": "eng", "french": "fre", "spanish": "spa", "german": "ger", "italian": "ita",
    "danish": "dan", "dutch": "dut", "flemish": "dut", "japanese": "jpn", "icelandic": "ice",
    "chinese": "chi", "russian": "rus", "polish": "pol", "vietnamese": "vie", "swedish": "swe",
    "norwegian": "nor", "finnish": "fin", "turkish": "tur", "portuguese": "por",
    "portuguese (brazil)": "por", "spanish (latino)": "spa", "greek": "gre", "korean": "kor",
    "hungarian": "hun", "hebrew": "heb", "lithuanian": "lit", "czech": "cze", "arabic": "ara",
    "hindi": "hin", "bulgarian": "bul", "malayalam": "mal", "ukrainian": "ukr", "slovak": "slo",
    "thai": "tha", "romanian": "rum", "latvian": "lav", "persian": "per", "catalan": "cat",
    "croatian": "hrv", "serbian": "srp", "bosnian": "bos", "estonian": "est", "tamil": "tam",
    "indonesian": "ind", "macedonian": "mac", "slovenian": "slv", "azerbaijani": "aze",
    "uzbek": "uzb", "malay": "may", "urdu": "urd", "mongolian": "mon", "bengali": "ben",
    "telugu": "tel", "georgian": "geo", "kannada": "kan", "albanian": "alb",
    "afrikaans": "afr", "marathi": "mar", "tagalog": "tgl", "filipino": "fil",
}
UNDEFINED = {"", "und", "mis", "mul", "zxx"}

# Only used for untagged tracks.
TITLE_LANG = [
    (re.compile(r"\b(german|deutsch)", re.I), "ger"),
    (re.compile(r"\b(english|englisch)", re.I), "eng"),
    (re.compile(r"\b(japanese|japanisch)", re.I), "jpn"),
]
FULL_RE = re.compile(r"\b(full|dialog(ue)?s?|vollständig|komplett)\b", re.I)
FORCED_RE = re.compile(r"forced|\bsigns?\b|\bsongs?\b|foreign|erzwungen|\bzwang", re.I)
SDH_RE = re.compile(r"\b(sdh|cc|hi|hearing[ -]?impaired|hörgeschädigte?n?|hoergeschaedigt)\b", re.I)
EXTRA_RE = re.compile(r"comment|kommentar|descriptive|audiodeskription|audio description|hörfilm", re.I)

SUB_FORMATS = {
    "S_TEXT/UTF8": "srt", "S_TEXT/ASCII": "srt", "S_TEXT/ASS": "ass", "S_TEXT/SSA": "ass",
    "S_ASS": "ass", "S_SSA": "ass", "S_TEXT/WEBVTT": "vtt", "S_HDMV/PGS": "pgs",
    "S_VOBSUB": "vobsub",
}
# Codec suffix Jellyfin appends to subtitle labels (report only).
JF_SUB_CODEC = {"srt": "SUBRIP", "ass": "ASS", "vtt": "WEBVTT", "pgs": "PGSSUB", "vobsub": "DVDSUB"}
JF_LANG = {"ger": "German", "eng": "English", "jpn": "Japanese"}

TMP_PREFIX = "._trackclean."
log = logging.getLogger("trackclean")


def norm_lang(code):
    code = (code or "").strip().lower()
    if not code:
        return ""
    code = code.split("-")[0]
    if len(code) == 2:
        return ISO1.get(code, code)
    return T_TO_B.get(code, code)


@dataclass
class Track:
    id: int
    uid: int
    type: str          # video / audio / subtitles
    codec_id: str
    lang: str          # normalised, "" when undefined
    file_lang: str     # legacy language as stored in the file
    name: str
    default: bool
    forced: bool
    hi: bool
    events: int = 0      # subtitle frames from the statistics tags / cues
    extra: bool = False  # commentary / audio description
    kind: str = ""       # subs: full / forced / sdh
    lang_guessed: bool = False
    forced_guessed: bool = False

    @property
    def fmt(self):
        return SUB_FORMATS.get(self.codec_id, "other")


@dataclass
class Plan:
    keep: list = field(default_factory=list)       # track ids in output order (audio+subs)
    drop: list = field(default_factory=list)       # Track objects
    props: dict = field(default_factory=dict)      # id -> desired {name, lang, default, forced, hi}
    notes: list = field(default_factory=list)
    audio_fallback: bool = False

    @property
    def remux(self):
        return bool(self.drop)

    def edits(self, tracks):
        """Track ids whose properties differ from the desired state."""
        by_id = {t.id: t for t in tracks}
        out = []
        for tid, p in self.props.items():
            t = by_id[tid]
            if (t.name != p["name"] or t.file_lang != p["lang"] or t.default != p["default"]
                    or t.forced != p["forced"] or t.hi != p["hi"]):
                out.append(tid)
        return out

    def changed(self, tracks):
        return self.remux or bool(self.edits(tracks))


def identify(path):
    out = subprocess.run(["mkvmerge", "-J", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def parse_tracks(info):
    tracks = []
    for t in info.get("tracks", []):
        p = t.get("properties", {})
        file_lang = (p.get("language") or "").lower()
        lang = norm_lang(file_lang)
        if lang in UNDEFINED:
            lang = norm_lang(p.get("language_ietf"))
        if lang in UNDEFINED:
            lang = ""
        tr = Track(
            id=t["id"], uid=p.get("uid", 0), type=t.get("type", ""),
            codec_id=p.get("codec_id", ""), lang=lang, file_lang=file_lang,
            name=p.get("track_name", "") or "", default=bool(p.get("default_track", False)),
            forced=bool(p.get("forced_track", False)), hi=bool(p.get("flag_hearing_impaired", False)),
        )
        if tr.type in ("audio", "subtitles"):
            if not tr.lang:
                for rx, code in TITLE_LANG:
                    if rx.search(tr.name):
                        tr.lang, tr.lang_guessed = code, True
                        break
            tr.extra = bool(p.get("flag_commentary") or p.get("flag_visual_impaired")
                            or EXTRA_RE.search(tr.name))
        if tr.type == "subtitles":
            tr.events = _events(p)
            if tr.forced or (FORCED_RE.search(tr.name) and not FULL_RE.search(tr.name)):
                tr.kind = "forced"
            elif tr.hi or SDH_RE.search(tr.name):
                tr.kind = "sdh"
            else:
                tr.kind = "full"
        tracks.append(tr)
    _guess_forced([t for t in tracks if t.type == "subtitles"])
    return tracks


def _events(props):
    for key in ("tag_number_of_frames", "num_index_entries"):
        try:
            return int(props[key])
        except (KeyError, TypeError, ValueError):
            pass
    return 0


def _guess_forced(subs):
    # WEB-DLs often carry unflagged forced tracks titled like the full one; they
    # have a fraction of the events. ASS is skipped: karaoke/sign tracks skew counts.
    counted = [t for t in subs if t.fmt != "ass" and t.events]
    peak = max((t.events for t in counted), default=0)
    if peak < 200:
        return
    for t in counted:
        if t.kind in ("full", "sdh") and t.events < peak * 0.1 and not FULL_RE.search(t.name):
            t.kind, t.forced_guessed = "forced", True


def resolve(langs, org):
    out = []
    for code in langs:
        code = org if code == "org" else code
        if code and code not in out:
            out.append(code)
    return out


def plan_tracks(tracks, profile_name, org=""):
    prof = PROFILES[profile_name]
    plan = Plan()
    audio_langs = resolve(prof["audio"], org)
    audio = [t for t in tracks if t.type == "audio"]
    subs = [t for t in tracks if t.type == "subtitles"]

    # Audio: wanted languages plus untagged tracks we cannot identify.
    keep_a = [t for t in audio if not t.extra and (t.lang in audio_langs or not t.lang)]
    if audio and not any(t.lang in audio_langs for t in keep_a):
        keep_a = list(audio)
        plan.audio_fallback = True
        plan.notes.append("no wanted audio language found, audio left untouched: "
                          + ",".join(t.lang or "und" for t in audio))
    keep_a.sort(key=lambda t: (_rank(t.lang, audio_langs), audio.index(t)))

    default_audio = None
    if not plan.audio_fallback:
        for code in resolve(prof["default_audio"], org):
            cands = [t for t in keep_a if t.lang == code]
            if cands:
                default_audio = next((t for t in cands if t.default), cands[0])
                break
        if default_audio is None:
            default_audio = next((t for t in keep_a if t.default), keep_a[0] if keep_a else None)
        if default_audio in keep_a:
            keep_a.remove(default_audio)
            keep_a.insert(0, default_audio)
        for t in keep_a:
            # Untagged tracks keep their title, it is all that identifies them.
            plan.props[t.id] = {"name": "" if t.lang else t.name, "lang": t.lang or t.file_lang,
                                "default": t is default_audio, "forced": False, "hi": False}

    # Subtitles: best track per (language, kind); SDH only when no plain full track exists.
    fmt_rank = {f: i for i, f in enumerate(prof["sub_formats"])}
    best = {}
    for t in subs:
        if t.extra or t.lang not in prof["subs"]:
            continue
        key = (t.lang, t.kind)
        rank = (fmt_rank.get(t.fmt, 99), not t.default, not t.forced, subs.index(t))
        if key not in best or rank < best[key][0]:
            best[key] = (rank, t)
    keep_s = []
    for code in prof["subs"]:
        full = best.get((code, "full")) or best.get((code, "sdh"))
        forced = best.get((code, "forced"))
        keep_s += [x[1] for x in (full, forced) if x]

    audio_lang = default_audio.lang if default_audio else ""
    default_sub = None
    if audio_lang and audio_lang != "ger":
        default_sub = next((t for t in keep_s if t.kind != "forced" and t.lang != audio_lang), None)
    if audio_lang and audio_lang not in prof["subs"] and not any(t.kind != "forced" for t in keep_s):
        plan.notes.append(f"no German/English subtitles for {audio_lang} audio, release needs replacing")
    for t in keep_s:
        plan.props[t.id] = {"name": "", "lang": t.lang, "default": t is default_sub,
                            "forced": t.kind == "forced", "hi": t.kind == "sdh"}

    plan.keep = [t.id for t in keep_a + keep_s]
    plan.drop = [t for t in audio + subs if t.id not in plan.keep]
    return plan


def _rank(lang, order):
    return order.index(lang) if lang in order else len(order)


def jf_label(t, props):
    """Approximate Jellyfin 12 label for the report (English UI)."""
    lang = JF_LANG.get(props["lang"], props["lang"] or "Und")
    parts = [lang]
    if t.type == "subtitles":
        if props["hi"]:
            parts.append("Hearing Impaired")
        if props["default"]:
            parts.append("Default")
        if props["forced"]:
            parts.append("Forced")
        parts.append(JF_SUB_CODEC.get(t.fmt, t.codec_id))
    else:
        parts.append(t.codec_id.split("/")[0].replace("A_", ""))
        if props["default"]:
            parts.append("Default")
    return " - ".join(parts)


def describe(path, tracks, plan):
    by_id = {t.id: t for t in tracks}
    lines = [path]
    for tid in plan.keep:
        t = by_id[tid]
        p = plan.props.get(tid)
        was = (f"{t.lang or 'und'} {t.name!r}{' def' if t.default else ''}{' forced' if t.forced else ''}"
               f"{' (few events)' if t.forced_guessed else ''}")
        now = jf_label(t, p) if p else "(untouched)"
        lines.append(f"  keep {t.type[:3]} #{tid:<2} {was:<55} -> {now}")
    others = {}
    for t in plan.drop:
        if t.lang in ("ger", "eng", "jpn", ""):
            lines.append(f"  drop {t.type[:3]} #{t.id:<2} {t.lang or 'und'} {t.name!r}")
        else:
            key = f"{t.type[:3]}:{t.lang}"
            others[key] = others.get(key, 0) + 1
    if others:
        lines.append("  drop " + ", ".join(k if n == 1 else f"{k}x{n}" for k, n in sorted(others.items())))
    lines += [f"  note {n}" for n in plan.notes]
    return "\n".join(lines)


def mkvmerge_args(tracks, plan, src, dst):
    by_id = {t.id: t for t in tracks}
    keep_a = [i for i in plan.keep if by_id[i].type == "audio"]
    keep_s = [i for i in plan.keep if by_id[i].type == "subtitles"]
    args = ["mkvmerge", "-q", "-o", dst]
    args += ["--audio-tracks", ",".join(map(str, keep_a))] if keep_a else ["--no-audio"]
    args += ["--subtitle-tracks", ",".join(map(str, keep_s))] if keep_s else ["--no-subtitles"]
    for tid, p in plan.props.items():
        args += ["--track-name", f"{tid}:{p['name']}", "--language", f"{tid}:{p['lang'] or 'und'}",
                 "--default-track-flag", f"{tid}:{int(p['default'])}",
                 "--forced-display-flag", f"{tid}:{int(p['forced'])}",
                 "--hearing-impaired-flag", f"{tid}:{int(p['hi'])}"]
    order = [t.id for t in tracks if t.type == "video"] + plan.keep
    args += ["--track-order", ",".join(f"0:{i}" for i in order), src]
    return args


def mkvpropedit_args(tracks, plan, path):
    by_id = {t.id: t for t in tracks}
    args = ["mkvpropedit", "-q", path]
    for tid in plan.edits(tracks):
        t, p = by_id[tid], plan.props[tid]
        args += ["--edit", f"track:={t.uid}" if t.uid else f"track:{tid + 1}"]
        if t.name:
            args += ["--delete", "name"]
        if p["lang"] and t.file_lang != p["lang"]:
            args += ["--set", f"language={p['lang']}"]
        args += ["--set", f"flag-default={int(p['default'])}",
                 "--set", f"flag-forced={int(p['forced'])}",
                 "--set", f"flag-hearing-impaired={int(p['hi'])}"]
    return args


def run_tool(args):
    # mkvtoolnix: 0 = ok, 1 = warnings (output is fine), 2 = error
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode > 1:
        raise RuntimeError(f"{args[0]} failed ({res.returncode}): {(res.stdout + res.stderr).strip()[-500:]}")
    if res.returncode == 1:
        log.warning("%s warnings: %s", args[0], (res.stdout + res.stderr).strip()[-500:])


def remux(tracks, plan, src, dst):
    """Remux into a hidden temp file next to dst, verify, then atomically replace dst."""
    size = os.path.getsize(src)
    dst_dir = os.path.dirname(dst)
    if shutil.disk_usage(dst_dir).free < size * 1.05 + (1 << 30):
        raise RuntimeError(f"not enough free space in {dst_dir}")
    tmp = os.path.join(dst_dir, TMP_PREFIX + os.path.basename(dst) + ".tmp")
    try:
        run_tool(mkvmerge_args(tracks, plan, src, tmp))
        verify(src, tmp, tracks, plan)
        shutil.copymode(src, tmp)
        if os.geteuid() == 0:
            st = os.stat(src)
            os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def verify(src, out, tracks, plan):
    before, after = identify(src), identify(out)
    by_id = {t.id: t for t in tracks}
    want = {k: sum(1 for i in plan.keep if by_id[i].type == k) for k in ("audio", "subtitles")}
    want["video"] = sum(1 for t in tracks if t.type == "video")
    got = {k: sum(1 for t in after.get("tracks", []) if t.get("type") == k) for k in want}
    if got != want:
        raise RuntimeError(f"verification failed: tracks {got} != {want}")
    # Container durations are unreliable (dropped tracks running past the video, bogus
    # segment durations), so the video frame count has to match exactly.
    # mkvextract counts differ from the tags by one, so both sides use the same method.
    count = any(t.get("type") == "video" and "tag_number_of_frames" not in t.get("properties", {})
                for t in before.get("tracks", []))
    f0, f1 = _video_frames(before, src, count), _video_frames(after, out, count)
    if f0 != f1:
        raise RuntimeError(f"verification failed: video frames {f1} != {f0}")


def _video_frames(info, path, count=False):
    """Frames per video track from the statistics tags, or counted with mkvextract."""
    frames = []
    for t in info.get("tracks", []):
        if t.get("type") != "video":
            continue
        n = t.get("properties", {}).get("tag_number_of_frames")
        if n is None or count:
            fd, ts = tempfile.mkstemp(prefix="trackclean-", suffix=".txt")
            os.close(fd)
            try:
                run_tool(["mkvextract", "-q", path, "timestamps_v2", f"{t['id']}:{ts}"])
                with open(ts) as fh:
                    n = sum(1 for line in fh if line.strip() and not line.startswith("#"))
            finally:
                os.remove(ts)
        frames.append(int(n))
    return frames


def setup_logging(stderr=True):
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if os.path.isdir("/config/logs") and os.access("/config/logs", os.W_OK):
        fh = RotatingFileHandler("/config/logs/trackclean.txt", maxBytes=1 << 20, backupCount=3)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    if stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        log.addHandler(sh)


def lower_priority():
    try:
        os.nice(10)
    except OSError:
        pass


# --- Sonarr/Radarr "Import Using Script" -------------------------------------

def import_mode(src, dst):
    env = os.environ
    app = "Sonarr" if "Sonarr_SourcePath" in env else "Radarr" if "Radarr_SourcePath" in env else "arr"
    profile = env.get("TRACKCLEAN_PROFILE") or (
        "anime" if env.get("Sonarr_Series_Type", "").lower() == "anime" else "standard")
    org = norm_lang(env.get("Sonarr_Series_OriginalLanguage") or env.get("Radarr_Movie_OriginalLanguage"))
    mode = env.get(f"{app}_TransferMode", "")
    # Any failure falls back to the normal *arr transfer so imports never break.
    try:
        if not (src.lower().endswith(".mkv") and dst.lower().endswith(".mkv")):
            log.info("%s import (%s): not MKV, deferring: %s", app, profile, src)
        elif os.path.exists(dst):
            log.info("%s import (%s): destination exists, deferring: %s", app, profile, dst)
        else:
            lower_priority()
            tracks = parse_tracks(identify(src))
            plan = plan_tracks(tracks, profile, org)
            if plan.changed(tracks):
                log.info("%s import (%s, org=%s, %s):\n%s", app, profile, org or "?", mode,
                         describe(dst, tracks, plan))
                remux(tracks, plan, src, dst)
                if mode == "Move":
                    os.remove(src)
                print("[MoveStatus] RenameRequested", flush=True)
                return 0
            log.info("%s import (%s): already clean, deferring: %s", app, profile, src)
    except Exception:
        log.exception("%s import failed, deferring to normal transfer: %s", app, src)
    print("[MoveStatus] DeferMove", flush=True)
    return 0


# --- Batch mode ---------------------------------------------------------------

class Arr:
    """Minimal Sonarr/Radarr API client using the container's own config.xml."""

    def __init__(self, config="/config/config.xml"):
        root = ET.parse(config).getroot()
        base = (root.findtext("UrlBase") or "").strip("/")
        self.url = f"http://localhost:{root.findtext('Port')}" + (f"/{base}" if base else "")
        self.key = root.findtext("ApiKey")
        self.app = None
        self.items = []  # (path, id, org)
        for app, endpoint in (("sonarr", "series"), ("radarr", "movie")):
            try:
                data = self.call("GET", f"/api/v3/{endpoint}")
            except Exception:
                continue
            self.app = app
            for it in data:
                org = ARR_NAMES.get(((it.get("originalLanguage") or {}).get("name") or "").lower(), "")
                self.items.append((it["path"].rstrip("/") + "/", it["id"], org))
            break
        if not self.app:
            raise RuntimeError("no Sonarr/Radarr API reachable")

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.url + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Api-Key": self.key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")

    def lookup(self, path):
        for prefix, item_id, org in self.items:
            if path.startswith(prefix):
                return item_id, org
        return None, ""

    def rescan(self, ids):
        for item_id in sorted(ids):
            if self.app == "sonarr":
                self.call("POST", "/api/v3/command", {"name": "RescanSeries", "seriesId": item_id})
            else:
                self.call("POST", "/api/v3/command", {"name": "RescanMovie", "movieId": item_id})


def walk(paths):
    for root in paths:
        if os.path.isfile(root):
            yield root
            continue
        for d, dirs, files in os.walk(root):
            dirs.sort()
            for f in sorted(files):
                if f.lower().endswith(".mkv") and not f.startswith("."):
                    yield os.path.join(d, f)


def batch_mode(args):
    lower_priority()
    arr = None
    if not args.no_arr:
        try:
            arr = Arr()
        except Exception as e:
            log.warning("original languages unavailable (%s); use --no-arr to silence", e)
    counts = {"files": 0, "clean": 0, "edit": 0, "remux": 0, "fallback": 0, "error": 0, "skipped": 0}
    touched, report = set(), []
    done = 0
    for path in walk(args.paths):
        counts["files"] += 1
        if time.time() - os.path.getmtime(path) < 600:
            counts["skipped"] += 1
            log.info("skip (modified in the last 10 min): %s", path)
            continue
        item_id, org = arr.lookup(path) if arr else (None, "")
        try:
            tracks = parse_tracks(identify(path))
            plan = plan_tracks(tracks, args.profile, org)
        except Exception as e:
            counts["error"] += 1
            log.error("probe failed: %s: %s", path, e)
            continue
        counts["fallback"] += plan.audio_fallback
        if not plan.changed(tracks):
            counts["clean"] += 1
            if plan.notes:
                print(f"[CLEAN] {describe(path, tracks, plan)}", flush=True)
            continue
        action = "remux" if plan.remux else "edit"
        counts[action] += 1
        if args.verbose or plan.notes:
            print(f"[{action.upper()}] {describe(path, tracks, plan)}", flush=True)
        report.append({"path": path, "action": action, "org": org, "notes": plan.notes,
                       "drop": [f"{t.type}:{t.lang or 'und'}:{t.name}" for t in plan.drop]})
        if args.apply and (args.limit is None or done < args.limit):
            try:
                if plan.remux:
                    remux(tracks, plan, path, path)
                else:
                    run_tool(mkvpropedit_args(tracks, plan, path))
                again = parse_tracks(identify(path))
                if plan_tracks(again, args.profile, org).changed(again):
                    log.warning("not idempotent after %s: %s", action, path)
                done += 1
                if item_id is not None:
                    touched.add(item_id)
                log.info("%s done: %s", action, path)
            except Exception as e:
                counts["error"] += 1
                log.error("%s failed: %s: %s", action, path, e)
    if args.report:
        with open(args.report, "w") as fh:
            json.dump({"profile": args.profile, "counts": counts, "files": report}, fh, indent=1)
    if arr and touched:
        arr.rescan(touched)
        log.info("requested %s rescan for %d items", arr.app, len(touched))
    print(json.dumps({"profile": args.profile, "applied": args.apply, **counts}), flush=True)
    return 1 if counts["error"] else 0


def main(argv):
    if len(argv) == 2 and argv[0] not in ("batch", "show"):
        setup_logging(stderr=False)
        return import_mode(argv[0], argv[1])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("batch")
    b.add_argument("paths", nargs="+")
    b.add_argument("--profile", choices=PROFILES, default=os.environ.get("TRACKCLEAN_PROFILE", "standard"))
    b.add_argument("--apply", action="store_true", help="modify files (default: dry run)")
    b.add_argument("--limit", type=int, help="apply to at most N files")
    b.add_argument("--report", help="write a JSON report")
    b.add_argument("--no-arr", action="store_true", help="skip the *arr API (no original language)")
    b.add_argument("-v", "--verbose", action="store_true", help="print the plan of every changed file")
    s = sub.add_parser("show")
    s.add_argument("file")
    s.add_argument("--profile", choices=PROFILES, default=os.environ.get("TRACKCLEAN_PROFILE", "standard"))
    s.add_argument("--org", default="", help="original language (ISO 639-2)")
    args = ap.parse_args(argv)
    setup_logging()
    if args.cmd == "show":
        tracks = parse_tracks(identify(args.file))
        plan = plan_tracks(tracks, args.profile, norm_lang(args.org))
        action = "remux" if plan.remux else "edit" if plan.changed(tracks) else "clean"
        print(f"[{action.upper()}] {describe(args.file, tracks, plan)}")
        return 0
    return batch_mode(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

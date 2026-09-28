# Media track cleanup (trackclean)

Every movie/episode keeps only German/English tracks (anime: Japanese audio
plus German/English dubs), one subtitle per language and kind, and clean
Matroska flags. Jellyfin builds its labels from language + flags + codec, so
the titles are cleared and the pickers read `German - SUBRIP`,
`German - Erzwungen - SUBRIP`, `English - Hörgeschädigt - SUBRIP`. The codec
suffix itself cannot be turned off in Jellyfin.

## How it works

- `roles/media_services_lxc/tasks/services/trackclean/trackclean.py`
  (python3 + mkvtoolnix) is mounted read-only at `/trackclean` into
  sonarr, radarr, sonarr-anime and radarr-anime. The packages come from the
  `universal-package-install` docker mod; `trackclean.sh` falls back to a
  normal import when they are missing.
- **New downloads**: the *arr "Import Using Script" (Media Management) runs
  `trackclean.sh SRC DST`. The remux *is* the copy into the library, then
  `[MoveStatus] RenameRequested` makes the *arr re-read the media info. Any
  error prints `DeferMove`, so the *arr imports the file untouched.
  Already-clean files are deferred as well.
- **Existing library**: `trackclean.py batch` (dry run unless `--apply`).
  Files that only need flags/titles are edited in place with `mkvpropedit`;
  files losing tracks are remuxed to a hidden `._trackclean.*.tmp` next to
  the original, verified (track counts, exact video frame count) and swapped atomically.
- Log: `/config/logs/trackclean.txt` in each *arr config dir.

## Rules

| | Standard (sonarr, radarr) | Anime (sonarr-anime, radarr-anime) |
|---|---|---|
| Audio kept | German, original language, English | original/Japanese, German, English |
| Default audio | German, else original, else English | original/Japanese |
| Subtitles kept | German, English | German, English |
| Default subtitle | none with German audio; else full German, then English | full German, then English |

- Original language comes from the *arr (`*_OriginalLanguage` on import,
  the API in batch mode). Parasite, Squid Game, Money Heist, Lupin etc. keep
  their original audio.
- Subtitles: per language one full track (plain before SDH) and one forced
  track. Format preference: SRT > ASS > PGS > VobSub (anime: ASS first).
- Forced is taken from the flag, from titles (Forced, Signs, Songs,
  Foreign) or from event counts: an unflagged track with <10% of the
  largest track's events is forced (WEB-DLs often ship those; ASS excluded).
  SDH/CC/HI titles set the hearing-impaired flag.
- Commentary and audio-description tracks are dropped.
- Never removes the last audio: if no wanted language is found (Flow,
  untagged Prison Break S01) the audio stays untouched and a note is logged.
  Untagged tracks named "Deutsch ..." etc. get their language from the title.

## Rollout of the existing library

State on 2026-09-28 (dry run): 2,369 MKVs, ~1,334 remux (8.1 TB) and
~800 flag-only edits. No hardlinks to downloads, so nothing seeding is hit.
Remux runs at ~500 MB/s on the SSD pool, about 4.5 h in total.

1. Deploy: `ansible-playbook playbooks/proxmox.yml --tags media_lxc`.
2. Dry run per instance (inside the container, as `abc`):
   ```sh
   docker exec -u abc sonarr /trackclean/trackclean.py batch /tv /documentaries --report /config/trackclean-dryrun.json
   docker exec -u abc sonarr-anime /trackclean/trackclean.py batch /tv
   docker exec -u abc radarr /trackclean/trackclean.py batch /movies
   docker exec -u abc radarr-anime /trackclean/trackclean.py batch /movies
   ```
3. Apply one instance per wave, each under a ZFS snapshot (on the Proxmox
   host). A single snapshot for all 8.1 TB does not fit into the free space;
   the biggest wave (sonarr, 3.9 TB) does.
   ```sh
   zfs snapshot mediapool@pre-trackclean-sonarr
   docker exec -u abc sonarr /trackclean/trackclean.py batch --apply /tv /documentaries
   # check a few files in Jellyfin, then
   zfs destroy mediapool@pre-trackclean-sonarr
   ```
   `--limit N` applies to the first N files only. After applying, the script
   requests a Rescan per series/movie so the *arr media info is refreshed.
   The release metadata (scene name, custom formats) is kept.
4. Jellyfin: run a library scan (changed mtimes trigger a re-probe). Then
   set subtitle mode "Default" per user, so the file flags drive the choice.
   Remembered track indices (UserData) can point at the wrong track after
   tracks were removed; clear them once.

## Turning it off

`media_services_trackclean_enabled: false` and re-run the role: the import
script is disabled in all four *arr instances. The files already processed
stay as they are.

# App icons

The home-screen icon, favicon and web app manifest (Phil, 2026-11-22).
`base.html` links them on every page.

- `icon.svg`: the source. The Shelves heading's `library-house` glyph
  (`templates/_icons.html`) on Gruvbox dark, inside the middle 80% circle
  that Android keeps when it masks an icon.
- `favicon.svg`: the same, cropped tighter for browser tabs.
- `manifest.webmanifest`: name, colours, icons, `display: standalone`.

Every PNG is rendered from the SVGs. After changing either one:

```bash
cd static/icons
rsvg-convert -w 512 -h 512 icon.svg -o icon-512.png
rsvg-convert -w 192 -h 192 icon.svg -o icon-192.png
rsvg-convert -w 180 -h 180 icon.svg -o apple-touch-icon.png
rsvg-convert -w 32 -h 32 favicon.svg -o favicon-32.png
```

There is no service worker: nothing works offline, which a catalogue behind a
login doesn't need, and nothing is cached that could serve one user's page to
another.

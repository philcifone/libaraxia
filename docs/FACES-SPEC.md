# Faces and placeholders (ROADMAP 16.0c)

From Phil, 2026-11-15. Approved the same day ("Go"). Builds on 16.0a's photos
and 3D item (docs/PHOTOS-VALUE-SPEC.md section 3, `utils/item3d.py`).

## 1. What it is for

Every face of an item's box is "your photo, or else something plain": paper
for a book's pages, card for a VHS sleeve's top, black for its open bottom,
black plastic for a DVD case. This phase lets every face of every type take
a photo, and turns the "something plain" into images an admin chooses:
photographed placeholders (a clamshell's plastic top, a Nickelodeon tape's
orange bottom, a clear DVD shell's edge, a page texture), grouped into named
sets that an owner picks per item.

## 2. Faces, every type

- New photo kind `bottom` (migration 041, an INSERT into `photo_kinds`).
- Every type and format takes back, spine (left), side (right), top and
  bottom, plus the gallery. Vinyl gains a spine (a gatefold's is printed).
- Labels by shape: a book's right side, top and bottom are its pages
  ("Fore-edge", "Top edge", "Bottom edge"); a VHS's spine is "Left side";
  everything else "Spine", "Right side", "Top", "Bottom".
- The 3D view draws every face from its photo when there is one; a book's
  page faces keep the drawn paper otherwise.
- What a shape needs before it turns is unchanged (16.0a `NEEDS`): printed
  faces only. A sleeve's thickness may now come from a spine photo.
- The flat cover box (the Shelf style's item page and library grids, not
  the video-store rack) shows the top and right side faces for every type,
  as VHS does since 16.0a: photo, else chosen placeholder, else default set,
  else the plain colour it has today.

## 3. The placeholder library (admin)

Admin → Placeholders. Global: every user can pick them; only admins add,
crop, rename or delete them.

- Grouped by **medium**, one tab each on the admin page:

  | medium | items |
  |---|---|
  | `book` | books (not audiobooks) |
  | `vinyl` | LP, EP, 7", 10", 12" |
  | `cd` | CD |
  | `cassette` | Cassette |
  | `dvd` | DVD (every non-VHS video) |
  | `vhs` | VHS, sleeve or clamshell alike |

  (Earlier drafts split VHS into sleeve and clamshell bodies with a default
  set each. Phil, 2026-11-16: the names say what a set is, so one VHS tab;
  and nothing automatic, so no defaults.)
- Each placeholder is an image for one face kind (spine, side, top or
  bottom) of one medium, with a name, uploaded through the crop tool
  (Perspective by default). Several per medium and kind. On upload a top or
  bottom is turned a quarter turn if it came in upright, and a spine or
  side if it came in wide (`image_utils.save_photo(shape=)`).
- **Sets**: a named group for one medium ("White clamshell", "Nickelodeon",
  "Clear DVD case", "Black DVD case") with at most one placeholder per face
  kind.
- Tables: `face_placeholders` (id, medium, kind, name, path, created_at),
  `face_sets` (id, medium, name), `face_set_members` (set_id, kind,
  placeholder_id; CASCADE), and `item_faces` (book_id, kind,
  placeholder_id; the owner's choice per face; CASCADE from both sides).
- Deleting a placeholder removes its file and every choice of it; those
  faces go back to the plain look.

## 4. Choosing on an item

- On the edit page's Photos section, each face slot without a photo offers
  the placeholders for that face from the item's medium, and "None". The current choice shows as a
  small preview, marked as a placeholder.
- A row of the medium's sets ("Use a set: Clamshell, Nickelodeon clamshell")
  fills the item's choices in one go (copies its members into
  `item_faces`). Editing a set later does not change items that used it;
  replacing a placeholder's image does (it's the same placeholder).
- The add form for a VHS (and other types with sets) offers the same set
  choice, applied when the item is saved.
- Bulk edit's More menu has **Placeholder set** (where the section has
  sets): fills the selected items' faces from one set, skips items of
  another medium and items that aren't yours, and undoes like any bulk
  edit (each face back to what it had).
- A photo always wins over a placeholder; deleting the photo brings the
  placeholder back.

## 5. Which face shows

For each face, first that exists:

1. the item's photo of that kind;
2. a VHS sleeve only: for the right side, the left side's photo (16.0a);
3. the item's chosen placeholder;
4. the plain look (styles.css "The 3D item").

Nothing is automatic: an item shows a placeholder only where its owner
picked one (Phil, 2026-11-16).

## 6. Sleeve or clamshell

A VHS is a **sleeve** when it has a top photo (front, back, top and a side
show a printed slip sleeve), and a **clamshell** otherwise (front, back and
a side: the sleeve's spine shows through the plastic, and the plastic is
the rest). Same size either way (Phil). The only rule that depends on it
is step 2 above: a sleeve's right side repeats its left side's photo.

## 7. Steps (branch `phase-16c-faces`, a commit each)

1. Bottom kind, every face for every type, labels, 3D bottom face, flat box
   faces for every type (photos only).
2. The library: migration, Admin → Placeholders (upload with crop, rename,
   delete), sets. Later reworked: one tab per medium, no defaults,
   strips turned the right way on upload.
3. Choosing: edit page slots and sets, add form's set, the face resolution
   of section 5 in 3D and on the flat box, sleeve or clamshell.
4. Docs (ARCHITECTURE), tests throughout, screenshots as `claude`.

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

- Grouped by **body**, the kind of thing a face belongs to:

  | body | items |
  |---|---|
  | `book` | books (not audiobooks) |
  | `vinyl` | LP, EP, 7", 10", 12" |
  | `cd` | CD |
  | `cassette` | Cassette |
  | `dvd` | DVD (every non-VHS video) |
  | `vhs_sleeve` | VHS, card slip sleeve |
  | `vhs_clamshell` | VHS, plastic clamshell |

- Each placeholder is an image for one face kind (spine, side, top or
  bottom) of one body, with a name, uploaded through the crop tool
  (Perspective by default). Several per body and kind.
- **Sets**: a named group for one body ("Clamshell", "Nickelodeon
  clamshell", "Clear DVD case", "Black DVD case") with at most one
  placeholder per face kind. One set per body may be the **default**.
- Tables: `face_placeholders` (id, body, kind, name, path, created_at),
  `face_sets` (id, body, name, is_default; one default per body by a partial
  unique index), `face_set_members` (set_id, kind, placeholder_id; CASCADE),
  and `item_faces` (book_id, kind, placeholder_id; the owner's choice per
  face; CASCADE from both sides).
- Deleting a placeholder removes its file and every choice of it; those
  faces fall back to the default set or the plain look.

## 4. Choosing on an item

- On the edit page's Photos section, each face slot without a photo offers
  the placeholders for that face from the item's bodies (a VHS sees both
  sleeve and clamshell ones), and "Default". The current choice shows as a
  small preview, marked as a placeholder.
- A row of the body's sets ("Use a set: Clamshell, Nickelodeon clamshell")
  fills the item's choices in one go (copies its members into
  `item_faces`). Editing a set later does not change items that used it;
  replacing a placeholder's image does (it's the same placeholder).
- The add form for a VHS (and other types with sets) offers the same set
  choice, applied when the item is saved.
- A photo always wins over a placeholder; deleting the photo brings the
  placeholder back.

## 5. Which face shows

For each face, first that exists:

1. the item's photo of that kind;
2. a VHS sleeve only: for the right side, the left side's photo (16.0a);
3. the item's chosen placeholder;
4. the default set of the item's body;
5. the plain look (styles.css "The 3D item").

## 6. Sleeve or clamshell

A VHS is a **sleeve** when it has a top photo (front, back, top and a side
show a printed slip sleeve), and a **clamshell** otherwise (front, back and
a side: the sleeve's spine shows through the plastic, and the plastic is
the rest). The body follows: `vhs_sleeve` or `vhs_clamshell`, which decides
the default set used in step 4 above. Same size either way (Phil). A VHS
with only a cover is a clamshell by this rule, so once an admin makes a
default clamshell set, every such tape's flat box shows it; that is wanted
(Phil: most VHS have covers only, and can be updated).

## 7. Steps (branch `phase-16c-faces`, a commit each)

1. Bottom kind, every face for every type, labels, 3D bottom face, flat box
   faces for every type (photos only).
2. The library: migration, Admin → Placeholders (upload with crop, rename,
   delete), sets with a default per body.
3. Choosing: edit page slots and sets, add form's set, the face resolution
   of section 5 in 3D and on the flat box, sleeve or clamshell.
4. Docs (ARCHITECTURE), tests throughout, screenshots as `claude`.

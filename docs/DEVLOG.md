# Dev log

The original development diary and to-do list, moved here from the README on 2026-11-02. Kept as written. Current open work lives in [ROADMAP.md](../ROADMAP.md).

## Original to-do list

- [x] Backup project files!!
- [x] Have fun!!!!!
#### Frontend
- [x] Fix tile text alignment
- [x] Add Author to tile
- [x] Add better back to list on search page inside search container
- [x] Fix add book button
- [x] Style main page search bar add sort
- [x] Heading on Add Book page
- [x] Update book details style to match
- [x] Hamburger menu and side bar
- [x] Add book floating button
- [x] View more button for description 
- [x] Fix collections toolbar (show read state)
- [x] Added tailwind css
- [x] Better search bar functionality
- [x] Better back to catalog button
- [x] Refactor styles.css
- [x] Make add & edit book pages prettier!!
- [x] Better fonts
- [x] better mobile on book details page
- [ ] Side scroll of books on collections page
- [ ] separate recent books/reviews feed/list?
- [x] Test Docker packaging
- [x] Release docker packaging

#### Backend
- [x] Fetch book descriptions
- [x] Multi-user creation & login authentication
- [x] Sort catalog feature
- [x] Admin only access to CRUD functions
- [x] Search function
- [x] Version Control
- [x] Fix image upload in add_image route
- [x] Image resize/optimize during upload
- [x] Refactor code, add blueprints
- [x] secret key to server/dev env instead of codebase
- [x] Remove books table read column (will be a future user table column)
- [x] Add rating & comments
- [x] Improve & fix bookshelves (collections, now reading lists)
- [x] auto image download
- [x] Cover image fetch script/button (auto fetch during add but user can replace in add and edit) - revisit
- [x] User book details
- [x] User profile
- [x] Add "DNF" section to reading status & list
- [x] Genre & subtitle add to API fetch & book details
- [x] Filter options!!! (year read, year published, page count, genre, is_read, etc.)
- [x] Export to spreadsheet/csv
- [x] User created bookshelves/collections
- [ ] Admin & user settings

### 📅 2024-12-30

#### Updated a lot of frontend
 - tailwind css - added but not used
 - vanishing header bar
 - hamburger menu and sidebar
 - moved "collections" to "user profile", switching name to "reading list"
 - need to create ability for users to create their own collections for collections page

### 📅 2025-01-01
#### Switched to Claude AI for troubleshooting, more frontend updates, some backend
- Better refactoring of blueprints.books.py to utils.book_utils.py
- Fixed cover fetch
- Layouts for book details and rate & review are much cleaner and polished
- More symbols/icons in use for UX/UI
- Better sidebar features
- User profile password and email update

### 📅 2025-01-05 

#### Lots of search and filtering advancements today, plus csv export

- Implemented title/author search functionality 
- Added CSV library & user info export
- Enhanced book addition with auto-fill  
- Improved cover image fetching and quality 
- Refined UI/UX with smoother transitions 
- Added reading statistics dashboard 
- Enhanced filter and sort capabilities 
- Implemented tag management system
- Created custom collections
- Started barcode scanner feature

### 📅 2025-01-22 

#### Been awhile since I updated after starting other projects. I started to rebuild this in React but realized it would be easier to simply add tailwindcss since the backend seems to function quite well here.
 - Updated tailwindcss for:
   - search/sort/filter
   - sidebar
   - add book
   - book details
   - index
- Added google books api key to book utils and books route - unsure if working!

needs addressed:
- better mobile style on book details - centered
- api title search and display on add book, need to test! - javascript??
- search bar inside top navbar, sort/filter dropdown.
  - sort reset button instead of on change?
- untracked read status not resetting? others work, low priority

#### Finished with changing all the templates to tailwind css and fixed the  api!
- Commited and pulled from repo to prod server and works!
- Tried updating search/navbar/sidebar into something more modern but couldn't get it.
- almost forgot to add the google api key :)

### 📅 2025-01-23
#### Images werent being added from the title/author search selection
 - mostly fixed after excruciating debugging.
 - Author and genre info are not fetching from the json data, see console, utils, and books.py.
 - see diff between old and new add_books.js, and old scripts.js (comment: populate data, fillBookForm)??
 - need to add "selected" javascript to button once the book data is fetched and populated below
 - need to add "no-cover.png" to prod server, or just do text placement. JavaScript goes brrrrr looking for it if it isn't there.
- WOOHOO fixed the search, cover fetch, and info fetch. Updated styles, working on fonts. Cant quite get it.
   
### 📅 2025-03-26
#### Docker packaging!
- Been awhile since any meaningful updates! Happy to have docker packaging figured out.
- trying to add github workflows, might be helpful.


# Libaraxia


![Libaraxia](static/git/libaraxiaAlpha.png)
![Sidebar](static/git/libaraxiaSidebar.png)
![Book Details](static/git/libaraxiaDetails.png)
![Rate & Review](static/git/libaraxiaRateReview.png)
![Book Details](static/git/libaraxiaProfile.png)

# 🚀 Project Overview

Libaraxia is a modern web application designed to help you catalog and manage your personal library with style and efficiency. Built with Flask and SQLite, it offers a seamless interface for organizing your book collection, tracking your reading progress, and maintaining your literary life. What started as a hobbyist project has evolved into a feature-rich library management system. While it's still growing and improving, it's already a robust solution for personal library organization.

## 🛠️ Installation 

Currently, Libaraxia is in active development and not recommended for production use. However, if you're feeling adventurous: 

1. Clone the repository 
2. Set up a virtual environment 
3. Install required packages (requirements.txt coming soon!) 
4. Initialize SQLite database with the provided create_database.sql file and run:

```shell
sqlite3 your_database.db < create_database.sql
``` 

5. Configure your environment variables 
6. Run with Flask Detailed installation instructions and proper packaging are on the roadmap!

### ✨ Features

- Tiled library view
- Add/edit/delete book
- ISBN fetch auto fill
- Book title and author search & autofill
- Catalog search
- Catalog sort
- Catalog filter
- User cover upload
- Account register (admin only)
- Multi-user login & authentication
- Email and Password update
- Library & user review csv export
- Custom book tags per user
- Custom collections per user
- Rating & comment system per user

### 🚧 Future Feature Ideas

- Barcode scanner
- Better mobile focused UI
- Admin & user settings
- Shelf/library share

### 💡 Contributing 

Found a bug? Have a feature idea? Contributions are welcome! While this started as a personal project, I believe in the power of community-driven development, and I am not a trained developer. This has been the product of a lot of AI collaboration, and I'd love for experienced human eyes to check this out. ***PLEASE*** feel free to: 

- Open issues for bugs or feature requests 
- Submit pull requests (I've never made it this far with github so bear with me as I learn to do more than commit/push/pull)
- Share your ideas and feedback 
- Help with documentation

### 📝 To Do:

- [ ] Backup project files!!
- [ ] Have fun!!!!!
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
- [ ] Better back to catalog button
- [ ] Refactor styles.css
- [ ] Make add & edit book pages prettier!!
- [ ] Light & dark mode toggle/color themes
- [ ] Better fonts
- [ ] Side scroll for collections page

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
- [ ] Sort/filter bugs
- [ ] Admin & user settings
- [ ] Switch to using SQLalchemy and migrate to different SQL?
- [ ] React or Swift port?

### 📅 2024-12-30

#### Updated a lot of frontend
 - tailwind css
 - vanishing header bar
 - hamburger menu and sidebar
 - moved "collections" to "user profile", switching name to "reading list"
 - need to create ability for users to create their own collections for collections page

### 📅 2025-1-1
#### Switched to Claude AI for troubleshooting, more frontend updates, some backend
- Better refactoring of blueprints.books.py to utils.book_utils.py
- Fixed cover fetch
- Layouts for book details and rate & review are much cleaner and polished
- More symbols/icons in use for UX/UI
- Better sidebar features
- User profile password and email update

### 📅 2025-1-5 

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

--- 
Built with 📚 and ☕ and 🥃 by a book lover, for book lovers.
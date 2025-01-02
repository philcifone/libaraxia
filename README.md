# Libaraxia


![Libaraxia](static/git/libaraxiaAlpha.png)
![Sidebar](static/git/libaraxiaSidebar.png)
![Book Details](static/git/libaraxiaDetails.png)
![Rate & Review](static/git/libaraxiaRateReview.png)
![Book Details](static/git/libaraxiaProfile.png)

# Project scope:

A self hosted personal library catalog. Accessible via web app to easily list, add, edit, and delete books from one's personal collection. Frontend in HTML and CSS and backend is SQLite and Flask (python). 

This is a beginner project I'm developing to achieve the goal of cataloging my personal library. It is a basic CRUD application, that sports a few additional features right now, although I'm still adding and testing more. I'm not much of a developer, and I am learning as I go. It is a bit of a hobby project I'm trying to to take seriously. Thus, if you find this interesting or useful and want to offer feedback I will happily listen!

## Usage & Installation

Anyone stumbling across this is absolutely welcome to use or fork this under the GPL license I guess? I **strongly recommend against it** in it's current form. I guess all you would need to do is setup the users and books tables (listed below) in a sqlite3 library.db and downloading all the flask packages (I havent set up requirements.txt yet) but you are on your own.

### Existing features:
- Tiled homepage
- Add book
- Edit entry
- Delete entry
- ISBN fetch
- Search
- Cover upload
- Catalog sort
- Account register
- Multi-user login & authentication
- Email and Password update

### Future features:
- Rating system
- Comment system
- User filter
- Custom shelf collections
- Share shelf
- Barcode scanner
- Better mobile UI
- General add book search?

### To Do:

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
- [x] Add book button
- [x] View more button for description 
- [x] Fix collections toolbar (show read state)
- [x] Added tailwind css
- [ ] Refactor styles.css
- [ ] Make add & edit book pages prettier!!
- [ ] Light & dark mode toggle/color themes
- [ ] Better fonts

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
- [ ] User created catalogs
- [ ] Replace image on edit?
- [ ] Setup email in flask
- [ ] Genre & subtitle add to book details
- [ ] Filter options (year read, year published, page count, genre, is_read, )
- [ ] Admin dashboard
- [ ] Update to better SQL? SQLalchemy?
- [ ] Export to spreadsheet/csv

### 2024-12-30

#### Updated a lot of frontend
 - tailwind css
 - vanishing header bar
 - hamburger menu and sidebar
 - moved "collections" to "user profile", switching name to "reading list"
 - need to create ability for users to create their own collections for collections page

### 2025-1-1
#### Switched to Claude AI for troubleshooting
- Layouts are much cleaner and polished
- More symbols
- Better sidebar
- Better refactoring of add books to book_utils

#### Tables Layout

##### Users

user_id (Primary Key)
username
password_hash
email
is_admin (Boolean, for admin tools)

###### Collections (Reading Lists)

collection_id (Primary Key)
user_id (Foreign Key to Users)
book_id (Foreign Key to Books)
status (Enum: 'read', 'want to read', 'currently reading')

###### Read Data

read_data_id (Primary Key)
user_id (Foreign Key to Users)
book_id (Foreign Key to Books)
date_read
rating
comment

---
#### To Implement:
###### User Book Details
user_book_id (primary key?)
user_id(Foreign Key to Users)
book_id (Foreign Key to Books)
tags
date_purchased
price
condition
location

###### User Collections
user_collection_id (primary key)
user_id
collection_name
book_id (list, '1', '2', '3' ?)

(new custom user database, empty)
button "Create new collection" > input "Name of collection" > add bok


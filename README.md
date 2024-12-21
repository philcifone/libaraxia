# Libaraxia

# Project scope:

A self hosted personal library catalog. Accessible via web app to easily list, add, edit, and delete books from one's personal collection. 

This is a beginner project I'm developing to achieve the goal of cataloging my personal library. It is a basic CRUD application, that sports a few additional features right now, although I'm still adding and testing more. I'm not much of a developer, and I am learning as I go. Thus, if you find this interesting or useful and want to offer feedback I will happily listen!

## Frontend:

HTML and CSS

## Backend:

SQLite & Flask

## Usage & Installation

Anyone is absolutely welcome to use or fork this under the GPL license but I strongly recommend against it in it's current form. As I said previously it's missing multi-user login, authentication, and sanitized inputs—for now. I'm still learning and do not feel comfortable deploying it as any sort of full fledge self hosted application for public use just yet.

That said, if you were to clone the repo and set up your own SQLite3 database with the following layout in the project folder you should, in theory, have yourself a basic CMS application after you run 'python3 app.py' on the command line to start a debugging environment. After that, you're on your own for production web server deployment.

```sql
DATABASE LAYOUT;
```

### Known Issues
There is sloppiness all over the place right now. I'm sure the HTML is not pretty according to best practices, and it seems CSS styles are fighting for specificity. I'm sure there's also redundancy causing performance overhead from the python routes that could be optimized as well. The SQL database inputs also need sanitized. It also does not support multi-user login or authentication yet, but I intend on cleaning up the code and implementing all of these features in the near future. 

### Existing features:
- Tiled homepage
- Add book
- Edit entry
- Delete entry
- ISBN lookup
- Search
- Cover upload
- Catalog sort

### To Do:

- [ ] Backup project files!!
- [ ] Have fun!!!!!!
#### Frontend
- [x] Fix tile text alignment
- [x] Add Author to tile
- [ ] Add better back to list on search page inside search container
- [ ] Fix add book button
- [ ] Style main page search bar add sort
- [ ] Make add & edit book pages prettier
- [ ] Make book details page prettier
- [x] Update book details style to match
- [ ] Light & dark mode toggle (tailwind css?)

#### Backend
- [x] Search function
- [x] Version Control
- [x] Fix image upload in add_image route
- [ ] Sanitize SQL database inputs
- [ ] Image resize/optimize during upload
- [ ] Cover fetch script/button (auto fetch during add but user can replace in add and edit)
- [ ] Genre fetch
- [x] Remove read status (will be a future user feature)
- [x] Fetch book descriptions
- [ ] Multi-user creation & login authentication
- [ ] user "bookshelves" (collections)
- [x] sort catalog feature
#### potential future features:
- rating system
- comment system
- multi-user login & authentication
- barcode scanner
- mobile integration
- react
- tailwind css
- bookshelf collections

#### User Info
username
email
password

#### User Book Collections
read
want to read

#### User Read Data
date read
rating
comment
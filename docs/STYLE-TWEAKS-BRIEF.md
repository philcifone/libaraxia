# style tweaks pass - deep dive

Enter plan mode.

### abstract

Please refer to this ‘style-tweaks.md’ brief and my notes and write a SPEC for a deep dive into each theme and page. The overall look and feel of each theme is already astounding, truly phenomenal work. Not looking to polish or overhaul anything, but to fine tune.

Small inconsistencies have fallen through the cracks as we built tooling such as crop, bulk edit, etc. This phases scope is only to peruse the application, its themes, pages, and maintain styling on elements and maintain consistency and a pleasant UI across them. Again, no overhauls, no flashy upgrades or CSS animations such as hover or glow besides what already exists. It’s mostly an audit/review. I anticipate only minor style tweaks, finding the inconsistencies is the major goal, and an efficient plan for you & execution to fix them is the goal.

Success on my end is when I stop finding things to tweak. Success on your end aside from search, find, gather, report, plan, and execute, should also entail any css ‘refactoring’ (unsure if correct term, clarify if not what I describe) but being able to make one adjustment to one element should update the element across the entire theme, when possible, without changing the current styling of elements. I.e. the bookcase, bookshelf grid, placeholder covers, media box design, etc. 

### workflow
Continue working as you are, create tests as needed, check any tests failure logs when they occur. Anything outside of the scope outlined below, take note of, but do not change (fix any thing I’ve outlined, blatant inconsistencies with theme you don’t need my intervention for, I.e button corners, font, etc.) during any refactoring unless explicitly approved by me. 

## shelf theme

So far the other themes look good, it’s this theme I’m finding the tweaks for. This isn’t all encompassing.
### rules
- book boxes sit on shelves
- any card with a cover (exclude add \[media\]) should be wrapped in bookcase and have book sitting on the shelf.
- Headings should also be on top of the page wrapped in bookcase
- add subtle drop shadow to bottom shelf underneath book, keep the one behind but ensure lighting makes sense.
### friend profile
- the route from friends tab in side bar takes you to their shelf, I feel like it should take you to their profile. The profile button on the bottom should instead read “See their shelf” and link as such. remove the direct shelf links from the books/movies/music quantity info subtitle.
- Friends profile card 
    - remove \[x\] / remove friend function buttons are unclear and poorly styled. The remove button should be clear about what your friend is being removed from. (Household?) 
    - Could we include info about if this friend is in your household here or something? Maybe add a ‘N books in common’ and their reading goal? A sort of “friend at a glance” info.
- using the accent color for active tabs on user info (overview/insights) makes it look like the other tab is active. When overview is selected the line kind of breaks the visual flow and if you look over it insights while overview is selected it looks like a seamless file folder. Thus making it look like you’re looking at insights rather than overview.

### friends page
- these friend cards should have bookcase wrap

### add media page
- “Add a \[media\]” heading should be moved to a heading card above the search box. Wrap only the heading in bookcase. 
### reviews page
- We should utilize the bookcase grid here too, and each shelf should be an existing review category. With each shelf keeping the side scroll styling.

### activity page
- straighten up the elements inside the card: lower the book box to sit on shelf, center title underneath user activity details, heart button needs more bottom padding, etc.) should be balanced.
- Move book box to the bottom so it sits on the shelf
- 

### \[media\] details
- title for books, title & icon for video/music should be in a book case wrapped heading outside of the \[media\] details card.
### wishlist 
- should use bookcase grid from the books/movies/music shelf grids

### general
- action descriptions are overly wordy, can we be a little more short and direct, but retain the warm, friendly tone and information provided? - low priority, I can always reword stuff later myself. I like having your explanations around as I get used to the updates, it would just be nice to be a little less wordy.
- Black font in headings and book placeholder covers on light mode feels harsh with the wooden bookcase vibe, suggest a dark brown maybe? White on dark mode seems okay, but could benefit from a very very very light cream.
- I’m thinking of a light glare/shimmer on all the covers like we have on the Easter egg video rental store shelf. 
    - Question before implementing: can we use mobile users accelerometer to add a glare/shimmer response to movement if they move their phone as such? 
- Toggle for “rounded cards” or “themed” cards as toggle (circle/square) and in appearance settings under all themes.
    - I’m having trouble figuring out which cards should have the bookcase wrap. I have a rule about this up top, but I seem to be breaking it here as I poke around and list design tweaks so if you could help me with UI input, it would be appreciated. (Which cards should have bookcase wrap, essentially.)

Still checking other themes as of 20261112 2300
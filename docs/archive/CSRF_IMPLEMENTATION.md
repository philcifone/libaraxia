# CSRF Protection Implementation Guide

## What Was Done

### 1. Installed Flask-WTF
```bash
pip install flask-wtf
```

Flask-WTF has been added to `requirements.txt`.

### 2. Configured CSRF Protection in app.py

Added CSRF protection initialization:
```python
from flask_wtf.csrf import CSRFProtect

# In create_app()
csrf = CSRFProtect(app)
```

###  3. Updated All HTML Forms

All HTML templates with `<form>` tags now include a CSRF token:
```html
<form method="POST" action="...">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
    <!-- rest of form -->
</form>
```

Updated templates:
- login.html
- register.html
- admin_settings.html (6 forms)
- add_book.html
- edit_book.html
- book_detail.html
- collections.html
- rate_review.html
- user.html
- wishlist.html
- _search_sort_filter.html
- activity_feed.html

### 4. JavaScript/AJAX Support

Added helper functions to `static/script.js`:

```javascript
// Get CSRF token
function getCSRFToken() {
    const tokenInput = document.querySelector('input[name="csrf_token"]');
    if (tokenInput) return tokenInput.value;
    return null;
}

// Add CSRF to FormData
function addCSRFToFormData(formData) {
    const token = getCSRFToken();
    if (token) formData.append('csrf_token', token);
    return formData;
}

// Get headers with CSRF
function getCSRFHeaders() {
    const token = getCSRFToken();
    return {
        'X-CSRFToken': token,
        'Content-Type': 'application/json'
    };
}
```

Updated fetch calls in:
- static/script.js (3 fetch calls)
- templates/admin_settings.html (2 AJAX requests)

### 5. Files That Still Need CSRF Token Updates

The following JavaScript files contain fetch calls that may need CSRF tokens:

**HIGH PRIORITY:**
- `static/tags.js` - tag add/remove operations
- `static/add_book.js` - book search and selection
- `static/wishlist.js` - wishlist operations
- `static/edit_book.js` - fetch cover operations

**LOWER PRIORITY (Read-only):**
- Most GET requests don't need CSRF tokens

## How to Test

### 1. Basic Test - Try to Submit a Form

1. Start your Flask app:
   ```bash
   python app.py
   ```

2. Try to login or register - it should work normally

3. Try to submit any admin form - should work

### 2. Security Test - Try Without CSRF Token

Open browser console and try:
```javascript
// This should FAIL with 400 Bad Request
fetch('/admin/create_user', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({username: 'hack', email: 'hack@test.com', password: 'hack123'})
})
```

You should see a `400 Bad Request` error with message about missing CSRF token.

### 3. With CSRF Token (should work)

```javascript
const token = document.querySelector('input[name="csrf_token"]').value;
fetch('/some/endpoint', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': token
    },
    body: JSON.stringify({...})
})
```

## Remaining Tasks

### Update Remaining JavaScript Files

You need to update these files to include CSRF tokens:

#### static/tags.js
```javascript
// Add at top of file
// (Copy helper functions from script.js or import them)

// Update fetch calls:
fetch('/tags/add', {
    method: 'POST',
    headers: getCSRFHeaders(),  // ADD THIS
    body: JSON.stringify({ book_id, tag_name })
})
```

#### static/add_book.js
```javascript
// For POST requests only:
fetch('/books/select_search_result', {
    method: 'POST',
    headers: getCSRFHeaders(),  // ADD THIS
    body: JSON.stringify({ bookData })
})
```

#### static/wishlist.js
```javascript
// Similar updates for POST requests
```

#### static/edit_book.js
```javascript
// Similar updates for POST requests
```

## Common Patterns

### HTML Forms
Always add after `<form>` tag:
```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
```

### JavaScript FormData
```javascript
const formData = new FormData();
addCSRFToFormData(formData);  // Helper function
```

### JavaScript JSON
```javascript
fetch(url, {
    method: 'POST',
    headers: getCSRFHeaders(),  // Helper function
    body: JSON.stringify(data)
})
```

## Troubleshooting

### "CSRF token missing" Error

1. Check that the form has the hidden input
2. Check that JavaScript has access to the token
3. Verify the token is being sent in the request (check Network tab in DevTools)

### Token is sent but still fails

1. Make sure SECRET_KEY is set properly in your `.env`
2. Check that CSRFProtect is initialized before routes are registered
3. Verify the session is working (cookies enabled)

### AJAX Requests Failing

1. Ensure you're using the helper functions from script.js
2. For FormData: use `addCSRFToFormData(formData)`
3. For JSON: use `headers: getCSRFHeaders()`

## Security Best Practices

1. **Never disable CSRF protection** except for specific API endpoints that use other auth methods
2. **Use HTTPS in production** - CSRF tokens can be intercepted over HTTP
3. **Keep SECRET_KEY secret** - rotate it if compromised
4. **Test thoroughly** - especially after updates

## Next Steps

1. Update the remaining JavaScript files (tags.js, add_book.js, wishlist.js, edit_book.js)
2. Test all forms and AJAX operations
3. Consider adding CSRF exemption for specific API endpoints if needed (rare)
4. Add CSRF protection to any new forms you create

## Notes

- CSRF protection is now ENABLED by default on all POST, PUT, DELETE, PATCH requests
- GET requests don't need CSRF tokens
- The token is unique per session
- Tokens expire when the session expires

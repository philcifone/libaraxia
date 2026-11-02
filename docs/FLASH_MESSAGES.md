# Unified Flash Message System

## Overview

The application now uses a unified flash message system that provides:
- **Auto-dismissal** after 5 seconds (configurable)
- **Manual close buttons** for immediate dismissal
- **Smooth animations** (slide in/out)
- **Consistent styling** across all pages
- **Toast-style notifications** (fixed position, non-intrusive)

## Usage

### In Templates

Simply include the flash messages component in your template:

```html
{% include '_flash_messages.html' %}
```

This should be placed near the top of your `<body>` tag, typically right after the sidebar or navigation.

### In Python (Flask Routes)

Use the standard Flask `flash()` function:

```python
from flask import flash

# Success message
flash('User created successfully!', 'success')

# Error message
flash('Failed to update email', 'error')

# Then redirect
return redirect(url_for('admin.settings'))
```

### In JavaScript (AJAX/Dynamic)

For dynamically showing messages without a page reload:

```javascript
// Show a success message
showFlashMessage('success', 'Profile updated successfully!');

// Show an error message
showFlashMessage('error', 'Failed to upload file');

// Show a message without auto-dismiss
showFlashMessage('success', 'Important: Read this carefully', false);
```

## Configuration

### Auto-Dismiss Time

To change the auto-dismiss duration, edit `FLASH_DISMISS_TIME` in `templates/_flash_messages.html`:

```javascript
const FLASH_DISMISS_TIME = 5000; // milliseconds (default: 5 seconds)
```

### Styling

Flash messages use these color schemes:
- **Success**: Green background (`bg-green-500`)
- **Error/Danger**: Red background (`bg-red-500`)

To customize, edit the classes in `templates/_flash_messages.html`.

## Features

### 1. Auto-Dismissal
All flash messages automatically disappear after 5 seconds (configurable).

### 2. Manual Dismissal
Users can click the × button to immediately close any message.

### 3. Smooth Animations
- **Slide-in** animation when messages appear
- **Slide-out** animation when messages are dismissed
- Animations are 300ms long

### 4. Responsive Design
Messages are positioned at `top-20 right-4` and have a max width to ensure they don't overflow on mobile devices.

### 5. Stack Multiple Messages
Multiple messages stack vertically with proper spacing.

## Implementation Details

### Files Modified
- `templates/_flash_messages.html` - New unified component
- `templates/admin_settings.html` - Updated to use new system
- `templates/user.html` - Updated to use new system

### Backward Compatibility
The new system is fully compatible with existing Flask `flash()` calls. No changes needed to Python code.

### JavaScript API

The component exposes two functions globally:

#### `dismissFlash(button)`
Manually dismiss a flash message.
- **Parameters**: `button` - The close button element (usually `this` in onclick)
- **Usage**: `onclick="dismissFlash(this)"`

#### `showFlashMessage(category, message, autoDismiss)`
Programmatically create a flash message.
- **Parameters**:
  - `category` (string): 'success' or 'error'
  - `message` (string): The message text
  - `autoDismiss` (boolean, optional): Whether to auto-dismiss (default: true)
- **Usage**: `showFlashMessage('success', 'Saved!')`

## Testing

To test the flash message system:

1. **Server-side flash (admin page)**:
   - Go to `/admin/settings`
   - Create a new user or modify an existing one
   - Observe the flash message appears, can be closed, and auto-dismisses

2. **Client-side flash (profile page)**:
   - Go to `/user/[your-username]`
   - Edit your email or username
   - Observe the success message appears dynamically

3. **Manual testing**:
   - Open browser console on any page with the component
   - Run: `showFlashMessage('success', 'Test message')`
   - Verify message appears and auto-dismisses
   - Run: `showFlashMessage('error', 'Test error', false)`
   - Verify message appears and does NOT auto-dismiss

## Future Enhancements

Potential improvements you could add:
- Different colors for warning/info categories
- Sound notifications
- Configurable positions (top-left, bottom-right, etc.)
- Progress bar showing time until auto-dismiss
- Pause auto-dismiss on hover
- Message history/log

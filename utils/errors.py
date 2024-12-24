from flask import flash, redirect, url_for

def unauthorized(error):
    flash('You must be logged in to access this page.', 'danger')
    return redirect(url_for('auth.login'))  # Adjust route name if it's under a blueprint

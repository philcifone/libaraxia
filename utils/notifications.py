"""How many things are waiting for a user on the Notifications page: pending
friend requests, household invites and unread notifications. Shown next to
the Notifications link in the sidebar (app.py's context processor) and by
the JSON route friends.notification_count."""


def unread_counts(conn, user_id):
    """{'friend_requests', 'notifications', 'household_invites', 'count'}."""
    friend_requests = conn.execute(
        "SELECT COUNT(*) FROM friend_requests WHERE receiver_id = ? AND status = 'pending'",
        (user_id,)).fetchone()[0]
    # Friend requests are counted above, not again as notifications
    notifications = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0 AND type != 'friend_request'",
        (user_id,)).fetchone()[0]
    household_invites = conn.execute(
        'SELECT COUNT(*) FROM household_invites WHERE invitee_id = ?', (user_id,)).fetchone()[0]
    return {'friend_requests': friend_requests, 'notifications': notifications,
            'household_invites': household_invites,
            'count': friend_requests + notifications + household_invites}

"""Households (shared libraries): invites, joining and leaving.

A household is the set of `library_members` rows sharing a `library_id`.
Each has one 'owner' (whoever started it) and any number of 'member's;
a user is in at most one household.

Rules (Phase 4):
- Nobody is added without consent. The owner, or someone not yet in a
  household, invites a friend (`household_invites`); the friend accepts or
  declines from the notifications page.
- Only the owner can remove a member; anyone can leave. When the owner
  leaves, the longest-standing member takes over. A household left with
  one person is dissolved, since a household of one shares nothing.
- Admins can still add and remove members directly (admin settings).

Functions take the caller's connection and leave committing to the caller.
Errors a user may see are raised as HouseholdError with a safe message.
"""
from models import is_friends_with


class HouseholdError(Exception):
    """A refused household action; the message is safe to show."""


def membership(conn, user_id):
    """The user's library_members row (library_id, role), or None."""
    return conn.execute('SELECT library_id, role FROM library_members WHERE user_id = ?',
                        (user_id,)).fetchone()


def can_invite(conn, user_id):
    """Owners invite into their household; someone in none starts one."""
    row = membership(conn, user_id)
    return row is None or row['role'] == 'owner'


def pending_invite(conn, inviter_id, invitee_id):
    return conn.execute('SELECT * FROM household_invites WHERE inviter_id = ? AND invitee_id = ?',
                        (inviter_id, invitee_id)).fetchone()


def invite(conn, inviter_id, invitee_id):
    """Invite a friend into the inviter's household."""
    if inviter_id == invitee_id:
        raise HouseholdError("You can't invite yourself.")
    if not is_friends_with(inviter_id, invitee_id):
        raise HouseholdError('You can only invite friends to your household.')
    if not can_invite(conn, inviter_id):
        raise HouseholdError('Only the owner of your household can invite people.')
    if membership(conn, invitee_id):
        raise HouseholdError('They are already in a household. They need to leave it first.')
    if pending_invite(conn, inviter_id, invitee_id):
        raise HouseholdError('You have already invited them.')
    # No notifications row: like friend requests, pending invites are listed
    # (and counted in the badge) straight from their own table
    conn.execute('INSERT INTO household_invites (inviter_id, invitee_id) VALUES (?, ?)',
                 (inviter_id, invitee_id))


def accept(conn, invite_id, user_id, user_name):
    """Accept an invite addressed to user_id: join the inviter's household.

    Returns the inviter's username. The invite is checked again here, since
    things may have changed since it was sent (friendship ended, inviter
    joined someone else's household, the user joined one).
    """
    inv = conn.execute('''
        SELECT i.id, i.inviter_id, u.username AS inviter_name
        FROM household_invites i JOIN users u ON u.id = i.inviter_id
        WHERE i.id = ? AND i.invitee_id = ?
    ''', (invite_id, user_id)).fetchone()
    if not inv:
        raise HouseholdError('Invite not found.')
    inviter_id = inv['inviter_id']
    # The invite is used up whatever happens next
    conn.execute('DELETE FROM household_invites WHERE id = ?', (invite_id,))

    if membership(conn, user_id):
        raise HouseholdError('You are already in a household. Leave it first.')
    if not is_friends_with(user_id, inviter_id) or not can_invite(conn, inviter_id):
        raise HouseholdError('That invite is no longer valid.')

    owner_row = membership(conn, inviter_id)
    if owner_row:
        library_id = owner_row['library_id']
    else:
        # The inviter starts a new household as its owner
        library_id = (conn.execute('SELECT MAX(library_id) FROM library_members').fetchone()[0] or 0) + 1
        conn.execute('''
            INSERT INTO library_members (library_id, user_id, role, added_by)
            VALUES (?, ?, 'owner', ?)
        ''', (library_id, inviter_id, inviter_id))
    conn.execute('''
        INSERT INTO library_members (library_id, user_id, role, added_by)
        VALUES (?, ?, 'member', ?)
    ''', (library_id, user_id, inviter_id))
    # A user can only be in one household: their other invites are moot now
    conn.execute('DELETE FROM household_invites WHERE invitee_id = ?', (user_id,))
    conn.execute('''
        INSERT INTO notifications (user_id, type, message, from_user_id)
        VALUES (?, 'household_accept', ?, ?)
    ''', (inviter_id, f'{user_name} joined your household.', user_id))
    return inv['inviter_name']


def decline(conn, invite_id, user_id):
    """Decline (as invitee) or cancel (as inviter) an invite."""
    cur = conn.execute('''
        DELETE FROM household_invites WHERE id = ? AND (invitee_id = ? OR inviter_id = ?)
    ''', (invite_id, user_id, user_id))
    if cur.rowcount == 0:
        raise HouseholdError('Invite not found.')


def leave(conn, user_id):
    """Take user_id out of their household, keeping it consistent.

    If they were the owner, the longest-standing member becomes owner. If
    one person is left, the household is dissolved. Returns False if the
    user wasn't in a household. Used for leaving, owner removal and admin
    removal alike.
    """
    row = membership(conn, user_id)
    if not row:
        return False
    library_id = row['library_id']
    conn.execute('DELETE FROM library_members WHERE user_id = ?', (user_id,))
    # Invites the owner sent are on behalf of this household
    if row['role'] == 'owner':
        conn.execute('DELETE FROM household_invites WHERE inviter_id = ?', (user_id,))

    rest = conn.execute('''
        SELECT id, role FROM library_members WHERE library_id = ? ORDER BY added_at, id
    ''', (library_id,)).fetchall()
    if len(rest) == 1:
        conn.execute('DELETE FROM library_members WHERE id = ?', (rest[0]['id'],))
    elif rest and not any(r['role'] == 'owner' for r in rest):
        conn.execute("UPDATE library_members SET role = 'owner' WHERE id = ?", (rest[0]['id'],))
    return True


def remove(conn, actor_id, target_id):
    """actor removes target from the household: only the owner may, or
    anyone removing themselves (leaving)."""
    if actor_id != target_id:
        actor, target = membership(conn, actor_id), membership(conn, target_id)
        if not actor or not target or actor['library_id'] != target['library_id']:
            raise HouseholdError('They are not in your household.')
        if actor['role'] != 'owner':
            raise HouseholdError('Only the owner of the household can remove people.')
    if not leave(conn, target_id):
        raise HouseholdError('Not in a household.')


def member_choice(conn, user_id, requested=()):
    """The household pages' member row (Books, Movies and Music, Household).

    Returns (others, owner_ids, chosen): the other members as rows (id,
    username, avatar_url) for the chips, whose items to show, and the chosen
    members' ids (a list, empty for everyone). `requested` is the ?member=
    values (any number, Phil 2026-11-09): those members' items and yours
    together, as one shelf (one member alone is their profile's job). Ids
    of people outside your household are ignored; none left means everyone.
    """
    from models import get_library_members
    everyone = get_library_members(user_id, conn)
    marks = ','.join('?' * len(everyone))
    others = conn.execute(f'''
        SELECT id, username, avatar_url FROM users
        WHERE id IN ({marks}) AND id != ? ORDER BY username COLLATE NOCASE
    ''', (*everyone, user_id)).fetchall()
    ids = {o['id'] for o in others}
    chosen = sorted({r for r in requested if r in ids})
    if chosen:
        return others, [user_id, *chosen], chosen
    return others, everyone, []

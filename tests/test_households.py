"""Households need consent to join; only the owner removes; anyone leaves
(utils/households.py, Phase 4).

people: alice (admin, household owner) + bob (member); carol is alice's friend.
"""
from conftest import add_user, login, make_friends, scalar


def role(db, user_id):
    row = db.execute('SELECT role FROM library_members WHERE user_id = ?', (user_id,)).fetchone()
    return row['role'] if row else None


def invite_id(db, inviter, invitee):
    return scalar(db, 'SELECT id FROM household_invites WHERE inviter_id = ? AND invitee_id = ?',
                  inviter, invitee)


def test_invite_does_not_add_until_accepted(client, db, people):
    login(client, 'alice')
    client.post(f"/user/household/invite/{people['carol']}")
    assert role(db, people['carol']) is None
    iid = invite_id(db, people['alice'], people['carol'])
    assert iid

    login(client, 'carol')
    page = client.get('/friends/notifications_page').get_data(as_text=True)
    assert 'Household Invites' in page
    assert client.get('/friends/notification_count').get_json()['household_invites'] == 1
    client.post(f'/user/household/accept/{iid}')
    assert role(db, people['carol']) == 'member'
    assert scalar(db, 'SELECT COUNT(*) FROM household_invites') == 0
    # alice hears about it
    assert scalar(db, "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND type = 'household_accept'",
                  people['alice']) == 1


def test_decline_and_cancel(client, db, people):
    login(client, 'alice')
    client.post(f"/user/household/invite/{people['carol']}")
    iid = invite_id(db, people['alice'], people['carol'])
    login(client, 'carol')
    client.post(f'/user/household/decline/{iid}')
    assert role(db, people['carol']) is None
    assert scalar(db, 'SELECT COUNT(*) FROM household_invites') == 0

    login(client, 'alice')
    client.post(f"/user/household/invite/{people['carol']}")
    iid = invite_id(db, people['alice'], people['carol'])
    client.post(f'/user/household/decline/{iid}', data={'cancel': '1'})
    assert scalar(db, 'SELECT COUNT(*) FROM household_invites') == 0


def test_only_invitee_can_accept(client, db, people):
    login(client, 'alice')
    client.post(f"/user/household/invite/{people['carol']}")
    iid = invite_id(db, people['alice'], people['carol'])
    login(client, 'bob')
    client.post(f'/user/household/accept/{iid}')
    assert role(db, people['carol']) is None
    assert invite_id(db, people['alice'], people['carol']) == iid


def test_only_friends_and_owners_can_invite(client, db, people):
    dave = add_user(db, 'dave')
    login(client, 'alice')
    client.post(f'/user/household/invite/{dave}')          # not a friend
    make_friends(db, people['bob'], people['carol'])
    login(client, 'bob')
    client.post(f"/user/household/invite/{people['carol']}")  # bob is a member, not owner
    assert scalar(db, 'SELECT COUNT(*) FROM household_invites') == 0


def test_invite_from_someone_without_a_household_starts_one(client, db, people):
    dave = add_user(db, 'dave')
    make_friends(db, people['carol'], dave)
    login(client, 'carol')
    client.post(f'/user/household/invite/{dave}')
    login(client, 'dave')
    client.post(f"/user/household/accept/{invite_id(db, people['carol'], dave)}")
    assert role(db, people['carol']) == 'owner' and role(db, dave) == 'member'


def test_member_cannot_remove_owner(client, db, people):
    login(client, 'bob')
    client.post(f"/user/household/remove/{people['alice']}")
    assert role(db, people['alice']) == 'owner' and role(db, people['bob']) == 'member'


def test_owner_removes_member_and_household_of_one_dissolves(client, db, people):
    login(client, 'alice')
    client.post(f"/user/household/remove/{people['bob']}")
    assert role(db, people['bob']) is None
    assert role(db, people['alice']) is None


def test_owner_leaving_hands_over(client, db, people):
    carol = people['carol']
    db.execute("INSERT INTO library_members (library_id, user_id, role) VALUES (?, ?, 'member')",
               (people['alice'], carol))
    db.commit()
    login(client, 'alice')
    client.post(f"/user/household/remove/{people['alice']}")
    assert role(db, people['alice']) is None
    assert role(db, people['bob']) == 'owner'      # longest-standing member
    assert role(db, carol) == 'member'


def test_member_can_leave(client, db, people):
    login(client, 'bob')
    client.post(f"/user/household/remove/{people['bob']}")
    assert role(db, people['bob']) is None


def test_profile_shows_the_right_household_button(client, db, people):
    login(client, 'alice')
    assert 'Remove from Household' in client.get('/user/bob').get_data(as_text=True)
    assert 'Invite to Household' in client.get('/user/carol').get_data(as_text=True)
    login(client, 'bob')
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'Leave Household' in page and 'Remove from Household' not in page

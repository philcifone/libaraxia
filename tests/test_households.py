"""Households need consent to join; only the owner removes; anyone leaves
(utils/households.py, Phase 4).

people: alice (admin, household owner) + bob (member); carol is alice's friend.
"""
from conftest import add_book, add_user, login, make_friends, scalar


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
    assert 'data-action="household-remove"' in client.get('/user/bob').get_data(as_text=True)
    assert f'action="/user/household/invite/{people["carol"]}"' in client.get('/user/carol').get_data(as_text=True)
    login(client, 'bob')
    page = client.get('/user/alice').get_data(as_text=True)
    assert 'data-action="household-leave"' in page and 'data-action="household-remove"' not in page


def test_member_row_on_every_household_page(client, db, people):
    """Household Books, Movies and Music share one member row (Phil,
    2026-11-09): Everyone, then each other member; a chip shows that
    member's items and yours together, and chips toggle so several can be
    on. Someone outside the household is ignored."""
    from test_records import add_record
    from test_videos import add_video
    alice, bob, carol = people['alice'], people['bob'], people['carol']
    dave = add_user(db, 'dave')                    # a third household member
    db.execute("INSERT INTO library_members (library_id, user_id, role) VALUES (?, ?, 'member')", (alice, dave))
    db.commit()
    add_book(db, dave, 'Daves Book'); add_video(db, dave, 'Daves Film'); add_record(db, dave, 'Daves Album')
    add_book(db, alice, 'Alices Book'); add_book(db, bob, 'Bobs Book')
    add_video(db, alice, 'Alices Film'); add_video(db, bob, 'Bobs Film')
    add_record(db, alice, 'Alices Album'); add_record(db, bob, 'Bobs Album')
    add_video(db, carol, 'Carols Film')            # a friend, not household
    login(client, 'alice')
    for url, mine, bobs, daves in (('/base/shared-library', 'Alices Book', 'Bobs Book', 'Daves Book'),
                                   ('/videos/shared', 'Alices Film', 'Bobs Film', 'Daves Film'),
                                   ('/records/shared', 'Alices Album', 'Bobs Album', 'Daves Album')):
        html = client.get(url).get_data(as_text=True)
        row = html[html.index('aria-label="Whose items"'):]
        row = row[:row.index('</nav>')]
        assert 'Everyone' in row and 'bob' in row and 'carol' not in row and '>alice' not in row
        assert mine in html and bobs in html and daves in html
        # bob's chip: bob's and yours together, not dave's
        with_bob = client.get(f'{url}?member={bob}').get_data(as_text=True)
        assert bobs in with_bob and mine in with_bob and daves not in with_bob
        # chips toggle: with bob on, dave's chip adds dave and bob's takes bob out
        assert f'{url}?member={bob}&amp;member={dave}' in with_bob
        assert f'href="{url}" class="member-chip card-link is-on"' in with_bob
        both = client.get(f'{url}?member={bob}&member={dave}').get_data(as_text=True)
        assert bobs in both and daves in both and mine in both
        # carol isn't in the household: her id shows everyone's, never hers
        not_member = client.get(f'{url}?member={carol}').get_data(as_text=True)
        assert 'class="member-chip card-link is-on"' in not_member.split('Everyone')[0][-200:]   # Everyone stays on
        assert mine in not_member and 'Carols Film' not in not_member


def test_member_row_without_a_household(client, db, people):
    login(client, 'carol')
    html = client.get('/videos/shared').get_data(as_text=True)
    assert "You're not sharing a library with anyone yet" in html
    assert 'aria-label="Whose items"' not in html


def test_member_row_label_per_section(client, db, people):
    login(client, 'alice')
    for url, word in (('/base/shared-library', 'books'), ('/videos/shared', 'movies and TV'), ('/records/shared', 'music')):
        html = client.get(url).get_data(as_text=True)
        assert f'Your shared {word} with</p>' in html

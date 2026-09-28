from fastapi.testclient import TestClient
from app.main import app
from app.services.account_policy import validate_username

B = '/api/halaqat/mosques/1'


def test_guardian_repair_preserves_history_and_other_children(network):
    n = network
    owner = n['owner']
    url = f"{B}/students/{n['ids'][0]}"
    other = n['students'][1]
    other_id = other.get('/api/halaqat/context').json()['user']['id']
    assert owner.put(url+'/recipient', json={'user_id':other_id, 'recipient_type':'guardian'}).status_code == 200
    from app.api.student_file import today
    assert n['teachers'][0].post(url+'/progress', json={'day':str(today()), 'memorized':'الفاتحة', 'memorized_amount':1}).status_code == 200
    payload = {'recipient_type':'guardian', 'full_name':'عبد الخالق الشهري', 'username':'عبد الخالق_الشهري', 'temporary_password':''}
    invalid = owner.post(url+'/recipient-account', json=payload)
    assert invalid.status_code == 422
    assert 'عبد_الخالق_الشهري' in invalid.json()['detail']
    assert other.get(url+'/file').status_code == 200
    payload['username'] = 'عبد_الخالق_الشهري'
    result = owner.post(url+'/recipient-account', json=payload)
    assert result.status_code == 200, result.text
    created = result.json()
    assert created['user']['account_type'] == 'guardian'
    assert owner.post(url+'/recipient-account', json=payload).status_code == 409
    assert other.get(url+'/file').status_code == 404
    assert other.get(f"{B}/students/{n['ids'][1]}/file").status_code == 200
    with TestClient(app) as parent:
        login = parent.post('/login', data={'identity':payload['username'], 'password':created['temporary_password']}, follow_redirects=False)
        assert login.status_code == 303
        assert login.headers['location'] == '/account/security'
        changed = parent.post('/account/security', data={'current_password':created['temporary_password'], 'new_password':'NewParent1@', 'confirm_password':'NewParent1@'}, follow_redirects=False)
        assert changed.status_code == 303
        saved = parent.get(url+'/file')
        assert saved.status_code == 200
        assert saved.json()['progress'][0]['memorized'] == 'الفاتحة'
        assert parent.get(f"{B}/students/{n['ids'][1]}/file").status_code == 404


def test_username_spaces_and_arabic():
    assert not validate_username('عبد الخالق_الشهري')[0]
    assert validate_username('عبد_الخالق_الشهري')[0]
